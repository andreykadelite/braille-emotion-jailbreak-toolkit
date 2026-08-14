from __future__ import annotations

import os
import queue
import re
import socket
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Sequence

from installer_errors import InstallerError


LogCallback = Callable[[str, str, Optional[int]], None]


@dataclass(frozen=True)
class CommandResult:
    args: tuple[str, ...]
    return_code: int
    output: str
    timed_out: bool = False
    cancelled: bool = False

    @property
    def ok(self) -> bool:
        return self.return_code == 0 and not self.timed_out and not self.cancelled


@dataclass(frozen=True)
class DeviceRecord:
    serial: str
    state: str
    details: str = ""


class AdbClient:
    def __init__(self, payload: dict[str, Path]) -> None:
        self.payload = payload
        self.adb_path = payload["adb.exe"]
        self.environment = os.environ.copy()
        self.environment["ADB_MDNS_AUTO_CONNECT"] = ""
        self._server_ownership_checked = False
        self._owns_server = False

    def run(
        self,
        args: Sequence[str],
        *,
        timeout: float = 30.0,
        log: Optional[LogCallback] = None,
        cancel_event: Optional[threading.Event] = None,
        log_command: bool = True,
    ) -> CommandResult:
        command = [str(self.adb_path), *map(str, args)]
        if log and log_command:
            log("command", "ADB: " + _display_command(args), None)

        startupinfo = None
        creationflags = 0
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                startupinfo=startupinfo,
                creationflags=creationflags,
                env=self.environment,
            )
        except OSError as exc:
            raise InstallerError(
                "adb_start_failed",
                "Не удалось запустить встроенный ADB.",
                str(exc),
                (
                    "Проверьте, не поместил ли антивирус ADB в карантин.",
                    "Перезапустите EXE из локальной папки с правом чтения и запуска.",
                ),
            ) from exc

        output_queue: queue.Queue[Optional[str]] = queue.Queue()

        def read_output() -> None:
            assert process.stdout is not None
            for line in iter(process.stdout.readline, ""):
                output_queue.put(line)
            output_queue.put(None)

        reader = threading.Thread(target=read_output, daemon=True)
        reader.start()
        output_parts: list[str] = []
        started = time.monotonic()
        reader_finished = False
        timed_out = False
        cancelled = False

        while process.poll() is None or not reader_finished or not output_queue.empty():
            try:
                item = output_queue.get(timeout=0.05)
                if item is None:
                    reader_finished = True
                else:
                    output_parts.append(item)
                    if log:
                        line = item.rstrip("\r\n")
                        if line:
                            log("output", line, None)
            except queue.Empty:
                pass

            if process.poll() is None and cancel_event and cancel_event.is_set():
                cancelled = True
                process.kill()
            if process.poll() is None and time.monotonic() - started > timeout:
                timed_out = True
                process.kill()

        try:
            return_code = process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            return_code = process.wait(timeout=2)

        output = "".join(output_parts).strip()
        if timed_out:
            output = (output + f"\nПревышено время ожидания: {timeout:.0f} с").strip()
        if cancelled:
            output = (output + "\nОперация отменена.").strip()
        return CommandResult(tuple(map(str, args)), return_code, output, timed_out, cancelled)

    def require(
        self,
        args: Sequence[str],
        *,
        timeout: float = 30.0,
        log: Optional[LogCallback] = None,
        message: str,
    ) -> CommandResult:
        result = self.run(args, timeout=timeout, log=log)
        if not result.ok:
            raise command_error(message, result)
        return result

    def start_server(self, log: Optional[LogCallback] = None) -> None:
        server_was_running = True
        if not self._server_ownership_checked:
            server_was_running = self._is_server_listening()
            self._server_ownership_checked = True
        result = self.run(("start-server",), timeout=20, log=log)
        if not result.ok:
            raise command_error(
                "Не удалось запустить службу ADB.",
                result,
                code="adb_server_failed",
            )
        if not server_was_running:
            self._owns_server = True

    def shutdown_owned_server(self, log: Optional[LogCallback] = None) -> None:
        if not self._owns_server:
            return
        try:
            self.run(("kill-server",), timeout=15, log=log)
        finally:
            self._owns_server = False

    @staticmethod
    def _is_server_listening() -> bool:
        try:
            with socket.create_connection(("127.0.0.1", 5037), timeout=0.25):
                return True
        except OSError:
            return False

    def list_devices(self, log: Optional[LogCallback] = None) -> list[DeviceRecord]:
        self.start_server(log)
        result = self.run(("devices", "-l"), timeout=15, log=log)
        if not result.ok:
            raise command_error("Не удалось получить список USB-устройств.", result)
        return parse_adb_devices(result.output)

    def shell(
        self,
        serial: str,
        args: Sequence[str],
        *,
        timeout: float = 30.0,
        log: Optional[LogCallback] = None,
        log_command: bool = True,
    ) -> CommandResult:
        return self.run(
            ("-s", serial, "shell", *args),
            timeout=timeout,
            log=log,
            log_command=log_command,
        )

    def package_exists(self, serial: str, package: str) -> bool:
        result = self.shell(serial, ("pm", "path", package), timeout=12, log_command=False)
        return result.ok and "package:" in result.output


def _display_command(args: Sequence[str]) -> str:
    parts = []
    for item in map(str, args):
        if re.search(r"\s", item):
            parts.append(f'"{item}"')
        else:
            parts.append(item)
    return " ".join(parts)


def parse_adb_devices(output: str) -> list[DeviceRecord]:
    records: list[DeviceRecord] = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("List of devices attached") or line.startswith("*"):
            continue
        parts = line.split(None, 2)
        if len(parts) < 2:
            continue
        serial, state = parts[0], parts[1]
        details = parts[2] if len(parts) > 2 else ""
        records.append(DeviceRecord(serial, state, details))
    return records


def command_error(
    message: str,
    result: CommandResult,
    *,
    code: str = "adb_command_failed",
) -> InstallerError:
    output = result.output or f"Код возврата: {result.return_code}"
    lower = output.lower()
    if result.timed_out:
        return InstallerError(
            "adb_timeout",
            message + " Устройство не ответило вовремя.",
            output,
            (
                "Подождите завершения запуска eMotion и повторите операцию.",
                "Переподключите исправный USB-кабель напрямую к компьютеру.",
            ),
        )
    if "unauthorized" in lower:
        return InstallerError(
            "device_unauthorized",
            "Компьютеру не разрешена USB-отладка на Braille eMotion.",
            output,
            (
                "Разрешите USB-отладку на устройстве и, если доступно, подтвердите этот компьютер.",
                "После подтверждения нажмите «Обновить список устройств».",
            ),
        )
    if "offline" in lower or "device not found" in lower or "no devices" in lower:
        return InstallerError(
            "device_disconnected",
            "Связь с Braille eMotion потеряна.",
            output,
            (
                "Не выключайте устройство и переподключите USB-кабель.",
                "Дождитесь состояния «готово», затем повторите операцию.",
            ),
        )
    return InstallerError(code, message, output)
