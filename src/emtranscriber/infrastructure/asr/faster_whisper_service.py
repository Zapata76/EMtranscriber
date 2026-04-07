from __future__ import annotations

import gc
import logging
import os
import sys
import threading
import time
from collections.abc import Callable
from importlib import import_module
from pathlib import Path

from emtranscriber.domain.entities.job import Job
from emtranscriber.domain.pipeline.asr_types import AsrResult, AsrSegment, AsrWord
from emtranscriber.infrastructure.settings.app_settings import AppSettings

AsrProgressCallback = Callable[[str, float | None], None]


class FasterWhisperService:
    def __init__(self, settings: AppSettings, logger: logging.Logger) -> None:
        self._settings = settings
        self._logger = logger
        self._models: dict[tuple[str, str, str], object] = {}

    def transcribe(
        self,
        job: Job,
        audio_path: Path,
        *,
        hint_text: str,
        hotwords: list[str],
        on_progress: AsrProgressCallback | None = None,
    ) -> tuple[AsrResult, dict]:
        model_name = job.model_name or self._settings.default_asr_model
        self._emit_progress(on_progress, f"Loading ASR model '{model_name}'", 0.02)

        whisper_model = self._load_model(job)
        self._emit_progress(on_progress, "ASR model ready. Initializing decoder", 0.08)

        language = None if (job.language_selected or "auto") == "auto" else job.language_selected
        options = {
            "word_timestamps": True,
            "vad_filter": True,
            "language": language,
            "initial_prompt": hint_text or None,
            "hotwords": ", ".join(hotwords) if hotwords else None,
        }

        self._logger.info(
            "ASR started | model=%s | device=%s | compute=%s",
            job.model_name,
            job.device_used,
            job.compute_type,
        )

        self._emit_progress(on_progress, "Decoder started", 0.12)
        segments_iter, info = whisper_model.transcribe(str(audio_path), **options)

        duration_s = self._safe_float(getattr(info, "duration", None))
        if duration_s and duration_s > 0:
            self._emit_progress(
                on_progress,
                f"Audio duration detected: {self._format_seconds(duration_s)}",
                0.15,
            )

        segments: list[AsrSegment] = []
        raw_segments: list[dict] = []

        heartbeat_stop = threading.Event()
        heartbeat_state: dict[str, float | int] = {"segments": 0, "estimated_segments": 0, "last_end_s": 0.0, "duration_s": duration_s or 0.0}
        heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            args=(heartbeat_stop, heartbeat_state, on_progress),
            daemon=True,
        )
        heartbeat_thread.start()

        last_report = time.monotonic()
        try:
            for seg in segments_iter:
                words = [
                    AsrWord(
                        text=(word.word or "").strip(),
                        start_s=float(word.start or seg.start),
                        end_s=float(word.end or seg.end),
                        probability=float(word.probability) if word.probability is not None else None,
                    )
                    for word in (seg.words or [])
                ]
                segment = AsrSegment(
                    text=(seg.text or "").strip(),
                    start_s=float(seg.start),
                    end_s=float(seg.end),
                    words=words,
                    avg_logprob=float(seg.avg_logprob) if seg.avg_logprob is not None else None,
                )
                segments.append(segment)
                heartbeat_state["segments"] = len(segments)
                heartbeat_state["last_end_s"] = float(segment.end_s)
                estimated_total = self._estimate_total_segments(
                    decoded_segments=len(segments),
                    decoded_audio_s=float(segment.end_s),
                    duration_s=duration_s,
                    previous_estimate=int(heartbeat_state.get("estimated_segments", 0) or 0),
                )
                if estimated_total is not None:
                    heartbeat_state["estimated_segments"] = estimated_total

                raw_segments.append(
                    {
                        "start": segment.start_s,
                        "end": segment.end_s,
                        "text": segment.text,
                        "avg_logprob": segment.avg_logprob,
                        "words": [
                            {
                                "text": word.text,
                                "start": word.start_s,
                                "end": word.end_s,
                                "probability": word.probability,
                            }
                            for word in words
                        ],
                    }
                )

                now = time.monotonic()
                should_report = len(segments) <= 3 or (now - last_report) >= 2.0
                if should_report:
                    progress = self._estimate_segment_progress(segment.end_s, duration_s)
                    decoded_at = self._format_seconds(segment.end_s)
                    estimated_for_message = int(heartbeat_state.get("estimated_segments", 0) or 0)
                    if duration_s and duration_s > 0:
                        if estimated_for_message > 0:
                            message = (
                                f"Decoded segment {len(segments)}/{estimated_for_message} "
                                f"(audio {decoded_at}/{self._format_seconds(duration_s)})"
                            )
                        else:
                            message = (
                                f"Decoded segment {len(segments)} "
                                f"(audio {decoded_at}/{self._format_seconds(duration_s)})"
                            )
                    else:
                        message = f"Decoded segment {len(segments)} (ends at {decoded_at})"
                    self._emit_progress(on_progress, message, progress)
                    last_report = now
        finally:
            heartbeat_stop.set()
            heartbeat_thread.join(timeout=0.5)

        if segments:
            self._emit_progress(on_progress, f"ASR completed: {len(segments)} segments", 1.0)
        else:
            self._emit_progress(on_progress, "ASR completed with no segments", 1.0)

        result = AsrResult(
            language=getattr(info, "language", None),
            duration_s=duration_s,
            segments=segments,
        )

        raw = {
            "engine": "faster-whisper",
            "model": job.model_name,
            "language": result.language,
            "duration_s": result.duration_s,
            "segments": raw_segments,
            "options": options,
        }

        return result, raw

    def _load_model(self, job: Job):
        self._prepare_download_runtime()

        try:
            whisper_pkg = import_module("faster_whisper")
            WhisperModel = getattr(whisper_pkg, "WhisperModel")
        except ModuleNotFoundError as exc:
            missing = exc.name or str(exc)
            raise RuntimeError(
                f"faster-whisper runtime dependency missing: {missing}. "
                "Install optional ML dependencies and ensure the related site-packages path is visible to EMtranscriber."
            ) from exc
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"faster-whisper initialization failed: {exc}") from exc

        model_ref = self._resolve_model_ref(job.model_name or self._settings.default_asr_model)
        device = self._resolve_device(job.device_used)
        compute_type = self._resolve_compute_type(job.compute_type)

        cache_key = (model_ref, device, compute_type)
        if cache_key not in self._models:
            self._logger.debug(
                "Loading ASR model: ref=%s, device=%s, compute_type=%s",
                model_ref,
                device,
                compute_type,
            )
            self._models[cache_key] = WhisperModel(model_ref, device=device, compute_type=compute_type)
            self._logger.debug("ASR model loaded and cached: %s", model_ref)
        else:
            self._logger.debug("Using cached ASR model: %s (device=%s, compute=%s)", model_ref, device, compute_type)

        return self._models[cache_key]

    def release_resources(self) -> None:
        cached_models = len(self._models)
        self._models.clear()

        try:
            torch = import_module("torch")
            cuda = getattr(torch, "cuda", None)
            if cuda is not None and callable(getattr(cuda, "is_available", None)) and cuda.is_available():
                cuda.empty_cache()
        except Exception:  # noqa: BLE001
            pass

        gc.collect()
        self._logger.info("ASR resources released (cached_models=%d)", cached_models)

    def _resolve_model_ref(self, model_name: str) -> str:
        override = self._settings.asr_model_paths.get(model_name)
        if override:
            return override
        return model_name

    @staticmethod
    def _resolve_device(device: str | None) -> str:
        if device in {"cpu", "gpu", "auto"}:
            return "cuda" if device == "gpu" else device
        return "auto"

    @staticmethod
    def _resolve_compute_type(compute_type: str | None) -> str:
        if not compute_type or compute_type == "auto":
            return "default"
        return compute_type

    @staticmethod
    def _emit_progress(callback: AsrProgressCallback | None, message: str, progress: float | None = None) -> None:
        if callback is not None:
            callback(message, progress)

    @staticmethod
    def _prepare_download_runtime() -> None:
        if sys.stdout is None:
            sys.stdout = open(os.devnull, "w", encoding="utf-8")
        if sys.stderr is None:
            sys.stderr = open(os.devnull, "w", encoding="utf-8")

        os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
        os.environ.setdefault("TQDM_DISABLE", "1")

        try:
            hub_utils = import_module("huggingface_hub.utils")
            disable_progress_bars = getattr(hub_utils, "disable_progress_bars", None)
            if callable(disable_progress_bars):
                disable_progress_bars()
        except Exception:
            return

    @staticmethod
    def _estimate_segment_progress(segment_end_s: float, duration_s: float | None) -> float | None:
        if duration_s is None or duration_s <= 0:
            return None
        return min(max(segment_end_s / duration_s, 0.0), 0.99)

    @staticmethod
    def _estimate_total_segments(
        *,
        decoded_segments: int,
        decoded_audio_s: float,
        duration_s: float | None,
        previous_estimate: int,
    ) -> int | None:
        if duration_s is None or duration_s <= 0:
            return None
        if decoded_segments < 8 or decoded_audio_s <= 0:
            return previous_estimate if previous_estimate > 0 else None

        ratio = min(max(decoded_audio_s / duration_s, 0.01), 1.0)
        estimate = max(decoded_segments, int(round(decoded_segments / ratio)))
        if previous_estimate > 0:
            estimate = max(estimate, previous_estimate)
        return min(estimate, 5000)

    def _heartbeat_loop(
        self,
        stop_event: threading.Event,
        state: dict[str, float | int],
        callback: AsrProgressCallback | None,
    ) -> None:
        started = time.monotonic()
        while not stop_event.wait(8.0):
            elapsed = self._format_seconds(time.monotonic() - started)
            decoded_segments = int(state.get("segments", 0) or 0)
            estimated_segments = int(state.get("estimated_segments", 0) or 0)
            if decoded_segments > 0 and estimated_segments > 0:
                message = (
                    f"ASR still running... elapsed {elapsed}, "
                    f"segments decoded: {decoded_segments}/{estimated_segments}"
                )
            elif decoded_segments > 0:
                message = f"ASR still running... elapsed {elapsed}, segments decoded: {decoded_segments}"
            else:
                message = f"ASR still running... elapsed {elapsed}, waiting for first segment"
            self._emit_progress(callback, message, None)

    @staticmethod
    def _safe_float(value) -> float | None:
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _format_seconds(value: float) -> str:
        total_seconds = max(0, int(value))
        minutes, seconds = divmod(total_seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"


