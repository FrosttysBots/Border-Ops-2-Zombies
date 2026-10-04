param([string]$Python = 'C:\Python314\python.exe')
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
Push-Location $root
try {
    $venvPython = Join-Path $root 'work/render-venv/Scripts/python.exe'
    if (!(Test-Path -LiteralPath $venvPython)) {
        & $Python -m venv (Join-Path $root 'work/render-venv')
        if ($LASTEXITCODE -ne 0) {throw 'Rendering environment setup failed.'}
    }
    & $venvPython -m pip install --only-binary=:all: -r bridge/render-requirements.txt
    if ($LASTEXITCODE -ne 0) {throw 'Rendering dependency installation failed.'}
} finally {Pop-Location}
