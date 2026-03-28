from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, Signal

from emtranscriber.application.services.transcription_orchestrator import TranscriptionOrchestrator


class JobProcessingSignals(QObject):
    progress = Signal(str, str, int)
    finished = Signal(str, str)
    failed = Signal(str, str)


class JobProcessingWorker(QRunnable):
    def __init__(self, orchestrator: TranscriptionOrchestrator, job_id: str) -> None:
        super().__init__()
        self._orchestrator = orchestrator
        self._job_id = job_id
        self.signals = JobProcessingSignals()

    def run(self) -> None:
        try:
            final_status = self._orchestrator.process_job(self._job_id, self._on_progress)
            self.signals.finished.emit(self._job_id, final_status.value)
        except Exception as exc:  # noqa: BLE001
            self.signals.failed.emit(self._job_id, str(exc))

    def cancel(self) -> None:
        self._orchestrator.cancel(self._job_id)

    def _on_progress(self, status, message: str, percent: int) -> None:
        self.signals.progress.emit(status.value, message, percent)
