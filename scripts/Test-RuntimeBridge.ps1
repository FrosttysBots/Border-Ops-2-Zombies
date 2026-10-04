param([string]$Python = 'C:\Python314\python.exe')
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
Push-Location $root
try {
    & cargo fmt --manifest-path runtime/Cargo.toml -- --check
    if ($LASTEXITCODE -ne 0) {throw 'Rust formatting check failed.'}
    & cargo test --locked --manifest-path runtime/Cargo.toml --target-dir work/runtime-target
    if ($LASTEXITCODE -ne 0) {throw 'Rust protocol tests failed.'}
    & cargo clippy --locked --manifest-path runtime/Cargo.toml --target-dir work/runtime-target --all-targets -- -D warnings
    if ($LASTEXITCODE -ne 0) {throw 'Rust lint check failed.'}
    & cargo build --locked --manifest-path runtime/Cargo.toml --target-dir work/runtime-target
    if ($LASTEXITCODE -ne 0) {throw 'Rust runtime build failed.'}
    & $Python bridge/check_runtime.py
    if ($LASTEXITCODE -ne 0) {throw 'Python/Rust IPC test failed.'}
} finally {Pop-Location}
