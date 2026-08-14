Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-AndroidSdkPath {
    $candidates = @(@(
        $env:ANDROID_SDK_ROOT,
        $env:ANDROID_HOME,
        (Join-Path $env:LOCALAPPDATA 'Android\Sdk')
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) })

    if (-not $candidates) {
        throw 'Android SDK was not found. Install Android Studio and Android SDK Platform-Tools.'
    }

    return (Resolve-Path -LiteralPath $candidates[0]).Path
}

function Get-AdbPath {
    $sdkPath = Get-AndroidSdkPath
    $adbPath = Join-Path $sdkPath 'platform-tools\adb.exe'
    if (-not (Test-Path -LiteralPath $adbPath)) {
        throw "adb.exe was not found: $adbPath"
    }
    return $adbPath
}

function Get-BuildToolsPath {
    param([string]$Version = '36.1.0')

    $sdkPath = Get-AndroidSdkPath
    $buildToolsPath = Join-Path $sdkPath "build-tools\$Version"
    if (-not (Test-Path -LiteralPath $buildToolsPath -PathType Container)) {
        throw "Android SDK Build-Tools $Version were not found. Install this exact version with SDK Manager."
    }
    return (Resolve-Path -LiteralPath $buildToolsPath).Path
}

function Get-AndroidJarPath {
    param([int]$PreferredApi = 34)

    $sdkPath = Get-AndroidSdkPath
    $androidJar = Join-Path $sdkPath "platforms\android-$PreferredApi\android.jar"
    if (-not (Test-Path -LiteralPath $androidJar -PathType Leaf)) {
        throw "android.jar was not found. Install Android SDK Platform $PreferredApi with SDK Manager."
    }
    return $androidJar
}

function Get-JavaToolPath {
    param([Parameter(Mandatory)][string]$ToolName)

    $studioTool = Join-Path ${env:ProgramFiles} "Android\Android Studio\jbr\bin\$ToolName.exe"
    if (Test-Path -LiteralPath $studioTool) {
        return $studioTool
    }

    $command = Get-Command $ToolName -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    throw "$ToolName was not found. Install Android Studio with JBR/JDK."
}

function Invoke-Checked {
    param(
        [Parameter(Mandatory)][string]$Executable,
        [Parameter()][string[]]$Arguments = @()
    )

    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $Executable $($Arguments -join ' ')"
    }
}

function Get-ConnectedAdbSerial {
    param([Parameter(Mandatory)][string]$AdbPath)

    Invoke-Checked -Executable $AdbPath -Arguments @('start-server')
    $rows = & $AdbPath devices
    if ($LASTEXITCODE -ne 0) {
        throw 'Failed to read the ADB device list.'
    }

    $devices = @($rows | Select-Object -Skip 1 | Where-Object { $_ -match '^([^\s]+)\s+device$' })
    $unauthorized = @($rows | Select-Object -Skip 1 | Where-Object { $_ -match '\s+unauthorized$' })
    $offline = @($rows | Select-Object -Skip 1 | Where-Object { $_ -match '\s+offline$' })

    if ($unauthorized) {
        throw 'ADB device is unauthorized. Confirm the USB debugging prompt on Braille eMotion.'
    }
    if ($offline) {
        throw 'ADB device is offline. Reconnect USB and try again.'
    }
    if ($devices.Count -eq 0) {
        throw 'No ADB device was found. Check the cable, driver, and USB debugging.'
    }
    if ($devices.Count -gt 1) {
        throw 'Multiple ADB devices are connected. Leave only Braille eMotion connected.'
    }

    return ([regex]::Match($devices[0], '^([^\s]+)').Groups[1].Value)
}

function Assert-BrailleEmotion {
    param(
        [Parameter(Mandatory)][string]$AdbPath,
        [Parameter(Mandatory)][string]$Serial
    )

    $model = (& $AdbPath -s $Serial shell getprop ro.product.model).Trim()
    $device = (& $AdbPath -s $Serial shell getprop ro.product.device).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw 'Failed to read the connected device model.'
    }
    if ($model -ne 'B340' -and $device -notmatch 'Braille_eMotion') {
        throw "Unexpected device: model=$model, device=$device. Installation was stopped."
    }
}

function Get-FileSha256 {
    param([Parameter(Mandatory)][string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToUpperInvariant()
}
