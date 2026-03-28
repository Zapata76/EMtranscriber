from __future__ import annotations

from dataclasses import dataclass

from emtranscriber.domain.entities.job_context_hints import JobContextHints


@dataclass(slots=True)
class NewJobRequest:
    project_name: str
    source_file_path: str
    artifacts_root_path: str | None = None
    language_selected: str = "auto"
    model_name: str = "large-v3"
    device_used: str = "auto"
    compute_type: str = "auto"
    speaker_count_mode: str = "auto"
    exact_speakers: int | None = None
    min_speakers: int | None = None
    max_speakers: int | None = None
    context_hints: JobContextHints | None = None
