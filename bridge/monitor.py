"""Observe bootstrap files. Never writes to either game or sends gameplay commands."""
import argparse
import json
import time
from pathlib import Path
from wire import DONOR_FILE, HOST_FILE, Freshness, parse_donor, parse_host, read_bounded


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mailbox", required=True, type=Path)
    parser.add_argument("--seconds", type=float, default=0, help="0 runs until Ctrl+C")
    args = parser.parse_args()
    peers = {"bo2": Freshness(), "bl2": Freshness()}
    last_output = None
    started = time.monotonic()
    print("Read-only passthrough monitor. ONLINE requires changing native snapshots.")
    while not args.seconds or time.monotonic() - started < args.seconds:
        now = time.monotonic()
        frames, errors = {}, {}
        for name, filename, decode in [("bo2", HOST_FILE, parse_host), ("bl2", DONOR_FILE, parse_donor)]:
            try:
                frame = decode(read_bounded(args.mailbox / filename))
                key = (frame.get("session"), frame["seq"], frame.get("game_ms"))
                peers[name].observe(key, now)
                frames[name] = frame
            except (OSError, ValueError, KeyError, TypeError) as exc:
                errors[name] = str(exc)
        online = {name: name in frames and peer.online(now) for name, peer in peers.items()}
        status = {"bo2_online": online["bo2"], "bl2_online": online["bl2"],
                  "bl2_acknowledges_host": online["bo2"] and online["bl2"] and
                  frames["bl2"]["host_seq"] is not None and
                  0 <= frames["bo2"]["seq"] - frames["bl2"]["host_seq"] <= 8,
                  "errors": errors}
        output = json.dumps(status, sort_keys=True)
        if output != last_output:
            print(output, flush=True)
            last_output = output
        time.sleep(0.1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Monitor stopped.")
