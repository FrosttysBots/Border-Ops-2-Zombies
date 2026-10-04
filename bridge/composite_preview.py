"""Finite dual-game CPU preview: BL2 gun+HUD chroma-keyed over BO2. No game input.

BL2 must be in isolation_mode (gun/arms in SDPG_Foreground + magenta key fog). The
receiver composites only while BL2's isolation heartbeat is active and advancing and
the captured BL2 frame is actually keyed (coverage check); otherwise it shows plain
BO2 with a notice, so the full donor world is never laid over the host.
"""
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
from composite import MIN_COVERAGE, STATUS_FILE, IsolationTracker, composite, coverage, read_status
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
    lock=threading.Lock();controls=[];tracker=IsolationTracker()
    states={source:dict(latest=None,next_frame=0.,callbacks=0,error=None,closed=False) for source in targets}
    report=dict(schema=1,started_utc=datetime.now(timezone.utc).isoformat(),running=True,
                method='two WGC client captures, CPU chroma key of BL2 over BO2',
                input_forwarding=False,bo2_injection=False,gpu_sharing=False,layout='bl2 stretched to bo2 client',
                composited=0,host_only=0,mode_changes=[],samples=[],saved=[],error=None,crop_mismatch_skips=0)
    box=Path(os.environ['LOCALAPPDATA'])/'Plutonium/storage/t6/raw/scriptdata'
    start=time.monotonic();deadline=start+args.seconds;last_key=None;next_report=0.;next_save=0.
    last_mode=None;crop_failure_since=None
    title='Black Lands 2 - composite experiment (no input forwarding; ESC closes)'

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
        controls.append(capture.start_free_threaded())

    def crop(source,pixels):
        x0,y0,x1,y1=measured_crop(user,targets[source][0],pixels.shape[1],pixels.shape[0])
        return pixels[y0:y1,x0:x1]

    try:
        for source in targets:create(source)
        while time.monotonic()<deadline:
            now=time.monotonic();status_error=None
            try:
                donor=parse_donor(read_bounded(box/DONOR_FILE))
                tracker.observe(read_status(box/STATUS_FILE,donor['session']),now)
            except (OSError,ValueError,KeyError,TypeError) as exc:status_error=str(exc)
            ready,reason=tracker.ready(now)
            with lock:
                host=states['bo2']['latest'];guest=states['bl2']['latest']
            if host is None:
                if now-start>12:raise RuntimeError('No BO2 frame received')
                time.sleep(.02);continue
            if now-host[0]>2:raise RuntimeError('BO2 capture stopped advancing')
            key=(host[1],guest[1] if guest else None,ready)
            if key!=last_key:
                try:
                    host_pixels=crop('bo2',host[2])
                    guest_pixels=crop('bl2',guest[2]) if guest and now-guest[0]<=2 else None
                except (ValueError,OSError):
                    report['crop_mismatch_skips']+=1
                    if crop_failure_since is None:crop_failure_since=now
                    if now-crop_failure_since>2:raise RuntimeError('Client geometry failed to settle after resize')
                    time.sleep(.02);continue
                crop_failure_since=None
                keyed=coverage(guest_pixels) if guest_pixels is not None else 0.
                if ready and guest_pixels is not None and keyed<MIN_COVERAGE:ready,reason=False,'bl2_frame_not_keyed'
                if ready and guest_pixels is None:ready,reason=False,'bl2_capture_unavailable'
                mode='composite' if ready else 'host_only'
                if ready:
                    shown=composite(host_pixels,guest_pixels);report['composited']+=1
                else:
                    shown=host_pixels.copy();report['host_only']+=1
                if mode!=last_mode:
                    report['mode_changes'].append(dict(elapsed=now-start,mode=mode,reason=reason,isolation_seq=tracker.seq))
                    last_mode=mode
                if args.save_every and now>=next_save and len(report['saved'])<120:
                    next_save=now+args.save_every
                    name=f'composite-{len(report["saved"]):03d}-{mode}.png'
                    if not cv2.imwrite(str(output/name),shown):raise RuntimeError('Could not save composite frame')
                    report['saved'].append(dict(elapsed=now-start,image=name,mode=mode))
                display=shown
                if not ready:
                    display=shown.copy()
                    cv2.putText(display,'BO2 only: '+reason,(12,24),cv2.FONT_HERSHEY_SIMPLEX,.5,(0,210,255),1,cv2.LINE_AA)
                scale=min(960/display.shape[1],540/display.shape[0],1.)
                cv2.imshow(title,cv2.resize(display,None,fx=scale,fy=scale))
                last_key=key
                report['samples'].append(dict(elapsed=now-start,mode=mode,reason=reason,keyed_coverage=round(keyed,4),
                    host_age_ms=(now-host[0])*1000,guest_age_ms=(now-guest[0])*1000 if guest else None,
                    isolation_seq=tracker.seq,status_error=status_error))
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
    print(json.dumps({k:v for k,v in report.items() if k not in ('samples','saved')}))
    return 1 if report['error'] else 0


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds',type=int,default=90)
    parser.add_argument('--save-every',type=float,default=2.)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--worker',action='store_true',help=argparse.SUPPRESS)
    args=parser.parse_args()
    if not 1<=args.seconds<=180:parser.error('Duration must be 1..180 seconds')
    if not 0<=args.save_every<=60:parser.error('--save-every must be 0..60 seconds')
    if args.worker:return run(args)
    try:return subprocess.run([sys.executable,__file__,*sys.argv[1:],'--worker'],timeout=args.seconds+20).returncode
    except subprocess.TimeoutExpired:
        report_path=args.output/'report.json'
        report=json.loads(report_path.read_text()) if report_path.exists() else {}
        report.update(running=False,error='Capture worker exceeded deadline',end_reason='watchdog_timeout')
        if report_path.parent.exists():write_json(report_path,report)
        return 1


if __name__=='__main__':raise SystemExit(main())
