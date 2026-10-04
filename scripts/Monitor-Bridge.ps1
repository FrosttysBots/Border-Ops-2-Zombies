param([string]$Python = 'python', [double]$Seconds = 0)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$mailbox = Join-Path $env:LOCALAPPDATA 'Plutonium/storage/t6/raw/scriptdata'
& $Python (Join-Path $root 'bridge/monitor.py') --mailbox $mailbox --seconds $Seconds
if ($LASTEXITCODE -ne 0) {throw 'Monitor failed.'}
