param([int]$Seconds = 90, [double]$SaveEverySeconds = 2)
$ErrorActionPreference='Stop'
if ($Seconds -lt 1 -or $Seconds -gt 180) {throw 'Duration must be 1..180 seconds.'}
if ($SaveEverySeconds -lt 0 -or $SaveEverySeconds -gt 60) {throw 'SaveEverySeconds must be 0..60.'}
$root=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$python=Join-Path $root 'work/render-venv/Scripts/python.exe'
if (!(Test-Path -LiteralPath $python)) {throw 'Run scripts/Setup-RenderProbe.ps1 first.'}
$output=Join-Path $root ('work/composite-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0,8))
Write-Output 'Both game windows must be restored. In BL2 activate: pyexec blacklands_passthrough/start_isolation_mode.py'
Write-Output 'External viewing experiment only; controls still go to the original game windows.'
& $python (Join-Path $root 'bridge/composite_preview.py') --seconds $Seconds --save-every $SaveEverySeconds --output $output
if ($LASTEXITCODE -ne 0) {throw "Composite preview failed. Inspect $output"}
Write-Output "Composite evidence saved under $output"
