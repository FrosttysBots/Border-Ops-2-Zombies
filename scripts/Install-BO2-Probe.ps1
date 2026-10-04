param()
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$plutonium = Join-Path $env:LOCALAPPDATA 'Plutonium'
if (!(Test-Path -LiteralPath (Join-Path $plutonium 'bin/plutonium-bootstrapper-win32.exe'))) {
    throw 'Install and sign in to Plutonium first. This script never downloads or replaces BO2 game files.'
}
$target = Join-Path $plutonium 'storage/t6/scripts/zm/blacklands_probe.gsc'
if (Test-Path -LiteralPath $target) {throw "Probe already exists: $target"}
New-Item -ItemType Directory -Force (Split-Path -Parent $target) | Out-Null
New-Item -ItemType Directory -Force (Join-Path $plutonium 'storage/t6/raw/scriptdata') | Out-Null
[IO.File]::Copy((Join-Path $root 'adapters/bo2/blacklands_probe.gsc'),$target,$false)
@{path=$target;sha256=(Get-FileHash -LiteralPath $target).Hash} | ConvertTo-Json |
    Set-Content -LiteralPath (Join-Path $root 'work/bo2-deployment.json') -Encoding UTF8
Write-Output "Added Zombies-only probe: $target"
