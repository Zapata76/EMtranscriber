from __future__ import annotations

import logging

from emtranscriber.infrastructure.ai_analysis.analysis_provider import AnalysisProvider
from emtranscriber.infrastructure.ai_analysis.disabled_provider import DisabledAnalysisProvider
from emtranscriber.infrastructure.ai_analysis.openai_compatible_provider import OpenAICompatibleAnalysisProvider
from emtranscriber.infrastructure.settings.app_settings import AppSettings


DEFAULT_OPENAI_COMPATIBLE_ENDPOINT = "https://api.openai.com/v1/chat/completions"


def build_analysis_provider(settings: AppSettings, logger: logging.Logger) -> AnalysisProvider:
    if not settings.ai_analysis_enabled:
        return DisabledAnalysisProvider("AI analysis is disabled. Enable it in Settings to continue.")

    provider = (settings.ai_analysis_provider or "disabled").strip().lower()

    if provider in {"openai", "openai_compatible"}:
        return OpenAICompatibleAnalysisProvider(
            endpoint=settings.ai_analysis_endpoint or DEFAULT_OPENAI_COMPATIBLE_ENDPOINT,
            api_key=settings.ai_analysis_api_key or "",
            model=settings.ai_analysis_model or "",
            logger=logger,
        )

    return DisabledAnalysisProvider(f"Unsupported AI analysis provider: {provider}")
