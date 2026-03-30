from emtranscriber.domain.value_objects.job_status import JobStatus
from emtranscriber.infrastructure.persistence.job_repository import JobRepository


def test_job_status_supports_queued() -> None:
    assert JobStatus("QUEUED") == JobStatus.QUEUED


def test_parse_status_falls_back_to_created_for_unknown_value() -> None:
    assert JobRepository._parse_status("UNKNOWN_FUTURE_STATUS") == JobStatus.CREATED