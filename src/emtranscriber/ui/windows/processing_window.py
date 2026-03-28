from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QProgressBar, QTextEdit, QVBoxLayout, QWidget

from emtranscriber.shared.i18n import UiTranslator


class ProcessingWindow(QDialog):
    cancel_requested = Signal(str)

    def __init__(self, job_id: str, translator: UiTranslator, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._job_id = job_id
        self._tr = translator
        self._started_at = datetime.now()
        self._last_progress_at = self._started_at
        self._last_heartbeat_log_at = self._started_at

        self.setWindowTitle(self._tr.t("processing.title", job=job_id[:8]))
        self.resize(600, 360)

        root = QVBoxLayout(self)

        self.stage_label = QLabel(self._tr.t("processing.waiting"))
        root.addWidget(self.stage_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        root.addWidget(self.progress_bar)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        root.addWidget(self.log_view)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.cancel_button = QPushButton(self._tr.t("processing.cancel"))
        self.cancel_button.clicked.connect(self._on_cancel)
        button_row.addWidget(self.cancel_button)
        root.addLayout(button_row)

        self._heartbeat_timer = QTimer(self)
        self._heartbeat_timer.setInterval(5000)
        self._heartbeat_timer.timeout.connect(self._on_heartbeat_tick)
        self._heartbeat_timer.start()

    def _on_cancel(self) -> None:
        self.cancel_button.setEnabled(False)
        self.append_log(self._tr.t("processing.cancel_req"))
        self.cancel_requested.emit(self._job_id)

    def update_progress(self, status: str, message: str, percent: int) -> None:
        self._last_progress_at = datetime.now()
        self.stage_label.setText(f"{status}: {message}")
        self.progress_bar.setValue(percent)
        self.append_log(f"{status}: {message}")

    def mark_finished(self) -> None:
        self._heartbeat_timer.stop()
        self.progress_bar.setValue(100)
        self.cancel_button.setEnabled(False)
        self.append_log(self._tr.t("processing.finished"))

    def mark_cancelled(self) -> None:
        self._heartbeat_timer.stop()
        self.progress_bar.setValue(100)
        self.cancel_button.setEnabled(False)
        self.append_log(self._tr.t("processing.cancelled"))

    def mark_failed(self, error: str) -> None:
        self._heartbeat_timer.stop()
        self.cancel_button.setEnabled(False)
        self.append_log(self._tr.t("processing.failed", error=error))

    def append_log(self, text: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_view.append(f"[{timestamp}] {text}")

    def _on_heartbeat_tick(self) -> None:
        if self.progress_bar.value() >= 100:
            return

        now = datetime.now()
        idle_seconds = int((now - self._last_progress_at).total_seconds())
        heartbeat_gap = int((now - self._last_heartbeat_log_at).total_seconds())

        if idle_seconds < 20 or heartbeat_gap < 20:
            return

        elapsed_seconds = int((now - self._started_at).total_seconds())
        self._last_heartbeat_log_at = now
        self.append_log(
            self._tr.t(
                "processing.heartbeat",
                elapsed=self._format_seconds(elapsed_seconds),
                idle=idle_seconds,
            )
        )

    @staticmethod
    def _format_seconds(total_seconds: int) -> str:
        minutes, seconds = divmod(max(0, int(total_seconds)), 60)
        hours, minutes = divmod(minutes, 60)
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"
