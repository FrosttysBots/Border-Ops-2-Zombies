"""User-initiated focus handoff. Never synthesizes keyboard or mouse input."""
import ctypes
from ctypes import wintypes
import os
import time
from render_probe import find_game_window, owner, window_api


def focus_game(source):
    user, kernel = window_api()
    target, pid = find_game_window(user, kernel, source)
    # A delayed confirmation must not steal focus from an unrelated application.
    foreground = user.GetForegroundWindow()
    foreground_pid, _ = owner(user, kernel, foreground)
    allowed = {os.getpid(), pid}
    for game in ('bl2', 'bo2'):
        try:
            allowed.add(find_game_window(user, kernel, game)[1])
        except RuntimeError:
            pass
    if foreground_pid not in allowed:
        return dict(success=False, reason='focus_changed_to_another_app', source=source)
    user.SetForegroundWindow.argtypes = [wintypes.HWND]
    user.SetForegroundWindow.restype = wintypes.BOOL
    accepted = bool(user.SetForegroundWindow(target))
    # Foreground activation may complete after the target services its message queue.
    deadline = time.monotonic()+.3
    while time.monotonic() < deadline:
        if user.GetForegroundWindow() == target:
            return dict(success=True, reason='foreground_verified', source=source)
        time.sleep(.01)
    return dict(success=False, reason='windows_declined_or_delayed_focus', source=source,
                api_accepted=accepted)
