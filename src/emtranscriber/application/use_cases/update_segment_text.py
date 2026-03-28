from __future__ import annotations

from emtranscriber.infrastructure.persistence.transcript_repository import TranscriptRepository


class UpdateSegmentTextUseCase:
    def __init__(self, transcript_repository: TranscriptRepository) -> None:
        self._transcript_repository = transcript_repository

    def execute(self, segment_id: str, text: str) -> None:
        self._transcript_repository.update_segment_text(segment_id, text)
