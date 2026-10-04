"""Finite BL2/BO2 window capture proof. CPU preview only; no injection or game input."""
import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
from capture_geometry import client_crop

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {'bl2':'borderlands2.exe', 'bo2':'plutonium-bootstrapper-win32.exe'}


def window_api():
    user = ctypes.WinDLL('user32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    user.GetForegroundWindow.restype = wintypes.HWND
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user.IsWindowVisible.argtypes = [wintypes.HWND]
    user.IsIconic.argtypes = [wintypes.HWND]
    user.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                               wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    return user, kernel


def owner(user, kernel, hwnd):
    pid = wintypes.DWORD()
    user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    process = kernel.OpenProcess(0x1000, False, pid.value)
    name = ''
    if process:
        try:
            buffer = ctypes.create_unicode_buffer(32768)
            size = wintypes.DWORD(len(buffer))
            if kernel.QueryFullProcessImageNameW(process, 0, buffer, ctypes.byref(size)):
                name = Path(buffer.value).name.lower()
        finally:
            kernel.CloseHandle(process)
    return pid.value, name


def find_game_window(user, kernel, source):
    found = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    @callback_type
    def visit(hwnd, _):
        pid, name = owner(user, kernel, hwnd)
        if name == SOURCES[source] and user.IsWindowVisible(hwnd):
            # Plutonium also owns a console window; target its Zombies game view.
            if source == 'bo2':
                title = ctypes.create_unicode_buffer(512)
                user.GetWindowTextW(hwnd,title,len(title))
                if not title.value.startswith('Plutonium T6 Zombies'):
                    return True
            found.append((hwnd, pid))
        return True
    user.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    if not user.EnumWindows(visit, 0):
        raise ctypes.WinError(ctypes.get_last_error())
    if len(found) != 1:
        raise RuntimeError(f'Expected exactly one visible {source} window; found {len(found)}. No desktop fallback.')
    if user.IsIconic(found[0][0]):
        raise RuntimeError(f'Restore the {source} window before capture; it is minimized.')
    return found[0]


def measured_crop(user, hwnd, width, height):
    client = wintypes.RECT()
    if not user.GetClientRect(hwnd, ctypes.byref(client)):
        raise ctypes.WinError(ctypes.get_last_error())
    origin = wintypes.POINT(client.left, client.top)
    end = wintypes.POINT(client.right, client.bottom)
    if not user.ClientToScreen(hwnd, ctypes.byref(origin)) or not user.ClientToScreen(hwnd, ctypes.byref(end)):
        raise ctypes.WinError(ctypes.get_last_error())
    bounds = (origin.x, origin.y, end.x, end.y)
    outer = wintypes.RECT()
    dwm = ctypes.WinDLL('dwmapi')
    dwm.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
    if dwm.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(outer), ctypes.sizeof(outer)) == 0:
        try:
            return client_crop((width,height),(outer.left,outer.top,outer.right,outer.bottom),bounds)
        except ValueError:
            pass
    if user.GetWindowRect(hwnd, ctypes.byref(outer)):
        return client_crop((width,height),(outer.left,outer.top,outer.right,outer.bottom),bounds)
    raise ValueError('Could not match captured frame to measured window/client geometry')


def write_json(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    temp.replace(path)


def worker(args):
    import cv2
    from windows_capture import WindowsCapture
    from importlib.metadata import version

    output = args.output.resolve()
    # Never overwrite a previous capture or write images into the source tree.
    output.relative_to((ROOT/'work').resolve())
    output.mkdir(parents=True, exist_ok=False)
    user, kernel = window_api()
    # All geometry must use physical pixels, matching WGC frames.
    user.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    user.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
    if not user.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4)):
        raise ctypes.WinError(ctypes.get_last_error())
    hwnd, pid = find_game_window(user, kernel, args.source)
    report = dict(schema=1, running=True, method='Windows.Graphics.Capture window HWND',
                  target=SOURCES[args.source], source=args.source, pid=pid, hwnd=hwnd,
                  client_only=args.client_only, crop_mismatch_skips=0,
                  started_utc=datetime.now(timezone.utc).isoformat(),
                  seconds_limit=args.seconds, preview_requested=args.preview,
                  dependencies={m:version(m) for m in ['windows-capture','numpy','opencv-python']},
                  samples=[], displayed=0, error=None,
                  limitations=['CPU readback/copy and preview; not GPU texture sharing.',
                               'Full game view with optional client crop; no weapon isolation, input forwarding or BO2 compositing.',
                               'Frame differences do not by themselves identify gameplay animation.'])
    state = dict(latest=None, next_sample=0., callbacks=0, closed=False, error=None)
    lock = threading.Lock()
    started = time.monotonic()
    # Leave border policy at the OS default: explicit toggles are unsupported
    # on some Windows builds even though window capture itself is available.
    capture = WindowsCapture(window_hwnd=hwnd, cursor_capture=False, draw_border=None)

    @capture.event
    def on_frame_arrived(frame, control):
        now = time.monotonic()
        try:
            with lock:
                state['callbacks'] += 1
                if now < state['next_sample']:
                    return
                state['next_sample'] = now + .1
                if not (0 < frame.width <= 4096 and 0 < frame.height <= 2160):
                    raise ValueError('Capture exceeds the diagnostic size bound (4096 x 2160).')
                # Native frame memory is callback-owned: copy before handing it off.
                state['latest'] = (state['callbacks'], now-started, int(frame.timespan),
                                   frame.frame_buffer.copy())
        except Exception as exc:
            with lock:
                state['error'] = str(exc)
            control.stop()

    @capture.event
    def on_closed():
        with lock:
            state['closed'] = True

    control = None
    previous = None
    last_sequence = 0
    last_image = None
    next_report = 0.
    next_image = 0.
    saved_images = 0
    title = f'Black Lands 2 - {args.source.upper()} capture proof (ESC closes)'
    try:
        control = capture.start_free_threaded()
        while time.monotonic()-started < args.seconds:
            with lock:
                latest, error, closed = state['latest'], state['error'], state['closed']
            if error:
                raise RuntimeError(error)
            if closed or control.is_finished():
                report['end_reason'] = 'capture_closed'
                break
            if latest is not None and latest[0] != last_sequence:
                sequence, elapsed, timespan, pixels = latest
                last_sequence = sequence
                captured_size = [pixels.shape[1],pixels.shape[0]]
                crop = None
                if args.client_only:
                    try:
                        crop = measured_crop(user,hwnd,*captured_size)
                    except (ValueError,OSError):
                        report['crop_mismatch_skips'] += 1
                        if time.monotonic()-started > 12 and not report['samples']:
                            raise RuntimeError('No frame matched native client geometry within 12 seconds')
                        time.sleep(.01)
                        continue
                    x0,y0,x1,y1 = crop
                    pixels = pixels[y0:y1,x0:x1]
                alpha_range = [int(pixels[:,:,3].min()),int(pixels[:,:,3].max())]
                pixels = pixels[:,:,:3].copy()
                small = cv2.resize(pixels, (160, 90), interpolation=cv2.INTER_AREA)
                delta = None if previous is None else float(cv2.absdiff(small, previous).mean())
                previous = small
                foreground_pid, foreground_name = owner(user, kernel, user.GetForegroundWindow())
                focus = next((k for k,v in SOURCES.items() if v == foreground_name), 'other')
                report['samples'].append(dict(callback=sequence, elapsed=elapsed, timespan=timespan,
                    width=pixels.shape[1], height=pixels.shape[0], foreground=focus,
                    captured_size=captured_size, crop=crop, captured_alpha_range=alpha_range,
                    minimized=bool(user.IsIconic(hwnd)), pixel_std=float(small.std()),
                    mean_pixel_delta=delta, sha256=hashlib.sha256(pixels.tobytes()).hexdigest()))
                if args.save_every and elapsed >= next_image:
                    name = f'sample-{saved_images:04d}.png'
                    if not cv2.imwrite(str(output/name), pixels):
                        raise RuntimeError('Could not save diagnostic frame')
                    report['samples'][-1]['saved_image'] = name
                    saved_images += 1
                    next_image = elapsed + args.save_every
                if last_image is None and not cv2.imwrite(str(output/'first.png'), pixels):
                    raise RuntimeError('Could not save first frame')
                last_image = pixels
                if args.preview:
                    scale = min(960/pixels.shape[1], 540/pixels.shape[0], 1.)
                    shown = cv2.resize(pixels, None, fx=scale, fy=scale)
                    cv2.imshow(title, shown)
                    report['displayed'] += 1
            if args.preview and report['displayed']:
                if cv2.waitKey(1) == 27 or cv2.getWindowProperty(title, cv2.WND_PROP_VISIBLE) < 1:
                    report['end_reason'] = 'preview_closed'
                    break
            elapsed_now = time.monotonic()-started
            if not report['samples'] and elapsed_now > 12:
                raise RuntimeError('No game frames arrived within 12 seconds')
            if elapsed_now >= next_report:
                next_report = elapsed_now + 1
                report['callbacks'] = state['callbacks']
                write_json(output/'report.json', report)
            time.sleep(.01)
        else:
            report['end_reason'] = 'duration_complete'
    except Exception as exc:
        report['error'] = str(exc)
        report['end_reason'] = 'error'
    finally:
        if control is not None:
            try:
                control.stop()
            except Exception as exc:
                report['error'] = report['error'] or str(exc)
        if args.preview:
            cv2.destroyAllWindows()
        if last_image is not None and not cv2.imwrite(str(output/'last.png'), last_image):
            report['error'] = report['error'] or 'Could not save final frame'
        report.update(running=False, callbacks=state['callbacks'],
                      ended_utc=datetime.now(timezone.utc).isoformat())
        write_json(output/'report.json', report)
    print(json.dumps({k:v for k,v in report.items() if k != 'samples'}))
    return 1 if report['error'] or not report['samples'] else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=int, default=30)
    parser.add_argument('--preview', action='store_true')
    parser.add_argument('--source', choices=tuple(SOURCES), default='bl2')
    parser.add_argument('--client-only', action='store_true')
    parser.add_argument('--save-every', type=int, default=0,
                        help='Save an additional frame every N seconds (1..60); 0 disables')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 180:
        parser.error('Duration must be 1..180 seconds')
    if not 0 <= args.save_every <= 60:
        parser.error('Image interval must be 0..60 seconds')
    if args.worker:
        return worker(args)
    try:
        return subprocess.run([sys.executable, __file__, *sys.argv[1:], '--worker'],
                              timeout=args.seconds+20).returncode
    except subprocess.TimeoutExpired:
        path = args.output/'report.json'
        report = json.loads(path.read_text()) if path.exists() else {}
        report.update(running=False, error='Worker exceeded deadline and was terminated',
                      end_reason='watchdog_timeout')
        if path.parent.exists():
            write_json(path, report)
        print('Capture worker exceeded deadline.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
