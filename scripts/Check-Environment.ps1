param([string]$BO2, [string]$BL2)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$configFile = Join-Path $root 'work/installations.json'
if (Test-Path -LiteralPath $configFile) {
    $saved = Get-Content -LiteralPath $configFile -Raw | ConvertFrom-Json
    if (!$BO2) {$BO2 = $saved.bo2}
    if (!$BL2) {$BL2 = $saved.borderlands2}
}
if (!$BO2 -or !$BL2) {throw 'Supply -BO2 and -BL2 installation folders on the first run.'}
$bo2Exe = Join-Path $BO2 't6zm.exe'
$bl2Exe = Join-Path $BL2 'Binaries/Win32/Borderlands2.exe'
foreach ($exe in @($bo2Exe,$bl2Exe)) {if (!(Test-Path -LiteralPath $exe -PathType Leaf)) {throw "Missing executable: $exe"}}
New-Item -ItemType Directory -Force (Join-Path $root 'work') | Out-Null
@{bo2=(Resolve-Path -LiteralPath $BO2).Path; borderlands2=(Resolve-Path -LiteralPath $BL2).Path} |
    ConvertTo-Json | Set-Content -LiteralPath $configFile -Encoding UTF8
$plutonium = Join-Path $env:LOCALAPPDATA 'Plutonium'
$report = [ordered]@{
    checked_utc = [DateTime]::UtcNow.ToString('o')
    bo2_executable_sha256 = (Get-FileHash -LiteralPath $bo2Exe -Algorithm SHA256).Hash
    bl2_executable_sha256 = (Get-FileHash -LiteralPath $bl2Exe -Algorithm SHA256).Hash
    plutonium_present = (Test-Path -LiteralPath (Join-Path $plutonium 'bin/plutonium-bootstrapper-win32.exe'))
    bl2_loader_present = (Test-Path -LiteralPath (Join-Path $BL2 'Binaries/Win32/ddraw.dll'))
    bl2_sdk_mods_present = (Test-Path -LiteralPath (Join-Path $BL2 'sdk_mods'))
    live_adapters_verified = $false
    note = 'Presence is not loader validation. No games launched or modified by this check.'
}
$report | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $root 'work/environment.json') -Encoding UTF8
[pscustomobject]$report
