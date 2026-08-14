[CmdletBinding()]
param(
    [string]$ManagerApk,
    [string]$ShortcutApk,
    [switch]$RefreshPlatformTools
)

. (Join-Path $PSScriptRoot 'common.ps1')

$repositoryRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$payloadRoot = Join-Path $repositoryRoot 'windows-installer\payload'
New-Item -ItemType Directory -Force -Path $payloadRoot | Out-Null

if (-not $ManagerApk) {
    $ManagerApk = Join-Path $repositoryRoot 'app-manager\app-manager.apk'
}
if (-not $ShortcutApk) {
    $ShortcutApk = Join-Path $repositoryRoot 'generated-shortcuts\appmanager\appmanager-shortcut.apk'
}

foreach ($item in @(
    @{ Source = $ManagerApk; Destination = 'app-manager.apk' },
    @{ Source = $ShortcutApk; Destination = 'appmanager-shortcut.apk' }
)) {
    if (-not (Test-Path -LiteralPath $item.Source -PathType Leaf)) {
        throw "APK was not found: $($item.Source)"
    }
    Copy-Item -LiteralPath $item.Source -Destination (Join-Path $payloadRoot $item.Destination) -Force
}

$platformNames = @('adb.exe', 'AdbWinApi.dll', 'AdbWinUsbApi.dll', 'NOTICE.txt')
$missingPlatformFile = $platformNames | Where-Object {
    -not (Test-Path -LiteralPath (Join-Path $payloadRoot $_) -PathType Leaf)
}
if ($RefreshPlatformTools -or $missingPlatformFile) {
    $platformRoot = Join-Path (Get-AndroidSdkPath) 'platform-tools'
    foreach ($name in $platformNames) {
        $source = Join-Path $platformRoot $name
        if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
            throw "Android Platform-Tools file was not found: $source"
        }
        Copy-Item -LiteralPath $source -Destination (Join-Path $payloadRoot $name) -Force
    }
}

& (Join-Path $PSScriptRoot 'update-payload-hashes.ps1')
if ($LASTEXITCODE -ne 0) {
    throw 'Could not update embedded payload checksums.'
}
