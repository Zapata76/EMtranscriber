import pytest

from emtranscriber.application.services.job_queue_state_machine import (
    InvalidQueueTransition,
    JobQueueStateMachine,
    QueueControlState,
)


def test_state_machine_starts_running_without_active_job() -> None:
    machine = JobQueueStateMachine()

    snap = machine.snapshot()

    assert snap.state == QueueControlState.RUNNING
    assert snap.active_job_id is None


def test_pause_resume_transitions() -> None:
    machine = JobQueueStateMachine()

    machine.pause()
    assert machine.snapshot().paused is True

    machine.resume()
    assert machine.snapshot().paused is False


def test_start_and_finish_active_job() -> None:
    machine = JobQueueStateMachine()

    machine.start_job("job-1")
    assert machine.snapshot().active_job_id == "job-1"

    machine.finish_active_job("job-1")
    assert machine.snapshot().active_job_id is None


def test_start_job_is_blocked_while_paused() -> None:
    machine = JobQueueStateMachine()
    machine.pause()

    with pytest.raises(InvalidQueueTransition):
        machine.start_job("job-1")


def test_start_job_is_blocked_when_another_job_is_active() -> None:
    machine = JobQueueStateMachine()
    machine.start_job("job-1")

    with pytest.raises(InvalidQueueTransition):
        machine.start_job("job-2")


def test_finish_job_must_match_active_job() -> None:
    machine = JobQueueStateMachine()
    machine.start_job("job-1")

    with pytest.raises(InvalidQueueTransition):
        machine.finish_active_job("job-2")


def test_can_dispatch_next_depends_on_state_active_and_queue_presence() -> None:
    machine = JobQueueStateMachine()

    assert machine.can_dispatch_next(has_queued_jobs=True) is True

    machine.pause()
    assert machine.can_dispatch_next(has_queued_jobs=True) is False

    machine.resume()
    machine.start_job("job-1")
    assert machine.can_dispatch_next(has_queued_jobs=True) is False

    machine.finish_active_job("job-1")
    assert machine.can_dispatch_next(has_queued_jobs=False) is False
