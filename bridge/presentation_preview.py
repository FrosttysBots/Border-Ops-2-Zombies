"""Finite dual-game CPU preview, switched by native BL2 menu state. No game input."""
import argparse
import ctypes
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from menu_router import MenuRouter
from presentation_health import choose_capture
from record_player import read_player
from render_probe import ROOT, find_game_window, measured_crop, window_api, write_json
from wire import DONOR_FILE, parse_donor, read_bounded


def run(args):
    import cv2
    from windows_capture import WindowsCapture
    output=args.output.resolve();output.relative_to((ROOT/'work').resolve())
    output.mkdir(parents=True,exist_ok=False)
    user,kernel=window_api()
    user.SetThreadDpiAwarenessContext.argtypes=[ctypes.c_void_p]
    user.SetThreadDpiAwarenessContext.restype=ctypes.c_void_p
    if not user.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4)):raise ctypes.WinError(ctypes.get_last_error())
    try:
        targets={source:find_game_window(user,kernel,source) for source in ('bo2','bl2')}
    except Exception as exc:
        write_json(output/'report.json',dict(schema=1,running=False,error=str(exc),end_reason='startup_error'))
        return 1
    lock=threading.Lock();controls=[];captures=[];router=MenuRouter()
    states={source:dict(latest=None,next_frame=0.,callbacks=0,error=None,closed=False) for source in targets}
    report=dict(schema=1,started_utc=datetime.now(timezone.utc).isoformat(),running=True,
                method='two WGC client captures, CPU receiver, native status-menu routing',
                input_forwarding=False,bo2_injection=False,gpu_sharing=False,
                transitions=[],samples=[],error=None,crop_mismatch_skips=0)
    box=Path(os.environ['LOCALAPPDATA'])/'Plutonium/storage/t6/raw/scriptdata'
    start=time.monotonic();deadline=start+args.seconds;last_route=None;last_display=None;next_report=0.
    crop_failure_since=None
    title='Black Lands 2 - presentation experiment (no input forwarding; ESC closes)'

    def create(source):
        state=states[source]
        capture=WindowsCapture(window_hwnd=targets[source][0],cursor_capture=False,draw_border=None)
        @capture.event
        def on_frame_arrived(frame,control):
            now=time.monotonic()
            try:
                with lock:
                    state['callbacks']+=1
                    if now<state['next_frame']:return
                    state['next_frame']=now+.1
                    if not 0<frame.width<=4096 or not 0<frame.height<=2160:raise ValueError('Oversized capture')
                    state['latest']=(now,state['callbacks'],frame.frame_buffer[:,:,:3].copy())
            except Exception as exc:
                with lock:state['error']=str(exc)
                control.stop()
        @capture.event
        def on_closed():
            with lock:state['closed']=True
        captures.append(capture)
        controls.append(capture.start_free_threaded())

    try:
        for source in targets:create(source)
        while time.monotonic()<deadline:
            now=time.monotonic();packet_error=None
            try:
                packet=read_player(box/'blacklands_player.json')
                donor=parse_donor(read_bounded(box/DONOR_FILE))
                router.observe(packet,donor['session'],now)
            except (OSError,ValueError,KeyError,TypeError) as exc:packet_error=str(exc)
            desired,reason=router.select(now)
            with lock:
                selected,fallback=choose_capture(desired,states,now)
                latest=states[selected]['latest'] if selected else None
            if selected is None:
                if last_display is not None or now-start>12:
                    raise RuntimeError('No fresh usable game view: '+str(fallback))
                time.sleep(.02);continue
            reason=fallback or reason
            received,callback,pixels=latest
            if now-received>2:raise RuntimeError(f'{selected} capture stopped advancing')
            key=(selected,callback)
            if key!=last_display:
                try:x0,y0,x1,y1=measured_crop(user,targets[selected][0],pixels.shape[1],pixels.shape[0])
                except (ValueError,OSError):
                    report['crop_mismatch_skips']+=1
                    if crop_failure_since is None:crop_failure_since=now
                    if now-crop_failure_since>2:raise RuntimeError('Client geometry failed to settle after resize')
                    time.sleep(.02);continue
                crop_failure_since=None
                pixels=pixels[y0:y1,x0:x1]
                if selected!=last_route:
                    event=dict(elapsed=now-start,source=selected,reason=reason,
                               player_seq=router.seq,capture_id=router.capture_id)
                    if len(report['transitions'])<32:
                        name=f'transition-{len(report["transitions"]):02d}-{selected}.png'
                        if not cv2.imwrite(str(output/name),pixels):raise RuntimeError('Could not save route frame')
                        event['image']=name
                    report['transitions'].append(event);last_route=selected
                scale=min(960/pixels.shape[1],540/pixels.shape[0],1.)
                shown=cv2.resize(pixels,None,fx=scale,fy=scale)
                if fallback:
                    cv2.putText(shown,'BL2 capture unavailable - showing BO2',(12,24),
                                cv2.FONT_HERSHEY_SIMPLEX,.5,(0,210,255),1,cv2.LINE_AA)
                cv2.imshow(title,shown);last_display=key
                report['samples'].append(dict(elapsed=now-start,source=selected,
                    frame_age_ms=(now-received)*1000,callback=callback,
                    width=pixels.shape[1],height=pixels.shape[0],reason=reason,player_error=packet_error))
            if cv2.waitKey(1)==27 or cv2.getWindowProperty(title,cv2.WND_PROP_VISIBLE)<1:
                report['end_reason']='preview_closed';break
            if now>=next_report:
                next_report=now+1;write_json(output/'report.json',report)
            time.sleep(.03)
        else:report['end_reason']='duration_complete'
    except Exception as exc:
        report['error']=str(exc);report['end_reason']='error'
    finally:
        for control in controls:
            try:control.stop()
            except Exception as exc:report['error']=report['error'] or str(exc)
        cv2.destroyAllWindows()
        report.update(running=False,ended_utc=datetime.now(timezone.utc).isoformat(),
                      callbacks={s:state['callbacks'] for s,state in states.items()},
                      capture_health={s:dict(error=state['error'],closed=state['closed']) for s,state in states.items()})
        write_json(output/'report.json',report)
    print(json.dumps({k:v for k,v in report.items() if k!='samples'}))
    return 1 if report['error'] else 0


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds',type=int,default=90)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--worker',action='store_true',help=argparse.SUPPRESS)
    args=parser.parse_args()
    if not 1<=args.seconds<=180:parser.error('Duration must be 1..180 seconds')
    if args.worker:return run(args)
    try:return subprocess.run([sys.executable,__file__,*sys.argv[1:],'--worker'],timeout=args.seconds+20).returncode
    except subprocess.TimeoutExpired:
        report_path=args.output/'report.json'
        report=json.loads(report_path.read_text()) if report_path.exists() else {}
        report.update(running=False,error='Capture worker exceeded deadline',end_reason='watchdog_timeout')
        if report_path.parent.exists():write_json(report_path,report)
        return 1


if __name__=='__main__':raise SystemExit(main())
