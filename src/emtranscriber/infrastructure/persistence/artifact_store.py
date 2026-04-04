from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


class JobArtifactStore:
    _APP_FOLDER_NAME = "EMtranscriber"
    _LAYOUT_VERSION = ""

    def __init__(self, projects_root: Path) -> None:
        self._projects_root = projects_root

    def ensure_job_directories(
        self,
        project_id: str,
        job_id: str,
        artifacts_root_path: str | None = None,
        *,
        source_file_path: str | None = None,
        created_at: datetime | None = None,
    ) -> dict[str, Path]:
        root = Path(artifacts_root_path).expanduser() if artifacts_root_path else self._projects_root
        base = self._resolve_job_base_path(
            root=root,
            project_id=project_id,
            job_id=job_id,
            source_file_path=source_file_path,
            created_at=created_at,
        )

        paths = {
            "base": base,
            "source": base / "source",
            "working": base / "working",
            "raw": base / "raw",
            "merged": base / "merged",
            # Final transcript artifacts live in the job root for easier access.
            "exports": base,
        }

        for path in paths.values():
            path.mkdir(parents=True, exist_ok=True)

        return paths

    def _resolve_job_base_path(
        self,
        *,
        root: Path,
        project_id: str,
        job_id: str,
        source_file_path: str | None,
        created_at: datetime | None,
    ) -> Path:
        existing_legacy = self._find_existing_legacy_base(root=root, project_id=project_id, job_id=job_id)
        if existing_legacy is not None:
            return existing_legacy

        em_root = root / self._APP_FOLDER_NAME / self._LAYOUT_VERSION

        if source_file_path and created_at is not None:
            return em_root / self._build_human_job_folder_name(created_at)

        # Deterministic fallback for partial records.
        if project_id:
            return em_root / project_id / job_id

        return em_root / job_id

    @staticmethod
    def _build_human_job_folder_name(created_at: datetime) -> str:
        return created_at.strftime("%Y%m%d_%H%M%S")

    @staticmethod
    def _find_existing_legacy_base(*, root: Path, project_id: str, job_id: str) -> Path | None:
        candidates = (
            root / project_id / "jobs" / job_id,
            root / "EMtranscriber" / project_id / job_id,
            root / "EMtranscriber" / job_id,
        )

        for candidate in candidates:
            if candidate.exists() and candidate.is_dir():
                return candidate

        return None

    def save_json(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def save_text(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

