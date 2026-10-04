"""Inspect bounded native event capture, preserving gaps and attribution limits."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
from event_wire import EVENT_FILE, MAX_EVENT_BYTES, parse_events
from wire import Freshness


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mailbox', type=Path, default=Path(os.environ.get('LOCALAPPDATA', '.')) /
                        'Plutonium/storage/t6/raw/scriptdata')
    parser.add_argument('--seconds', type=float, default=2)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if not 0 < args.seconds <= 60:
        parser.error('Observation must be between 0 and 60 seconds')
    freshness = Freshness()
    packet = None
    error = None
    started = time.monotonic()
    while time.monotonic()-started < args.seconds:
        try:
            with (args.mailbox/EVENT_FILE).open('rb') as stream:
                data = stream.read(MAX_EVENT_BYTES+1)
            packet = parse_events(data.decode('utf-8'))
            freshness.observe((packet['capture_id'], packet['seq']), time.monotonic())
            error = None
        except (OSError, ValueError, KeyError, TypeError) as exc:
            error = str(exc)
        time.sleep(0.1)
    live = error is None and packet is not None and packet['active'] and freshness.online(time.monotonic())
    counts = dict(Counter(e['kind'] for e in packet['events'])) if packet else {}
    summary = dict(observed_at=datetime.now(timezone.utc).isoformat(), live=bool(live),
                   retained_event_counts=counts, error=error,
                   evicted=packet['evicted'] if packet else None,
                   callback_errors=packet['errors'] if packet else None,
                   limitation='Function calls are not normalized shots. Damage display events have no proven shot attribution.')
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(summary|{'packet':packet},indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary,indent=2))
    return 0 if packet is not None and error is None else 1


if __name__ == '__main__':
    raise SystemExit(main())
