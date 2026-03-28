from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from emtranscriber.domain.entities.job import Job
from emtranscriber.domain.pipeline.asr_types import AsrResult, AsrSegment, AsrWord

AsrProgressCallback = Callable[[str, float | None], None]


class FasterWhisperServiceStub:
    def transcribe(
        self,
        job: Job,
        audio_path: Path,
        *,
        hint_text: str = "",
        hotwords: list[str] | None = None,
        on_progress: AsrProgressCallback | None = None,
    ) -> tuple[AsrResult, dict]:
        self._emit_progress(on_progress, "Stub ASR: preparing model", 0.2)
        time.sleep(0.2)

        self._emit_progress(on_progress, "Stub ASR: decoding demo segment", 0.7)
        time.sleep(0.2)

        segment = AsrSegment(
            text="Stub transcript for EMtranscriber.",
            start_s=0.0,
            end_s=3.4,
            words=[
                AsrWord(text="Stub", start_s=0.0, end_s=0.4),
                AsrWord(text="transcript", start_s=0.5, end_s=1.4),
                AsrWord(text="for", start_s=1.5, end_s=1.7),
                AsrWord(text="EMtranscriber.", start_s=1.8, end_s=3.4),
            ],
        )
        result = AsrResult(language="en", duration_s=3.4, segments=[segment])
        raw = {
            "engine": "faster-whisper-stub",
            "audio_path": str(audio_path),
            "hint_used": bool(hint_text),
            "hotwords": hotwords or [],
            "segments": [
                {
                    "start": segment.start_s,
                    "end": segment.end_s,
                    "text": segment.text,
                }
            ],
        }

        self._emit_progress(on_progress, "Stub ASR completed", 1.0)
        return result, raw

    @staticmethod
    def _emit_progress(callback: AsrProgressCallback | None, message: str, progress: float | None = None) -> None:
        if callback is not None:
            callback(message, progress)
