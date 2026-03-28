from __future__ import annotations

import logging
import shutil
from collections.abc import Callable
from pathlib import Path

from emtranscriber.domain.exports.transcript_exporter import TranscriptExporter
from emtranscriber.domain.pipeline.hint_builder import build_hint_text
from emtranscriber.domain.value_objects.job_status import JobStatus
from emtranscriber.infrastructure.persistence.artifact_store import JobArtifactStore
from emtranscriber.infrastructure.persistence.job_repository import JobRepository
from emtranscriber.infrastructure.persistence.transcript_repository import TranscriptRepository


ProgressCallback = Callable[[JobStatus, str, int], None]
StageDetailCallback = Callable[[str, float | None], None]


class JobCancelledError(RuntimeError):
    """Raised when a running job is explicitly cancelled by user action."""


class TranscriptionOrchestrator:
    def __init__(
        self,
        job_repository: JobRepository,
        transcript_repository: TranscriptRepository,
        artifact_store: JobArtifactStore,
        audio_normalizer,
        asr_service,
        diarization_service,
        aligner,
        exporter: TranscriptExporter,
        logger: logging.Logger,
    ) -> None:
        self._job_repository = job_repository
        self._transcript_repository = transcript_repository
        self._artifact_store = artifact_store
        self._audio_normalizer = audio_normalizer
        self._asr_service = asr_service
        self._diarization_service = diarization_service
        self._aligner = aligner
        self._exporter = exporter
        self._logger = logger
        self._cancelled_jobs: set[str] = set()

    def cancel(self, job_id: str) -> None:
        self._cancelled_jobs.add(job_id)
        self._logger.info("Cancellation requested for job %s", job_id)

    def process_job(self, job_id: str, on_progress: ProgressCallback | None = None) -> JobStatus:
        job = self._job_repository.get_by_id(job_id)
        if job is None:
            raise ValueError(f"Job not found: {job_id}")

        diarization_error: Exception | None = None
        using_stub_pipeline = False

        try:
            self._guard_not_cancelled(job_id)
            directories = self._artifact_store.ensure_job_directories(job.project_id, job.job_id, job.artifacts_root_path)

            self._update(job_id, JobStatus.PREPARING_AUDIO, on_progress, "Preparing media", 10)
            source_path = Path(job.source_file_path)
            staged_source = directories["source"] / source_path.name
            if not staged_source.exists():
                shutil.copy2(source_path, staged_source)

            self._update(job_id, JobStatus.PREPARING_AUDIO, on_progress, "Normalizing audio", 18)
            working_audio = directories["working"] / "working_audio.wav"
            normalized_audio = self._audio_normalizer.normalize(staged_source, working_audio)
            self._job_repository.update_working_audio_path(job_id, str(normalized_audio))
            self._guard_not_cancelled(job_id)

            hints = self._job_repository.get_context_hints(job_id)
            hint_text = build_hint_text(hints)
            hotwords = hints.hotwords if hints is not None else []

            self._update(job_id, JobStatus.TRANSCRIBING, on_progress, "Running faster-whisper", 35)
            asr_progress = self._build_stage_progress_callback(
                job_id=job_id,
                status=JobStatus.TRANSCRIBING,
                on_progress=on_progress,
                start_percent=35,
                end_percent=59,
            )
            asr_result, asr_raw = self._asr_service.transcribe(
                job,
                normalized_audio,
                hint_text=hint_text,
                hotwords=hotwords,
                on_progress=asr_progress,
            )
            using_stub_pipeline = str(asr_raw.get("engine", "")).endswith("-stub")
            self._artifact_store.save_json(directories["raw"] / "asr_output.json", asr_raw)
            self._job_repository.update_status(
                job_id,
                JobStatus.TRANSCRIBING,
                language_detected=asr_result.language,
            )
            self._guard_not_cancelled(job_id)

            diarization_result = None
            self._update(job_id, JobStatus.DIARIZING, on_progress, "Running pyannote diarization", 60)
            diarization_progress = self._build_stage_progress_callback(
                job_id=job_id,
                status=JobStatus.DIARIZING,
                on_progress=on_progress,
                start_percent=60,
                end_percent=77,
            )
            try:
                diarization_result, diarization_raw = self._diarization_service.diarize(
                    job,
                    normalized_audio,
                    on_progress=diarization_progress,
                )
                using_stub_pipeline = using_stub_pipeline or str(diarization_raw.get("engine", "")).endswith("-stub")
                self._artifact_store.save_json(directories["raw"] / "diarization_output.json", diarization_raw)
            except Exception as exc:  # noqa: BLE001
                diarization_error = exc
                self._logger.exception("Diarization failed for job %s", job_id)
                self._notify_progress(
                    on_progress,
                    JobStatus.DIARIZING,
                    f"Diarization failed: {exc}",
                    77,
                )

            self._guard_not_cancelled(job_id)
            self._update(job_id, JobStatus.ALIGNING, on_progress, "Aligning transcript with speakers", 78)
            transcript_doc = self._aligner.align(job_id, asr_result, diarization_result)

            self._guard_not_cancelled(job_id)
            self._transcript_repository.replace_transcript(job_id, transcript_doc.segments, transcript_doc.speakers)

            export_payload = self._exporter.build_json(job, transcript_doc)
            self._artifact_store.save_json(directories["merged"] / "transcript.json", export_payload)

            self._guard_not_cancelled(job_id)
            self._update(job_id, JobStatus.READY_FOR_REVIEW, on_progress, "Preparing exports", 90)
            self._artifact_store.save_text(
                directories["exports"] / "transcript.md",
                self._exporter.build_markdown(job, transcript_doc),
            )
            self._guard_not_cancelled(job_id)
            self._artifact_store.save_text(
                directories["exports"] / "transcript.txt",
                self._exporter.build_txt(transcript_doc),
            )
            self._guard_not_cancelled(job_id)
            self._artifact_store.save_json(directories["exports"] / "transcript.json", export_payload)
            self._guard_not_cancelled(job_id)
            self._artifact_store.save_text(
                directories["exports"] / "transcript.srt",
                self._exporter.build_srt(transcript_doc),
            )
            self._guard_not_cancelled(job_id)

            if using_stub_pipeline:
                self._job_repository.update_status(
                    job_id,
                    JobStatus.PARTIAL_SUCCESS,
                    error_message="Stub pipeline active: output is demo-only and not a real transcription.",
                    completed=True,
                )
                self._notify_progress(on_progress, JobStatus.PARTIAL_SUCCESS, "Completed in demo mode (stub pipeline)", 100)
                self._logger.warning("Job completed in stub mode: %s", job_id)
                return JobStatus.PARTIAL_SUCCESS

            if diarization_error is None:
                self._job_repository.update_status(job_id, JobStatus.COMPLETED, completed=True)
                self._notify_progress(on_progress, JobStatus.COMPLETED, "Completed", 100)
                self._logger.info("Job completed: %s", job_id)
                return JobStatus.COMPLETED

            self._job_repository.update_status(
                job_id,
                JobStatus.PARTIAL_SUCCESS,
                error_message=f"Diarization failed: {diarization_error}",
                completed=True,
            )
            self._notify_progress(on_progress, JobStatus.PARTIAL_SUCCESS, f"Completed without speaker diarization ({diarization_error})", 100)
            self._logger.warning("Job partial success: %s", job_id)
            return JobStatus.PARTIAL_SUCCESS
        except JobCancelledError:
            self._job_repository.update_status(job_id, JobStatus.CANCELLED, completed=True)
            self._notify_progress(on_progress, JobStatus.CANCELLED, "Cancelled by user", 100)
            self._logger.warning("Job cancelled: %s", job_id)
            return JobStatus.CANCELLED
        except Exception as exc:  # noqa: BLE001
            self._job_repository.update_status(
                job_id,
                JobStatus.FAILED,
                error_message=str(exc),
                completed=True,
            )
            self._logger.exception("Job failed: %s", job_id)
            raise
        finally:
            self._cancelled_jobs.discard(job_id)

    def _update(
        self,
        job_id: str,
        status: JobStatus,
        on_progress: ProgressCallback | None,
        message: str,
        progress: int,
    ) -> None:
        self._guard_not_cancelled(job_id)
        self._job_repository.update_status(job_id, status)
        self._notify_progress(on_progress, status, message, progress)

    @staticmethod
    def _notify_progress(
        on_progress: ProgressCallback | None,
        status: JobStatus,
        message: str,
        progress: int,
    ) -> None:
        if on_progress is not None:
            on_progress(status, message, progress)

    def _build_stage_progress_callback(
        self,
        *,
        job_id: str,
        status: JobStatus,
        on_progress: ProgressCallback | None,
        start_percent: int,
        end_percent: int,
    ) -> StageDetailCallback:
        current_percent = start_percent

        def callback(message: str, progress_fraction: float | None = None) -> None:
            nonlocal current_percent

            self._guard_not_cancelled(job_id)

            next_percent = current_percent
            if progress_fraction is not None:
                try:
                    fraction = float(progress_fraction)
                    fraction = min(max(fraction, 0.0), 1.0)
                    mapped = start_percent + int((end_percent - start_percent) * fraction)
                    next_percent = max(current_percent, min(end_percent, mapped))
                except (TypeError, ValueError):
                    next_percent = current_percent
            elif current_percent < (end_percent - 1):
                # Keep the bar moving on heartbeat-only updates to avoid a "stuck" perception.
                next_percent = current_percent + 1

            current_percent = next_percent
            self._notify_progress(on_progress, status, message, current_percent)

        return callback

    def _guard_not_cancelled(self, job_id: str) -> None:
        if job_id in self._cancelled_jobs:
            raise JobCancelledError("Job cancelled")

