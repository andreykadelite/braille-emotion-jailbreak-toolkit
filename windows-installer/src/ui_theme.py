from __future__ import annotations

import ctypes
import os
from typing import Final

from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QApplication, QWidget


COLORS: Final[dict[str, str]] = {
    "background": "#F4F7FC",
    "surface": "#FFFFFF",
    "surface_alt": "#F8FAFC",
    "text": "#101828",
    "muted": "#475467",
    "border": "#D0D5DD",
    "primary": "#175CD3",
    "primary_hover": "#1849A9",
    "primary_soft": "#EFF4FF",
    "danger": "#B42318",
    "danger_hover": "#912018",
    "danger_soft": "#FEF3F2",
    "success": "#067647",
    "success_soft": "#ECFDF3",
    "warning": "#93370D",
    "warning_soft": "#FFFAEB",
    "focus": "#000000",
    "disabled": "#667085",
    "disabled_bg": "#EAECF0",
}


def _style_sheet() -> str:
    color = COLORS
    return f"""
QMainWindow, QWidget#rootWidget {{
    background: {color['background']};
    color: {color['text']};
}}
QWidget {{
    color: {color['text']};
    selection-background-color: {color['primary']};
    selection-color: {color['surface']};
}}
QFrame#heroFrame {{
    background: {color['surface']};
    border: 1px solid {color['border']};
    border-radius: 12px;
}}
QLabel#eyebrowLabel {{
    color: {color['primary']};
    font-weight: 700;
}}
QLabel#headingLabel {{
    color: {color['text']};
    font-weight: 700;
}}
QLabel#subtitleLabel, QLabel#sectionDescription {{
    color: {color['muted']};
}}
QFrame#statusFrame {{
    background: {color['primary_soft']};
    border: 1px solid #B2CCFF;
    border-left: 6px solid {color['primary']};
    border-radius: 10px;
}}
QFrame#statusFrame[statusLevel="success"] {{
    background: {color['success_soft']};
    border-color: #ABEFC6;
    border-left-color: {color['success']};
}}
QFrame#statusFrame[statusLevel="warning"] {{
    background: {color['warning_soft']};
    border-color: #FEDF89;
    border-left-color: {color['warning']};
}}
QFrame#statusFrame[statusLevel="error"] {{
    background: {color['danger_soft']};
    border-color: #FECDCA;
    border-left-color: {color['danger']};
}}
QLabel#statusBadge {{
    color: {color['primary']};
    font-weight: 700;
}}
QFrame#statusFrame[statusLevel="success"] QLabel#statusBadge {{ color: {color['success']}; }}
QFrame#statusFrame[statusLevel="warning"] QLabel#statusBadge {{ color: {color['warning']}; }}
QFrame#statusFrame[statusLevel="error"] QLabel#statusBadge {{ color: {color['danger']}; }}
QLabel[focusableStatus="true"] {{
    padding: 7px;
    border: 2px solid transparent;
    border-radius: 7px;
}}
QLabel[focusableStatus="true"]:focus {{
    background: {color['surface']};
    border: 3px solid {color['focus']};
}}
QPlainTextEdit#appStatusLabel {{
    padding: 7px;
    border: 2px solid transparent;
    border-radius: 7px;
}}
QPlainTextEdit#appStatusLabel:focus {{
    padding: 6px;
    border: 3px solid {color['focus']};
}}
QPlainTextEdit#appStatusLabel[appState="installed"] {{
    background: {color['success_soft']};
    color: {color['success']};
}}
QPlainTextEdit#appStatusLabel[appState="partial"] {{
    background: {color['warning_soft']};
    color: {color['warning']};
}}
QPlainTextEdit#appStatusLabel[appState="missing"] {{
    background: {color['surface_alt']};
    color: {color['muted']};
}}
QGroupBox {{
    background: {color['surface']};
    border: 1px solid {color['border']};
    border-radius: 10px;
    margin-top: 14px;
    padding-top: 14px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 14px;
    padding: 0 6px;
    color: {color['text']};
    background: {color['surface']};
}}
QLineEdit, QComboBox, QPlainTextEdit, QListWidget {{
    background: {color['surface']};
    color: {color['text']};
    border: 1px solid #98A2B3;
    border-radius: 7px;
    padding: 7px;
}}
QComboBox {{ min-height: 28px; }}
QComboBox::drop-down {{
    width: 32px;
    border-left: 1px solid {color['border']};
}}
QPlainTextEdit:focus, QListWidget:focus, QComboBox:focus, QLineEdit:focus {{
    border: 3px solid {color['focus']};
    padding: 5px;
}}
QListWidget::item {{
    min-height: 34px;
    padding: 6px 8px;
    border-radius: 5px;
}}
QListWidget::item:selected {{
    background: {color['primary']};
    color: {color['surface']};
}}
QPushButton {{
    min-height: 28px;
    padding: 8px 14px;
    border: 1px solid #98A2B3;
    border-radius: 7px;
    background: {color['surface']};
    color: {color['text']};
    font-weight: 600;
}}
QPushButton:hover {{ background: {color['surface_alt']}; border-color: {color['muted']}; }}
QPushButton:pressed {{ background: #EAECF0; }}
QPushButton:focus {{ border: 3px solid {color['focus']}; padding: 6px 12px; }}
QPushButton[primaryAction="true"] {{
    background: {color['primary']};
    color: {color['surface']};
    border-color: {color['primary']};
}}
QPushButton[primaryAction="true"]:hover {{
    background: {color['primary_hover']};
    border-color: {color['primary_hover']};
}}
QPushButton[primaryAction="true"]:focus {{ border-color: {color['focus']}; }}
QPushButton[dangerAction="true"] {{
    background: {color['surface']};
    color: {color['danger']};
    border: 2px solid {color['danger']};
}}
QPushButton[dangerAction="true"]:hover {{ background: {color['danger_soft']}; }}
QPushButton[dangerAction="true"]:focus {{ border: 3px solid {color['focus']}; }}
QPushButton:disabled {{
    background: {color['disabled_bg']};
    color: {color['disabled']};
    border-color: #D0D5DD;
}}
QProgressBar {{
    min-height: 20px;
    border: 1px solid #98A2B3;
    border-radius: 7px;
    background: {color['surface']};
    color: {color['text']};
    text-align: center;
}}
QProgressBar::chunk {{
    background: {color['primary']};
    border-radius: 5px;
}}
QTabWidget::pane {{
    border: 1px solid {color['border']};
    border-radius: 8px;
    background: {color['surface_alt']};
    top: -1px;
}}
QTabBar::tab {{
    min-height: 32px;
    padding: 8px 18px;
    margin-right: 4px;
    background: #E4E7EC;
    color: {color['muted']};
    border: 1px solid {color['border']};
    border-bottom: none;
    border-top-left-radius: 7px;
    border-top-right-radius: 7px;
    font-weight: 600;
}}
QTabBar::tab:selected {{
    background: {color['surface']};
    color: {color['primary']};
}}
QTabBar:focus {{ border: 3px solid {color['focus']}; border-radius: 7px; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QSplitter::handle {{ background: {color['border']}; width: 3px; height: 3px; }}
QToolTip {{
    background: {color['text']};
    color: {color['surface']};
    border: 1px solid {color['text']};
    padding: 5px;
}}
QScrollBar:vertical {{ width: 16px; background: #EAECF0; margin: 0; }}
QScrollBar::handle:vertical {{ background: #667085; min-height: 32px; border-radius: 7px; margin: 2px; }}
QScrollBar:horizontal {{ height: 16px; background: #EAECF0; margin: 0; }}
QScrollBar::handle:horizontal {{ background: #667085; min-width: 32px; border-radius: 7px; margin: 2px; }}
QMessageBox QLabel {{ min-width: 360px; }}
"""


APP_STYLE_SHEET: Final[str] = _style_sheet()


def high_contrast_enabled() -> bool:
    override = os.environ.get("BRAILLE_INSTALLER_HIGH_CONTRAST", "").strip().lower()
    if override in {"1", "true", "yes"}:
        return True
    if os.name != "nt":
        return False
    try:
        class HighContrast(ctypes.Structure):
            _fields_ = (
                ("cbSize", ctypes.c_uint),
                ("dwFlags", ctypes.c_uint),
                ("lpszDefaultScheme", ctypes.c_wchar_p),
            )

        settings = HighContrast()
        settings.cbSize = ctypes.sizeof(settings)
        ok = ctypes.windll.user32.SystemParametersInfoW(
            0x0042, settings.cbSize, ctypes.byref(settings), 0
        )
        return bool(ok and settings.dwFlags & 0x00000001)
    except (AttributeError, OSError):
        return False


def apply_application_theme(app: QApplication) -> bool:
    if high_contrast_enabled():
        app.setStyleSheet("")
        app.setProperty("customVisualTheme", False)
        return False
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLE_SHEET)
    app.setProperty("customVisualTheme", True)
    return True


def repolish(widget: QWidget) -> None:
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


def contrast_ratio(foreground: str, background: str) -> float:
    def luminance(value: str) -> float:
        rgb = QColor(value)
        channels = (rgb.redF(), rgb.greenF(), rgb.blueF())
        converted = [
            channel / 12.92
            if channel <= 0.04045
            else ((channel + 0.055) / 1.055) ** 2.4
            for channel in channels
        ]
        return 0.2126 * converted[0] + 0.7152 * converted[1] + 0.0722 * converted[2]

    lighter, darker = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)
