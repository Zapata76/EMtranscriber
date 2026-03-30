from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pytest

from emtranscriber.application.services.transcription_orchestrator import TranscriptionOrchestrator
from emtranscriber.domain.entities.job import Job
from emtranscriber.domain.pipeline.asr_types import AsrResult
from emtranscriber.domain.value_objects.job_status import JobStatus


class FakeJobRepository:
    def __init__(self, job: Job) -> None:
        self.job = job
        self.last_status: JobStatus | None = None
        self.last_error: str | None = None
        self.completed = False
        self.execution_duration_seconds: int | None = None

    def get_by_id(self, job_id: str) -> Job | None:
        return self.job if job_id == self.job.job_id else None

    def update_working_audio_path(self, job_id: str, working_audio_path: str) -> None:
        self.job.working_audio_path = working_audio_path

    def get_context_hints(self, job_id: str):
        return None

    def update_status(
        self,
        job_id: str,
        status: JobStatus,
        *,
        language_detected: str | None = None,
        error_message: str | None = None,
        completed: bool = False,
        execution_duration_seconds: int | None = None,
    ) -> None:
        self.last_status = status
        self.last_error = error_message
        self.completed = completed
        self.execution_duration_seconds = execution_duration_seconds
        self.job.execution_duration_seconds = execution_duration_seconds
        if language_detected:
            self.job.language_detected = language_detected


class FakeTranscriptRepository:
    def replace_transcript(self, job_id: str, segments, speakers) -> None:
        return None


class FakeArtifactStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def ensure_job_directories(
        self,
        project_id: str,
        job_id: str,
        artifacts_root_path: str | None = None,
        *,
        source_file_path: str | None = None,
        created_at=None,
    ) -> dict[str, Path]:
        base = self.root / project_id / job_id
        paths = {
            "source": base / "source",
            "working": base / "working",
            "raw": base / "raw",
            "merged": base / "merged",
            "exports": base / "exports",
        }
        for path in paths.values():
            path.mkdir(parents=True, exist_ok=True)
        return paths

    def save_json(self, path: Path, payload) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")

    def save_text(self, path: Path, payload: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding="utf-8")


class FakeAudioNormalizer:
    def normalize(self, source_path: Path, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(source_path.read_bytes())
        return output_path


class FailingAsrService:
    def transcribe(self, *args, **kwargs):
        raise RuntimeError("boom asr")


class AsrShouldNotRunService:
    def __init__(self) -> None:
        self.called = False

    def transcribe(self, *args, **kwargs):
        self.called = True
        raise AssertionError("ASR should not be called after explicit cancellation")


class CancellableAsrService:
    def __init__(self) -> None:
        self.progress_calls = 0

    def transcribe(self, *args, **kwargs):
        on_progress = kwargs.get("on_progress")
        if on_progress is not None:
            on_progress("phase-1", 0.2)
            self.progress_calls += 1
            # This call should raise as soon as the orchestrator has registered cancellation.
            on_progress("phase-2", 0.3)
            self.progress_calls += 1

        return AsrResult(language="en", duration_s=1.0, segments=[]), {"engine": "faster-whisper"}


class DummyDiarizationService:
    def diarize(self, *args, **kwargs):
        raise AssertionError("diarization should not run in these tests")


@dataclass(slots=True)
class DummyTranscript:
    segments: list
    speakers: list


class DummyAligner:
    def align(self, *args, **kwargs) -> DummyTranscript:
        return DummyTranscript(segments=[], speakers=[])


class DummyExporter:
    def build_json(self, *args, **kwargs):
        return {}

    def build_markdown(self, *args, **kwargs) -> str:
        return ""

    def build_txt(self, *args, **kwargs) -> str:
        return ""

    def build_srt(self, *args, **kwargs) -> str:
        return ""


def _build_job(tmp_path: Path) -> Job:
    source_path = tmp_path / "source.wav"
    source_path.write_bytes(b"RIFF")
    return Job(
        job_id="job-1",
        project_id="proj-1",
        source_file_path=str(source_path),
        status=JobStatus.CREATED,
        created_at=datetime.now(),
        language_selected="auto",
        model_name="small",
        device_used="cpu",
        compute_type="int8",
    )


def _build_orchestrator(tmp_path: Path, asr_service) -> tuple[TranscriptionOrchestrator, FakeJobRepository]:
    job = _build_job(tmp_path)
    repo = FakeJobRepository(job)
    orchestrator = TranscriptionOrchestrator(
        job_repository=repo,
        transcript_repository=FakeTranscriptRepository(),
        artifact_store=FakeArtifactStore(tmp_path / "artifacts"),
        audio_normalizer=FakeAudioNormalizer(),
        asr_service=asr_service,
        diarization_service=DummyDiarizationService(),
        aligner=DummyAligner(),
        exporter=DummyExporter(),
        logger=logging.getLogger("test"),
    )
    return orchestrator, repo


def test_runtime_error_is_failed_not_cancelled(tmp_path: Path) -> None:
    orchestrator, repo = _build_orchestrator(tmp_path, FailingAsrService())

    with pytest.raises(RuntimeError, match="boom asr"):
        orchestrator.process_job("job-1")

    assert repo.last_status == JobStatus.FAILED
    assert repo.last_error == "boom asr"
    assert repo.completed is True
    assert repo.execution_duration_seconds is not None


def test_explicit_cancel_is_reported_as_cancelled(tmp_path: Path) -> None:
    asr = AsrShouldNotRunService()
    orchestrator, repo = _build_orchestrator(tmp_path, asr)

    orchestrator.cancel("job-1")
    result = orchestrator.process_job("job-1")

    assert result == JobStatus.CANCELLED
    assert repo.last_status == JobStatus.CANCELLED
    assert repo.execution_duration_seconds is not None
    assert asr.called is False


def test_cancel_during_asr_progress_is_honored(tmp_path: Path) -> None:
    asr = CancellableAsrService()
    orchestrator, repo = _build_orchestrator(tmp_path, asr)

    def on_progress(status: JobStatus, message: str, _percent: int) -> None:
        if status == JobStatus.TRANSCRIBING and "phase-1" in message:
            orchestrator.cancel("job-1")

    result = orchestrator.process_job("job-1", on_progress=on_progress)

    assert result == JobStatus.CANCELLED
    assert repo.last_status == JobStatus.CANCELLED
    assert repo.execution_duration_seconds is not None
    assert asr.progress_calls == 1
