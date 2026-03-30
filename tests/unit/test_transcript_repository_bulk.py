from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import uuid4

from emtranscriber.application.dto.new_job_request import NewJobRequest
from emtranscriber.domain.entities.speaker import Speaker
from emtranscriber.domain.entities.transcript_segment import TranscriptSegment
from emtranscriber.domain.value_objects.job_status import JobStatus
from emtranscriber.infrastructure.persistence.job_repository import JobRepository
from emtranscriber.infrastructure.persistence.project_repository import ProjectRepository
from emtranscriber.infrastructure.persistence.sqlite import SQLiteDatabase
from emtranscriber.infrastructure.persistence.transcript_repository import TranscriptRepository
from emtranscriber.shared.paths import AppPaths


def _build_app_paths(base_dir: Path) -> AppPaths:
    return AppPaths(
        base_dir=base_dir,
        db_file=base_dir / "emtranscriber.db",
        settings_file=base_dir / "settings.json",
        logs_dir=base_dir / "logs",
        cache_dir=base_dir / "cache",
        models_dir=base_dir / "models",
        projects_dir=base_dir / "projects",
    )


def _create_job(database: SQLiteDatabase) -> str:
    project_repo = ProjectRepository(database)
    job_repo = JobRepository(database)

    project = project_repo.get_or_create("Demo")
    source = str(Path(__file__).resolve())
    job = job_repo.create(project.project_id, NewJobRequest(project_name="Demo", source_file_path=source))
    job_repo.update_status(job.job_id, JobStatus.COMPLETED, completed=True)
    return job.job_id


def _segment(job_id: str, idx: int, speaker_key: str, text: str) -> TranscriptSegment:
    start_ms = idx * 1000
    end_ms = start_ms + 900
    return TranscriptSegment(
        segment_id=str(uuid4()),
        job_id=job_id,
        start_ms=start_ms,
        end_ms=end_ms,
        speaker_key=speaker_key,
        speaker_name_resolved=speaker_key,
        text=text,
        source_type="merged",
        confidence=0.9,
        order_index=idx,
        words=[],
    )


def test_bulk_rename_and_segment_update_are_applied_consistently(tmp_path: Path) -> None:
    app_paths = _build_app_paths(tmp_path / "app")
    app_paths.ensure()
    database = SQLiteDatabase(app_paths)
    database.apply_migrations()

    job_id = _create_job(database)
    repo = TranscriptRepository(database)

    segments = [
        _segment(job_id, 0, "SPEAKER_00", "ciao"),
        _segment(job_id, 1, "SPEAKER_01", "buongiorno"),
    ]
    speakers = [
        Speaker(speaker_key="SPEAKER_00"),
        Speaker(speaker_key="SPEAKER_01"),
    ]

    repo.replace_transcript(job_id, segments, speakers)

    repo.rename_speakers_bulk(job_id, [("SPEAKER_00", "Alice"), ("SPEAKER_01", "Bob")])
    repo.update_segment_texts_bulk(
        [
            (segments[0].segment_id, "ciao a tutti"),
            (segments[1].segment_id, "buongiorno team"),
        ]
    )

    document = repo.load_document(job_id)

    assert [speaker.resolved_name for speaker in document.speakers] == ["Alice", "Bob"]
    assert document.segments[0].speaker_name_resolved == "Alice"
    assert document.segments[1].speaker_name_resolved == "Bob"
    assert document.segments[0].text == "ciao a tutti"
    assert document.segments[1].text == "buongiorno team"
    assert all(segment.source_type == "edited" for segment in document.segments)


def test_bulk_segment_update_handles_large_transcript(tmp_path: Path) -> None:
    app_paths = _build_app_paths(tmp_path / "app")
    app_paths.ensure()
    database = SQLiteDatabase(app_paths)
    database.apply_migrations()

    job_id = _create_job(database)
    repo = TranscriptRepository(database)

    speakers = [Speaker(speaker_key="SPEAKER_00")]
    segments = [_segment(job_id, idx, "SPEAKER_00", f"text-{idx}") for idx in range(300)]
    repo.replace_transcript(job_id, segments, speakers)

    updates = [(segment.segment_id, f"edited-{idx}") for idx, segment in enumerate(segments) if idx % 2 == 0]
    repo.update_segment_texts_bulk(updates)

    with database.connect() as conn:
        edited_count = conn.execute(
            "SELECT COUNT(*) AS n FROM transcript_segments WHERE job_id = ? AND source_type = 'edited'",
            (job_id,),
        ).fetchone()["n"]

    assert edited_count == len(updates)
