from emtranscriber.domain.entities.job_context_hints import JobContextHints
from emtranscriber.domain.pipeline.hint_builder import build_hint_text


def test_build_hint_text_deduplicates_terms() -> None:
    hints = JobContextHints(
        domain_context="Insurance meeting",
        hotwords=["backlog", "Backlog", "rollout"],
        glossary_terms=["KPI"],
        expected_participants=["Paolo", "paolo", "Stefania"],
        expected_acronyms=["UAT", "UAT"],
    )

    output = build_hint_text(hints)

    assert "Expected participants: Paolo, Stefania" in output
    assert "Expected terms: KPI, backlog, rollout" in output
    assert "Expected acronyms: UAT" in output


def test_build_hint_text_respects_max_chars() -> None:
    hints = JobContextHints(domain_context="x" * 200)
    output = build_hint_text(hints, max_chars=40)

    assert len(output) == 40
    assert output.endswith("...")
