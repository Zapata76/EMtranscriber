from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class AsrWord:
    text: str
    start_s: float
    end_s: float
    probability: float | None = None


@dataclass(slots=True)
class AsrSegment:
    text: str
    start_s: float
    end_s: float
    words: list[AsrWord] = field(default_factory=list)
    avg_logprob: float | None = None


@dataclass(slots=True)
class AsrResult:
    language: str | None
    duration_s: float | None
    segments: list[AsrSegment]
