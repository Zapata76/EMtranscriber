from __future__ import annotations

from dataclasses import dataclass, field

from emtranscriber.domain.entities.transcript_word import TranscriptWord


@dataclass(slots=True)
class TranscriptSegment:
    segment_id: str
    job_id: str
    start_ms: int
    end_ms: int
    speaker_key: str | None
    speaker_name_resolved: str | None
    text: str
    source_type: str
    confidence: float | None
    order_index: int
    words: list[TranscriptWord] = field(default_factory=list)
