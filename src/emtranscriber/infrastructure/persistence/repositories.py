"""Backward-compatible imports for older references.

New code should import concrete repository classes from:
- job_repository.py
- project_repository.py
- transcript_repository.py
"""

from emtranscriber.infrastructure.persistence.job_repository import JobRepository
from emtranscriber.infrastructure.persistence.project_repository import ProjectRepository
from emtranscriber.infrastructure.persistence.transcript_repository import TranscriptRepository

__all__ = ["JobRepository", "ProjectRepository", "TranscriptRepository"]
