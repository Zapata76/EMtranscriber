from __future__ import annotations

import ctypes
import gc
import logging
import os
import shutil
import time
from ctypes import wintypes
from collections.abc import Callable
from pathlib import Path

from emtranscriber.domain.exports.transcript_exporter import TranscriptExporter
from emtranscriber.domain.pipeline.hint_builder import build_hint_text
from emtranscriber.domain.value_objects.job_status import JobStatus
from emtranscriber.infrastructure.persistence.artifact_store import JobArtifactStore
from emtranscriber.infrastructure.persistence.job_repository import JobRepository
from emtranscriber.infrastructure.persistence.transcript_repository import TranscriptRepository


ProgressCallback = Callable[[JobStatus, str, int], None]
StageDetailCallback = Callable[[str, float | None], None]


class JobCancelledError(RuntimeError):
    """Raised when a running job is explicitly cancelled by user action."""


class TranscriptionOrchestrator:
    _DEFAULT_MEMORY_GUARD_PRIVATE_MB = 4500.0
    _DEFAULT_MEMORY_GUARD_TRIM_WS = True
    _DEFAULT_MEMORY_GUARD_RELEASE_DIARIZATION = False

    def __init__(
        self,
        job_repository: JobRepository,
        transcript_repository: TranscriptRepository,
        artifact_store: JobArtifactStore,
        audio_normalizer,
        asr_service,
        diarization_service,
        aligner,
        exporter: TranscriptExporter,
        logger: logging.Logger,
    ) -> None:
        self._job_repository = job_repository
        self._transcript_repository = transcript_repository
        self._artifact_store = artifact_store
        self._audio_normalizer = audio_normalizer
        self._asr_service = asr_service
        self._diarization_service = diarization_service
        self._aligner = aligner
        self._exporter = exporter
        self._logger = logger
        self._cancelled_jobs: set[str] = set()
        self._memory_guard_enabled = self._parse_bool_env("EMTRANSCRIBER_MEMORY_GUARD_ENABLED", default=True)
        self._memory_guard_private_mb_threshold = self._parse_float_env(
            "EMTRANSCRIBER_MEMORY_GUARD_PRIVATE_MB",
            default=self._DEFAULT_MEMORY_GUARD_PRIVATE_MB,
            minimum=512.0,
        )
        self._memory_guard_trim_working_set = self._parse_bool_env(
            "EMTRANSCRIBER_MEMORY_GUARD_TRIM_WS",
            default=self._DEFAULT_MEMORY_GUARD_TRIM_WS,
        )
        self._memory_guard_release_diarization = self._parse_bool_env(
            "EMTRANSCRIBER_MEMORY_GUARD_RELEASE_DIARIZATION",
            default=self._DEFAULT_MEMORY_GUARD_RELEASE_DIARIZATION,
        )
        self._logger.info(
            "Runtime memory guard configured | enabled=%s | private_threshold_mb=%.1f | trim_working_set=%s "
            "| release_diarization=%s",
            self._memory_guard_enabled,
            self._memory_guard_private_mb_threshold,
            self._memory_guard_trim_working_set,
            self._memory_guard_release_diarization,
        )

    def cancel(self, job_id: str) -> None:
        self._cancelled_jobs.add(job_id)
        self._logger.info("Cancellation requested for job %s", job_id)

    def process_job(self, job_id: str, on_progress: ProgressCallback | None = None) -> JobStatus:
        job = self._job_repository.get_by_id(job_id)
        if job is None:
            raise ValueError(f"Job not found: {job_id}")

        self._logger.info("Job started: %s", job_id)
        self._log_runtime_snapshot(job_id, "job-start")
        self._run_pre_job_memory_guard(job_id)

        diarization_error: Exception | None = None
        using_stub_pipeline = False
        started_at_monotonic = time.monotonic()

        def elapsed_seconds() -> int:
            return max(0, int(time.monotonic() - started_at_monotonic))

        try:
            self._guard_not_cancelled(job_id)
            directories = self._artifact_store.ensure_job_directories(
                job.project_id,
                job.job_id,
                job.artifacts_root_path,
                source_file_path=job.source_file_path,
                created_at=job.created_at,
            )
            self._logger.info("Job %s: directories prepared: %s", job_id, directories)

            self._update(job_id, JobStatus.PREPARING_AUDIO, on_progress, "Preparing media", 10)
            source_path = Path(job.source_file_path)
            if not source_path.exists():
                self._logger.error("Job %s: source audio file not found: %s", job_id, source_path)
                raise FileNotFoundError(f"Source audio file not found: {source_path}")
            if not source_path.is_file():
                self._logger.error("Job %s: source audio path is not a file: %s", job_id, source_path)
                raise ValueError(f"Source audio path is not a file: {source_path}")
            
            staged_source = directories["source"] / source_path.name
            if not staged_source.exists():
                shutil.copy2(source_path, staged_source)

            self._update(job_id, JobStatus.PREPARING_AUDIO, on_progress, "Normalizing audio", 18)
            working_audio = directories["working"] / "working_audio.wav"
            normalized_audio = self._audio_normalizer.normalize(staged_source, working_audio)
            self._job_repository.update_working_audio_path(job_id, str(normalized_audio))
            self._logger.info("Job %s: normalized audio written: %s", job_id, normalized_audio)
            self._guard_not_cancelled(job_id)

            hints = self._job_repository.get_context_hints(job_id)
            hint_text = build_hint_text(hints)
            hotwords = hints.hotwords if hints is not None else []

            self._guard_not_cancelled(job_id)

            self._update(job_id, JobStatus.TRANSCRIBING, on_progress, "Running faster-whisper", 35)
            asr_progress = self._build_stage_progress_callback(
                job_id=job_id,
                status=JobStatus.TRANSCRIBING,
                on_progress=on_progress,
                start_percent=35,
                end_percent=59,
            )
            asr_result, asr_raw = self._asr_service.transcribe(
                job,
                normalized_audio,
                hint_text=hint_text,
                hotwords=hotwords,
                on_progress=asr_progress,
            )
            using_stub_pipeline = str(asr_raw.get("engine", "")).endswith("-stub")
            
            self._logger.debug("Job %s: Attempting to save ASR raw output", job_id)
            try:
                self._artifact_store.save_json(directories["raw"] / "asr_output.json", asr_raw)
                self._logger.debug("Job %s: ASR raw output saved successfully", job_id)
            except Exception as exc:
                self._logger.error("Job %s: Failed to save ASR raw output: %s", job_id, exc)
                raise # Re-raise to ensure job fails if artifacts cannot be saved

            self._logger.debug("Job %s: Attempting to update job status to TRANSCRIBING", job_id)
            try:
                self._job_repository.update_status(
                    job_id,
                    JobStatus.TRANSCRIBING,
                    language_detected=asr_result.language,
                )
                self._logger.debug("Job %s: Job status updated to TRANSCRIBING", job_id)
            except Exception as exc:
                self._logger.error("Job %s: Failed to update DB status to TRANSCRIBING: %s", job_id, exc)
                raise # Re-raise to ensure job fails if DB cannot be updated
            
            self._logger.info(
                "Job %s: ASR finished (language=%s, segments=%d)",
                job_id,
                asr_result.language,
                len(asr_result.segments),
            )
            self._logger.debug(
                "Job %s: ASR details duration_s=%s, raw_segments=%d",
                job_id,
                asr_result.duration_s,
                len(asr_result.segments),
            )
            if len(asr_result.segments) == 0:
                self._logger.warning("Job %s: ASR returned 0 segments (empty audio or unrecognized speech)", job_id)
            self._log_runtime_snapshot(job_id, "post-asr")
            self._release_service_resources(job_id, "asr", self._asr_service, reason="after-asr")
            self._guard_not_cancelled(job_id)

            diarization_result = None
            self._update(job_id, JobStatus.DIARIZING, on_progress, "Running pyannote diarization", 60)
            diarization_progress = self._build_stage_progress_callback(
                job_id=job_id,
                status=JobStatus.DIARIZING,
                on_progress=on_progress,
                start_percent=60,
                end_percent=77,
            )
            self._logger.debug("Job %s: Calling diarization service...", job_id)
            try:
                diarization_result, diarization_raw = self._diarization_service.diarize(
                    job,
                    normalized_audio,
                    on_progress=diarization_progress,
                )
                self._logger.debug("Job %s: Diarization service returned. Attempting to save raw output.", job_id)
                
                using_stub_pipeline = using_stub_pipeline or str(diarization_raw.get("engine", "")).endswith("-stub")
                try:
                    self._artifact_store.save_json(directories["raw"] / "diarization_output.json", diarization_raw)
                    self._logger.debug("Job %s: Diarization raw output saved successfully", job_id)
                except Exception as exc:
                    self._logger.error("Job %s: Failed to save Diarization raw output: %s", job_id, exc)
                    raise # Re-raise to ensure job fails if artifacts cannot be saved
                    
                self._logger.info(
                    "Job %s: diarization finished (engine=%s)",
                    job_id,
                    diarization_raw.get("engine", "<unknown>"),
                )
            except Exception as exc: # noqa: BLE001
                diarization_error = exc
                self._logger.exception("Job %s: Diarization failed", job_id) # Modificato il messaggio per chiarezza
                self._notify_progress(
                    on_progress,
                    JobStatus.DIARIZING,
                    f"Diarization failed: {exc}",
                    77,
                )
            self._log_runtime_snapshot(job_id, "post-diarization")

            self._guard_not_cancelled(job_id)
            self._update(job_id, JobStatus.ALIGNING, on_progress, "Aligning transcript with speakers", 78)
            transcript_doc = self._aligner.align(job_id, asr_result, diarization_result)

            self._guard_not_cancelled(job_id)
            try:
                self._job_repository.update_status(job_id, JobStatus.ALIGNING)
            except Exception as exc:  # noqa: BLE001
                self._logger.error("Job %s: failed to update DB status to ALIGNING: %s", job_id, exc)
                raise
            
            speakers_count = len(transcript_doc.speakers) if transcript_doc.speakers else 0
            segments_with_speaker = sum(1 for s in transcript_doc.segments if s.speaker_key)
            if speakers_count > 0 and segments_with_speaker == 0:
                self._logger.warning(
                    "Job %s: speakers detected (%d) but no segments have speaker assignment",
                    job_id,
                    speakers_count,
                )
            
            self._transcript_repository.replace_transcript(job_id, transcript_doc.segments, transcript_doc.speakers)

            export_payload = self._exporter.build_json(job, transcript_doc)
            self._logger.info("Job %s: exporting transcript files", job_id)
            try:
                self._artifact_store.save_json(directories["merged"] / "transcript.json", export_payload)
            except Exception as exc:  # noqa: BLE001
                self._logger.error("Job %s: failed to save merged transcript.json: %s", job_id, exc)
                raise

            self._guard_not_cancelled(job_id)
            self._update(job_id, JobStatus.READY_FOR_REVIEW, on_progress, "Preparing exports", 90)
            try:
                self._artifact_store.save_text(
                    directories["exports"] / "transcript.md",
                    self._exporter.build_markdown(job, transcript_doc),
                )
            except Exception as exc:  # noqa: BLE001
                self._logger.error("Job %s: failed to save transcript.md: %s", job_id, exc)
                raise
            self._guard_not_cancelled(job_id)
            try:
                self._artifact_store.save_text(
                    directories["exports"] / "transcript.txt",
                    self._exporter.build_txt(transcript_doc),
                )
            except Exception as exc:  # noqa: BLE001
                self._logger.error("Job %s: failed to save transcript.txt: %s", job_id, exc)
                raise
            self._guard_not_cancelled(job_id)
            try:
                self._artifact_store.save_json(directories["exports"] / "transcript.json", export_payload)
            except Exception as exc:  # noqa: BLE001
                self._logger.error("Job %s: failed to save exports/transcript.json: %s", job_id, exc)
                raise
            self._guard_not_cancelled(job_id)
            try:
                self._artifact_store.save_text(
                    directories["exports"] / "transcript.srt",
                    self._exporter.build_srt(transcript_doc),
                )
            except Exception as exc:  # noqa: BLE001
                self._logger.error("Job %s: failed to save transcript.srt: %s", job_id, exc)
                raise
            self._guard_not_cancelled(job_id)

            if using_stub_pipeline:
                self._job_repository.update_status(
                    job_id,
                    JobStatus.PARTIAL_SUCCESS,
                    error_message="Stub pipeline active: output is demo-only and not a real transcription.",
                    completed=True,
                    execution_duration_seconds=elapsed_seconds(),
                )
                self._notify_progress(on_progress, JobStatus.PARTIAL_SUCCESS, "Completed in demo mode (stub pipeline)", 100)
                self._logger.warning("Job completed in stub mode: %s", job_id)
                return JobStatus.PARTIAL_SUCCESS

            if diarization_error is None:
                self._job_repository.update_status(
                    job_id,
                    JobStatus.COMPLETED,
                    completed=True,
                    execution_duration_seconds=elapsed_seconds(),
                )
                self._notify_progress(on_progress, JobStatus.COMPLETED, "Completed", 100)
                self._logger.info("Job completed: %s", job_id)
                return JobStatus.COMPLETED

            self._job_repository.update_status(
                job_id,
                JobStatus.PARTIAL_SUCCESS,
                error_message=f"Diarization failed: {diarization_error}",
                completed=True,
                execution_duration_seconds=elapsed_seconds(),
            )
            self._notify_progress(on_progress, JobStatus.PARTIAL_SUCCESS, f"Completed without speaker diarization ({diarization_error})", 100)
            self._logger.warning("Job partial success: %s", job_id)
            return JobStatus.PARTIAL_SUCCESS
        except JobCancelledError:
            self._job_repository.update_status(
                job_id,
                JobStatus.CANCELLED,
                completed=True,
                execution_duration_seconds=elapsed_seconds(),
            )
            self._notify_progress(on_progress, JobStatus.CANCELLED, "Cancelled by user", 100)
            self._logger.warning("Job cancelled: %s", job_id)
            return JobStatus.CANCELLED
        except Exception as exc:  # noqa: BLE001
            self._job_repository.update_status(
                job_id,
                JobStatus.FAILED,
                error_message=str(exc),
                completed=True,
                execution_duration_seconds=elapsed_seconds(),
            )
            self._logger.exception("Job failed: %s", job_id)
            raise
        finally:
            self._cancelled_jobs.discard(job_id)
            self._release_runtime_resources(job_id)
            self._log_runtime_snapshot(job_id, "job-finalized")
            self._logger.info("Job %s: cleanup done", job_id)

    def _update(
        self,
        job_id: str,
        status: JobStatus,
        on_progress: ProgressCallback | None,
        message: str,
        progress: int,
    ) -> None:
        self._guard_not_cancelled(job_id)
        self._job_repository.update_status(job_id, status)
        self._notify_progress(on_progress, status, message, progress)

    @staticmethod
    def _notify_progress(
        on_progress: ProgressCallback | None,
        status: JobStatus,
        message: str,
        progress: int,
    ) -> None:
        if on_progress is not None:
            on_progress(status, message, progress)

    def _build_stage_progress_callback(
        self,
        *,
        job_id: str,
        status: JobStatus,
        on_progress: ProgressCallback | None,
        start_percent: int,
        end_percent: int,
    ) -> StageDetailCallback:
        current_percent = start_percent

        def callback(message: str, progress_fraction: float | None = None) -> None:
            nonlocal current_percent

            self._guard_not_cancelled(job_id)

            next_percent = current_percent
            if progress_fraction is not None:
                try:
                    fraction = float(progress_fraction)
                    fraction = min(max(fraction, 0.0), 1.0)
                    mapped = start_percent + int((end_percent - start_percent) * fraction)
                    next_percent = max(current_percent, min(end_percent, mapped))
                except (TypeError, ValueError):
                    next_percent = current_percent
            elif current_percent < (end_percent - 1):
                # Keep the bar moving on heartbeat-only updates to avoid a "stuck" perception.
                next_percent = current_percent + 1

            current_percent = next_percent
            self._notify_progress(on_progress, status, message, current_percent)

        return callback

    def _guard_not_cancelled(self, job_id: str) -> None:
        if job_id in self._cancelled_jobs:
            raise JobCancelledError("Job cancelled")

    def _release_runtime_resources(self, job_id: str) -> None:
        self._release_service_resources(job_id, "asr", self._asr_service, reason="job-finalize")

        release_diarization = False
        rss_mb, private_mb = self._read_process_memory_mb()
        if self._memory_guard_enabled and private_mb is not None and private_mb >= self._memory_guard_private_mb_threshold:
            if self._memory_guard_release_diarization:
                release_diarization = True
                self._logger.warning(
                    "Runtime memory guard: high private memory before finalize cleanup "
                    "(job=%s, private_mb=%.1f, threshold_mb=%.1f). Releasing diarization cache.",
                    job_id,
                    private_mb,
                    self._memory_guard_private_mb_threshold,
                )
            else:
                self._logger.warning(
                    "Runtime memory guard: high private memory before finalize cleanup "
                    "(job=%s, private_mb=%.1f, threshold_mb=%.1f), but diarization cache release is disabled.",
                    job_id,
                    private_mb,
                    self._memory_guard_private_mb_threshold,
                )

        if release_diarization:
            self._release_service_resources(
                job_id,
                "diarization",
                self._diarization_service,
                reason="job-finalize-memory-guard",
            )
        else:
            self._logger.debug(
                "Runtime memory guard: keeping diarization pipeline cached "
                "(job=%s, rss_mb=%s, private_mb=%s)",
                job_id,
                f"{rss_mb:.1f}" if rss_mb is not None else "n/a",
                f"{private_mb:.1f}" if private_mb is not None else "n/a",
            )

        gc.collect()
        if self._memory_guard_enabled and self._memory_guard_trim_working_set:
            self._trim_process_working_set()

    def _release_service_resources(self, job_id: str, service_name: str, service: object, *, reason: str) -> None:
        release_resources = getattr(service, "release_resources", None)
        if not callable(release_resources):
            return

        try:
            release_resources()
            self._logger.info(
                "Runtime safe mode: released %s resources for job %s (%s)",
                service_name,
                job_id,
                reason,
            )
        except Exception as exc:  # noqa: BLE001
            self._logger.warning(
                "Runtime safe mode: failed to release %s resources for job %s (%s): %s",
                service_name,
                job_id,
                reason,
                exc,
            )

    def _log_runtime_snapshot(self, job_id: str, stage: str) -> None:
        rss_mb, private_mb = self._read_process_memory_mb()
        if rss_mb is None:
            self._logger.info("Runtime snapshot | job=%s | stage=%s", job_id, stage)
            return
        if private_mb is None:
            self._logger.info("Runtime snapshot | job=%s | stage=%s | rss_mb=%.1f", job_id, stage, rss_mb)
            return
        self._logger.info(
            "Runtime snapshot | job=%s | stage=%s | rss_mb=%.1f | private_mb=%.1f",
            job_id,
            stage,
            rss_mb,
            private_mb,
        )

    @staticmethod
    def _read_process_memory_mb() -> tuple[float | None, float | None]:
        if os.name != "nt":
            return None, None

        try:
            class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                    ("PrivateUsage", ctypes.c_size_t),
                ]

            counters = PROCESS_MEMORY_COUNTERS_EX()
            counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS_EX)

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            psapi = ctypes.WinDLL("psapi", use_last_error=True)

            kernel32.GetCurrentProcess.restype = wintypes.HANDLE
            psapi.GetProcessMemoryInfo.argtypes = [
                wintypes.HANDLE,
                ctypes.POINTER(PROCESS_MEMORY_COUNTERS_EX),
                wintypes.DWORD,
            ]
            psapi.GetProcessMemoryInfo.restype = wintypes.BOOL

            process_handle = kernel32.GetCurrentProcess()

            ok = psapi.GetProcessMemoryInfo(
                process_handle,
                ctypes.byref(counters),
                counters.cb,
            )
            if not bool(ok):
                return None, None

            to_mb = float(1024 * 1024)
            rss_mb = float(counters.WorkingSetSize) / to_mb
            private_mb = float(counters.PrivateUsage) / to_mb
            return rss_mb, private_mb
        except Exception:  # noqa: BLE001
            return None, None

    def _run_pre_job_memory_guard(self, job_id: str) -> None:
        if not self._memory_guard_enabled:
            return

        rss_mb, private_mb = self._read_process_memory_mb()
        if private_mb is None or private_mb < self._memory_guard_private_mb_threshold:
            return

        self._logger.warning(
            "Runtime memory guard: high private memory before job start "
            "(job=%s, rss_mb=%s, private_mb=%.1f, threshold_mb=%.1f). Running aggressive cleanup.",
            job_id,
            f"{rss_mb:.1f}" if rss_mb is not None else "n/a",
            private_mb,
            self._memory_guard_private_mb_threshold,
        )
        self._release_service_resources(job_id, "asr", self._asr_service, reason="pre-job-memory-guard")
        if self._memory_guard_release_diarization:
            self._release_service_resources(
                job_id,
                "diarization",
                self._diarization_service,
                reason="pre-job-memory-guard",
            )
        else:
            self._logger.warning(
                "Runtime memory guard: pre-job cleanup skipped diarization release (disabled by configuration)."
            )
        gc.collect()
        if self._memory_guard_trim_working_set:
            self._trim_process_working_set()
        self._log_runtime_snapshot(job_id, "pre-job-memory-guard")

    def _trim_process_working_set(self) -> None:
        if os.name != "nt":
            return

        try:
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            psapi = ctypes.WinDLL("psapi", use_last_error=True)

            kernel32.GetCurrentProcess.restype = wintypes.HANDLE
            psapi.EmptyWorkingSet.argtypes = [wintypes.HANDLE]
            psapi.EmptyWorkingSet.restype = wintypes.BOOL

            process_handle = kernel32.GetCurrentProcess()
            ok = bool(psapi.EmptyWorkingSet(process_handle))
            self._logger.debug("Runtime memory guard: EmptyWorkingSet invoked (ok=%s)", ok)
        except Exception as exc:  # noqa: BLE001
            self._logger.debug("Runtime memory guard: EmptyWorkingSet failed: %s", exc)

    @staticmethod
    def _parse_bool_env(name: str, *, default: bool) -> bool:
        raw_value = os.getenv(name)
        if raw_value is None:
            return default
        return raw_value.strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _parse_float_env(name: str, *, default: float, minimum: float) -> float:
        raw_value = os.getenv(name)
        if raw_value is None:
            return default
        try:
            parsed = float(raw_value.strip())
        except (TypeError, ValueError):
            return default
        if parsed < minimum:
            return minimum
        return parsed
