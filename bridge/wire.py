"""Bootstrap snapshot protocol. No executable commands or gameplay mutations."""
import json
import math
import os
import re
from pathlib import Path

MAX_BYTES = 8192
HOST_FILE = "blacklands_host.txt"
DONOR_FILE = "blacklands_bl2.json"
REPLY_FILE = "blacklands_reply.txt"
WEAPON_FILE = "blacklands_weapon.json"


def read_bounded(path):
    with Path(path).open("rb") as stream:
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("Oversized frame")
    return data.decode("utf-8")


def integer(value, maximum=2**31 - 1):
    if isinstance(value, bool) or not re.fullmatch(r"\d{1,10}", str(value)):
        raise ValueError("Invalid integer")
    result = int(value)
    if not 0 <= result <= maximum:
        raise ValueError("Integer outside range")
    return result


def vector(values):
    if len(values) != 3:
        raise ValueError("Expected three coordinates")
    result = [float(v) for v in values]
    if not all(math.isfinite(v) and abs(v) <= 100_000_000 for v in result):
        raise ValueError("Invalid coordinates")
    return result


def parse_host(text):
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise ValueError("Oversized frame")
    fields = text.strip().split("|")
    if len(fields) != 13 or fields[0] != "BLPT1" or fields[-1] != "END":
        raise ValueError("Incomplete/unsupported host frame")
    if not re.fullmatch(r"[A-Za-z0-9_./:-]{1,128}", fields[11]):
        raise ValueError("Invalid weapon identifier")
    return dict(schema=1, source="bo2", seq=integer(fields[1]),
                game_ms=integer(fields[2]), position=vector(fields[3:6]),
                angles=vector(fields[6:9]), health=integer(fields[9], 1_000_000),
                round=integer(fields[10], 1_000_000), weapon=fields[11])


def parse_donor(text):
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise ValueError("Oversized frame")
    frame = json.loads(text)
    if not isinstance(frame, dict) or frame.get("schema") != 1 or frame.get("source") != "bl2":
        raise ValueError("Unsupported donor frame")
    integer(frame["seq"])
    if frame["host_seq"] is not None:
        integer(frame["host_seq"])
    if not isinstance(frame["session"], str) or not re.fullmatch(r"[0-9a-f]{32}", frame["session"]):
        raise ValueError("Invalid donor session")
    if frame["position"] is not None:
        vector(frame["position"])
    if not isinstance(frame["weapon"], str) or len(frame["weapon"]) > 512:
        raise ValueError("Invalid weapon path")
    return frame


def write_atomic(path, text):
    path = Path(path)
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise ValueError("Oversized output")
    # One SDK writer; replace only after the entire snapshot has been written.
    temp = path.with_name(path.name + ".tmp")
    try:
        with temp.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def parse_weapon(text):
    """Validate the separate diagnostic packet before presenting native data."""
    if len(text.encode('utf-8')) > MAX_BYTES:
        raise ValueError('Oversized weapon frame')
    frame = json.loads(text)
    if not isinstance(frame, dict) or frame.get('schema') != 1 or frame.get('source') != 'bl2_weapon':
        raise ValueError('Unsupported weapon frame')
    integer(frame['seq'])
    if not isinstance(frame['session'], str) or not re.fullmatch(r'[0-9a-f]{32}', frame['session']):
        raise ValueError('Invalid weapon session')
    weapon = frame['weapon']
    if weapon is None:
        return frame
    if not isinstance(weapon, dict):
        raise ValueError('Invalid weapon details')
    for key, limit in [('object_path', 512), ('display_name', 256)]:
        value = weapon[key]
        if value is None and key == 'display_name':
            continue
        if not isinstance(value, str) or len(value) > limit:
            raise ValueError('Invalid weapon text')
    sections = ['definitions', 'native_properties', 'unavailable']
    sections += [key for key in ('native_getters', 'native_state') if key in weapon]
    for key in sections:
        values = weapon[key]
        if not isinstance(values, dict) or len(values) > (64 if key == 'unavailable' else 32):
            raise ValueError('Invalid weapon fields')
        for name, value in values.items():
            if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]{0,63}', name):
                raise ValueError('Invalid field name')
            if value is None and key != 'unavailable':
                continue
            if key == 'native_state':
                if type(value) is bool:
                    continue
                raise ValueError('Invalid state value')
            if isinstance(value, str) and key in ('definitions', 'unavailable') and len(value) <= 512:
                continue
            if key != 'unavailable' and type(value) in (int, float) and math.isfinite(value):
                continue
            raise ValueError('Invalid field value')
    return frame


class Freshness:
    """A pre-existing snapshot starts offline; two changing samples prove progress."""
    def __init__(self, timeout=2.0):
        self.timeout = timeout
        self.key = None
        self.last_progress = None

    def observe(self, key, now):
        if key != self.key:
            if self.key is not None:
                self.last_progress = now
            self.key = key

    def online(self, now):
        return self.last_progress is not None and 0 <= now - self.last_progress <= self.timeout
