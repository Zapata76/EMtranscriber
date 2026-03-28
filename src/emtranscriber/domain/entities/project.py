from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class Project:
    project_id: str
    name: str
    created_at: datetime
    updated_at: datetime
