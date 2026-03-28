from __future__ import annotations

from emtranscriber.domain.entities.transcript_document import TranscriptDocument
from emtranscriber.infrastructure.persistence.transcript_repository import TranscriptRepository


class GetTranscriptDocumentUseCase:
    def __init__(self, transcript_repository: TranscriptRepository) -> None:
        self._transcript_repository = transcript_repository

    def execute(self, job_id: str) -> TranscriptDocument:
        return self._transcript_repository.load_document(job_id)
