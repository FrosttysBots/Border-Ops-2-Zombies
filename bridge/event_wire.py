"""Bounded diagnostic event transport, with explicit eviction accounting."""
from collections import deque
import json
import math
import re

EVENT_FILE = 'blacklands_events.json'
MAX_EVENT_BYTES = 262144
CAPACITY = 128
KINDS = {'consume_ammo', 'fire_mode', 'projectile', 'reload_begin', 'reload_done', 'display_damage',
         'fire_begin', 'projectile_spawn', 'take_damage', 'impact_begin', 'impact_end'}


class EventBuffer:
    def __init__(self):
        self.events = deque(maxlen=CAPACITY)
        self.last_id = 0
        self.evicted = 0

    def append(self, kind, elapsed_ms, weapon, data):
        if kind not in KINDS:
            raise ValueError('Unknown event kind')
        if len(self.events) == CAPACITY:
            self.evicted += 1
        self.last_id += 1
        self.events.append(dict(id=self.last_id, elapsed_ms=elapsed_ms, kind=kind,
                                weapon=weapon, data=data))


def parse_events(text):
    if len(text.encode('utf-8')) > MAX_EVENT_BYTES:
        raise ValueError('Oversized event packet')
    packet = json.loads(text)
    if not isinstance(packet, dict) or packet.get('schema') != 1 or packet.get('source') != 'bl2_events':
        raise ValueError('Unsupported event packet')
    for name in ('capture_id', 'donor_session'):
        if not isinstance(packet[name], str) or not re.fullmatch('[0-9a-f]{32}', packet[name]):
            raise ValueError('Invalid event session')
    for name in ('seq', 'last_id', 'evicted', 'errors'):
        if type(packet[name]) is not int or not 0 <= packet[name] <= 2**31-1:
            raise ValueError('Invalid event counter')
    if type(packet['active']) is not bool:
        raise ValueError('Invalid capture state')
    if not isinstance(packet['events'], list) or len(packet['events']) > CAPACITY:
        raise ValueError('Invalid event list')
    previous = packet['evicted']
    for event in packet['events']:
        if type(event['id']) is not int or event['id'] != previous+1:
            raise ValueError('Noncontiguous event IDs')
        previous = event['id']
        if type(event['elapsed_ms']) is not int or not 0 <= event['elapsed_ms'] <= 181000:
            raise ValueError('Invalid event timestamp')
        if event['kind'] not in KINDS:
            raise ValueError('Invalid event kind')
        if event['weapon'] is not None and (not isinstance(event['weapon'], str) or len(event['weapon']) > 256):
            raise ValueError('Invalid weapon path')
        if not isinstance(event['data'], dict) or len(event['data']) > 12:
            raise ValueError('Invalid event data')
        for key, value in event['data'].items():
            if not re.fullmatch('[a-z_]{1,40}', key):
                raise ValueError('Invalid event field')
            if value is None or type(value) is bool:
                continue
            if type(value) in (int, float) and math.isfinite(value) and abs(value) <= 1e15:
                continue
            if isinstance(value, str) and len(value) <= 256:
                continue
            raise ValueError('Invalid event value')
    if previous != packet['last_id']:
        raise ValueError('Event count mismatch')
    return packet
