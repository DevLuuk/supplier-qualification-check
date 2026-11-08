import argparse
import json
import logging
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from typing import TypeVar

from google.genai import errors
from pydantic import BaseModel, TypeAdapter

from supplier_check import llm
from supplier_check.classify import classify
from supplier_check.email_draft import NOTHING_TO_ASK, draft_email, officer_note
from supplier_check import extract as extraction
from supplier_check.extract import extract, extract_scan
from supplier_check.models import (
    CallLog,
    DocCard,
    DocSummary,
    ExtractedDocument,
    FirmFile,
    ReadFrom,
    RunResult,
    RunSummary,
    StepEvent,
    StepName,
    UnreadableFile,
    Verdict,
)
from supplier_check.pdf_text import has_text, read_page_images, read_pages
from supplier_check.rules import rule_book, run_lookups, run_rules

ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = ROOT / "eval" / "results"
ANSWER_KEY = "answer_key.json"
DEFAULT_COUNTRY = "DE"
MAX_PARALLEL_FILES = 6
COLUMN_WIDTHS = (10, 7)
REASON_WIDTH = 90
STATUSES = ("pass", "fail", "unsure")
VISION_FOR_SCANS = True
SCAN_REASON = "no text layer (scan)"
OTHER = "other"
CALL_LIST = TypeAdapter(list[CallLog])

OnStep = Callable[[StepEvent], None]
R = TypeVar("R")


logger = logging.getLogger(__name__)


class _Input(BaseModel):
    path: Path
    pages: list[str]
    read_from: ReadFrom


def _ignore(event: StepEvent) -> None:
    return None


def is_cached(call: CallLog) -> bool:
    return call.model.endswith(llm.CACHED_SUFFIX)


class _Stage:
    def __init__(self, step: StepName, on_step: OnStep):
        self.step = step
        self.on_step = on_step
        self.detail = ""
        self.final_facts: dict[str, object] = {}

    def __enter__(self) -> "_Stage":
        self.first_call = len(llm.calls)
        self.started = time.perf_counter()
        self.on_step(StepEvent(step=self.step, status="running"))
        return self

    def progress(self, detail: str, **facts: object) -> None:
        self.on_step(StepEvent(step=self.step, status="running", detail=detail, **facts))

    def file_progress(self, item_name: str, done: int, total: int, detail: str, **facts: object) -> None:
        own = [c for c in llm.calls[self.first_call :] if c.file == item_name]
        self.progress(
            detail,
            done=done,
            total=total,
            file=item_name,
            tokens_in=sum(c.tokens_in for c in own),
            tokens_out=sum(c.tokens_out for c in own),
            rappen=round(sum(map(llm.cost_rappen, own)), 4),
            cached=bool(own) and all(map(is_cached, own)),
            **facts,
        )

    def __exit__(self, exc_type: type | None, exc: BaseException | None, _tb: object) -> bool:
        stage_calls = llm.calls[self.first_call :]
        self.on_step(
            StepEvent(
                step=self.step,
                status="failed" if exc else "done",
                seconds=round(time.perf_counter() - self.started, 2),
                tokens_in=sum(call.tokens_in for call in stage_calls),
                tokens_out=sum(call.tokens_out for call in stage_calls),
                rappen=round(sum(map(llm.cost_rappen, stage_calls)), 4),
                cached=bool(stage_calls) and all(map(is_cached, stage_calls)),
                detail=str(exc) if exc else self.detail,
                **self.final_facts,
            )
        )
        return False


def _as_of(folder: Path) -> date:
    key_file = folder / ANSWER_KEY
    if key_file.exists():
        as_of = json.loads(key_file.read_text(encoding="utf-8")).get("as_of")
        if as_of:
            return date.fromisoformat(as_of)
    return date.today()


def _load(path: Path) -> _Input:
    pages = read_pages(path)
    if has_text(pages):
        return _Input(path=path, pages=pages, read_from="text")
    return _Input(path=path, pages=pages, read_from="page_image" if VISION_FOR_SCANS else "unreadable")


def _with_media(item: _Input, call: Callable[[list[bytes]], R]) -> R:
    if item.read_from != "page_image":
        return call([])
    try:
        return call([item.path.read_bytes()])
    except errors.ClientError:
        logger.warning("PDF input rejected for %s, sending embedded page images", item.path.name)
        return call(read_page_images(item.path))


Describe = Callable[[_Input, R], tuple[str, dict[str, object]]]


def _parallel(work: Callable[[_Input], R], inputs: list[_Input], stage: _Stage, describe: Describe) -> dict[Path, R]:
    def tagged_work(item: _Input) -> R:
        with llm.tagged(item.path.name):
            return work(item)

    results: dict[Path, R] = {}
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_FILES) as pool:
        futures = {pool.submit(tagged_work, item): item for item in inputs}
        for future in as_completed(futures):
            item = futures[future]
            results[item.path] = future.result()
            detail, facts = describe(item, results[item.path])
            stage.file_progress(item.path.name, len(results), len(inputs), detail, **facts)
    return results


def _first_quote(doc: ExtractedDocument) -> str:
    return next((f.source.quote for f in doc.fields.values() if f.source and f.source.quote), "")


def _describe_document(item: _Input, doc: ExtractedDocument) -> tuple[str, dict[str, object]]:
    low = sum(field.confidence == "low" for field in doc.fields.values())
    source = " from page image" if item.read_from == "page_image" else ""
    card = DocCard(
        file=item.path.name,
        doc_type=doc.doc_type,
        read_from=item.read_from,
        fields=sum(f.value is not None for f in doc.fields.values()),
        low_confidence=low,
        first_quote=_first_quote(doc),
    )
    two_reads = item.read_from == "page_image" and extraction.SCAN_READS_MUST_AGREE
    detail = f"{item.path.name}: {len(doc.fields)} fields{source}, {low} low confidence"
    return detail, {"card": card, "two_reads": two_reads}


def _describe_type(item: _Input, doc_type: str) -> tuple[str, dict[str, object]]:
    return f"{item.path.name}: {doc_type}", {}


def _read_and_classify(folder: Path, on_step: OnStep) -> tuple[list[_Input], dict[Path, str]]:
    with _Stage("read_text", on_step) as stage:
        inputs = [_load(path) for path in sorted(folder.glob("*.pdf"))]
        scans = [i.path.name for i in inputs if i.read_from != "text"]
        stage.detail = f"{len(inputs)} PDFs, {sum(len(i.pages) for i in inputs)} pages"
        stage.detail += f"; no text layer: {', '.join(scans)}" if scans else ""
    readable = [i for i in inputs if i.read_from != "unreadable"]
    with _Stage("classify", on_step) as stage:
        types = _parallel(
            lambda item: _with_media(item, lambda media: classify(item.pages, media)).doc_type,
            readable,
            stage,
            _describe_type,
        )
        recognised = sum(doc_type != OTHER for doc_type in types.values())
        stage.detail = f"{recognised} of {len(inputs)} documents recognised"
    return inputs, types


def build_firm_file(
    folder: Path, on_step: OnStep = _ignore
) -> tuple[FirmFile, list[str], list[_Input]]:
    inputs, types = _read_and_classify(folder, on_step)
    known = [i for i in inputs if types.get(i.path, OTHER) != OTHER]
    with _Stage("extract", on_step) as stage:
        for scan in (i for i in known if i.read_from == "page_image" and extraction.SCAN_READS_MUST_AGREE):
            stage.progress(f"{scan.path.name}: scan, read twice", total=len(known), two_reads=True)
        extracted = _parallel(
            lambda item: _with_media(
                item,
                lambda media: (extract_scan if media else extract)(
                    types[item.path], item.path.name, item.pages, media
                ),
            ),
            known,
            stage,
            _describe_document,
        )
        documents = [extracted[item.path] for item in known]
        low = sum(f.confidence == "low" for doc in documents for f in doc.fields.values())
        stage.detail = f"{len(documents)} documents read, {low} fields with low confidence"
    unreadable = [
        UnreadableFile(file=i.path.name, reason=SCAN_REASON)
        for i in inputs
        if i.read_from == "unreadable"
    ]
    firm = FirmFile(
        slug=folder.name,
        country=DEFAULT_COUNTRY,
        as_of=_as_of(folder),
        documents=documents,
        unreadable=unreadable,
    )
    unclassified = sorted(path.name for path, doc_type in types.items() if doc_type == OTHER)
    return firm, unclassified, inputs


def _firm_name(firm: FirmFile) -> str:
    for doc in firm.documents:
        field = doc.fields.get("legal_name")
        if doc.doc_type == "register_extract" and field and field.value:
            return str(field.value)
    return firm.slug


def _doc_summary(item: _Input, firm: FirmFile, calls: list[CallLog]) -> DocSummary:
    doc = next((d for d in firm.documents if d.file == item.path.name), None)
    own = [call for call in calls if call.file == item.path.name]
    return DocSummary(
        file=item.path.name,
        doc_type=doc.doc_type if doc else ("unreadable" if item.read_from == "unreadable" else OTHER),
        read_from=item.read_from,
        pages=len(item.pages),
        fields=len(doc.fields) if doc else 0,
        low_confidence=sum(f.confidence == "low" for f in doc.fields.values()) if doc else 0,
        seconds=round(sum(call.seconds for call in own), 2),
        tokens_in=sum(call.tokens_in for call in own),
        tokens_out=sum(call.tokens_out for call in own),
        rappen=round(sum(map(llm.cost_rappen, own)), 4),
    )


def _summary(
    firm: FirmFile, verdicts: list[Verdict], calls: list[CallLog], inputs: list[_Input], wall: float
) -> RunSummary:
    per_document = [_doc_summary(item, firm, calls) for item in inputs]
    return RunSummary(
        wall_seconds=round(wall, 2),
        model_seconds=round(sum(call.seconds for call in calls), 2),
        tokens_in=sum(call.tokens_in for call in calls),
        tokens_out=sum(call.tokens_out for call in calls),
        rappen=round(sum(map(llm.cost_rappen, calls)), 4),
        documents=len(firm.documents),
        fields=sum(row.fields for row in per_document),
        low_confidence=sum(row.low_confidence for row in per_document),
        passed=sum(v.status == "pass" for v in verdicts),
        failed=sum(v.status == "fail" for v in verdicts),
        unsure=sum(v.status == "unsure" for v in verdicts),
        cached_calls=sum(map(is_cached, calls)),
        thinking=llm.thinking,
        per_document=per_document,
    )


def _timed(on_step: OnStep, started: float) -> OnStep:
    def emit(event: StepEvent) -> None:
        on_step(event.model_copy(update={"at": round(time.perf_counter() - started, 2)}))

    return emit


def check_firm(folder: Path, on_step: OnStep = _ignore) -> RunResult:
    started, first_call = time.perf_counter(), len(llm.calls)
    on_step = _timed(on_step, started)
    firm, unclassified, inputs = build_firm_file(folder, on_step)
    with _Stage("lookups", on_step) as stage:
        lookups = run_lookups(firm, firm.country)
        stage.detail = " ".join(lookup.note for lookup in lookups)
    with _Stage("rules", on_step) as stage:
        verdicts = run_rules(firm, firm.country)
        tally = {s: sum(v.status == s for v in verdicts) for s in STATUSES}
        stage.detail = f"{len(verdicts)} rules: " + ", ".join(f"{n} {s}" for s, n in tally.items())
        stage.final_facts = {"verdict_counts": tally}
    with _Stage("verdicts", on_step) as stage:
        rules = rule_book(firm.country)
        email = draft_email(_firm_name(firm), verdicts, rules)
        note = officer_note(verdicts, rules)
        stage.detail = "no email needed" if email == NOTHING_TO_ASK else "email drafted"
    calls = llm.calls[first_call:]
    return RunResult(
        firm_file=firm,
        verdicts=verdicts,
        lookups=lookups,
        calls=calls,
        unclassified=unclassified,
        email=email,
        officer_note=note,
        summary=_summary(firm, verdicts, calls, inputs, time.perf_counter() - started),
    )


def _call_key(call: CallLog) -> tuple[str, str, str, str]:
    return call.step, call.file, call.thinking, call.model.removesuffix(llm.CACHED_SUFFIX)


def _with_real_calls(calls: list[CallLog], previous: list[CallLog]) -> list[CallLog]:
    real = {_call_key(call): call for call in previous if not is_cached(call)}
    return [real.get(_call_key(call), call) if is_cached(call) else call for call in calls]


def _usage(calls: list[CallLog]) -> dict[str, float | int]:
    return {
        "tokens_in": sum(call.tokens_in for call in calls),
        "tokens_out": sum(call.tokens_out for call in calls),
        "rappen": round(sum(map(llm.cost_rappen, calls)), 4),
    }


def _with_call_costs(summary: RunSummary, calls: list[CallLog]) -> RunSummary:
    rows = [
        row.model_copy(
            update={
                **_usage([c for c in calls if c.file == row.file]),
                "seconds": round(sum(c.seconds for c in calls if c.file == row.file), 2),
            }
        )
        for row in summary.per_document
    ]
    totals = {**_usage(calls), "model_seconds": round(sum(c.seconds for c in calls), 2)}
    return summary.model_copy(update={**totals, "per_document": rows})


def _result_path(result: RunResult) -> Path:
    level = result.summary.thinking if result.summary else llm.DEFAULT_THINKING
    suffix = "" if level == llm.DEFAULT_THINKING else f".{level}"
    return RESULTS_DIR / f"{result.firm_file.slug}{suffix}.json"


def merge_with_saved(result: RunResult) -> RunResult:
    path = _result_path(result)
    if not path.exists() or not any(map(is_cached, result.calls)):
        return result
    stored = json.loads(path.read_text(encoding="utf-8"))
    update = {"calls": _with_real_calls(result.calls, CALL_LIST.validate_python(stored["calls"]))}
    if result.summary:
        summary = _with_call_costs(result.summary, update["calls"])
        if all(map(is_cached, result.calls)) and stored.get("summary"):
            summary.wall_seconds = RunSummary.model_validate(stored["summary"]).wall_seconds
        update["summary"] = summary
    return result.model_copy(update=update)


def save(result: RunResult) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = _result_path(result)
    path.write_text(merge_with_saved(result).model_dump_json(indent=2), encoding="utf-8")
    return path


def cache_caption(summary: RunSummary) -> str:
    if not summary.cached_calls:
        return ""
    return f"from cache; live run took {summary.wall_seconds:.1f} s and cost {summary.rappen:.2f} rappen"


def usage_text(event: StepEvent) -> str:
    if event.cached:
        return f"{event.seconds:.1f} s, cached"
    if event.tokens_in or event.tokens_out:
        return f"{event.seconds:.1f} s, {event.tokens_in}+{event.tokens_out} tokens"
    return f"{event.seconds:.1f} s"


def format_event(event: StepEvent) -> str:
    usage = f" ({usage_text(event)})" if event.status != "running" else ""
    return f"[{event.step}] {event.status}{usage} {event.detail}".rstrip()


def newest_first(events: list[StepEvent]) -> str:
    return "\n".join(format_event(event) for event in reversed(events))


def summary_lines(summary: RunSummary) -> list[str]:
    return [
        f"wall {summary.wall_seconds:.1f} s | model {summary.model_seconds:.1f} s | "
        f"tokens {summary.tokens_in} in, {summary.tokens_out} out | {summary.rappen:.2f} rappen",
        f"{summary.documents} documents, {summary.fields} fields, {summary.low_confidence} low confidence | "
        f"pass {summary.passed}, fail {summary.failed}, unsure {summary.unsure} | "
        f"{summary.cached_calls} cached calls | thinking {summary.thinking}",
    ]


def print_table(result: RunResult) -> None:
    rule_width, status_width = COLUMN_WIDTHS
    if result.summary:
        print("\n" + "\n".join(summary_lines(result.summary)))
        if cache_caption(result.summary):
            print(cache_caption(result.summary))
        for row in result.summary.per_document:
            print(f"  {row.file:<28} {row.doc_type:<22} {row.read_from:<10} p{row.pages} "
                  f"{row.fields}f {row.low_confidence}low {row.seconds:.1f}s "
                  f"{row.tokens_in}+{row.tokens_out}t {row.rappen:.2f} rappen")
    print(f"\n{'rule':<{rule_width}} {'status':<{status_width}} reason")
    for verdict in result.verdicts:
        print(f"{verdict.rule_id:<{rule_width}} {verdict.status:<{status_width}} {verdict.reason[:REASON_WIDTH]}")
    if result.unclassified:
        print(f"Not recognised: {', '.join(result.unclassified)}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m supplier_check.pipeline")
    parser.add_argument("folder", type=Path, help="data/firms/<slug>")
    parser.add_argument("--thinking", choices=list(llm.THINKING_LEVELS), default=llm.DEFAULT_THINKING)
    parser.add_argument("--live", action="store_true", help="ignore cached model answers for this run")
    args = parser.parse_args(argv)
    if not args.folder.is_dir():
        parser.error(f"{args.folder} is not a folder")
    llm.use_thinking(args.thinking)
    llm.use_live(args.live)
    events: list[StepEvent] = []
    result = merge_with_saved(check_firm(args.folder, events.append))
    print("Run log, newest first:\n" + newest_first(events))
    print_table(result)
    print(f"Saved {save(result)}")


if __name__ == "__main__":
    main()
