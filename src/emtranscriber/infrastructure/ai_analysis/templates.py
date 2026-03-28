from __future__ import annotations

from collections.abc import Iterable

ANALYSIS_TEMPLATE_LABELS: dict[str, str] = {
    "meeting-summary": "Meeting Summary",
    "action-items": "Action Items",
    "risks-issues": "Risks and Issues",
    "executive-memo": "Executive Memo",
    "custom": "Custom",
}

ANALYSIS_TEMPLATE_PROMPTS: dict[str, str] = {
    "meeting-summary": (
        "Create a concise meeting summary with key points, decisions, and next steps. "
        "Keep wording factual and avoid invented details."
    ),
    "action-items": (
        "Extract action items as a numbered list. For each action include owner (if available), "
        "deadline (if available), and dependencies."
    ),
    "risks-issues": (
        "List risks, blockers, and open issues. Highlight impact, urgency, and suggested mitigation."
    ),
    "executive-memo": (
        "Write an executive memo in short sections: context, major decisions, timeline, risks, and recommendations."
    ),
    "custom": "",
}


def available_templates() -> list[tuple[str, str]]:
    return [(key, ANALYSIS_TEMPLATE_LABELS[key]) for key in ANALYSIS_TEMPLATE_LABELS]


def resolve_template_instruction(template_key: str | None) -> str:
    if not template_key:
        return ANALYSIS_TEMPLATE_PROMPTS["meeting-summary"]
    return ANALYSIS_TEMPLATE_PROMPTS.get(template_key, ANALYSIS_TEMPLATE_PROMPTS["meeting-summary"])


def normalize_template_key(template_key: str | None) -> str:
    if template_key in ANALYSIS_TEMPLATE_LABELS:
        return template_key
    return "meeting-summary"


def merge_prompt(template_instruction: str, custom_prompt: str | None) -> str:
    prompt = (custom_prompt or "").strip()
    if not prompt:
        return template_instruction
    if not template_instruction:
        return prompt
    return f"{template_instruction}\n\nAdditional user instructions:\n{prompt}"


def normalize_output_language(raw: str | None) -> str | None:
    value = (raw or "").strip()
    return value or None


def serialize_speaker_map(pairs: Iterable[tuple[str, str]]) -> dict[str, str]:
    return {key: value for key, value in pairs}
