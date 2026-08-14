from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication, QMessageBox

from help_content import HELP_TOPICS
from installer_core import DeviceInfo, InstallerEngine
from installer_gui import InstallerWindow
from ui_theme import COLORS, contrast_ratio, high_contrast_enabled


class IdleFakeAdb:
    def list_devices(self, log=None):
        return []


class AccessibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.window = InstallerWindow(
            InstallerEngine(IdleFakeAdb(), {}), auto_start=False
        )
        self.window.auto_scan_timer.stop()

    def tearDown(self) -> None:
        self.window.close()
        self.app.processEvents()

    def test_all_primary_controls_have_accessible_names(self) -> None:
        controls = (
            self.window.status_label,
            self.window.progress,
            self.window.tabs,
            self.window.device_combo,
            self.window.device_details,
            self.window.app_status_label,
            self.window.refresh_button,
            self.window.install_button,
            self.window.uninstall_button,
            self.window.open_help_button,
            self.window.open_log_button,
            self.window.close_button,
            self.window.log_view,
            self.window.copy_log_button,
            self.window.save_log_button,
            self.window.clear_log_button,
            self.window.help_topics,
            self.window.help_paragraphs,
        )
        unnamed = [control.__class__.__name__ for control in controls if not control.accessibleName()]
        self.assertEqual(unnamed, [])

    def test_application_status_is_in_visual_tab_order(self) -> None:
        self.window.show()
        self.app.processEvents()
        self.window.install_button.setEnabled(True)
        self.window.device_details.setFocus(Qt.OtherFocusReason)

        QTest.keyClick(self.window.device_details, Qt.Key_Tab)
        self.assertIs(QApplication.focusWidget(), self.window.app_status_label)

        QTest.keyClick(self.window.app_status_label, Qt.Key_Tab)
        self.assertIs(QApplication.focusWidget(), self.window.install_button)

    def test_responsibility_is_first_and_paragraphs_are_separate_items(self) -> None:
        self.assertIn("Ответственность", HELP_TOPICS[0].title)
        self.assertIn("Ответственность", self.window.help_topics.item(0).text())
        self.assertEqual(
            self.window.help_paragraphs.count(), len(HELP_TOPICS[0].paragraphs)
        )
        self.assertTrue(self.window.help_paragraphs.item(0).text().startswith("Абзац 1"))

    def test_dangerous_actions_start_disabled_without_device(self) -> None:
        self.assertFalse(self.window.install_button.isEnabled())
        self.assertFalse(self.window.uninstall_button.isEnabled())

    def test_application_status_controls_install_and_remove_actions(self) -> None:
        not_installed = DeviceInfo(
            serial="TEST",
            state="device",
            model="B340",
            compatible=True,
            compatibility_message="Готово.",
        )
        self.window.device_infos = {"TEST": not_installed}
        self.window.device_combo.addItem(not_installed.display_name, "TEST")
        self.window._selected_device_changed(0)
        self.assertIn("не установлен", self.window.app_status_label.toPlainText())
        self.assertTrue(self.window.install_button.isEnabled())
        self.assertFalse(self.window.uninstall_button.isEnabled())

        partial = DeviceInfo(
            serial="TEST",
            state="device",
            model="B340",
            compatible=True,
            compatibility_message="Готово.",
            manager_installed=True,
            manager_version="1.5",
            bridge_installed=False,
        )
        self.window.device_infos["TEST"] = partial
        self.window._selected_device_changed(0)
        self.assertIn("Неполная установка", self.window.app_status_label.toPlainText())
        self.assertIn("Восстановить", self.window.install_button.text())
        self.assertTrue(self.window.uninstall_button.isEnabled())

        complete = DeviceInfo(
            serial="TEST",
            state="device",
            model="B340",
            compatible=True,
            compatibility_message="Готово.",
            manager_installed=True,
            manager_version="1.5",
            bridge_installed=True,
        )
        self.window.device_infos["TEST"] = complete
        self.window._selected_device_changed(0)
        self.assertIn("установлен", self.window.app_status_label.toPlainText())
        self.assertIn("1.5", self.window.app_status_label.toPlainText())
        self.assertIn("Пере", self.window.install_button.text())

    def test_interactive_targets_have_keyboard_focus_and_minimum_size(self) -> None:
        buttons = (
            self.window.refresh_button,
            self.window.install_button,
            self.window.uninstall_button,
            self.window.open_help_button,
            self.window.open_log_button,
            self.window.close_button,
            self.window.copy_log_button,
            self.window.save_log_button,
            self.window.clear_log_button,
        )
        self.assertGreaterEqual(self.window.device_combo.minimumHeight(), 44)
        for button in buttons:
            self.assertGreaterEqual(button.minimumHeight(), 44, button.accessibleName())
            self.assertNotEqual(button.focusPolicy(), Qt.NoFocus, button.accessibleName())

    def test_palette_contrast_meets_accessibility_thresholds(self) -> None:
        self.assertGreaterEqual(contrast_ratio(COLORS["text"], COLORS["surface"]), 4.5)
        self.assertGreaterEqual(contrast_ratio(COLORS["muted"], COLORS["surface"]), 4.5)
        self.assertGreaterEqual(contrast_ratio(COLORS["surface"], COLORS["primary"]), 4.5)
        self.assertGreaterEqual(contrast_ratio(COLORS["danger"], COLORS["surface"]), 4.5)
        self.assertGreaterEqual(contrast_ratio(COLORS["focus"], COLORS["surface"]), 3.0)
        self.assertGreaterEqual(contrast_ratio(COLORS["focus"], COLORS["primary"]), 3.0)

    def test_responsive_layout_reflows_without_hiding_actions(self) -> None:
        self.window.show()
        self.window._apply_responsive_layout(600)
        self.app.processEvents()
        self.assertTrue(self.window._compact_layout)
        self.assertEqual(self.window.help_splitter.orientation(), Qt.Vertical)
        compact_positions = []
        for button in self.window.main_focus_order[4:]:
            index = self.window.actions_layout.indexOf(button)
            compact_positions.append(self.window.actions_layout.getItemPosition(index)[:2])
            self.assertTrue(button.isVisible())
        self.assertEqual(compact_positions, [(0, 0), (1, 0), (2, 0), (3, 0), (4, 0)])

        self.window._apply_responsive_layout(1000)
        self.app.processEvents()
        self.assertFalse(self.window._compact_layout)
        self.assertEqual(self.window.help_splitter.orientation(), Qt.Horizontal)

    def test_responsive_reflow_preserves_keyboard_focus(self) -> None:
        self.window.show()
        self.app.processEvents()
        self.window.install_button.setEnabled(True)
        self.window.install_button.setFocus(Qt.OtherFocusReason)
        self.app.processEvents()
        self.window._apply_responsive_layout(600)
        self.app.processEvents()
        self.assertIs(QApplication.focusWidget(), self.window.install_button)

    def test_small_window_uses_vertical_scroll_without_horizontal_overflow(self) -> None:
        self.window.resize(560, 520)
        self.window.show()
        self.app.processEvents()
        self.assertTrue(self.window._compact_layout)
        self.assertEqual(self.window.main_scroll.horizontalScrollBar().maximum(), 0)
        self.assertGreater(self.window.main_scroll.verticalScrollBar().maximum(), 0)

    def test_escape_returns_focus_to_section_origin(self) -> None:
        self.window.show()
        self.app.processEvents()
        self.window.open_help_button.setFocus(Qt.OtherFocusReason)
        self.app.processEvents()
        self.window.focus_help()
        self.app.processEvents()
        self.assertIs(QApplication.focusWidget(), self.window.help_topics)
        self.window._escape_pressed()
        self.app.processEvents()
        self.assertIs(QApplication.focusWidget(), self.window.open_help_button)

    def test_manual_refresh_returns_focus_to_refresh_button(self) -> None:
        self.window.show()
        self.app.processEvents()
        self.window._initial_focus_pending = False
        self.window.refresh_button.setFocus(Qt.OtherFocusReason)
        self.window.request_scan()
        self.assertIs(QApplication.focusWidget(), self.window.status_label)
        assert self.window.scan_thread is not None
        self.window.scan_thread.wait(2000)
        self.app.processEvents()
        self.app.processEvents()
        self.assertIs(QApplication.focusWidget(), self.window.refresh_button)

    def test_confirmation_defaults_to_cancel_and_restores_trigger_focus(self) -> None:
        self.window.show()
        self.app.processEvents()
        self.window.install_button.setEnabled(True)
        self.window.install_button.setFocus(Qt.OtherFocusReason)
        observed = {}

        def inspect_and_cancel(dialog: QMessageBox) -> int:
            self.app.processEvents()
            observed["default"] = dialog.defaultButton().text()
            return QMessageBox.Cancel

        with patch.object(QMessageBox, "exec_", inspect_and_cancel):
            accepted = self.window._ask_confirmation(
                title="Проверка",
                question="Продолжить?",
                details="Тест безопасного фокуса.",
                confirm_text="Продолжить",
                trigger=self.window.install_button,
            )
        self.app.processEvents()
        self.assertFalse(accepted)
        self.assertIn("Отмена", observed["default"])
        self.assertIs(QApplication.focusWidget(), self.window.install_button)

    def test_dynamic_status_is_textual_and_accessible(self) -> None:
        self.window._set_status("Проверка завершена.", level="success")
        self.assertEqual(self.window.status_badge.text(), "ГОТОВО")
        self.assertIn("Проверка завершена", self.window.status_label.text())
        self.assertIn("Проверка завершена", self.window.status_label.accessibleName())
        self.assertEqual(self.window.status_frame.property("statusLevel"), "success")

    def test_high_contrast_mode_can_disable_custom_visual_theme(self) -> None:
        with patch.dict(os.environ, {"BRAILLE_INSTALLER_HIGH_CONTRAST": "1"}):
            self.assertTrue(high_contrast_enabled())

    def test_log_does_not_jump_while_reader_is_on_earlier_lines(self) -> None:
        self.window.show()
        self.window.focus_log()
        for index in range(120):
            self.window._append_log("info", f"Строка {index}")
        scrollbar = self.window.log_view.verticalScrollBar()
        self.assertGreater(scrollbar.maximum(), 0)
        scrollbar.setValue(0)
        self.window.log_view.setFocus(Qt.OtherFocusReason)
        self.window._append_log("info", "Новая строка в конце")
        self.assertEqual(scrollbar.value(), 0)


if __name__ == "__main__":
    unittest.main()
