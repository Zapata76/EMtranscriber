from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class AnalysisRequestOptions:
    analysis_prompt: str | None = None
    analysis_template: str | None = None
    output_language: str | None = None
