from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from emtranscriber.domain.entities.job import Job
from emtranscriber.domain.pipeline.diarization_types import DiarizationResult, SpeakerTurn

DiarizationProgressCallback = Callable[[str, float | None], None]


class PyannoteDiarizationServiceStub:
    def diarize(
        self,
        job: Job,
        audio_path: Path,
        on_progress: DiarizationProgressCallback | None = None,
    ) -> tuple[DiarizationResult, dict]:
        self._emit_progress(on_progress, "Stub diarization: preparing", 0.2)
        time.sleep(0.15)

        self._emit_progress(on_progress, "Stub diarization: estimating turns", 0.7)
        time.sleep(0.15)

        turns = [
            SpeakerTurn(start_s=0.0, end_s=1.6, speaker_label="speaker_a"),
            SpeakerTurn(start_s=1.6, end_s=3.4, speaker_label="speaker_b"),
        ]
        result = DiarizationResult(turns=turns)
        raw = {
            "engine": "pyannote-stub",
            "audio_path": str(audio_path),
            "turns": [
                {"start": turn.start_s, "end": turn.end_s, "speaker": turn.speaker_label}
                for turn in turns
            ],
        }

        self._emit_progress(on_progress, "Stub diarization completed", 1.0)
        return result, raw

    @staticmethod
    def _emit_progress(
        callback: DiarizationProgressCallback | None,
        message: str,
        progress: float | None = None,
    ) -> None:
        if callback is not None:
            callback(message, progress)
