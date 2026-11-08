import re
from datetime import date

from pydantic import BaseModel

from supplier_check.llm import complete
from supplier_check.models import (
    BankLetterFields,
    DocType,
    ExtractedDocument,
    Field,
    InsuranceCertificateFields,
    IsoCertificateFields,
    RegisterExtractFields,
    SafetyRecordFields,
    Source,
    Tier,
    parse_date,
)

SCHEMAS: dict[DocType, type[BaseModel]] = {
    "register_extract": RegisterExtractFields,
    "insurance_certificate": InsuranceCertificateFields,
    "iso_9001": IsoCertificateFields,
    "iso_45001": IsoCertificateFields,
    "safety_record": SafetyRecordFields,
    "bank_letter": BankLetterFields,
}

PROMPT = """You read one onboarding document ({doc_type}) and copy values out of it.
Rules:
- Copy each value exactly as printed. Never invent a value. Never guess.
- quote: the exact sentence or table row the value came from, copied character for character.
  For a table row, quote the label and the value together, for example "Versicherungsende 28.02.2027".
- page: the page number the quote is on.
- confidence: "high" only when the value is printed clearly. "low" when it is absent, ambiguous or you had to interpret it.
- If a value is absent: value null, quote "", confidence "low".
- Dates: return ISO format YYYY-MM-DD.
- Money and counts: return a whole number (10.000.000,00 EUR becomes 10000000, 2,5 Mio. EUR becomes 2500000).
- valid_from and valid_until are the period of cover, not the date the document was issued.
- A cover letter may come first; read the values from the main document.
- IBAN: return it without spaces.
- legal_form: return the short form in brackets, for example GmbH.
- period: return as YYYY-YYYY.
- language: the ISO 639-1 code of the document language, for example de or en."""

LANGUAGE_FIELD = "language"
SCAN_READS_MUST_AGREE = True
SECOND_READ_TIER: Tier = "fast"
MISSING_IN_BOTH = "missing in both reads"
MILLION = 1_000_000
NUMBER = re.compile(r"(\d[\d.,]*)\s*(Mio\.?|Millionen|million)?", re.IGNORECASE)
DATE_TEXT = re.compile(r"\d{4}-\d{2}-\d{2}|\d{1,2}\.\d{1,2}\.\d{4}|\d{1,2} [A-Za-z]+ \d{4}")
ZERO_WORDS = {"no", "none", "zero", "keine", "kein", "null"}
IMAGE_NOTE = "\n- The document is a scan. It is attached as page images; read the values from the images."


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def _clean(value: object) -> object:
    return re.sub(r"\s+", " ", value).strip() if isinstance(value, str) else value


def _as_number(text: str) -> set[float]:
    readings = set()
    for candidate in (text.replace(".", "").replace(",", "."), text.replace(",", "")):
        try:
            readings.add(float(candidate))
        except ValueError:
            continue
    return readings


def _numbers_in(quote: str) -> set[int]:
    found = set()
    for match in NUMBER.finditer(quote):
        factor = MILLION if match.group(2) else 1
        found |= {int(n * factor) for n in _as_number(match.group(1).rstrip(".,")) if (n * factor).is_integer()}
    words = set(re.findall(r"\w+", quote.casefold()))
    return found | ({0} if words & ZERO_WORDS else set())


def _dates_in(quote: str) -> set[date]:
    return {parsed for text in DATE_TEXT.findall(quote) if (parsed := parse_date(text))}


def _text_supported(value: str, quote: str) -> bool:
    plain_value, plain_quote = _squash(value), _squash(quote)
    if plain_value in plain_quote or plain_value.replace(" ", "") in plain_quote.replace(" ", ""):
        return True
    return set(re.findall(r"\w+", plain_value)) <= set(re.findall(r"\w+", plain_quote))


def value_supported(value: object, quote: str) -> bool:
    if value is None:
        return True
    if isinstance(value, bool) or not isinstance(value, (int, date, str)):
        return False
    if isinstance(value, int):
        return value in _numbers_in(quote)
    if isinstance(value, date):
        return value in _dates_in(quote)
    return _text_supported(value, quote)


def _to_field(raw: dict, file: str, pages_text: str | None) -> Field:
    quote = raw["quote"].strip()
    if not quote:
        return Field(value=_clean(raw["value"]), source=None, confidence="low")
    from_image = pages_text is None
    field = Field(
        value=_clean(raw["value"]),
        source=Source(file=file, page=raw["page"], quote=quote, kind="page_image" if from_image else "text"),
        confidence=raw["confidence"],
    )
    verified = not from_image and _squash(quote) in pages_text and value_supported(field.value, quote)
    if not verified:
        field.confidence = "low"
    return field


def values_agree(a: object, b: object) -> bool:
    if a is None or b is None or isinstance(a, bool) or isinstance(b, bool):
        return False
    if isinstance(a, (int, date)) or isinstance(b, (int, date)):
        return a == b
    return _squash(str(a)).replace(" ", "") == _squash(str(b)).replace(" ", "")


def _merged_field(first: Field, second: Field | None) -> Field:
    other = second.value if second else None
    agreed = (
        first.source is not None
        and values_agree(first.value, other)
        and value_supported(first.value, first.source.quote)
    )
    if not agreed:
        both_missing = first.value is None and other is None
        note = MISSING_IN_BOTH if both_missing else f"two reads differ: A={first.value} B={other}"
        return first.model_copy(update={"confidence": "low", "note": note})
    source = first.source.model_copy(update={"kind": "page_image_two_reads"})
    return first.model_copy(update={"confidence": "high", "source": source, "note": ""})


def merge_reads(read_a: ExtractedDocument, read_b: ExtractedDocument) -> ExtractedDocument:
    fields = {name: _merged_field(field, read_b.fields.get(name)) for name, field in read_a.fields.items()}
    return read_a.model_copy(update={"fields": fields})


def extract_scan(doc_type: DocType, file: str, pages: list[str], images: list[bytes]) -> ExtractedDocument:
    read_a = extract(doc_type, file, pages, images)
    if not SCAN_READS_MUST_AGREE:
        return read_a
    return merge_reads(read_a, extract(doc_type, file, pages, images, SECOND_READ_TIER))


def extract(
    doc_type: DocType,
    file: str,
    pages: list[str],
    images: list[bytes] | None = None,
    tier: Tier = "careful",
) -> ExtractedDocument:
    prompt = PROMPT.format(doc_type=doc_type) + (IMAGE_NOTE if images else "")
    result = complete(prompt, SCHEMAS[doc_type], pages, tier, images)
    raw = result.model_dump()
    pages_text = None if images else _squash(" ".join(pages))
    fields = {
        name: _to_field(value, file, pages_text)
        for name, value in raw.items()
        if name != LANGUAGE_FIELD
    }
    return ExtractedDocument(
        doc_type=doc_type, file=file, language=raw[LANGUAGE_FIELD], fields=fields
    )
