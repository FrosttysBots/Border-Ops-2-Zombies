param([int]$Seconds = 90)
$ErrorActionPreference='Stop'
if ($Seconds -lt 1 -or $Seconds -gt 180) {throw 'Duration must be 1..180 seconds.'}
$root=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$python=Join-Path $root 'work/render-venv/Scripts/python.exe'
if (!(Test-Path -LiteralPath $python)) {throw 'Run scripts/Setup-RenderProbe.ps1 first.'}
$output=Join-Path $root ('work/presentation-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0,8))
Write-Output 'Both games must have restored windows. In BL2 activate: pyexec blacklands_passthrough/start_player_probe.py'
Write-Output 'External viewing experiment only; controls still go to the original game windows.'
& $python (Join-Path $root 'bridge/presentation_preview.py') --seconds $Seconds --output $output
if ($LASTEXITCODE -ne 0) {throw "Presentation preview failed. Inspect $output"}
Write-Output "Presentation evidence saved under $output"
