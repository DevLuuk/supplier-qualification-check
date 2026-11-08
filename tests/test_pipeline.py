from datetime import date

import pytest

from supplier_check import pipeline
from supplier_check.models import CallLog, FirmFile, RunResult, RunSummary, StepEvent

REAL = CallLog(step="Extract", model="gemini-3.8-flash", tokens_in=500, tokens_out=1500, seconds=9.0)
CACHED = CallLog(step="Extract", model="gemini-3.8-flash (cached)", tokens_in=0, tokens_out=0, seconds=0.0)


def _result(calls: list[CallLog]) -> RunResult:
    firm = FirmFile(slug="test-firm", country="DE", as_of=date(2026, 11, 9), documents=[])
    return RunResult(firm_file=firm, verdicts=[], lookups=[], calls=calls, unclassified=[], email="")


@pytest.fixture
def results_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "RESULTS_DIR", tmp_path)
    return tmp_path


def _saved_calls(results_dir) -> list[CallLog]:
    saved = RunResult.model_validate_json((results_dir / "test-firm.json").read_text())
    return saved.calls


def test_cached_run_keeps_real_call_log(results_dir):
    pipeline.save(_result([REAL]))
    pipeline.save(_result([CACHED]))
    assert _saved_calls(results_dir) == [REAL]


def test_partly_cached_run_keeps_real_cost_of_cached_calls(results_dir):
    other_file = REAL.model_copy(update={"file": "b.pdf", "tokens_in": 7})
    pipeline.save(_result([REAL]))
    pipeline.save(_result([CACHED, other_file]))
    assert _saved_calls(results_dir) == [REAL, other_file]


def test_cached_call_without_real_match_stays_cached(results_dir):
    pipeline.save(_result([REAL]))
    unmatched = CACHED.model_copy(update={"file": "new.pdf"})
    pipeline.save(_result([unmatched]))
    assert _saved_calls(results_dir) == [unmatched]


def test_first_cached_run_is_saved_as_is(results_dir):
    pipeline.save(_result([CACHED]))
    assert _saved_calls(results_dir) == [CACHED]


def test_partly_cached_summary_counts_real_costs(results_dir):
    summary = RunSummary(
        wall_seconds=1.0, model_seconds=0.0, tokens_in=0, tokens_out=0, rappen=0.0, documents=0,
        fields=0, low_confidence=0, passed=0, failed=0, unsure=0, cached_calls=2, thinking="minimal",
        per_document=[],
    )
    other_file = REAL.model_copy(update={"file": "b.pdf"})
    pipeline.save(_result([REAL]))
    pipeline.save(_result([CACHED, other_file]).model_copy(update={"summary": summary}))
    saved = RunResult.model_validate_json((results_dir / "test-firm.json").read_text())
    assert saved.summary.tokens_in == 1000
    assert saved.summary.cached_calls == 2


def test_merge_shows_stored_real_numbers_for_cached_run(results_dir):
    summary = RunSummary(
        wall_seconds=0.1, model_seconds=0.0, tokens_in=0, tokens_out=0, rappen=0.0, documents=0,
        fields=0, low_confidence=0, passed=0, failed=0, unsure=0, cached_calls=1, thinking="minimal",
        per_document=[],
    )
    stored = _result([REAL]).model_copy(update={"summary": summary.model_copy(update={"wall_seconds": 6.0})})
    pipeline.save(stored)
    merged = pipeline.merge_with_saved(_result([CACHED]).model_copy(update={"summary": summary}))
    assert merged.summary.wall_seconds == 6.0
    assert merged.summary.tokens_in == 500
    assert merged.summary.rappen > 0
    assert pipeline.cache_caption(merged.summary).startswith("from cache; live run took 6.0 s and cost")


def test_live_run_has_no_cache_caption():
    summary = RunSummary(
        wall_seconds=5.0, model_seconds=20.0, tokens_in=1, tokens_out=1, rappen=0.9, documents=0,
        fields=0, low_confidence=0, passed=0, failed=0, unsure=0, cached_calls=0, thinking="minimal",
        per_document=[],
    )
    assert pipeline.cache_caption(summary) == ""


def test_run_log_shows_newest_line_first():
    events = [
        StepEvent(step="read_text", status="running"),
        StepEvent(step="read_text", status="done", detail="6 PDFs"),
        StepEvent(step="classify", status="running"),
    ]
    lines = pipeline.newest_first(events).splitlines()
    assert lines[0] == "[classify] running"
    assert lines[-1] == "[read_text] running"


def test_merge_never_takes_verdicts_or_notes_from_the_saved_file(results_dir):
    from supplier_check.models import Verdict

    def with_reason(result: RunResult, reason: str) -> RunResult:
        verdict = Verdict(rule_id="DE-INS-05", requirement="", status="unsure", reason=reason, evidence=[])
        return result.model_copy(update={"verdicts": [verdict]})

    pipeline.save(with_reason(_result([REAL]), "two reads differ: A=None B=old"))
    merged = pipeline.merge_with_saved(with_reason(_result([CACHED]), "two reads differ: A=None B=new"))
    assert merged.verdicts[0].reason == "two reads differ: A=None B=new"
    assert merged.calls == [REAL]
