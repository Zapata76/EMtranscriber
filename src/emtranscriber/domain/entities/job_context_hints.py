from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class JobContextHints:
    language_hint: str | None = None
    domain_context: str | None = None
    hotwords: list[str] = field(default_factory=list)
    glossary_terms: list[str] = field(default_factory=list)
    expected_participants: list[str] = field(default_factory=list)
    expected_entities: list[str] = field(default_factory=list)
    expected_acronyms: list[str] = field(default_factory=list)
