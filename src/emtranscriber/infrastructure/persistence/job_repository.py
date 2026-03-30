from __future__ import annotations

import json
import logging
from pathlib import Path
from uuid import uuid4

from emtranscriber.application.dto.new_job_request import NewJobRequest
from emtranscriber.domain.entities.job import Job
from emtranscriber.domain.entities.job_context_hints import JobContextHints
from emtranscriber.domain.value_objects.job_status import JobStatus
from emtranscriber.infrastructure.persistence.common import from_iso, to_iso, utc_now
from emtranscriber.infrastructure.persistence.sqlite import SQLiteDatabase


_LOGGER = logging.getLogger(__name__)


class JobRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def create(self, project_id: str, request: NewJobRequest) -> Job:
        now = utc_now()
        job = Job(
            job_id=str(uuid4()),
            project_id=project_id,
            source_file_path=str(Path(request.source_file_path).resolve()),
            status=JobStatus.CREATED,
            created_at=now,
            language_selected=request.language_selected,
            model_name=request.model_name,
            device_used=request.device_used,
            compute_type=request.compute_type,
            artifacts_root_path=request.artifacts_root_path,
            speaker_count_mode=request.speaker_count_mode,
            exact_speakers=request.exact_speakers,
            min_speakers=request.min_speakers,
            max_speakers=request.max_speakers,
        )

        with self._database.connect() as conn:
            conn.execute(
                """
                INSERT INTO jobs(
                  job_id,
                  project_id,
                  source_file_path,
                  artifacts_root_path,
                  status,
                  language_selected,
                  model_name,
                  device_used,
                  compute_type,
                  speaker_count_mode,
                  exact_speakers,
                  min_speakers,
                  max_speakers,
                  created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.job_id,
                    job.project_id,
                    job.source_file_path,
                    job.artifacts_root_path,
                    job.status.value,
                    job.language_selected,
                    job.model_name,
                    job.device_used,
                    job.compute_type,
                    job.speaker_count_mode,
                    job.exact_speakers,
                    job.min_speakers,
                    job.max_speakers,
                    to_iso(job.created_at),
                ),
            )
            conn.commit()

        return job

    def save_context_hints(self, job_id: str, hints: JobContextHints | None) -> None:
        if hints is None:
            return

        with self._database.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO job_context_hints(
                  job_id,
                  language_hint,
                  domain_context,
                  hotwords_json,
                  glossary_json,
                  expected_participants_json,
                  expected_entities_json,
                  expected_acronyms_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    hints.language_hint,
                    hints.domain_context,
                    json.dumps(hints.hotwords),
                    json.dumps(hints.glossary_terms),
                    json.dumps(hints.expected_participants),
                    json.dumps(hints.expected_entities),
                    json.dumps(hints.expected_acronyms),
                ),
            )
            conn.commit()

    def get_context_hints(self, job_id: str) -> JobContextHints | None:
        with self._database.connect() as conn:
            row = conn.execute("SELECT * FROM job_context_hints WHERE job_id = ?", (job_id,)).fetchone()

        if row is None:
            return None

        return JobContextHints(
            language_hint=row["language_hint"],
            domain_context=row["domain_context"],
            hotwords=json.loads(row["hotwords_json"] or "[]"),
            glossary_terms=json.loads(row["glossary_json"] or "[]"),
            expected_participants=json.loads(row["expected_participants_json"] or "[]"),
            expected_entities=json.loads(row["expected_entities_json"] or "[]"),
            expected_acronyms=json.loads(row["expected_acronyms_json"] or "[]"),
        )

    def get_by_id(self, job_id: str) -> Job | None:
        with self._database.connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()

        if row is None:
            return None

        return self._row_to_job(row)

    def list_recent(self, limit: int = 100) -> list[Job]:
        with self._database.connect() as conn:
            rows = conn.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()

        return [self._row_to_job(row) for row in rows]

    def list_by_status(self, status: JobStatus, limit: int = 500) -> list[Job]:
        with self._database.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE status = ? ORDER BY created_at ASC LIMIT ?",
                (status.value, limit),
            ).fetchall()

        return [self._row_to_job(row) for row in rows]

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
        completed_at = to_iso(utc_now()) if completed else None

        with self._database.connect() as conn:
            conn.execute(
                """
                UPDATE jobs
                SET
                  status = ?,
                  language_detected = COALESCE(?, language_detected),
                  error_message = ?,
                  completed_at = COALESCE(?, completed_at),
                  execution_duration_seconds = COALESCE(?, execution_duration_seconds)
                WHERE job_id = ?
                """,
                (status.value, language_detected, error_message, completed_at, execution_duration_seconds, job_id),
            )
            conn.commit()

    def update_working_audio_path(self, job_id: str, working_audio_path: str) -> None:
        with self._database.connect() as conn:
            conn.execute(
                "UPDATE jobs SET working_audio_path = ? WHERE job_id = ?",
                (working_audio_path, job_id),
            )
            conn.commit()

    @staticmethod
    def _row_to_job(row: dict[str, str]) -> Job:
        created_at = from_iso(row["created_at"])
        assert created_at is not None

        row_keys = set(row.keys()) if hasattr(row, "keys") else set()
        artifacts_root_path = row["artifacts_root_path"] if "artifacts_root_path" in row_keys else None
        execution_duration_seconds = row["execution_duration_seconds"] if "execution_duration_seconds" in row_keys else None

        return Job(
            job_id=row["job_id"],
            project_id=row["project_id"],
            source_file_path=row["source_file_path"],
            status=JobRepository._parse_status(row["status"]),
            created_at=created_at,
            completed_at=from_iso(row["completed_at"]),
            working_audio_path=row["working_audio_path"],
            language_detected=row["language_detected"],
            language_selected=row["language_selected"],
            model_name=row["model_name"],
            device_used=row["device_used"],
            compute_type=row["compute_type"],
            execution_duration_seconds=execution_duration_seconds,
            artifacts_root_path=artifacts_root_path,
            speaker_count_mode=row["speaker_count_mode"] or "auto",
            exact_speakers=row["exact_speakers"],
            min_speakers=row["min_speakers"],
            max_speakers=row["max_speakers"],
            error_message=row["error_message"],
        )

    @staticmethod
    def _parse_status(raw_status: str | None) -> JobStatus:
        if not raw_status:
            return JobStatus.CREATED

        try:
            return JobStatus(raw_status)
        except ValueError:
            _LOGGER.warning("Unknown job status '%s' found in DB; falling back to CREATED.", raw_status)
            return JobStatus.CREATED
