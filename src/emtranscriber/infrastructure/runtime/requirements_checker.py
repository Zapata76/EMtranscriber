from __future__ import annotations

import importlib.util
import shutil
from dataclasses import dataclass

from emtranscriber.infrastructure.settings.app_settings import AppSettings


@dataclass(slots=True)
class RuntimeIssue:
    key: str
    details: str
    fix: str
    critical: bool = True


@dataclass(slots=True)
class RuntimeReport:
    issues: list[RuntimeIssue]

    @property
    def has_critical(self) -> bool:
        return any(issue.critical for issue in self.issues)

    @property
    def is_ok(self) -> bool:
        return not self.issues


def check_runtime_requirements(settings: AppSettings) -> RuntimeReport:
    issues: list[RuntimeIssue] = []

    for module_name, label in (
        ("faster_whisper", "faster-whisper"),
        ("ctranslate2", "ctranslate2"),
        ("torch", "torch"),
        ("torchaudio", "torchaudio"),
        ("pyannote.audio", "pyannote.audio"),
    ):
        if not _is_module_available(module_name):
            issues.append(
                RuntimeIssue(
                    key=f"module:{module_name}",
                    details=f"Missing Python module: {label}",
                    fix="Install ML runtime dependencies.",
                    critical=True,
                )
            )

    if shutil.which("ffmpeg") is None:
        issues.append(
            RuntimeIssue(
                key="tool:ffmpeg",
                details="ffmpeg not found in PATH (recommended for robust media normalization).",
                fix="Install FFmpeg and add it to PATH.",
                critical=False,
            )
        )

    if not settings.pyannote_model_path and not settings.huggingface_token:
        issues.append(
            RuntimeIssue(
                key="config:hf_token",
                details="Hugging Face token is not configured. Diarization may fail on gated model download.",
                fix="Set Hugging Face token in Settings, or configure a local pyannote model path.",
                critical=False,
            )
        )

    return RuntimeReport(issues=issues)


def install_command_candidates() -> list[str]:
    return [
        "py -m pip install --user -r requirements-ml.txt",
        "python -m pip install --user -r requirements-ml.txt",
    ]


def _is_module_available(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False
