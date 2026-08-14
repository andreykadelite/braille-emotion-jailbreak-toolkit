[CmdletBinding()]
param(
    [switch]$RebuildApks,
    [string]$KeystorePath = (Join-Path $env:USERPROFILE '.android\debug.keystore'),
    [switch]$RefreshPlatformTools,
    [switch]$ReuseBuildEnvironment,
    [string]$BootstrapPython = 'python'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repositoryRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$venvRoot = Join-Path $repositoryRoot '.build-venv'
$venvPython = Join-Path $venvRoot 'Scripts\python.exe'

& $BootstrapPython -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 11) and sys.maxsize > 2**32 else 1)"
if ($LASTEXITCODE -ne 0) {
    throw 'Release build requires 64-bit Python 3.11.'
}

if ($RebuildApks) {
    & (Join-Path $PSScriptRoot 'build-app-manager.ps1') -KeystorePath $KeystorePath
    if ($LASTEXITCODE -ne 0) {
        throw 'APK build failed.'
    }
    & (Join-Path $PSScriptRoot 'prepare-installer-payload.ps1') `
        -RefreshPlatformTools:$RefreshPlatformTools
    if ($LASTEXITCODE -ne 0) {
        throw 'Could not prepare the Windows installer payload.'
    }
} elseif ($RefreshPlatformTools) {
    & (Join-Path $PSScriptRoot 'prepare-installer-payload.ps1') -RefreshPlatformTools
    if ($LASTEXITCODE -ne 0) {
        throw 'Could not refresh Android Platform-Tools.'
    }
}

if (-not $ReuseBuildEnvironment -or -not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    if (Test-Path -LiteralPath $venvRoot) {
        $resolvedVenv = (Resolve-Path -LiteralPath $venvRoot).Path
        if (-not $resolvedVenv.StartsWith($repositoryRoot + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Unsafe build environment path: $resolvedVenv"
        }
        Remove-Item -LiteralPath $resolvedVenv -Recurse -Force
    }
    & $BootstrapPython -m venv $venvRoot
    if ($LASTEXITCODE -ne 0) {
        throw 'Could not create the Python build environment.'
    }
    & $venvPython -m pip install --disable-pip-version-check `
        -r (Join-Path $repositoryRoot 'windows-installer\requirements-build.txt')
    if ($LASTEXITCODE -ne 0) {
        throw 'Could not install pinned Python build dependencies.'
    }
}

& $venvPython -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 11) and sys.maxsize > 2**32 else 1)"
if ($LASTEXITCODE -ne 0) {
    throw 'The isolated build environment is not using 64-bit Python 3.11.'
}

& (Join-Path $repositoryRoot 'windows-installer\build-windows-installer.ps1') `
    -PythonExe $venvPython
if ($LASTEXITCODE -ne 0) {
    throw 'Windows installer build failed.'
}

Write-Host ''
Write-Host 'Release build completed.'
Write-Host "APK: $(Join-Path $repositoryRoot 'windows-installer\payload\app-manager.apk')"
Write-Host "EXE: $(Join-Path $repositoryRoot 'windows-installer\dist\Braille-eMotion-AppManager-Setup.exe')"
