from __future__ import annotations

from PySide6.QtCore import QThreadPool, Qt
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from emtranscriber.application.dto.analysis_run_result import AnalysisRunResult
from emtranscriber.application.workers.analysis_worker import AnalysisWorker
from emtranscriber.bootstrap import AppContainer
from emtranscriber.domain.entities.transcript_document import TranscriptDocument
from emtranscriber.ui.dialogs.analysis_dialog import AnalysisDialog


class ReviewWindow(QMainWindow):
    def __init__(self, container: AppContainer, job_id: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._container = container
        self._tr = container.translator
        self._job_id = job_id
        self._thread_pool = QThreadPool.globalInstance()
        self._analysis_worker: AnalysisWorker | None = None

        self.setWindowTitle(self._tr.t("review.title", job=job_id[:8]))
        self.resize(1200, 760)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        toolbar = QHBoxLayout()
        root.addLayout(toolbar)

        refresh_btn = QPushButton(self._tr.t("review.refresh"))
        refresh_btn.clicked.connect(self._load)
        toolbar.addWidget(refresh_btn)

        save_segments_btn = QPushButton(self._tr.t("review.save_segments"))
        save_segments_btn.clicked.connect(self._save_segment_edits)
        toolbar.addWidget(save_segments_btn)

        save_speakers_btn = QPushButton(self._tr.t("review.save_speakers"))
        save_speakers_btn.clicked.connect(self._save_speaker_mapping)
        toolbar.addWidget(save_speakers_btn)

        export_btn = QPushButton(self._tr.t("review.reexport"))
        export_btn.clicked.connect(self._export)
        toolbar.addWidget(export_btn)

        self.analyze_btn = QPushButton(self._tr.t("review.analyze"))
        self.analyze_btn.clicked.connect(self._on_analyze)
        toolbar.addWidget(self.analyze_btn)

        toolbar.addStretch(1)
        self.status_label = QLabel("")
        toolbar.addWidget(self.status_label)

        splitter = QSplitter()
        root.addWidget(splitter)

        self.segment_table = QTableWidget(0, 4)
        self.segment_table.setHorizontalHeaderLabels(
            [
                self._tr.t("review.table.start"),
                self._tr.t("review.table.end"),
                self._tr.t("review.table.speaker"),
                self._tr.t("review.table.text"),
            ]
        )
        self.segment_table.horizontalHeader().setStretchLastSection(True)
        splitter.addWidget(self.segment_table)

        speaker_panel = QWidget()
        speaker_layout = QVBoxLayout(speaker_panel)

        speaker_group = QGroupBox(self._tr.t("review.speaker_mapping"))
        speaker_group_layout = QVBoxLayout(speaker_group)
        speaker_layout.addWidget(speaker_group)

        self.speaker_table = QTableWidget(0, 2)
        self.speaker_table.setHorizontalHeaderLabels([self._tr.t("review.map_key"), self._tr.t("review.map_name")])
        self.speaker_table.horizontalHeader().setStretchLastSection(True)
        speaker_group_layout.addWidget(self.speaker_table)

        splitter.addWidget(speaker_panel)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 2)

        self._load()

    def _load(self) -> None:
        document = self._container.get_transcript_document_use_case.execute(self._job_id)
        self._populate_segments(document)
        self._populate_speakers(document)
        self.status_label.setText(
            self._tr.t("review.status_counts", segments=len(document.segments), speakers=len(document.speakers))
        )

    def _populate_segments(self, document: TranscriptDocument) -> None:
        self.segment_table.setRowCount(len(document.segments))
        for row_idx, seg in enumerate(document.segments):
            start_item = QTableWidgetItem(self._clock(seg.start_ms))
            start_item.setFlags(start_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            start_item.setData(Qt.ItemDataRole.UserRole, seg.segment_id)

            end_item = QTableWidgetItem(self._clock(seg.end_ms))
            end_item.setFlags(end_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

            speaker_item = QTableWidgetItem(seg.speaker_name_resolved or seg.speaker_key or "")
            speaker_item.setFlags(speaker_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

            text_item = QTableWidgetItem(seg.text)

            self.segment_table.setItem(row_idx, 0, start_item)
            self.segment_table.setItem(row_idx, 1, end_item)
            self.segment_table.setItem(row_idx, 2, speaker_item)
            self.segment_table.setItem(row_idx, 3, text_item)

        self.segment_table.resizeColumnsToContents()

    def _populate_speakers(self, document: TranscriptDocument) -> None:
        self.speaker_table.setRowCount(len(document.speakers))
        for row_idx, speaker in enumerate(document.speakers):
            key_item = QTableWidgetItem(speaker.speaker_key)
            key_item.setFlags(key_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

            name_item = QTableWidgetItem(speaker.display_name or "")
            self.speaker_table.setItem(row_idx, 0, key_item)
            self.speaker_table.setItem(row_idx, 1, name_item)

        self.speaker_table.resizeColumnsToContents()

    def _save_segment_edits(self) -> None:
        for row in range(self.segment_table.rowCount()):
            start_item = self.segment_table.item(row, 0)
            text_item = self.segment_table.item(row, 3)
            if start_item is None or text_item is None:
                continue

            segment_id = start_item.data(Qt.ItemDataRole.UserRole)
            if not segment_id:
                continue

            self._container.update_segment_text_use_case.execute(segment_id, text_item.text())

        self._load()
        QMessageBox.information(self, self._tr.t("common.saved"), self._tr.t("review.saved_segments"))

    def _save_speaker_mapping(self) -> None:
        for row in range(self.speaker_table.rowCount()):
            key_item = self.speaker_table.item(row, 0)
            name_item = self.speaker_table.item(row, 1)
            if key_item is None or name_item is None:
                continue

            self._container.rename_speaker_use_case.execute(
                self._job_id,
                key_item.text(),
                name_item.text(),
            )

        self._load()
        QMessageBox.information(self, self._tr.t("common.saved"), self._tr.t("review.saved_speakers"))

    def _export(self) -> None:
        outputs = self._container.export_transcript_use_case.execute(self._job_id)
        export_lines = "\n".join(f"{fmt}: {path}" for fmt, path in outputs.items())
        QMessageBox.information(self, self._tr.t("review.export_done"), export_lines)

    def _on_analyze(self) -> None:
        if self._analysis_worker is not None:
            QMessageBox.information(
                self,
                self._tr.t("review.analysis_busy_title"),
                self._tr.t("review.analysis_busy_text"),
            )
            return

        if not self._container.settings.ai_analysis_enabled:
            QMessageBox.information(
                self,
                self._tr.t("review.analysis_disabled_title"),
                self._tr.t("review.analysis_disabled_text"),
            )
            return

        dialog = AnalysisDialog(self._container.settings, self._tr, self)
        if dialog.exec() != AnalysisDialog.DialogCode.Accepted:
            return

        options = dialog.build_options()

        self.analyze_btn.setEnabled(False)
        self.status_label.setText(self._tr.t("review.analysis_running"))

        worker = AnalysisWorker(
            self._container.analyze_transcript_use_case,
            self._job_id,
            options,
        )
        worker.signals.finished.connect(self._on_analysis_finished)
        worker.signals.failed.connect(self._on_analysis_failed)

        self._analysis_worker = worker
        self._thread_pool.start(worker)

    def _on_analysis_finished(self, result: AnalysisRunResult) -> None:
        self._analysis_worker = None
        self.analyze_btn.setEnabled(True)
        self.status_label.setText(self._tr.t("review.analysis_done"))

        preview = result.output_text.strip()
        if len(preview) > 700:
            preview = preview[:700].rstrip() + "..."

        QMessageBox.information(
            self,
            self._tr.t("review.analysis_done_title"),
            "\n".join(
                [
                    f"Provider: {result.provider_name}",
                    f"Model: {result.model_identifier or self._tr.t('review.analysis_model_na')}",
                    f"Output: {result.output_markdown_path}",
                    "",
                    preview,
                ]
            ),
        )

    def _on_analysis_failed(self, error: str) -> None:
        self._analysis_worker = None
        self.analyze_btn.setEnabled(True)
        self.status_label.setText(self._tr.t("review.analysis_fail"))
        QMessageBox.critical(self, self._tr.t("review.analysis_fail"), error)

    @staticmethod
    def _clock(total_ms: int) -> str:
        minutes, ms_remaining = divmod(max(total_ms, 0), 60_000)
        seconds, milliseconds = divmod(ms_remaining, 1000)
        return f"{minutes:02d}:{seconds:02d}.{milliseconds:03d}"
