param()
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$stage = Join-Path $root 'work/staging'
$mod = Join-Path $stage 'sdk_mods/blacklands_passthrough'
$gsc = Join-Path $stage 't6/scripts/zm'
New-Item -ItemType Directory -Force $mod,$gsc | Out-Null
Copy-Item -LiteralPath (Join-Path $root 'adapters/bl2/blacklands_passthrough/__init__.py') -Destination $mod
Copy-Item -LiteralPath (Join-Path $root 'adapters/bl2/blacklands_passthrough/weapon.py') -Destination $mod
Copy-Item -LiteralPath (Join-Path $root 'adapters/bl2/blacklands_passthrough/diagnose_weapon.py') -Destination $mod
Copy-Item -LiteralPath (Join-Path $root 'adapters/bl2/blacklands_passthrough/refresh_weapon.py') -Destination $mod
Copy-Item -LiteralPath (Join-Path $root 'adapters/bl2/blacklands_passthrough/pyproject.toml') -Destination $mod
Copy-Item -LiteralPath (Join-Path $root 'bridge/wire.py') -Destination $mod
Copy-Item -LiteralPath (Join-Path $root 'bridge/event_wire.py') -Destination $mod
Copy-Item -LiteralPath (Join-Path $root 'adapters/bl2/blacklands_passthrough/events.py') -Destination $mod
Copy-Item -LiteralPath (Join-Path $root 'adapters/bl2/blacklands_passthrough/hit_trace.py') -Destination $mod
Copy-Item -LiteralPath (Join-Path $root 'adapters/bl2/blacklands_passthrough/start_events.py') -Destination $mod
Copy-Item -LiteralPath (Join-Path $root 'bridge/runtime_ipc.py') -Destination $mod
Copy-Item -LiteralPath (Join-Path $root 'adapters/bl2/blacklands_passthrough/runtime.py') -Destination $mod
Copy-Item -LiteralPath (Join-Path $root 'adapters/bl2/blacklands_passthrough/start_runtime.py') -Destination $mod
Copy-Item -LiteralPath (Join-Path $root 'adapters/bl2/blacklands_passthrough/diagnose_render.py') -Destination $mod
Copy-Item -LiteralPath (Join-Path $root 'adapters/bl2/blacklands_passthrough/render_trial.py') -Destination $mod
Copy-Item -LiteralPath (Join-Path $root 'adapters/bl2/blacklands_passthrough/start_render_trial.py') -Destination $mod
Copy-Item -LiteralPath (Join-Path $root 'adapters/bl2/blacklands_passthrough/diagnose_postprocess.py') -Destination $mod
Copy-Item -LiteralPath (Join-Path $root 'adapters/bl2/blacklands_passthrough/postprocess_trial.py') -Destination $mod
Copy-Item -LiteralPath (Join-Path $root 'adapters/bl2/blacklands_passthrough/start_postprocess_trial.py') -Destination $mod
Copy-Item -LiteralPath (Join-Path $root 'adapters/bl2/blacklands_passthrough/ao_key_trial.py') -Destination $mod
Copy-Item -LiteralPath (Join-Path $root 'adapters/bl2/blacklands_passthrough/start_ao_key_trial.py') -Destination $mod
Copy-Item -LiteralPath (Join-Path $root 'adapters/bl2/blacklands_passthrough/foreground_trial.py') -Destination $mod
Copy-Item -LiteralPath (Join-Path $root 'adapters/bl2/blacklands_passthrough/start_foreground_trial.py') -Destination $mod
Copy-Item -LiteralPath (Join-Path $root 'adapters/bl2/blacklands_passthrough/blackout_trial.py') -Destination $mod
Copy-Item -LiteralPath (Join-Path $root 'adapters/bl2/blacklands_passthrough/start_blackout_trial.py') -Destination $mod
Copy-Item -LiteralPath (Join-Path $root 'adapters/bl2/blacklands_passthrough/coverage_trial.py') -Destination $mod
Copy-Item -LiteralPath (Join-Path $root 'adapters/bl2/blacklands_passthrough/start_coverage_trial.py') -Destination $mod
Copy-Item -LiteralPath (Join-Path $root 'adapters/bl2/blacklands_passthrough/diagnose_fog.py') -Destination $mod
Copy-Item -LiteralPath (Join-Path $root 'adapters/bl2/blacklands_passthrough/fog_trial.py') -Destination $mod
Copy-Item -LiteralPath (Join-Path $root 'adapters/bl2/blacklands_passthrough/start_fog_trial.py') -Destination $mod
Copy-Item -LiteralPath (Join-Path $root 'adapters/bl2/blacklands_passthrough/isolation_mode.py') -Destination $mod
Copy-Item -LiteralPath (Join-Path $root 'adapters/bl2/blacklands_passthrough/start_isolation_mode.py') -Destination $mod
foreach ($name in @('player_state.py','player_probe.py','start_player_probe.py','menu_control.py','start_menu_control.py')) {
    Copy-Item -LiteralPath (Join-Path $root ('adapters/bl2/blacklands_passthrough/' + $name)) -Destination $mod
}
Copy-Item -LiteralPath (Join-Path $root 'adapters/bo2/blacklands_probe.gsc') -Destination $gsc
Write-Output "Staged authored probes at $stage. No game installation modified."

Copy-Item -LiteralPath (Join-Path $root 'bridge/menu_wire.py') -Destination $mod
