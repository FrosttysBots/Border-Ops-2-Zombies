param([string]$Python = 'C:\Python314\python.exe',[int]$Seconds = 90)
$ErrorActionPreference='Stop'
if ($Seconds -lt 1 -or $Seconds -gt 180) {throw 'Duration must be 1..180 seconds.'}
$root=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$output=Join-Path $root ('work/player-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0,8) + '.json')
& $Python (Join-Path $root 'bridge/record_player.py') --seconds $Seconds --output $output
if ($LASTEXITCODE -ne 0) {throw "Player observation failed. Inspect $output"}
