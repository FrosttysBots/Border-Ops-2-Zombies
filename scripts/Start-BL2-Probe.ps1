param()
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$config = Get-Content -LiteralPath (Join-Path $root 'work/installations.json') -Raw | ConvertFrom-Json
$bin = Join-Path $config.borderlands2 'Binaries/Win32'
if (!(Test-Path -LiteralPath (Join-Path $bin 'ddraw.dll'))) {throw 'Run Install-BL2-Probe.ps1 first.'}
if (Get-Process Borderlands2 -ErrorAction SilentlyContinue) {throw 'Close the existing BL2 process before launching the probe session.'}
$mailbox = Join-Path $env:LOCALAPPDATA 'Plutonium/storage/t6/raw/scriptdata'
New-Item -ItemType Directory -Force $mailbox | Out-Null
$previous = $env:BLACKLANDS_MAILBOX
try {
    $env:BLACKLANDS_MAILBOX = $mailbox
    # An intentional interactive game window. No Steam flags or executable patches.
    Start-Process -FilePath (Join-Path $bin 'Borderlands2.exe') -WorkingDirectory $bin -WindowStyle Normal
} finally {$env:BLACKLANDS_MAILBOX = $previous}
Write-Output 'In BL2, enable Black Lands 2 Passthrough Probe in Mods and load a test character. Probe v0.2.0 can also find the default Plutonium mailbox on normal launches.'
