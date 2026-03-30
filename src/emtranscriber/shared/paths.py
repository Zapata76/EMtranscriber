from __future__ import annotations

import os
import sys
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


def _is_frozen_app() -> bool:
    return bool(getattr(sys, "frozen", False))


def _appdata_base_dir() -> Path:
    if os.name == "nt":
        appdata = os.getenv("APPDATA")
        if appdata:
            return Path(appdata) / APP_NAME
        return Path.home() / "AppData" / "Roaming" / APP_NAME

    return Path.home() / f".{APP_NAME.lower()}"


def _frozen_portable_base_dir() -> Path:
    exe_dir = Path(sys.executable).resolve().parent
    return exe_dir / "data"


def _default_base_dir() -> Path:
    override = os.getenv("EMTRANSCRIBER_HOME")
    if override:
        return Path(override).expanduser().resolve()

    if _is_frozen_app():
        return _frozen_portable_base_dir()

    return _appdata_base_dir()


def get_app_paths() -> AppPaths:
    default_paths = _build(_default_base_dir())
    try:
        default_paths.ensure()
        return default_paths
    except PermissionError:
        if _is_frozen_app():
            appdata_fallback = _build(_appdata_base_dir())
            appdata_fallback.ensure()
            return appdata_fallback

        cwd_fallback = _build(Path.cwd() / ".emtranscriber")
        cwd_fallback.ensure()
        return cwd_fallback
