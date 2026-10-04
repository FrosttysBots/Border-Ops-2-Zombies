param([string]$Python = 'C:\Python314\python.exe', [int]$Seconds = 180)
$ErrorActionPreference = 'Stop'
if ($Seconds -lt 1 -or $Seconds -gt 180) { throw 'Duration must be 1..180 seconds.' }
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$output = Join-Path $root ('work/control-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0,8))
Write-Output 'In BL2 run: pyexec blacklands_passthrough/start_menu_control.py'
& $Python (Join-Path $root 'bridge/control_panel.py') --seconds $Seconds --output $output
if ($LASTEXITCODE -ne 0) { throw "Control panel failed. Inspect $output" }
