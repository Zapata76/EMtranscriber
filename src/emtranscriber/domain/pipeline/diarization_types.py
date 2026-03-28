from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class SpeakerTurn:
    start_s: float
    end_s: float
    speaker_label: str


@dataclass(slots=True)
class DiarizationResult:
    turns: list[SpeakerTurn]
