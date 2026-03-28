from datetime import datetime, timezone

from emtranscriber.domain.entities.job import Job
from emtranscriber.domain.entities.speaker import Speaker
from emtranscriber.domain.entities.transcript_document import TranscriptDocument
from emtranscriber.domain.entities.transcript_segment import TranscriptSegment
from emtranscriber.domain.value_objects.job_status import JobStatus
from emtranscriber.domain.exports.transcript_exporter import TranscriptExporter


def test_transcript_exporter_generates_all_formats() -> None:
    job = Job(
        job_id="job-1",
        project_id="prj",
        source_file_path="meeting.wav",
        status=JobStatus.COMPLETED,
        created_at=datetime.now(timezone.utc),
        language_detected="it",
        model_name="large-v3",
    )
    segment = TranscriptSegment(
        segment_id="seg-1",
        job_id="job-1",
        start_ms=1200,
        end_ms=2200,
        speaker_key="SPEAKER_00",
        speaker_name_resolved="Paolo",
        text="Ciao a tutti",
        source_type="merged",
        confidence=0.9,
        order_index=0,
        words=[],
    )
    document = TranscriptDocument(
        job_id="job-1",
        segments=[segment],
        speakers=[Speaker(speaker_key="SPEAKER_00", display_name="Paolo", is_manually_named=True)],
    )

    exporter = TranscriptExporter()
    md = exporter.build_markdown(job, document)
    txt = exporter.build_txt(document)
    payload = exporter.build_json(job, document)
    srt = exporter.build_srt(document)

    assert "# Transcript" in md
    assert "Paolo: Ciao a tutti" in srt
    assert "Paolo" in txt
    assert payload["segments"][0]["speaker_name"] == "Paolo"
