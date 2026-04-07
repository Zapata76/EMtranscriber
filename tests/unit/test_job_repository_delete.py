from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from emtranscriber.application.dto.new_job_request import NewJobRequest
from emtranscriber.domain.entities.job_context_hints import JobContextHints
from emtranscriber.domain.entities.speaker import Speaker
from emtranscriber.domain.entities.transcript_segment import TranscriptSegment
from emtranscriber.domain.entities.transcript_word import TranscriptWord
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


def test_delete_job_removes_all_related_rows(tmp_path: Path) -> None:
    app_paths = _build_app_paths(tmp_path / "app")
    app_paths.ensure()
    database = SQLiteDatabase(app_paths)
    database.apply_migrations()

    project_repo = ProjectRepository(database)
    job_repo = JobRepository(database)
    transcript_repo = TranscriptRepository(database)

    project = project_repo.get_or_create("Delete Demo")
    source = str(Path(__file__).resolve())
    job = job_repo.create(project.project_id, NewJobRequest(project_name="Delete Demo", source_file_path=source))
    job_repo.save_context_hints(
        job.job_id,
        JobContextHints(
            language_hint="it",
            domain_context="finance",
            hotwords=["budget"],
            glossary_terms=["margine"],
            expected_participants=["Mario"],
            expected_entities=["AziendaX"],
            expected_acronyms=["KPI"],
        ),
    )

    segment_id = str(uuid4())
    segments = [
        TranscriptSegment(
            segment_id=segment_id,
            job_id=job.job_id,
            start_ms=0,
            end_ms=1200,
            speaker_key="SPEAKER_00",
            speaker_name_resolved="SPEAKER_00",
            text="ciao mondo",
            source_type="merged",
            confidence=0.9,
            order_index=0,
            words=[
                TranscriptWord(
                    word_id=str(uuid4()),
                    segment_id=segment_id,
                    start_ms=0,
                    end_ms=500,
                    speaker_key="SPEAKER_00",
                    text="ciao",
                    probability=0.98,
                    order_index=0,
                )
            ],
        )
    ]
    speakers = [Speaker(speaker_key="SPEAKER_00")]
    transcript_repo.replace_transcript(job.job_id, segments, speakers)

    assert job_repo.delete_job(job.job_id) is True
    assert job_repo.get_by_id(job.job_id) is None

    with database.connect() as conn:
        hints_count = conn.execute("SELECT COUNT(*) AS n FROM job_context_hints WHERE job_id = ?", (job.job_id,)).fetchone()["n"]
        speakers_count = conn.execute("SELECT COUNT(*) AS n FROM speakers WHERE job_id = ?", (job.job_id,)).fetchone()["n"]
        segments_count = conn.execute(
            "SELECT COUNT(*) AS n FROM transcript_segments WHERE job_id = ?",
            (job.job_id,),
        ).fetchone()["n"]
        words_count = conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM transcript_words
            WHERE segment_id = ?
            """,
            (segment_id,),
        ).fetchone()["n"]

    assert hints_count == 0
    assert speakers_count == 0
    assert segments_count == 0
    assert words_count == 0
