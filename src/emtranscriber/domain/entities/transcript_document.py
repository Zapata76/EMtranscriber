from __future__ import annotations

from dataclasses import dataclass, field

from emtranscriber.domain.entities.speaker import Speaker
from emtranscriber.domain.entities.transcript_segment import TranscriptSegment


@dataclass(slots=True)
class TranscriptDocument:
    job_id: str
    segments: list[TranscriptSegment] = field(default_factory=list)
    speakers: list[Speaker] = field(default_factory=list)
