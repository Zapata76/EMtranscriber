from __future__ import annotations

from typing import Protocol

from emtranscriber.domain.analysis import AnalysisRequest, AnalysisResult


class AnalysisProvider(Protocol):
    provider_name: str

    def analyze_transcript(self, request: AnalysisRequest) -> AnalysisResult:
        ...
