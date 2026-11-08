import json
import re
import shutil
from collections.abc import Iterable
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from supplier_check import llm
from supplier_check.models import CallLog, RunResult, parse_date

ROOT = Path(__file__).resolve().parents[1]
FIRMS_DIR = ROOT / "data" / "firms"
RESULTS_DIR = ROOT / "eval" / "results"
REPORT_FILE = RESULTS_DIR / "eval_report.md"
DOCS_COPY = ROOT / "docs" / "eval_report.md"
SLUGS = ["hansen-elektrotechnik", "weber-stahlbau", "mueller-geruestbau", "baltic-krane", "nordhaus-bau"]
LEVEL_FILES = {"minimal": "{slug}.json", "normal": "{slug}.normal.json"}
NO_VISION_FILE = "baltic-krane.novision.json"
CLASSIFY_STEP = "Classification"
SCAN_ROW = "read from scan"
SCAN_KINDS = {"page_image", "page_image_two_reads"}
TWO_READS_KIND = "page_image_two_reads"
SECOND_READ_MODEL = llm.MODELS["fast"]
EXPECTED: dict[str, dict[str, str]] = {
    "hansen-elektrotechnik": {},
    "weber-stahlbau": {"DE-INS-01": "fail"},
    "mueller-geruestbau": {
        "DE-DOC-04": "fail",
        "DE-INS-02": "fail",
        "DE-INS-03": "unsure",
        "DE-ISO-02": "unsure",
        "DE-ISO-03": "unsure",
        "DE-BNK-01": "unsure",
    },
    "baltic-krane": {f"DE-INS-0{n}": "pass" for n in range(1, 5)},
    "nordhaus-bau": {"DE-REG-02": "fail", "DE-INS-04": "unsure", "DE-INS-05": "unsure", "DE-SAN-01": "unsure"},
}
AMOUNT = re.compile(r"^(?:EUR\s*)?(\d[\d.\s]*)(?:,\d{1,2})?\s*(?:EUR)?$", re.IGNORECASE)
SPACES = re.compile(r"\s+")

Outcome = Literal["match", "caught", "confident_wrong"]
OUTCOME_LABELS = {"caught": "wrong, unsure caught", "confident_wrong": "confident but wrong"}


class FieldOutcome(BaseModel):
    firm: str
    document: str
    field: str
    expected: str
    got: str
    confidence: str
    quote: str
    from_scan: bool
    exact: bool
    normalised: bool

    @property
    def outcome(self) -> Outcome:
        if self.exact or self.normalised:
            return "match"
        return "caught" if self.confidence == "low" else "confident_wrong"


class Counts(BaseModel):
    compared: int = 0
    exact: int = 0
    normalised_only: int = 0
    wrong: int = 0
    low: int = 0
    caught: int = 0
    confident_wrong: int = 0

    def add(self, item: FieldOutcome) -> None:
        self.compared += 1
        self.exact += item.exact
        self.normalised_only += item.normalised and not item.exact
        self.low += item.confidence == "low"
        self.wrong += item.outcome != "match"
        self.caught += item.outcome == "caught"
        self.confident_wrong += item.outcome == "confident_wrong"

    def cells(self) -> list[str]:
        return [str(v) for v in self.model_dump().values()]


def normalise_value(value: object) -> str:
    if value is None:
        return ""
    text = SPACES.sub(" ", str(value)).strip()
    parsed = parse_date(text)
    if parsed:
        return parsed.isoformat()
    amount = AMOUNT.match(text)
    if amount:
        return str(int(re.sub(r"[.\s]", "", amount.group(1))))
    return text.casefold()


def _raw(value: object) -> str:
    return "" if value is None else str(value)


def compare_firm(slug: str, result: RunResult) -> list[FieldOutcome]:
    key = json.loads((FIRMS_DIR / slug / "answer_key.json").read_text(encoding="utf-8"))
    docs = {doc.doc_type: doc for doc in result.firm_file.documents}
    outcomes = []
    for doc_type, expected_doc in key["documents"].items():
        doc = docs.get(doc_type)
        for name, expected in expected_doc["fields"].items():
            field = doc.fields.get(name) if doc else None
            got = field.value if field else None
            source = field.source if field else None
            outcomes.append(
                FieldOutcome(
                    firm=slug,
                    document=doc_type,
                    field=name,
                    expected=_raw(expected["value"]),
                    got=_raw(got),
                    confidence=field.confidence if field else "low",
                    quote=source.quote if source else "",
                    from_scan=bool(source and source.kind in SCAN_KINDS),
                    exact=_raw(got) == _raw(expected["value"]),
                    normalised=normalise_value(got) == normalise_value(expected["value"]),
                )
            )
    return outcomes


def load(slug: str, pattern: str = "{slug}.json") -> RunResult | None:
    path = RESULTS_DIR / pattern.format(slug=slug)
    return RunResult.model_validate_json(path.read_text(encoding="utf-8")) if path.exists() else None


def table(headers: list[str], rows: Iterable[list[str]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(cell.replace("|", "/") for cell in row) + " |" for row in rows]
    return "\n".join(lines)


COUNT_HEADERS = ["compared", "exact", "match after normalising", "wrong", "low confidence",
                 "wrong, unsure caught", "confident but wrong"]


def field_type_table(outcomes: list[FieldOutcome]) -> str:
    groups: dict[str, Counts] = {}
    for item in outcomes:
        groups.setdefault(SCAN_ROW if item.from_scan else item.field, Counts()).add(item)
    order = sorted(k for k in groups if k != SCAN_ROW) + ([SCAN_ROW] if SCAN_ROW in groups else [])
    return table(["field", *COUNT_HEADERS], ([name, *groups[name].cells()] for name in order))


def _planted(result: RunResult, expected: dict[str, str]) -> tuple[str, str]:
    statuses = {v.rule_id: v.status for v in result.verdicts}
    hits = [rule for rule, status in expected.items() if statuses.get(rule) == status]
    caught = f"{len(hits)} of {len(expected)}" if expected else ("all pass" if set(statuses.values()) == {"pass"} else "no")
    extra = [f"{r} {s}" for r, s in statuses.items() if s != "pass" and r not in expected]
    return caught, ", ".join(extra) or "none"


def firm_rows(results: dict[str, RunResult], outcomes: list[FieldOutcome]) -> list[list[str]]:
    rows = []
    for slug, result in results.items():
        counts = Counts()
        for item in outcomes:
            if item.firm == slug:
                counts.add(item)
        verdicts = [v.status for v in result.verdicts]
        caught, extra = _planted(result, EXPECTED[slug])
        totals = f"{verdicts.count('pass')} / {verdicts.count('fail')} / {verdicts.count('unsure')}"
        rows.append([slug, *counts.cells(), totals, caught, extra])
    return rows


def planted_rows(results: dict[str, RunResult]) -> list[list[str]]:
    rows = []
    for slug, result in results.items():
        statuses = {v.rule_id: v.status for v in result.verdicts}
        for rule, want in EXPECTED[slug].items():
            got = statuses.get(rule, "missing")
            rows.append([slug, rule, want, got, "yes" if got == want else "NO"])
    return rows


def miss_lines(outcomes: list[FieldOutcome]) -> list[str]:
    misses = [o for o in outcomes if o.outcome != "match"]
    misses.sort(key=lambda o: o.outcome != "confident_wrong")
    return [
        f"- {OUTCOME_LABELS[o.outcome]}: {o.firm}, {o.document}, {o.field}, expected '{o.expected}', "
        f"got '{o.got}', confidence {o.confidence}, quote '{o.quote}'"
        for o in misses
    ] or ["- none"]


def _step(call: CallLog) -> str:
    return "classify" if call.step == CLASSIFY_STEP else "extract"


def _usage_cells(calls: list[CallLog]) -> list[str]:
    real = [c for c in calls if not c.model.endswith(llm.CACHED_SUFFIX)]
    return [
        str(len(real)),
        str(sum(c.tokens_in for c in real)),
        str(sum(c.tokens_out for c in real)),
        f"{sum(c.seconds for c in real):.1f}",
        f"{sum(map(llm.cost_rappen, real)):.2f}",
    ]


def cost_rows(results: dict[str, RunResult]) -> list[list[str]]:
    rows = []
    for slug, result in results.items():
        for step in ("classify", "extract"):
            rows.append([slug, step, *_usage_cells([c for c in result.calls if _step(c) == step])])
        rows.append([slug, "total", *_usage_cells(result.calls)])
    return rows


def thinking_rows() -> list[list[str]]:
    rows = []
    for slug in SLUGS:
        for level, pattern in LEVEL_FILES.items():
            result = load(slug, pattern)
            if result is None:
                rows.append([slug, level, "no result file", "", "", "", "", ""])
                continue
            outcomes = compare_firm(slug, result)
            right = sum(o.outcome == "match" for o in outcomes)
            usage = _usage_cells(result.calls)
            rows.append([slug, level, f"{right}/{len(outcomes)}", *usage[1:]])
    return rows


def _two_reads_lines(result: RunResult) -> list[str]:
    scan = [o for o in compare_firm("baltic-krane", result) if o.from_scan]
    doc = next(d for d in result.firm_file.documents if d.doc_type == "insurance_certificate")
    agreed = [n for n, f in doc.fields.items() if f.source and f.source.kind == TWO_READS_KIND]
    second = [c for c in result.calls if c.file == doc.file and c.model == SECOND_READ_MODEL and c.step != CLASSIFY_STEP]
    lines = [
        f"- Scan: two reads. Read A {llm.MODELS['careful']}, read B {SECOND_READ_MODEL}, both on the PDF bytes. "
        f"{sum(o.normalised for o in scan)} of {len(scan)} answer-key fields match; the two reads agree on "
        f"{len(agreed)} of {len(doc.fields)} schema fields, which become high confidence.",
        f"  - Read B added {_usage_cells(second)[1]} tokens in, {_usage_cells(second)[2]} tokens out, "
        f"{_usage_cells(second)[4]} rappen.",
    ]
    lines += [f"  - {o.field}: expected '{o.expected}', got '{o.got}', confidence {o.confidence}" for o in scan]
    lines += [f"  - {name}: {f.note}" for name, f in doc.fields.items() if f.note]
    return lines


def scan_section() -> list[str]:
    lines = []
    with_vision = load("baltic-krane")
    if with_vision:
        lines += _two_reads_lines(with_vision)
    without = load("baltic-krane", NO_VISION_FILE)
    if without:
        unread = ", ".join(f"{u.file} ({u.reason})" for u in without.firm_file.unreadable) or "none"
        flagged = ", ".join(f"{v.rule_id} {v.status}" for v in without.verdicts if v.status != "pass")
        lines.append(f"- Vision off: unreadable files: {unread}. Non-pass rules: {flagged}.")
    return lines or ["- no baltic-krane result files"]


def _header() -> list[str]:
    usd = llm.PRICE_USD_PER_MILLION
    prices = "; ".join(f"{m}: {i} USD in, {o} USD out per million tokens" for m, (i, o) in usd.items())
    return [
        "# Eval report",
        "",
        f"All numbers are measured on {date.today().isoformat()} from the saved runs in `eval/results/`, "
        "compared with `data/firms/<slug>/answer_key.json`. All firms and documents are mock.",
        f"Prices from {llm.PRICE_SOURCE}, checked {llm.PRICE_CHECKED}: {prices}.",
        f"Cost is in rappen (Swiss cents, 100 rappen = 1 CHF) at an assumed {llm.CHF_PER_USD} CHF per USD "
        "(not verified; x-rates.com showed 0.8198 on 2026-11-08).",
        "Main runs use thinking level minimal (gemini-3.8-flash at ThinkingLevel.LOW) with vision on for scans.",
        "",
    ]


def build_report() -> str:
    results = {slug: r for slug in SLUGS if (r := load(slug))}
    outcomes = [o for slug, result in results.items() for o in compare_firm(slug, result)]
    firm_headers = ["firm", *COUNT_HEADERS, "pass / fail / unsure", "planted caught", "other non-pass rules"]
    sections = [
        *_header(),
        "## Accuracy per field type (measured, all firms)",
        "Scan fields are counted only in the 'read from scan' row.",
        "",
        field_type_table(outcomes),
        "",
        "## Accuracy and verdicts per firm (measured)",
        "",
        table(firm_headers, firm_rows(results, outcomes)),
        "",
        "## Planted issues (measured)",
        "",
        table(["firm", "rule", "expected", "got", "caught"], planted_rows(results)),
        "",
        "## Misses (confident but wrong first)",
        "",
        *miss_lines(outcomes),
        "",
        "## Cost per firm and step (measured, live calls only)",
        "",
        table(["firm", "step", "live calls", "tokens in", "tokens out", "model seconds", "rappen"],
              cost_rows(results)),
        "",
        "## Thinking level comparison (measured)",
        "Normal result files keep older verdicts; only their fields and call logs are used here.",
        "For baltic-krane the normal run sent the scan as the embedded PNG, the minimal run as PDF bytes "
        "at medium resolution, so its token counts differ in input as well as thinking.",
        "",
        table(["firm", "level", "fields right", "tokens in", "tokens out", "model seconds", "rappen"],
              thinking_rows()),
        "",
        "## Scan handling, baltic-krane (measured)",
        "",
        *scan_section(),
        "",
    ]
    return "\n".join(sections)


def main() -> None:
    report = build_report()
    print(report)
    REPORT_FILE.write_text(report, encoding="utf-8")
    DOCS_COPY.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(REPORT_FILE, DOCS_COPY)
    print(f"Wrote {REPORT_FILE} and {DOCS_COPY}")


if __name__ == "__main__":
    main()
