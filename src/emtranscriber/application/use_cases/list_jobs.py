from __future__ import annotations

from emtranscriber.domain.entities.job import Job
from emtranscriber.infrastructure.persistence.job_repository import JobRepository


class ListJobsUseCase:
    def __init__(self, job_repository: JobRepository) -> None:
        self._job_repository = job_repository

    def execute(self, limit: int = 200) -> list[Job]:
        return self._job_repository.list_recent(limit=limit)

