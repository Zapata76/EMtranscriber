from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, Signal

from emtranscriber.application.dto.analysis_request_options import AnalysisRequestOptions
from emtranscriber.application.use_cases.analyze_transcript import AnalyzeTranscriptUseCase


class AnalysisWorkerSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)


class AnalysisWorker(QRunnable):
    def __init__(
        self,
        use_case: AnalyzeTranscriptUseCase,
        job_id: str,
        options: AnalysisRequestOptions,
    ) -> None:
        super().__init__()
        self._use_case = use_case
        self._job_id = job_id
        self._options = options
        self.signals = AnalysisWorkerSignals()

    def run(self) -> None:
        try:
            result = self._use_case.execute(self._job_id, self._options)
            self.signals.finished.emit(result)
        except Exception as exc:  # noqa: BLE001
            self.signals.failed.emit(str(exc))
