from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Speaker:
    speaker_key: str
    display_name: str | None = None
    color_tag: str | None = None
    is_manually_named: bool = False
    notes: str | None = None

    @property
    def resolved_name(self) -> str:
        value = (self.display_name or "").strip()
        return value if value else self.speaker_key
