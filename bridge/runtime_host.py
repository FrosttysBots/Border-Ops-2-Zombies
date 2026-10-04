"""Launch the finite Rust sidecar with a private local endpoint and single-owner lock."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import uuid


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=int, default=180)
    parser.add_argument('--mailbox',type=Path,default=Path(os.environ.get('LOCALAPPDATA','.'))/'Plutonium/storage/t6/raw/scriptdata')
    parser.add_argument('--report',type=Path,default=Path(__file__).resolve().parents[1]/'work/runtime-status.json')
    parser.add_argument('--binary',type=Path,default=Path(__file__).resolve().parents[1]/'work/runtime-target/debug/blacklands-runtime.exe')
    args=parser.parse_args()
    if not 1<=args.seconds<=180:
        parser.error('Duration must be 1..180 seconds')
    if not args.mailbox.is_dir() or not args.binary.is_file():
        parser.error('Mailbox or built Rust binary missing')
    args.report.parent.mkdir(parents=True,exist_ok=True)
    import msvcrt
    with (args.mailbox/'blacklands_runtime.lock').open('a+b') as lock:
        lock.seek(0,2)
        if lock.tell()==0:
            lock.write(b'\0');lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:
            parser.error('A runtime bridge already owns this mailbox')
        try:
            result=subprocess.run([str(args.binary),str(args.mailbox/'blacklands_runtime_endpoint.json'),
                                   str(args.report),str(args.seconds)],input=json.dumps(
                                       dict(epoch=uuid.uuid4().hex,token=uuid.uuid4().hex))+'\n',text=True)
            return result.returncode
        finally:
            lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)


if __name__=='__main__':
    raise SystemExit(main())
