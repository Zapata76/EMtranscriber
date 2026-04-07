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
    )
    store.save(settings)

    loaded = store.load()

    assert loaded.default_asr_model == "large-v3"
    assert loaded.pyannote_model_path == "C:/models/pyannote"
    assert loaded.ui_language == "fr"
    assert loaded.ui_theme == "dark"
