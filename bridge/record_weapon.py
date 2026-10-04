"""Record bounded native observations, not commands or authoritative shot events."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
from inspect_weapon import matches_donor
from wire import DONOR_FILE, WEAPON_FILE, Freshness, parse_donor, parse_weapon, read_bounded


def transition(previous, current):
    if previous is None or any(previous[k] != current[k] for k in ('session', 'object_path')):
        return None
    if not 0 < current['seq'] - previous['seq'] <= 8 or current['elapsed'] - previous['elapsed'] > 2:
        return None
    before, after = previous['getters'].get('GetAmmoCount'), current['getters'].get('GetAmmoCount')
    if before is None or after is None or before == after:
        return None
    return dict(elapsed=current['elapsed'], before=before, after=after,
                kind='ammo_decreased' if after < before else 'ammo_increased')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mailbox', type=Path, default=Path(os.environ.get('LOCALAPPDATA', '.')) /
                        'Plutonium/storage/t6/raw/scriptdata')
    parser.add_argument('--seconds', type=float, default=45)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not 0 < args.seconds <= 180:
        parser.error('--seconds must be between 0 and 180')
    started = time.monotonic()
    freshness = Freshness()
    samples, transitions = [], []
    previous = None
    last_key = None
    errors = set()
    print('Recording native weapon data. Gameplay stays under user control.', flush=True)
    while time.monotonic() - started < args.seconds:
        now = time.monotonic()
        try:
            frame = parse_weapon(read_bounded(args.mailbox / WEAPON_FILE))
            donor = parse_donor(read_bounded(args.mailbox / DONOR_FILE))
            key = (frame['session'], frame['seq'])
            freshness.observe(key, now)
            if not freshness.online(now) or not matches_donor(frame, donor) or frame['weapon'] is None:
                previous = None
            elif key != last_key:
                weapon = frame['weapon']
                sample = dict(elapsed=round(now-started, 3), session=frame['session'], seq=frame['seq'],
                              object_path=weapon['object_path'], name=weapon['display_name'],
                              properties=weapon['native_properties'], getters=weapon.get('native_getters', {}),
                              state=weapon.get('native_state', {}))
                event = transition(previous, sample)
                if event:
                    transitions.append(event)
                samples.append(sample)
                previous, last_key = sample, key
        except (OSError, ValueError, KeyError, TypeError) as exc:
            previous = None
            if len(errors) < 8:
                errors.add(str(exc)[:256])
        time.sleep(0.1)
    report = dict(observed_at=datetime.now(timezone.utc).isoformat(), samples=samples,
                  transitions=transitions, errors=sorted(errors),
                  limitation='4 Hz polling can miss intermediate changes. Ammo changes are not exact shot events.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    print(json.dumps(dict(samples=len(samples), transitions=transitions, errors=sorted(errors)), indent=2))
    return 0 if len(samples) > 1 else 1


if __name__ == '__main__':
    raise SystemExit(main())
