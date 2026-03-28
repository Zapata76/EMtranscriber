from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "EMtranscriber"


@dataclass(frozen=True)
class AppPaths:
    base_dir: Path
    db_file: Path
    settings_file: Path
    logs_dir: Path
    cache_dir: Path
    models_dir: Path
    projects_dir: Path

    def ensure(self) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.projects_dir.mkdir(parents=True, exist_ok=True)



def _build(base_dir: Path) -> AppPaths:
    return AppPaths(
        base_dir=base_dir,
        db_file=base_dir / "emtranscriber.db",
        settings_file=base_dir / "settings.json",
        logs_dir=base_dir / "logs",
        cache_dir=base_dir / "cache",
        models_dir=base_dir / "models",
        projects_dir=base_dir / "projects",
    )


def _default_base_dir() -> Path:
    override = os.getenv("EMTRANSCRIBER_HOME")
    if override:
        return Path(override).expanduser().resolve()

    if os.name == "nt":
        appdata = os.getenv("APPDATA")
        if appdata:
            return Path(appdata) / APP_NAME
        return Path.home() / "AppData" / "Roaming" / APP_NAME

    return Path.home() / f".{APP_NAME.lower()}"


def get_app_paths() -> AppPaths:
    default_paths = _build(_default_base_dir())
    try:
        default_paths.ensure()
        return default_paths
    except PermissionError:
        fallback = _build(Path.cwd() / ".emtranscriber")
        fallback.ensure()
        return fallback
