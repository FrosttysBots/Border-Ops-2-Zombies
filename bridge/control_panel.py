"""Finite native-menu control panel. Foreground handoff, no synthetic game input."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk
from menu_client import open_inventory, StatusTracker
from menu_wire import STATUS_FILE, read_packet, validate_status
from render_probe import ROOT, write_json
from window_focus import focus_game


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=int, default=180)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 180:
        parser.error('Duration must be 1..180 seconds')
    args.output.resolve().relative_to((ROOT/'work').resolve())
    args.output.mkdir(parents=True, exist_ok=False)
    box = Path(os.environ['LOCALAPPDATA'])/'Plutonium/storage/t6/raw/scriptdata'
    import msvcrt
    lock_file = (box/'blacklands_menu_panel.lock').open('a+b')
    try:
        lock_file.seek(0); msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        lock_file.close(); raise RuntimeError('A menu control panel is already running.')
    report = dict(schema=1, started_utc=datetime.now(timezone.utc).isoformat(),
                  method='native inventory request and user-initiated foreground handoff',
                  synthetic_input=False, events=[], running=True)
    messages = queue.Queue(); tracker = StatusTracker(); deadline = time.monotonic()+args.seconds
    window = tk.Tk(); window.title('Black Lands 2 — inventory control trial')
    window.geometry('560x300'); window.resizable(False, False)
    status_text = tk.StringVar(value='Waiting for the BL2 menu adapter…')
    action_text = tk.StringVar(value='Run the activation command in BL2, then use Open inventory.')
    busy = False

    def log(event):
        report['events'].append(dict(utc=datetime.now(timezone.utc).isoformat(), **event))
        write_json(args.output/'report.json', report)

    def request():
        nonlocal busy
        if busy: return
        busy = True; open_button.configure(state='disabled')
        action_text.set('Waiting for native Inventory to open…')
        def work():
            try:
                result = open_inventory(box, lambda event: messages.put(('event', event)))
                messages.put(('opened', result))
            except Exception as exc:
                messages.put(('error', str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def focus(source):
        try:
            result = focus_game(source)
            log(dict(event='focus', **result))
            action_text.set(('Control handed to '+source.upper()) if result['success'] else
                            'Use Alt+Tab to select '+source.upper()+': '+result['reason'])
        except Exception as exc:
            action_text.set(str(exc)); log(dict(event='focus_error', message=str(exc)))

    def close(reason='panel_closed'):
        report.update(running=False, end_reason=reason, ended_utc=datetime.now(timezone.utc).isoformat())
        write_json(args.output/'report.json', report)
        window.destroy()

    def poll():
        nonlocal busy
        if time.monotonic() >= deadline:
            close('duration_complete'); return
        try:
            packet = validate_status(read_packet(box/STATUS_FILE))
            live = tracker.observe(packet, time.monotonic())
            label = 'Online' if live else 'Offline / waiting for advancing state'
            status_text.set(f'{label} · {max(0, int(deadline-time.monotonic()))}s left')
        except (OSError, ValueError, KeyError, TypeError):
            live = False; status_text.set('Menu adapter unavailable')
        while not messages.empty():
            kind, value = messages.get_nowait()
            if kind == 'event': log(value)
            else:
                busy = False
                if kind == 'opened':
                    action_text.set('Native Inventory confirmed.'); focus('bl2')
                else:
                    action_text.set(value); log(dict(event='request_error', message=value))
        open_button.configure(state='normal' if live and not busy else 'disabled')
        window.after(100, poll)

    frame = ttk.Frame(window, padding=16); frame.pack(fill='both', expand=True)
    ttk.Label(frame, text='Black Lands 2 · Native inventory trial', font=('Segoe UI', 15)).pack(anchor='w')
    ttk.Label(frame, textvariable=status_text).pack(anchor='w', pady=(10, 8))
    open_button = ttk.Button(frame, text='Open BL2 inventory', command=request, state='disabled')
    open_button.pack(fill='x')
    ttk.Button(frame, text='Switch control to BO2', command=lambda: focus('bo2')).pack(fill='x', pady=6)
    ttk.Label(frame, text='Close Inventory using BL2’s normal controls.\nBO2 pause behavior is unchanged; zombies may continue moving.').pack(anchor='w')
    ttk.Label(frame, textvariable=action_text, wraplength=520).pack(anchor='w', pady=8)
    window.protocol('WM_DELETE_WINDOW', close)
    window.bind('<Escape>', lambda _: close())
    log(dict(event='panel_started')); window.after(100, poll)
    try:
        window.mainloop()
    finally:
        lock_file.close()


if __name__ == '__main__':
    main()
