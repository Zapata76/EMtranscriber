from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class InvalidQueueTransition(RuntimeError):
    pass


class QueueControlState(str, Enum):
    RUNNING = "running"
    PAUSED = "paused"


@dataclass(frozen=True, slots=True)
class QueueSnapshot:
    state: QueueControlState
    active_job_id: str | None

    @property
    def paused(self) -> bool:
        return self.state == QueueControlState.PAUSED

    @property
    def has_active_job(self) -> bool:
        return bool(self.active_job_id)


class JobQueueStateMachine:
    def __init__(self) -> None:
        self._state = QueueControlState.RUNNING
        self._active_job_id: str | None = None

    def snapshot(self) -> QueueSnapshot:
        return QueueSnapshot(state=self._state, active_job_id=self._active_job_id)

    def pause(self) -> QueueSnapshot:
        self._state = QueueControlState.PAUSED
        return self.snapshot()

    def resume(self) -> QueueSnapshot:
        self._state = QueueControlState.RUNNING
        return self.snapshot()

    def start_job(self, job_id: str) -> QueueSnapshot:
        if not job_id.strip():
            raise InvalidQueueTransition("Cannot start queue with empty job id.")

        if self._state == QueueControlState.PAUSED:
            raise InvalidQueueTransition("Cannot start a job while queue is paused.")

        if self._active_job_id is not None:
            raise InvalidQueueTransition("Cannot start a new job while another one is active.")

        self._active_job_id = job_id
        return self.snapshot()

    def finish_active_job(self, job_id: str) -> QueueSnapshot:
        if self._active_job_id != job_id:
            raise InvalidQueueTransition("Job completion does not match active queue job.")

        self._active_job_id = None
        return self.snapshot()

    def clear_active_job(self) -> QueueSnapshot:
        self._active_job_id = None
        return self.snapshot()

    def can_dispatch_next(self, *, has_queued_jobs: bool) -> bool:
        return self._state == QueueControlState.RUNNING and self._active_job_id is None and has_queued_jobs
