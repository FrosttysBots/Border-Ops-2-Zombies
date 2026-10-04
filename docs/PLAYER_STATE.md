# Native player state and menu presentation

The finite BL2 observer reads native health, shield, grenade, level, XP, backpack
and status-menu state. It does not change equipment, grant XP or synchronize those
values with BO2. All current values belong to the donor campaign character.

## Run

Keep the main Black Lands probe enabled and a test character loaded. In the BL2
SDK console, run:

```text
pyexec blacklands_passthrough/start_player_probe.py
```

This explicitly reloads only the player observer and runs for 180 seconds. It also
reports whether three candidate controller visibility arrays are exposed. That
report is read-only; none of those arrays was exposed in the tested build.

From the passthrough workspace, record player state or start the external preview:

```powershell
.\scripts\Record-PlayerState.ps1 -Seconds 90
.\scripts\Start-PresentationPreview.ps1 -Seconds 90
```

Run these independently or in separate terminals if both are wanted together.
The preview requires the render environment from `Setup-RenderProbe.ps1` and both
games restored, not minimized. New ignored `work/` outputs preserve older runs.
Open BL2's actual inventory yourself: the preview selects its native menu frame;
closing the menu returns the preview to BO2. Controls still go to the original
game windows. Escape, the preview close button or its deadline ends the preview.
It neither opens the menu nor pauses BO2. There is no input forwarding yet.

The separate [menu control trial](MENU_CONTROL.md) can request native Inventory
and hand foreground control to the original game. It is explicitly activated;
the observer and preview remain read-only. Their reports must not imply otherwise.

Manual observer stop:

```text
py from blacklands_passthrough import player_probe; player_probe.stop()
```

## Source and state contract

- `player_state.py`: `inspect_player` calls a small set of verified read-only
  getters on the game thread. `native` and `hud_cache` are separate measurements;
  unavailable fields are null with explanations, never fabricated zero values.
  Grenades use the unique `Ammo_Grenade_Protean` resource pool (at most 64 pools).
  Backpack count/capacity and equipped weapon path are observations, not item IDs.
- `player_probe.py`: two POST hooks, PlayerTick and viewport PostRender, share
  `IDENTIFIER=blacklands.readonly.player_state`. The second hook keeps the observer
  sampling during menus. `_state` owns `capture_id`, `donor_session`, `seq`,
  `active`, `deadline`, `next_sample`, `registered`, `player`, `menus`, `errors`,
  `menu_error` and `write_skips`. Sampling is capped at 4 Hz, duration at 180s.
  Deadline, donor restart or main-probe disable stops the owned hooks. If the game
  suspends both callbacks, cleanup waits for a callback; consumers still go stale.
- `menus()` reads at most 32 `StatusMenuExGFxMovie` objects and reports only open
  movies with their native `CurrentScreen`. Screen 3 was observed with Inventory,
  screen 5 with Badass Rank. Routing accepts all open status-menu tabs.
- `publish()` writes bounded 32 KiB JSON to `blacklands_player.json` in the existing
  Plutonium mailbox. Temporary-file replacement can conflict with Windows readers.
  WinErrors 5/32/33 drop that snapshot and increment `write_skips`; no sleep or busy
  retry blocks the game thread. The next scheduled observation retries. A failed
  final publication can leave an old active packet, so file presence is never
  liveness. Other observation errors stop the diagnostic and are reported.
- `record_player.py`: bounded reads close the file before JSON parsing; schema,
  session IDs, counters, finite numbers and donor-session match are validated.
  Advancing capture/sequence determines freshness. Records at most 720 rows.
- `menu_router.py`: `MenuRouter` requires two advancing samples from an active,
  matching donor and a last advance within two seconds. Duplicate/reordered
  packets cannot keep it alive. Missing, stale, inactive or unavailable menu state
  selects BO2. This is display selection only.
- `presentation_preview.py`: two exact game-window captures, measured client
  crops, bounded latest-frame slots, CPU preview at at most 10 Hz. Selected frames
  must be fresh; no initial frames within 12 seconds fails. Runs at most 180s with
  a parent watchdog. Logs transitions and saves the first 32 transition images.
  It does not inject code into BO2 or share GPU textures.
  Donor capture failure now falls back to a fresh host view with a visible notice;
  startup failures produce a report. No usable host view causes an explicit error.

Important XP distinction: `xp_pool_max` was 100,000,000 while `xp_next_level_at`
was 899,363 at level 30. The resource-pool maximum is not the next-level threshold.
Do not use it as an XP-bar denominator. No progression reset or multiplier exists.

## Live evidence, 2026-10-04

Both clean client views were captured (BL2 1280x720, BO2 800x600). Native Inventory
is visible in `work/render-inventory-batch/sample-0019.png`; `sample-0015.png`
shows Badass Rank. These local game images are not distribution assets.

The 120-second external receiver submitted 1,161 frames and logged five view
entries (initial BO2 plus two menu open/close cycles), with no capture error.
The user confirmed that it switched to Inventory and back to BO2. Evidence:
`work/presentation-live/report.json` and its transition images.

The first observer run stopped after a Windows replacement conflict. Its failed
evidence remains in `work/player-state-live.json`. After the fix, the native
observer reached sequence 711 and stopped normally at its deadline, with zero
errors and two skipped writes. The recording contains 472 observations; the final
packet is saved separately in `work/player-state-fixed-final.json`. Thus the fix
has both a real Windows file-lock regression test and live conflict/recovery
evidence. The recorder in that live run had an earlier reader implementation;
the final short-lived reader handle is covered separately by the offline test.

The complete Python suite passed 60 tests. All 84 installed SDK/probe files and
the original BL2 executable matched their recorded hashes. These checks do not
prove input routing, cross-game health/equipment synchronization or playable combat.
