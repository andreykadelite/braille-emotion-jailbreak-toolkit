from __future__ import annotations

import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional

from PyQt5.QtCore import QLockFile, QStandardPaths, Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtGui import QCloseEvent
from PyQt5.QtWidgets import (
    QApplication,
    QFileDialog,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QWidget,
)

from help_content import HELP_TOPICS
from installer_core import (
    APP_VERSION,
    AdbClient,
    DeviceInfo,
    InstallerEngine,
    InstallerError,
    OperationReport,
    ScanReport,
    prepare_runtime_payload,
    verify_payload,
)
from installer_view import InstallerViewMixin
from ui_theme import apply_application_theme, repolish


WINDOW_TITLE = "Установщик Диспетчера приложений для Braille eMotion"


from ui_theme import apply_application_theme, repolish


WINDOW_TITLE = "Установщик Диспетчера приложений для Braille eMotion"


class ScanThread(QThread):
    completed = pyqtSignal(object)
    failed = pyqtSignal(object)
    log_event = pyqtSignal(str, str, object)

    def __init__(self, engine: InstallerEngine) -> None:
        super().__init__()
        self.engine = engine

    def run(self) -> None:
        try:
            report = self.engine.scan(self._log)
            self.completed.emit(report)
        except Exception as exc:  # QThread must deliver failures to the GUI.
            self.failed.emit(normalize_exception(exc))

    def _log(self, level: str, message: str, progress: Optional[int]) -> None:
        self.log_event.emit(level, message, progress)


class OperationThread(QThread):
    completed = pyqtSignal(object)
    failed = pyqtSignal(object)
    log_event = pyqtSignal(str, str, object)

    def __init__(
        self,
        engine: InstallerEngine,
        operation: str,
        serial: str,
    ) -> None:
        super().__init__()
        self.engine = engine
        self.operation = operation
        self.serial = serial

    def run(self) -> None:
        try:
            if self.operation == "install":
                report = self.engine.install(self.serial, self._log)
            elif self.operation == "uninstall":
                report = self.engine.uninstall(self.serial, self._log)
            else:
                raise RuntimeError(f"Unknown operation: {self.operation}")
            self.completed.emit(report)
        except Exception as exc:  # QThread must deliver failures to the GUI.
            self.failed.emit(normalize_exception(exc))

    def _log(self, level: str, message: str, progress: Optional[int]) -> None:
        self.log_event.emit(level, message, progress)


def normalize_exception(exc: Exception) -> InstallerError:
    if isinstance(exc, InstallerError):
        return exc
    return InstallerError(
        "unexpected_error",

        "Произошла непредвиденная ошибка установщика.",
        "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
        ("Сохраните журнал и приложите его при обращении за помощью.",),
    )


class InstallerWindow(InstallerViewMixin, QMainWindow):
    def __init__(self, engine: InstallerEngine, *, auto_start: bool = True) -> None:
        super().__init__()
        self.engine = engine
        self.device_infos: dict[str, DeviceInfo] = {}
        self.scan_thread: Optional[ScanThread] = None
        self.operation_thread: Optional[OperationThread] = None
        self.pending_close = False
        self.last_status_key = ("", "")
        self._compact_layout: Optional[bool] = None
        self._scan_return_target: Optional[QWidget] = None
        self._section_return_target: Optional[QWidget] = None
        self._initial_focus_pending = True

        self.setWindowTitle(f"{WINDOW_TITLE} {APP_VERSION}")
        self.setAccessibleName(WINDOW_TITLE)
        self.resize(1060, 820)
        self.setMinimumSize(560, 520)

        self._build_ui()
        self._build_shortcuts()
        self._populate_help()
        self._set_status(
            "Подготовка завершена. Выполняется автоматический поиск Braille eMotion.",
            log=False,
        )

        self.auto_scan_timer = QTimer(self)
        self.auto_scan_timer.setInterval(4000)
        self.auto_scan_timer.timeout.connect(self.start_scan)
        if auto_start:
            QTimer.singleShot(0, self.status_label.setFocus)
            self.auto_scan_timer.start()
            QTimer.singleShot(100, self.start_scan)

    def _populate_help(self) -> None:
        for index, topic in enumerate(HELP_TOPICS, 1):
            item = QListWidgetItem(f"{index}. {topic.title}")
            item.setData(Qt.UserRole, index - 1)
            item.setToolTip(topic.title)
            self.help_topics.addItem(item)
        self.help_topics.setCurrentRow(0)

    def _help_topic_changed(self, row: int) -> None:
        self.help_paragraphs.clear()
        if row < 0 or row >= len(HELP_TOPICS):
            return
        topic = HELP_TOPICS[row]
        total = len(topic.paragraphs)
        self.paragraph_label.setText(f"{topic.title}. Абзацев: {total}:")
        self.help_paragraphs.setAccessibleName(f"{topic.title}. Абзацы справки")
        for index, paragraph in enumerate(topic.paragraphs, 1):
            item = QListWidgetItem(f"Абзац {index} из {total}. {paragraph}")
            item.setData(Qt.AccessibleTextRole, f"Абзац {index} из {total}. {paragraph}")
            self.help_paragraphs.addItem(item)
        if total:
            self.help_paragraphs.setCurrentRow(0)

    def request_scan(self) -> None:
        if self.operation_thread and self.operation_thread.isRunning():
            self._set_status("Дождитесь завершения текущей операции.", level="warning")
            self.status_label.setFocus(Qt.ShortcutFocusReason)
            return
        if self.scan_thread and self.scan_thread.isRunning():
            self._set_status("Поиск устройства уже выполняется.")
            self.status_label.setFocus(Qt.ShortcutFocusReason)
            return
        self._scan_return_target = self.refresh_button
        self.status_label.setFocus(Qt.ShortcutFocusReason)
        self.start_scan(manual=True)

    def start_scan(self, manual: bool = False) -> None:
        if self.operation_thread and self.operation_thread.isRunning():
            return
        if self.scan_thread and self.scan_thread.isRunning():
            return
        if not manual and QApplication.focusWidget() is self.refresh_button:
            return
        if manual:
            self.refresh_button.setEnabled(False)
        if manual or not self.device_infos:
            self._set_status("Поиск подключённых устройств…")
            self.progress.setFormat("Поиск устройства — %p%")
            self.progress.setValue(5)
        thread = ScanThread(self.engine)
        thread.log_event.connect(self._handle_event)
        thread.completed.connect(self._scan_completed)
        thread.failed.connect(self._scan_failed)
        thread.finished.connect(self._thread_finished)
        self.scan_thread = thread
        thread.start()

    def _scan_completed(self, report: ScanReport) -> None:
        selected_serial = self.current_serial()
        self.device_infos = {info.serial: info for info in report.devices}
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        for info in report.devices:
            self.device_combo.addItem(info.display_name, info.serial)
        self.device_combo.blockSignals(False)

        if selected_serial:
            for index in range(self.device_combo.count()):
                if self.device_combo.itemData(index) == selected_serial:
                    self.device_combo.setCurrentIndex(index)
                    break
        if self.device_combo.count() == 0:
            self.device_details.setPlainText("Совместимый Braille eMotion не найден.")
            self._set_app_status(
                "Состояние не определено: Braille eMotion не найден.", "missing"
            )
        self._selected_device_changed(self.device_combo.currentIndex())
        compatible = any(info.compatible for info in report.devices)
        self._set_status(report.message, level="success" if compatible else "warning")
        self.progress.setValue(0)
        self.progress.setFormat("Ожидание — %p%")
        if self._initial_focus_pending:
            self._initial_focus_pending = False
            if QApplication.focusWidget() in (None, self.status_label):
                QTimer.singleShot(0, self.app_status_label.setFocus)

    def _scan_failed(self, error: InstallerError) -> None:
        self.device_infos.clear()
        self.device_combo.clear()
        self.device_details.setPlainText(error.full_text())
        self._set_app_status("Состояние не определено из-за ошибки подключения.", "partial")
        self._set_status(error.message, level="error")
        self.progress.setValue(0)
        self.progress.setFormat("Ошибка — %p%")
        self._append_log("error", error.full_text())

    def _thread_finished(self) -> None:
        self.refresh_button.setEnabled(True)
        self._update_action_state()
        return_target = self._scan_return_target
        self._scan_return_target = None
        if return_target and QApplication.focusWidget() in (None, self.status_label):
            QTimer.singleShot(0, return_target.setFocus)
        if self.pending_close and not self._anything_running():
            self.close()

    def _selected_device_changed(self, _index: int) -> None:
        info = self.current_device_info()
        if not info:
            self.device_details.setPlainText("Устройство не выбрано.")
            self._set_app_status(
                "Состояние не определено: устройство не выбрано.", "missing"
            )
            self._update_action_state()
            return
        details = (
            f"Серийный номер: {info.serial}\n"
            f"Модель: {info.model or 'не определена'}\n"
            f"Устройство: {info.device or 'не определено'}\n"
            f"Производитель: {info.manufacturer or 'не определён'}\n"
            f"Android: {info.android_version or '?'}; API {info.api_level or '?'}\n"
            f"Проверка: {info.compatibility_message}"
        )
        self.device_details.setPlainText(details)
        app_state = (
            "installed"
            if info.manager_installed and info.bridge_installed
            else "partial"
            if info.has_manager_components
            else "missing"
        )
        self._set_app_status(info.installation_status, app_state)
        self._update_action_state()

    def _set_app_status(self, message: str, state: str) -> None:
        self.app_status_label.setPlainText(message)
        self.app_status_label.setAccessibleName(
            f"Статус установленного Диспетчера приложений. {message}"
        )
        self.app_status_label.setAccessibleDescription(message)
        if self.app_status_label.property("appState") != state:
            self.app_status_label.setProperty("appState", state)
            repolish(self.app_status_label)

    def _update_action_state(self) -> None:
        info = self.current_device_info()
        ready = bool(info and info.compatible and info.state == "device")
        busy = self._anything_running()
        self.install_button.setEnabled(ready and not busy)
        self.uninstall_button.setEnabled(
            ready and bool(info and info.has_manager_components) and not busy
        )
        self.close_button.setEnabled(not busy)
        if info and info.manager_installed and info.bridge_installed:
            self.install_button.setAccessibleName("Переустановить Диспетчер приложений")
        elif info and info.has_manager_components:
            self.install_button.setAccessibleName("Восстановить Диспетчер приложений")
        else:
            self.install_button.setAccessibleName("Установить Диспетчер приложений")
        self._refresh_responsive_labels()

    def current_serial(self) -> str:
        data = self.device_combo.currentData()
        return str(data) if data else ""

    def current_device_info(self) -> Optional[DeviceInfo]:
        return self.device_infos.get(self.current_serial())

    def _ask_confirmation(
        self,
        *,
        title: str,
        question: str,
        details: str,
        confirm_text: str,
        trigger: QWidget,
        danger: bool = False,
    ) -> bool:
        message = QMessageBox(self)
        message.setAccessibleName(title)
        message.setIcon(QMessageBox.Warning)
        message.setWindowTitle(title)
        message.setText(question)
        message.setInformativeText(details)
        message.setStandardButtons(QMessageBox.Cancel | QMessageBox.Yes)
        confirm_button = message.button(QMessageBox.Yes)
        cancel_button = message.button(QMessageBox.Cancel)
        confirm_button.setText(confirm_text)
        confirm_button.setAccessibleName(confirm_text)
        confirm_button.setAccessibleDescription(
            "Подтверждает изменение подключённого Braille eMotion."
        )
        cancel_button.setText("Отмена")
        cancel_button.setAccessibleName("Отмена. Безопасное действие")
        cancel_button.setAccessibleDescription(
            "Закрывает окно без изменения подключённого устройства."
        )
        confirm_button.setProperty("dangerAction" if danger else "primaryAction", True)
        repolish(confirm_button)
        message.setDefaultButton(QMessageBox.Cancel)
        message.setEscapeButton(QMessageBox.Cancel)
        QTimer.singleShot(0, lambda: cancel_button.setFocus(Qt.OtherFocusReason))
        accepted = message.exec_() == QMessageBox.Yes
        if not accepted and trigger.isEnabled() and trigger.isVisible():
            QTimer.singleShot(0, trigger.setFocus)
        return accepted

    def confirm_install(self) -> None:
        info = self.current_device_info()
        if not info or not info.compatible:
            self._show_error(
                InstallerError("no_device", "Сначала выберите готовый Braille eMotion.")
            )
            return
        if self._ask_confirmation(
            title="Подтверждение установки",
            question="Установить Диспетчер приложений 1.5?",
            details=(
                "Программная конфигурация Braille eMotion изменится. Вы действуете на свой страх и риск; "
                "если неисправность свяжут с изменениями, возможен отказ в бесплатном гарантийном ремонте.\n\n"
                "Не отключайте USB и питание до завершения. Другие приложения не изменяются."
            ),
            confirm_text="Установить",
            trigger=self.install_button,
        ):
            self._start_operation("install", info.serial)

    def confirm_uninstall(self) -> None:
        info = self.current_device_info()
        if not info or not info.compatible:
            self._show_error(
                InstallerError("no_device", "Сначала выберите готовый Braille eMotion.")
            )
            return
        if self._ask_confirmation(
            title="Подтверждение удаления",
            question="Удалить Диспетчер приложений?",
            details=(
                "Будут удалены только Диспетчер приложений, его пункт заводского меню и, если она "
                "осталась, старая версия диспетчера. Локальные данные диспетчера будут стёрты. "
                "Стандартные и другие пользовательские приложения не изменяются.\n\n"
                "Не отключайте USB и питание до завершения."
            ),
            confirm_text="Удалить",
            trigger=self.uninstall_button,
            danger=True,
        ):
            self._start_operation("uninstall", info.serial)

    def _start_operation(self, operation: str, serial: str) -> None:
        if self._anything_running():
            return
        self.auto_scan_timer.stop()
        self.status_label.setFocus(Qt.OtherFocusReason)
        self.progress.setValue(0)
        label = "Установка" if operation == "install" else "Удаление"
        self.progress.setFormat(f"{label} — %p%")
        self._set_status(f"{label} начато. Не отключайте устройство.")
        self._append_log("info", "=" * 64)
        self._append_log("info", f"{label}. Устройство: {serial}")
        thread = OperationThread(self.engine, operation, serial)
        thread.log_event.connect(self._handle_event)
        thread.completed.connect(self._operation_completed)
        thread.failed.connect(self._operation_failed)
        thread.finished.connect(self._operation_thread_finished)
        self.operation_thread = thread
        self._update_action_state()
        self.refresh_button.setEnabled(False)
        thread.start()

    def _operation_completed(self, report: OperationReport) -> None:
        self.progress.setValue(100)
        self.progress.setFormat("Завершено — %p%")
        self._set_status(report.message)
        self._append_log("success", report.message)
        if report.warnings:
            warning_text = "\n".join(f"• {item}" for item in report.warnings)
            self._append_log("warning", warning_text)
            self._show_result_dialog(
                "Операция завершена с предупреждениями",
                report.message + "\n\n" + warning_text,
                warning=True,
            )
        else:
            self._show_result_dialog("Готово", report.message)
        QTimer.singleShot(0, self.app_status_label.setFocus)

    def _operation_failed(self, error: InstallerError) -> None:
        self.progress.setFormat("Ошибка — %p%")
        self._set_status(error.message, level="error")
        self._append_log("error", error.full_text())
        self._show_error(error)

    def _operation_thread_finished(self) -> None:
        self.operation_thread = None
        self.refresh_button.setEnabled(True)
        self.auto_scan_timer.start()
        self._update_action_state()
        if self.pending_close:
            self.close()
        else:
            QTimer.singleShot(500, self.start_scan)

    def _handle_event(
        self, level: str, message: str, progress: Optional[int]
    ) -> None:
        self._append_log(level, message)
        if progress is not None:
            progress_value = max(0, min(100, int(progress)))
            self.progress.setValue(progress_value)
            self.progress.setAccessibleName(f"Ход операции. Выполнено {progress_value} процентов")
        if level in {"status", "success", "warning", "error"}:
            self._set_status(message, level=level, log=False)

    def _set_status(self, message: str, *, level: str = "status", log: bool = True) -> None:
        status_key = (level, message)
        if status_key != self.last_status_key:
            prefix = {
                "success": "Готово. ",
                "error": "Ошибка. ",
                "warning": "Предупреждение. ",
            }.get(level, "")
            rendered = prefix + message
            self.status_label.setText(rendered)
            self.status_label.setAccessibleName(f"Текущее состояние. {rendered}")
            self.status_label.setAccessibleDescription(rendered)
            badge = {
                "success": "ГОТОВО",
                "warning": "ВНИМАНИЕ",
                "error": "ОШИБКА",
            }.get(level, "СОСТОЯНИЕ")
            self.status_badge.setText(badge)
            self.status_badge.setAccessibleName(f"Тип сообщения. {badge.lower()}")
            style_level = level if level in {"success", "warning", "error"} else "status"
            if self.status_frame.property("statusLevel") != style_level:
                self.status_frame.setProperty("statusLevel", style_level)
                repolish(self.status_frame)
            self.last_status_key = status_key
        if log:
            self._append_log(level, message)

    def _append_log(self, level: str, message: str) -> None:
        if not message:
            return
        labels = {
            "command": "КОМАНДА",
            "output": "ADB",
            "status": "СТАТУС",
            "info": "СВЕДЕНИЯ",
            "success": "ГОТОВО",
            "warning": "ПРЕДУПРЕЖДЕНИЕ",
            "error": "ОШИБКА",
        }
        timestamp = datetime.now().strftime("%H:%M:%S")
        label = labels.get(level, level.upper())
        scrollbar = self.log_view.verticalScrollBar()
        previous_scroll = scrollbar.value()
        follow_tail = previous_scroll >= scrollbar.maximum() - 2
        for line in str(message).splitlines() or [""]:
            self.log_view.appendPlainText(f"[{timestamp}] {label}: {line}")
        if follow_tail:
            scrollbar.setValue(scrollbar.maximum())
        else:
            scrollbar.setValue(min(previous_scroll, scrollbar.maximum()))

    def _remember_section_origin(self) -> None:
        focused = QApplication.focusWidget()
        if focused and (focused is self or self.isAncestorOf(focused)):
            if self.tabs.currentWidget() == self.main_tab:
                self._section_return_target = focused

    def focus_main(self) -> None:
        self.tabs.setCurrentWidget(self.main_tab)
        target = self._section_return_target
        self._section_return_target = None
        if not target or not target.isVisible() or not target.isEnabled():
            target = self.app_status_label
        target.setFocus(Qt.ShortcutFocusReason)

    def focus_help(self) -> None:
        self._remember_section_origin()
        self.tabs.setCurrentWidget(self.help_tab)
        self.help_topics.setFocus(Qt.ShortcutFocusReason)

    def focus_log(self) -> None:
        self._remember_section_origin()
        self.tabs.setCurrentWidget(self.log_tab)
        self.log_view.setFocus(Qt.ShortcutFocusReason)

    def _escape_pressed(self) -> None:
        if self.tabs.currentWidget() != self.main_tab:
            self.focus_main()

    def copy_log(self) -> None:
        QApplication.clipboard().setText(self.log_view.toPlainText())
        self._set_status("Журнал скопирован в буфер обмена.")

    def save_log(self) -> None:
        suggested = f"Braille-eMotion-Installer-{datetime.now():%Y%m%d-%H%M%S}.log"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить журнал",
            str(Path.home() / suggested),
            "Текстовый журнал (*.log *.txt);;Все файлы (*.*)",
        )
        if not path:
            return
        try:
            Path(path).write_text(self.log_view.toPlainText(), encoding="utf-8-sig")
            self._set_status(f"Журнал сохранён: {path}")
        except OSError as exc:
            self._show_error(
                InstallerError(
                    "log_save_failed",
                    "Не удалось сохранить журнал.",
                    str(exc),
                    ("Выберите папку, в которую разрешена запись.",),
                )
            )

    def clear_log(self) -> None:
        self.log_view.clear()
        self._append_log("info", "Журнал очищен пользователем.")

    def _show_error(self, error: InstallerError) -> None:
        return_target = QApplication.focusWidget()
        dialog = QMessageBox(self)
        dialog.setAccessibleName(f"Ошибка. {error.message}")
        dialog.setIcon(QMessageBox.Critical)
        dialog.setWindowTitle("Ошибка")
        dialog.setText(error.message)
        details = []
        if error.remedies:
            details.append("Что сделать:\n" + "\n".join(f"• {item}" for item in error.remedies))
        if error.technical:
            dialog.setDetailedText(error.technical)
        dialog.setInformativeText("\n\n".join(details))
        dialog.setStandardButtons(QMessageBox.Ok)
        ok_button = dialog.button(QMessageBox.Ok)
        ok_button.setText("Закрыть сообщение")
        ok_button.setAccessibleName("Закрыть сообщение об ошибке")
        dialog.setDefaultButton(QMessageBox.Ok)
        dialog.setEscapeButton(QMessageBox.Ok)
        ok_button.setFocus(Qt.OtherFocusReason)
        dialog.exec_()
        if return_target and return_target.isVisible() and return_target.isEnabled():
            QTimer.singleShot(0, return_target.setFocus)
        else:
            QTimer.singleShot(0, self.status_label.setFocus)

    def _show_result_dialog(
        self, title: str, message: str, *, warning: bool = False
    ) -> None:
        dialog = QMessageBox(self)
        dialog.setAccessibleName(f"{title}. {message}")
        dialog.setIcon(QMessageBox.Warning if warning else QMessageBox.Information)
        dialog.setWindowTitle(title)
        dialog.setText(message)
        dialog.setStandardButtons(QMessageBox.Ok)
        ok_button = dialog.button(QMessageBox.Ok)
        ok_button.setText("Продолжить")
        ok_button.setAccessibleName("Продолжить и вернуться в главное окно")
        dialog.setDefaultButton(QMessageBox.Ok)
        dialog.setEscapeButton(QMessageBox.Ok)
        ok_button.setFocus(Qt.OtherFocusReason)
        dialog.exec_()

    def _anything_running(self) -> bool:
        return bool(
            (self.scan_thread and not self.scan_thread.isFinished())
            or (self.operation_thread and not self.operation_thread.isFinished())
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.operation_thread and self.operation_thread.isRunning():
            QMessageBox.warning(
                self,
                "Операция ещё выполняется",
                "Нельзя закрыть установщик во время изменения устройства. Дождитесь завершения.",
            )
            event.ignore()
            return
        if self.scan_thread and self.scan_thread.isRunning():
            self.pending_close = True
            self._set_status("Завершается поиск устройства. Окно закроется после ответа ADB.")
            event.ignore()
            return
        self.auto_scan_timer.stop()
        event.accept()

def run_gui() -> int:
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    app.setApplicationName(WINDOW_TITLE)
    app.setApplicationDisplayName("Braille eMotion")
    app.setOrganizationName("Braille eMotion")
    apply_application_theme(app)

    lock_path = Path(QStandardPaths.writableLocation(QStandardPaths.TempLocation)) / (
        "BrailleEmotionAppManagerInstaller.lock"
    )
    lock = QLockFile(str(lock_path))
    lock.setStaleLockTime(30_000)
    if not lock.tryLock(100):
        QMessageBox.warning(
            None,
            "Установщик уже запущен",
            "Другая копия установщика уже работает. Перейдите к её окну и дождитесь завершения операции.",
        )
        return 2

    try:
        payload = prepare_runtime_payload(verify_payload())
    except InstallerError as error:
        dialog = QMessageBox()
        dialog.setIcon(QMessageBox.Critical)
        dialog.setWindowTitle("Проверка установщика не пройдена")
        dialog.setText(error.message)
        dialog.setInformativeText("\n".join(error.remedies))
        dialog.setDetailedText(error.technical)
        dialog.exec_()
        return 3

    engine = InstallerEngine(AdbClient(payload), payload)
    window = InstallerWindow(engine)
    window.show()
    exit_code = app.exec_()
    engine.adb.shutdown_owned_server()
    lock.unlock()
    return exit_code
