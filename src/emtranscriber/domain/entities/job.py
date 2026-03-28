from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from emtranscriber.domain.value_objects.job_status import JobStatus


@dataclass(slots=True)
class Job:
    job_id: str
    project_id: str
    source_file_path: str
    status: JobStatus
    created_at: datetime
    completed_at: datetime | None = None
    working_audio_path: str | None = None
    language_detected: str | None = None
    language_selected: str | None = None
    model_name: str | None = None
    device_used: str | None = None
    compute_type: str | None = None
    artifacts_root_path: str | None = None
    speaker_count_mode: str = "auto"
    exact_speakers: int | None = None
    min_speakers: int | None = None
    max_speakers: int | None = None
    error_message: str | None = None
