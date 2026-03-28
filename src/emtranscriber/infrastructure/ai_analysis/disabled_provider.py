from __future__ import annotations

from emtranscriber.domain.analysis import AnalysisRequest, AnalysisResult


class DisabledAnalysisProvider:
    provider_name = "disabled"

    def __init__(self, reason: str | None = None) -> None:
        self._reason = reason or "AI analysis is disabled in Settings."

    def analyze_transcript(self, request: AnalysisRequest) -> AnalysisResult:  # noqa: ARG002
        raise RuntimeError(self._reason)
