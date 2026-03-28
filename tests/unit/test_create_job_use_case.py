from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pytest

from emtranscriber.application.dto.new_job_request import NewJobRequest
from emtranscriber.application.use_cases.create_job import CreateJobUseCase
from emtranscriber.domain.entities.job import Job
from emtranscriber.domain.value_objects.job_status import JobStatus
from emtranscriber.infrastructure.persistence.artifact_store import JobArtifactStore


@dataclass(slots=True)
class FakeProject:
    project_id: str


class FakeProjectRepository:
    def get_or_create(self, _project_name: str) -> FakeProject:
        return FakeProject(project_id="proj-1")


class FakeJobRepository:
    def __init__(self) -> None:
        self.last_request: NewJobRequest | None = None

    def create(self, project_id: str, request: NewJobRequest) -> Job:
        self.last_request = request
        return Job(
            job_id="job-1",
            project_id=project_id,
            source_file_path=request.source_file_path,
            status=JobStatus.CREATED,
            created_at=datetime.now(),
            artifacts_root_path=request.artifacts_root_path,
        )

    def save_context_hints(self, _job_id: str, _hints) -> None:
        return None


def test_create_job_uses_source_folder_as_default_output(tmp_path: Path) -> None:
    source = tmp_path / "meeting.wav"
    source.write_bytes(b"RIFF")

    request = NewJobRequest(project_name="Demo", source_file_path=str(source))
    jobs = FakeJobRepository()
    use_case = CreateJobUseCase(FakeProjectRepository(), jobs)

    job = use_case.execute(request)

    expected_root = str(source.parent.resolve())
    assert jobs.last_request is not None
    assert jobs.last_request.artifacts_root_path == expected_root
    assert job.artifacts_root_path == expected_root


def test_create_job_uses_custom_output_folder(tmp_path: Path) -> None:
    source = tmp_path / "meeting.wav"
    source.write_bytes(b"RIFF")
    custom_root = tmp_path / "exports_out"

    request = NewJobRequest(
        project_name="Demo",
        source_file_path=str(source),
        artifacts_root_path=str(custom_root),
    )
    jobs = FakeJobRepository()
    use_case = CreateJobUseCase(FakeProjectRepository(), jobs)

    job = use_case.execute(request)

    expected_root = str(custom_root.resolve())
    assert custom_root.exists() and custom_root.is_dir()
    assert jobs.last_request is not None
    assert jobs.last_request.artifacts_root_path == expected_root
    assert job.artifacts_root_path == expected_root


def test_create_job_rejects_file_output_path(tmp_path: Path) -> None:
    source = tmp_path / "meeting.wav"
    source.write_bytes(b"RIFF")
    output_file = tmp_path / "not_a_dir.txt"
    output_file.write_text("x", encoding="utf-8")

    request = NewJobRequest(
        project_name="Demo",
        source_file_path=str(source),
        artifacts_root_path=str(output_file),
    )
    use_case = CreateJobUseCase(FakeProjectRepository(), FakeJobRepository())

    with pytest.raises(ValueError, match="not a directory"):
        use_case.execute(request)


def test_artifact_store_honors_custom_root_override(tmp_path: Path) -> None:
    store = JobArtifactStore(tmp_path / "default_root")
    custom_root = tmp_path / "custom_root"

    paths = store.ensure_job_directories("proj", "job", str(custom_root))

    assert paths["base"] == custom_root / "proj" / "jobs" / "job"
    assert paths["exports"].exists()
