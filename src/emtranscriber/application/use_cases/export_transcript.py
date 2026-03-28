from __future__ import annotations

from pathlib import Path

from emtranscriber.domain.exports.transcript_exporter import TranscriptExporter
from emtranscriber.infrastructure.persistence.artifact_store import JobArtifactStore
from emtranscriber.infrastructure.persistence.job_repository import JobRepository
from emtranscriber.infrastructure.persistence.transcript_repository import TranscriptRepository


class ExportTranscriptUseCase:
    def __init__(
        self,
        job_repository: JobRepository,
        transcript_repository: TranscriptRepository,
        artifact_store: JobArtifactStore,
        exporter: TranscriptExporter,
    ) -> None:
        self._job_repository = job_repository
        self._transcript_repository = transcript_repository
        self._artifact_store = artifact_store
        self._exporter = exporter

    def execute(self, job_id: str) -> dict[str, Path]:
        job = self._job_repository.get_by_id(job_id)
        if job is None:
            raise ValueError(f"Job not found: {job_id}")

        document = self._transcript_repository.load_document(job_id)
        directories = self._artifact_store.ensure_job_directories(job.project_id, job.job_id, job.artifacts_root_path)

        json_payload = self._exporter.build_json(job, document)
        md_path = directories["exports"] / "transcript.md"
        txt_path = directories["exports"] / "transcript.txt"
        json_path = directories["exports"] / "transcript.json"
        srt_path = directories["exports"] / "transcript.srt"

        self._artifact_store.save_text(md_path, self._exporter.build_markdown(job, document))
        self._artifact_store.save_text(txt_path, self._exporter.build_txt(document))
        self._artifact_store.save_json(json_path, json_payload)
        self._artifact_store.save_text(srt_path, self._exporter.build_srt(document))

        return {
            "md": md_path,
            "txt": txt_path,
            "json": json_path,
            "srt": srt_path,
        }

