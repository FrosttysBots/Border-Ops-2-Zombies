"""Real Python/Rust IPC exercise with synthetic poses. Never calls either game."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from runtime_ipc import Publisher

ROOT=Path(__file__).resolve().parents[1]


def read_report(path):
    return json.loads(path.read_text())


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'work/runtime-ipc-validation.json')
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(dir=ROOT/'work') as folder:
        folder=Path(folder);report=folder/'report.json';endpoint=folder/'blacklands_runtime_endpoint.json'
        proc=subprocess.Popen([sys.executable,str(ROOT/'bridge/runtime_host.py'),'--seconds','8',
                               '--mailbox',str(folder),'--report',str(report)],stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT,text=True)
        publisher=None
        try:
            deadline=time.monotonic()+4
            while not endpoint.exists() and time.monotonic()<deadline and proc.poll() is None:
                time.sleep(.02)
            publisher=Publisher(endpoint,origin='synthetic_test')
            duplicate=subprocess.run([sys.executable,str(ROOT/'bridge/runtime_host.py'),'--seconds','1',
                                      '--mailbox',str(folder),'--report',str(folder/'duplicate.json')],
                                     capture_output=True,text=True,timeout=3)
            assert duplicate.returncode!=0 and 'already owns' in duplicate.stderr,duplicate.stderr
            # Reject a gameplay instruction and an oversized datagram.
            publisher.socket.send(json.dumps({'kind':'apply_damage'}).encode())
            publisher.socket.send(b'x'*9000)
            start=time.monotonic();rtts=[]
            while time.monotonic()-start<1.2:
                publisher.send([1,2,3],[0,0,0],'Synthetic.Gun')
                if publisher.last_rtt_ms is not None:rtts.append(publisher.last_rtt_ms)
                time.sleep(1/60)
            publisher.poll()
            active=read_report(report)
            assert active['online'] and not active['native_bl2_online'],active
            assert active['accepted']>20 and active['rejected']>=2,active
            assert publisher.status()['online'],publisher.status()
            old_session=publisher.session
            publisher.close()
            # Verify stale detection while the server is still running.
            time.sleep(2.4)
            stale=read_report(report)
            assert stale['running'] and not stale['online'],stale
            publisher=Publisher(endpoint,origin='synthetic_test')
            start=time.monotonic()
            while time.monotonic()-start<.5:
                publisher.send([4,5,6],[0,0,0],None);time.sleep(.02)
            resumed=read_report(report)
            assert resumed['online'] and resumed['latest']['session']!=old_session,resumed
            # Old session replay must not revive even after a restart.
            packet=dict(schema=1,kind='pose',source='bl2',origin='synthetic_test',
                        epoch=publisher.endpoint['epoch'],token=publisher.endpoint['token'],session=old_session,
                        seq=999,sent_us=999999,position=[1,2,3],angles=[0,0,0],weapon=None)
            publisher.socket.send(json.dumps(packet).encode())
            publisher.close()
            stdout,_=proc.communicate(timeout=6)
            assert proc.returncode==0,stdout
            final=read_report(report)
            assert not final['running'] and not final['online'],final
            result=dict(synthetic_only=True,real_python_rust_processes=True,
                        duplicate_launcher_rejected=True,
                        malformed_and_oversized_rejected=True,stale_detection=True,restart_verified=True,
                        native_game_test=False,accepted=final['accepted'],rejected=final['rejected'],
                        sample_rtt_ms_min=min(rtts),sample_rtt_ms_max=max(rtts),
                        timing_note='Includes Python polling schedule; not engine-to-engine or GPU latency.')
            args.output.write_text(json.dumps(result,indent=2)+'\n')
            print(json.dumps(result,indent=2))
        finally:
            if publisher is not None:publisher.close()
            if proc.poll() is None:proc.terminate();proc.wait(timeout=5)


if __name__=='__main__':main()
