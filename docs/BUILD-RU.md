# Сборка из исходников

Инструкция рассчитана на чистую 64-разрядную Windows 10 или 11. Команды выполняются в PowerShell из корня клонированного репозитория.

## Закреплённый набор инструментов

- Git for Windows;
- 64-разрядный Python 3.11;
- Android Studio с JBR/JDK;
- Android SDK Platform 34;
- Android SDK Build-Tools 36.1.0;
- Android SDK Platform-Tools 37.0.0 в опубликованном payload;
- PyQt5 5.15.11 и Qt 5.15.2;
- Nuitka 4.1.3;
- MinGW64, который Nuitka загружает в собственный кэш при первой сборке.

Версии Python-пакетов закреплены в `windows-installer/requirements-build.txt`. Скрипт не использует глобально установленную Nuitka и не меняет её версию: все зависимости ставятся в локальную `.build-venv`.

## Подготовка Android SDK

В Android Studio откройте SDK Manager и установите Android SDK Platform 34 и Build-Tools 36.1.0. Platform-Tools нужен для обновления вложенного ADB; опубликованный payload уже содержит версию 37.0.0. Скрипты ищут SDK по `ANDROID_SDK_ROOT`, затем по `ANDROID_HOME`, затем в `%LOCALAPPDATA%\Android\Sdk`.

Проверить нужные файлы можно так:

```powershell
$sdk = Join-Path $env:LOCALAPPDATA 'Android\Sdk'
Test-Path "$sdk\platforms\android-34\android.jar"
Test-Path "$sdk\build-tools\36.1.0\aapt.exe"
Test-Path "$sdk\platform-tools\adb.exe"
```

Все три команды должны вернуть `True`. Если SDK расположен иначе, задайте путь только для текущего окна:

```powershell
$env:ANDROID_SDK_ROOT = 'D:\Android\Sdk'
```

## Клонирование

```powershell
git clone https://github.com/andreykadelite/braille-emotion-jailbreak-toolkit.git
Set-Location .\braille-emotion-jailbreak-toolkit
git status --short
```

Последняя команда должна ничего не вывести.

## Подпись APK

По умолчанию скрипт использует `%USERPROFILE%\.android\debug.keystore`. Если файла нет, он создаётся стандартным ключом Android Debug. Такой ключ удобен для самостоятельной сборки, но не подходит для официального магазина.

Android разрешает обновление пакета только при совпадающей подписи. Сохраните использованный keystore: потеря ключа потребует удалить старую сборку вместе с её данными перед установкой новой.

Для собственного ключа передайте абсолютный путь:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build-app-manager.ps1 `
  -KeystorePath 'C:\keys\braille-emotion.jks'
```

Скрипт ожидает псевдоним и пароль от стандартного debug keystore. Для производственного ключа измените параметры `apksigner` либо используйте собственную безопасную систему подписи. Никогда не добавляйте keystore и пароли в Git.

## Сборка Android-приложения

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build-app-manager.ps1
```

Скрипт выполняет следующие операции:

1. генерирует `R.java` через `aapt`;
2. компилирует Java 8 через JBR/JDK;
3. создаёт `classes.dex` через D8 с минимальным API 26;
4. упаковывает ресурсы и DEX;
5. выравнивает архив через `zipalign`;
6. подписывает основной APK;
7. проверяет подпись, манифест и разрешения;
8. генерирует и собирает мост для заводского меню с той же подписью.

Результаты:

```text
app-manager\app-manager.apk
generated-shortcuts\appmanager\appmanager-shortcut.apk
```

Промежуточные каталоги игнорируются Git.

## Подготовка содержимого Windows-установщика

После новой сборки APK перенесите их в payload и пересчитайте ожидаемые SHA-256:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\prepare-installer-payload.ps1
```

Чтобы осознанно заменить ADB и DLL версией из локального Android SDK:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\prepare-installer-payload.ps1 `
  -RefreshPlatformTools
```

Скрипт копирует только `adb.exe`, `AdbWinApi.dll`, `AdbWinUsbApi.dll` и `NOTICE.txt`, затем обновляет `windows-installer/src/resource_hashes.py`. Проверьте номер версии командой `adb version` и изучите изменения перед коммитом: флаг `-RefreshPlatformTools` намеренно меняет закреплённую зависимость.

Если менялись только уже подготовленные файлы payload, суммы можно пересчитать отдельно:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\update-payload-hashes.ps1
```

## Тесты Python без сборки EXE

```powershell
py -3.11 -m venv .build-venv
.\.build-venv\Scripts\python.exe -m pip install `
  -r .\windows-installer\requirements-build.txt
$env:PYTHONPATH = (Resolve-Path .\windows-installer\src)
$env:QT_QPA_PLATFORM = 'offscreen'
.\.build-venv\Scripts\python.exe -m unittest discover `
  -s .\windows-installer\tests -v
Remove-Item Env:QT_QPA_PLATFORM
Remove-Item Env:PYTHONPATH
```

Проверка целостности встроенных файлов из исходного запуска:

```powershell
.\.build-venv\Scripts\python.exe `
  .\windows-installer\src\braille_emotion_installer.py `
  --cli bundle-check
```

Команда должна вернуть JSON с `"success": true`.

## Сборка одного EXE

Если `.build-venv` уже подготовлена:

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\windows-installer\build-windows-installer.ps1 `
  -PythonExe .\.build-venv\Scripts\python.exe
```

Скрипт проверяет 64-разрядность процесса, запускает тесты, создаёт значок, требует Nuitka ровно 4.1.3, собирает onefile-EXE и запускает готовый файл в режиме `bundle-check`.

Результат:

```text
windows-installer\dist\Braille-eMotion-AppManager-Setup.exe
```

В `dist` должен лежать только этот EXE.

## Полная релизная сборка

Одна команда пересобирает APK, обновляет payload, создаёт чистое Python-окружение и компилирует EXE:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build-release.ps1 `
  -RebuildApks `
  -BootstrapPython 'C:\Users\user\AppData\Local\Programs\Python\Python311\python.exe'
```

Узнать путь к Python 3.11 можно командой `py -3.11 -c "import sys; print(sys.executable)"`. Передайте полученный полный путь:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build-release.ps1 `
  -RebuildApks `
  -BootstrapPython 'C:\Python311\python.exe'
```

Для повторной сборки с готовой `.build-venv` добавьте `-ReuseBuildEnvironment`. Для обновления ADB из SDK добавьте `-RefreshPlatformTools`.

## Проверка APK

```powershell
$bt = Join-Path $env:LOCALAPPDATA 'Android\Sdk\build-tools\36.1.0'
& "$bt\apksigner.bat" verify --verbose --print-certs `
  .\windows-installer\payload\app-manager.apk
& "$bt\aapt.exe" dump badging `
  .\windows-installer\payload\app-manager.apk
```

Для основной сборки ожидаются пакет `org.brailleemotion.appmanager`, версия `1.5`, код версии `6`, минимальный API `26` и целевой API `34`.

## Проверка готового EXE

```powershell
.\windows-installer\dist\Braille-eMotion-AppManager-Setup.exe `
  --cli bundle-check `
  --report-file .\bundle-check.json
Get-Content .\bundle-check.json
```

Для безопасной проверки соединения с eMotion:

```powershell
.\windows-installer\dist\Braille-eMotion-AppManager-Setup.exe `
  --cli status `
  --report-file .\status-report.json
Get-Content .\status-report.json
```

Скрытые CLI-команды установки и удаления предназначены для автоматизированной проверки. Они требуют одновременно `--serial` и `--accept-risk`; без явного согласия изменение устройства блокируется.

## Контрольные суммы релиза

После копирования окончательных файлов в отдельную локальную папку:

```powershell
Get-ChildItem .\release-assets -File |
  Where-Object Name -ne 'SHA256SUMS.txt' |
  Sort-Object Name |
  ForEach-Object {
    '{0}  {1}' -f (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant(), $_.Name
  } | Set-Content .\release-assets\SHA256SUMS.txt -Encoding ascii
```

`release-assets` исключён из Git, чтобы большие бинарные файлы не попадали в историю. Они прикрепляются к GitHub Release отдельно.

## Что означает воспроизводимость

Репозиторий закрепляет версии исходников, Android SDK API/Build-Tools, Python-пакетов и Nuitka. Из чистой среды можно повторить все шаги и получить функционально одинаковые APK и EXE.

Побайтовое совпадение не гарантируется. На результат влияют время ZIP, подпись APK, локальный keystore, версия JBR/JDK, загрузившийся MinGW64 и внутренние временные данные Nuitka onefile. Для строгого сравнения сначала используйте один keystore и одинаковые версии всех внешних инструментов, затем сравнивайте содержимое и поведение, а не только хеш готового файла.
