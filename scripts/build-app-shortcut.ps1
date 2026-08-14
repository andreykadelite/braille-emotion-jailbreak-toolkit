[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$TargetPackage,
    [Parameter(Mandatory)][string]$AppName,
    [Parameter(Mandatory)][string]$ShortcutId,
    [string]$NotInstalledMessage,
    [string]$KeystorePath = (Join-Path $env:USERPROFILE '.android\debug.keystore'),
    [switch]$Force
)

. (Join-Path $PSScriptRoot 'common.ps1')

if (-not [System.IO.Path]::IsPathRooted($KeystorePath)) {
    $KeystorePath = Join-Path (Get-Location).Path $KeystorePath
}
$KeystorePath = [System.IO.Path]::GetFullPath($KeystorePath)

if ($TargetPackage -notmatch '^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+$') {
    throw 'TargetPackage is not a valid Android package name.'
}
if ($ShortcutId -notmatch '^[a-z][a-z0-9_]{0,39}$') {
    throw 'ShortcutId must start with a-z and contain only a-z, 0-9, or underscore (maximum 40 characters).'
}
if ([string]::IsNullOrWhiteSpace($AppName)) {
    throw 'AppName cannot be empty.'
}
if ($AppName.Length -gt 80) {
    throw 'AppName cannot be longer than 80 characters.'
}
if ($AppName -match '[\x00-\x1F]') {
    throw 'AppName cannot contain control characters, tabs, or line breaks.'
}
if ([string]::IsNullOrWhiteSpace($NotInstalledMessage)) {
    $NotInstalledMessage = "$AppName is not installed"
}
if ($NotInstalledMessage.Length -gt 160 -or $NotInstalledMessage -match '[\x00-\x1F]') {
    throw 'NotInstalledMessage cannot exceed 160 characters or contain control characters.'
}

$bundleRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$outputRoot = Join-Path $bundleRoot 'generated-shortcuts'
$projectRoot = Join-Path $outputRoot $ShortcutId
$buildRoot = Join-Path $projectRoot 'build'
$sourceRoot = Join-Path $projectRoot 'src'
$resourceRoot = Join-Path $projectRoot 'res\values'
$generatedRoot = Join-Path $buildRoot 'generated'
$classesRoot = Join-Path $buildRoot 'classes'
$dexRoot = Join-Path $buildRoot 'dex'
$wrapperPackage = "com.selvashc.shortcut.$ShortcutId"
$packagePath = $wrapperPackage.Replace('.', '\')
$javaDirectory = Join-Path $sourceRoot $packagePath
$javaPath = Join-Path $javaDirectory 'MainActivity.java'
$manifestPath = Join-Path $projectRoot 'AndroidManifest.xml'
$stringsPath = Join-Path $resourceRoot 'strings.xml'
$outputApk = Join-Path $projectRoot "$ShortcutId-shortcut.apk"

if (Test-Path -LiteralPath $projectRoot) {
    $resolvedProject = (Resolve-Path -LiteralPath $projectRoot).Path
    if (-not $resolvedProject.StartsWith($outputRoot + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Unsafe generated project path: $resolvedProject"
    }
    if (-not $Force) {
        throw "The generated shortcut already exists: $resolvedProject. Use another ShortcutId or add -Force to replace it."
    }
    Remove-Item -LiteralPath $resolvedProject -Recurse -Force
}
New-Item -ItemType Directory -Force -Path `
    $javaDirectory, $resourceRoot, $generatedRoot, $classesRoot, $dexRoot | Out-Null

$androidAppName = $AppName.Replace('\', '\\').Replace('@', '\@').Replace('?', '\?').Replace("'", "\'").Replace('"', '\"')
$escapedAppName = [System.Security.SecurityElement]::Escape($androidAppName)
$androidNotInstalledMessage = $NotInstalledMessage.Replace('\', '\\').Replace('@', '\@').Replace('?', '\?').Replace("'", "\'").Replace('"', '\"')
$escapedNotInstalledMessage = [System.Security.SecurityElement]::Escape($androidNotInstalledMessage)
$escapedTargetPackage = [System.Security.SecurityElement]::Escape($TargetPackage)
$manifest = @"
<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="$wrapperPackage"
    android:versionCode="1"
    android:versionName="1.0">

    <uses-sdk android:minSdkVersion="26" android:targetSdkVersion="34" />

    <queries>
        <package android:name="$escapedTargetPackage" />
    </queries>

    <application
        android:allowBackup="false"
        android:label="@string/app_name"
        android:supportsRtl="true"
        android:theme="@android:style/Theme.NoDisplay">
        <activity
            android:name="$wrapperPackage.MainActivity"
            android:excludeFromRecents="true"
            android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>
    </application>
</manifest>
"@
$strings = @"
<?xml version="1.0" encoding="utf-8"?>
<resources>
    <string name="app_name" formatted="false">$escapedAppName</string>
    <string name="target_package" translatable="false">$escapedTargetPackage</string>
    <string name="target_not_installed" formatted="false">$escapedNotInstalledMessage</string>
</resources>
"@
$java = @"
package $wrapperPackage;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.os.Bundle;
import android.widget.Toast;

public final class MainActivity extends Activity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        String targetPackage = getString(R.string.target_package);
        Intent launchIntent = getPackageManager().getLaunchIntentForPackage(targetPackage);
        if (launchIntent == null) {
            showNotInstalledMessage();
        } else {
            try {
                launchIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                startActivity(launchIntent);
            } catch (ActivityNotFoundException exception) {
                showNotInstalledMessage();
            }
        }
        finish();
    }

    private void showNotInstalledMessage() {
        Toast.makeText(this, getString(R.string.target_not_installed), Toast.LENGTH_LONG).show();
    }
}
"@

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($manifestPath, $manifest, $utf8NoBom)
[System.IO.File]::WriteAllText($stringsPath, $strings, $utf8NoBom)
[System.IO.File]::WriteAllText($javaPath, $java, $utf8NoBom)

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

Write-Host "Building shortcut $wrapperPackage -> $TargetPackage"
Invoke-Checked -Executable $aapt -Arguments @(
    'package', '-f', '-m', '-J', $generatedRoot,
    '-M', $manifestPath, '-S', (Split-Path -Parent $resourceRoot), '-I', $androidJar
)
$generatedR = Join-Path $generatedRoot "$packagePath\R.java"
Invoke-Checked -Executable $javac -Arguments @(
    '-source', '8', '-target', '8', '-Xlint:-options',
    '-bootclasspath', $androidJar, '-d', $classesRoot,
    $javaPath, $generatedR
)
$classFiles = @(Get-ChildItem -LiteralPath $classesRoot -Filter '*.class' -File -Recurse | ForEach-Object FullName)
if (-not $classFiles) {
    throw 'Compilation did not create any .class files.'
}
Invoke-Checked -Executable $d8 -Arguments (@('--min-api', '26', '--output', $dexRoot) + $classFiles)

$unsignedApk = Join-Path $buildRoot "$ShortcutId-unsigned.apk"
$alignedApk = Join-Path $buildRoot "$ShortcutId-aligned.apk"
Invoke-Checked -Executable $aapt -Arguments @(
    'package', '-f', '-M', $manifestPath,
    '-S', (Split-Path -Parent $resourceRoot), '-I', $androidJar, '-F', $unsignedApk
)
Push-Location $dexRoot
try {
    Invoke-Checked -Executable $aapt -Arguments @('add', $unsignedApk, 'classes.dex')
} finally {
    Pop-Location
}
Invoke-Checked -Executable $zipalign -Arguments @('-f', '-p', '4', $unsignedApk, $alignedApk)

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
    '--out', $outputApk, $alignedApk
)
Invoke-Checked -Executable $apksigner -Arguments @('verify', '--verbose', $outputApk)

Write-Host "Done: $outputApk"
Write-Host "Wrapper package: $wrapperPackage"
Write-Host "Target package: $TargetPackage"
Write-Host "SHA-256: $(Get-FileSha256 -Path $outputApk)"
Write-Host 'Install with:'
Write-Host "adb install -r -i com.selvashc.launcher `"$outputApk`""
