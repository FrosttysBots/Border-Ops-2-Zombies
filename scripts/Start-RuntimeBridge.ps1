param([string]$Python = 'C:\Python314\python.exe', [int]$Seconds = 180)
$ErrorActionPreference = 'Stop'
if ($Seconds -lt 1 -or $Seconds -gt 180) {throw 'Duration must be 1..180 seconds.'}
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
Push-Location $root
try {
    & cargo build --locked --manifest-path runtime/Cargo.toml --target-dir work/runtime-target
    if ($LASTEXITCODE -ne 0) {throw 'Rust runtime build failed.'}
    & $Python bridge/runtime_host.py --seconds $Seconds
    if ($LASTEXITCODE -ne 0) {throw 'Rust runtime exited with an error.'}
} finally {Pop-Location}
