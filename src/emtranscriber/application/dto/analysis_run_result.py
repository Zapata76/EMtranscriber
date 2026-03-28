from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class AnalysisRunResult:
    provider_name: str
    model_identifier: str | None
    output_text: str
    request_json_path: Path
    response_json_path: Path
    output_markdown_path: Path
