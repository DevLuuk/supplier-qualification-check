from datetime import date

import pytest

from supplier_check import pipeline
from supplier_check.models import CallLog, FirmFile, RunResult

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


def test_partly_cached_run_replaces_call_log(results_dir):
    pipeline.save(_result([REAL]))
    pipeline.save(_result([CACHED, REAL.model_copy(update={"tokens_in": 7})]))
    assert [call.tokens_in for call in _saved_calls(results_dir)] == [0, 7]


def test_first_cached_run_is_saved_as_is(results_dir):
    pipeline.save(_result([CACHED]))
    assert _saved_calls(results_dir) == [CACHED]
