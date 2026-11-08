from html import escape
from typing import Literal

import streamlit as st
from pydantic import BaseModel

from supplier_check import llm
from supplier_check.models import DocCard, StepEvent, StepName

State = Literal["waiting", "running", "done", "failed"]
PROGRESS_STEPS = {"classify", "extract"}
MODEL_TIERS: dict[str, str] = {"classify": "fast", "extract": "careful"}
COLOURS = {"model": "#3b6fd4", "code": "#9aa0a6", "running": "#e8a317", "done": "#2e9d5b", "failed": "#d93025"}
CACHED_STRIPES = "repeating-linear-gradient(45deg, rgba(128,128,128,0.10) 0 6px, transparent 6px 12px)"
VERDICT_COLOURS = {"pass": "#2e9d5b", "fail": "#d93025", "unsure": "#e8a317"}
ARROW = "&#8594;"
QUOTE_CHARS = 90


class StageView(BaseModel):
    step: StepName
    state: State = "waiting"
    seconds: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    rappen: float = 0.0
    cached: bool = False
    done: int = 0
    total: int = 0
    file: str = ""
    two_reads: bool = False
    file_usage: dict[str, tuple[int, int, float]] = {}


class StripState(BaseModel):
    stages: dict[str, StageView]
    elapsed: float = 0.0
    cards: list[DocCard] = []
    verdict_counts: dict[str, int] = {}

    @classmethod
    def start(cls, steps: list[StepName]) -> "StripState":
        return cls(stages={step: StageView(step=step) for step in steps})

    def apply(self, event: StepEvent) -> StageView:
        stage = self.stages[event.step]
        self.elapsed = max(self.elapsed, event.at)
        stage.two_reads = stage.two_reads or event.two_reads
        self.verdict_counts = event.verdict_counts or self.verdict_counts
        if event.status == "running":
            _apply_running(stage, event, self.cards)
        else:
            stage.state, stage.seconds, stage.cached = event.status, event.seconds, event.cached
            stage.tokens_in, stage.tokens_out, stage.rappen = event.tokens_in, event.tokens_out, event.rappen
        return stage

    def totals(self) -> tuple[int, int, float]:
        stages = self.stages.values()
        return (
            sum(s.tokens_in for s in stages),
            sum(s.tokens_out for s in stages),
            sum(s.rappen for s in stages),
        )

    @property
    def finished(self) -> bool:
        return self.stages[list(self.stages)[-1]].state == "done"


def _apply_running(stage: StageView, event: StepEvent, cards: list[DocCard]) -> None:
    stage.state = "running"
    stage.total = event.total or stage.total
    if not event.file:
        return
    stage.done, stage.file = event.done, event.file
    stage.file_usage[event.file] = (event.tokens_in, event.tokens_out, event.rappen)
    usage = stage.file_usage.values()
    stage.tokens_in = sum(u[0] for u in usage)
    stage.tokens_out = sum(u[1] for u in usage)
    stage.rappen = sum(u[2] for u in usage)
    if event.card and all(card.file != event.card.file for card in cards):
        cards.append(event.card)


def model_label(model_id: str) -> str:
    return " ".join(word if word[0].isdigit() else word.capitalize() for word in model_id.split("-"))


def kind_badge(step: str) -> str:
    tier = MODEL_TIERS.get(step)
    return model_label(llm.MODELS[tier]) if tier else "code"


def progress_text(stage: StageView) -> str:
    if stage.step not in PROGRESS_STEPS or not stage.total:
        return ""
    current = f", {stage.file}" if stage.file and stage.state == "running" else ""
    return f"{stage.done} of {stage.total} documents{current}"


def usage_line(stage: StageView) -> str:
    if stage.state == "waiting":
        return "waiting"
    if stage.cached:
        return f"{stage.seconds:.1f} s, cached"
    tokens = f", {stage.tokens_in}+{stage.tokens_out} tokens, {stage.rappen:.2f} rappen" if stage.tokens_in else ""
    seconds = f"{stage.seconds:.1f} s" if stage.state != "running" else "running"
    return seconds + tokens


def border_colour(stage: StageView) -> str:
    if stage.state in ("running", "done", "failed"):
        return COLOURS[stage.state]
    return COLOURS["model" if stage.step in MODEL_TIERS else "code"]


def _badge(text: str, colour: str) -> str:
    style = f"border:1px solid {colour};color:{colour};border-radius:9px;padding:0 6px;font-size:0.72rem;"
    return f'<span style="{style}">{escape(text)}</span>'


def box_html(stage: StageView, sentence: str) -> str:
    colour = border_colour(stage)
    border = "dashed" if stage.cached else "solid"
    background = CACHED_STRIPES if stage.cached else "transparent"
    badges = _badge(kind_badge(stage.step), COLOURS["model" if stage.step in MODEL_TIERS else "code"])
    badges += " " + _badge("two reads", COLOURS["model"]) if stage.two_reads else ""
    lines = [
        f"<div style='font-weight:600'>{escape(stage.step)}</div>",
        f"<div style='font-size:0.8rem;opacity:0.8;min-height:2.4em'>{escape(sentence)}</div>",
        f"<div style='margin:4px 0'>{badges}</div>",
        f"<div style='font-size:0.8rem;color:{colour};font-weight:600'>{stage.state}</div>",
        f"<div style='font-size:0.75rem'>{escape(progress_text(stage))}</div>",
        f"<div style='font-size:0.75rem;opacity:0.85'>{escape(usage_line(stage))}</div>",
    ]
    style = f"border:2px {border} {colour};border-radius:8px;padding:8px;background:{background};min-height:11em"
    return f"<div style=\"{style}\">{''.join(lines)}</div>"


def counters_text(state: StripState) -> str:
    tokens_in, tokens_out, rappen = state.totals()
    return f"Elapsed {state.elapsed:.1f} s | tokens so far {tokens_in} in, {tokens_out} out | {rappen:.2f} rappen so far"


def card_html(card: DocCard) -> str:
    quote = card.first_quote if len(card.first_quote) <= QUOTE_CHARS else card.first_quote[:QUOTE_CHARS] + "..."
    scan = " (scan)" if card.read_from == "page_image" else ""
    style = "border:1px solid rgba(128,128,128,0.4);border-radius:6px;padding:6px 8px;width:15rem;font-size:0.78rem"
    return (
        f"<div style='{style}'><b>{escape(card.file)}</b>{scan}<br>{escape(card.doc_type)}, "
        f"{card.fields} fields, {card.low_confidence} low confidence<br><i>{escape(quote)}</i></div>"
    )


def cards_html(cards: list[DocCard]) -> str:
    return "<div style='display:flex;flex-wrap:wrap;gap:8px'>" + "".join(map(card_html, cards)) + "</div>"


def verdict_line_html(counts: dict[str, int]) -> str:
    parts = [
        f"<span style='color:{VERDICT_COLOURS[s]};font-weight:700'>{counts.get(s, 0)} {s}</span>"
        for s in VERDICT_COLOURS
    ]
    style = "border-left:4px solid #3b6fd4;padding:6px 10px;background:rgba(59,111,212,0.08);font-size:1.05rem"
    return f"<div style='{style}'>{' &nbsp;|&nbsp; '.join(parts)}</div>"


class StripView:
    def __init__(self, sentences: dict[StepName, str]) -> None:
        self.sentences = sentences
        self.state = StripState.start(list(sentences))
        self.counters = st.empty()
        widths = [item for _ in sentences for item in (5, 1)][:-1]
        columns = st.columns(widths)
        self.boxes = {step: columns[index * 2].empty() for index, step in enumerate(sentences)}
        for column in columns[1::2]:
            column.markdown(f"<div style='text-align:center;font-size:1.6rem;margin-top:3.5em'>{ARROW}</div>",
                            unsafe_allow_html=True)
        self.verdicts = st.empty()
        self.cards = st.empty()
        for step in sentences:
            self._draw(self.state.stages[step])
        self.counters.markdown(counters_text(self.state))

    def update(self, event: StepEvent) -> None:
        stage = self.state.apply(event)
        self._draw(stage)
        self.counters.markdown(counters_text(self.state))
        if self.state.cards:
            self.cards.markdown(cards_html(self.state.cards), unsafe_allow_html=True)
        if self.state.finished and self.state.verdict_counts:
            self.verdicts.markdown(verdict_line_html(self.state.verdict_counts), unsafe_allow_html=True)

    def _draw(self, stage: StageView) -> None:
        with self.boxes[stage.step].container():
            st.markdown(box_html(stage, self.sentences[stage.step]), unsafe_allow_html=True)
            if stage.step in PROGRESS_STEPS and stage.total:
                st.progress(min(stage.done / stage.total, 1.0))
