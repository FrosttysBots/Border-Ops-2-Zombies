"""Bounded, nonblocking pose IPC. Lossy snapshots only, never combat commands."""
import json
import math
import re
import socket
import time
import uuid
from pathlib import Path

MAX_BYTES = 8192
ENDPOINT_FILE = 'blacklands_runtime_endpoint.json'


def identifier(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{32}', value) is not None


def read_endpoint(path):
    with Path(path).open('rb') as stream:
        raw = stream.read(MAX_BYTES+1)
    if len(raw) > MAX_BYTES:
        raise ValueError('Oversized runtime endpoint')
    endpoint = json.loads(raw)
    if (endpoint.get('schema') != 1 or endpoint.get('transport') != 'udp_loopback'
            or endpoint.get('host') != '127.0.0.1'
            or type(endpoint.get('port')) is not int or not 1 <= endpoint['port'] <= 65535
            or not identifier(endpoint.get('epoch')) or not identifier(endpoint.get('token'))
            or endpoint.get('capabilities') != ['bl2_pose_readonly']
            or endpoint.get('max_bytes') != MAX_BYTES):
        raise ValueError('Unsupported runtime endpoint')
    return endpoint


def coordinates(values):
    values = list(values)
    if len(values) != 3 or any(type(v) not in (int,float) or not math.isfinite(v)
                               or abs(v) > 100_000_000 for v in values):
        raise ValueError('Invalid native coordinates')
    return values


class Publisher:
    def __init__(self, endpoint_path, *, origin='native_bl2'):
        if origin not in ('native_bl2', 'synthetic_test'):
            raise ValueError('Invalid observation origin')
        self.endpoint = read_endpoint(endpoint_path)
        self.origin = origin
        self.session = uuid.uuid4().hex
        self.seq = 0
        self.started = time.monotonic()
        self.last_ack = None
        self.ack_seq = 0
        self.ack_count = 0
        self.last_rtt_ms = None
        self.skipped = 0
        self.closed = False
        self.pending = {}
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self.socket.setblocking(False)
            self.socket.connect((self.endpoint['host'], self.endpoint['port']))
        except Exception:
            self.socket.close()
            raise

    def send(self, position, angles, weapon):
        if self.closed:
            raise RuntimeError('Publisher closed')
        if weapon is not None and (not isinstance(weapon,str) or len(weapon.encode('utf-8'))>512):
            raise ValueError('Invalid weapon identity')
        now = time.monotonic()
        self.seq += 1
        sent_us = int((now-self.started)*1_000_000)
        packet = dict(schema=1,kind='pose',source='bl2',origin=self.origin,
                      epoch=self.endpoint['epoch'],token=self.endpoint['token'],session=self.session,
                      seq=self.seq,sent_us=sent_us,position=coordinates(position),
                      angles=coordinates(angles),weapon=weapon)
        encoded = json.dumps(packet,allow_nan=False,separators=(',',':')).encode('utf-8')
        if len(encoded)>MAX_BYTES:
            raise ValueError('Oversized pose')
        self.poll()
        try:
            self.socket.send(encoded)
        except OSError:
            self.skipped += 1
            return False
        self.pending[self.seq] = (sent_us, now)
        while len(self.pending)>128:
            self.pending.pop(next(iter(self.pending)))
        return True

    def poll(self):
        # Fixed work bound: no blocking waits or unbounded drain on the game thread.
        for _ in range(8):
            try:
                raw = self.socket.recv(MAX_BYTES+1)
            except OSError:
                break
            try:
                if len(raw)>MAX_BYTES:
                    continue
                ack = json.loads(raw)
                if (ack.get('schema') != 1 or ack.get('kind') != 'ack'
                        or ack.get('epoch') != self.endpoint['epoch']
                        or ack.get('session') != self.session
                        or type(ack.get('seq')) is not int or ack['seq'] <= self.ack_seq):
                    continue
                pending = self.pending.get(ack['seq'])
                if pending is None or ack.get('sent_us') != pending[0]:
                    continue
                self.last_ack = time.monotonic()
                self.last_rtt_ms = (self.last_ack-pending[1])*1000
                self.ack_seq = ack['seq']
                self.ack_count += 1
                for seq in list(self.pending):
                    if seq <= self.ack_seq:
                        del self.pending[seq]
            except (ValueError, TypeError, KeyError, AttributeError):
                continue

    def status(self):
        online = (not self.closed and self.ack_count >= 2 and self.last_ack is not None
                  and time.monotonic()-self.last_ack <= 2)
        return dict(online=online,origin=self.origin,session=self.session,sent=self.seq,
                    ack_seq=self.ack_seq,ack_count=self.ack_count,skipped=self.skipped,
                    last_rtt_ms=self.last_rtt_ms)

    def close(self):
        self.socket.close()
        self.closed = True
        self.pending.clear()
