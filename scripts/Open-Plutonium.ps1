param()
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$launcher = Join-Path $root 'work/downloads/plutonium.exe'
if (!(Test-Path -LiteralPath $launcher)) {throw 'The official Plutonium launcher has not been downloaded.'}
# This helper is explicitly invoked to open the interactive login/setup window.
Start-Process -FilePath $launcher -WorkingDirectory (Split-Path -Parent $launcher) -WindowStyle Normal
