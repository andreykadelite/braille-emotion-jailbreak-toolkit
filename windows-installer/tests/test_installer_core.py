from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from adb_client import parse_adb_devices
from installer_core import (
    BRIDGE_PACKAGE,
    FACTORY_LAUNCHER,
    FACTORY_LAUNCHER_PACKAGE,
    LEGACY_MANAGER_PACKAGE,
    MANAGER_PACKAGE,
    MANAGER_VERSION,
    MANAGER_VERSION_CODE,
    RESOURCE_HASHES,
    AdbClient,
    CommandResult,
    DeviceRecord,
    InstallerEngine,
    InstallerError,
    prepare_runtime_payload,
    verify_payload,
)

UNRELATED_PACKAGE = "org.example.reader"


def ok(*args: str, output: str = "") -> CommandResult:
    return CommandResult(tuple(args), 0, output)


def failed(*args: str, output: str = "Failure") -> CommandResult:
    return CommandResult(tuple(args), 1, output)


class FakeAdb:
    def __init__(self) -> None:
        self.records = [
            DeviceRecord(
                "TEST SERIAL",
                "device",
                "product:B340 model:B340 device:Braille_eMotion_40",
            )
        ]
        self.props = {
            "ro.product.model": "B340",
            "ro.product.device": "Braille_eMotion_40",
            "ro.product.manufacturer": "SELVAS",
            "ro.product.brand": "SELVAS",
            "ro.build.version.release": "12",
            "ro.build.version.sdk": "32",
        }
        self.packages = {
            FACTORY_LAUNCHER_PACKAGE: ("1", 1),
            UNRELATED_PACKAGE: ("2.0", 20),
        }
        self.commands: list[tuple[str, ...]] = []
        self.fail_install_name = ""
        self.fail_uninstall_package = ""
        self.fail_permissions = False
        self.home = FACTORY_LAUNCHER

    def list_devices(self, log=None):
        if log:
            log("command", "ADB: devices -l", None)
        return list(self.records)

    def package_exists(self, serial: str, package: str) -> bool:
        return package in self.packages

    def run(self, args, *, timeout=30.0, log=None, **_kwargs):
        args = tuple(map(str, args))
        self.commands.append(args)
        if log:
            log("command", "ADB: " + " ".join(args), None)
        if "install" in args:
            apk_name = Path(args[-1]).name
            if apk_name == self.fail_install_name:
                return failed(*args, output="Failure [INSTALL_FAILED_INVALID_APK]")
            if apk_name == "app-manager.apk":
                self.packages[MANAGER_PACKAGE] = (MANAGER_VERSION, MANAGER_VERSION_CODE)
            elif apk_name == "appmanager-shortcut.apk":
                self.packages[BRIDGE_PACKAGE] = ("1.0", 1)
            return ok(*args, output="Success")
        if "uninstall" in args:
            package = args[-1]
            if package == self.fail_uninstall_package:
                return failed(*args, output="Failure [DELETE_FAILED_INTERNAL_ERROR]")
            self.packages.pop(package, None)
            return ok(*args, output="Success")
        return ok(*args)

    def shell(self, serial, args, *, timeout=30.0, log=None, **_kwargs):
        args = tuple(map(str, args))
        self.commands.append(("shell", *args))
        if args[:1] == ("getprop",):
            return ok(*args, output=self.props.get(args[1], ""))
        if args[:2] == ("pm", "path"):
            package = args[2]
            if package in self.packages:
                return ok(*args, output=f"package:/data/app/{package}/base.apk")
            return failed(*args, output="")
        if args[:2] == ("dumpsys", "package"):
            version, code = self.packages.get(args[2], ("", 0))
            return ok(*args, output=f"versionCode={code}\nversionName={version}")
        if args[:3] == ("cmd", "package", "resolve-activity"):
            if "android.intent.category.HOME" in args:
                return ok(*args, output=self.home)
            package = args[-1]
            if package in self.packages:
                return ok(*args, output=f"{package}/.MainActivity")
            return failed(*args)
        if args[:3] == ("cmd", "package", "set-home-activity"):
            self.home = FACTORY_LAUNCHER
            return ok(*args, output="Success")
        if args[:2] == ("appops", "set") or args[:2] == ("pm", "grant"):
            if self.fail_permissions:
                return failed(*args, output="SecurityException")
            return ok(*args)
        if args[:2] == ("appops", "get"):
            operation = args[-1]
            if self.fail_permissions:
                return ok(*args, output=f"{operation}: default")
            return ok(*args, output=f"{operation}: allow")
        if args[:1] == ("sha256sum",):
            return ok(*args, output=f"{RESOURCE_HASHES['app-manager.apk'].lower()}  {args[1]}")
        if args[:2] in (("am", "force-stop"), ("am", "start")):
            return ok(*args, output="Complete")
        return ok(*args)


def make_payload(base: Path) -> dict[str, Path]:
    names = (
        "adb.exe",
        "AdbWinApi.dll",
        "AdbWinUsbApi.dll",
        "app-manager.apk",
        "appmanager-shortcut.apk",
    )
    payload = {}
    for name in names:
        path = base / name
        path.write_bytes(name.encode("ascii"))
        payload[name] = path
    return payload


class DeviceParsingTests(unittest.TestCase):
    def test_parse_devices_handles_all_states_and_spaces(self) -> None:
        output = """List of devices attached
SERIAL-1 device product:B340 model:B340 device:Braille_eMotion_40
SERIAL-2 unauthorized usb:1-2
SERIAL-3 offline transport_id:4
"""
        records = parse_adb_devices(output)
        self.assertEqual([record.state for record in records], ["device", "unauthorized", "offline"])
        self.assertEqual(records[0].serial, "SERIAL-1")

    def test_scan_reports_unauthorized_without_querying_properties(self) -> None:
        fake = FakeAdb()
        fake.records = [DeviceRecord("LOCKED", "unauthorized")]
        engine = InstallerEngine(fake, {})
        report = engine.scan()
        self.assertEqual(report.devices[0].state, "unauthorized")
        self.assertFalse(report.devices[0].compatible)
        self.assertIn("не разрешена", report.message)

    def test_scan_rejects_unrelated_android_phone(self) -> None:
        fake = FakeAdb()
        fake.props.update(
            {
                "ro.product.model": "Pixel 8",
                "ro.product.device": "husky",
                "ro.product.manufacturer": "Google",
                "ro.product.brand": "google",
            }
        )
        fake.packages.pop(FACTORY_LAUNCHER_PACKAGE)
        engine = InstallerEngine(fake, {})
        report = engine.scan()
        self.assertFalse(report.devices[0].compatible)
        self.assertIn("не похоже", report.devices[0].compatibility_message)

    def test_scan_rejects_android_below_api_26(self) -> None:
        fake = FakeAdb()
        fake.props["ro.build.version.sdk"] = "25"
        engine = InstallerEngine(fake, {})
        info = engine.scan().devices[0]
        self.assertFalse(info.compatible)
        self.assertIn("слишком старый", info.compatibility_message)


class PayloadTests(unittest.TestCase):
    def test_verify_payload_supports_unicode_and_spaces(self) -> None:
        with tempfile.TemporaryDirectory(prefix="Проверка установщика ") as folder:
            base = Path(folder)
            content = b"portable payload"
            (base / "only.bin").write_bytes(content)
            expected = hashlib.sha256(content).hexdigest().upper()
            with patch.dict(RESOURCE_HASHES, {"only.bin": expected}, clear=True):
                verified = verify_payload(base)
            self.assertEqual(verified["only.bin"], base / "only.bin")

    def test_verify_payload_blocks_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            (base / "only.bin").write_bytes(b"changed")
            with patch.dict(RESOURCE_HASHES, {"only.bin": "0" * 64}, clear=True):
                with self.assertRaises(InstallerError) as caught:
                    verify_payload(base)
            self.assertEqual(caught.exception.code, "payload_corrupt")

    def test_runtime_adb_uses_stable_verified_cache_and_repairs_tampering(self) -> None:
        with tempfile.TemporaryDirectory(prefix="Встроенный ADB ") as source_folder, tempfile.TemporaryDirectory(
            prefix="Кэш ADB "
        ) as cache_folder:
            source = Path(source_folder)
            payload = {}
            hashes = {}
            for name in ("adb.exe", "AdbWinApi.dll", "AdbWinUsbApi.dll"):
                path = source / name
                content = f"verified-{name}".encode("ascii")
                path.write_bytes(content)
                payload[name] = path
                hashes[name] = hashlib.sha256(content).hexdigest().upper()
            with patch.dict(RESOURCE_HASHES, hashes, clear=True):
                prepared = prepare_runtime_payload(payload, Path(cache_folder))
                first_adb_path = prepared["adb.exe"]
                self.assertNotEqual(first_adb_path.parent, source)
                first_adb_path.write_bytes(b"tampered")
                repaired = prepare_runtime_payload(payload, Path(cache_folder))
            self.assertEqual(repaired["adb.exe"], first_adb_path)
            self.assertEqual(first_adb_path.read_bytes(), b"verified-adb.exe")


class OperationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="Payload with spaces ")
        self.payload = make_payload(Path(self.temp.name))
        self.fake = FakeAdb()
        self.engine = InstallerEngine(self.fake, self.payload)
        self.events = []

    def tearDown(self) -> None:
        self.temp.cleanup()

    def log(self, level, message, progress) -> None:
        self.events.append((level, message, progress))

    def test_successful_install_is_verified_and_preserves_other_apps(self) -> None:
        report = self.engine.install("TEST SERIAL", self.log)
        self.assertTrue(report.success)
        self.assertIn(MANAGER_PACKAGE, self.fake.packages)
        self.assertIn(BRIDGE_PACKAGE, self.fake.packages)
        self.assertIn(UNRELATED_PACKAGE, self.fake.packages)
        self.assertEqual(self.fake.home, FACTORY_LAUNCHER)
        self.assertEqual(self.events[-1][2], 100)

    def test_bridge_failure_rolls_back_new_manager_and_keeps_other_apps(self) -> None:
        self.fake.fail_install_name = "appmanager-shortcut.apk"
        with self.assertRaises(InstallerError):
            self.engine.install("TEST SERIAL", self.log)
        self.assertNotIn(MANAGER_PACKAGE, self.fake.packages)
        self.assertIn(UNRELATED_PACKAGE, self.fake.packages)

    def test_permission_failure_becomes_warning_not_broken_install(self) -> None:
        self.fake.fail_permissions = True
        report = self.engine.install("TEST SERIAL", self.log)
        self.assertTrue(report.success)
        self.assertEqual(len(report.warnings), 1)
        self.assertIn("разрешить", report.warnings[0])

    def test_uninstall_removes_only_manager_components(self) -> None:
        self.fake.packages[MANAGER_PACKAGE] = (MANAGER_VERSION, MANAGER_VERSION_CODE)
        self.fake.packages[BRIDGE_PACKAGE] = ("1", 1)
        self.fake.packages[LEGACY_MANAGER_PACKAGE] = ("1.2", 3)
        report = self.engine.uninstall("TEST SERIAL", self.log)
        self.assertTrue(report.success)
        self.assertNotIn(MANAGER_PACKAGE, self.fake.packages)
        self.assertNotIn(BRIDGE_PACKAGE, self.fake.packages)
        self.assertNotIn(LEGACY_MANAGER_PACKAGE, self.fake.packages)
        self.assertIn(UNRELATED_PACKAGE, self.fake.packages)

    def test_failed_manager_uninstall_restores_bridge(self) -> None:
        self.fake.packages[MANAGER_PACKAGE] = (MANAGER_VERSION, MANAGER_VERSION_CODE)
        self.fake.packages[BRIDGE_PACKAGE] = ("1", 1)
        self.fake.fail_uninstall_package = MANAGER_PACKAGE
        with self.assertRaises(InstallerError):
            self.engine.uninstall("TEST SERIAL", self.log)
        self.assertIn(MANAGER_PACKAGE, self.fake.packages)
        self.assertIn(BRIDGE_PACKAGE, self.fake.packages)

    def test_uninstall_never_removes_unrelated_application(self) -> None:
        self.engine.uninstall("TEST SERIAL", self.log)
        uninstall_commands = [cmd for cmd in self.fake.commands if "uninstall" in cmd]
        self.assertTrue(all(cmd[-1] != UNRELATED_PACKAGE for cmd in uninstall_commands))
        self.assertIn(UNRELATED_PACKAGE, self.fake.packages)


class AdbCommandTests(unittest.TestCase):
    def test_missing_adb_has_actionable_error(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            client = AdbClient({"adb.exe": Path(folder) / "missing-adb.exe"})
            with self.assertRaises(InstallerError) as caught:
                client.run(("devices",))
        self.assertEqual(caught.exception.code, "adb_start_failed")
        self.assertTrue(caught.exception.remedies)

    def test_client_stops_only_the_server_it_started(self) -> None:
        client = AdbClient({"adb.exe": Path("adb.exe")})
        calls = []

        def fake_run(args, **_kwargs):
            calls.append(tuple(args))
            return ok(*args, output="Success")

        with patch.object(client, "_is_server_listening", return_value=False), patch.object(
            client, "run", side_effect=fake_run
        ):
            client.start_server()
            client.shutdown_owned_server()
        self.assertEqual(calls, [("start-server",), ("kill-server",)])

    def test_client_preserves_preexisting_adb_server(self) -> None:
        client = AdbClient({"adb.exe": Path("adb.exe")})
        calls = []

        def fake_run(args, **_kwargs):
            calls.append(tuple(args))
            return ok(*args, output="Success")

        with patch.object(client, "_is_server_listening", return_value=True), patch.object(
            client, "run", side_effect=fake_run
        ):
            client.start_server()
            client.shutdown_owned_server()
        self.assertEqual(calls, [("start-server",)])

    def test_client_disables_automatic_network_device_discovery(self) -> None:
        client = AdbClient({"adb.exe": Path("adb.exe")})
        self.assertEqual(client.environment["ADB_MDNS_AUTO_CONNECT"], "")


if __name__ == "__main__":
    unittest.main()
