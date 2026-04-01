from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

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

from emtranscriber.application.services.job_queue_state_machine import (
    InvalidQueueTransition,
    JobQueueStateMachine,
)
from emtranscriber.application.workers.job_processing_worker import JobProcessingWorker
from emtranscriber.bootstrap import AppContainer
from emtranscriber.domain.entities.job import Job
from emtranscriber.domain.entities.job_context_hints import JobContextHints
from emtranscriber.domain.value_objects.job_status import JobStatus
from emtranscriber.infrastructure.runtime.requirements_checker import (
    RuntimeReport,
    check_runtime_requirements,
    install_command_candidates,
)
from emtranscriber.shared.theme import apply_theme
from emtranscriber.ui.dialogs.credits_dialog import CreditsDialog
from emtranscriber.ui.dialogs.new_job_dialog import NewJobDialog, NewJobPrefill
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
_TERMINAL_STATUSES = {
    JobStatus.COMPLETED,
    JobStatus.PARTIAL_SUCCESS,
    JobStatus.READY_FOR_REVIEW,
    JobStatus.FAILED,
    JobStatus.CANCELLED,
}
_ACTIVE_PROCESSING_STATUSES = {
    JobStatus.PREPARING_AUDIO,
    JobStatus.TRANSCRIBING,
    JobStatus.DIARIZING,
    JobStatus.ALIGNING,
}


class MainWindow(QMainWindow):
    def __init__(self, container: AppContainer) -> None:
        super().__init__()
        self._container = container
        self._tr = container.translator
        self._thread_pool = QThreadPool.globalInstance()
        self._active_workers: dict[str, JobProcessingWorker] = {}
        self._review_windows: dict[str, ReviewWindow] = {}
        self._queue_machine = JobQueueStateMachine()
        self._runtime_report: RuntimeReport | None = None
        self._jobs_cache_by_id: dict[str, Job] = {}
        self._jobs_cache_queued_ids: set[str] = set()
        self._last_jobs_refresh_ts = 0.0
        self._last_jobs_resize_rows = -1

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

        self.queue_stop_button = QPushButton(self._tr.t("main.queue_stop"))
        self.queue_stop_button.clicked.connect(self._on_interrupt_queue)
        toolbar.addWidget(self.queue_stop_button)

        self.queue_resume_button = QPushButton(self._tr.t("main.queue_resume"))
        self.queue_resume_button.clicked.connect(self._on_resume_queue)
        toolbar.addWidget(self.queue_resume_button)

        self.remove_queued_button = QPushButton(self._tr.t("main.queue_remove_selected"))
        self.remove_queued_button.clicked.connect(self._on_remove_selected_queued)
        toolbar.addWidget(self.remove_queued_button)

        self.review_button = QPushButton(self._tr.t("main.open_review"))
        self.review_button.clicked.connect(self._on_open_review_selected)
        toolbar.addWidget(self.review_button)

        self.refresh_button = QPushButton(self._tr.t("main.refresh"))
        self.refresh_button.clicked.connect(self._on_refresh_clicked)
        toolbar.addWidget(self.refresh_button)

        toolbar.addStretch(1)

        self.settings_button = QPushButton(self._tr.t("main.settings"))
        self.settings_button.clicked.connect(self._on_settings)
        toolbar.addWidget(self.settings_button)

        self.credits_button = QPushButton(self._tr.t("main.credits"))
        self.credits_button.clicked.connect(self._on_credits)
        toolbar.addWidget(self.credits_button)

        content = QHBoxLayout()
        root.addLayout(content, 1)

        self.sidebar_image_label = QLabel()
        self.sidebar_image_label.setObjectName("mainSidebarImage")
        self.sidebar_image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sidebar_image_label.setMinimumHeight(500)
        self.sidebar_image_label.setMinimumWidth(320)
        self.sidebar_image_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        content.addWidget(self.sidebar_image_label)

        self.jobs_table = QTableWidget(0, 7)
        self.jobs_table.setHorizontalHeaderLabels(
            [
                self._tr.t("main.table.project"),
                self._tr.t("main.table.job_id"),
                self._tr.t("main.table.project_id"),
                self._tr.t("main.table.status"),
                self._tr.t("main.table.created"),
                self._tr.t("main.table.completed"),
                self._tr.t("main.table.source"),
            ]
        )
        self.jobs_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.jobs_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.jobs_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.jobs_table.horizontalHeader().setStretchLastSection(True)
        self.jobs_table.doubleClicked.connect(self._on_open_review_selected)
        self.jobs_table.itemSelectionChanged.connect(self._update_queue_buttons)
        content.addWidget(self.jobs_table, 1)
        self.jobs_table.setColumnHidden(1, True)
        self.jobs_table.setColumnHidden(2, True)

        self.processing_panel = ProcessingWindow(self._tr, self)
        self.processing_panel.setMinimumHeight(260)
        self.processing_panel.cancel_requested.connect(self._on_cancel_requested)
        root.addWidget(self.processing_panel, 1)

        self._set_sidebar_image("welcome")
        self._recover_interrupted_jobs_to_queue()
        self._refresh_jobs(resize_columns=True)
        self._update_queue_buttons()

        QTimer.singleShot(0, self._run_startup_flow)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._update_sidebar_pixmap()

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._active_workers:
            response = QMessageBox.question(
                self,
                self._tr.t("main.queue_stop_title"),
                self._tr.t("main.queue_stop_text"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if response != QMessageBox.StandardButton.Yes:
                event.ignore()
                return

            for worker in list(self._active_workers.values()):
                worker.cancel()

            # Give workers a short grace window to observe cancellation before closing.
            self._thread_pool.waitForDone(2000)
            if self._thread_pool.activeThreadCount() > 0:
                QMessageBox.warning(
                    self,
                    self._tr.t("common.warning_title"),
                    "A job is still shutting down. Wait a moment and try closing again.",
                )
                event.ignore()
                return

        self._processing_image_timer.stop()
        for review in list(self._review_windows.values()):
            review.close()

        super().closeEvent(event)

    def _run_startup_flow(self) -> None:
        if self._container.is_first_run:
            self._open_settings_dialog(focus_hf_token=True, show_saved_message=False)

        if self._container.pipeline_is_stub:
            QMessageBox.warning(
                self,
                self._tr.t("pipeline.stub_warning_title"),
                self._tr.t("pipeline.stub_warning_text"),
            )
            return

        self._runtime_report = check_runtime_requirements(self._container.settings)
        self._show_runtime_requirements_report(blocking=False)

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
        latest_job = self._get_latest_job()
        initial_language = self._resolve_new_job_initial_language(latest_job)
        prefill = self._build_new_job_prefill(latest_job)

        dialog = NewJobDialog(
            self._container.settings,
            self._tr,
            self,
            initial_language=initial_language,
            prefill=prefill,
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

        self._refresh_jobs(select_job_id=job.job_id, resize_columns=True)
        if not self._ensure_runtime_ready_for_processing(show_dialog=True):
            return

        self._enqueue_job(job.job_id)

    def _get_latest_job(self) -> Job | None:
        jobs = self._container.list_jobs_use_case.execute(limit=1)
        if not jobs:
            return None
        return jobs[0]

    @staticmethod
    def _resolve_new_job_initial_language(job: Job | None) -> str | None:
        if job is None:
            return None

        language = (job.language_selected or "").strip().lower()
        detected = (job.language_detected or "").strip().lower()

        if language == "auto" and detected in {"it", "en", "es", "fr", "de"}:
            return detected

        if language in {"auto", "it", "en", "es", "fr", "de"}:
            return language

        if detected in {"it", "en", "es", "fr", "de"}:
            return detected

        return None

    def _build_new_job_prefill(self, job: Job | None) -> NewJobPrefill | None:
        if job is None:
            return None

        project_name = None
        project = self._container.project_repository.get_by_id(job.project_id)
        if project is not None:
            project_name = project.name

        hints = self._container.job_repository.get_context_hints(job.job_id)

        return NewJobPrefill(
            project_name=project_name,
            device_used=(job.device_used or None),
            compute_type=(job.compute_type or None),
            speaker_count_mode=(job.speaker_count_mode or "auto"),
            exact_speakers=job.exact_speakers,
            min_speakers=job.min_speakers,
            max_speakers=job.max_speakers,
            context_hints_enabled=hints is not None,
            context_hints=hints,
        )

    def _on_start_selected_job(self, *_args) -> None:
        job_id = self._selected_job_id()
        if not job_id:
            QMessageBox.information(self, self._tr.t("common.select_job_title"), self._tr.t("common.select_job_text"))
            return

        if not self._ensure_runtime_ready_for_processing(show_dialog=True):
            return

        self._enqueue_job(job_id, start_immediately=True)

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
        self._open_settings_dialog(focus_hf_token=False, show_saved_message=True)

    def _open_settings_dialog(self, *, focus_hf_token: bool, show_saved_message: bool) -> bool:
        dialog = SettingsDialog(
            self._container.settings,
            self._tr,
            self,
            focus_hf_token=focus_hf_token,
        )
        if dialog.exec() != SettingsDialog.DialogCode.Accepted:
            return False

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
        self._runtime_report = None

        app = QApplication.instance()
        if app is not None:
            apply_theme(app, self._container.settings.ui_theme)

        if show_saved_message:
            message_key = "main.settings_saved"
            if old_ui_language != new_settings.ui_language:
                message_key = "main.settings_saved_restart"
            QMessageBox.information(self, self._tr.t("common.saved"), self._tr.t(message_key))

        return True

    def _on_refresh_clicked(self, *_args) -> None:
        self._refresh_jobs(resize_columns=True)

    def _runtime_installer_script_path(self) -> Path | None:
        candidates: list[Path] = []

        if getattr(sys, "frozen", False):
            exe_dir = Path(sys.executable).resolve().parent
            candidates.append(exe_dir / "install_ml_runtime.ps1")
            candidates.append(exe_dir / "_internal" / "install_ml_runtime.ps1")

        project_root = Path(__file__).resolve().parents[4]
        candidates.append(project_root / "scripts" / "install_ml_runtime.ps1")

        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return candidate

        return None

    def _runtime_report_text(self, report: RuntimeReport) -> str:
        lines = [self._tr.t("runtime.check.detected_issues")]

        for issue in report.issues:
            level_key = "runtime.check.level_critical" if issue.critical else "runtime.check.level_warning"
            lines.append(f"- [{self._tr.t(level_key)}] {issue.details}")
            lines.append(f"  -> {issue.fix}")

        lines.append("")
        lines.append(self._tr.t("runtime.check.install_commands"))
        for command in install_command_candidates():
            lines.append(f"  {command}")

        return "\n".join(lines)

    def _launch_runtime_installer(self, installer_path: Path) -> None:
        try:
            subprocess.Popen(
                [
                    "powershell",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(installer_path),
                ],
                cwd=str(installer_path.parent),
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(
                self,
                self._tr.t("runtime.check.title"),
                self._tr.t("runtime.check.installer_launch_failed", error=str(exc)),
            )

    def _show_runtime_requirements_report(self, *, blocking: bool) -> None:
        if self._runtime_report is None or self._runtime_report.is_ok:
            return

        intro_key = "runtime.check.blocking_text" if blocking else "runtime.check.startup_text"
        body = f"{self._tr.t(intro_key)}\n\n{self._runtime_report_text(self._runtime_report)}"

        installer_path = self._runtime_installer_script_path()
        if installer_path is None:
            QMessageBox.warning(self, self._tr.t("runtime.check.title"), body)
            return

        prompt = (
            f"{body}\n\n"
            f"{self._tr.t('runtime.check.installer_hint', path=str(installer_path))}\n"
            f"{self._tr.t('runtime.check.run_installer_question')}"
        )
        response = QMessageBox.question(
            self,
            self._tr.t("runtime.check.title"),
            prompt,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if response == QMessageBox.StandardButton.Yes:
            self._launch_runtime_installer(installer_path)

    def _ensure_runtime_ready_for_processing(self, *, show_dialog: bool) -> bool:
        if self._container.pipeline_is_stub:
            return True

        self._runtime_report = check_runtime_requirements(self._container.settings)
        if not self._runtime_report.has_critical:
            return True

        if show_dialog:
            self._show_runtime_requirements_report(blocking=True)
        return False

    def _recover_interrupted_jobs_to_queue(self) -> None:
        jobs = self._container.list_jobs_use_case.execute(limit=2000)
        for job in jobs:
            if job.status in _ACTIVE_PROCESSING_STATUSES:
                self._container.job_repository.update_status(
                    job.job_id,
                    JobStatus.QUEUED,
                    error_message="Recovered to queue after app restart.",
                )

    def _enqueue_job(self, job_id: str, start_immediately: bool = False) -> None:
        if job_id in self._active_workers:
            return

        job = self._jobs_cache_by_id.get(job_id)
        if job is None:
            QMessageBox.warning(self, self._tr.t("common.warning_title"), f"Job not found: {job_id}")
            return

        if job.status in _TERMINAL_STATUSES:
            QMessageBox.information(
                self,
                self._tr.t("main.queue_info_title"),
                self._tr.t("main.queue_cannot_enqueue_final"),
            )
            return

        if job.status != JobStatus.QUEUED:
            self._container.job_repository.update_status(job_id, JobStatus.QUEUED)

        self._refresh_jobs(select_job_id=job_id)
        self._update_queue_buttons()

        if start_immediately:
            if self._queue_machine.snapshot().paused:
                self._queue_machine.resume()
                
            if not self._queue_machine.snapshot().has_active_job:
                if not self._ensure_runtime_ready_for_processing(show_dialog=False):
                    self._queue_machine.pause()
                    self._update_queue_buttons()
                    return
                self._start_job_processing(job_id)
                return

        self._start_next_queued_job()

    def _start_next_queued_job(self) -> bool:
        if not self._queue_machine.can_dispatch_next(has_queued_jobs=bool(self._jobs_cache_queued_ids)):
            return False

        if not self._ensure_runtime_ready_for_processing(show_dialog=False):
            self._queue_machine.pause()
            self._update_queue_buttons()
            return False

        queued_jobs = self._container.job_repository.list_by_status(JobStatus.QUEUED, limit=1)
        if not queued_jobs:
            return False

        self._start_job_processing(queued_jobs[0].job_id)
        return True

    def _on_interrupt_queue(self, *_args) -> None:
        has_active = self._queue_machine.snapshot().has_active_job
        has_queued = bool(self._jobs_cache_queued_ids)

        if not has_active and not has_queued:
            QMessageBox.information(self, self._tr.t("main.queue_info_title"), self._tr.t("main.queue_empty"))
            return

        if has_active:
            response = QMessageBox.question(
                self,
                self._tr.t("main.queue_stop_title"),
                self._tr.t("main.queue_stop_text"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Yes,
            )
            if response == QMessageBox.StandardButton.Cancel:
                return

            self._queue_machine.pause()
            active_job_id = self._queue_machine.snapshot().active_job_id
            if response == QMessageBox.StandardButton.No and active_job_id is not None:
                worker = self._active_workers.get(active_job_id)
                if worker is not None:
                    worker.cancel()

            self._refresh_jobs(select_job_id=self._queue_machine.snapshot().active_job_id)
            self._update_queue_buttons()
            return

        self._queue_machine.pause()
        self._refresh_jobs()
        self._update_queue_buttons()

    def _on_resume_queue(self, *_args) -> None:
        if not self._ensure_runtime_ready_for_processing(show_dialog=True):
            return

        self._queue_machine.resume()
        started = self._start_next_queued_job()
        if not started:
            self._refresh_jobs()
        self._update_queue_buttons()

    def _on_remove_selected_queued(self, *_args) -> None:
        job_id = self._selected_job_id()
        if not job_id:
            QMessageBox.information(self, self._tr.t("common.select_job_title"), self._tr.t("common.select_job_text"))
            return

        job = self._jobs_cache_by_id.get(job_id)
        if job is None:
            QMessageBox.warning(self, self._tr.t("common.warning_title"), f"Job not found: {job_id}")
            return

        if job.status != JobStatus.QUEUED:
            QMessageBox.information(
                self,
                self._tr.t("main.queue_info_title"),
                self._tr.t("main.queue_remove_only_queued"),
            )
            return

        self._container.job_repository.update_status(
            job_id,
            JobStatus.CANCELLED,
            error_message="Removed from queue by user.",
            completed=True,
        )
        self._refresh_jobs()
        self._update_queue_buttons()

    def _update_queue_buttons(self) -> None:
        has_active = self._queue_machine.snapshot().has_active_job
        has_queued = bool(self._jobs_cache_queued_ids)

        selected_job_id = self._selected_job_id()
        selected_is_queued = False
        if selected_job_id:
            selected_job = self._jobs_cache_by_id.get(selected_job_id)
            selected_is_queued = selected_job is not None and selected_job.status == JobStatus.QUEUED

        self.queue_stop_button.setEnabled(has_active or has_queued)
        self.queue_resume_button.setEnabled(self._queue_machine.snapshot().paused)
        self.remove_queued_button.setEnabled(selected_is_queued)

    def _start_job_processing(self, job_id: str) -> None:
        if job_id in self._active_workers:
            return

        if self._active_workers:
            return

        worker = JobProcessingWorker(self._container.orchestrator, job_id)
        job = self._jobs_cache_by_id.get(job_id)
        hints = self._container.job_repository.get_context_hints(job_id) if job is not None else None
        initial_log_lines = self._build_processing_log_header(job, hints)
        job_display_name = self._resolve_job_display_name(job, fallback=job_id[:8])
        self.processing_panel.bind_job(job_id, job_display_name, initial_log_lines=initial_log_lines)

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

        try:
            self._queue_machine.start_job(job_id)
        except InvalidQueueTransition:
            return

        self._active_workers[job_id] = worker

        if len(self._active_workers) == 1:
            self._start_processing_image_cycle()

        self._thread_pool.start(worker)
        self._update_queue_buttons()

    def _on_worker_progress(self, job_id: str, status: str, message: str, percent: int) -> None:
        if self._queue_machine.snapshot().active_job_id == job_id:
            self.processing_panel.update_progress(status, message, percent)

        # Rebuilding the full jobs table on every progress callback is expensive.
        # Throttle refresh frequency to keep UI responsive.
        now = time.monotonic()
        if (now - self._last_jobs_refresh_ts) >= 1.0:
            self._refresh_jobs(select_job_id=job_id, resize_columns=False)

    def _on_worker_finished(self, job_id: str, final_status: str) -> None:
        if self._queue_machine.snapshot().active_job_id == job_id:
            if final_status == JobStatus.CANCELLED.value:
                self.processing_panel.mark_cancelled()
            else:
                self.processing_panel.mark_finished()

        self._active_workers.pop(job_id, None)
        try:
            self._queue_machine.finish_active_job(job_id)
        except InvalidQueueTransition:
            self._queue_machine.clear_active_job()

        self._refresh_jobs(select_job_id=job_id)

        job = self._jobs_cache_by_id.get(job_id)
        if job and job.status in {JobStatus.COMPLETED, JobStatus.PARTIAL_SUCCESS, JobStatus.READY_FOR_REVIEW}:
            self._open_review(job_id)

        started_next = self._start_next_queued_job()
        if not started_next and not self._active_workers:
            self._finish_processing_image_cycle(success=final_status in _SUCCESS_FINAL_STATUSES)

        self._update_queue_buttons()

    def _on_worker_failed(self, job_id: str, error: str) -> None:
        if self._queue_machine.snapshot().active_job_id == job_id:
            self.processing_panel.mark_failed(error)

        self._active_workers.pop(job_id, None)
        try:
            self._queue_machine.finish_active_job(job_id)
        except InvalidQueueTransition:
            self._queue_machine.clear_active_job()

        self._refresh_jobs(select_job_id=job_id)

        started_next = self._start_next_queued_job()
        if not started_next and not self._active_workers:
            self._finish_processing_image_cycle(success=False)

        self._update_queue_buttons()

    def _on_cancel_requested(self, job_id: str) -> None:
        worker = self._active_workers.get(job_id)
        if worker is not None:
            worker.cancel()

    def _open_review(self, job_id: str) -> None:
        existing = self._review_windows.get(job_id)
        if existing is not None:
            if existing.isMinimized():
                existing.showNormal()
            else:
                existing.show()
            existing.raise_()
            existing.activateWindow()
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

    def _refresh_jobs(self, select_job_id: str | None = None, *, resize_columns: bool = False) -> None:
        jobs = self._container.list_jobs_use_case.execute(limit=500)
        self._last_jobs_refresh_ts = time.monotonic()
        self._jobs_cache_by_id = {job.job_id: job for job in jobs}
        self._jobs_cache_queued_ids = {job.job_id for job in jobs if job.status == JobStatus.QUEUED}

        queued_jobs_fifo = sorted(
            [job for job in jobs if job.status == JobStatus.QUEUED],
            key=lambda item: item.created_at,
        )
        queued_total = len(queued_jobs_fifo)
        queued_positions = {job.job_id: index + 1 for index, job in enumerate(queued_jobs_fifo)}

        self.jobs_table.setRowCount(len(jobs))
        project_name_cache: dict[str, str] = {}

        for row_idx, job in enumerate(jobs):
            row = JobRowMapper.map(job)

            project_name = project_name_cache.get(row.project_id)
            if project_name is None:
                project = self._container.project_repository.get_by_id(row.project_id)
                project_name = project.name if project is not None else row.project_id
                project_name_cache[row.project_id] = project_name

            status_text = row.status
            if job.status == JobStatus.QUEUED:
                position = queued_positions.get(row.job_id, 1)
                status_key = "main.queue_status_paused" if self._queue_machine.snapshot().paused else "main.queue_status"
                status_text = self._tr.t(status_key, position=position, total=queued_total)

            self._set_cell(row_idx, 0, project_name)
            self._set_cell(row_idx, 1, row.job_id)
            self._set_cell(row_idx, 2, row.project_id)
            self._set_cell(row_idx, 3, status_text)
            self._set_cell(row_idx, 4, row.created_at)
            self._set_cell(row_idx, 5, row.completed_at)
            self._set_cell(row_idx, 6, row.source_path)

            if select_job_id and row.job_id == select_job_id:
                self.jobs_table.selectRow(row_idx)

        row_count_changed = self._last_jobs_resize_rows != len(jobs)
        if resize_columns or row_count_changed:
            self.jobs_table.resizeColumnsToContents()
            self._last_jobs_resize_rows = len(jobs)

    def _selected_job_id(self) -> str | None:
        selection_model = self.jobs_table.selectionModel()
        if selection_model is None:
            return None

        selected_rows = selection_model.selectedRows()
        if not selected_rows:
            return None

        selected_row_idx = selected_rows[0].row()
        job_item = self.jobs_table.item(selected_row_idx, 1)
        if job_item is None:
            return None
        return job_item.text()

    @staticmethod
    def _compact_log_text(raw: str | None) -> str:
        if not raw:
            return "-"

        normalized = " ".join(raw.split())
        return normalized if normalized else "-"

    @staticmethod
    def _format_csv_values(values: list[str]) -> str:
        cleaned = [item.strip() for item in values if item and item.strip()]
        return ", ".join(cleaned) if cleaned else "-"

    def _resolve_job_display_name(self, job: Job | None, fallback: str = "-") -> str:
        if job is None:
            return fallback

        project = self._container.project_repository.get_by_id(job.project_id)
        if project is not None and project.name.strip():
            return project.name.strip()

        project_id = (job.project_id or "").strip()
        return project_id or fallback

    def _build_processing_log_header(self, job: Job | None, hints: JobContextHints | None) -> list[str]:
        if job is None:
            return []

        speaker_mode = (job.speaker_count_mode or "auto").strip() or "auto"
        exact = str(job.exact_speakers) if job.exact_speakers is not None else "-"
        min_speakers = str(job.min_speakers) if job.min_speakers is not None else "-"
        max_speakers = str(job.max_speakers) if job.max_speakers is not None else "-"

        hints_enabled = hints is not None
        domain_context = self._compact_log_text(hints.domain_context) if hints is not None else "-"
        hotwords = self._format_csv_values(hints.hotwords) if hints is not None else "-"
        glossary = self._format_csv_values(hints.glossary_terms) if hints is not None else "-"
        participants = self._format_csv_values(hints.expected_participants) if hints is not None else "-"
        acronyms = self._format_csv_values(hints.expected_acronyms) if hints is not None else "-"
        entities = self._format_csv_values(hints.expected_entities) if hints is not None else "-"

        return [
            "JOB_CONFIG: ----------------",
            f"JOB_CONFIG: {self._tr.t('new_job.language')} = {(job.language_selected or 'auto')}",
            f"JOB_CONFIG: {self._tr.t('new_job.asr_model')} = {(job.model_name or '-')}",
            f"JOB_CONFIG: {self._tr.t('new_job.device')} = {(job.device_used or '-')}",
            f"JOB_CONFIG: {self._tr.t('new_job.compute')} = {(job.compute_type or '-')}",
            f"JOB_CONFIG: {self._tr.t('new_job.mode')} = {speaker_mode}",
            f"JOB_CONFIG: {self._tr.t('new_job.exact')} = {exact}",
            f"JOB_CONFIG: {self._tr.t('new_job.min')} = {min_speakers}",
            f"JOB_CONFIG: {self._tr.t('new_job.max')} = {max_speakers}",
            f"JOB_CONFIG: {self._tr.t('new_job.hints_toggle')} = {'on' if hints_enabled else 'off'}",
            f"JOB_CONFIG: {self._tr.t('new_job.domain_context')} = {domain_context}",
            f"JOB_CONFIG: {self._tr.t('new_job.hotwords')} = {hotwords}",
            f"JOB_CONFIG: {self._tr.t('new_job.glossary')} = {glossary}",
            f"JOB_CONFIG: {self._tr.t('new_job.participants')} = {participants}",
            f"JOB_CONFIG: {self._tr.t('new_job.acronyms')} = {acronyms}",
            f"JOB_CONFIG: {self._tr.t('new_job.entities')} = {entities}",
            "JOB_CONFIG: ----------------",
        ]

    def _set_cell(self, row: int, col: int, value: str) -> None:
        item = QTableWidgetItem(value)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.jobs_table.setItem(row, col, item)
