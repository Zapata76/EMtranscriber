from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class AnalysisRequest:
    transcript_markdown: str
    transcript_json: dict
    speaker_map: dict[str, str]
    job_metadata: dict
    analysis_prompt: str
    analysis_template: str | None = None
    output_language: str | None = None


@dataclass(slots=True)
class AnalysisResult:
    provider_name: str
    analysis_text: str
    model_identifier: str | None = None
    raw_response: dict | None = None
    created_at: datetime = field(default_factory=utc_now)
