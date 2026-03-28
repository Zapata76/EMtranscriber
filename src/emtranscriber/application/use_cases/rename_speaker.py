from __future__ import annotations

from emtranscriber.infrastructure.persistence.transcript_repository import TranscriptRepository


class RenameSpeakerUseCase:
    def __init__(self, transcript_repository: TranscriptRepository) -> None:
        self._transcript_repository = transcript_repository

    def execute(self, job_id: str, speaker_key: str, display_name: str) -> None:
        self._transcript_repository.rename_speaker(job_id, speaker_key, display_name)
