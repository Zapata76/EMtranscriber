from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class TranscriptWord:
    word_id: str
    segment_id: str
    start_ms: int
    end_ms: int
    speaker_key: str | None
    text: str
    probability: float | None
    order_index: int
