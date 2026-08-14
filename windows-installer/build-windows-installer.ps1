[CmdletBinding()]
param(
    [string]$PythonExe = 'python'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$installerRoot = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$source = Join-Path $installerRoot 'src\braille_emotion_installer.py'
$payload = Join-Path $installerRoot 'payload'
$tests = Join-Path $installerRoot 'tests'
$build = Join-Path $installerRoot 'build'
$dist = Join-Path $installerRoot 'dist'
$icon = Join-Path $installerRoot 'installer.ico'
$output = Join-Path $dist 'Braille-eMotion-AppManager-Setup.exe'

function Remove-SafeBuildDirectory {
    param([Parameter(Mandatory)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }
    $resolved = (Resolve-Path -LiteralPath $Path).Path
    if (-not $resolved.StartsWith($installerRoot + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Unsafe build cleanup path: $resolved"
    }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}

if (-not [Environment]::Is64BitOperatingSystem) {
    throw 'This build requires 64-bit Windows.'
}
if (-not [Environment]::Is64BitProcess) {
    throw 'Run the build with 64-bit Python.'
}

$requiredFiles = @(
    $source,
    (Join-Path $payload 'adb.exe'),
    (Join-Path $payload 'AdbWinApi.dll'),
    (Join-Path $payload 'AdbWinUsbApi.dll'),
    (Join-Path $payload 'NOTICE.txt'),
    (Join-Path $payload 'app-manager.apk'),
    (Join-Path $payload 'appmanager-shortcut.apk')
)
foreach ($requiredFile in $requiredFiles) {
    if (-not (Test-Path -LiteralPath $requiredFile -PathType Leaf)) {
        throw "Required build input was not found: $requiredFile"
    }
}

Write-Host '1/6 Checking build dependencies...'
& $PythonExe -c "from PyQt5.QtCore import PYQT_VERSION_STR; from nuitka.Version import getNuitkaVersion; print('PyQt5', PYQT_VERSION_STR, 'Nuitka', getNuitkaVersion())"
if ($LASTEXITCODE -ne 0) {
    throw 'Install the pinned build dependencies from requirements-build.txt.'
}
$nuitkaVersion = (& $PythonExe -m nuitka --version | Select-Object -First 1).Trim()
if ($nuitkaVersion -ne '4.1.3') {
    throw "This release must be compiled with Nuitka 4.1.3; found $nuitkaVersion."
}

Write-Host '2/6 Running unit and accessibility tests...'
$oldPythonPath = $env:PYTHONPATH
$oldQtPlatform = $env:QT_QPA_PLATFORM
try {
    $env:PYTHONPATH = (Join-Path $installerRoot 'src')
    $env:QT_QPA_PLATFORM = 'offscreen'
    & $PythonExe -m unittest discover -s $tests -v
    if ($LASTEXITCODE -ne 0) {
        throw 'Automated tests failed.'
    }
} finally {
    $env:PYTHONPATH = $oldPythonPath
    $env:QT_QPA_PLATFORM = $oldQtPlatform
}

Write-Host '3/6 Creating the application icon...'
& $PythonExe (Join-Path $installerRoot 'tools\create_icon.py')
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $icon -PathType Leaf)) {
    throw 'Could not create installer.ico.'
}

Write-Host '4/6 Cleaning isolated build output...'
Remove-SafeBuildDirectory -Path $build
Remove-SafeBuildDirectory -Path $dist
New-Item -ItemType Directory -Force -Path $build, $dist | Out-Null

Write-Host '5/6 Compiling one portable Windows EXE with Nuitka 4.1.3...'
$nuitkaOutput = Join-Path $build 'nuitka-output'
$nuitkaArguments = @(
    '-m', 'nuitka',
    '--onefile',
    '--mingw64',
    '--assume-yes-for-downloads',
    '--enable-plugin=pyqt5',
    '--windows-console-mode=disable',
    "--output-dir=$nuitkaOutput",
    '--output-filename=Braille-eMotion-AppManager-Setup.exe',
    "--windows-icon-from-ico=$icon",
    "--include-data-files=$(Join-Path $payload 'adb.exe')=payload/adb.exe",
    "--include-data-files=$(Join-Path $payload 'AdbWinApi.dll')=payload/AdbWinApi.dll",
    "--include-data-files=$(Join-Path $payload 'AdbWinUsbApi.dll')=payload/AdbWinUsbApi.dll",
    "--include-data-files=$(Join-Path $payload 'NOTICE.txt')=payload/NOTICE.txt",
    "--include-data-files=$(Join-Path $payload 'app-manager.apk')=payload/app-manager.apk",
    "--include-data-files=$(Join-Path $payload 'appmanager-shortcut.apk')=payload/appmanager-shortcut.apk",
    '--company-name=Braille eMotion tools',
    '--product-name=Braille eMotion App Manager Installer',
    '--file-description=Braille eMotion App Manager Installer',
    '--file-version=2.0.0.0',
    '--product-version=2.0.0.0',
    '--copyright=Application bundle; third-party notices are embedded',
    "--report=$(Join-Path $build 'nuitka-compilation-report.xml')",
    '--remove-output',
    $source
)
& $PythonExe @nuitkaArguments
if ($LASTEXITCODE -ne 0) {
    throw 'Nuitka compilation failed.'
}
$compiledOutput = Join-Path $nuitkaOutput 'Braille-eMotion-AppManager-Setup.exe'
if (-not (Test-Path -LiteralPath $compiledOutput -PathType Leaf)) {
    throw "Expected Nuitka EXE was not created: $compiledOutput"
}
Copy-Item -LiteralPath $compiledOutput -Destination $output -Force
$unexpected = @(Get-ChildItem -LiteralPath $dist -Force | Where-Object { $_.FullName -ne $output })
if ($unexpected) {
    throw "The distribution directory contains unexpected files: $($unexpected.Name -join ', ')"
}

Write-Host '6/6 Testing the frozen bundle in a clean process...'
$reportPath = Join-Path $build 'compiled-bundle-check.json'
$process = Start-Process -FilePath $output -ArgumentList @(
    '--cli', 'bundle-check', '--report-file', $reportPath
) -WindowStyle Hidden -Wait -PassThru
if ($process.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $reportPath -PathType Leaf)) {
    throw "Frozen bundle verification failed with exit code $($process.ExitCode)."
}
$report = Get-Content -LiteralPath $reportPath -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not $report.success) {
    throw 'Compiled bundle reported a resource-verification error.'
}

$file = Get-Item -LiteralPath $output
$sha256 = (Get-FileHash -LiteralPath $output -Algorithm SHA256).Hash
Write-Host "Done: $output"
Write-Host "Size: $($file.Length) bytes"
Write-Host "SHA-256: $sha256"
