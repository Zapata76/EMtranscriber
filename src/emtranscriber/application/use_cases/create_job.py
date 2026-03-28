from __future__ import annotations

from pathlib import Path

from emtranscriber.application.dto.new_job_request import NewJobRequest
from emtranscriber.domain.entities.job import Job
from emtranscriber.infrastructure.persistence.job_repository import JobRepository
from emtranscriber.infrastructure.persistence.project_repository import ProjectRepository


class CreateJobUseCase:
    def __init__(self, project_repository: ProjectRepository, job_repository: JobRepository) -> None:
        self._project_repository = project_repository
        self._job_repository = job_repository

    def execute(self, request: NewJobRequest) -> Job:
        source_path = Path(request.source_file_path)
        if not source_path.exists() or not source_path.is_file():
            raise FileNotFoundError(f"Source file not found: {request.source_file_path}")

        resolved_source = source_path.resolve()
        output_root = Path(request.artifacts_root_path).expanduser() if request.artifacts_root_path else resolved_source.parent
        if output_root.exists() and not output_root.is_dir():
            raise ValueError(f"Output path is not a directory: {output_root}")

        try:
            output_root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise OSError(f"Unable to create output directory: {output_root}") from exc

        request.artifacts_root_path = str(output_root.resolve())

        project = self._project_repository.get_or_create(request.project_name)
        job = self._job_repository.create(project.project_id, request)
        self._job_repository.save_context_hints(job.job_id, request.context_hints)
        return job
