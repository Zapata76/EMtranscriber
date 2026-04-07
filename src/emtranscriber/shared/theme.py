from __future__ import annotations

from PySide6.QtWidgets import QApplication

SUPPORTED_UI_THEMES = {"light", "dark"}

_DARK_STYLESHEET = """
QWidget {
    background-color: #1f232a;
    color: #e6edf3;
}
QTableWidget {
    background-color: #151a20;
    alternate-background-color: #1b2129;
    gridline-color: #2f3944;
    selection-background-color: #2a5f98;
    selection-color: #ffffff;
}
QHeaderView::section {
    background-color: #2a313a;
    color: #e6edf3;
    border: 1px solid #3b4652;
    padding: 4px;
}
QPushButton {
    background-color: #2d3742;
    border: 1px solid #445261;
    padding: 5px 10px;
    border-radius: 4px;
}
QPushButton:hover {
    background-color: #37414d;
}
QPushButton:pressed {
    background-color: #25303b;
}
QLineEdit, QPlainTextEdit, QComboBox, QSpinBox {
    background-color: #151a20;
    color: #e6edf3;
    border: 1px solid #3b4652;
    padding: 4px;
}
QGroupBox {
    border: 1px solid #3b4652;
    margin-top: 8px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 3px 0 3px;
}
QMenuBar, QMenu {
    background-color: #1f232a;
    color: #e6edf3;
}
QMenu::item:disabled {
    color: #7a8592;
}
QMenu::item:selected:disabled {
    background-color: #1f232a;
    color: #7a8592;
}
QLabel#mainSidebarImage {
    border: 1px solid #3b4652;
    background-color: #151a20;
}
""".strip()


def normalize_theme_name(theme: str | None) -> str:
    if not isinstance(theme, str):
        return "dark"
    candidate = theme.strip().lower()
    if candidate in SUPPORTED_UI_THEMES:
        return candidate
    return "dark"


def apply_theme(app: QApplication, theme: str | None) -> str:
    normalized = normalize_theme_name(theme)
    if normalized == "dark":
        app.setStyleSheet(_DARK_STYLESHEET)
    else:
        app.setStyleSheet("")
    return normalized

