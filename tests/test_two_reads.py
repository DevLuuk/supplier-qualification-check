from datetime import date

import pytest

from supplier_check import extract as extract_module
from supplier_check.extract import extract_scan, merge_reads, values_agree
from supplier_check.models import ExtractedDocument, Field, Source


def _field(value: object, quote: str) -> Field:
    source = Source(file="insurance_certificate.pdf", page=1, quote=quote, kind="page_image")
    return Field(value=value, source=source, confidence="low")


def _read(**fields: Field) -> ExtractedDocument:
    return ExtractedDocument(
        doc_type="insurance_certificate", file="insurance_certificate.pdf", language="de", fields=fields
    )


READ_A = _read(
    insured_amount_eur=_field(5_000_000, "Deckungssumme EUR 5 Mio."),
    valid_until=_field("2027-03-31", "Versicherungsende 31.03.2027"),
    insured_name=_field("Baltic Krane GmbH", "Versicherungsnehmer Baltic Krane GmbH"),
)


def test_agreeing_reads_give_high_confidence():
    read_b = _read(
        insured_amount_eur=_field(5_000_000, "EUR 5 Mio."),
        valid_until=_field("31.03.2027", "31.03.2027"),
        insured_name=_field("baltic  krane gmbh", "Baltic Krane GmbH"),
    )
    merged = merge_reads(READ_A, read_b)
    for field in merged.fields.values():
        assert field.confidence == "high"
        assert field.source.kind == "page_image_two_reads"
        assert field.note == ""


def test_disagreeing_reads_stay_low_with_both_values():
    read_b = _read(**{**READ_A.fields, "insured_amount_eur": _field(3_000_000, "EUR 3 Mio.")})
    field = merge_reads(READ_A, read_b).fields["insured_amount_eur"]
    assert field.confidence == "low"
    assert field.note == "two reads differ: A=5000000 B=3000000"
    assert field.source.kind == "page_image"


def test_missing_in_second_read_stays_low():
    read_b = _read(valid_until=READ_A.fields["valid_until"])
    merged = merge_reads(READ_A, read_b)
    assert merged.fields["insured_name"].confidence == "low"
    assert merged.fields["insured_name"].note == "two reads differ: A=Baltic Krane GmbH B=None"
    assert merged.fields["valid_until"].confidence == "high"


def test_missing_in_first_read_stays_low():
    read_a = _read(insured_name=_field(None, "Versicherungsnehmer"))
    merged = merge_reads(read_a, READ_A)
    assert merged.fields["insured_name"].confidence == "low"


def test_agreeing_value_not_in_its_quote_stays_low():
    read_a = _read(insured_amount_eur=_field(5_000_000, "Deckungssumme EUR 3 Mio."))
    read_b = _read(insured_amount_eur=_field(5_000_000, "EUR 5 Mio."))
    assert merge_reads(read_a, read_b).fields["insured_amount_eur"].confidence == "low"


@pytest.mark.parametrize(
    ("a", "b", "agree"),
    [
        (date(2027, 3, 31), date(2027, 3, 31), True),
        (date(2027, 3, 31), date(2027, 3, 30), False),
        (5_000_000, 5_000_000, True),
        (5_000_000, "5000000", False),
        ("DE06 1305 0001", "DE0613050001", True),
        (None, None, False),
    ],
)
def test_values_agree(a, b, agree):
    assert values_agree(a, b) is agree


def test_switch_off_keeps_single_low_read(monkeypatch):
    calls = []

    def fake_extract(doc_type, file, pages, images, tier="careful"):
        calls.append(tier)
        return READ_A

    monkeypatch.setattr(extract_module, "extract", fake_extract)
    monkeypatch.setattr(extract_module, "SCAN_READS_MUST_AGREE", False)
    result = extract_scan("insurance_certificate", "insurance_certificate.pdf", [""], [b"%PDF"])
    assert calls == ["careful"]
    assert all(field.confidence == "low" for field in result.fields.values())


def test_switch_on_reads_twice_with_two_tiers(monkeypatch):
    calls = []

    def fake_extract(doc_type, file, pages, images, tier="careful"):
        calls.append(tier)
        return READ_A

    monkeypatch.setattr(extract_module, "extract", fake_extract)
    monkeypatch.setattr(extract_module, "SCAN_READS_MUST_AGREE", True)
    extract_scan("insurance_certificate", "insurance_certificate.pdf", [""], [b"%PDF"])
    assert calls == ["careful", "fast"]


def test_missing_in_both_reads_stays_low_with_plain_note():
    read = _read(insured_address=_field(None, "Anschrift"))
    field = merge_reads(read, read).fields["insured_address"]
    assert (field.confidence, field.note) == ("low", "missing in both reads")
