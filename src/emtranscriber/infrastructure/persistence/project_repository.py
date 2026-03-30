from __future__ import annotations

from uuid import uuid4

from emtranscriber.domain.entities.project import Project
from emtranscriber.infrastructure.persistence.common import from_iso, to_iso, utc_now
from emtranscriber.infrastructure.persistence.sqlite import SQLiteDatabase


class ProjectRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def get_or_create(self, name: str) -> Project:
        normalized_name = name.strip() or "Default Project"

        existing = self.find_by_name(normalized_name)
        if existing is not None:
            return existing

        now = utc_now()
        project = Project(
            project_id=str(uuid4()),
            name=normalized_name,
            created_at=now,
            updated_at=now,
        )

        with self._database.connect() as conn:
            conn.execute(
                """
                INSERT INTO projects(project_id, name, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (project.project_id, project.name, to_iso(project.created_at), to_iso(project.updated_at)),
            )
            conn.commit()

        return project

    def find_by_name(self, name: str) -> Project | None:
        with self._database.connect() as conn:
            row = conn.execute("SELECT * FROM projects WHERE name = ?", (name,)).fetchone()

        if row is None:
            return None

        created_at = from_iso(row["created_at"])
        updated_at = from_iso(row["updated_at"])
        assert created_at is not None
        assert updated_at is not None

        return Project(
            project_id=row["project_id"],
            name=row["name"],
            created_at=created_at,
            updated_at=updated_at,
        )

    def get_by_id(self, project_id: str) -> Project | None:
        with self._database.connect() as conn:
            row = conn.execute("SELECT * FROM projects WHERE project_id = ?", (project_id,)).fetchone()

        if row is None:
            return None

        created_at = from_iso(row["created_at"])
        updated_at = from_iso(row["updated_at"])
        assert created_at is not None
        assert updated_at is not None

        return Project(
            project_id=row["project_id"],
            name=row["name"],
            created_at=created_at,
            updated_at=updated_at,
        )
