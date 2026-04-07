from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal

from emtranscriber.domain.value_objects.job_status import JobStatus
from emtranscriber.infrastructure.persistence.job_repository import JobRepository


class JobProcessingSignals(QObject):
    progress = Signal(str, str, int)
    finished = Signal(str, str)
    failed = Signal(str, str)


class JobProcessingWorker(QRunnable):
    _TERMINAL_STATUSES = {
        JobStatus.COMPLETED,
        JobStatus.PARTIAL_SUCCESS,
        JobStatus.READY_FOR_REVIEW,
        JobStatus.FAILED,
        JobStatus.CANCELLED,
    }

    def __init__(self, job_repository: JobRepository, job_id: str) -> None:
        super().__init__()
        self._job_repository = job_repository
        self._job_id = job_id
        self._cancel_requested = threading.Event()
        self._process_lock = threading.Lock()
        self._process: subprocess.Popen[str] | None = None
        self.signals = JobProcessingSignals()

    def run(self) -> None:
        command = self._build_worker_command(self._job_id)
        env = self._build_worker_env()
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0

        try:
            process = subprocess.Popen(
                command,
                cwd=str(self._worker_cwd()),
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=creationflags,
            )
        except Exception as exc:  # noqa: BLE001
            self.signals.failed.emit(self._job_id, f"Unable to start worker process: {exc}")
            return

        with self._process_lock:
            self._process = process

        child_final_status: str | None = None
        child_error_message: str | None = None

        try:
            assert process.stdout is not None
            for raw_line in process.stdout:
                line = raw_line.strip()
                if not line:
                    continue
                parsed_status, parsed_error = self._handle_worker_line(line)
                if parsed_status is not None:
                    child_final_status = parsed_status
                if parsed_error is not None:
                    child_error_message = parsed_error
        finally:
            process.wait()
            with self._process_lock:
                self._process = None

        if self._cancel_requested.is_set():
            self._mark_cancelled_if_needed()
            self.signals.finished.emit(self._job_id, JobStatus.CANCELLED.value)
            return

        return_code = int(process.returncode or 0)
        if return_code == 0:
            final_status = child_final_status or self._read_status_from_db(default=JobStatus.COMPLETED.value)
            self.signals.finished.emit(self._job_id, final_status)
            return

        self._mark_failed_if_needed(
            error_message=child_error_message or f"Worker process exited unexpectedly (code={return_code})."
        )
        final_error = child_error_message or f"Worker process exited unexpectedly (code={return_code})."
        self.signals.failed.emit(self._job_id, final_error)

    def cancel(self) -> None:
        self._cancel_requested.set()

        with self._process_lock:
            process = self._process

        if process is None or process.poll() is not None:
            return

        try:
            process.terminate()
            process.wait(timeout=8)
        except Exception:  # noqa: BLE001
            try:
                process.kill()
            except Exception:  # noqa: BLE001
                return

    @staticmethod
    def _build_worker_command(job_id: str) -> list[str]:
        if getattr(sys, "frozen", False):
            return [sys.executable, "--run-job", job_id]
        return [sys.executable, "-m", "emtranscriber.main", "--run-job", job_id]

    @staticmethod
    def _worker_cwd() -> Path:
        if getattr(sys, "frozen", False):
            return Path(sys.executable).resolve().parent
        return Path(__file__).resolve().parents[4]

    @staticmethod
    def _project_src_path() -> Path:
        return Path(__file__).resolve().parents[3]

    def _build_worker_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env.setdefault("PYTHONUNBUFFERED", "1")

        if not getattr(sys, "frozen", False):
            src_path = str(self._project_src_path())
            current_python_path = env.get("PYTHONPATH", "")
            python_path_entries = [entry for entry in current_python_path.split(os.pathsep) if entry]
            if src_path not in python_path_entries:
                python_path_entries.insert(0, src_path)
                env["PYTHONPATH"] = os.pathsep.join(python_path_entries)

        return env

    def _handle_worker_line(self, line: str) -> tuple[str | None, str | None]:
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            return None, None

        event_type = str(payload.get("type") or "").strip().lower()
        if event_type == "progress":
            status = str(payload.get("status") or JobStatus.TRANSCRIBING.value)
            message = str(payload.get("message") or "")
            try:
                percent = int(payload.get("percent") or 0)
            except (TypeError, ValueError):
                percent = 0
            percent = max(0, min(100, percent))
            self.signals.progress.emit(status, message, percent)
            return None, None

        if event_type == "finished":
            status = str(payload.get("status") or "").strip()
            if status:
                return status, None
            return None, None

        if event_type == "error":
            message = str(payload.get("message") or "").strip()
            return None, message if message else None

        return None, None

    def _read_status_from_db(self, *, default: str) -> str:
        job = self._job_repository.get_by_id(self._job_id)
        if job is None:
            return default
        return job.status.value

    def _mark_cancelled_if_needed(self) -> None:
        job = self._job_repository.get_by_id(self._job_id)
        if job is None or job.status in self._TERMINAL_STATUSES:
            return
        self._job_repository.update_status(
            self._job_id,
            JobStatus.CANCELLED,
            error_message="Cancelled by user (worker process terminated).",
            completed=True,
        )

    def _mark_failed_if_needed(self, *, error_message: str) -> None:
        job = self._job_repository.get_by_id(self._job_id)
        if job is None or job.status in self._TERMINAL_STATUSES:
            return
        self._job_repository.update_status(
            self._job_id,
            JobStatus.FAILED,
            error_message=error_message,
            completed=True,
        )
