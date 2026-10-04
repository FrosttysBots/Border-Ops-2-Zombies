# Status — 2026-10-04

Current consolidated model handoff: [PROGRESS.txt](../PROGRESS.txt). This status
file is chronological; earlier milestone details may describe superseded states.

Active project: Black Lands 2 Passthrough. The older Rust engine rewrite is preserved
in the sibling Black Lands 2 folder, and no further rewrite development is intended
without another direction change from the user.

Confirmed final target: BO2 Zombies as the core across all maps, with BL2 drops,
guns, characters, shields, grenades, class upgrades and the native inventory screen.
Native skill trees with accelerated leveling are proposed: complete a chosen build
within one Zombies match, with 10x XP or higher as a tuning candidate. These added
systems and all-map compatibility are not implemented. Progression resets with
every new Zombies match; this lifecycle is specified but not implemented. Starting
baseline, action skills, XP mapping and Mystery Box behavior remain undecided.

Completed:

- Separate source repository and architecture/ownership plan.
- Read-only T6 GSC probe: position, orientation, health, round, equipped weapon and
  sequence snapshot; displays donor acknowledgement in the game console.
- BL2 SDK probe: game-thread sampling of the actual player/weapon object and an
  acknowledgement of the host sequence. It never changes gameplay or inventory.
- Bounded protocol/parser, stale-peer detection, atomic donor output and monitor.
- Thirty-five Python tests and four Rust tests pass, including partial writes, invalid values, stale files,
  SDK loading/no-pawn cases, missing weapon, missing host, and returned sequence.
- BO2 GSC compiles with xensik gsc-tool 1.5.1.359 for T6 PC (dry run).
- Installed official Willow2 SDK v3.8 and our probe without replacing existing
  files. Original BO2/BL2 executable hashes remain unchanged; deployment manifest
  lives in work/. Both probes have now been observed inside the running games.
- User completed Plutonium setup. Revision 5354 is present. Installed the BO2
  Zombies probe under its storage/t6/scripts/zm folder and recorded its file hash
  in work/bo2-deployment.json. Original game executable fingerprints still match.

BO2 live proof verified:

- The user entered a Zombies map. The running Plutonium console confirms the GSC
  loaded and init executed. Three valid native snapshots advanced in sequence and
  game time; position changed, with round 1, health 100 and m1911_zm equipped.
- Plutonium writes these files under storage/t6/raw/scriptdata. Corrected the
  monitor, BL2 launcher and BO2 installer to use this observed mailbox path.
- Local evidence is recorded in ignored work/live-validation.json. The previous
  snowroller authentication error no longer blocks this running session; its
  underlying cause and whether online authentication is fixed remain unverified.

Bidirectional live connection verified:

- BL2 SDK logged probe enablement, and its PlayerTick hook produced advancing
  snapshots with the actual player position. Both games remained running.
- Five sampled pairs showed advancing BO2/BL2 sequences and current host
  acknowledgements. Eleven new donor replies appeared in BO2's native console
  during the observation. The monitor reported both peers online and acknowledged.
- Initial evidence is recorded in ignored work/live-validation.json. After the
  user acquired a gun, three advancing BL2 samples reported a native WillowWeapon
  object. Weapon evidence is in work/weapon-live-validation.json. Native weapon
  identity detection is verified; its name, parts and statistics are not yet read.
- Recovered a missing BL2 window after a resolution change by backing up its user
  settings and restarting at 1280x720 windowed. The backup is under ignored
  work/display-recovery/. BO2 stayed running.

Next validation:

- Validate ammo behavior on other weapon types and distinguish native damage
  properties from final projectile/elemental/target damage. Accuracy/card formatting
  and exact firing-event capture remain unverified.
- Verify disconnect/reconnect behavior in real sessions. Existing stale-frame
  tests cover the parser/monitor only; no live shutdown test has been performed.

Weapon inspection milestone — 2026-10-04:

- Probe v0.2.0 deployed with backed-up prior files and an updated hash manifest;
  all 69 deployed SDK/probe file hashes match. No original game files changed.
- BL2's log confirmed the updated probe enabled. Live advancing detail snapshots
  matched the current donor session and weapon path. A Swift Hail exposed its
  native short name, weapon/balance/manufacturer definitions, part references,
  manufacturer grade, game stage and unique ID. Optional accessory2 was null.
- Native FireInterval, ReloadTime, ClipSize, ShotCost and Spread were numeric.
  WeaponDamage, CurrentClipCount, WeaponAccuracy and ProjectileSpeed were absent
  under those property names. They remain explicitly unavailable; no guessed
  values or alternate damage formulas were substituted. These raw fields do not
  establish final damage, the complete weapon card, or firing behavior transfer.
- Local report: work/weapon-details-first-live.json. Reproduce with
  bridge/inspect_weapon.py. Its parser and freshness/session checks reject stale
  or mismatched detail snapshots instead of presenting them as current data.
- Live switch verified within the same BL2 session: Swift Hail changed to Hard
  Bangstick, with a new weapon path, definitions and raw properties (ClipSize
  changed from 30 to 4). Evidence: work/weapon-switch-validation.json and its two
  referenced reports. This validates detection, not cross-game weapon switching.
- Normal launches can use the observed default Plutonium mailbox when no explicit
  BLACKLANDS_MAILBOX is set. Automated fallback tests passed; this live launch
  used the helper's explicit environment, so a normal-launch test is still pending.
- Update-BL2-Probe.ps1 preflights original hashes and refuses untracked or modified
  files; backups/update records are under ignored work/probe-updates/.

Damage/ammo inspection revision 2 — 2026-10-04:

- A one-shot SDK reflection report identified the actual properties and zero-arg
  getters on the running weapon. It only listed signatures; it did not invoke
  arbitrary discovered methods. Evidence: work/weapon-api-live.json.
- Replaced absent property guesses with InstantHitDamage, its base value,
  AmmoNotInClip, ReloadCnt, LastReloadCnt, AmmoLeftInClipDuringReload and raw
  ReplicatedReloadState. Added GetAmmoCount, GetMaxAmmo, GetMultiProjectileDamage,
  plus firing/manual-reload flags. All requested fields were available on the
  tested Hard Bangstick. InstantHitDamage was 468.1390380859375; this is not proof
  of final damage to a target or of complete shotgun/projectile damage behavior.
- Applied a backed-up inspector-only update while BL2 stayed running. The SDK
  refresh reloaded only our weapon module and retained the existing tick hook,
  session and sequence. All 71 deployed hashes and original BL2 EXE hash match.
- Recorded 168 fresh samples during a user-controlled firing/reload test. Two
  shots reduced GetAmmoCount 111 -> 110 -> 109; ReloadCnt changed 3 -> 2 -> 1.
  Manual reload changed reserve 108 -> 105 and ReloadCnt 1 -> 4 while total ammo
  remained 109. bManualReload became true then false; firing flags were observed.
  User confirmed final HUD 4/105, matching the settled native counters.
- Evidence: work/weapon-fire-reload-validation.json and its compact
  work/weapon-fire-reload-summary.json. The 4 Hz recorder reports observations,
  not lossless firing events; comparisons break across weapon/session changes,
  invalid frames and long sequence/time gaps. Tests cover these boundaries.
- BO2 and BL2 remained online with acknowledgements after the update. Both
  adapters still only read gameplay state; no BO2 damage or inventory changed.

Native event capture — 2026-10-04:

- Added a finite, read-only diagnostic using SDK POST hooks. It records local
  weapon ammo/fire-mode/projectile/reload calls and local-player damage-display
  notifications separately. Damage displays have no assigned weapon or shot ID.
- The first live capture recorded three ConsumeAmmo and three
  FiringModeDefinitionFire callbacks, followed by one ReloadDone. Firing definitions
  identified the default pistol bullet mode. No callback errors or evictions.
  Evidence: work/event-capture-first-live.json. This does not establish universal
  one-call-per-shot behavior across automatic/burst/shotgun/projectile weapons.
- BeginReload and ProjectileDefinitionFire did not appear in this initial test;
  those callbacks remain unverified. Damage-display validation succeeded in the
  subsequent enemy-map test described below.
- The capture ended natively with duration_complete and active=false after the
  three-minute window. Final totals stayed at 3 ammo-consumption, 3 firing-mode
  and 1 reload-completion callback, with zero errors/evictions. No damage-display
  notification was observed; this does not prove the hook works or fails without
  a confirmed enemy hit. Final evidence: work/event-capture-final.json. The main
  BO2/BL2 telemetry and acknowledgement loop remained online afterward.
- A 128-event ring, monotonically increasing IDs, explicit evictions/errors,
  bounded JSON and capture/session IDs prevent silently presenting truncated or
  stale data as complete live capture. Tests verify filtering, no original-function
  invocation, restart cleanup, timeout cleanup, and registration-failure rollback.
- All 74 deployed file hashes match the manifest. The optional event module is
  activated through the SDK console and does not start with the main probe.

Enemy-map damage notification validation — 2026-10-04:

- After the user loaded an enemy map and restarted capture through the SDK,
  a new capture ID and advancing sequence were verified against the donor session.
- Two DisplayRecentDamageForPlayer callbacks reported TotalDamageForDamageType
  452.7012939453125 against two distinct Ice_P WillowAIPawn instances. Their
  callback records followed native firing-mode/ammo callbacks. Errors and event
  evictions were both zero. Evidence: work/enemy-hit-live-validation.json.
- This proves local-player native damage-display notifications can be read.
  Temporal ordering is not shot attribution: each damage event deliberately has
  weapon=null. No source projectile, shot ID, target health delta or causal link
  was established, and no damage was forwarded to BO2. The main connection stayed
  online after this test. BeginReload/projectile callbacks remain unverified.

Native weapon cause and firing context — 2026-10-04:

- Two live enemy TakeDamage callbacks directly named the pistol WillowWeapon
  object as DamageCauser, each with Damage 452.7012939453125. The same capture
  recorded five firing calls and five ammo callbacks, with zero callback errors
  or evictions. Evidence: work/hit-attribution-native-weapon.json. It was read
  after the capture stopped, so the report correctly does not claim it is live.
- The native firing PRE/POST callbacks have capture-local IDs, but the tested
  bullets hit after those calls returned. Several bullets can be in flight at
  once. No timing-based or most-recent-shot association is made; shot_id remains
  null for these hits. DamageCauser was the weapon, not a projectile object.
- Live reflection identified ProcessInstantHitBullet with native Impact.HitActor,
  BulletDamage and firing-definition parameters. Added a bounded entry/exit
  observer with separate impact IDs to test its relationship to TakeDamage.
  The subsequent live capture recorded four firing calls, three TakeDamage
  callbacks and three damage displays, but zero impact callbacks. Every hit
  retained native_weapon_causer attribution and null shot_id/impact_id. No
  errors or evictions occurred. Evidence: work/impact-attribution-live.json.
  This does not prove whether the native implementation bypasses SDK dispatch
  or a different path handles these bullets. Projectile-reference linkage is
  also still synthetic-only; no projectile-spawn callback appeared in this test.
- The loaded bullet-class signature inventory exposed listener/damage-type
  classes, without an exposed per-bullet identifier in the collected report.
  Evidence: work/bullet-api-live.json. Next investigation should trace the native
  delayed-bullet path or a bounded SDK call trace before proposing another hook;
  repeating the same pistol test alone will not resolve the missing identifier.
- 29 synthetic tests pass, including context cleanup, stale projectile handling,
  nested impact scope, target matching and refusal to guess a delayed shot ID.
  The isolated updater backs up the previous module, stops its old hooks during
  SDK refresh and preserves the main telemetry session. No BO2 damage is sent.
- All 75 deployed file hashes match the manifest; the original BL2 executable
  hash also matches. A short background monitor did not establish both peers
  online simultaneously; the subsequent event capture itself was advancing and
  matched the current donor session. Historical connection proof still stands,
  but this turn does not add a new simultaneous two-peer validation.

MC interface document / Rust boundary — 2026-10-04:

- Reviewed the supplied document. Adopted separate processes, explicit authority,
  versioned bounded interfaces and incremental validation. Corrected claims that
  isolation eliminates crashes, Rust makes foreign calls automatically safe, or
  composition implies universal rewriting/optimization. Updated docs/DESIGN.md.
- Brought background rendering and frame-sharing feasibility ahead of completing
  combat. Native gun/hand isolation, input ownership, audio and target/collision
  mapping now have explicit unresolved responsibilities. No placeholder gun-drop
  model, rarity-based Pack-a-Punch or menu pause rule was silently adopted.
- Built a separate Rust sidecar and optional BL2 native pose publisher with
  nonblocking loopback UDP, capped/bounded work, session/sequence checks, stale
  detection, explicit synthetic labels and finite lifetimes. It accepts no game
  commands. BO2 stays on its existing file adapter. See docs/RUNTIME.md.
- Actual separate Python/Rust processes exchanged synthetic poses, rejected
  malformed/oversized traffic and an old-session replay, detected an absent
  producer, accepted a new session and shut down cleanly. Evidence is
  work/runtime-ipc-validation.json. Observed round-trip numbers include Python
  polling; they do not establish game-to-game/frame latency.
- 35 Python tests, 4 Rust tests and warning-free cargo clippy passed. SDK tests
  cover local-player filtering, read-only operation and disconnect/registration
  cleanup. These are synthetic tests, not proof the new hook runs inside BL2.
- Deployed three additive runtime modules with the hash-checked updater and prior
  manifest backup. The main SDK probe, gameplay and original game files were not
  changed. User explicitly deferred live activation; neither game was running.
- All 78 deployed hashes and the original BL2 executable fingerprint match. The
  final isolated IPC run accepted 95 synthetic snapshots and rejected three bad
  messages. Duplicate launcher rejection also passed. The waiting game-endpoint
  sidecar expired with zero samples; no live native test is claimed.

Model handoff — 2026-10-04:

- Created root PROGRESS.txt with consolidated requirements, evidence, 37 source
  file entries, important functions/state variables, protocols, deployment rules,
  commands, unresolved findings, UI feasibility research and next steps.
- AGENTS.md now requires reading it on continuation and updating it after each
  major code/design/deployment/validation change. README links it; .gitignore
  allows it into the authored source repository. No background automation added.
- Verified every FILE entry exists and the documented test counts match the
  current 35 Python and 4 Rust test definitions. This documentation-only change
  did not rerun game tests or launch/modify either game.

Native Rust IPC live validation — 2026-10-04:

- User reopened both games and explicitly activated start_runtime.py in BL2.
  The SDK log and installed-file checks support native provenance; all 78 deployed
  file hashes and the original BL2 executable matched. No source or deployed
  adapter code changed during this validation.
- Finite Rust receiver accepted 6,474 native poses, rejected zero, counted 15
  sequence gaps, and exited normally. Recorded 578 status observations include
  25 distinct positions, 20 distinct camera rotations and matching advancing ACKs.
  SDK reported zero observation errors and zero send skips. About 43.05 accepted
  updates/sec observed; sampled ACK RTT median 23.55 ms includes tick polling.
- After receiver exit, the SDK observer automatically stopped with
  sidecar_unresponsive, inactive/offline and zero errors. Final 6,474 ACKs matched
  receiver acceptance count. Both optional runtime components are now stopped.
- User reported keeping BO2 focused while BL2 stayed in gameplay. The preceding
  14.90-second observation window received 633 poses and both peers stayed online.
  Focus was user-reported, not instrumented. Background rendering is unverified.
- Saved local runtime-native-observations.json, runtime-native-validation.json,
  runtime-background-validation.json, runtime-native-sdk-log.txt and
  runtime-native-provenance.json under work/. No synthetic producer was used.
- Read-only module inventory found d3d9.dll in BL2 and d3d11.dll/dxgi.dll in
  Plutonium. This is not proof of active device type, D3D9Ex or texture sharing.
- Updated PROGRESS.txt, AGENTS.md, README.md and RUNTIME.md. Prior 35 Python/4 Rust
  test results remain historical; no code changes called for rerunning those tests.

External rendering proof — 2026-10-04:

- Added bridge/render_probe.py, pinned rendering dependencies, isolated setup and
  finite launcher scripts. No injection, game changes, automatic input or desktop
  capture. Exact HWND is selected by Borderlands2.exe ownership.
- Initial capture failed because an explicit capture-border toggle is unsupported
  on this Windows build. OS-default border policy fixed it; preserved failed report.
- Eight-second successful WGC capture: 74 distinct 1282x747 sampled frames while
  another application held focus. PNG inspection confirms native world, gun, HUD.
- 120-second external preview: 1,155 submissions, 1,150 distinct hashes, ~9.66 Hz
  under a deliberate 10 Hz sampling cap. 131 distinct frames arrived with BO2
  foreground, including a continuous 12.19-second span. No error; finite exit.
  Dimensions changed between 1282x747 and 1286x749 and were handled.
- Visible preview and inventory-screen confirmation from user remains pending.
  Saved first/last PNGs show gameplay. This is CPU-copy whole-window capture,
  including decorations, not isolated guns, shared textures or BO2 compositing.
- Local evidence in work/render-first-retry, render-preview-live and
  render-validation.json. Extra render-inventory-check images show gameplay.
- Python compilation, both new PowerShell scripts' syntax, and a two-second live
  launcher smoke test passed. Existing telemetry tests were not rerun because
  no telemetry/protocol code changed. Docs and PROGRESS.txt updated.

Native BL2 HUD scope decision — 2026-10-04:

- User explicitly wants the BL2 HUD, particularly shield/grenade status and
  leveling feedback. Preserve native HUD and weapon/hand layers while isolating
  the donor world. Updated AGENTS, PROGRESS, README, DESIGN and RENDERING.
- Capture already includes native HUD pixels; values still belong to the BL2
  session. Synchronization with BO2 health and match-local equipment/XP is not
  implemented. HUD layout for BO2 rounds/points and donor quests/minimap remains
  unselected. This does not silently confirm the optional skill-tree implementation.

Native HUD separation trial — 2026-10-04:

- Added read-only diagnose_render.py and hash-checked -RenderOnly deployment.
  Native report found viewport bDisableWorldRendering=false, separate HUDMovie,
  foreground arms (DepthPriorityGroup=1) and weapon FirstPersonMesh.
- Added explicit render_trial.py/start_render_trial.py. Only a transient viewport
  presentation bool changes; telemetry remains read-only. Hooks register before
  mutation, restoration precedes hook removal, failed restoration retries, and
  main-probe session changes stop the experiment. No arbitrary remote commands.
- Native test: 3s delay, 12s world-disabled, original false restored. User and PNGs
  confirm HUD remained while gun/world disappeared, then gun/world returned.
  This is a HUD-only candidate; proper alpha and gun isolation remain unresolved.
- Captured intermediate frames using new optional render_probe --save-every and
  launcher -SaveEverySeconds. Local evidence: render-api-live.json,
  render-world-trial-state.json, render-world-trial-validation.json and
  render-world-trial/sample-0016.png / sample-0020.png under work/.
- 41 Python tests passed (six new restoration tests); Python compilation and
  changed PowerShell syntax checked. 81 deployment hashes and original BL2
  executable matched. Backup manifests: ed90a3e1bc2744528f8b943e404b3c58 (inspector),
  67146ccd3a69417799ded51856583843 (three rendering modules).
- No persistent rendering setting, normal save or original game file changed.
  Next investigate a selective foreground render path and true alpha/coverage;
  do not repeat the whole-world switch as if it could preserve the gun.

Native player/menu and dual-game presentation batch — 2026-10-04:

- Expanded native reflection to FirstPersonMesh, HUDMovie, resources, XP and
  inventory. FirstPersonMesh depth group 1 observed; controller HiddenActors,
  HiddenComponents and HiddenPrimitiveComponents were not exposed. No guessed
  offsets or selective visibility writes were introduced.
- Added measured physical client crops for BL2 and BO2: native 1280x720 and 800x600
  captures passed. BO2's separate console initially caused an ambiguous HWND
  selection; the Zombies title prefix now disambiguates the allowlisted process.
- Added optional 4 Hz/180s read-only player/HUD/menu observer and bounded recorder.
  Native shields/health, grenade pool, level/XP, backpack and HUD cache fields
  resolved. XP pool max 100,000,000 is not next-level threshold 899,363 at level 30.
- Native Inventory and Badass Rank captured in render-inventory-batch. Separate
  120s presentation receiver submitted 1,161 frames with five view entries and no
  capture errors. User explicitly confirmed Inventory -> BO2 switching. This
  supersedes earlier pending inventory/visible-preview verification.
- Initial player capture stopped on WinError5 during atomic snapshot replacement.
  Fixed producer to skip Windows busy-file writes and retry on the next sample,
  without sleeping on the game thread. Actual Windows lock regression passed.
  Corrected live observer reached sequence 711, stopped normally at 180s, zero errors,
  two skipped writes. 472 recorded observations plus final stopped packet saved locally.
  That recorder used an earlier reader implementation; final short-read reader
  is covered independently by a file-handle-release regression test.
- Added Start-PresentationPreview.ps1 and Record-PlayerState.ps1, -Source and
  -ClientOnly render flags, and -PlayerOnly isolated deployment. 60 Python tests
  passed; Python compilation and all PowerShell syntax checks passed. 84 deployed
  file hashes and the original executable matched. Source docs/PROGRESS updated.
- Evidence: work/presentation-validation.json, presentation-live/,
  player-state-fixed-live.json, player-state-fixed-final.json,
  interfaces-api-live.json and visibility-capabilities-live.json. Preserve failed
  player-state-live.json. No game saves, original files or persistent settings
  were changed. External preview and optional player observer ended normally.

Native Inventory commands and foreground handoff — 2026-10-04:

- Added menu_wire/MenuGate, finite SDK menu_control/start_menu_control, confirmed
  request client, exact-window foreground helper, Tk control panel and launcher.
  Only open_inventory is accepted: bounded schema, activation/donor match,
  contiguous request IDs, two-second expiry, at-most-once invocation and native
  screen3 confirmation. No arbitrary native dispatch or gameplay operations.
- First activation exposed installed SDK b1852aa4 add_hook append returning false
  after insertion. Pinned source confirms the missing successful return branch.
  Updated player/menu lifecycle to clear only fixed owned identifiers and verify
  has_hook; also recover owned hooks if Python state was lost. Added regressions.
- Corrected first activation confirmed native open and then already_open without
  toggling it. Independent retry activation confirmed another open. User reported
  Inventory opened and received control. Both game foreground HWND checks passed.
  PNG inspection confirms the real Inventory. Initial failed SDK logs retained.
- Preview now falls back to fresh BO2 on donor capture failure, displays a notice,
  reports startup errors, rejects malformed nested menu state and bounds persistent
  client-crop failure. Actual normal capture smoke passed; source-loss branches
  have synthetic coverage, not a forced live game-close test.
- 85 Python tests pass, including temporary-file client/peer exchange and Windows
  focus guard fixtures. Python compilation and PowerShell syntax passed.87 deployed
  hashes and original executable matched. Installed backup manifests:
  893abad89f3a4980964d357ee039430a (initial), d78061c1d5d349e0953aabe18d6c7ac7 (fix).
- Evidence: work/control-native-first/, control-native-retry/,
  menu-native-confirmed.json, player-menu-confirmed.json, menu-native-sdk-log.txt,
  menu-native-capture/last.png and menu-control-validation.json. New runbook:
  docs/MENU_CONTROL.md. The panel changes focus to original windows; no synthetic
  keys/mouse, input-queue attachment, host pause or preview input forwarding.
- Final native menu session: seq1665, inactive duration_complete, zero errors,
  two skipped busy status writes. Player observer ended normally (seq698, zero
  errors/skips), and both panels exited at their deadlines. Final packets saved in
  work/menu-native-final.json and player-menu-final.json.

Not implemented: item transfer/generation, cross-game damage, isolated BL2 gun
compositing into BO2, input forwarding, native inventory compositing, shared GPU textures,
reliable gameplay-event delivery/persistence or frame synchronization. Do not describe the current
probe as a playable mashup or a completed 1:1 implementation.

References are under work/references and excluded from Git. SDK archive v3.8 SHA256:
E1862DDB282CF845369C9CA1CA70AC180D6104CCE25D8A133557FC74E157B4C7.
gsc-tool archive 1.5.1 SHA256:
C70744996C4801BD564760143CC9D735EF951359BAE31D72A52F291CD1FEF36B.
