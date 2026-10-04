# Black Lands 2 Passthrough

Start with [PROGRESS.txt](PROGRESS.txt) when continuing with a different AI model.
It covers current decisions, verified results, key files/variables, run commands
and next steps. Update it after every major change as required by AGENTS.md.

New project, preserving the original Rust rewrite separately. The target is actual
BO2 Zombies gameplay across all maps, with BL2's native guns, drops, characters,
shields, grenades, class upgrades, inventory screen and native BL2 HUD (including
shield/grenade status and XP/level-up feedback). Native skill trees with
accelerated leveling are proposed so a chosen full build can be reached within
one match; 10x XP or higher is a tuning candidate. Progression resets with every
new Zombies match. Starting progression, action skills and Mystery Box behavior
remain undecided.

This first milestone is a read-only connection probe. It does not yet replace guns,
merge rendering, transfer loot or embed the inventory menu. Both original games
run through compatible loaders. The first live telemetry/acknowledgement loop has
been verified with both games running, including a live native equipped-weapon object.
Probe v0.2.0 also reads its native name, definitions, parts and available numeric
properties. Missing properties stay explicitly unavailable. Run
`C:\Python314\python.exe bridge/inspect_weapon.py` for a current diagnostic report.
Inspection revision 2 also reads native damage/ammo values and firing/reload flags.
A live two-shot/reload test matched the user's final ammo HUD. This remains
read-only telemetry; it does not send combat actions into BO2.
A finite event diagnostic now captures native firing/ammo/reload callbacks.
Live captures verified pistol firing-mode calls, reload completion and native
enemy-damage notifications. Native enemy TakeDamage records now identify the
actual pistol as DamageCauser. Exact firing-call attribution and projectile
callbacks still require validation before any BO2 damage integration.

An optional Rust sidecar now accepts bounded, nonblocking BL2 pose observations
over localhost IPC. Native movement/camera observations and return ACKs have now
been verified live, including continued publication while the user focused BO2.
See [runtime setup and protocol](docs/RUNTIME.md) for evidence and limitations.
This first runtime interface does not integrate combat or rendering.

A separate Windows application-window capture proof now captures BL2's native
world, gun and HUD and can display them in a finite external preview. It uses CPU
copies; GPU sharing, separating the gun/HUD from the donor world and BO2 compositing
remain unbuilt. The BL2 HUD is part of the desired final display.
See [rendering proof and run commands](docs/RENDERING.md).

A reversible native viewport test preserved the BL2 HUD while hiding the world,
but also hid the gun. Restoration worked. This establishes a HUD-only candidate;
proper transparency and a separate first-person rendering path are still needed.

Both games now have clean client capture. A finite external preview automatically
switches from BO2 to BL2's native inventory and back using observed menu state;
the user verified this live. A read-only observer also exports native shield,
grenade, health, level/XP and backpack fields. Its Windows file-conflict fix passed
a full native run, and the Python suite now passes 60 tests. See the
[player state and presentation runbook](docs/PLAYER_STATE.md) for reusable commands.
Controls still go to the original game windows; cross-game state and input routing
are not implemented.

A separate [native inventory control trial](docs/MENU_CONTROL.md) now provides
an explicit Open Inventory request with expiry, duplicate protection and observed
completion. Its desktop panel supports foreground handoff to the original BL2/BO2
windows. This does not forward keys through the preview or pause Zombies. The
preview also falls back to BO2 when BL2 capture becomes unavailable. See PROGRESS
for the current live-validation status; offline tests alone are not native proof.

- BO2: Plutonium T6, using a small Zombies-only GSC adapter.
- BL2: Willow2 Mod Manager / Python SDK, using a game-thread tick hook.
- Initial transport: bounded snapshot files with sequence acknowledgements, at 4 Hz.
  This is for proving access, not for final combat/frame synchronization.

Run `scripts/Check-Environment.ps1` for local prerequisites and
`scripts/Test-Bridge.ps1` for authored protocol/adapter tests. These tests simulate
the SDK; they do not count as real game integration. Runtime setup and results are
kept under ignored `work/`.

The diagnostic loop is BO2 snapshot -> BL2 hook -> acknowledgement -> BO2 console,
plus a local monitor. BL2 reports its actual current weapon object and position;
BO2 reports its actual position, health and round. Neither adapter changes those
values. A missing/stale peer is shown as disconnected.

Read [design](docs/DESIGN.md), [setup](docs/SETUP.md), and [current status](docs/STATUS.md).
