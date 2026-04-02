from __future__ import annotations

import faulthandler
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

_FAULT_LOG_HANDLE = None


def _enable_native_crash_dump(logs_dir: Path, logger: logging.Logger) -> None:
    global _FAULT_LOG_HANDLE

    if _FAULT_LOG_HANDLE is not None:
        return

    crash_log_path = logs_dir / "emtranscriber-crash.log"
    try:
        _FAULT_LOG_HANDLE = open(crash_log_path, "a", encoding="utf-8")
        faulthandler.enable(file=_FAULT_LOG_HANDLE, all_threads=True)
        logger.info("Native crash diagnostics enabled: %s", crash_log_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Unable to enable native crash diagnostics: %s", exc)


def configure_logging(logs_dir: Path, log_level: int = logging.INFO) -> logging.Logger:
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / "emtranscriber.log"

    logger = logging.getLogger("emtranscriber")
    logger.setLevel(log_level)

    if logger.handlers:
        _enable_native_crash_dump(logs_dir, logger)
        return logger

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        "%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        filename=log_file,
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    _enable_native_crash_dump(logs_dir, logger)

    return logger
