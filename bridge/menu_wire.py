"""Narrow, expiring native-inventory requests; separate from telemetry."""
import json
import re

STATUS_FILE = 'blacklands_menu_status.json'
REQUEST_FILE = 'blacklands_menu_request.json'
MAX_BYTES = 8192


def uuid_hex(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{32}', value):
        raise ValueError('Invalid activation/session ID')
    return value


def integer(value, low=0, high=2**53-1):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('Invalid integer')
    return value


def read_packet(path):
    with path.open('rb') as stream:
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError('Oversized menu packet')
    result = json.loads(data)
    if not isinstance(result, dict):
        raise ValueError('Expected menu object')
    return result


def write_packet(path, packet):
    data = json.dumps(packet, allow_nan=False) + '\n'
    if len(data.encode('utf-8')) > MAX_BYTES:
        raise ValueError('Oversized menu packet')
    temp = path.with_suffix('.tmp')
    try:
        temp.write_text(data, encoding='utf-8')
        temp.replace(path)
    except OSError as exc:
        if getattr(exc, 'winerror', None) not in (5, 32, 33):
            raise
        return False
    return True


def validate_request(packet, activation, donor_session, wall_ms):
    keys = {'schema', 'activation', 'donor_session', 'seq', 'action', 'created_ms', 'expires_ms'}
    if set(packet) != keys or type(packet['schema']) is not int or packet['schema'] != 1:
        raise ValueError('Unsupported menu request')
    if uuid_hex(packet['activation']) != activation or uuid_hex(packet['donor_session']) != donor_session:
        raise ValueError('Old or foreign activation')
    integer(packet['seq'], 1, 128)
    if packet['action'] != 'open_inventory':
        raise ValueError('Only open_inventory is supported')
    created = integer(packet['created_ms']); expires = integer(packet['expires_ms'])
    if not 0 < expires-created <= 2000 or created > wall_ms + 250:
        raise ValueError('Invalid request deadline')
    return expires >= wall_ms


def validate_status(packet):
    if packet.get('schema') != 1 or packet.get('source') != 'bl2_menu_control':
        raise ValueError('Unsupported menu status')
    uuid_hex(packet.get('activation')); uuid_hex(packet.get('donor_session'))
    integer(packet.get('seq')); integer(packet.get('last_request'), 0, 128)
    if type(packet.get('active')) is not bool:
        raise ValueError('Invalid menu lifecycle')
    return packet


class MenuGate:
    """At-most-once invocation per explicit activation, observed completion only."""
    def __init__(self, activation, donor_session):
        self.activation = activation
        self.donor_session = donor_session
        self.last_request = 0
        self.result = None
        self.pending_until = None

    def submit(self, packet, wall_ms, now, menu_screens, invoke):
        fresh = validate_request(packet, self.activation, self.donor_session, wall_ms)
        if packet['seq'] <= self.last_request or self.pending_until is not None:
            return
        if packet['seq'] != self.last_request + 1:
            raise ValueError('Noncontiguous request sequence')
        # Reserve before calling native code, including when it raises or reenters.
        self.last_request = packet['seq']
        self.result = dict(seq=self.last_request, state='expired' if not fresh else 'awaiting_menu')
        if not fresh:
            return
        if menu_screens:
            self.result['state'] = 'already_open' if 3 in menu_screens else 'other_menu_open'
            return
        self.pending_until = now + 2
        try:
            invoke()
        except Exception as exc:
            self.pending_until = None
            self.result.update(state='native_error', error=type(exc).__name__)

    def observe(self, menu_screens, now):
        if self.pending_until is None:
            return
        if 3 in menu_screens:
            self.result['state'] = 'opened'
        elif now >= self.pending_until:
            self.result['state'] = 'unconfirmed'
        else:
            return
        self.pending_until = None

    def cancel(self):
        if self.pending_until is not None:
            self.result['state'] = 'cancelled'
            self.pending_until = None
