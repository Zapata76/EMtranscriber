from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from emtranscriber.domain.entities.job import Job


@dataclass(slots=True)
class JobRow:
    job_id: str
    project_id: str
    source_path: str
    status: str
    created_at: str
    completed_at: str


class JobRowMapper:
    @staticmethod
    def map(job: Job) -> JobRow:
        return JobRow(
            job_id=job.job_id,
            project_id=job.project_id,
            source_path=job.source_file_path,
            status=job.status.value,
            created_at=JobRowMapper._fmt_dt(job.created_at),
            completed_at=JobRowMapper._fmt_dt(job.completed_at),
        )

    @staticmethod
    def _fmt_dt(value: datetime | None) -> str:
        if value is None:
            return ""
        return value.astimezone().strftime("%Y-%m-%d %H:%M:%S")
