from collections.abc import Callable
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, field_validator

DocType = Literal[
    "register_extract",
    "insurance_certificate",
    "iso_9001",
    "iso_45001",
    "safety_record",
    "bank_letter",
]
Status = Literal["pass", "fail", "unsure"]
Confidence = Literal["high", "low"]
Tier = Literal["fast", "careful"]
Thinking = Literal["normal", "minimal"]
ReadFrom = Literal["text", "page_image", "unreadable"]

DATE_FORMATS = ("%Y-%m-%d", "%d.%m.%Y", "%d %B %Y")


def parse_date(text: str) -> date | None:
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text.strip(), fmt).date()
        except ValueError:
            continue
    return None


class Source(BaseModel):
    file: str
    page: int
    quote: str
    kind: Literal["text", "page_image", "page_image_two_reads"] = "text"


class Field(BaseModel):
    value: str | int | date | None
    source: Source | None
    confidence: Confidence
    note: str = ""

    @field_validator("value", mode="before")
    @classmethod
    def dates_from_text(cls, value: object) -> object:
        if isinstance(value, str):
            return parse_date(value) or value
        return value


class ExtractedDocument(BaseModel):
    doc_type: DocType
    file: str
    language: str
    fields: dict[str, Field]


class UnreadableFile(BaseModel):
    file: str
    reason: str


class FirmFile(BaseModel):
    slug: str
    country: str
    as_of: date
    documents: list[ExtractedDocument]
    unreadable: list[UnreadableFile] = []


class Verdict(BaseModel):
    rule_id: str
    requirement: str
    status: Status
    reason: str
    evidence: list[Source]
    deferred: bool = False


class LookupResult(BaseModel):
    source: Literal["mock_register", "mock_sanctions"]
    query: str
    match: str | None
    score: float
    note: str


class CallLog(BaseModel):
    step: str
    model: str
    tokens_in: int
    tokens_out: int
    seconds: float
    file: str = ""
    thinking: str = ""


StepName = Literal["read_text", "classify", "extract", "lookups", "rules", "verdicts"]


class StepEvent(BaseModel):
    step: StepName
    status: Literal["running", "done", "failed"]
    seconds: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    cached: bool = False
    detail: str = ""


class Finding(BaseModel):
    status: Status
    reason: str
    evidence: list[Source] = []
    deferred: bool = False


class RuleContext(BaseModel):
    firm: FirmFile
    lookups: dict[str, LookupResult] = {}


class Rule(BaseModel):
    rule_id: str
    requirement: str
    ask: str
    external: str = ""
    internal_only: bool = False
    check: Callable[[RuleContext], Finding]


class DocSummary(BaseModel):
    file: str
    doc_type: str
    read_from: ReadFrom
    pages: int
    fields: int
    low_confidence: int
    seconds: float
    tokens_in: int
    tokens_out: int
    rappen: float


class RunSummary(BaseModel):
    wall_seconds: float
    model_seconds: float
    tokens_in: int
    tokens_out: int
    rappen: float
    documents: int
    fields: int
    low_confidence: int
    passed: int
    failed: int
    unsure: int
    cached_calls: int
    thinking: Thinking
    per_document: list[DocSummary]


class RunResult(BaseModel):
    firm_file: FirmFile
    verdicts: list[Verdict]
    lookups: list[LookupResult]
    calls: list[CallLog]
    unclassified: list[str]
    email: str
    officer_note: str = ""
    summary: RunSummary | None = None


class Decision(BaseModel):
    slug: str
    decision: Literal["approved", "rejected"]
    decided_at: datetime


class Classification(BaseModel):
    doc_type: DocType | Literal["other"]


class _Evidence(BaseModel):
    page: int
    quote: str
    confidence: Confidence


class TextValue(_Evidence):
    value: str | None


class NumberValue(_Evidence):
    value: int | None


class DateValue(_Evidence):
    value: str | None


class _DocFields(BaseModel):
    language: str


class RegisterExtractFields(_DocFields):
    legal_name: TextValue
    registration_number: TextValue
    register_court: TextValue
    legal_form: TextValue
    registered_address: TextValue
    managing_director: TextValue
    date_of_extract: DateValue


class InsuranceCertificateFields(_DocFields):
    insurer: TextValue
    policy_number: TextValue
    insured_name: TextValue
    coverage_type: TextValue
    insured_amount_eur: NumberValue
    valid_from: DateValue
    valid_until: DateValue
    insured_address: TextValue


class IsoCertificateFields(_DocFields):
    certificate_number: TextValue
    holder_name: TextValue
    standard: TextValue
    scope: TextValue
    issuer: TextValue
    valid_until: DateValue


class SafetyRecordFields(_DocFields):
    firm_name: TextValue
    period: TextValue
    reportable_accidents: NumberValue
    lost_time_injuries: NumberValue
    fatalities: NumberValue


class BankLetterFields(_DocFields):
    bank_name: TextValue
    account_holder: TextValue
    iban: TextValue
    date: DateValue
