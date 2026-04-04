from __future__ import annotations

from dataclasses import asdict, dataclass, field


SUPPORTED_UI_THEMES = {"light", "dark"}


@dataclass(slots=True)
class AppSettings:
    default_asr_model: str = "large-v3"
    default_device: str = "auto"
    default_compute_type: str = "auto"
    asr_model_paths: dict[str, str] = field(default_factory=dict)
    pyannote_model_path: str | None = None
    huggingface_token: str | None = None

    ui_language: str | None = None
    ui_theme: str = "dark"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict) -> "AppSettings":
        raw_ui_language = payload.get("ui_language")
        ui_language = raw_ui_language.strip().lower() if isinstance(raw_ui_language, str) and raw_ui_language.strip() else None

        return cls(
            default_asr_model=payload.get("default_asr_model", "large-v3"),
            default_device=payload.get("default_device", "auto"),
            default_compute_type=payload.get("default_compute_type", "auto"),
            asr_model_paths=dict(payload.get("asr_model_paths", {})),
            pyannote_model_path=payload.get("pyannote_model_path"),
            huggingface_token=payload.get("huggingface_token"),
            ui_language=ui_language,
            ui_theme=_normalize_ui_theme(payload.get("ui_theme")),
        )


def _normalize_ui_theme(value: str | None) -> str:
    if not isinstance(value, str):
        return "dark"
    candidate = value.strip().lower()
    if candidate in SUPPORTED_UI_THEMES:
        return candidate
    return "dark"

