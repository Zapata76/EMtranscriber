from __future__ import annotations

from emtranscriber.domain.entities.job_context_hints import JobContextHints


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for raw in items:
        item = raw.strip()
        if not item:
            continue
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def build_hint_text(hints: JobContextHints | None, max_chars: int = 800) -> str:
    if hints is None:
        return ""

    lines: list[str] = []

    if hints.domain_context:
        lines.append(f"Context: {hints.domain_context.strip()}")

    participants = _dedupe(hints.expected_participants)
    if participants:
        lines.append(f"Expected participants: {', '.join(participants)}")

    terms = _dedupe(hints.glossary_terms + hints.hotwords)
    if terms:
        lines.append(f"Expected terms: {', '.join(terms)}")

    acronyms = _dedupe(hints.expected_acronyms)
    if acronyms:
        lines.append(f"Expected acronyms: {', '.join(acronyms)}")

    entities = _dedupe(hints.expected_entities)
    if entities:
        lines.append(f"Expected entities: {', '.join(entities)}")

    if hints.language_hint:
        lines.append(f"Language hint: {hints.language_hint.strip()}")

    merged = "\n".join(lines).strip()
    if len(merged) <= max_chars:
        return merged

    return merged[: max_chars - 3].rstrip() + "..."
