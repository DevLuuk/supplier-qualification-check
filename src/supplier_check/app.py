import logging
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
from google.genai import errors

from supplier_check.models import Decision, RunResult, Source, StepEvent, StepName, Verdict
from supplier_check.pipeline import (
    RESULTS_DIR,
    ROOT,
    check_firm,
    format_event,
    save,
    usage_text,
)

FIRMS_DIR = ROOT / "data" / "firms"
STATUS_COLOURS = {"pass": "#c8e6c9", "fail": "#ffcdd2", "unsure": "#fff59d"}
RESULT_KEY = "result"
INTERNAL_LABEL = "Internal, for the officer only. Not part of the email."
SCAN_LABEL = "read from scan, not verified"
SESSION_KEY = "session_runs"
EVENTS_KEY = "events"
GEMINI = ":blue[Gemini]"
CODE = ":gray[code]"
STEPS: list[tuple[StepName, str]] = [
    ("read_text", CODE),
    ("classify", GEMINI),
    ("extract", GEMINI),
    ("lookups", CODE),
    ("rules", CODE),
    ("verdicts", CODE),
]
STEP_KINDS = dict(STEPS)
STATE_BADGES = {
    "waiting": ":gray-background[waiting]",
    "running": ":orange-background[running...]",
    "done": ":green-background[done]",
    "failed": ":red-background[failed]",
}

logger = logging.getLogger(__name__)


def _result_for(slug: str) -> RunResult | None:
    result: RunResult | None = st.session_state.get(RESULT_KEY)
    return result if result and result.firm_file.slug == slug else None


def _firm_slugs() -> list[str]:
    return sorted(path.name for path in FIRMS_DIR.iterdir() if path.is_dir())


def _quote(source: Source) -> str:
    image = f" ({SCAN_LABEL})" if source.kind == "page_image" else ""
    return f"{source.file} p{source.page}{image}: {source.quote}"


def _show_summary(result: RunResult) -> None:
    summary = result.summary
    if summary is None:
        return
    st.subheader("Run summary")
    first = st.columns(5)
    first[0].metric("Wall clock", f"{summary.wall_seconds:.1f} s")
    first[1].metric("Model time", f"{summary.model_seconds:.1f} s")
    first[2].metric("Tokens in / out", f"{summary.tokens_in} / {summary.tokens_out}")
    first[3].metric("Cost", f"{summary.cents:.2f} euro cents")
    first[4].metric("Thinking", summary.thinking)
    second = st.columns(5)
    second[0].metric("Documents read", summary.documents)
    second[1].metric("Fields pulled", summary.fields)
    second[2].metric("Low confidence", summary.low_confidence)
    second[3].metric("Pass / fail / unsure", f"{summary.passed} / {summary.failed} / {summary.unsure}")
    second[4].metric("Cached calls", summary.cached_calls)
    st.dataframe(pd.DataFrame([row.model_dump() for row in summary.per_document]), hide_index=True)


def _count_session(result: RunResult) -> None:
    runs = st.session_state.setdefault(SESSION_KEY, [])
    runs.append((result.firm_file.slug, result.summary.cents if result.summary else 0.0))


def _show_session_total() -> None:
    runs = st.session_state.get(SESSION_KEY, [])
    firms = len({slug for slug, _ in runs})
    cents = sum(cost for _, cost in runs)
    st.caption(f"Session: {len(runs)} runs, {firms} firms checked, {cents:.2f} euro cents in total.")


def _row(verdict: Verdict) -> dict[str, str]:
    return {
        "rule": verdict.rule_id,
        "requirement": verdict.requirement,
        "status": verdict.status,
        "reason": verdict.reason,
        "quote": " | ".join(_quote(source) for source in verdict.evidence),
    }


def _status_style(status: str) -> str:
    return f"background-color: {STATUS_COLOURS[status]}"


def _show_verdicts(result: RunResult) -> None:
    table = pd.DataFrame([_row(verdict) for verdict in result.verdicts])
    st.dataframe(table.style.map(_status_style, subset=["status"]), hide_index=True)
    counts = {s: sum(v.status == s for v in result.verdicts) for s in STATUS_COLOURS}
    st.caption(f"pass {counts['pass']}, fail {counts['fail']}, unsure {counts['unsure']}")


def _show_details(result: RunResult) -> None:
    st.subheader("Lookups")
    for lookup in result.lookups:
        st.write(f"{lookup.source}: {lookup.note}")
    st.subheader("Raw extraction")
    for doc in result.firm_file.documents:
        from_scan = any(f.source and f.source.kind == "page_image" for f in doc.fields.values())
        label = f"{doc.file} ({doc.doc_type})" + (f", {SCAN_LABEL}" if from_scan else "")
        with st.expander(label):
            if from_scan:
                st.warning(f"Every field in this document is {SCAN_LABEL}.")
            st.json(doc.model_dump(mode="json")["fields"])
    if result.unclassified:
        st.warning(f"Not recognised: {', '.join(result.unclassified)}")
    for unreadable in result.firm_file.unreadable:
        st.warning(f"Could not read {unreadable.file}: {unreadable.reason}")


def _decide(slug: str, decision: str) -> Path:
    record = Decision(slug=slug, decision=decision, decided_at=datetime.now())
    path = RESULTS_DIR / f"{slug}.decision.json"
    path.write_text(record.model_dump_json(), encoding="utf-8")
    return path


def _show_decision(slug: str) -> None:
    approve, reject = st.columns(2)
    if approve.button("Approve", type="primary"):
        st.success(f"Approved. Saved to {_decide(slug, 'approved').name}")
    if reject.button("Reject"):
        st.error(f"Rejected. Saved to {_decide(slug, 'rejected').name}")


class StageStrip:
    def __init__(self) -> None:
        columns = st.columns(len(STEPS))
        self.boxes = {step: column.empty() for (step, _), column in zip(STEPS, columns)}
        for step, _ in STEPS:
            self.update(StepEvent(step=step, status="running"), waiting=True)

    def update(self, event: StepEvent, waiting: bool = False) -> None:
        state = "waiting" if waiting else event.status
        with self.boxes[event.step].container(border=True):
            st.markdown(f"**{event.step}**  \n{STEP_KINDS[event.step]}")
            st.markdown(STATE_BADGES[state])
            st.caption(usage_text(event) if state in ("done", "failed") else " ")


def _run(slug: str) -> None:
    strip = StageStrip()
    log = st.status("Run log", expanded=True)
    events: list[StepEvent] = []

    def on_step(event: StepEvent) -> None:
        events.append(event)
        strip.update(event)
        log.write(format_event(event))

    try:
        result = check_firm(FIRMS_DIR / slug, on_step)
    except errors.APIError as error:
        logger.exception("Model call failed for %s", slug)
        log.update(label="Run log: failed", state="error")
        st.error(f"The model call failed: {error.message}")
        return
    log.update(label="Run log", state="complete", expanded=False)
    save(result)
    _count_session(result)
    st.session_state[RESULT_KEY] = result
    st.session_state[EVENTS_KEY] = events


def _show_last_run() -> None:
    events: list[StepEvent] = st.session_state.get(EVENTS_KEY, [])
    strip = StageStrip()
    for event in events:
        strip.update(event)
    with st.expander("Run log"):
        for event in events:
            st.text(format_event(event))


def main() -> None:
    st.set_page_config(page_title="Supplier check", layout="wide")
    st.title("Supplier check")
    st.badge("MOCK lookups", color="orange")
    st.caption("All firms, documents, register and sanctions data are mock.")
    slug = st.selectbox("Firm", _firm_slugs())
    if st.button("Run"):
        _run(slug)
    elif _result_for(slug):
        _show_last_run()
    result = _result_for(slug)
    if result is not None:
        _show_summary(result)
        _show_verdicts(result)
        st.subheader("Draft email to the firm")
        st.text_area("Email", result.email, height=300)
        if result.officer_note:
            with st.container(border=True):
                st.markdown(f"**{INTERNAL_LABEL}**")
                st.warning(result.officer_note)
        _show_decision(slug)
        _show_details(result)
    _show_session_total()


if __name__ == "__main__":
    main()
