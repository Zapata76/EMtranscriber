from __future__ import annotations

from PySide6.QtCore import QThreadPool, QTimer, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from emtranscriber.application.workers.job_processing_worker import JobProcessingWorker
from emtranscriber.bootstrap import AppContainer
from emtranscriber.domain.value_objects.job_status import JobStatus
from emtranscriber.shared.theme import apply_theme
from emtranscriber.ui.dialogs.credits_dialog import CreditsDialog
from emtranscriber.ui.dialogs.new_job_dialog import NewJobDialog
from emtranscriber.ui.dialogs.settings_dialog import SettingsDialog
from emtranscriber.ui.viewmodels.job_row_mapper import JobRowMapper
from emtranscriber.ui.windows.processing_window import ProcessingWindow
from emtranscriber.ui.windows.review_window import ReviewWindow

_PROCESSING_IMAGE_SEQUENCE = (
    "working1",
    "working2",
    "working3",
    "working4",
    "working5",
    "tired",
    "panic",
    "desperate",
    "fail",
)
_SUCCESS_FINAL_STATUSES = {
    JobStatus.COMPLETED.value,
    JobStatus.READY_FOR_REVIEW.value,
}


class MainWindow(QMainWindow):
    def __init__(self, container: AppContainer) -> None:
        super().__init__()
        self._container = container
        self._tr = container.translator
        self._thread_pool = QThreadPool.globalInstance()
        self._active_workers: dict[str, JobProcessingWorker] = {}
        self._processing_windows: dict[str, ProcessingWindow] = {}
        self._review_windows: dict[str, ReviewWindow] = {}

        self._branding_pixmaps = self._load_branding_pixmaps()
        self._sidebar_source_pixmap: QPixmap | None = None
        self._processing_image_keys = [key for key in _PROCESSING_IMAGE_SEQUENCE if key in self._branding_pixmaps]
        self._processing_image_index = 0

        self._processing_image_timer = QTimer(self)
        self._processing_image_timer.setInterval(120_000)  # 2 minutes
        self._processing_image_timer.timeout.connect(self._on_processing_image_tick)

        self.setWindowTitle(self._tr.t("main.title"))
        self.resize(1100, 700)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        root = QVBoxLayout(central_widget)

        title = QLabel(self._tr.t("main.header"))
        root.addWidget(title)

        toolbar = QHBoxLayout()
        root.addLayout(toolbar)

        self.new_job_button = QPushButton(self._tr.t("main.new_job"))
        self.new_job_button.clicked.connect(self._on_new_job)
        toolbar.addWidget(self.new_job_button)

        self.start_job_button = QPushButton(self._tr.t("main.start_selected"))
        self.start_job_button.clicked.connect(self._on_start_selected_job)
        toolbar.addWidget(self.start_job_button)

        self.review_button = QPushButton(self._tr.t("main.open_review"))
        self.review_button.clicked.connect(self._on_open_review_selected)
        toolbar.addWidget(self.review_button)

        self.settings_button = QPushButton(self._tr.t("main.settings"))
        self.settings_button.clicked.connect(self._on_settings)
        toolbar.addWidget(self.settings_button)

        self.credits_button = QPushButton(self._tr.t("main.credits"))
        self.credits_button.clicked.connect(self._on_credits)
        toolbar.addWidget(self.credits_button)

        self.refresh_button = QPushButton(self._tr.t("main.refresh"))
        self.refresh_button.clicked.connect(self._on_refresh_clicked)
        toolbar.addWidget(self.refresh_button)

        toolbar.addStretch(1)

        content = QHBoxLayout()
        root.addLayout(content, 1)

        self.sidebar_image_label = QLabel()
        self.sidebar_image_label.setObjectName("mainSidebarImage")
        self.sidebar_image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sidebar_image_label.setMinimumHeight(500)
        self.sidebar_image_label.setMinimumWidth(320)
        self.sidebar_image_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        content.addWidget(self.sidebar_image_label)

        self.jobs_table = QTableWidget(0, 6)
        self.jobs_table.setHorizontalHeaderLabels(
            [
                self._tr.t("main.table.job_id"),
                self._tr.t("main.table.project_id"),
                self._tr.t("main.table.source"),
                self._tr.t("main.table.status"),
                self._tr.t("main.table.created"),
                self._tr.t("main.table.completed"),
            ]
        )
        self.jobs_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.jobs_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.jobs_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.jobs_table.horizontalHeader().setStretchLastSection(True)
        self.jobs_table.doubleClicked.connect(self._on_open_review_selected)
        content.addWidget(self.jobs_table, 1)

        self._set_sidebar_image("welcome")
        self._refresh_jobs()

        if self._container.pipeline_is_stub:
            QMessageBox.warning(
                self,
                self._tr.t("pipeline.stub_warning_title"),
                self._tr.t("pipeline.stub_warning_text"),
            )

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._update_sidebar_pixmap()

    def _load_branding_pixmaps(self) -> dict[str, QPixmap]:
        pixmaps: dict[str, QPixmap] = {}
        for key in (
            "icon",
            "welcome",
            "working1",
            "working2",
            "working3",
            "working4",
            "working5",
            "tired",
            "panic",
            "desperate",
            "fail",
            "sad",
        ):
            pixmap = QPixmap(f":/branding/{key}")
            if not pixmap.isNull():
                pixmaps[key] = pixmap
        return pixmaps

    def _set_sidebar_image(self, key: str) -> None:
        pixmap = self._branding_pixmaps.get(key)
        if pixmap is None:
            self._sidebar_source_pixmap = None
            self.sidebar_image_label.setPixmap(QPixmap())
            self.sidebar_image_label.setText(self._tr.t("main.sidebar_image_missing"))
            return

        self._sidebar_source_pixmap = pixmap
        self.sidebar_image_label.setText("")
        self._update_sidebar_pixmap()

    def _update_sidebar_pixmap(self) -> None:
        if self._sidebar_source_pixmap is None:
            return

        target_size = self.sidebar_image_label.size()
        if target_size.width() <= 0 or target_size.height() <= 0:
            return

        scaled = self._sidebar_source_pixmap.scaled(
            target_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.sidebar_image_label.setPixmap(scaled)

    def _start_processing_image_cycle(self) -> None:
        if not self._processing_image_keys:
            return
        self._processing_image_index = 0
        self._set_sidebar_image(self._processing_image_keys[self._processing_image_index])
        self._processing_image_timer.start()

    def _on_processing_image_tick(self) -> None:
        if not self._processing_image_keys:
            return
        self._processing_image_index = (self._processing_image_index + 1) % len(self._processing_image_keys)
        self._set_sidebar_image(self._processing_image_keys[self._processing_image_index])

    def _finish_processing_image_cycle(self, *, success: bool) -> None:
        self._processing_image_timer.stop()
        self._set_sidebar_image("welcome" if success else "sad")

    def _on_new_job(self, *_args) -> None:
        initial_language = self._resolve_new_job_initial_language()
        dialog = NewJobDialog(
            self._container.settings,
            self._tr,
            self,
            initial_language=initial_language,
        )
        if dialog.exec() != NewJobDialog.DialogCode.Accepted:
            return

        request = dialog.build_request()

        try:
            job = self._container.create_job_use_case.execute(request)
        except FileNotFoundError as exc:
            QMessageBox.critical(self, self._tr.t("new_job.missing_source_title"), str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, self._tr.t("common.error_title"), str(exc))
            return

        self._refresh_jobs(select_job_id=job.job_id)
        self._start_job_processing(job.job_id)

    def _resolve_new_job_initial_language(self) -> str | None:
        jobs = self._container.list_jobs_use_case.execute(limit=1)
        if not jobs:
            return None

        job = jobs[0]
        language = (job.language_selected or "").strip().lower()
        detected = (job.language_detected or "").strip().lower()

        if language == "auto" and detected in {"it", "en", "es", "fr", "de"}:
            return detected

        if language in {"auto", "it", "en", "es", "fr", "de"}:
            return language

        if detected in {"it", "en", "es", "fr", "de"}:
            return detected

        return None

    def _on_start_selected_job(self, *_args) -> None:
        job_id = self._selected_job_id()
        if not job_id:
            QMessageBox.information(self, self._tr.t("common.select_job_title"), self._tr.t("common.select_job_text"))
            return

        self._start_job_processing(job_id)

    def _on_open_review_selected(self, *_args) -> None:
        job_id = self._selected_job_id()
        if not job_id:
            QMessageBox.information(self, self._tr.t("common.select_job_title"), self._tr.t("common.select_job_text"))
            return

        self._open_review(job_id)

    def _on_credits(self, *_args) -> None:
        dialog = CreditsDialog(self._tr, self)
        dialog.exec()

    def _on_settings(self, *_args) -> None:
        dialog = SettingsDialog(self._container.settings, self._tr, self)
        if dialog.exec() != SettingsDialog.DialogCode.Accepted:
            return

        old_ui_language = self._container.settings.ui_language
        new_settings = dialog.build_settings()

        self._container.settings.default_asr_model = new_settings.default_asr_model
        self._container.settings.default_device = new_settings.default_device
        self._container.settings.default_compute_type = new_settings.default_compute_type
        self._container.settings.asr_model_paths = new_settings.asr_model_paths
        self._container.settings.pyannote_model_path = new_settings.pyannote_model_path
        self._container.settings.huggingface_token = new_settings.huggingface_token
        self._container.settings.ui_language = new_settings.ui_language
        self._container.settings.ui_theme = new_settings.ui_theme

        self._container.settings.ai_analysis_enabled = new_settings.ai_analysis_enabled
        self._container.settings.ai_analysis_provider = new_settings.ai_analysis_provider
        self._container.settings.ai_analysis_endpoint = new_settings.ai_analysis_endpoint
        self._container.settings.ai_analysis_api_key = new_settings.ai_analysis_api_key
        self._container.settings.ai_analysis_model = new_settings.ai_analysis_model
        self._container.settings.ai_analysis_default_template = new_settings.ai_analysis_default_template
        self._container.settings.ai_analysis_default_prompt = new_settings.ai_analysis_default_prompt
        self._container.settings.ai_analysis_output_language = new_settings.ai_analysis_output_language

        self._container.settings_store.save(self._container.settings)

        app = QApplication.instance()
        if app is not None:
            apply_theme(app, self._container.settings.ui_theme)

        message_key = "main.settings_saved"
        if old_ui_language != new_settings.ui_language:
            message_key = "main.settings_saved_restart"

        QMessageBox.information(self, self._tr.t("common.saved"), self._tr.t(message_key))

    def _on_refresh_clicked(self, *_args) -> None:
        self._refresh_jobs()

    def _start_job_processing(self, job_id: str) -> None:
        if job_id in self._active_workers:
            window = self._processing_windows.get(job_id)
            if window is not None:
                window.raise_()
                window.activateWindow()
            return

        worker = JobProcessingWorker(self._container.orchestrator, job_id)
        processing_window = ProcessingWindow(job_id, self._tr, self)
        processing_window.cancel_requested.connect(self._on_cancel_requested)

        worker.signals.progress.connect(
            lambda status, message, percent, jid=job_id: self._on_worker_progress(
                jid,
                status,
                message,
                percent,
            )
        )
        worker.signals.finished.connect(self._on_worker_finished)
        worker.signals.failed.connect(self._on_worker_failed)

        self._active_workers[job_id] = worker
        self._processing_windows[job_id] = processing_window

        if len(self._active_workers) == 1:
            self._start_processing_image_cycle()

        processing_window.show()
        self._thread_pool.start(worker)

    def _on_worker_progress(self, job_id: str, status: str, message: str, percent: int) -> None:
        window = self._processing_windows.get(job_id)
        if window is not None:
            window.update_progress(status, message, percent)
        self._refresh_jobs(select_job_id=job_id)

    def _on_worker_finished(self, job_id: str, final_status: str) -> None:
        window = self._processing_windows.get(job_id)
        if window is not None:
            if final_status == JobStatus.CANCELLED.value:
                window.mark_cancelled()
            else:
                window.mark_finished()

        self._active_workers.pop(job_id, None)
        if not self._active_workers:
            self._finish_processing_image_cycle(success=final_status in _SUCCESS_FINAL_STATUSES)

        self._refresh_jobs(select_job_id=job_id)

        job = self._container.job_repository.get_by_id(job_id)
        if job and job.status in {JobStatus.COMPLETED, JobStatus.PARTIAL_SUCCESS, JobStatus.READY_FOR_REVIEW}:
            self._open_review(job_id)

    def _on_worker_failed(self, job_id: str, error: str) -> None:
        window = self._processing_windows.get(job_id)
        if window is not None:
            window.mark_failed(error)

        self._active_workers.pop(job_id, None)
        if not self._active_workers:
            self._finish_processing_image_cycle(success=False)

        self._refresh_jobs(select_job_id=job_id)

    def _on_cancel_requested(self, job_id: str) -> None:
        worker = self._active_workers.get(job_id)
        if worker is not None:
            worker.cancel()

    def _open_review(self, job_id: str) -> None:
        if job_id in self._review_windows:
            win = self._review_windows[job_id]
            win.raise_()
            win.activateWindow()
            return

        try:
            self._container.get_transcript_document_use_case.execute(job_id)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, self._tr.t("common.warning_title"), str(exc))
            return

        review = ReviewWindow(self._container, job_id, self)
        review.destroyed.connect(lambda *_: self._review_windows.pop(job_id, None))
        self._review_windows[job_id] = review
        review.show()

    def _refresh_jobs(self, select_job_id: str | None = None) -> None:
        jobs = self._container.list_jobs_use_case.execute(limit=500)

        self.jobs_table.setRowCount(len(jobs))
        for row_idx, job in enumerate(jobs):
            row = JobRowMapper.map(job)
            self._set_cell(row_idx, 0, row.job_id)
            self._set_cell(row_idx, 1, row.project_id)
            self._set_cell(row_idx, 2, row.source_path)
            self._set_cell(row_idx, 3, row.status)
            self._set_cell(row_idx, 4, row.created_at)
            self._set_cell(row_idx, 5, row.completed_at)

            if select_job_id and row.job_id == select_job_id:
                self.jobs_table.selectRow(row_idx)

        self.jobs_table.resizeColumnsToContents()

    def _selected_job_id(self) -> str | None:
        selected = self.jobs_table.selectedItems()
        if not selected:
            return None
        return selected[0].text()

    def _set_cell(self, row: int, col: int, value: str) -> None:
        item = QTableWidgetItem(value)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.jobs_table.setItem(row, col, item)

