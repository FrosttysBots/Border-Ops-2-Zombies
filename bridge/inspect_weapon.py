"""Observe current weapon details; stale packets never count as live proof."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
from wire import DONOR_FILE, WEAPON_FILE, Freshness, parse_donor, parse_weapon, read_bounded


def matches_donor(detail, donor):
    path = 'None' if detail['weapon'] is None else detail['weapon']['object_path']
    return (detail['session'] == donor['session'] and
            0 <= donor['seq'] - detail['seq'] <= 8 and path == donor['weapon'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mailbox', type=Path, default=Path(os.environ.get('LOCALAPPDATA', '.')) /
                        'Plutonium/storage/t6/raw/scriptdata')
    parser.add_argument('--seconds', type=float, default=3)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.seconds <= 0:
        parser.error('--seconds must be positive')
    freshness = Freshness()
    latest = None
    error = None
    live = False
    started = time.monotonic()
    while time.monotonic() - started < args.seconds:
        live = False
        try:
            detail = parse_weapon(read_bounded(args.mailbox / WEAPON_FILE))
            donor = parse_donor(read_bounded(args.mailbox / DONOR_FILE))
            now = time.monotonic()
            freshness.observe((detail['session'], detail['seq']), now)
            live = freshness.online(now) and matches_donor(detail, donor)
            latest = detail
            error = None
        except (OSError, ValueError, KeyError, TypeError) as exc:
            error = str(exc)
        time.sleep(0.1)
    report = dict(observed_at=datetime.now(timezone.utc).isoformat(), live=live,
                  weapon_equipped=live and latest['weapon'] is not None,
                  error=error, snapshot=latest,
                  interpretation='Native fields only; not final damage or a complete item card.')
    text = json.dumps(report, indent=2, allow_nan=False) + '\n'
    print(text)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding='utf-8')
    return 0 if live else 1


if __name__ == '__main__':
    raise SystemExit(main())
