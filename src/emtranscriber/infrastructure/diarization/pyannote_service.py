from __future__ import annotations

import logging
import os
import sys
import threading
import time
import warnings
from collections.abc import Callable
from importlib import import_module
from pathlib import Path

from emtranscriber.domain.entities.job import Job
from emtranscriber.domain.pipeline.diarization_types import DiarizationResult, SpeakerTurn
from emtranscriber.infrastructure.settings.app_settings import AppSettings

DiarizationProgressCallback = Callable[[str, float | None], None]


class _DiarizationProgressState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._step_name: str | None = None
        self._completed: int | None = None
        self._total: int | None = None

    def update(self, *, step_name: str | None, completed: int | None, total: int | None) -> None:
        with self._lock:
            self._step_name = step_name
            self._completed = completed
            self._total = total

    def snapshot(self) -> tuple[str | None, int | None, int | None]:
        with self._lock:
            return self._step_name, self._completed, self._total


class PyannoteDiarizationService:
    def __init__(self, settings: AppSettings, logger: logging.Logger) -> None:
        self._settings = settings
        self._logger = logger
        self._pipeline = None

    def diarize(
        self,
        job: Job,
        audio_path: Path,
        on_progress: DiarizationProgressCallback | None = None,
    ) -> tuple[DiarizationResult, dict]:
        self._emit_progress(on_progress, "Loading diarization pipeline", 0.05)
        pipeline = self._load_pipeline(job, on_progress=on_progress)

        options = self._speaker_options(job)
        self._emit_progress(on_progress, "Running diarization inference", 0.25)

        diarization_input = self._build_pipeline_input(audio_path, on_progress=on_progress)
        progress_state = _DiarizationProgressState()
        hook = self._build_pipeline_hook(on_progress, progress_state)

        inference_stop = threading.Event()
        inference_thread = threading.Thread(
            target=self._heartbeat_loop,
            args=(inference_stop, on_progress, "Diarization still running", progress_state),
            daemon=True,
        )
        inference_thread.start()
        try:
            diarization = self._run_pipeline_with_hook(
                pipeline,
                diarization_input,
                options,
                hook,
                on_progress=on_progress,
            )
        finally:
            inference_stop.set()
            inference_thread.join(timeout=0.5)

        annotation = getattr(diarization, "exclusive_speaker_diarization", diarization)

        turns: list[SpeakerTurn] = []
        for idx, (turn, _, speaker) in enumerate(annotation.itertracks(yield_label=True), start=1):
            turns.append(
                SpeakerTurn(
                    start_s=float(turn.start),
                    end_s=float(turn.end),
                    speaker_label=str(speaker),
                )
            )
            if idx <= 3 or idx % 25 == 0:
                self._emit_progress(on_progress, f"Collected {idx} speaker turns", 0.8)

        turns.sort(key=lambda t: (t.start_s, t.end_s))
        result = DiarizationResult(turns=turns)

        self._emit_progress(on_progress, f"Diarization completed: {len(turns)} turns", 1.0)

        raw = {
            "engine": "pyannote/speaker-diarization-community-1",
            "model_source": self._resolve_model_source(),
            "input_mode": "waveform" if isinstance(diarization_input, dict) else "path",
            "options": options,
            "turns": [
                {
                    "start": turn.start_s,
                    "end": turn.end_s,
                    "speaker": turn.speaker_label,
                }
                for turn in turns
            ],
        }

        return result, raw

    def _load_pipeline(
        self,
        job: Job,
        *,
        on_progress: DiarizationProgressCallback | None = None,
    ):
        if self._pipeline is not None:
            self._emit_progress(on_progress, "Using cached diarization model", 0.12)
            return self._pipeline

        try:
            pyannote_audio = import_module("pyannote.audio")
            Pipeline = getattr(pyannote_audio, "Pipeline")
        except ModuleNotFoundError as exc:
            missing = exc.name or str(exc)
            if missing in {"pyannote", "pyannote.audio"}:
                raise RuntimeError(
                    "pyannote.audio is not installed. Install optional ML dependencies before running diarization."
                ) from exc
            raise RuntimeError(
                f"pyannote runtime dependency missing: {missing}. "
                "Install optional ML dependencies and ensure related site-packages are visible to EMtranscriber."
            ) from exc
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"pyannote initialization failed: {exc}") from exc

        model_source = self._resolve_model_source()
        token = self._settings.huggingface_token
        kwargs = {"token": token} if token else {}

        self._emit_progress(on_progress, f"Loading diarization model source '{model_source}'", 0.15)
        self._prepare_download_runtime()
        model_load_stop = threading.Event()
        model_load_thread = threading.Thread(
            target=self._heartbeat_loop,
            args=(model_load_stop, on_progress, "Downloading/loading diarization model"),
            daemon=True,
        )
        model_load_thread.start()
        try:
            self._pipeline = Pipeline.from_pretrained(model_source, **kwargs)
        except Exception as exc:  # noqa: BLE001
            message = str(exc)
            if "gated" in message.lower() or "401" in message.lower() or "access to model" in message.lower():
                raise RuntimeError(
                    "pyannote model access denied. Accept model terms on Hugging Face and set a valid token in Settings."
                ) from exc
            raise
        finally:
            model_load_stop.set()
            model_load_thread.join(timeout=0.5)

        if job.device_used == "gpu":
            try:
                torch = import_module("torch")
                self._pipeline.to(torch.device("cuda"))
                self._emit_progress(on_progress, "Diarization pipeline moved to CUDA", 0.2)
            except Exception:  # noqa: BLE001
                self._logger.warning("GPU requested for diarization but CUDA is not available. Falling back to CPU.")
                self._emit_progress(on_progress, "CUDA unavailable for diarization, using CPU", 0.2)

        return self._pipeline

    def _resolve_model_source(self) -> str:
        if self._settings.pyannote_model_path:
            return self._settings.pyannote_model_path
        return "pyannote/speaker-diarization-community-1"

    def _build_pipeline_input(
        self,
        audio_path: Path,
        *,
        on_progress: DiarizationProgressCallback | None = None,
    ):
        if self._has_torchcodec_decoder():
            return str(audio_path)

        self._emit_progress(
            on_progress,
            "TorchCodec decoder unavailable. Using in-memory fallback decoding",
            0.24,
        )

        decode_errors: list[str] = []

        try:
            waveform, sample_rate = self._decode_audio_with_faster_whisper(audio_path)
            backend = "faster-whisper"
        except Exception as exc_fw:  # noqa: BLE001
            decode_errors.append(f"faster-whisper: {exc_fw}")
            self._logger.warning("faster-whisper fallback decoding failed for %s: %s", audio_path, exc_fw)
            try:
                waveform, sample_rate = self._decode_audio_with_torchaudio(audio_path)
                backend = "torchaudio"
            except Exception as exc_ta:  # noqa: BLE001
                decode_errors.append(f"torchaudio: {exc_ta}")
                self._logger.warning("torchaudio fallback decoding failed for %s: %s", audio_path, exc_ta)
                try:
                    waveform, sample_rate = self._decode_audio_with_wave(audio_path)
                    backend = "wave"
                except Exception as exc_wave:  # noqa: BLE001
                    decode_errors.append(f"wave: {exc_wave}")
                    details = " | ".join(decode_errors)
                    raise RuntimeError(
                        "Unable to decode audio for diarization fallback. "
                        "Install FFmpeg/TorchCodec dependencies or use a full ML runtime. "
                        f"Decoding backends tried: {details}"
                    ) from exc_wave

        duration_s = 0.0
        try:
            samples = int(waveform.shape[-1])
            duration_s = samples / float(sample_rate) if sample_rate else 0.0
        except Exception:  # noqa: BLE001
            duration_s = 0.0

        if duration_s > 0:
            self._emit_progress(
                on_progress,
                f"Loaded fallback waveform via {backend} ({self._format_seconds(duration_s)})",
                0.24,
            )

        return {"waveform": waveform, "sample_rate": int(sample_rate), "uri": audio_path.stem}

    @staticmethod
    def _decode_audio_with_faster_whisper(audio_path: Path):
        fw_audio = import_module("faster_whisper.audio")
        decode_audio = getattr(fw_audio, "decode_audio")
        audio_np = decode_audio(str(audio_path), sampling_rate=16000, split_stereo=False)

        torch = import_module("torch")
        waveform = torch.from_numpy(audio_np).unsqueeze(0)
        return waveform, 16000

    @staticmethod
    def _decode_audio_with_torchaudio(audio_path: Path):
        torchaudio = import_module("torchaudio")
        return torchaudio.load(str(audio_path))

    @staticmethod
    def _decode_audio_with_wave(audio_path: Path):
        import wave

        torch = import_module("torch")

        with wave.open(str(audio_path), "rb") as wav_file:
            if wav_file.getcomptype() != "NONE":
                raise RuntimeError(f"compressed WAV not supported ({wav_file.getcomptype()})")

            channels = int(wav_file.getnchannels())
            sample_rate = int(wav_file.getframerate())
            sample_width = int(wav_file.getsampwidth())
            frame_count = int(wav_file.getnframes())
            payload = wav_file.readframes(frame_count)

        if channels <= 0 or frame_count <= 0:
            raise RuntimeError("empty waveform")

        if sample_width == 1:
            samples = torch.frombuffer(memoryview(payload), dtype=torch.uint8).clone().to(torch.float32)
            samples = (samples - 128.0) / 128.0
        elif sample_width == 2:
            samples = torch.frombuffer(memoryview(payload), dtype=torch.int16).clone().to(torch.float32)
            samples = samples / 32768.0
        elif sample_width == 4:
            samples = torch.frombuffer(memoryview(payload), dtype=torch.int32).clone().to(torch.float32)
            samples = samples / 2147483648.0
        else:
            raise RuntimeError(f"unsupported WAV sample width: {sample_width}")

        waveform = samples.reshape(-1, channels).transpose(0, 1).contiguous()
        return waveform, sample_rate

    @staticmethod
    def _has_torchcodec_decoder() -> bool:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                io_module = import_module("pyannote.audio.core.io")
            return hasattr(io_module, "AudioDecoder")
        except Exception:  # noqa: BLE001
            return False

    @staticmethod
    def _speaker_options(job: Job) -> dict:
        mode = (job.speaker_count_mode or "auto").lower()

        if mode == "exact" and job.exact_speakers:
            return {"num_speakers": int(job.exact_speakers)}
        if mode == "minmax":
            payload: dict[str, int] = {}
            if job.min_speakers:
                payload["min_speakers"] = int(job.min_speakers)
            if job.max_speakers:
                payload["max_speakers"] = int(job.max_speakers)
            return payload
        return {}

    def _run_pipeline_with_hook(
        self,
        pipeline,
        diarization_input,
        options: dict,
        hook,
        *,
        on_progress: DiarizationProgressCallback | None,
    ):
        try:
            return pipeline(diarization_input, hook=hook, **options)
        except TypeError as exc:
            if "hook" not in str(exc).lower():
                raise
            self._logger.debug("Diarization pipeline does not support progress hook: %s", exc)
            self._emit_progress(
                on_progress,
                "Diarization progress hook unavailable. Falling back to heartbeat-only updates",
                0.26,
            )
            return pipeline(diarization_input, **options)

    def _build_pipeline_hook(
        self,
        callback: DiarizationProgressCallback | None,
        state: _DiarizationProgressState,
    ):
        def hook(step_name: str, _artifact=None, **kwargs) -> None:
            completed = self._coerce_progress_count(kwargs.get("completed"))
            total = self._coerce_progress_count(kwargs.get("total"))
            step_label = self._humanize_step_name(step_name)
            state.update(step_name=step_label, completed=completed, total=total)

            progress = self._estimate_hook_progress(step_name, completed=completed, total=total)
            if completed is not None and total is not None and total > 0:
                message = f"Diarization {step_label}: {completed}/{total}"
            else:
                message = f"Diarization step: {step_label}"
            self._emit_progress(callback, message, progress)

        return hook

    @staticmethod
    def _coerce_progress_count(value) -> int | None:
        try:
            if value is None:
                return None
            return max(0, int(value))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _humanize_step_name(step_name: str | None) -> str:
        mapping = {
            "segmentation": "segmentation",
            "speaker_counting": "speaker counting",
            "embeddings": "embeddings",
            "discrete_diarization": "diarization reconstruction",
        }
        if not step_name:
            return "processing"
        return mapping.get(step_name, str(step_name).replace("_", " "))

    @staticmethod
    def _estimate_hook_progress(step_name: str, *, completed: int | None, total: int | None) -> float:
        # Keep diarization progress monotonic and map internal steps to coarse ranges.
        ranges = {
            "segmentation": (0.30, 0.56),
            "speaker_counting": (0.57, 0.62),
            "embeddings": (0.63, 0.90),
            "discrete_diarization": (0.91, 0.97),
        }
        start, end = ranges.get(step_name, (0.30, 0.95))
        if completed is not None and total is not None and total > 0:
            ratio = min(max(float(completed) / float(total), 0.0), 1.0)
            return start + ((end - start) * ratio)
        return start

    @staticmethod
    def _heartbeat_details(state: _DiarizationProgressState | None) -> str | None:
        if state is None:
            return None
        step_name, completed, total = state.snapshot()
        if step_name is None:
            return None
        if completed is not None and total is not None and total > 0:
            return f"{step_name}: {completed}/{total}"
        return f"step: {step_name}"

    @staticmethod
    def _emit_progress(
        callback: DiarizationProgressCallback | None,
        message: str,
        progress: float | None = None,
    ) -> None:
        if callback is not None:
            callback(message, progress)

    def _prepare_download_runtime(self) -> None:
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
        except Exception as exc:  # noqa: BLE001
            self._logger.debug("Unable to force-disable Hugging Face progress bars: %s", exc)

    def _heartbeat_loop(
        self,
        stop_event: threading.Event,
        callback: DiarizationProgressCallback | None,
        prefix: str,
        state: _DiarizationProgressState | None = None,
    ) -> None:
        started = time.monotonic()
        while not stop_event.wait(8.0):
            elapsed = self._format_seconds(time.monotonic() - started)
            details = self._heartbeat_details(state)
            if details:
                self._emit_progress(callback, f"{prefix} ({details})... elapsed {elapsed}", None)
                continue
            self._emit_progress(callback, f"{prefix}... elapsed {elapsed}", None)

    @staticmethod
    def _format_seconds(value: float) -> str:
        total_seconds = max(0, int(value))
        minutes, seconds = divmod(total_seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"


