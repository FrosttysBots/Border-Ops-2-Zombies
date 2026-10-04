# First live connection

The BL2 SDK v3.8 and our probe have been installed additively on this machine.
No original game or pre-existing SDK file was overwritten. Our own probe updates
are hash-checked and backed up. The original BL2 and BO2 executable fingerprints
are recorded in ignored work/environment.json. Added files/hashes are recorded in
work/bl2-deployment.json. Both games have produced advancing native snapshots, and
BO2 has received BL2 acknowledgements. A native equipped BL2 weapon object has also been
verified, including changes when switching native BL2 weapons. Live disconnect/
reconnect validation remains pending. The steps below reproduce setup;
skip installation steps for adapters already deployed on this machine.

1. Run scripts/Open-Plutonium.ps1. The official launcher installs its client files.
   Sign in with your existing account and select your installed BO2 directory using
   its SETUP button. See the [official instructions](https://plutonium.pw/docs/install/).
2. Run scripts/Install-BO2-Probe.ps1. It places only our GSC in Plutonium's
   storage/t6/scripts/zm directory. The Steam BO2 installation stays untouched.
3. Launch BO2 Zombies through Plutonium and start a solo/custom session with one
   player. The console should show `[BlackLands] BO2 probe loaded`. Its storage/t6/raw/scriptdata
   folder receives blacklands_host.txt with advancing sequence/time values. This
   location and live writes were verified on this machine.
4. Run scripts/Start-BL2-Probe.ps1 with Steam already running. This sets a mailbox
   environment variable for this BL2 process only. Enable **Black Lands 2 Passthrough
   Probe** in the SDK Mods menu and load a test character. The hook only reads native
   state; it does not grant items, move the player, change stats or write saves.
5. Run scripts/Monitor-Bridge.ps1. Both peers should become online after their files
   advance. BL2 should acknowledge BO2 sequence numbers, and BO2's console should
   print changing donor replies. Closing either game must make that peer go offline.

Probe v0.2.0 also finds the observed Plutonium mailbox under
%LOCALAPPDATA%/Plutonium/storage/t6/raw/scriptdata when no explicit environment
setting is provided. The folder must already exist. This supports normal Steam
launches without requiring inherited environment variables. An explicit but invalid
BLACKLANDS_MAILBOX remains an error, rather than silently choosing another folder.

For updates, save and close BL2, then run scripts/Update-BL2-Probe.ps1. It checks
the previous deployment hashes and original executable, backs up our files under
work/probe-updates, and updates only our adapter. Modified or untracked files block
the update. Add -CheckOnly to inspect prerequisites without changing the deployment.

Inspect the equipped native weapon with:

```powershell
C:\Python314\python.exe .\bridge\inspect_weapon.py --output .\work\weapon-inspection.json
```

The inspector requires advancing snapshots matching the current donor session and
weapon path. It reports native name, definitions and raw numeric properties;
unavailable fields are explicit. Raw properties are not necessarily item-card
values or final damage after skills, elemental effects and target resistances.

For a read-only native API report, run this in BL2's SDK console while holding a gun:
`pyexec blacklands_passthrough/diagnose_weapon.py`. It records property values and
function signatures without invoking the discovered functions. The report is
blacklands_weapon_api.json in the mailbox.

An inspector-only update can be applied while BL2 runs with
`scripts/Update-BL2-Probe.ps1 -WeaponOnly`. Then run
`pyexec blacklands_passthrough/refresh_weapon.py` in its SDK console. This reloads
only our inspector, retaining the existing tick hook, session and sequence. Full
adapter updates still require saving and closing BL2. The workflow uses the SDK's
[documented console commands](https://bl-sdk.github.io/developing/getting_started/).

Record a bounded manual firing/reload test with:

```powershell
C:\Python314\python.exe .\bridge\record_weapon.py --seconds 45 --output .\work\weapon-recording.json
```

The recorder observes native ammo getters, raw properties and state flags. It
does not fire or reload for you. Polling can miss intermediate changes, so its
ammo transitions must not be treated as exact shot events. Session/weapon changes,
large sequence gaps and disconnections break comparisons.

## Native event diagnostics

Install the isolated event module using `scripts/Update-BL2-Probe.ps1 -EventsOnly`.
In BL2's SDK console run `pyexec blacklands_passthrough/start_events.py`. This
starts a finite 180-second capture, removing any previous hooks owned by this
diagnostic before registering its PRE/POST hooks. It does not fire, reload, change
ammo, apply damage or block the game functions. It stops at the duration limit
on the next game tick; stale output is not considered live by the inspector.

```powershell
C:\Python314\python.exe .\bridge\inspect_events.py --output .\work\event-capture.json
```

Callbacks separately record ConsumeAmmo, FiringModeDefinitionFire,
ProjectileDefinitionFire, BeginReload, ReloadDone and DisplayRecentDamageForPlayer.
The last is a local player's damage-display notification, not a proven hit event
attributed to the currently equipped weapon. Weapon callbacks filter to the local
player's main/offhand weapon. The 128-event ring explicitly counts evictions;
retained event counts must not be presented as complete totals after eviction.
The JSON packet has a separate 256 KiB ceiling and capture/session identifiers.
Use `py from blacklands_passthrough import events; events.stop()` to stop early.
The current start_events helper stops the previously loaded event module first,
then reloads only its transport, hit-inspection helper and event module before
starting a new capture. It preserves the main probe and avoids duplicate hooks.

Hit attribution diagnostics also observe the entry/exit of
FiringModeDefinitionFire, ExecuteProjectileFiredConstructEvent and the local
player's calls into WillowAIPawn.TakeDamage. A firing-call ID is scoped to its
synchronous call context. A projectile is associated only when its spawn callback
occurs in that context; a hit must reference that observed projectile. Unresolved
hits have no inferred shot or equipped weapon; a native weapon DamageCauser is
recorded directly even when a firing ID is unavailable. A bounded blacklands_hit_api.json
report records native argument/reference structure to investigate missing links.
ProcessInstantHitBullet entry/exit also records separate impact IDs. A nested
damage callback must match that impact's native weapon and target to link to it.
This is not proof of the original firing ID. blacklands_trace_api.json and
blacklands_bullet_api.json list candidate signatures without executing them.

The loader is an external dependency from the official bl-sdk release. Its stock
SDK libraries are separate from our authored source and keep their own licenses.
Do not package the SDK installation, source games, saves, logs or work/ as our mod.

## Running development checks

The optional Rust pose channel has separate [runtime setup instructions](RUNTIME.md).
Its modules can be installed using `Update-BL2-Probe.ps1 -RuntimeOnly`; activation
is explicit through `start_runtime.py` after launching `Start-RuntimeBridge.ps1`.
Use `Test-RuntimeBridge.ps1` for Rust checks and the synthetic process-to-process
test. That test uses an isolated mailbox and does not require either game.

```powershell
.\scripts\Test-Bridge.ps1 -Python C:\Python314\python.exe
.\scripts\Check-Environment.ps1
.\work\tools\gsc-tool-1.5.1\gsc-tool.exe -m comp -g t6 -s pc -y .\adapters\bo2\blacklands_probe.gsc
```

GSC compilation verifies syntax, not the presence/behavior of Plutonium builtins.
Python tests use a simulated SDK; they are explicitly not evidence of live engines.
