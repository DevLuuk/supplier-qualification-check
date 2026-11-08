import importlib.util
from pathlib import Path

import pytest

EVAL_FILE = Path(__file__).resolve().parents[1] / "eval" / "run_eval.py"
spec = importlib.util.spec_from_file_location("run_eval", EVAL_FILE)
run_eval = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_eval)


@pytest.mark.parametrize(
    ("raw", "normalised"),
    [
        ("15.10.2026", "2026-10-15"),
        ("15 October 2026", "2026-10-15"),
        ("2026-10-15", "2026-10-15"),
        ("5.000.000,00 EUR", "5000000"),
        ("EUR 10.000.000", "10000000"),
        (5000000, "5000000"),
        ("  Weber   Stahlbau GmbH ", "weber stahlbau gmbh"),
        ("2023-2025", "2023-2025"),
        ("HRB 774102", "hrb 774102"),
        (None, ""),
    ],
)
def test_normalise_value(raw, normalised):
    assert run_eval.normalise_value(raw) == normalised


def _outcome(expected: str, got: str, confidence: str) -> "run_eval.FieldOutcome":
    return run_eval.FieldOutcome(
        firm="weber-stahlbau",
        document="insurance_certificate",
        field="valid_until",
        expected=expected,
        got=got,
        confidence=confidence,
        quote="",
        from_scan=False,
        exact=expected == got,
        normalised=run_eval.normalise_value(expected) == run_eval.normalise_value(got),
    )


def test_wrong_and_low_confidence_is_caught():
    assert _outcome("2026-10-15", "2026-10-16", "low").outcome == "caught"


def test_wrong_and_high_confidence_is_confident_but_wrong():
    assert _outcome("2026-10-15", "2026-10-16", "high").outcome == "confident_wrong"


def test_match_after_normalising_is_a_match():
    item = _outcome("2026-10-15", "15.10.2026", "high")
    assert (item.exact, item.outcome) == (False, "match")


def test_confident_misses_are_listed_first():
    misses = [_outcome("1", "2", "low"), _outcome("3", "4", "high")]
    lines = run_eval.miss_lines(misses)
    assert lines[0].startswith("- confident but wrong")
    assert lines[1].startswith("- wrong, unsure caught")


def test_counts_add_up():
    counts = run_eval.Counts()
    for item in (_outcome("a", "a", "high"), _outcome("a", "b", "low"), _outcome("a", "b", "high")):
        counts.add(item)
    assert (counts.compared, counts.exact, counts.wrong, counts.caught, counts.confident_wrong) == (3, 1, 2, 1, 1)


def test_table_escapes_pipes():
    assert "a/b" in run_eval.table(["h"], [["a|b"]])
