param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
& (Join-Path $PSScriptRoot 'Stage-Probes.ps1')
Push-Location $root
try {
    & $Python -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) {throw 'Bridge tests failed.'}
} finally {Pop-Location}
