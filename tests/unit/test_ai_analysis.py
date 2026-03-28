import json
import logging
from datetime import datetime, timezone

import pytest

from emtranscriber.application.dto.analysis_request_options import AnalysisRequestOptions
from emtranscriber.application.use_cases.analyze_transcript import AnalyzeTranscriptUseCase
from emtranscriber.domain.analysis import AnalysisRequest, AnalysisResult
from emtranscriber.domain.entities.job import Job
from emtranscriber.domain.entities.speaker import Speaker
from emtranscriber.domain.entities.transcript_document import TranscriptDocument
from emtranscriber.domain.entities.transcript_segment import TranscriptSegment
from emtranscriber.domain.exports.transcript_exporter import TranscriptExporter
from emtranscriber.domain.value_objects.job_status import JobStatus
from emtranscriber.infrastructure.ai_analysis.provider_factory import build_analysis_provider
from emtranscriber.infrastructure.persistence.artifact_store import JobArtifactStore
from emtranscriber.infrastructure.settings.app_settings import AppSettings


class _FakeJobRepository:
    def __init__(self, job: Job) -> None:
        self._job = job

    def get_by_id(self, job_id: str) -> Job | None:
        if self._job.job_id == job_id:
            return self._job
        return None


class _FakeTranscriptRepository:
    def __init__(self, document: TranscriptDocument) -> None:
        self._document = document

    def load_document(self, job_id: str) -> TranscriptDocument:
        if self._document.job_id != job_id:
            raise ValueError("unexpected job_id")
        return self._document


class _FakeProvider:
    provider_name = "fake"

    def __init__(self) -> None:
        self.last_request: AnalysisRequest | None = None

    def analyze_transcript(self, request: AnalysisRequest) -> AnalysisResult:
        self.last_request = request
        return AnalysisResult(
            provider_name=self.provider_name,
            analysis_text="Concise summary",
            model_identifier="fake-model-v1",
            raw_response={"status": "ok"},
        )


def test_analyze_transcript_use_case_persists_artifacts(tmp_path) -> None:
    job = Job(
        job_id="job-1",
        project_id="project-1",
        source_file_path="meeting.wav",
        status=JobStatus.COMPLETED,
        created_at=datetime.now(timezone.utc),
        language_detected="it",
        model_name="large-v3",
    )

    document = TranscriptDocument(
        job_id="job-1",
        segments=[
            TranscriptSegment(
                segment_id="seg-1",
                job_id="job-1",
                start_ms=0,
                end_ms=1000,
                speaker_key="SPEAKER_00",
                speaker_name_resolved="Paolo",
                text="Ciao a tutti",
                source_type="merged",
                confidence=0.8,
                order_index=0,
                words=[],
            )
        ],
        speakers=[Speaker(speaker_key="SPEAKER_00", display_name="Paolo", is_manually_named=True)],
    )

    provider = _FakeProvider()
    use_case = AnalyzeTranscriptUseCase(
        job_repository=_FakeJobRepository(job),
        transcript_repository=_FakeTranscriptRepository(document),
        artifact_store=JobArtifactStore(tmp_path / "projects"),
        exporter=TranscriptExporter(),
        provider_factory=lambda: provider,
    )

    result = use_case.execute(
        "job-1",
        AnalysisRequestOptions(
            analysis_template="meeting-summary",
            analysis_prompt="Focus on decisions.",
            output_language="Italian",
        ),
    )

    assert result.provider_name == "fake"
    assert result.model_identifier == "fake-model-v1"
    assert result.output_markdown_path.exists()
    assert result.request_json_path.exists()
    assert result.response_json_path.exists()

    request_payload = json.loads(result.request_json_path.read_text(encoding="utf-8"))
    assert request_payload["analysis_template"] == "meeting-summary"
    assert "Focus on decisions." in request_payload["analysis_prompt"]

    response_payload = json.loads(result.response_json_path.read_text(encoding="utf-8"))
    assert response_payload["provider_name"] == "fake"
    assert response_payload["analysis_text"] == "Concise summary"


def test_disabled_provider_raises_runtime_error() -> None:
    settings = AppSettings(ai_analysis_enabled=False)
    provider = build_analysis_provider(settings, logging.getLogger("test"))

    with pytest.raises(RuntimeError):
        provider.analyze_transcript(
            AnalysisRequest(
                transcript_markdown="test",
                transcript_json={},
                speaker_map={},
                job_metadata={},
                analysis_prompt="test",
            )
        )
