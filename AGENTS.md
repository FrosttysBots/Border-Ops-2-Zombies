# Black Lands 2: passthrough direction

## Handoff maintenance (explicit user request)

Read PROGRESS.txt at the start of project work. Keep it current after every major
code, architecture, user-scope, deployment or validation change, before the final
handoff. Update its date, current status, important files/functions/variables,
evidence, limitations and next steps. Distinguish live proof, synthetic tests,
research, proposals and unimplemented features. Reconcile affected docs as well.
Never put credentials, tokens, game content/saves or actual install paths in the
handoff; refer to ignored local configuration. This applies across AI models and
does not require a new user request each time. It is not a scheduled automation.

## Direction and boundaries

The user explicitly switched to passthrough on 2026-10-03. This is a separate
project from C:\Claude Projects\Black Lands 2. Preserve the old Rust prototype.
Do not continue rebuilding BO2's engine here.

Target: original BO2 Zombies as the core game across all its Zombies maps, plus
original BL2 weapons, drops, characters, shields, grenades, class upgrades and
native inventory screen and native BL2 HUD. Preserve shield/grenade visibility,
ammo and XP/level-up feedback; do not remove the HUD as part of world isolation.
HUD values must follow integrated match state, with BO2 authoritative for health
and death. This UI choice does not settle the proposed skill-tree implementation.
All maps are the release target; a single-map prototype
does not reduce that scope. Class-mod equipment is a working interpretation of
class upgrades, not an exhaustive definition. Native skill trees with accelerated
leveling are proposed (user said "maybe"): target completion of a chosen full build
within one Zombies match, with configurable 10x XP or higher as a tuning candidate,
not a fixed guarantee. Do not equate a full build with maximizing every skill tree.
Progression resets at every new Zombies match (explicit user decision): XP, level
gains and skill progression return to the chosen starting baseline. Starting level,
action-skill scope and exact leveling rules remain open. Apply resets to isolated
mod match state, not the user's existing BL2 campaign saves. A bridge reconnect or
adapter reload within the same match must not trigger another progression reset.
The Mystery Box is explicitly undecided; do not replace or redesign it by default.
BO2 owns movement, zombies, rounds, player health and map events.
BL2 should own item generation, weapon/shield/grenade behavior and inventory. Shield
absorption and character bonuses must integrate explicitly with BO2 damage/health
and perks; do not run competing player-health authorities. The bridge translates
events, input and rendering; do not silently substitute authored weapon tuning or
a lookalike inventory for native BL2 behavior.

Current scope includes read-only live telemetry and bidirectional acknowledgement through
Plutonium T6 GSC and the Willow2 Python SDK. File polling is a bootstrap diagnostic,
not the eventual frame transport. Neither loader nor native hooks are assumed to
work until observed inside the running games. Test fixtures are never live evidence.

Presentation work also includes an explicitly activated, reversible viewport trial:
render_trial.py briefly changes bDisableWorldRendering, then restores its captured
value. This is separate from the read-only telemetry channels. No remote arbitrary
commands or gameplay mutations were added. Live result: HUD survives, weapon does
not; do not mistake this for weapon isolation. Preserve its restore-before-unhook
behavior and keep native UObject access on the game thread.

Keep original game files unchanged. Stage tools/adapters locally; additive loader
deployment must preserve existing files and record a removable installation manifest.
Do not bypass login, licensing, anti-cheat or change public servers. Initial tests
use a locally hosted Zombies session and a separate BL2 test character.
No game content, saves, runtime logs or installation paths in the source repository.
work/ is ignored and contains references, tool downloads, runtime configuration and
results. Document source revisions and limitations in docs/STATUS.md.

The optional runtime/ Rust sidecar and BL2 runtime.py observer add a read-only
loopback pose channel. Read docs/RUNTIME.md before changing its protocol. Keep
snapshot transport separate from future reliable gameplay transactions. The
existing BO2 GSC file bridge remains active; fast BO2 IPC and in-game compositing
are not implemented. Synthetic IPC tests are not live game proof. On 2026-10-04 the user
resumed live testing: native pose publication/ACKs and continued ticking while
BO2 was reportedly focused were observed. A separate Windows.Graphics.Capture
experiment subsequently captured native whole-window BL2 frames while unfocused.
Read docs/RENDERING.md before renderer work. CPU preview is not GPU texture sharing,
isolated gun rendering, hidden/minimized-window support or game-to-game latency.
See PROGRESS.txt for current evidence.

The finite player_state/player_probe observer adds read-only native HUD/resource
and status-menu telemetry. Read docs/PLAYER_STATE.md before changing it. Native
inventory capture and menu-driven BO2/BL2 switching in an external receiver have
user-confirmed live evidence. Client capture uses measured physical bounds, not
guessed window borders. Gun+HUD isolation now works as an explicit finite
isolation_mode (gun/arms to SDPG_Foreground + key-coloured height fog) keyed over
BO2 in an external preview; see docs/RENDERING.md. It is a chroma key, not alpha.
Input forwarding and embedded BO2 compositing remain unimplemented. Windows snapshot conflicts must not sleep or
busy-retry on the game thread; bounded latest-state drops are counted, and readers
require advancing sequence numbers. Do not reuse this lossy policy for gameplay
transactions. PROGRESS.txt records the failed run and corrected live completion.

An explicitly activated finite menu_control.py channel now accepts only
open_inventory. Read docs/MENU_CONTROL.md before changing it. It uses native
ShowStatusMenu_Inventory and observes completion, with activation/session IDs,
expiry and at-most-once invocation. It is separate from read-only telemetry;
never add arbitrary function names/code to its packets. The external control panel
supports user-initiated foreground handoff, not synthetic input forwarding or a
unified playable window. BO2 pause behavior is unchanged. Hook registration in SDK
b1852aa4 must be verified with has_hook after clearing owned identifiers: add_hook
can return false after a successful append. Do not remove any other mod's hooks.
