from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGraphicsOpacityEffect,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from emtranscriber.application.dto.new_job_request import NewJobRequest
from emtranscriber.domain.entities.job_context_hints import JobContextHints
from emtranscriber.infrastructure.settings.app_settings import AppSettings
from emtranscriber.shared.i18n import UiTranslator


class NewJobDialog(QDialog):
    def __init__(
        self,
        settings: AppSettings,
        translator: UiTranslator,
        parent: QWidget | None = None,
        initial_language: str | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._tr = translator

        self.setWindowTitle(self._tr.t("new_job.title"))
        self.resize(760, 700)

        root = QVBoxLayout(self)

        form = QFormLayout()
        root.addLayout(form)

        source_row = QHBoxLayout()
        self.source_file_edit = QLineEdit()
        self.source_file_edit.setPlaceholderText(self._tr.t("new_job.source_placeholder"))
        browse_button = QPushButton(self._tr.t("common.browse"))
        browse_button.clicked.connect(self._on_browse)
        source_row.addWidget(self.source_file_edit)
        source_row.addWidget(browse_button)
        form.addRow(self._tr.t("new_job.source_file"), self._wrap_layout(source_row))

        output_row = QHBoxLayout()
        self.output_dir_edit = QLineEdit()
        self.output_dir_edit.setPlaceholderText(self._tr.t("new_job.output_dir_placeholder"))
        output_browse = QPushButton(self._tr.t("common.browse"))
        output_browse.clicked.connect(self._on_browse_output_dir)
        output_row.addWidget(self.output_dir_edit)
        output_row.addWidget(output_browse)
        form.addRow(self._tr.t("new_job.output_dir"), self._wrap_layout(output_row))

        self.project_name_edit = QLineEdit(self._tr.t("new_job.default_project"))
        form.addRow(self._tr.t("new_job.project"), self.project_name_edit)

        self.language_combo = QComboBox()
        self.language_combo.addItems(["auto", "it", "en", "es", "fr", "de"])
        if initial_language and self.language_combo.findText(initial_language) >= 0:
            self.language_combo.setCurrentText(initial_language)
        form.addRow(self._tr.t("new_job.language"), self.language_combo)

        self.model_combo = QComboBox()
        model_choices = ["small", "medium", "large-v3"]
        for key in self._settings.asr_model_paths:
            if key not in model_choices:
                model_choices.append(key)
        self.model_combo.addItems(model_choices)
        self.model_combo.setCurrentText(self._settings.default_asr_model)
        form.addRow(self._tr.t("new_job.asr_model"), self.model_combo)

        self.device_combo = QComboBox()
        self.device_combo.addItems(["auto", "cpu", "gpu"])
        self.device_combo.setCurrentText(self._settings.default_device)
        form.addRow(self._tr.t("new_job.device"), self.device_combo)

        self.compute_type_combo = QComboBox()
        self.compute_type_combo.addItems(["auto", "float16", "int8"])
        self.compute_type_combo.setCurrentText(self._settings.default_compute_type)
        form.addRow(self._tr.t("new_job.compute"), self.compute_type_combo)

        speaker_box = QGroupBox(self._tr.t("new_job.speaker_group"))
        speaker_layout = QGridLayout(speaker_box)
        root.addWidget(speaker_box)

        self.speaker_mode_combo = QComboBox()
        self.speaker_mode_combo.addItems(["auto", "exact", "minmax"])
        self.speaker_mode_combo.currentTextChanged.connect(self._on_speaker_mode_changed)

        self.exact_speakers_spin = QSpinBox()
        self.exact_speakers_spin.setRange(1, 20)
        self.exact_speakers_spin.setEnabled(False)

        self.min_speakers_spin = QSpinBox()
        self.min_speakers_spin.setRange(1, 20)
        self.min_speakers_spin.setEnabled(False)

        self.max_speakers_spin = QSpinBox()
        self.max_speakers_spin.setRange(1, 20)
        self.max_speakers_spin.setValue(2)
        self.max_speakers_spin.setEnabled(False)

        self.mode_label = QLabel(self._tr.t("new_job.mode"))
        self.exact_label = QLabel(self._tr.t("new_job.exact"))
        self.min_label = QLabel(self._tr.t("new_job.min"))
        self.max_label = QLabel(self._tr.t("new_job.max"))

        speaker_layout.addWidget(self.mode_label, 0, 0)
        speaker_layout.addWidget(self.speaker_mode_combo, 0, 1)
        speaker_layout.addWidget(self.exact_label, 1, 0)
        speaker_layout.addWidget(self.exact_speakers_spin, 1, 1)
        speaker_layout.addWidget(self.min_label, 2, 0)
        speaker_layout.addWidget(self.min_speakers_spin, 2, 1)
        speaker_layout.addWidget(self.max_label, 3, 0)
        speaker_layout.addWidget(self.max_speakers_spin, 3, 1)

        self._on_speaker_mode_changed(self.speaker_mode_combo.currentText())

        hints_box = QGroupBox(self._tr.t("new_job.hints_group"))
        hints_layout = QFormLayout(hints_box)
        root.addWidget(hints_box)

        self.enable_hints_check = QCheckBox(self._tr.t("new_job.hints_toggle"))
        self.enable_hints_check.setChecked(True)
        self.enable_hints_check.toggled.connect(self._on_hints_toggled)
        hints_layout.addRow(self.enable_hints_check)

        self.domain_context_edit = QPlainTextEdit()
        self.domain_context_edit.setPlaceholderText(self._tr.t("new_job.domain_placeholder"))
        self.domain_context_edit.setFixedHeight(220)
        hints_layout.addRow(self._tr.t("new_job.domain_context"), self.domain_context_edit)

        self.hotwords_edit = QLineEdit()
        self.hotwords_edit.setPlaceholderText(self._tr.t("new_job.csv_terms_placeholder"))
        hints_layout.addRow(self._tr.t("new_job.hotwords"), self.hotwords_edit)

        self.glossary_edit = QLineEdit()
        self.glossary_edit.setPlaceholderText(self._tr.t("new_job.csv_terms_placeholder"))
        hints_layout.addRow(self._tr.t("new_job.glossary"), self.glossary_edit)

        self.participants_edit = QLineEdit()
        self.participants_edit.setPlaceholderText(self._tr.t("new_job.csv_names_placeholder"))
        hints_layout.addRow(self._tr.t("new_job.participants"), self.participants_edit)

        self.acronyms_edit = QLineEdit()
        self.acronyms_edit.setPlaceholderText(self._tr.t("new_job.csv_acronyms_placeholder"))
        hints_layout.addRow(self._tr.t("new_job.acronyms"), self.acronyms_edit)

        self.entities_edit = QLineEdit()
        self.entities_edit.setPlaceholderText(self._tr.t("new_job.csv_entities_placeholder"))
        hints_layout.addRow(self._tr.t("new_job.entities"), self.entities_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    @staticmethod
    def _wrap_layout(layout) -> QWidget:
        widget = QWidget()
        widget.setLayout(layout)
        return widget

    def _on_browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            self._tr.t("new_job.source_file"),
            "",
            self._tr.t("new_job.media_filter"),
        )
        if path:
            self.source_file_edit.setText(path)
            self._sync_output_path_from_source()

    def _on_browse_output_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, self._tr.t("new_job.output_dir"))
        if path:
            self.output_dir_edit.setText(path)

    def _sync_output_path_from_source(self) -> None:
        if self.output_dir_edit.text().strip():
            return

        source_raw = self.source_file_edit.text().strip()
        if not source_raw:
            return

        source_parent = Path(source_raw).expanduser().resolve().parent
        self.output_dir_edit.setText(str(source_parent))

    def _on_speaker_mode_changed(self, mode: str) -> None:
        self._apply_speaker_field_state(
            label=self.exact_label,
            spin=self.exact_speakers_spin,
            active=mode == "exact",
        )
        minmax_enabled = mode == "minmax"
        self._apply_speaker_field_state(
            label=self.min_label,
            spin=self.min_speakers_spin,
            active=minmax_enabled,
        )
        self._apply_speaker_field_state(
            label=self.max_label,
            spin=self.max_speakers_spin,
            active=minmax_enabled,
        )

    def _apply_speaker_field_state(self, *, label: QLabel, spin: QSpinBox, active: bool) -> None:
        label.setEnabled(active)
        spin.setEnabled(active)
        spin.setButtonSymbols(QSpinBox.ButtonSymbols.UpDownArrows if active else QSpinBox.ButtonSymbols.NoButtons)
        self._set_faded(label, not active)
        self._set_faded(spin, not active)

    @staticmethod
    def _set_faded(widget: QWidget, faded: bool) -> None:
        if not faded:
            widget.setGraphicsEffect(None)
            return

        effect = QGraphicsOpacityEffect(widget)
        effect.setOpacity(0.38)
        widget.setGraphicsEffect(effect)

    def _on_hints_toggled(self, enabled: bool) -> None:
        self.domain_context_edit.setEnabled(enabled)
        self.hotwords_edit.setEnabled(enabled)
        self.glossary_edit.setEnabled(enabled)
        self.participants_edit.setEnabled(enabled)
        self.acronyms_edit.setEnabled(enabled)
        self.entities_edit.setEnabled(enabled)

    def _on_accept(self) -> None:
        if not self.source_file_edit.text().strip():
            QMessageBox.warning(
                self,
                self._tr.t("new_job.missing_source_title"),
                self._tr.t("new_job.missing_source_text"),
            )
            return

        self._sync_output_path_from_source()

        if self.speaker_mode_combo.currentText() == "minmax":
            if self.min_speakers_spin.value() > self.max_speakers_spin.value():
                QMessageBox.warning(
                    self,
                    self._tr.t("new_job.invalid_speaker_title"),
                    self._tr.t("new_job.invalid_speaker_text"),
                )
                return

        self.accept()

    @staticmethod
    def _parse_csv(raw: str) -> list[str]:
        return [item.strip() for item in raw.split(",") if item.strip()]

    def build_request(self) -> NewJobRequest:
        speaker_mode = self.speaker_mode_combo.currentText()
        exact_speakers = self.exact_speakers_spin.value() if speaker_mode == "exact" else None
        min_speakers = self.min_speakers_spin.value() if speaker_mode == "minmax" else None
        max_speakers = self.max_speakers_spin.value() if speaker_mode == "minmax" else None

        hints = None
        if self.enable_hints_check.isChecked():
            hints = JobContextHints(
                language_hint=None if self.language_combo.currentText() == "auto" else self.language_combo.currentText(),
                domain_context=self.domain_context_edit.toPlainText().strip() or None,
                hotwords=self._parse_csv(self.hotwords_edit.text()),
                glossary_terms=self._parse_csv(self.glossary_edit.text()),
                expected_participants=self._parse_csv(self.participants_edit.text()),
                expected_entities=self._parse_csv(self.entities_edit.text()),
                expected_acronyms=self._parse_csv(self.acronyms_edit.text()),
            )

        return NewJobRequest(
            project_name=self.project_name_edit.text().strip() or self._tr.t("new_job.default_project"),
            source_file_path=self.source_file_edit.text().strip(),
            artifacts_root_path=self.output_dir_edit.text().strip() or None,
            language_selected=self.language_combo.currentText(),
            model_name=self.model_combo.currentText(),
            device_used=self.device_combo.currentText(),
            compute_type=self.compute_type_combo.currentText(),
            speaker_count_mode=speaker_mode,
            exact_speakers=exact_speakers,
            min_speakers=min_speakers,
            max_speakers=max_speakers,
            context_hints=hints,
        )
