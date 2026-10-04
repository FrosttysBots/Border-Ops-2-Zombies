# Native inventory control trial

This adds a narrowly scoped UI command channel alongside the existing read-only
telemetry. It can ask BL2 to open its native Inventory and confirm that the native
menu appeared. A small desktop panel can then hand foreground control to the
original game window. The player uses BL2's normal menu controls there.

This is a step toward input ownership, not input forwarding through the captured
preview. It does not synthesize keys, clicks or mouse movement, hook Windows input,
pause BO2, transfer items, change XP, or open an arbitrary native function.

## Run

With both games available, the main BL2 probe enabled and a test character loaded:

```powershell
.\scripts\Update-BL2-Probe.ps1 -MenuOnly
.\scripts\Start-ControlPanel.ps1 -Seconds 180
```

In BL2's SDK console:

```text
pyexec blacklands_passthrough/start_menu_control.py
```

Close the console, then click **Open BL2 inventory** in the panel. It waits for
native confirmation before attempting to focus BL2. Close Inventory using its
normal controls. **Switch control to BO2** focuses the original Zombies window;
it does not close BL2's menu. BO2 pause behavior is unchanged, so zombies may keep
moving. Escape in the panel, closing it, or its finite deadline ends the panel.
Escape in a game retains that game's normal behavior.

The activation also refreshes the finite player observer for the external preview.
Both SDK modules expire after 180 seconds. The panel has its own 180-second maximum.
No persistent hotkey or background service remains. Manual SDK stop:

```text
py from blacklands_passthrough import menu_control; menu_control.stop()
py from blacklands_passthrough import player_probe; player_probe.stop()
```

Stopping does not forcibly close native menus. A request already submitted may
finish within its short deadline; closing the panel is not an undo for native UI.

## Request and acknowledgement contract

`bridge/menu_wire.py` is canonical and is staged into the SDK package.
`blacklands_menu_request.json` and `blacklands_menu_status.json` are separate from
the bootstrap files. Packets are at most 8 KiB and contain no executable strings.

Each explicit SDK activation creates a new random `activation` ID tied to the
current `donor_session`. Requests must contain exactly schema, activation,
donor_session, seq, action, created_ms and expires_ms. Only `open_inventory` is
accepted. Request numbers must be contiguous, 1 through 128, with at most two
seconds of lifetime. Old activations, extra fields and unsupported actions fail
validation. The local wall clock bounds acceptance; observation deadlines use a
monotonic clock. These IDs prevent accidental replay, not hostile same-user access.

`MenuGate` reserves a sequence before calling native code. Duplicates cannot call
it again, including after an exception, delayed acknowledgement or file conflict.
One pending request cannot be replaced. Native `ShowStatusMenu_Inventory()` has a
zero-argument signature verified in the earlier live reflection report.

Actual success requires observed open Inventory (`CurrentScreen == 3`). If it is
already open, no native function runs. Another status tab returns `other_menu_open`
instead of guessing toggle behavior. No confirmation within two seconds yields
`unconfirmed`; it does not retry native code. `native_error`, `expired` and
`cancelled` are distinct outcomes. This is at-most-once invocation per activation,
not a durable exactly-once gameplay transaction.

The adapter polls on PlayerTick and viewport PostRender at up to 10 Hz on the game
thread. Main-probe restart/disable, missing player, deadline or observation error
removes its owned hooks. Status publication counts skipped Windows busy-file writes
and retries only the status snapshot on a later tick. No game-thread sleeps.

The first live activation failed on a misleading hook-registration result. Installed
SDK revision b1852aa4's append branch inserts a new hook but falls through to a
false return ([source](https://github.com/bl-sdk/unrealsdk/blob/b1852aa4/src/unrealsdk/hook_manager.cpp#L199-L209)).
The player and menu adapters now remove only their fixed owned identifiers before
registration, then verify `has_hook`. Stop also recovers owned hooks after lost
module state. Regression fixtures cover both successful insertion with false return
and true insertion failure. Other optional adapters still need this compatibility
check before future simultaneous activation; do not assume their old return-value
checks are sufficient.

The client requires two advancing active status packets before submitting, waits
at most three seconds for readiness and 4.5 seconds for the result, and rejects an
activation change. It does not automatically resubmit an uncertain request.
The panel uses an OS file lock to prevent duplicate cooperating panel instances.

## Focus and recovery

`window_focus.focus_game` selects the same verified process/window identities used
by capture, including exclusion of Plutonium's console. It calls SetForegroundWindow
once and checks the actual foreground HWND. If the user has switched to another
application while waiting, it does not take focus back. Windows may decline the
request; the panel reports that and directs the player to Alt+Tab.

Microsoft documents these restrictions in
[SetForegroundWindow](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setforegroundwindow)
and explains [asynchronous foreground activation](https://devblogs.microsoft.com/oldnewthing/20161118-00/?p=94745).
No input-queue attachment, focus-lock bypass or fake keystroke workaround is used.

Separately, the external preview now falls back to fresh BO2 frames if a requested
BL2 capture is closed, errors or stops advancing. It displays a notice on that
fallback. If there is no usable requested/host view, the preview reports failure.
It never substitutes the donor world for missing BO2 gameplay. Startup selection
failures now create a report. Player packet validation rejects malformed menu lists.

## Files and evidence

- `menu_wire.py`: schema, bounded I/O and `MenuGate` request/result lifecycle.
- SDK `menu_control.py`: native execution, hook ownership, status publication.
- SDK `start_menu_control.py`: explicit activation and safe module refresh order.
- `menu_client.py`: `StatusTracker`, readiness, one request and confirmed outcome.
- `window_focus.py`: user-initiated exact-window foreground handoff.
- `control_panel.py`: finite Tk panel, request worker, UI queue, singleton lock,
  status and event report under ignored `work/control-*`.
- `presentation_health.py`: pure capture availability/fallback policy.

Offline checks cover replay, expiry, old sessions, native errors, missing menu
confirmation, partial hook registration, busy acknowledgements, real temporary-file
client exchange with a synthetic peer, focus refusal and preview recovery. These
do not establish native UI behavior. See PROGRESS.txt and the current work/ evidence
summary for the separate live test result. No source-game content belongs in a
release package.

Live result, 2026-10-04: after the SDK compatibility fix, the first panel observed
an `opened` result and then `already_open` on a second request. A fresh activation
also returned `opened`; the user confirmed Inventory opened and received control.
Both BL2 and BO2 foreground HWND checks succeeded. Native screenshot
`work/menu-native-capture/last.png` shows Inventory. The corrected adapter reported
zero observation errors during this test. Evidence is in `work/control-native-first`,
`work/control-native-retry`, `work/menu-native-confirmed.json` and
`work/menu-control-validation.json`. The full Python suite passed 85 tests; 87
installed file hashes and the original game executable matched the manifest.
The final menu session stopped at its deadline with sequence 1665, zero errors and
two skipped status writes. The player observer also stopped normally with zero
errors. Both panels exited at their deadlines; no ongoing control session remains.
