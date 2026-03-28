from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path


class AudioNormalizer:
    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger

    def normalize(self, source_path: Path, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)

        ffmpeg_path = shutil.which("ffmpeg")
        if ffmpeg_path:
            cmd = [
                ffmpeg_path,
                "-y",
                "-i",
                str(source_path),
                "-ac",
                "1",
                "-ar",
                "16000",
                "-sample_fmt",
                "s16",
                str(output_path),
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                return output_path

            self._logger.warning(
                "ffmpeg normalization failed, fallback to source copy | stderr=%s",
                result.stderr[-500:],
            )

        # Fallback path keeps pipeline usable even without ffmpeg in developer machines.
        shutil.copy2(source_path, output_path)
        return output_path
