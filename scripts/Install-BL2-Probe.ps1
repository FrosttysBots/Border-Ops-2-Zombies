param()
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$config = Get-Content -LiteralPath (Join-Path $root 'work/installations.json') -Raw | ConvertFrom-Json
$game = [IO.Path]::GetFullPath($config.borderlands2)
$exe = Join-Path $game 'Binaries/Win32/Borderlands2.exe'
if (!(Test-Path -LiteralPath $exe -PathType Leaf)) {throw 'Configured BL2 executable is missing.'}
if (Get-Process Borderlands2 -ErrorAction SilentlyContinue) {throw 'Close Borderlands 2 before adding its SDK.'}
$manifestPath = Join-Path $root 'work/bl2-deployment.json'
if (Test-Path -LiteralPath $manifestPath) {throw 'A deployment manifest already exists. Inspect it before redeploying.'}
$archive = Join-Path $root 'work/downloads/willow2-sdk-v3.8.zip'
$expected = 'E1862DDB282CF845369C9CA1CA70AC180D6104CCE25D8A133557FC74E157B4C7'
if ((Get-FileHash -LiteralPath $archive).Hash -ne $expected) {throw 'SDK archive differs from the inspected v3.8 download.'}
& (Join-Path $PSScriptRoot 'Stage-Probes.ps1')
$sdk = Join-Path $root 'work/downloads/willow2-sdk-v3.8'
$mod = Join-Path $root 'work/staging/sdk_mods/blacklands_passthrough'
$plan = @()
foreach ($file in Get-ChildItem -LiteralPath $sdk -File -Recurse) {
    $relative = $file.FullName.Substring($sdk.Length + 1)
    $plan += [pscustomobject]@{source=$file.FullName;destination=(Join-Path $game $relative);sha256=(Get-FileHash -LiteralPath $file.FullName).Hash}
}
foreach ($file in Get-ChildItem -LiteralPath $mod -File) {
    $plan += [pscustomobject]@{source=$file.FullName;destination=(Join-Path $game ('sdk_mods/blacklands_passthrough/' + $file.Name));sha256=(Get-FileHash -LiteralPath $file.FullName).Hash}
}
# Preflight the whole addition. Never overwrite an existing mod, SDK or game file.
foreach ($item in $plan) {
    if (Test-Path -LiteralPath $item.destination) {throw "Destination already exists: $($item.destination)"}
}
$originalHash = (Get-FileHash -LiteralPath $exe).Hash
$copied = @()
try {
    foreach ($item in $plan) {
        New-Item -ItemType Directory -Force (Split-Path -Parent $item.destination) | Out-Null
        [IO.File]::Copy($item.source,$item.destination,$false)
        $copied += $item
    }
    if ((Get-FileHash -LiteralPath $exe).Hash -ne $originalHash) {throw 'Executable fingerprint changed unexpectedly.'}
    @{sdk_version='3.8';source_url='https://github.com/bl-sdk/willow2-mod-manager/releases/tag/v3.8';game=$game;original_executable_sha256=$originalHash;files=$copied} |
        ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
} catch {
    foreach ($item in $copied) {
        if ((Test-Path -LiteralPath $item.destination) -and (Get-FileHash -LiteralPath $item.destination).Hash -eq $item.sha256) {
            Remove-Item -LiteralPath $item.destination
        }
    }
    throw
}
Write-Output "Added SDK/probe files; original executable unchanged. Deployment manifest: $manifestPath"
