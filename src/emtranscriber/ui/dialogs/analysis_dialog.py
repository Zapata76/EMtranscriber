from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from emtranscriber.application.dto.analysis_request_options import AnalysisRequestOptions
from emtranscriber.infrastructure.ai_analysis.templates import available_templates
from emtranscriber.infrastructure.settings.app_settings import AppSettings
from emtranscriber.shared.i18n import UiTranslator


class AnalysisDialog(QDialog):
    def __init__(self, settings: AppSettings, translator: UiTranslator, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tr = translator

        self.setWindowTitle(self._tr.t("analysis.title"))
        self.resize(760, 460)

        root = QVBoxLayout(self)

        warning = QLabel(self._tr.t("analysis.privacy"))
        warning.setWordWrap(True)
        root.addWidget(warning)

        form = QFormLayout()
        root.addLayout(form)

        self.template_combo = QComboBox()
        for key, label in available_templates():
            self.template_combo.addItem(label, key)
        template_idx = self.template_combo.findData(settings.ai_analysis_default_template)
        self.template_combo.setCurrentIndex(template_idx if template_idx >= 0 else 0)
        form.addRow(self._tr.t("analysis.template"), self.template_combo)

        self.output_language_edit = QLineEdit(settings.ai_analysis_output_language or "")
        self.output_language_edit.setPlaceholderText(self._tr.t("analysis.output_language_placeholder"))
        form.addRow(self._tr.t("analysis.output_language"), self.output_language_edit)

        self.prompt_edit = QPlainTextEdit(settings.ai_analysis_default_prompt or "")
        self.prompt_edit.setPlaceholderText(self._tr.t("analysis.prompt_ph"))
        self.prompt_edit.setFixedHeight(220)
        form.addRow(self._tr.t("analysis.prompt"), self.prompt_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _on_accept(self) -> None:
        if self.template_combo.currentData() == "custom" and not self.prompt_edit.toPlainText().strip():
            QMessageBox.warning(
                self,
                self._tr.t("analysis.prompt_required_title"),
                self._tr.t("analysis.prompt_required_text"),
            )
            return
        self.accept()

    def build_options(self) -> AnalysisRequestOptions:
        return AnalysisRequestOptions(
            analysis_template=self.template_combo.currentData(),
            analysis_prompt=self.prompt_edit.toPlainText().strip() or None,
            output_language=self.output_language_edit.text().strip() or None,
        )
