from emtranscriber.domain.alignment.speaker_aligner import SpeakerAligner
from emtranscriber.domain.pipeline.asr_types import AsrResult, AsrSegment, AsrWord
from emtranscriber.domain.pipeline.diarization_types import DiarizationResult, SpeakerTurn


def test_speaker_aligner_maps_to_stable_keys() -> None:
    asr = AsrResult(
        language="it",
        duration_s=4.0,
        segments=[
            AsrSegment(
                text="ciao",
                start_s=0.0,
                end_s=1.0,
                words=[AsrWord(text="ciao", start_s=0.0, end_s=0.9)],
            ),
            AsrSegment(
                text="come va",
                start_s=1.1,
                end_s=2.5,
                words=[AsrWord(text="come", start_s=1.1, end_s=1.6), AsrWord(text="va", start_s=1.7, end_s=2.4)],
            ),
        ],
    )

    diar = DiarizationResult(
        turns=[
            SpeakerTurn(start_s=0.0, end_s=1.0, speaker_label="A"),
            SpeakerTurn(start_s=1.0, end_s=3.0, speaker_label="B"),
        ]
    )

    doc = SpeakerAligner().align("job-1", asr, diar)

    assert [s.speaker_key for s in doc.speakers] == ["SPEAKER_00", "SPEAKER_01"]
    assert len(doc.segments) == 2
    assert doc.segments[0].speaker_key == "SPEAKER_00"
    assert doc.segments[1].speaker_key == "SPEAKER_01"
