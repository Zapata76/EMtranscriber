from __future__ import annotations

import json
from pathlib import Path

from emtranscriber.infrastructure.settings.app_settings import AppSettings


class SettingsStore:
    def __init__(self, settings_file: Path) -> None:
        self._settings_file = settings_file

    def load(self) -> AppSettings:
        if not self._settings_file.exists():
            settings = AppSettings()
            self.save(settings)
            return settings

        payload = json.loads(self._settings_file.read_text(encoding="utf-8"))
        return AppSettings.from_dict(payload)

    def save(self, settings: AppSettings) -> None:
        self._settings_file.parent.mkdir(parents=True, exist_ok=True)
        self._settings_file.write_text(
            json.dumps(settings.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
