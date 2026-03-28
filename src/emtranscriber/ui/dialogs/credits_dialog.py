from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from emtranscriber.shared.i18n import UiTranslator

_GPL_V3_URL = "https://www.gnu.org/licenses/gpl-3.0.html"


@dataclass(frozen=True, slots=True)
class CreditLink:
    label_key: str
    url: str
    object_name: str


_PROFILE_LINKS: tuple[CreditLink, ...] = (
    CreditLink("credits.link.github", "https://github.com/Zapata76", "creditsGithubButton"),
    CreditLink("credits.link.website", "https://www.emilianomaugeri.it", "creditsWebsiteButton"),
    CreditLink("credits.link.linkedin", "https://www.linkedin.com/in/emiliano-maugeri-710395a6/", "creditsLinkedinButton"),
)


class CreditsDialog(QDialog):
    def __init__(self, translator: UiTranslator, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tr = translator
        self._license_text = self._load_license_text()

        self.setWindowTitle(self._tr.t("credits.window_title"))
        self.resize(840, 620)
        self._apply_stylesheet()
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        header = QLabel(self._tr.t("credits.header"))
        header.setObjectName("creditsHeader")
        root.addWidget(header)

        profile_card = QFrame()
        profile_card.setObjectName("creditsCard")
        profile_layout = QVBoxLayout(profile_card)
        profile_layout.setContentsMargins(20, 18, 20, 18)
        profile_layout.setSpacing(16)
        root.addWidget(profile_card)

        top_row = QHBoxLayout()
        top_row.setSpacing(14)
        profile_layout.addLayout(top_row)

        badge = QLabel("EM")
        badge.setObjectName("creditsBadge")
        badge.setFixedSize(76, 76)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top_row.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)

        identity_layout = QVBoxLayout()
        identity_layout.setSpacing(4)
        top_row.addLayout(identity_layout, 1)

        name = QLabel(self._tr.t("credits.author_name"))
        name.setObjectName("creditsAuthorName")
        identity_layout.addWidget(name)

        role = QLabel(self._tr.t("credits.author_role"))
        role.setObjectName("creditsAuthorRole")
        identity_layout.addWidget(role)

        bio = QLabel(self._tr.t("credits.author_bio"))
        bio.setObjectName("creditsBio")
        bio.setWordWrap(True)
        profile_layout.addWidget(bio)

        links_row = QHBoxLayout()
        links_row.setSpacing(10)
        profile_layout.addLayout(links_row)

        for link in _PROFILE_LINKS:
            button = QPushButton(self._tr.t(link.label_key))
            button.setObjectName(link.object_name)
            button.clicked.connect(lambda _checked=False, target=link.url: self._open_link(target))
            links_row.addWidget(button)
        links_row.addStretch(1)

        about_card = QFrame()
        about_card.setObjectName("creditsCard")
        about_layout = QVBoxLayout(about_card)
        about_layout.setContentsMargins(20, 18, 20, 18)
        about_layout.setSpacing(12)
        root.addWidget(about_card)

        about_title = QLabel(self._tr.t("credits.about_title"))
        about_title.setObjectName("creditsAboutTitle")
        about_layout.addWidget(about_title)

        about_body = QLabel(self._tr.t("credits.about_body"))
        about_body.setWordWrap(True)
        about_body.setObjectName("creditsAboutBody")
        about_layout.addWidget(about_body)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setObjectName("creditsDivider")
        about_layout.addWidget(divider)

        license_line = QLabel(self._tr.t("credits.license_line"))
        license_line.setObjectName("creditsLicenseLine")
        license_line.setWordWrap(True)
        about_layout.addWidget(license_line)

        license_button = QPushButton(self._tr.t("credits.view_license"))
        license_button.setObjectName("creditsLicenseButton")
        license_button.clicked.connect(self._show_license)
        about_layout.addWidget(license_button, 0, Qt.AlignmentFlag.AlignLeft)

        close_buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_buttons.rejected.connect(self.reject)
        close_buttons.accepted.connect(self.accept)
        root.addWidget(close_buttons)

    def _open_link(self, url: str) -> None:
        if not QDesktopServices.openUrl(QUrl(url)):
            QMessageBox.warning(
                self,
                self._tr.t("credits.link_error_title"),
                self._tr.t("credits.link_error_text", url=url),
            )

    def _show_license(self) -> None:
        if not self._license_text:
            self._open_link(_GPL_V3_URL)
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(self._tr.t("credits.license_dialog_title"))
        dialog.resize(880, 680)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(12, 12, 12, 12)

        viewer = QPlainTextEdit(dialog)
        viewer.setReadOnly(True)
        viewer.setPlainText(self._license_text)
        layout.addWidget(viewer)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        buttons.accepted.connect(dialog.accept)
        layout.addWidget(buttons)
        dialog.exec()

    def _load_license_text(self) -> str:
        candidates: list[Path] = []

        frozen_root = getattr(sys, "_MEIPASS", None)
        if frozen_root:
            candidates.append(Path(frozen_root) / "LICENSE")

        candidates.append(Path(__file__).resolve().parents[4] / "LICENSE")

        for candidate in candidates:
            if candidate.exists():
                try:
                    return candidate.read_text(encoding="utf-8")
                except OSError:
                    continue
        return ""

    def _apply_stylesheet(self) -> None:
        self.setStyleSheet(
            """
            QDialog {
                background: #0f1115;
                color: #f1f3f5;
            }
            QLabel#creditsHeader {
                color: #4f8dff;
                font-size: 34px;
                font-weight: 700;
            }
            QFrame#creditsCard {
                background: #161b22;
                border: 1px solid #2c3542;
                border-radius: 14px;
            }
            QLabel#creditsBadge {
                background: #3f7ae0;
                color: #eef4ff;
                border-radius: 38px;
                font-size: 34px;
                font-weight: 700;
            }
            QLabel#creditsAuthorName {
                font-size: 42px;
                font-weight: 700;
                color: #f8fafc;
            }
            QLabel#creditsAuthorRole {
                color: #4d8dff;
                font-size: 24px;
                font-weight: 600;
            }
            QLabel#creditsBio,
            QLabel#creditsAboutBody {
                color: #d8dde7;
                font-size: 24px;
                line-height: 1.4em;
            }
            QLabel#creditsAboutTitle {
                color: #4d8dff;
                font-size: 30px;
                font-weight: 650;
            }
            QFrame#creditsDivider {
                color: #2a3342;
                background: #2a3342;
            }
            QLabel#creditsLicenseLine {
                color: #d8dde7;
                font-size: 22px;
            }
            QPushButton {
                border-radius: 8px;
                padding: 8px 16px;
                font-size: 20px;
                font-weight: 600;
                color: #ecf2ff;
                border: 1px solid transparent;
                background: #2b313a;
            }
            QPushButton:hover {
                background: #374150;
            }
            QPushButton#creditsGithubButton {
                background: #2e333b;
            }
            QPushButton#creditsWebsiteButton {
                background: #4f8dff;
            }
            QPushButton#creditsLinkedinButton {
                background: #1180d3;
            }
            QPushButton#creditsLicenseButton {
                background: #2e333b;
                border: 1px solid #4d8dff;
            }
            """
        )

