[CmdletBinding()]
param(
    [string]$KeystorePath = (Join-Path $env:USERPROFILE '.android\debug.keystore')
)

. (Join-Path $PSScriptRoot 'common.ps1')

if (-not [System.IO.Path]::IsPathRooted($KeystorePath)) {
    $KeystorePath = Join-Path (Get-Location).Path $KeystorePath
}
$KeystorePath = [System.IO.Path]::GetFullPath($KeystorePath)

$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\app-manager')).Path
$manifestPath = Join-Path $projectRoot 'AndroidManifest.xml'
$resourcePath = Join-Path $projectRoot 'res'
$sourceRoot = Join-Path $projectRoot 'src'
$outputPath = Join-Path $projectRoot 'app-manager.apk'
$buildPath = Join-Path $projectRoot 'build'
$generatedPath = Join-Path $buildPath 'generated'
$classesPath = Join-Path $buildPath 'classes'
$dexPath = Join-Path $buildPath 'dex'

foreach ($requiredPath in @($manifestPath, $resourcePath, $sourceRoot)) {
    if (-not (Test-Path -LiteralPath $requiredPath)) {
        throw "Required file or directory was not found: $requiredPath"
    }
}

if (Test-Path -LiteralPath $buildPath) {
    $resolvedBuild = (Resolve-Path -LiteralPath $buildPath).Path
    if (-not $resolvedBuild.StartsWith($projectRoot + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Unsafe build directory path: $resolvedBuild"
    }
    Remove-Item -LiteralPath $resolvedBuild -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $generatedPath, $classesPath, $dexPath | Out-Null

$buildTools = Get-BuildToolsPath -Version '36.1.0'
$androidJar = Get-AndroidJarPath -PreferredApi 34
$javac = Get-JavaToolPath -ToolName 'javac'
$keytool = Get-JavaToolPath -ToolName 'keytool'
$aapt = Join-Path $buildTools 'aapt.exe'
$d8 = Join-Path $buildTools 'd8.bat'
$zipalign = Join-Path $buildTools 'zipalign.exe'
$apksigner = Join-Path $buildTools 'apksigner.bat'

foreach ($tool in @($aapt, $d8, $zipalign, $apksigner)) {
    if (-not (Test-Path -LiteralPath $tool)) {
        throw "Android SDK Build-Tools executable was not found: $tool"
    }
}

Write-Host '1/7 Generating R.java...'
Invoke-Checked -Executable $aapt -Arguments @(
    'package', '-f', '-m', '-J', $generatedPath,
    '-M', $manifestPath, '-S', $resourcePath, '-I', $androidJar
)

Write-Host '2/7 Compiling Java...'
$generatedR = Join-Path $generatedPath 'org\brailleemotion\appmanager\R.java'
$sourceFiles = @(Get-ChildItem -LiteralPath $sourceRoot -Filter '*.java' -File -Recurse | ForEach-Object FullName)
if (-not $sourceFiles) {
    throw "No Java sources were found under: $sourceRoot"
}
$javacArguments = @(
    '-encoding', 'UTF-8',
    '-source', '8', '-target', '8', '-Xlint:-options',
    '-bootclasspath', $androidJar, '-d', $classesPath
)
$javacArguments += $sourceFiles
$javacArguments += $generatedR
Invoke-Checked -Executable $javac -Arguments $javacArguments

Write-Host '3/7 Creating classes.dex...'
$classFiles = @(Get-ChildItem -LiteralPath $classesPath -Filter '*.class' -File -Recurse | ForEach-Object FullName)
if (-not $classFiles) {
    throw 'Compilation did not create any .class files.'
}
Invoke-Checked -Executable $d8 -Arguments (@('--min-api', '26', '--output', $dexPath) + $classFiles)

Write-Host '4/7 Packaging APK...'
$unsignedApk = Join-Path $buildPath 'app-manager-unsigned.apk'
Invoke-Checked -Executable $aapt -Arguments @(
    'package', '-f', '-M', $manifestPath, '-S', $resourcePath,
    '-I', $androidJar, '-F', $unsignedApk
)
Push-Location $dexPath
try {
    Invoke-Checked -Executable $aapt -Arguments @('add', $unsignedApk, 'classes.dex')
} finally {
    Pop-Location
}

Write-Host '5/7 Aligning APK...'
$alignedApk = Join-Path $buildPath 'app-manager-aligned.apk'
Invoke-Checked -Executable $zipalign -Arguments @('-f', '-p', '4', $unsignedApk, $alignedApk)

Write-Host '6/7 Signing APK...'
if (-not (Test-Path -LiteralPath $KeystorePath)) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $KeystorePath) | Out-Null
    Invoke-Checked -Executable $keytool -Arguments @(
        '-genkeypair', '-keystore', $KeystorePath,
        '-storepass', 'android', '-alias', 'androiddebugkey', '-keypass', 'android',
        '-dname', 'CN=Android Debug,O=Android,C=US',
        '-keyalg', 'RSA', '-keysize', '2048', '-validity', '10000'
    )
}
Invoke-Checked -Executable $apksigner -Arguments @(
    'sign', '--ks', $KeystorePath, '--ks-key-alias', 'androiddebugkey',
    '--ks-pass', 'pass:android', '--key-pass', 'pass:android',
    '--v4-signing-enabled', 'false',
    '--out', $outputPath, $alignedApk
)

Write-Host '7/7 Verifying APK...'
Invoke-Checked -Executable $apksigner -Arguments @('verify', '--verbose', '--print-certs', $outputPath)
Invoke-Checked -Executable $aapt -Arguments @('dump', 'badging', $outputPath)
Invoke-Checked -Executable $aapt -Arguments @('dump', 'permissions', $outputPath)

Write-Host "Done: $outputPath"
Write-Host "SHA-256: $(Get-FileSha256 -Path $outputPath)"

Write-Host 'Building the factory-menu shortcut...'
$shortcutBuilder = Join-Path $PSScriptRoot 'build-app-shortcut.ps1'
$stringResources = [xml](Get-Content -LiteralPath `
    (Join-Path $resourcePath 'values\strings.xml') -Raw -Encoding UTF8)
$appManagerNameNode = $stringResources.resources.string |
    Where-Object { $_.name -eq 'app_name' } |
    Select-Object -First 1
$appManagerName = $appManagerNameNode.InnerText
$notInstalledNameNode = $stringResources.resources.string |
    Where-Object { $_.name -eq 'app_manager_not_installed' } |
    Select-Object -First 1
$notInstalledMessage = $notInstalledNameNode.InnerText
& $shortcutBuilder `
    -TargetPackage 'org.brailleemotion.appmanager' `
    -AppName $appManagerName `
    -ShortcutId 'appmanager' `
    -NotInstalledMessage $notInstalledMessage `
    -KeystorePath $KeystorePath `
    -Force
