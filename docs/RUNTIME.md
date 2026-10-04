# Optional Rust runtime boundary

Implemented 2026-10-04 from the useful interface principles in MC's supplied
document. This is a finite, read-only BL2 pose experiment. It sends no input,
damage, loot, audio, textures or inventory commands. BO2 stays on its GSC mailbox.

## Components

- `runtime/`: separate Rust executable with strict serde validation.
- `bridge/runtime_host.py`: launches it with fresh epoch/token values and a local
  single-owner launcher lock. No permanent service is installed.
- `bridge/runtime_ipc.py`: nonblocking Python producer, staged into the SDK mod.
- `adapters/bl2/blacklands_passthrough/runtime.py`: game-thread observer, local
  player only, capped at 60 Hz. Actual rate depends on native ticks and focus.
- `start_runtime.py`: explicit module refresh, removing only its previous hook.

The producer reads native Pawn.Location, PlayerController.Rotation and the weapon
object path. Only primitives cross processes. Coordinates/angles retain native
BL2 units in X/Y/Z and Pitch/Yaw/Roll order. No BO2 axis/unit conversion or camera
alignment has been calibrated.

## Protocol

The sidecar binds only `127.0.0.1` on an OS-assigned UDP port. It writes an endpoint
file to the existing mailbox containing schema, port, epoch, token, size bound and
the sole capability `bl2_pose_readonly`. The SDK reads this once at explicit start.
Local tokens prevent accidental session mixing; they are not protection against
a hostile process running as the same user.

Each datagram is one UTF-8 JSON object of at most 8192 bytes. Unknown fields,
wrong schema/kind/source/epoch/token, malformed data, non-finite/out-of-range
coordinates and oversized strings are rejected by Rust.

| Field | Meaning |
| --- | --- |
| schema / kind / source | `1` / `pose` / `bl2` |
| origin | `native_bl2` or `synthetic_test`; producer label, not attestation |
| epoch / token | Fresh 32-character lowercase hex values per sidecar launch |
| session | Fresh producer ID, separate from the main probe session |
| seq | Positive increasing integer, at most 2^53-1 |
| sent_us | Microseconds since producer start; not a shared engine clock |
| position / angles | Three finite numbers each, absolute value at most 100,000,000 |
| weapon | Null or native path, at most 512 UTF-8 bytes |

Accepted poses receive schema, kind=ack, epoch, session, seq and echoed sent_us.
The producer checks acknowledgements against at most 128 outstanding observations
and drains at most eight replies per sample. Socket operations never wait for the
sidecar on the game thread. Only one-second diagnostic status writes use disk.

Two advancing accepted samples/replies establish online status; two seconds
without progress makes the peer stale. Duplicates, reordered packets, changed
source endpoints and backwards timestamps cannot keep a session online. A new
producer may take over after the old session is stale. Up to 64 retired IDs are
remembered and rejected; then restart the sidecar. Sequence gaps are counted,
without claiming whether they were sender skips or network losses.

UDP carries replaceable snapshots only. There is no retransmission, durable
delivery or exactly-once gameplay guarantee. Never use this implementation for
damage, pickups, saves or other critical transactions.

Both components run at most 180 seconds. The adapter stops on the next native tick
after its deadline, main-probe restart/disable, observation error, or five seconds
without replies. A paused game may delay hook cleanup; the receiver still marks
it stale. Restarting the sidecar requires explicitly restarting the SDK publisher
to load the new endpoint. Changed endpoint files are not followed automatically.

## Run and stop

From the project root:

```powershell
.\scripts\Update-BL2-Probe.ps1 -RuntimeOnly
.\scripts\Start-RuntimeBridge.ps1 -Seconds 180
```

While the sidecar waits and a BL2 character is loaded, enter in the SDK console:

```text
pyexec blacklands_passthrough/start_runtime.py
```

Move/look around; firing is unnecessary. To stop the adapter early:

```text
py from blacklands_passthrough import runtime; runtime.stop()
```

Sidecar status is `work/runtime-status.json`. Adapter status is
`blacklands_runtime_bl2.json` in the mailbox. Neither report contains the token.
Normal shutdown sets running/online false. A process crash can leave a stale
report: require advancing values and a running sidecar before calling it live.

## Verification

```powershell
cargo test --locked --manifest-path runtime/Cargo.toml --target-dir work/runtime-target
cargo clippy --locked --manifest-path runtime/Cargo.toml --target-dir work/runtime-target --all-targets -- -D warnings
.\scripts\Test-Bridge.ps1 -Python C:\Python314\python.exe
C:\Python314\python.exe bridge/check_runtime.py
```

The last command uses separate real Python/Rust processes with synthetic poses.
It checks replies, invalid/oversized rejection, staleness, restart and shutdown
in a temporary mailbox, never the game's endpoint. Its report is
`work/runtime-ipc-validation.json`. Round-trip timing includes Python polling and
does not measure game-to-game or GPU latency.

Native verification on 2026-10-04: the installed SDK publisher sent changing native
position/rotation and weapon identity to Rust and received advancing ACKs in the
same producer session. The SDK log recorded explicit start_runtime.py activation;
all 78 deployed file hashes matched. No synthetic producer was used for this run.
The finite receiver finished with 6,474 accepted snapshots, zero rejected and 15
sequence gaps. Observed online throughput averaged about 43.05 accepted/sec; the
adapter reported zero errors and zero send skips. Sampled ACK RTT median was
23.55 ms, including polling. These numbers describe this one run, not a guarantee.
After normal receiver exit, the SDK observer automatically stopped with
sidecar_unresponsive and zero errors. Its final 6,474 ACK count matched the receiver.
The user then reported keeping BO2 focused for 15 seconds. In the 14.90-second
observation window preceding that confirmation, Rust accepted 633 more poses and
both peers remained online. Focus itself was user-reported, not instrumented.
This proves continued background ticking in this setup, not background rendering.
Detailed local evidence: work/runtime-native-observations.json,
work/runtime-native-validation.json and work/runtime-background-validation.json.
Reported RTT includes native tick polling; sequence gaps are recorded rather than
treated as reliable delivery. The 60 Hz cap is not a measured rate guarantee.

Loaded-module inspection also observed d3d9.dll in BL2 and d3d11.dll/dxgi.dll in
Plutonium. This does not identify an active D3D9Ex device or demonstrate sharing.
Evidence: work/graphics-modules-live.json.

Remaining gates: end-to-end latency, BO2 fast IPC, reliable transactions and
graphics sharing. A separate [window-capture proof](RENDERING.md) has now copied
native donor frames externally, including while unfocused. Actual graphics device
compatibility, GPU sharing, gun transparency, effects, HUD ordering and inventory
input remain separate work; none uses this pose channel.

Primary references: [Rust FFI safety](https://doc.rust-lang.org/nomicon/ffi.html),
[Windows named shared memory](https://learn.microsoft.com/en-us/windows/win32/memory/creating-named-shared-memory),
[graphics API interoperability](https://learn.microsoft.com/en-us/windows/win32/direct3darticles/surface-sharing-between-windows-graphics-apis).
