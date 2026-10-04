# Direction and ownership

BO2 remains authoritative for player movement/collision, camera, player health,
zombies, rounds, map scripts, barriers, perks and interactions. The target donor
is running BL2: native weapon instances, parts/stat evaluation, ammo/reload/firing
logic, shield/grenade behavior, class equipment, loot selection, inventory actions
and the rendered inventory/HUD themselves. Character bonuses and proposed skill progression
need explicit integration with BO2's host systems.

This intentionally differs from SkyCraft's choice to put player physics in its
donor game. Here preserving BO2 movement is an explicit requirement. No player
teleportation or competing physics controller is introduced by the first probe.

## Milestones

Confirmed product scope (user clarification, 2026-10-04):

- BO2 Zombies is the core game, with all BO2 Zombies maps as the final target.
  Prototype on one map, then validate each map's scripts, transitions, interactions
  and compatibility individually. Existing tests do not establish all-map support.
- BL2 supplies native guns, loot/drop generation, characters, shields, grenades,
  class upgrades and the actual inventory screen. Class-mod equipment is a working
  interpretation of class upgrades, not a settled exhaustive list. Character
  integration must not silently be reduced to cosmetic skins.
- Preserve the native BL2 HUD (explicit user decision): shield status, grenades,
  ammo, XP/level progress and level-up feedback should remain visible. Isolating
  presentation must remove the donor world while retaining the gun/hand and HUD
  layers. The existing capture already contains the HUD; it is not yet composited
  into BO2 or synchronized to Zombies state.
- Native skill trees and faster leveling are proposed, not yet a confirmed final
  system. User goal: finish a chosen full build during one Zombies match. Treat
  configurable 10x XP or higher as a playtest candidate; it does not guarantee a
  particular build-completion time. Progression resets with every new Zombies
  match, as explicitly selected by the user. See progression policy below.
- Mystery Box behavior is undecided. Preserve existing behavior during unrelated
  work; neither BL2 loot rolls nor removal/replacement are a selected design.
- Retain the install-location setup target for both user-owned games. These scope
  requirements are targets, not claims about currently implemented features.

1. Preserve verified BO2/BL2 telemetry and weapon inspection. Establish firing/hit
   identity without inferring causality from timestamps.
2. Establish a Rust sidecar with versioned messages, bounded nonblocking adapters,
   lifecycle and stale-peer handling. The first implementation is an optional
   BL2-to-Rust pose channel; BO2 remains on GSC files.
3. Prove presentation feasibility early: identify actual graphics devices, verify
   background ticking/rendering, copy one donor frame to a standalone receiver,
   then isolate gun/hand and native HUD from the donor world with transparency.
   Do not wait for complete combat.
4. Prove one pistol combat loop with BO2 target identity, native BL2 firing/ammo/
   reload, BO2 collision and death/score processing. A BL2 test target alone does
   not establish correct BO2-world collision.
5. Test pellets, elemental ticks and rockets separately, including misses, walls,
   travel time and splash occlusion. Document target/proxy mapping before claiming
   native damage fidelity in the BO2 world.
6. Composite the animated weapon, native HUD and inventory with exclusive input routing.
   Translate a zombie death into one native BL2 item and collect/equip that exact
   item. Critical actions need acknowledgement, deduplication and persistence rules.
7. Integrate BL2 characters, shields, grenades and class upgrades; prototype the
   proposed skill progression after establishing its mapping to BO2. Extend and
   validate the bridge across every BO2 Zombies map, including transitions, saves
   and map-specific item rules. Co-op follows solo correctness. Mystery Box,
   Pack-a-Punch/rarity mapping, placeholder drops and menu pause remain undecided.

## Equipment and proposed match progression

The native HUD should display actual integrated equipment and progression state.
BL2 provides evaluated shield/grenade/ammo and match-local XP/level state. Any native
health display must mirror BO2's authoritative health/down/death state; do not show
unrelated donor-character health or apply incoming damage twice to satisfy the HUD.
Level-up presentation is a confirmed display requirement; exact XP rules and the
optional skill-tree implementation remain undecided as described below.
BO2 round/points/map-interaction information still needs a presentation mapping.
Treatment of BL2's donor-world minimap/quest tracker and overlapping BO2 HUD
elements is unselected. Preserve needed information; do not silently redesign it.

Shields should use BL2's native item properties and behavior. BO2 remains the
final authority for player health and death/down state; the interface must route
incoming damage through donor shield absorption and return the resulting health
damage without applying the same hit twice. Recharge, depletion effects and perk
interactions need native validation. This pipeline is not implemented.

Grenades should retain native BL2 grenade-mod behavior, inventory and ammunition.
Their movement, impacts, splash/elemental effects and interaction with BO2 world
geometry require the same explicit collision bridge as weapon projectiles.
Class equipment/bonuses must reference actual donor items and evaluated effects,
not independently authored approximations.

For the optional skill-tree experiment, native BL2 skill allocation remains the
target. Accelerating XP is an intentional user-requested departure from original
BL2 pacing. Plan a configurable multiplier, initially testing 10x and higher as
needed. A complete chosen build is the objective, not automatically unlocking
every skill in every tree. Base XP for BO2 kills, starting level/skill points,
intended match length or completion round, level cap, and action-skill behavior
still need definition. More XP may affect level-dependent gear/damage as well as
skill availability; test that coupling before selecting a multiplier.

Future BO2 kill-to-XP awards must be identified and deduplicated so replays cannot
grant XP twice. Progression is match-local: every new Zombies match resets XP,
level gains and skill progression to a defined starting baseline. That baseline
is still a tuning decision; do not assume level 1 or a fixed number of skill points.
Use a BO2 match identity for this lifecycle, separate from transport epochs and
adapter sessions. Reconnecting the bridge, refreshing an adapter, starting a new
round or being revived within the same match must not count as a new match.
Reject delayed XP awards belonging to a previous match.

Implement this in isolated mod match state without resetting or overwriting the
user's normal BL2 campaign saves. Starting loadout and item carryover rules still
need their own specification; the progression decision does not establish them.
These are design requirements, not active game changes.

## Application of MC's interface-method document

The user supplied MC's "The Passthrough / Interface Method" on 2026-10-04.
Adopt process isolation, explicit interfaces and incremental validation. This is
runtime composition, not an engine rewrite or a promise that arbitrary games can
be combined. BL2 owns gameplay subsystems, not merely a visual skin. AI assists
implementation; it supplies no runtime compatibility layer by itself.

Separate processes protect ordinary address spaces; thread groups alone do not.
Native hooks can still crash their game, interfaces can misinterpret state, and
graphics resources need synchronization. Shared buffers are deliberate shared
memory despite separate game processes. No heap merging or raw pointer exchange
is needed. Rust does not automatically make foreign calls safe or bind arbitrary
C++/managed binaries. Universal optimization and one-executable conversion do not
follow from this architecture.

| State/system | Authority | Bridge responsibility |
| --- | --- | --- |
| Movement, camera, zombies, rounds, health, collision | BO2 | Export observations; preserve host simulation |
| Weapon definitions, inventory, ammo/reload | BL2 | Export native identity/state; eventually route explicit actions |
| Shields, grenades and class equipment | BL2 item behavior; BO2 world/final health | Explicit damage, collision and bonus mapping; avoid duplicate effects |
| Characters and proposed skill trees | BL2 content/native skills; bridge progression policy | Reset progression per new match; tune starting baseline/XP; define action skills |
| Cross-game hit mapping | Unimplemented interface | Prove shot/target identity and collision semantics |
| Gun/hand and inventory image | BL2 renderer, not integrated | Isolate, synchronize and composite images |
| Input ownership | Future bridge policy | One recipient per action; clear held state on focus/menu transitions |
| Audio | Not integrated | Separate weapon/UI sounds from duplicate donor-world audio |
| Transport lifecycle | Sidecar and adapters | Validate, bound and detect stale peers |

Pose snapshots are replaceable observations. Damage, pickups, equipment changes
and saves are transactions requiring a separate acknowledged design. A pose ACK
means the receiver accepted an observation, never that gameplay executed. Transport
sequence IDs, firing-call IDs, impact IDs and cross-game entity IDs are distinct.
Native UObject paths remain local diagnostic identities.

The [runtime protocol](RUNTIME.md) implements the first explicit interface using
loopback UDP. Shared-memory CPU channels can be evaluated after profiling; GPU
textures require a separate renderer interface. This is not final combat transport.

## Bootstrap transport

The GSC adapter writes one bounded pipe-delimited snapshot to its sandboxed
scriptdata directory. A terminal marker rejects partial writes. It reads a reply
containing its sequence number and BL2's tick sequence. The SDK adapter checks the
host frame, samples its own native state on PlayerTick, and writes JSON telemetry
and a reply. Unsupported schema/invalid/non-finite fields are rejected. The monitor
requires both files to advance within a timeout; old files cannot keep a peer online.

Disk polling is temporary and intentionally limited to 4 Hz. Final interactive
weapon/UI passthrough requires low-latency IPC, frame synchronization and a renderer
bridge. A working GSC probe does not establish those capabilities. No arbitrary
commands, Python execution, memory writes or damage messages are accepted here.

The BL2 v0.2.0 probe writes a separate bounded blacklands_weapon.json packet with
the same session/sequence as its heartbeat. It reads DefinitionData paths and
numeric fields, the native short name, and selected raw weapon properties on the
game thread. Unsupported fields are marked unavailable. Weapon inspection errors
do not prevent heartbeat acknowledgements. No UObject references leave that tick;
only JSON scalars are exported. The inspector rejects stale/mismatched sessions,
weapon paths, non-finite numbers and oversized packets.

Inspection revision 2 reads native InstantHitDamage and ammo/reload fields, plus
three explicitly allowlisted zero-argument getters verified by live reflection.
There is no general function dispatcher. State flags and getter values retain
their native names. A bounded recorder observes manual firing/reloading at the
bootstrap sampling rate; its ammo changes are not sufficient as combat events.
The final combat transport needs actual firing/hit events and engine attribution,
including projectiles, pellet counts, elements, skills and target resistances.

The optional finite event diagnostic uses PRE/POST hooks to observe native call
sites without suppressing or re-invoking them. Callbacks immediately serialize
primitive fields into a bounded in-memory ring; a separate tick callback publishes
it atomically. Captures carry monotonic event IDs, a donor session, a fresh capture
ID, explicit evictions and callback errors. A three-minute time bound and owned
hook cleanup keep this diagnostic separate from permanent gameplay integration.
Ammo, fire-mode, projectile and damage-display callbacks are distinct observations;
they are not yet correlated into one authoritative shot or BO2 damage instruction.

Enemy TakeDamage attribution uses its native DamageCauser reference, independent
of the currently equipped weapon. Native firing calls receive capture-local IDs;
delayed damage is never assigned the most recent ID by timing. An experimental
projectile association requires the spawn to occur inside an observed firing
call and damage to name that projectile. SDK WeakPointer checks limit stale object
reuse but are emulated and are not an absolute identity guarantee. That branch
has only synthetic coverage so far.

ProcessInstantHitBullet receives a separate impact ID. A nested TakeDamage record
can reference that impact only when both native weapon and target references
match. An impact ID does not establish which earlier firing call created the
bullet. Contexts expire on return or the next tick; unrelated delayed damage stays
unlinked. Reflection reports list candidate native bullet APIs without invoking
discovered methods. No damage-display callback is assigned a shot by proximity.

## External presentation proof

The current receiver can capture both games' measured client areas and select
BO2 gameplay or BL2's native status menu from fresh donor observations. Native
inventory open/close switching was user-confirmed. This is a finite external CPU
preview, not an overlay embedded in BO2. Input ownership, pause policy, gun alpha,
GPU transport and synchronized player state remain separate implementation gates.
The [player-state contract](PLAYER_STATE.md) documents the read-only HUD/resource
observer and menu selection. A missed snapshot may be dropped; that policy must
not be reused for future damage, XP, inventory or progression transactions.

The separate [native menu control contract](MENU_CONTROL.md) now permits only an
expiring open_inventory request under explicit finite SDK activation. Invocation
is at most once per sequence; success requires native menu observation. A desktop
panel hands foreground control to the original windows at the user's request.
Native opening and both focus handoffs are live-verified; this does not implement
key forwarding, automatic host pause or embedded menus. No item/XP/save actions
are allowed in the menu command channel.

## Sources

- [SkyCraft design](https://github.com/chasmlol/SkyCraft/blob/main/docs/DESIGN.md),
  inspected at bfcaf178524b92c2cdeb88e4ce0f13ef9ded6f32. Architecture reference;
  no Skyrim/Minecraft code is transplanted into this project.
- [Willow2 Mod Manager](https://github.com/bl-sdk/willow2-mod-manager), inspected at
  beaab44e6509ebc91565ca6ccb6c846aabc0982d. LGPL-3.0; external dependency, not bundled.
  Its networking/message_queue.py uses Engine.PlayerController:PlayerTick.
- [mods_base](https://github.com/bl-sdk/mods_base): build_mod, hook and get_pc APIs.
- [Apple's SDK mods](https://github.com/apple1417/bl-sdk-mods/tree/351af68f6d9ffc28d4fc484ac9b9b3256ef187cf),
  inspected at 351af68f6d9ffc28d4fc484ac9b9b3256ef187cf. SanitySaver/helpers.py
  documents native WeaponDefinitionData field names; vendor_edit/hooks.py uses
  GetShortHumanReadableName. API reference only; no gameplay-changing mod installed.
  Its true_damage_logger also documents the DisplayRecentDamageForPlayer callback
  fields used by the separate damage-display diagnostic. Its ammo-hook example
  confirms the local main/offhand weapon filter; our callbacks are POST observers
  and never return a block signal, refill ammo, or re-invoke an original function.
- [Plutonium script loading](https://plutonium.pw/docs/modding/loading-mods/) and
  [changelog](https://plutonium.pw/docs/changelog/): T6 supports Zombies GSC and
  sandboxed fs_* file I/O. Installed revision and function signatures still require
  runtime confirmation. Third-party client fixes can differ from retail behavior;
  therefore 1:1 fidelity remains a test target, not a current claim.
