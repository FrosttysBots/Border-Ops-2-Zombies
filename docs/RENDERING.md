# Rendering proof

The renderer experiments capture BL2 or BO2 through Windows.Graphics.Capture,
optionally crop to measured client bounds, and display CPU-copied frames externally.
It does not hook either game, alter game settings, send input, or inject an overlay
into BO2. It does not establish that BL2 uses D3D9Ex or supports shared textures.

The user explicitly wants the native BL2 HUD retained: shield/grenade indicators,
ammo and XP/level-up feedback are part of the target presentation. Preserve the HUD
when separating donor world pixels from the gun/hand layers. Its values will need
to follow integrated match state; BO2 continues to own health/death. The current
capture shows ordinary BL2 state, not Zombies state. Host rounds/points and donor
minimap/quest information need a later UI mapping.

## Run

```powershell
.\scripts\Setup-RenderProbe.ps1
.\scripts\Start-RenderProbe.ps1 -Seconds 30 -Preview
.\scripts\Start-RenderProbe.ps1 -Source bo2 -ClientOnly -Seconds 30 -Preview
```

Setup creates an isolated environment under `work/render-venv` using the pinned
versions in `bridge/render-requirements.txt`. Only binary wheels are accepted.
The tested interpreter is 64-bit Python 3.14. Setup does not install game files.

The capture requires one visible, non-minimized game window. `-Source bl2` is the
default; `-Source bo2` selects Plutonium Zombies. The helper verifies the executable
owner and additionally filters BO2's title prefix to exclude its console window.
It passes that exact HWND to capture. There is no desktop/monitor fallback.
No focus switching is automated. Other foreground applications are recorded only
as `other`; BO2 and BL2 are recognized by their process identity.

Each run uses a new ignored output directory. It saves `first.png`, `last.png`
and `report.json`. Optional `-SaveEverySeconds 2` (`--save-every 2` in Python)
saves intermediate frames with names recorded in report.samples; zero disables
this. These are local game-content evidence, not release assets.
The preview closes with Escape, its close button or the finite deadline. Runs
are limited to 180 seconds and a parent-process watchdog terminates a stuck
capture worker after an additional 20 seconds. Neither game process is stopped.

## Implementation

`bridge/render_probe.py`:

- `window_api`, `owner`, `find_game_window`: typed Win32 calls to select the game HWND
  and identify foreground ownership. Multiple candidates fail explicitly.
- `worker`: creates the capture and owns the CPU preview/report loop.
- `on_frame_arrived`: copies callback-owned BGRA pixels into a bounded latest-frame
  slot under a lock, at most ten times per second. Native callbacks may arrive
  faster; callback count is not the receiver's displayed frame rate.
- Local `state` holds `latest`, `next_sample`, `callbacks`,
  `closed` and `error`. No unbounded frame queue is retained.
- `report.samples`: sampled dimensions, native timespan, callback number, elapsed
  time, foreground classification, minimized flag, SHA-256, thumbnail pixel
  variation and difference from the previous sample. Maximum capture size is
  4096 x 2160. The duration and sample rate bound report growth.
- `displayed`: calls that submitted images to the preview. User confirmation is
  recorded separately; this counter alone does not prove visible presentation.
- `main`: validates duration, supervises the capture worker and enforces timeout.

Preview images are scaled to fit 960 x 540; saved frames retain captured dimensions.
Default capture includes window decorations. `-ClientOnly` uses physical Win32
client coordinates and measured DWM/window bounds, checked against capture size.
Resize mismatches skip a sample instead of applying guessed offsets. The pure
geometry helper is `capture_geometry.client_crop`; negative monitor coordinates
are supported. Reports include crop, captured dimensions and alpha range before
converting to BGR. Neither mode provides a separate weapon alpha channel.

Keep the capture border at the OS default (`draw_border=None`). Explicitly setting
it to true failed on this Windows build even though capture itself works. The
first failed attempt is preserved under `work/render-first/report.json`.

## First native result, 2026-10-04

The initial successful eight-second capture produced 74 sampled frames at
1282 x 747, all with different pixel hashes, while another application held focus.
Visual inspection confirmed native BL2 world, first-person gun and HUD. No black
frame or capture error was observed. Evidence: `work/render-first-retry`.

The 120-second preview then submitted 1,155 frames at about 9.66 sampled frames/sec
under the diagnostic 10 Hz cap. It recorded 1,150 distinct hashes and handled
dimensions of 1282 x 747 and 1286 x 749. Foreground-process sampling recorded 131
frames (all distinct) with BO2 focused, including a continuous 12.19-second span.
The preview ended on its deadline without an error. This rate is deliberately
limited by the observer and is not a maximum-performance benchmark.
Evidence: `work/render-preview-live/report.json` and `work/render-validation.json`.
At that earlier milestone, user confirmation was pending; the later dual-game
test below supplies it. First/last PNGs here show gameplay; hashes alone do not identify an inventory
screen. The short `work/render-inventory-check` capture also shows gameplay and
must not be counted as visual inventory evidence despite its folder name.

Python compilation, both PowerShell scripts' syntax checks, and a two-second run
through Start-RenderProbe.ps1 passed. The dependency/API change required here was
leaving border policy at its default; no game adapter was redeployed.

This proves OS-level whole-window capture while unfocused in this configuration.
It does not prove capture while minimized/hidden, rendering with the world disabled,
transparent gun isolation, low-latency GPU transfer, inventory input switching,
or compositing inside BO2. Moving pixels may include HUD counters; a changing hash
alone does not prove a specific gameplay animation.

## Next rendering gates

1. Preserve the now-verified client capture and native inventory display baseline.
2. Choose how to obtain gun/hand plus native HUD layers and independent inventory
   frames. Test donor-world suppression while retaining the desired HUD, without
   changing normal campaign saves.
3. Establish actual graphics device/resource compatibility; profile an all-GPU
   receiver path instead of assuming this CPU-copy preview meets latency goals.
4. Only then compose into the host and implement explicit input/focus ownership.

## Native layer-separation test, 2026-10-04

Read-only `diagnose_render.py` enumerated selected properties/function signatures
on the native controller, local player, viewport, pawn, arms, weapon and HUD. It
does not invoke reflected game functions. Evidence: `work/render-api-live.json`.
Observed `WillowGameViewportClient.bDisableWorldRendering=false`, a distinct
`WillowHUDGFxMovie` object, pawn Arms with DepthPriorityGroup=1, and a separate
weapon FirstPersonMesh. `pShowFlags` is an opaque WrappedStruct in this report;
do not assume its native layout or copy offsets from another engine/game.

The explicit finite `render_trial.py` test changed only bDisableWorldRendering:
three-second delay, twelve seconds true, restore original false. PlayerTick and
viewport PostRender callbacks enforce restoration on the game thread. It does
not change HUD flags, game input, item state, normal campaign saves or game files.
User confirmation plus captured PNGs showed that the world AND gun disappeared,
while native shields/health/ammo/grenade/XP HUD elements remained. The flag read
back false after restoration, and the gun/world visibly returned. No error.

This is a HUD-only capture candidate, not the required weapon+HUD separation.
The black background is opaque: treating every black pixel as transparent would
also erase black HUD artwork and mishandle translucent/antialiased edges. No
alpha extraction or BO2 compositing is claimed.

Evidence: `work/render-world-trial-state.json` and `work/render-world-trial/`.
`sample-0016.png` shows HUD on black; `sample-0020.png` shows restored world/gun.
The user confirmed: HUD remained, gun disappeared, scene returned.

To reproduce this exact diagnostic (do not repeat it as a weapon-isolation fix):

```powershell
.\scripts\Update-BL2-Probe.ps1 -RenderOnly
.\scripts\Start-RenderProbe.ps1 -Seconds 60 -SaveEverySeconds 2
```

In BL2's SDK console:

```text
pyexec blacklands_passthrough/diagnose_render.py
pyexec blacklands_passthrough/start_render_trial.py
```

Manual early restore:

```text
py from blacklands_passthrough import render_trial; render_trial.stop()
```

`render_trial._state` holds the viewport weak reference, original value,
restore_needed/restored, phase, delay/deadline, donor session, history and owned
hooks. Restore happens before removing hooks; a failed restore keeps them to retry.
Missing player or changed main-probe session also triggers restoration. If neither
tick nor render callback executes (for example a fully suspended process), cleanup
waits for a callback or manual stop; this is not an independent real-time watchdog.
Tests cover restore, hook registration failure, retry, preexisting flag state,
external change during the delay and adapter restart. 41 Python tests passed
(six new restoration tests); live flag restoration is separately verified.

Next: inspect per-view visibility or a dedicated foreground render target/pass
for the first-person mesh/arms/effects while retaining native HUD. Capture proper
alpha or an explicit coverage mask; do not approximate the gun by cutting a fixed
rectangle out of the full frame. These approaches are candidates, not implemented.

## Post-process world-key trials, live results 2026-10-04

Live inspector: BL2's active chain is AmbientOcclusion (SDPG_World=1),
EdgeDetection (5), FXAA (4) and Uber (4). Trial 1 below inserted a chain that
BL2 stored as a renamed copy with its uber SceneDPG reset to 4, and the active
combined chain never included it. No frame changed. Both copies were later removed
with `recover()`. Trial 2 (`ao_key_trial.py`) retuned the existing world-group AO
effect through four profiles and restored every value (`restored=True`), but the
frames were identical during the profiles. AO may be disabled in video settings.
The user confirmed AO was off. With AO on, the tint appeared in occluded world
areas and on the gun as well. Neither trial changed viewport/HUD flags or saves.
Evidence: `work/render-20261004-172030-c209e70e`, `work/render-20261004-172550-b185cd7e`,
`work/render-20261004-172833-ad1f83fb`.

Correction: `DepthPriorityGroup=1` on Arms and the weapon FirstPersonMesh is
`SDPG_World` on this build (`SDPG_Foreground=2`). Earlier notes misread it as foreground.

`foreground_trial.py` (live, user-confirmed) calls native `SetDepthPriorityGroup`
to move Arms and the FirstPersonMesh to `SDPG_Foreground`, holds them there, then
applies the AO key and restores both. While keyed, the world was tinted and the gun
stayed clean. This is the first working gun/world layer separation. The AO key still
covers only occluded areas, so a full world mask is the next gate.

`blackout_trial.py` (live, negative) moved the gun to Foreground and then set
`bDisableWorldRendering`. The user saw only the HUD over black. The flag skips the
foreground group as well. Everything restored cleanly. A full world mask therefore
needs another route, such as fuller AO coverage, a constant-colour world-group
material effect, hiding world actors, or native render-level capture.

`coverage_trial.py` (live, negative) showed stronger AO settings and chain refreshes
stay at about 0.3% world coverage.

`fog_trial.py` (live, success) keeps arms/gun in Foreground and drives the map's
existing `HeightFogComponent` to a dense, unbounded magenta fog. BL2 rewrites this
fog every frame, so the trial reasserts the values and calls `ForceUpdate(False)`
while active, then restores the latest originals. The upper world region measured
99.7% key colour, and the gun and native HUD stayed clean (user confirmed). This is a
chroma key, not alpha. Translucent HUD parts pick up the key colour, and it was
tested on one map. Evidence: `work/fog-trial-validation.json`, `work/fog-trial-grid.png`.

```text
pyexec blacklands_passthrough/diagnose_fog.py
pyexec blacklands_passthrough/start_fog_trial.py
```

## First combined picture, 2026-10-04

`isolation_mode.py` holds the fog_trial combination for up to 180 seconds. It
follows weapon switches into Foreground and publishes `blacklands_isolation.json`
as a heartbeat. `bridge/composite_preview.py` captures both clients and keys BL2
over BO2 using `bridge/composite.py`. It composites only while the heartbeat is
active and advancing and the BL2 frame is actually keyed. Otherwise it shows plain
BO2. Live: 219 composited frames of BL2's native gun and HUD over BO2 Zombies, a
weapon switch followed, and the user confirmed it. Evidence:
`work/composite-validation.json`, `work/composite-grid.png`.

```powershell
.\scripts\Start-CompositePreview.ps1 -Seconds 170
```

```text
pyexec blacklands_passthrough/start_isolation_mode.py
py from blacklands_passthrough import isolation_mode; isolation_mode.stop()
```

Limits: it's an external CPU window, not compositing inside BO2, and it doesn't
forward input. BO2's own viewmodel and crosshair still show underneath. BL2 is
stretched to BO2's client size. Translucent HUD parts are chroma-keyed, not alpha.
It was tested on one BL2 map.
Evidence: `work/foreground-trial-validation.json`, `work/render-20261004-173159-1d01e8ec`.

```text
pyexec blacklands_passthrough/start_ao_key_trial.py
pyexec blacklands_passthrough/start_foreground_trial.py
```

## Post-process world-key trial 1 design (live result above)

UE3 post-process effects carry `SceneDPG`, the depth-priority group after which
they run. The hypothesis is that an effect assigned to `SDPG_World` replaces the
donor-world pixels before the foreground group (arms/weapon FirstPersonMesh, group
1 per earlier reflection) and the Scaleform HUD are drawn. Earlier reflection
showed `LocalPlayer.PlayerPostProcess`, `PlayerPostProcessChains` (one chain) and
native `InsertPostProcessingChain`/`RemovePostProcessingChain`.

`diagnose_postprocess.py` is read-only: it records the active chain effects, their
`SceneDPG`, class defaults of candidate effect classes and the SDPG enum values
into `blacklands_postprocess_api.json`.

`postprocess_trial.py` builds one owned chain named `BlackLandsWorldKeyChain`
holding one `UberPostProcessEffect` set to saturate and tint the image to a key
colour (default magenta), inserts it after 3 seconds, and removes it after 12
seconds (1..15 allowed). Only chains with that exact name are ever removed.
Removal happens before unhooking; a failed removal keeps hooks to retry. It
refuses to apply if the chain list changed during the delay and records the
effect fields it actually set. It changes no viewport or HUD flags. Whether BL2's
uber shader and renderer honour these values is exactly what the live run tests.

```powershell
.\scripts\Update-BL2-Probe.ps1 -RenderOnly
.\scripts\Start-RenderProbe.ps1 -ClientOnly -Seconds 60 -SaveEverySeconds 1
```

```text
pyexec blacklands_passthrough/diagnose_postprocess.py
pyexec blacklands_passthrough/start_postprocess_trial.py
py from blacklands_passthrough import postprocess_trial; postprocess_trial.recover()
```

Possible outcomes: world keyed with gun and HUD intact (pass, still a chroma key,
not true alpha; translucent effects and key-coloured art need later handling);
whole frame tinted including the gun (SceneDPG ignored or effect runs later);
no change (effect inactive or bUseWorldSettings/shader differs). Record which.

## Client capture and automatic native menu preview, 2026-10-04

BL2 client capture produced 1280x720 frames, BO2 800x600, without title bars or
crop mismatches. BL2's captured alpha range was 255..255 (opaque). BO2's outer
capture contained other alpha values; that does not establish gun transparency.
The first BO2 selection found both its game and console windows and failed;
executable ownership plus the Zombies title prefix resolved that ambiguity.

Expanded reflection found the actual weapon FirstPersonMesh in foreground depth
group 1, a separate HUD movie and native player resource/inventory interfaces.
Direct checks found no exposed HiddenActors, HiddenComponents or
HiddenPrimitiveComponents on this controller. `pShowFlags` remains opaque.
No selective visibility control was assumed or applied.

The new read-only player observer detects native status-menu open/closed state.
`presentation_preview.py` captures both clients and selects BO2 gameplay or BL2's
native menu using fresh, session-matched observations. The live 120s run submitted
1,161 frames and recorded initial BO2 plus two menu open/close cycles. The user
confirmed the preview switched to Inventory and back. Native Inventory is also
visually verified in `work/render-inventory-batch/sample-0019.png`; Badass Rank is
visible in `sample-0015.png`. This supersedes the earlier pending menu proof.

See [player state and presentation runbook](PLAYER_STATE.md) for activation,
launchers, freshness handling and the fixed Windows snapshot replacement conflict.
Evidence is summarized in `work/presentation-validation.json`. The preview remains
external and CPU-based. It does not forward input, pause zombies, embed inventory
inside BO2 or isolate/composite the first-person gun. Those remain separate gates.

The later [native menu control panel](MENU_CONTROL.md) can open actual Inventory
and hand foreground control to BL2/BO2; this was verified live and user-confirmed.
It is separate from capture and does not make the preview an interactive game
window. Capture recovery now selects fresh BO2 frames with an explanatory notice
when a requested BL2 source fails. No usable host view reports an error; a client
crop mismatch persisting over two seconds also fails instead of freezing forever.
Initial target-selection failures now leave a report. Normal native capture after
these changes passed; induced capture loss remains covered by offline fixtures.

## Primary references

- [Microsoft application-window capture](https://learn.microsoft.com/en-us/windows/apps/develop/media-authoring-processing/screen-capture)
- [windows-capture author documentation](https://github.com/NiiightmareXD/windows-capture/blob/main/windows-capture-python/README.md)
- [windows-capture source](https://github.com/NiiightmareXD/windows-capture/blob/main/windows-capture-python/windows_capture/__init__.py)

The installed package is windows-capture 2.0.1 (MIT); the source linked above is
the moving upstream branch. Installed signatures were inspected before use.
OpenCV/numpy and their dependency notices must be reviewed if bundled for release;
this development environment is not a distribution package.
