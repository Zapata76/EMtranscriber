from __future__ import annotations

import json
import logging
from urllib import error, request

from emtranscriber.domain.analysis import AnalysisRequest, AnalysisResult


class OpenAICompatibleAnalysisProvider:
    provider_name = "openai_compatible"

    def __init__(
        self,
        endpoint: str,
        api_key: str,
        model: str,
        logger: logging.Logger,
        timeout_s: int = 90,
    ) -> None:
        self._endpoint = endpoint.strip()
        self._api_key = api_key.strip()
        self._model = model.strip()
        self._timeout_s = timeout_s
        self._logger = logger

    def analyze_transcript(self, request_payload: AnalysisRequest) -> AnalysisResult:
        self._validate_configuration()

        body = {
            "model": self._model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You analyze meeting transcripts. Keep output factual, concise, and grounded in the provided transcript."
                    ),
                },
                {
                    "role": "user",
                    "content": self._build_user_prompt(request_payload),
                },
            ],
            "temperature": 0.2,
        }

        raw_response = self._send_request(body)
        text = self._extract_text(raw_response)

        return AnalysisResult(
            provider_name=self.provider_name,
            analysis_text=text,
            model_identifier=self._model,
            raw_response=raw_response,
        )

    def _validate_configuration(self) -> None:
        missing: list[str] = []
        if not self._endpoint:
            missing.append("endpoint")
        if not self._api_key:
            missing.append("api_key")
        if not self._model:
            missing.append("model")

        if missing:
            names = ", ".join(missing)
            raise RuntimeError(
                f"AI analysis provider is not configured: missing {names}. Update Settings > AI Analysis."
            )

    def _send_request(self, payload: dict) -> dict:
        raw = json.dumps(payload).encode("utf-8")
        req = request.Request(
            self._endpoint,
            data=raw,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=self._timeout_s) as response:
                content = response.read().decode("utf-8")
        except error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            summary = details[:350].strip().replace("\n", " ")
            raise RuntimeError(f"AI analysis request failed ({exc.code}): {summary}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"AI analysis provider is unreachable: {exc.reason}") from exc

        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise RuntimeError("AI analysis provider returned invalid JSON.") from exc

    def _extract_text(self, payload: dict) -> str:
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise RuntimeError("AI analysis provider returned no choices.")

        message = choices[0].get("message", {})
        content = message.get("content")
        if isinstance(content, str):
            text = content.strip()
            if text:
                return text

        if isinstance(content, list):
            chunks: list[str] = []
            for item in content:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "text" and isinstance(item.get("text"), str):
                    value = item["text"].strip()
                    if value:
                        chunks.append(value)
            if chunks:
                return "\n".join(chunks)

        self._logger.warning("AI analysis response did not include text content: %s", payload)
        raise RuntimeError("AI analysis provider returned an empty response.")

    @staticmethod
    def _build_user_prompt(payload: AnalysisRequest) -> str:
        language_line = (
            f"Preferred output language: {payload.output_language}.\n" if payload.output_language else ""
        )
        return (
            f"{payload.analysis_prompt}\n\n"
            f"{language_line}"
            "Speaker map:\n"
            f"{json.dumps(payload.speaker_map, ensure_ascii=False, indent=2)}\n\n"
            "Job metadata:\n"
            f"{json.dumps(payload.job_metadata, ensure_ascii=False, indent=2)}\n\n"
            "Transcript markdown:\n"
            f"{payload.transcript_markdown}\n"
        ).strip()
