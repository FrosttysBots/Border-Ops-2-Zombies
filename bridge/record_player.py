"""Record bounded read-only player snapshots, checking the live donor session."""
import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import time
from wire import DONOR_FILE, Freshness, parse_donor, read_bounded


def read_player(path):
    # Release the file handle before parsing. The producer handles Windows
    # replace/share conflicts by dropping a snapshot and trying next tick.
    with path.open('rb') as stream:data=stream.read(32769)
    if len(data)>32768:raise ValueError('Oversized player packet')
    packet=json.loads(data)
    if not isinstance(packet,dict):raise ValueError('Expected player object')
    if packet.get('schema')!=1 or packet.get('source')!='bl2_player' or packet.get('readonly') is not True:
        raise ValueError('Unsupported player snapshot')
    for key in ('capture_id','donor_session'):
        if not isinstance(packet.get(key),str) or not re.fullmatch('[0-9a-f]{32}',packet[key]):
            raise ValueError('Invalid session')
    if type(packet.get('seq')) is not int or not 0<=packet['seq']<=2**53-1 or type(packet.get('active')) is not bool:
        raise ValueError('Invalid progress state')
    def check(value):
        if isinstance(value,float) and not math.isfinite(value):raise ValueError('Nonfinite player value')
        if isinstance(value,dict):
            for child in value.values():check(child)
        elif isinstance(value,list):
            for child in value:check(child)
    check(packet)
    menus=packet.get('menus')
    if menus is not None:
        if not isinstance(menus,list) or len(menus)>32:raise ValueError('Invalid menu list')
        for menu in menus:
            if (not isinstance(menu,dict) or menu.get('open') is not True
                    or type(menu.get('screen')) is not int):
                raise ValueError('Invalid native menu state')
    return packet


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds',type=int,default=180)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if not 1<=args.seconds<=180:parser.error('Duration must be 1..180 seconds')
    box=Path(os.environ['LOCALAPPDATA'])/'Plutonium/storage/t6/raw/scriptdata'
    args.output.parent.mkdir(parents=True,exist_ok=True)
    if args.output.exists():parser.error('Output already exists; preserve prior evidence')
    started=time.monotonic();freshness=Freshness();rows=[];last=None;error=None
    while time.monotonic()-started<args.seconds:
        try:
            packet=read_player(box/'blacklands_player.json')
            donor=parse_donor(read_bounded(box/DONOR_FILE))
            if packet['donor_session']!=donor['session']:raise ValueError('Player/donor session mismatch')
            key=(packet['capture_id'],packet['seq'],packet['active'])
            if not packet['active'] and not rows:
                time.sleep(.1);continue
            now=time.monotonic();freshness.observe(key[:2],now)
            if key!=last:
                if len(rows)>=720:break
                rows.append(dict(utc=datetime.now(timezone.utc).isoformat(),packet=packet,
                                 advancing_recently=freshness.online(now)))
                last=key
                temp=args.output.with_suffix('.tmp')
                temp.write_text(json.dumps(dict(schema=1,observations=rows),indent=2)+'\n',encoding='utf-8')
                temp.replace(args.output)
            error=None
            if rows and not packet['active']:break
        except (OSError,ValueError,KeyError,TypeError) as exc:error=str(exc)
        time.sleep(.1)
    print(json.dumps(dict(observations=len(rows),error=error,output=str(args.output))))
    return 0 if len(rows)>=2 and error is None else 1


if __name__=='__main__':raise SystemExit(main())
