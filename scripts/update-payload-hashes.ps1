[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repositoryRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$payloadRoot = Join-Path $repositoryRoot 'windows-installer\payload'
$modulePath = Join-Path $repositoryRoot 'windows-installer\src\resource_hashes.py'
$requiredNames = @(
    'adb.exe',
    'AdbWinApi.dll',
    'AdbWinUsbApi.dll',
    'NOTICE.txt',
    'app-manager.apk',
    'appmanager-shortcut.apk'
)

$rows = foreach ($name in $requiredNames) {
    $path = Join-Path $payloadRoot $name
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Payload file was not found: $path"
    }
    [pscustomobject]@{
        Name = $name
        Hash = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToUpperInvariant()
    }
}

$lines = @(
    '"""Generated checksums for files embedded in the Windows installer."""',
    '',
    'RESOURCE_HASHES = {'
)
foreach ($row in $rows) {
    $lines += "    `"$($row.Name)`": `"$($row.Hash)`","
}
$lines += '}'

$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[System.IO.File]::WriteAllLines($modulePath, $lines, $utf8NoBom)
Write-Host "Updated: $modulePath"
foreach ($row in $rows) {
    Write-Host "$($row.Hash)  $($row.Name)"
}
