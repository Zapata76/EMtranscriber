from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from emtranscriber.shared.paths import AppPaths


class SQLiteDatabase:
    def __init__(self, app_paths: AppPaths) -> None:
        self._app_paths = app_paths
        self._db_path = app_paths.db_file

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def apply_migrations(self) -> None:
        migration_files, scanned_dirs = self._find_migration_files()
        if not migration_files:
            scanned = "\n- ".join(str(path) for path in scanned_dirs)
            raise RuntimeError(
                "No SQL migrations found. The application looked in:\n"
                f"- {scanned}\n"
                "Rebuild the app including the migrations directory."
            )

        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                  version TEXT PRIMARY KEY,
                  applied_at TEXT NOT NULL
                )
                """
            )

            rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
            applied_versions = {row["version"] for row in rows}

            for path in migration_files:
                version = path.stem
                if version in applied_versions:
                    continue

                sql = path.read_text(encoding="utf-8-sig")
                try:
                    conn.executescript(sql)
                except sqlite3.OperationalError as exc:
                    message = str(exc).lower()
                    if "duplicate column name" not in message:
                        raise

                conn.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                    (version, datetime.now(timezone.utc).isoformat()),
                )

            conn.commit()

    def _find_migration_files(self) -> tuple[list[Path], list[Path]]:
        scanned_dirs: list[Path] = []

        for candidate in self._candidate_migration_dirs():
            if candidate in scanned_dirs:
                continue
            scanned_dirs.append(candidate)
            files = sorted(candidate.glob("*.sql"))
            if files:
                return files, scanned_dirs

        return [], scanned_dirs

    def _candidate_migration_dirs(self) -> list[Path]:
        candidates: list[Path] = []

        if getattr(sys, "frozen", False):
            exe_dir = Path(sys.executable).resolve().parent
            candidates.extend(
                [
                    exe_dir / "migrations",
                    exe_dir / "_internal" / "migrations",
                ]
            )

            meipass = getattr(sys, "_MEIPASS", None)
            if meipass:
                candidates.append(Path(meipass) / "migrations")

        module_path = Path(__file__).resolve()
        if len(module_path.parents) >= 5:
            candidates.append(module_path.parents[4] / "migrations")
        candidates.append(Path.cwd() / "migrations")

        return candidates
