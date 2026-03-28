from __future__ import annotations

from collections.abc import Callable

from emtranscriber.application.dto.analysis_request_options import AnalysisRequestOptions
from emtranscriber.application.dto.analysis_run_result import AnalysisRunResult
from emtranscriber.domain.analysis import AnalysisRequest
from emtranscriber.domain.exports.transcript_exporter import TranscriptExporter
from emtranscriber.infrastructure.ai_analysis.analysis_provider import AnalysisProvider
from emtranscriber.infrastructure.ai_analysis.templates import (
    merge_prompt,
    normalize_output_language,
    normalize_template_key,
    serialize_speaker_map,
    resolve_template_instruction,
)
from emtranscriber.infrastructure.persistence.artifact_store import JobArtifactStore
from emtranscriber.infrastructure.persistence.job_repository import JobRepository
from emtranscriber.infrastructure.persistence.transcript_repository import TranscriptRepository


class AnalyzeTranscriptUseCase:
    def __init__(
        self,
        job_repository: JobRepository,
        transcript_repository: TranscriptRepository,
        artifact_store: JobArtifactStore,
        exporter: TranscriptExporter,
        provider_factory: Callable[[], AnalysisProvider],
    ) -> None:
        self._job_repository = job_repository
        self._transcript_repository = transcript_repository
        self._artifact_store = artifact_store
        self._exporter = exporter
        self._provider_factory = provider_factory

    def execute(self, job_id: str, options: AnalysisRequestOptions | None = None) -> AnalysisRunResult:
        opts = options or AnalysisRequestOptions()

        job = self._job_repository.get_by_id(job_id)
        if job is None:
            raise ValueError(f"Job not found: {job_id}")

        document = self._transcript_repository.load_document(job_id)
        directories = self._artifact_store.ensure_job_directories(job.project_id, job.job_id, job.artifacts_root_path)

        transcript_markdown = self._exporter.build_markdown(job, document)
        transcript_json = self._exporter.build_json(job, document)

        template_key = normalize_template_key(opts.analysis_template)
        prompt = merge_prompt(resolve_template_instruction(template_key), opts.analysis_prompt)

        speaker_map = serialize_speaker_map((speaker.speaker_key, speaker.resolved_name) for speaker in document.speakers)
        analysis_request = AnalysisRequest(
            transcript_markdown=transcript_markdown,
            transcript_json=transcript_json,
            speaker_map=speaker_map,
            job_metadata={
                "job_id": job.job_id,
                "project_id": job.project_id,
                "source_file_path": job.source_file_path,
                "language_detected": job.language_detected,
                "language_selected": job.language_selected,
                "model_name": job.model_name,
                "created_at": job.created_at.isoformat(),
                "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            },
            analysis_prompt=prompt,
            analysis_template=template_key,
            output_language=normalize_output_language(opts.output_language),
        )

        provider = self._provider_factory()
        analysis_result = provider.analyze_transcript(analysis_request)

        request_json_path = directories["analysis"] / "analysis_request.json"
        response_json_path = directories["analysis"] / "analysis_response.json"
        output_markdown_path = directories["analysis"] / "analysis_output.md"

        self._artifact_store.save_json(request_json_path, self._serialize_request(analysis_request))
        self._artifact_store.save_json(response_json_path, self._serialize_response(analysis_result))
        self._artifact_store.save_text(output_markdown_path, analysis_result.analysis_text.strip() + "\n")

        return AnalysisRunResult(
            provider_name=analysis_result.provider_name,
            model_identifier=analysis_result.model_identifier,
            output_text=analysis_result.analysis_text,
            request_json_path=request_json_path,
            response_json_path=response_json_path,
            output_markdown_path=output_markdown_path,
        )

    @staticmethod
    def _serialize_request(payload: AnalysisRequest) -> dict:
        return {
            "analysis_template": payload.analysis_template,
            "analysis_prompt": payload.analysis_prompt,
            "output_language": payload.output_language,
            "speaker_map": payload.speaker_map,
            "job_metadata": payload.job_metadata,
            "transcript_markdown": payload.transcript_markdown,
            "transcript_json": payload.transcript_json,
        }

    @staticmethod
    def _serialize_response(result) -> dict:
        return {
            "provider_name": result.provider_name,
            "model_identifier": result.model_identifier,
            "created_at": result.created_at.isoformat(),
            "analysis_text": result.analysis_text,
            "raw_response": result.raw_response,
        }

