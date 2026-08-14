from __future__ import annotations

import hashlib
import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from adb_client import (
    AdbClient,
    CommandResult,
    DeviceRecord,
    LogCallback,
    command_error,
)
from installer_errors import InstallerError
from resource_hashes import RESOURCE_HASHES


APP_VERSION = "2.0"
MANAGER_PACKAGE = "org.brailleemotion.appmanager"
MANAGER_VERSION = "1.5"
MANAGER_VERSION_CODE = 6
BRIDGE_PACKAGE = "com.selvashc.shortcut.appmanager"
LEGACY_MANAGER_PACKAGE = "com.selvashc.appmanager"
FACTORY_LAUNCHER = "com.selvashc.launcher/.LauncherActivity"
FACTORY_LAUNCHER_PACKAGE = "com.selvashc.launcher"
MIN_ANDROID_API = 26

ADB_RUNTIME_FILES = ("adb.exe", "AdbWinApi.dll", "AdbWinUsbApi.dll")


@dataclass(frozen=True)
class DeviceInfo:
    serial: str
    state: str
    model: str = ""
    device: str = ""
    manufacturer: str = ""
    brand: str = ""
    android_version: str = ""
    api_level: int = 0
    launcher_present: bool = False
    compatible: bool = False
    compatibility_message: str = ""
    manager_installed: bool = False
    manager_version: str = ""
    bridge_installed: bool = False
    legacy_manager_installed: bool = False

    @property
    def display_name(self) -> str:
        model = self.model or "неизвестная модель"
        if self.state != "device":
            return f"{self.serial} — {translated_device_state(self.state)}"
        suffix = "совместимо" if self.compatible else "не подходит"
        return f"{self.serial} — {model} — {suffix}"

    @property
    def has_manager_components(self) -> bool:
        return self.manager_installed or self.bridge_installed or self.legacy_manager_installed

    @property
    def installation_status(self) -> str:
        if self.manager_installed and self.bridge_installed:
            version = self.manager_version or "не определена"
            return f"Диспетчер приложений установлен. Версия: {version}. Пункт заводского меню установлен."
        if self.manager_installed and not self.bridge_installed:
            version = self.manager_version or "не определена"
            return (
                f"Неполная установка: Диспетчер приложений версии {version} установлен, "
                "но пункт заводского меню отсутствует."
            )
        if self.bridge_installed and not self.manager_installed:
            return (
                "Неполная установка: пункт заводского меню установлен, "
                "но основное приложение отсутствует."
            )
        if self.legacy_manager_installed:
            return "Найдена только старая недоступная версия Диспетчера приложений."
        return "Диспетчер приложений не установлен."


@dataclass(frozen=True)
class ScanReport:
    devices: tuple[DeviceInfo, ...]
    raw_records: tuple[DeviceRecord, ...]
    message: str


@dataclass
class OperationReport:
    success: bool
    message: str
    warnings: list[str] = field(default_factory=list)


def translated_device_state(state: str) -> str:
    return {
        "device": "подключено",
        "unauthorized": "не разрешена USB-отладка",
        "offline": "устройство не отвечает",
        "no permissions": "нет доступа к USB-драйверу",
    }.get(state, state or "неизвестное состояние")


def payload_directory() -> Path:
    module_directory = Path(__file__).resolve().parent
    candidates = (
        module_directory / "payload",
        module_directory.parent / "payload",
        Path(sys.argv[0]).resolve().parent / "payload",
    )
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return candidates[0]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def verify_payload(base: Optional[Path] = None) -> dict[str, Path]:
    base = (base or payload_directory()).resolve()
    verified: dict[str, Path] = {}
    for name, expected_hash in RESOURCE_HASHES.items():
        path = base / name
        if not path.is_file():
            raise InstallerError(
                "payload_missing",
                "Внутренний компонент установщика не найден.",
                f"Отсутствует: {name}",
                (
                    "Скачайте EXE заново целиком.",
                    "Проверьте карантин антивируса или Защитника Windows.",
                ),
            )
        actual_hash = file_sha256(path)
        if actual_hash != expected_hash:
            raise InstallerError(
                "payload_corrupt",
                "Встроенный компонент повреждён или был изменён. Работа остановлена.",
                f"Файл: {name}\nОжидалось: {expected_hash}\nПолучено: {actual_hash}",
                (
                    "Удалите эту копию EXE и получите исходный файл повторно.",
                    "Не отключайте антивирус: сначала проверьте источник файла.",
                ),
            )
        verified[name] = path
    return verified


def prepare_runtime_payload(
    payload: dict[str, Path], cache_root: Optional[Path] = None
) -> dict[str, Path]:
    """Place ADB at a stable verified path while keeping the distribution one-file."""
    if cache_root is None:
        local_data = os.environ.get("LOCALAPPDATA")
        base = Path(local_data) if local_data else Path.home() / "AppData" / "Local"
        cache_root = base / "Braille eMotion AppManager Installer" / "runtime"
    version_directory = cache_root / RESOURCE_HASHES["adb.exe"][:16]
    try:
        version_directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise InstallerError(
            "runtime_cache_failed",
            "Не удалось подготовить встроенный ADB.",
            str(exc),
            (
                "Проверьте доступ к локальной папке текущего пользователя.",
                "Проверьте журнал Защитника Windows или антивируса.",
            ),
        ) from exc

    prepared = dict(payload)
    for name in ADB_RUNTIME_FILES:
        source = payload[name]
        target = version_directory / name
        expected_hash = RESOURCE_HASHES[name]
        try:
            cached_copy_is_valid = target.is_file() and file_sha256(target) == expected_hash
        except OSError:
            cached_copy_is_valid = False
        if cached_copy_is_valid:
            prepared[name] = target
            continue
        temporary = version_directory / f".{name}.{os.getpid()}.tmp"
        try:
            shutil.copyfile(source, temporary)
            if file_sha256(temporary) != expected_hash:
                raise OSError(f"Контрольная сумма временного файла {name} не совпала.")
            os.replace(temporary, target)
        except OSError as exc:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise InstallerError(
                "runtime_cache_failed",
                "Не удалось подготовить встроенный ADB.",
                f"Файл: {name}\n{exc}",
                (
                    "Проверьте журнал Защитника Windows или антивируса.",
                    "Разрешите запуск установщика из локальной папки пользователя.",
                ),
            ) from exc
        prepared[name] = target
    return prepared


def map_install_failure(output: str, component_name: str) -> InstallerError:
    upper = output.upper()
    mappings = (
        (
            "INSTALL_FAILED_UPDATE_INCOMPATIBLE",
            "Подпись установленной версии не совпадает с подписью встроенного APK.",
            (
                "Сначала удалите несовместимую версию кнопкой удаления.",
                "Учтите: при удалении локальные данные диспетчера будут стёрты.",
            ),
        ),
        (
            "INSTALL_FAILED_VERSION_DOWNGRADE",
            "На устройстве уже установлена более новая версия.",
            ("Не понижайте версию без необходимости.",),
        ),
        (
            "INSTALL_FAILED_INSUFFICIENT_STORAGE",
            "На устройстве недостаточно свободного места.",
            ("Освободите место во внутренней памяти eMotion и повторите установку.",),
        ),
        (
            "INSTALL_FAILED_OLDER_SDK",
            "Версия Android на устройстве слишком старая.",
            ("Для Диспетчера приложений требуется Android 8.0 или новее.",),
        ),
        (
            "INSTALL_FAILED_INVALID_APK",
            "Встроенный APK был отклонён Android как некорректный.",
            ("Проверьте контрольную сумму EXE и получите установщик заново.",),
        ),
        (
            "INSTALL_FAILED_USER_RESTRICTED",
            "Установка через USB запрещена настройками устройства.",
            (
                "Проверьте параметры разработчика и разрешение установки через USB.",
                "Если устройство управляется организацией, обратитесь к администратору.",
            ),
        ),
    )
    for marker, message, remedies in mappings:
        if marker in upper:
            return InstallerError(
                "apk_install_failed",
                f"Не удалось установить {component_name}. {message}",
                output,
                remedies,
            )
    return InstallerError(
        "apk_install_failed",
        f"Android не установил {component_name}.",
        output,
        ("Откройте журнал и найдите строку Failure для точной причины.",),
    )


class InstallerEngine:
    def __init__(self, adb: AdbClient, payload: dict[str, Path]) -> None:
        self.adb = adb
        self.payload = payload

    def scan(self, log: Optional[LogCallback] = None) -> ScanReport:
        records = self.adb.list_devices(log)
        infos: list[DeviceInfo] = []
        for record in records:
            if record.state == "device":
                try:
                    infos.append(self.get_device_info(record.serial))
                except InstallerError as exc:
                    infos.append(
                        DeviceInfo(
                            serial=record.serial,
                            state=record.state,
                            compatible=False,
                            compatibility_message=exc.message,
                        )
                    )
            else:
                infos.append(
                    DeviceInfo(
                        serial=record.serial,
                        state=record.state,
                        compatible=False,
                        compatibility_message=self._state_message(record.state),
                    )
                )
        message = self._scan_message(records, infos)
        return ScanReport(tuple(infos), tuple(records), message)

    def get_device_info(self, serial: str) -> DeviceInfo:
        props = {
            "model": self._getprop(serial, "ro.product.model"),
            "device": self._getprop(serial, "ro.product.device"),
            "manufacturer": self._getprop(serial, "ro.product.manufacturer"),
            "brand": self._getprop(serial, "ro.product.brand"),
            "android_version": self._getprop(serial, "ro.build.version.release"),
            "api": self._getprop(serial, "ro.build.version.sdk"),
        }
        try:
            api_level = int(props["api"])
        except ValueError:
            api_level = 0

        launcher_present = self.adb.package_exists(serial, FACTORY_LAUNCHER_PACKAGE)
        model_marker = props["model"].upper().startswith("B3")
        device_marker = "BRAILLE_EMOTION" in props["device"].upper()
        vendor_marker = props["manufacturer"].upper() in {"SELVAS", "HIMS"}
        is_emotion = launcher_present and (device_marker or (vendor_marker and model_marker))

        if not is_emotion:
            compatibility = (
                "Это устройство не похоже на Braille eMotion: не найдено сочетание "
                "заводской оболочки SELVAS и идентификаторов eMotion."
            )
        elif api_level < MIN_ANDROID_API:
            compatibility = (
                f"Android API {api_level or 'не определён'} слишком старый. "
                "Требуется Android 8.0, API 26 или новее."
            )
        else:
            compatibility = "Braille eMotion распознан и готов к работе."

        version = self._package_version(serial, MANAGER_PACKAGE)
        return DeviceInfo(
            serial=serial,
            state="device",
            model=props["model"],
            device=props["device"],
            manufacturer=props["manufacturer"],
            brand=props["brand"],
            android_version=props["android_version"],
            api_level=api_level,
            launcher_present=launcher_present,
            compatible=is_emotion and api_level >= MIN_ANDROID_API,
            compatibility_message=compatibility,
            manager_installed=bool(version[0]),
            manager_version=version[0],
            bridge_installed=self.adb.package_exists(serial, BRIDGE_PACKAGE),
            legacy_manager_installed=self.adb.package_exists(
                serial, LEGACY_MANAGER_PACKAGE
            ),
        )

    def install(self, serial: str, log: LogCallback) -> OperationReport:
        warnings: list[str] = []
        self._event(log, "status", "Повторная проверка устройства…", 2)
        info = self.get_device_info(serial)
        self._require_compatible(info)
        manager_existed = info.manager_installed

        self._event(log, "status", "Установка Диспетчера приложений…", 12)
        manager_result = self.adb.run(
            (
                "-s",
                serial,
                "install",
                "-r",
                "-i",
                FACTORY_LAUNCHER_PACKAGE,
                str(self.payload["app-manager.apk"]),
            ),
            timeout=180,
            log=log,
        )
        if not manager_result.ok or "Success" not in manager_result.output:
            raise map_install_failure(manager_result.output, "Диспетчер приложений")

        self._event(log, "status", "Установка пункта заводского меню…", 34)
        bridge_result = self.adb.run(
            (
                "-s",
                serial,
                "install",
                "-r",
                "-i",
                FACTORY_LAUNCHER_PACKAGE,
                str(self.payload["appmanager-shortcut.apk"]),
            ),
            timeout=120,
            log=log,
        )
        if not bridge_result.ok or "Success" not in bridge_result.output:
            if not manager_existed:
                self._event(
                    log,
                    "warning",
                    "Мост не установился; удаляю новую неполную установку диспетчера.",
                    38,
                )
                self.adb.run(("-s", serial, "uninstall", MANAGER_PACKAGE), timeout=60, log=log)
            raise map_install_failure(bridge_result.output, "пункт заводского меню")

        self._event(log, "status", "Настройка разрешений…", 52)
        permission_warning = self._configure_permissions(serial, info.api_level, log)
        if permission_warning:
            warnings.append(permission_warning)

        self._event(log, "status", "Проверка установленных пакетов…", 68)
        self._verify_install(serial, warnings, log)

        self._event(log, "status", "Возврат заводской оболочки…", 82)
        self._restore_factory_home(serial, warnings, log)

        self._event(log, "status", "Очистка старой версии диспетчера…", 91)
        if self.adb.package_exists(serial, LEGACY_MANAGER_PACKAGE):
            result = self.adb.run(
                ("-s", serial, "uninstall", LEGACY_MANAGER_PACKAGE),
                timeout=60,
                log=log,
            )
            if not result.ok or "Success" not in result.output:
                warnings.append("Старая недоступная версия диспетчера не удалена.")

        self._event(log, "status", "Установка и проверка завершены.", 100)
        return OperationReport(
            True,
            "Диспетчер приложений 1.5 установлен. Путь: Домой → Онлайн библиотеки → Диспетчер приложений.",
            warnings,
        )

    def uninstall(
        self,
        serial: str,
        log: LogCallback,
    ) -> OperationReport:
        warnings: list[str] = []
        self._event(log, "status", "Повторная проверка устройства…", 3)
        info = self.get_device_info(serial)
        self._require_compatible(info)
        bridge_existed = info.bridge_installed
        manager_existed = info.manager_installed
        legacy_existed = info.legacy_manager_installed

        self._event(log, "status", "Удаление пункта заводского меню…", 18)
        self._uninstall_if_present(serial, BRIDGE_PACKAGE, "пункт заводского меню", log)

        self._event(log, "status", "Удаление Диспетчера приложений…", 42)
        try:
            self._uninstall_if_present(serial, MANAGER_PACKAGE, "Диспетчер приложений", log)
            self._uninstall_if_present(
                serial, LEGACY_MANAGER_PACKAGE, "старую версию диспетчера", log
            )
        except InstallerError:
            if bridge_existed and self.adb.package_exists(serial, MANAGER_PACKAGE):
                rollback = self.adb.run(
                    (
                        "-s",
                        serial,
                        "install",
                        "-r",
                        "-i",
                        FACTORY_LAUNCHER_PACKAGE,
                        str(self.payload["appmanager-shortcut.apk"]),
                    ),
                    timeout=120,
                    log=log,
                )
                if not rollback.ok:
                    warnings.append("Не удалось вернуть пункт меню после ошибки удаления.")
            raise

        self._event(log, "status", "Проверка удаления компонентов…", 70)
        self._event(log, "status", "Возврат заводской оболочки…", 84)
        self._restore_factory_home(serial, warnings, log)

        if self.adb.package_exists(serial, MANAGER_PACKAGE) or self.adb.package_exists(
            serial, BRIDGE_PACKAGE
        ):
            raise InstallerError(
                "uninstall_verify_failed",
                "После удаления на устройстве остались компоненты Диспетчера приложений.",
                "Повторная проверка pm path обнаружила пакет.",
                ("Переподключите устройство и повторите удаление.",),
            )

        self._event(log, "status", "Удаление и проверка завершены.", 100)
        if manager_existed or bridge_existed or legacy_existed:
            message = "Диспетчер приложений и его пункт заводского меню удалены."
        else:
            message = "Диспетчер приложений уже отсутствовал; остаточные компоненты проверены."
        return OperationReport(True, message, warnings)

    def _getprop(self, serial: str, name: str) -> str:
        result = self.adb.shell(serial, ("getprop", name), timeout=10, log_command=False)
        if not result.ok:
            raise command_error("Не удалось прочитать сведения об устройстве.", result)
        return result.output.strip()

    def _package_version(self, serial: str, package: str) -> tuple[str, int]:
        if not self.adb.package_exists(serial, package):
            return "", 0
        result = self.adb.shell(
            serial, ("dumpsys", "package", package), timeout=15, log_command=False
        )
        if not result.ok:
            return "", 0
        version_name = ""
        version_code = 0
        name_match = re.search(r"\bversionName=([^\s]+)", result.output)
        code_match = re.search(r"\bversionCode=(\d+)", result.output)
        if name_match:
            version_name = name_match.group(1)
        if code_match:
            version_code = int(code_match.group(1))
        return version_name, version_code

    def _configure_permissions(
        self, serial: str, api_level: int, log: LogCallback
    ) -> str:
        warning_parts: list[str] = []
        if api_level >= 30:
            storage = self.adb.shell(
                serial,
                ("appops", "set", MANAGER_PACKAGE, "MANAGE_EXTERNAL_STORAGE", "allow"),
                timeout=20,
                log=log,
            )
        else:
            storage = self.adb.shell(
                serial,
                ("pm", "grant", MANAGER_PACKAGE, "android.permission.READ_EXTERNAL_STORAGE"),
                timeout=20,
                log=log,
            )
        storage_allowed = self._android_command_succeeded(storage)
        if storage_allowed and api_level >= 30:
            storage_allowed = self._appop_is_allowed(
                serial, "MANAGE_EXTERNAL_STORAGE", log
            )
        if not storage_allowed:
            warning_parts.append("доступ к папке Download нужно будет разрешить на устройстве")

        install = self.adb.shell(
            serial,
            ("appops", "set", MANAGER_PACKAGE, "REQUEST_INSTALL_PACKAGES", "allow"),
            timeout=20,
            log=log,
        )
        install_allowed = self._android_command_succeeded(install) and self._appop_is_allowed(
            serial, "REQUEST_INSTALL_PACKAGES", log
        )
        if not install_allowed:
            warning_parts.append("установку неизвестных приложений нужно будет разрешить вручную")
        if warning_parts:
            return "Не все разрешения настроены автоматически: " + "; ".join(warning_parts) + "."
        return ""

    def _appop_is_allowed(
        self, serial: str, operation: str, log: LogCallback
    ) -> bool:
        result = self.adb.shell(
            serial,
            ("appops", "get", MANAGER_PACKAGE, operation),
            timeout=20,
            log=log,
        )
        return self._android_command_succeeded(result) and bool(
            re.search(rf"\b{re.escape(operation)}\s*:\s*allow\b", result.output)
        )

    @staticmethod
    def _android_command_succeeded(result: CommandResult) -> bool:
        if not result.ok:
            return False
        return not bool(
            re.search(
                r"(?im)^\s*(error|exception|securityexception|unknown operation)\b",
                result.output,
            )
        )

    def _verify_install(
        self, serial: str, warnings: list[str], log: LogCallback
    ) -> None:
        version_name, version_code = self._package_version(serial, MANAGER_PACKAGE)
        if version_name != MANAGER_VERSION or version_code != MANAGER_VERSION_CODE:
            raise InstallerError(
                "install_verify_failed",
                "Установленная версия Диспетчера приложений не прошла проверку.",
                f"Получено: versionName={version_name or '?'} versionCode={version_code or '?'}\n"
                f"Ожидалось: versionName={MANAGER_VERSION} versionCode={MANAGER_VERSION_CODE}",
            )
        if not self.adb.package_exists(serial, BRIDGE_PACKAGE):
            raise InstallerError(
                "bridge_verify_failed",
                "Пункт заводского меню не найден после установки.",
            )

        manager_activity = self.adb.shell(
            serial,
            (
                "cmd",
                "package",
                "resolve-activity",
                "--brief",
                "-a",
                "android.intent.action.MAIN",
                "-c",
                "android.intent.category.LAUNCHER",
                MANAGER_PACKAGE,
            ),
            timeout=20,
            log=log,
        )
        if not manager_activity.ok or f"{MANAGER_PACKAGE}/" not in manager_activity.output:
            raise InstallerError(
                "activity_verify_failed",
                "Android не нашёл запускаемый экран Диспетчера приложений.",
                manager_activity.output,
            )

        bridge_activity = self.adb.shell(
            serial,
            (
                "cmd",
                "package",
                "resolve-activity",
                "--brief",
                "-a",
                "android.intent.action.MAIN",
                "-c",
                "android.intent.category.LAUNCHER",
                BRIDGE_PACKAGE,
            ),
            timeout=20,
            log=log,
        )
        if not bridge_activity.ok or f"{BRIDGE_PACKAGE}/" not in bridge_activity.output:
            raise InstallerError(
                "bridge_activity_verify_failed",
                "Android не нашёл запускаемый пункт заводского меню.",
                bridge_activity.output,
            )

        path_result = self.adb.shell(
            serial, ("pm", "path", MANAGER_PACKAGE), timeout=15, log_command=False
        )
        if path_result.ok and path_result.output.startswith("package:"):
            device_path = path_result.output.splitlines()[0].replace("package:", "", 1).strip()
            hash_result = self.adb.shell(
                serial, ("sha256sum", device_path), timeout=30, log=log
            )
            if hash_result.ok:
                actual = hash_result.output.split()[0].upper() if hash_result.output else ""
                if actual != RESOURCE_HASHES["app-manager.apk"]:
                    raise InstallerError(
                        "installed_hash_mismatch",
                        "Контрольная сумма установленного APK не совпала с исходной.",
                        f"Получено: {actual}",
                    )
            else:
                warnings.append("Android не поддерживает sha256sum; проверены версия и запускаемый экран.")

    def _restore_factory_home(
        self, serial: str, warnings: list[str], log: LogCallback
    ) -> None:
        current = self.adb.shell(
            serial,
            (
                "cmd",
                "package",
                "resolve-activity",
                "--brief",
                "-a",
                "android.intent.action.MAIN",
                "-c",
                "android.intent.category.HOME",
            ),
            timeout=20,
            log=log,
        )
        if not current.ok or FACTORY_LAUNCHER not in current.output:
            set_home = self.adb.shell(
                serial,
                (
                    "cmd",
                    "package",
                    "set-home-activity",
                    "--user",
                    "0",
                    FACTORY_LAUNCHER,
                ),
                timeout=20,
                log=log,
            )
            if not set_home.ok:
                raise InstallerError(
                    "home_restore_failed",
                    "Не удалось назначить заводскую оболочку основной.",
                    set_home.output,
                    ("Нажмите системную Home на eMotion и выберите заводскую оболочку SELVAS.",),
                )

        self.adb.shell(
            serial, ("am", "force-stop", FACTORY_LAUNCHER_PACKAGE), timeout=15, log=log
        )
        started = self.adb.shell(
            serial,
            (
                "am",
                "start",
                "-W",
                "-a",
                "android.intent.action.MAIN",
                "-c",
                "android.intent.category.HOME",
            ),
            timeout=45,
            log=log,
        )
        if not started.ok:
            warnings.append("Команда запуска HOME не завершилась, но назначение оболочки сохранено.")
        verified = self.adb.shell(
            serial,
            (
                "cmd",
                "package",
                "resolve-activity",
                "--brief",
                "-a",
                "android.intent.action.MAIN",
                "-c",
                "android.intent.category.HOME",
            ),
            timeout=20,
            log=log,
        )
        if not verified.ok or FACTORY_LAUNCHER not in verified.output:
            raise InstallerError(
                "home_verify_failed",
                "Заводская оболочка не стала основной после операции.",
                verified.output,
            )

    def _uninstall_if_present(
        self, serial: str, package: str, display_name: str, log: LogCallback
    ) -> None:
        if not self.adb.package_exists(serial, package):
            self._event(log, "info", f"Пакет {package} уже отсутствует.", None)
            return
        result = self.adb.run(
            ("-s", serial, "uninstall", package), timeout=90, log=log
        )
        if not result.ok or "Success" not in result.output:
            raise InstallerError(
                "uninstall_failed",
                f"Не удалось удалить {display_name}.",
                result.output,
                (
                    "Убедитесь, что USB-соединение не прервалось.",
                    "Перезапустите eMotion и повторите удаление.",
                ),
            )

    @staticmethod
    def _event(
        log: LogCallback, level: str, message: str, progress: Optional[int]
    ) -> None:
        log(level, message, progress)

    @staticmethod
    def _require_compatible(info: DeviceInfo) -> None:
        if info.state != "device" or not info.compatible:
            raise InstallerError(
                "incompatible_device",
                "Операция остановлена: выбранное устройство не прошло проверку Braille eMotion.",
                info.compatibility_message,
                ("Выберите в списке распознанный Braille eMotion со статусом «совместимо».",),
            )

    @staticmethod
    def _state_message(state: str) -> str:
        if state == "unauthorized":
            return (
                "USB-отладка не разрешена. Подтвердите подключённый компьютер на eMotion, "
                "затем обновите список."
            )
        if state == "offline":
            return "ADB видит устройство, но оно не отвечает. Переподключите USB."
        if state == "no permissions":
            return "Windows не предоставила доступ к устройству. Проверьте ADB-драйвер."
        return f"ADB сообщил состояние: {state}."

    @staticmethod
    def _scan_message(records: list[DeviceRecord], infos: list[DeviceInfo]) -> str:
        if not records:
            return (
                "Braille eMotion не найден. Подключите включённое устройство исправным "
                "USB-кабелем, включите USB-отладку и проверьте ADB-драйвер Windows."
            )
        compatible = [info for info in infos if info.compatible]
        if compatible:
            if len(compatible) == 1:
                return "Braille eMotion найден и готов к работе."
            return "Найдено несколько совместимых устройств. Выберите нужный серийный номер."
        if any(record.state == "unauthorized" for record in records):
            return "Устройство найдено, но этому компьютеру не разрешена USB-отладка."
        if any(record.state == "offline" for record in records):
            return "Устройство найдено, но ADB сообщает состояние offline."
        return "Подключённые устройства не прошли проверку Braille eMotion."
