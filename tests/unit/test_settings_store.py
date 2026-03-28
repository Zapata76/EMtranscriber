from pathlib import Path

from emtranscriber.infrastructure.settings.app_settings import AppSettings
from emtranscriber.infrastructure.settings.settings_store import SettingsStore


def test_settings_store_roundtrip(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path / "settings.json")
    settings = AppSettings(
        default_asr_model="large-v3",
        pyannote_model_path="C:/models/pyannote",
        ui_language="fr",
        ui_theme="dark",
        ai_analysis_enabled=True,
        ai_analysis_provider="openai_compatible",
        ai_analysis_endpoint="https://api.openai.com/v1/chat/completions",
        ai_analysis_api_key="secret-key",
        ai_analysis_model="gpt-4.1-mini",
        ai_analysis_default_template="meeting-summary",
        ai_analysis_default_prompt="Focus on decisions",
        ai_analysis_output_language="Italian",
    )
    store.save(settings)

    loaded = store.load()

    assert loaded.default_asr_model == "large-v3"
    assert loaded.pyannote_model_path == "C:/models/pyannote"
    assert loaded.ui_language == "fr"
    assert loaded.ui_theme == "dark"
    assert loaded.ai_analysis_enabled is True
    assert loaded.ai_analysis_provider == "openai_compatible"
    assert loaded.ai_analysis_model == "gpt-4.1-mini"
    assert loaded.ai_analysis_output_language == "Italian"
