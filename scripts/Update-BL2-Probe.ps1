param([switch]$CheckOnly, [switch]$WeaponOnly, [switch]$EventsOnly, [switch]$RuntimeOnly, [switch]$RenderOnly, [switch]$PlayerOnly, [switch]$MenuOnly)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if (([int]$WeaponOnly.IsPresent + [int]$EventsOnly.IsPresent + [int]$RuntimeOnly.IsPresent + [int]$RenderOnly.IsPresent + [int]$PlayerOnly.IsPresent + [int]$MenuOnly.IsPresent) -gt 1) { throw 'Choose one isolated update mode.' }
if (!$WeaponOnly -and !$EventsOnly -and !$RuntimeOnly -and !$RenderOnly -and !$PlayerOnly -and !$MenuOnly -and (Get-Process Borderlands2 -ErrorAction SilentlyContinue)) { throw 'Save and close BL2 before updating the full probe. Isolated modules can be updated for explicit SDK activation.' }
$manifestPath = Join-Path $root 'work/bl2-deployment.json'
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$config = Get-Content -LiteralPath (Join-Path $root 'work/installations.json') -Raw | ConvertFrom-Json
if ([IO.Path]::GetFullPath($config.borderlands2) -ne [IO.Path]::GetFullPath($manifest.game)) { throw 'Game path differs from deployment manifest.' }
$exe = Join-Path $manifest.game 'Binaries/Win32/Borderlands2.exe'
if ((Get-FileHash -LiteralPath $exe).Hash -ne $manifest.original_executable_sha256) { throw 'Original executable fingerprint changed; inspect before updating.' }
& (Join-Path $PSScriptRoot 'Stage-Probes.ps1')
$stage = Join-Path $root 'work/staging/sdk_mods/blacklands_passthrough'
$mod = [IO.Path]::GetFullPath((Join-Path $manifest.game 'sdk_mods/blacklands_passthrough'))
$plan = @()
$names = if ($WeaponOnly) { @('weapon.py','refresh_weapon.py') } elseif ($EventsOnly) { @('events.py','event_wire.py','hit_trace.py','start_events.py') } elseif ($RuntimeOnly) { @('runtime.py','runtime_ipc.py','start_runtime.py') } elseif ($RenderOnly) { @('diagnose_render.py','render_trial.py','start_render_trial.py','diagnose_postprocess.py','postprocess_trial.py','start_postprocess_trial.py','ao_key_trial.py','start_ao_key_trial.py','foreground_trial.py','start_foreground_trial.py','blackout_trial.py','start_blackout_trial.py','coverage_trial.py','start_coverage_trial.py','diagnose_fog.py','fog_trial.py','start_fog_trial.py','isolation_mode.py','start_isolation_mode.py') } elseif ($PlayerOnly) { @('player_state.py','player_probe.py','start_player_probe.py') } elseif ($MenuOnly) { @('menu_wire.py','menu_control.py','start_menu_control.py','player_state.py','player_probe.py','start_player_probe.py') } else { @('__init__.py','wire.py','weapon.py','diagnose_weapon.py','refresh_weapon.py','events.py','event_wire.py','hit_trace.py','start_events.py','runtime.py','runtime_ipc.py','start_runtime.py','diagnose_render.py','render_trial.py','start_render_trial.py','diagnose_postprocess.py','postprocess_trial.py','start_postprocess_trial.py','ao_key_trial.py','start_ao_key_trial.py','foreground_trial.py','start_foreground_trial.py','blackout_trial.py','start_blackout_trial.py','coverage_trial.py','start_coverage_trial.py','diagnose_fog.py','fog_trial.py','start_fog_trial.py','isolation_mode.py','start_isolation_mode.py','player_state.py','player_probe.py','start_player_probe.py','menu_wire.py','menu_control.py','start_menu_control.py','pyproject.toml') }
foreach ($name in $names) {
    $target = [IO.Path]::GetFullPath((Join-Path $mod $name))
    if ([IO.Path]::GetDirectoryName($target) -ne $mod) { throw 'Target escaped the probe directory.' }
    $entries = @($manifest.files | Where-Object { $_.destination -eq $target })
    $exists = Test-Path -LiteralPath $target
    if ($entries.Count -gt 1) { throw "Duplicate manifest entry: $name" }
    if ($exists -and ($entries.Count -ne 1 -or (Get-FileHash -LiteralPath $target).Hash -ne $entries[0].sha256)) { throw "Untracked or modified probe file: $name" }
    if (!$exists -and $entries.Count) { throw "Tracked probe file missing: $name" }
    $source = Join-Path $stage $name
    $plan += [pscustomobject]@{source=$source;destination=$target;sha256=(Get-FileHash -LiteralPath $source).Hash;existed=$exists}
}
if ($CheckOnly) { Write-Output 'Preflight passed: only hash-checked probe files and new owned modules will change.'; return }
$backup = Join-Path $root ('work/probe-updates/' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $backup | Out-Null
Copy-Item -LiteralPath $manifestPath -Destination (Join-Path $backup 'bl2-deployment.json')
foreach ($item in $plan) {
    if ($item.existed) { Copy-Item -LiteralPath $item.destination -Destination (Join-Path $backup ([IO.Path]::GetFileName($item.destination))) }
}
$written = @()
try {
    foreach ($item in $plan) {
        [IO.File]::Copy($item.source,$item.destination,$item.existed)
        $written += $item
        if ((Get-FileHash -LiteralPath $item.destination).Hash -ne $item.sha256) { throw 'Updated file hash mismatch.' }
    }
    $targets = @($plan | ForEach-Object { $_.destination })
    $manifest.files = @($manifest.files | Where-Object { $_.destination -notin $targets }) + @($plan | Select-Object source,destination,sha256)
    $manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $manifestPath -Encoding utf8
    $plan | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $backup 'update.json') -Encoding utf8
} catch {
    foreach ($item in $written) {
        if ((Get-FileHash -LiteralPath $item.destination).Hash -eq $item.sha256) {
            if ($item.existed) { Copy-Item -LiteralPath (Join-Path $backup ([IO.Path]::GetFileName($item.destination))) -Destination $item.destination }
            else { Remove-Item -LiteralPath $item.destination }
        }
    }
    Copy-Item -LiteralPath (Join-Path $backup 'bl2-deployment.json') -Destination $manifestPath
    throw
}
Write-Output "Updated selected probe files. Prior versions backed up at $backup. SDK and game files unchanged."
if ($WeaponOnly) { Write-Output 'In the BL2 SDK console run: pyexec blacklands_passthrough/refresh_weapon.py' }
if ($EventsOnly) { Write-Output 'In the BL2 SDK console run: pyexec blacklands_passthrough/start_events.py' }
if ($RuntimeOnly) { Write-Output 'Start scripts/Start-RuntimeBridge.ps1, then in BL2 run: pyexec blacklands_passthrough/start_runtime.py' }
if ($RenderOnly) { Write-Output 'In the BL2 SDK console run: pyexec blacklands_passthrough/diagnose_render.py (or diagnose_postprocess.py / start_isolation_mode.py)' }
if ($PlayerOnly) { Write-Output 'In the BL2 SDK console run: pyexec blacklands_passthrough/start_player_probe.py' }

if ($MenuOnly) { Write-Output 'In the BL2 SDK console run: pyexec blacklands_passthrough/start_menu_control.py' }
