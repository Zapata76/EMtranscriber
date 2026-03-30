from __future__ import annotations

from dataclasses import asdict, dataclass, field


DEFAULT_ANALYSIS_ENDPOINT = "https://api.openai.com/v1/chat/completions"
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

    ai_analysis_enabled: bool = False
    ai_analysis_provider: str = "disabled"
    ai_analysis_endpoint: str = DEFAULT_ANALYSIS_ENDPOINT
    ai_analysis_api_key: str | None = None
    ai_analysis_model: str | None = None
    ai_analysis_default_template: str = "meeting-summary"
    ai_analysis_default_prompt: str = ""
    ai_analysis_output_language: str | None = None

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
            ai_analysis_enabled=_to_bool(payload.get("ai_analysis_enabled", False)),
            ai_analysis_provider=payload.get("ai_analysis_provider", "disabled"),
            ai_analysis_endpoint=payload.get("ai_analysis_endpoint", DEFAULT_ANALYSIS_ENDPOINT),
            ai_analysis_api_key=payload.get("ai_analysis_api_key"),
            ai_analysis_model=payload.get("ai_analysis_model"),
            ai_analysis_default_template=payload.get("ai_analysis_default_template", "meeting-summary"),
            ai_analysis_default_prompt=payload.get("ai_analysis_default_prompt", ""),
            ai_analysis_output_language=payload.get("ai_analysis_output_language"),
        )


def _to_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _normalize_ui_theme(value: str | None) -> str:
    if not isinstance(value, str):
        return "dark"
    candidate = value.strip().lower()
    if candidate in SUPPORTED_UI_THEMES:
        return candidate
    return "dark"

