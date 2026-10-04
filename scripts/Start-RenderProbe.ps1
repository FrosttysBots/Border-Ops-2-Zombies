param([int]$Seconds = 30, [switch]$Preview, [int]$SaveEverySeconds = 0,
      [ValidateSet('bl2','bo2')][string]$Source = 'bl2', [switch]$ClientOnly)
$ErrorActionPreference = 'Stop'
if ($Seconds -lt 1 -or $Seconds -gt 180) {throw 'Duration must be 1..180 seconds.'}
if ($SaveEverySeconds -lt 0 -or $SaveEverySeconds -gt 60) {throw 'Save interval must be 0..60 seconds.'}
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$python = Join-Path $root 'work/render-venv/Scripts/python.exe'
if (!(Test-Path -LiteralPath $python)) {throw 'Run scripts/Setup-RenderProbe.ps1 first.'}
$output = Join-Path $root ('work/render-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0,8))
$captureArgs = @((Join-Path $root 'bridge/render_probe.py'), '--seconds', $Seconds, '--output', $output, '--save-every', $SaveEverySeconds)
$captureArgs += @('--source', $Source)
if ($Preview) {$captureArgs += '--preview'}
if ($ClientOnly) {$captureArgs += '--client-only'}
& $python @captureArgs
if ($LASTEXITCODE -ne 0) {throw "Capture failed; inspect report under $output"}
Write-Output "Rendering evidence saved under $output"
