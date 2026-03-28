from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from emtranscriber.infrastructure.ai_analysis.templates import available_templates
from emtranscriber.infrastructure.settings.app_settings import AppSettings
from emtranscriber.shared.i18n import UiTranslator


class SettingsDialog(QDialog):
    def __init__(self, settings: AppSettings, translator: UiTranslator, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._tr = translator

        self.setWindowTitle(self._tr.t("settings.title"))
        self.resize(820, 760)

        root = QVBoxLayout(self)

        self._build_defaults_group(root)
        self._build_asr_paths_group(root)
        self._build_pyannote_group(root)
        self._build_ai_analysis_group(root)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._refresh_ai_controls()

    def _build_defaults_group(self, root: QVBoxLayout) -> None:
        general_box = QGroupBox(self._tr.t("settings.defaults"))
        general_form = QFormLayout(general_box)
        root.addWidget(general_box)

        self.ui_language_combo = QComboBox()
        self.ui_language_combo.addItem(self._tr.t("settings.lang.system"), "")
        self.ui_language_combo.addItem(self._tr.t("settings.lang.en"), "en")
        self.ui_language_combo.addItem(self._tr.t("settings.lang.es"), "es")
        self.ui_language_combo.addItem(self._tr.t("settings.lang.de"), "de")
        self.ui_language_combo.addItem(self._tr.t("settings.lang.fr"), "fr")
        self.ui_language_combo.addItem(self._tr.t("settings.lang.it"), "it")
        idx = self.ui_language_combo.findData(self._settings.ui_language or "")
        self.ui_language_combo.setCurrentIndex(idx if idx >= 0 else 0)
        general_form.addRow(self._tr.t("settings.ui_language"), self.ui_language_combo)

        self.ui_theme_combo = QComboBox()
        self.ui_theme_combo.addItem(self._tr.t("settings.theme.light"), "light")
        self.ui_theme_combo.addItem(self._tr.t("settings.theme.dark"), "dark")
        theme_index = self.ui_theme_combo.findData(self._settings.ui_theme or "light")
        self.ui_theme_combo.setCurrentIndex(theme_index if theme_index >= 0 else 0)
        general_form.addRow(self._tr.t("settings.ui_theme"), self.ui_theme_combo)

        self.default_model_combo = QComboBox()
        self.default_model_combo.addItems(["small", "medium", "large-v3"])
        self.default_model_combo.setCurrentText(self._settings.default_asr_model)
        general_form.addRow(self._tr.t("settings.default_asr_model"), self.default_model_combo)

        self.default_device_combo = QComboBox()
        self.default_device_combo.addItems(["auto", "cpu", "gpu"])
        self.default_device_combo.setCurrentText(self._settings.default_device)
        general_form.addRow(self._tr.t("settings.default_device"), self.default_device_combo)

        self.default_compute_combo = QComboBox()
        self.default_compute_combo.addItems(["auto", "float16", "int8"])
        self.default_compute_combo.setCurrentText(self._settings.default_compute_type)
        general_form.addRow(self._tr.t("settings.default_compute"), self.default_compute_combo)

    def _build_asr_paths_group(self, root: QVBoxLayout) -> None:
        models_box = QGroupBox(self._tr.t("settings.asr_paths"))
        models_layout = QGridLayout(models_box)
        root.addWidget(models_box)

        self.path_small = self._create_path_row(models_layout, 0, "small", self._settings.asr_model_paths.get("small"))
        self.path_medium = self._create_path_row(models_layout, 1, "medium", self._settings.asr_model_paths.get("medium"))
        self.path_large = self._create_path_row(models_layout, 2, "large-v3", self._settings.asr_model_paths.get("large-v3"))

    def _build_pyannote_group(self, root: QVBoxLayout) -> None:
        pyannote_box = QGroupBox(self._tr.t("settings.pyannote_group"))
        pyannote_form = QFormLayout(pyannote_box)
        root.addWidget(pyannote_box)

        pyannote_row = QHBoxLayout()
        self.pyannote_model_path_edit = QLineEdit(self._settings.pyannote_model_path or "")
        browse_pyannote = QPushButton(self._tr.t("common.browse"))
        browse_pyannote.clicked.connect(lambda: self._browse_directory(self.pyannote_model_path_edit))
        pyannote_row.addWidget(self.pyannote_model_path_edit)
        pyannote_row.addWidget(browse_pyannote)
        pyannote_form.addRow(self._tr.t("settings.pyannote_path"), self._wrap(pyannote_row))

        self.hf_token_edit = QLineEdit(self._settings.huggingface_token or "")
        self.hf_token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.hf_token_edit.setPlaceholderText(self._tr.t("settings.hf_token_ph"))
        pyannote_form.addRow(self._tr.t("settings.hf_token"), self.hf_token_edit)

    def _build_ai_analysis_group(self, root: QVBoxLayout) -> None:
        ai_box = QGroupBox(self._tr.t("settings.ai_group"))
        ai_form = QFormLayout(ai_box)
        root.addWidget(ai_box)

        self.ai_enabled_check = QCheckBox(self._tr.t("settings.ai_enable"))
        self.ai_enabled_check.setChecked(self._settings.ai_analysis_enabled)
        self.ai_enabled_check.toggled.connect(self._refresh_ai_controls)
        ai_form.addRow(self.ai_enabled_check)

        self.ai_provider_combo = QComboBox()
        self.ai_provider_combo.addItem("disabled")
        self.ai_provider_combo.addItem("openai_compatible")
        self.ai_provider_combo.setCurrentText(self._settings.ai_analysis_provider or "disabled")
        self.ai_provider_combo.currentTextChanged.connect(self._refresh_ai_controls)
        ai_form.addRow(self._tr.t("settings.provider"), self.ai_provider_combo)

        self.ai_endpoint_edit = QLineEdit(self._settings.ai_analysis_endpoint)
        self.ai_endpoint_edit.setPlaceholderText("https://api.openai.com/v1/chat/completions")
        ai_form.addRow(self._tr.t("settings.endpoint"), self.ai_endpoint_edit)

        self.ai_model_edit = QLineEdit(self._settings.ai_analysis_model or "")
        self.ai_model_edit.setPlaceholderText("gpt-4.1-mini")
        ai_form.addRow(self._tr.t("settings.model"), self.ai_model_edit)

        self.ai_api_key_edit = QLineEdit(self._settings.ai_analysis_api_key or "")
        self.ai_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.ai_api_key_edit.setPlaceholderText(self._tr.t("settings.api_key"))
        ai_form.addRow(self._tr.t("settings.api_key"), self.ai_api_key_edit)

        self.ai_template_combo = QComboBox()
        for key, label in available_templates():
            self.ai_template_combo.addItem(label, key)
        template_index = self.ai_template_combo.findData(self._settings.ai_analysis_default_template)
        self.ai_template_combo.setCurrentIndex(template_index if template_index >= 0 else 0)
        ai_form.addRow(self._tr.t("settings.default_template"), self.ai_template_combo)

        self.ai_output_language_edit = QLineEdit(self._settings.ai_analysis_output_language or "")
        self.ai_output_language_edit.setPlaceholderText(self._tr.t("settings.output_language_placeholder"))
        ai_form.addRow(self._tr.t("settings.output_language"), self.ai_output_language_edit)

        self.ai_prompt_edit = QPlainTextEdit(self._settings.ai_analysis_default_prompt or "")
        self.ai_prompt_edit.setPlaceholderText(self._tr.t("settings.default_prompt_ph"))
        self.ai_prompt_edit.setFixedHeight(120)
        ai_form.addRow(self._tr.t("settings.default_prompt"), self.ai_prompt_edit)

    def build_settings(self) -> AppSettings:
        paths = {
            "small": self.path_small.text().strip(),
            "medium": self.path_medium.text().strip(),
            "large-v3": self.path_large.text().strip(),
        }

        ui_language = self.ui_language_combo.currentData()
        ui_language_value = ui_language if ui_language else None
        ui_theme_value = self.ui_theme_combo.currentData() or "light"

        return AppSettings(
            default_asr_model=self.default_model_combo.currentText(),
            default_device=self.default_device_combo.currentText(),
            default_compute_type=self.default_compute_combo.currentText(),
            asr_model_paths={key: value for key, value in paths.items() if value},
            pyannote_model_path=self.pyannote_model_path_edit.text().strip() or None,
            huggingface_token=self.hf_token_edit.text().strip() or None,
            ui_language=ui_language_value,
            ui_theme=ui_theme_value,
            ai_analysis_enabled=self.ai_enabled_check.isChecked(),
            ai_analysis_provider=self.ai_provider_combo.currentText(),
            ai_analysis_endpoint=self.ai_endpoint_edit.text().strip(),
            ai_analysis_api_key=self.ai_api_key_edit.text().strip() or None,
            ai_analysis_model=self.ai_model_edit.text().strip() or None,
            ai_analysis_default_template=self.ai_template_combo.currentData(),
            ai_analysis_default_prompt=self.ai_prompt_edit.toPlainText().strip(),
            ai_analysis_output_language=self.ai_output_language_edit.text().strip() or None,
        )

    def _create_path_row(self, layout: QGridLayout, row: int, label: str, value: str | None) -> QLineEdit:
        layout.addWidget(QLabel(label), row, 0)
        line_edit = QLineEdit(value or "")
        browse = QPushButton(self._tr.t("common.browse"))
        browse.clicked.connect(lambda: self._browse_directory(line_edit))
        layout.addWidget(line_edit, row, 1)
        layout.addWidget(browse, row, 2)
        return line_edit

    def _browse_directory(self, line_edit: QLineEdit) -> None:
        path = QFileDialog.getExistingDirectory(self, self._tr.t("common.browse"))
        if path:
            line_edit.setText(path)

    def _refresh_ai_controls(self, *_args) -> None:
        enabled = self.ai_enabled_check.isChecked()
        provider_active = enabled and self.ai_provider_combo.currentText() != "disabled"

        self.ai_provider_combo.setEnabled(enabled)
        self.ai_endpoint_edit.setEnabled(provider_active)
        self.ai_model_edit.setEnabled(provider_active)
        self.ai_api_key_edit.setEnabled(provider_active)
        self.ai_template_combo.setEnabled(enabled)
        self.ai_output_language_edit.setEnabled(enabled)
        self.ai_prompt_edit.setEnabled(enabled)

    @staticmethod
    def _wrap(layout) -> QWidget:
        widget = QWidget()
        widget.setLayout(layout)
        return widget
