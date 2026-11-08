from pathlib import Path

import pytest

from supplier_check import llm, pipeline
from supplier_check.models import (
    Classification,
    DocCard,
    ExtractedDocument,
    Field,
    Source,
    StepEvent,
)
from supplier_check.strip import (
    StripState,
    box_html,
    counters_text,
    kind_badge,
    model_label,
    progress_text,
    usage_line,
    verdict_line_html,
)

STEPS = ["read_text", "classify", "extract", "lookups", "rules", "verdicts"]
HANSEN = Path(__file__).resolve().parents[1] / "data" / "firms" / "hansen-elektrotechnik"


def _card(file: str) -> DocCard:
    return DocCard(file=file, doc_type="bank_letter", read_from="text", fields=4, low_confidence=0, first_quote="Q")


def test_model_labels_come_from_real_ids():
    assert model_label("gemini-3.8-flash") == "Gemini 3.8 Flash"
    assert model_label("gemini-3.5-flash-lite") == "Gemini 3.5 Flash Lite"
    assert kind_badge("extract") == model_label(llm.MODELS["careful"])
    assert kind_badge("classify") == model_label(llm.MODELS["fast"])
    assert kind_badge("rules") == "code"


def test_progress_counts_files_and_tokens():
    state = StripState.start(STEPS)
    state.apply(StepEvent(step="extract", status="running", total=6, at=1.0))
    state.apply(StepEvent(step="extract", status="running", file="a.pdf", done=1, total=6,
                          tokens_in=100, tokens_out=50, rappen=0.1, card=_card("a.pdf"), at=2.0))
    stage = state.apply(StepEvent(step="extract", status="running", file="b.pdf", done=2, total=6,
                                  tokens_in=200, tokens_out=60, rappen=0.2, card=_card("b.pdf"), at=3.5))
    assert progress_text(stage) == "2 of 6 documents, b.pdf"
    assert (stage.tokens_in, stage.tokens_out) == (300, 110)
    assert [card.file for card in state.cards] == ["a.pdf", "b.pdf"]
    assert counters_text(state) == "Elapsed 3.5 s | tokens so far 300 in, 110 out | 0.30 rappen so far"


def test_done_event_replaces_running_sums_without_double_counting():
    state = StripState.start(STEPS)
    state.apply(StepEvent(step="classify", status="running", file="a.pdf", done=1, total=1, tokens_in=10))
    stage = state.apply(StepEvent(step="classify", status="done", seconds=1.2, tokens_in=10, tokens_out=2, rappen=0.01))
    assert stage.state == "done"
    assert state.totals()[0] == 10
    assert progress_text(stage) == "1 of 1 documents"


def test_cached_stage_is_dashed_and_says_cached():
    state = StripState.start(STEPS)
    stage = state.apply(StepEvent(step="extract", status="done", seconds=0.0, cached=True))
    assert usage_line(stage) == "0.0 s, cached"
    assert "dashed" in box_html(stage, "Pull the fields with a proof quote")


def test_two_reads_badge_appears_on_extract():
    state = StripState.start(STEPS)
    stage = state.apply(StepEvent(step="extract", status="running", total=6, two_reads=True))
    assert "two reads" in box_html(stage, "x")


def test_waiting_colours_say_model_or_code():
    state = StripState.start(STEPS)
    assert "#3b6fd4" in box_html(state.stages["classify"], "x")
    assert "#9aa0a6" in box_html(state.stages["rules"], "x")


def test_verdict_counts_show_only_when_last_stage_done():
    state = StripState.start(STEPS)
    state.apply(StepEvent(step="rules", status="done", verdict_counts={"pass": 16, "fail": 1, "unsure": 3}))
    assert not state.finished
    state.apply(StepEvent(step="verdicts", status="done"))
    assert state.finished
    html = verdict_line_html(state.verdict_counts)
    assert "16 pass" in html and "1 fail" in html and "3 unsure" in html


@pytest.fixture
def fake_models(monkeypatch):
    def fake_classify(pages, media=None):
        return Classification(doc_type="bank_letter")

    def fake_extract(doc_type, file, pages, media=None, tier="careful"):
        source = Source(file=file, page=1, quote="Kontoinhaber Hansen Elektrotechnik GmbH")
        field = Field(value="Hansen Elektrotechnik GmbH", source=source, confidence="high")
        return ExtractedDocument(doc_type=doc_type, file=file, language="de", fields={"account_holder": field})

    monkeypatch.setattr(pipeline, "classify", fake_classify)
    monkeypatch.setattr(pipeline, "extract", fake_extract)


def test_pipeline_events_carry_progress_cards_and_time(fake_models):
    events: list[StepEvent] = []
    pipeline.check_firm(HANSEN, events.append)
    extract_files = [e for e in events if e.step == "extract" and e.file]
    assert [e.done for e in extract_files] == list(range(1, 7))
    assert {e.total for e in extract_files} == {6}
    assert all(e.card and e.card.first_quote.startswith("Kontoinhaber") for e in extract_files)
    assert [e.at for e in events] == sorted(e.at for e in events)
    rules_done = next(e for e in events if e.step == "rules" and e.status == "done")
    assert sum(rules_done.verdict_counts.values()) == len(pipeline.rule_book("DE"))
