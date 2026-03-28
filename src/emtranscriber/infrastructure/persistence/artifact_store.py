from __future__ import annotations

import json
from pathlib import Path


class JobArtifactStore:
    def __init__(self, projects_root: Path) -> None:
        self._projects_root = projects_root

    def ensure_job_directories(
        self,
        project_id: str,
        job_id: str,
        artifacts_root_path: str | None = None,
    ) -> dict[str, Path]:
        root = Path(artifacts_root_path).expanduser() if artifacts_root_path else self._projects_root
        base = root / project_id / "jobs" / job_id
        paths = {
            "base": base,
            "source": base / "source",
            "working": base / "working",
            "raw": base / "raw",
            "merged": base / "merged",
            "exports": base / "exports",
            "analysis": base / "analysis",
        }
        for path in paths.values():
            path.mkdir(parents=True, exist_ok=True)
        return paths

    def save_json(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def save_text(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
