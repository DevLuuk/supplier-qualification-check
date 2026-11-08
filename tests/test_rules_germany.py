from datetime import date

import pytest

from supplier_check.models import (
    ExtractedDocument,
    Field,
    FirmFile,
    Source,
    UnreadableFile,
    Verdict,
)
from supplier_check.rules import run_rules

AS_OF = date(2026, 11, 9)
LEGAL_NAME = "Hansen Elektrotechnik GmbH"


def _doc(doc_type: str, values: dict) -> ExtractedDocument:
    fields = {
        name: Field(
            value=value,
            source=Source(file=f"{doc_type}.pdf", page=1, quote=f"{name} {value}"),
            confidence="high",
        )
        for name, value in values.items()
    }
    return ExtractedDocument(doc_type=doc_type, file=f"{doc_type}.pdf", language="de", fields=fields)


def _clean_values(name: str = LEGAL_NAME) -> dict[str, dict]:
    return {
        "register_extract": {
            "legal_name": name,
            "registration_number": "HRB 148263",
            "registered_address": "Kaiserdamm 41, 22301 Hamburg",
        },
        "insurance_certificate": {
            "insured_name": name,
            "insured_address": None,
            "insured_amount_eur": 5_000_000,
            "valid_from": "2026-01-01",
            "valid_until": "2026-12-31",
        },
        "iso_9001": {"holder_name": name, "valid_until": "2027-06-30"},
        "iso_45001": {"holder_name": name, "valid_until": "2027-06-30"},
        "safety_record": {"firm_name": name, "period": "2023-2025", "fatalities": 0},
        "bank_letter": {"account_holder": name},
    }


def _firm(values: dict[str, dict]) -> FirmFile:
    documents = [_doc(doc_type, fields) for doc_type, fields in values.items()]
    return FirmFile(slug="test", country="DE", as_of=AS_OF, documents=documents)


def _by_id(verdicts: list[Verdict]) -> dict[str, Verdict]:
    return {verdict.rule_id: verdict for verdict in verdicts}


def _mueller_values() -> dict[str, dict]:
    values = _clean_values("Müller Gerüstbau GmbH")
    values["register_extract"]["registration_number"] = "HRB 209317"
    values["insurance_certificate"]["insured_name"] = "Mueller Geruestbau GmbH"
    values["insurance_certificate"]["insured_amount_eur"] = 3_000_000
    values["iso_9001"]["holder_name"] = "Müller Gerüstbau GmbH & Co. KG"
    values["bank_letter"]["account_holder"] = "Mueller Geruestbau GmbH"
    del values["iso_45001"]
    return values


def test_clean_firm_passes_everything():
    verdicts = run_rules(_firm(_clean_values()), "DE")
    assert len(verdicts) == 20
    assert {v.rule_id: v.status for v in verdicts if v.status != "pass"} == {}


def test_expired_insurance_fails_validity_only():
    values = _clean_values()
    values["insurance_certificate"]["valid_until"] = "2026-10-15"
    verdicts = _by_id(run_rules(_firm(values), "DE"))
    assert verdicts["DE-INS-01"].status == "fail"
    assert verdicts["DE-INS-04"].status == "unsure"
    assert {v.rule_id for v in verdicts.values() if v.status != "pass"} == {"DE-INS-01", "DE-INS-04"}


def test_mueller_case():
    verdicts = _by_id(run_rules(_firm(_mueller_values()), "DE"))
    statuses = {rule_id: v.status for rule_id, v in verdicts.items() if v.status != "pass"}
    assert statuses == {
        "DE-DOC-04": "fail",
        "DE-INS-02": "fail",
        "DE-INS-03": "unsure",
        "DE-ISO-02": "unsure",
        "DE-ISO-03": "unsure",
        "DE-BNK-01": "unsure",
    }
    assert verdicts["DE-ISO-02"].reason == "document missing"


def test_register_name_differs_from_extract():
    values = _clean_values("Weber Stahlbau GmbH")
    values["register_extract"]["registration_number"] = "HRB 774210"
    verdicts = _by_id(run_rules(_firm(values), "DE"))
    assert verdicts["DE-REG-01"].status == "pass"
    assert verdicts["DE-REG-02"].status == "unsure"
    assert "MOCK: " in verdicts["DE-REG-02"].reason


def test_unknown_register_number_fails():
    values = _clean_values()
    values["register_extract"]["registration_number"] = "HRB 000000"
    verdicts = _by_id(run_rules(_firm(values), "DE"))
    assert verdicts["DE-REG-01"].status == "fail"
    assert verdicts["DE-REG-02"].status == "unsure"


@pytest.mark.parametrize(
    ("amount", "status"), [(3_000_000, "fail"), (4_999_999, "fail"), (5_000_000, "pass")]
)
def test_insured_amount_boundary(amount, status):
    values = _clean_values()
    values["insurance_certificate"]["insured_amount_eur"] = amount
    assert _by_id(run_rules(_firm(values), "DE"))["DE-INS-02"].status == status


def test_insurance_valid_on_last_day():
    values = _clean_values()
    values["insurance_certificate"]["valid_until"] = AS_OF.isoformat()
    assert _by_id(run_rules(_firm(values), "DE"))["DE-INS-01"].status == "pass"


def test_german_date_text_is_parsed():
    values = _clean_values()
    values["insurance_certificate"]["valid_until"] = "15.10.2026"
    values["iso_9001"]["valid_until"] = "30 June 2027"
    verdicts = _by_id(run_rules(_firm(values), "DE"))
    assert verdicts["DE-INS-01"].status == "fail"
    assert verdicts["DE-ISO-01"].status == "pass"


def test_low_confidence_is_unsure_not_pass():
    firm = _firm(_clean_values())
    firm.documents[1].fields["valid_until"].confidence = "low"
    assert _by_id(run_rules(firm, "DE"))["DE-INS-01"].status == "unsure"


def test_missing_quote_is_unsure_not_pass():
    firm = _firm(_clean_values())
    firm.documents[1].fields["insured_amount_eur"].source = None
    assert _by_id(run_rules(firm, "DE"))["DE-INS-02"].status == "unsure"


def test_missing_value_is_unsure():
    firm = _firm(_clean_values())
    firm.documents[4].fields["fatalities"].value = None
    assert _by_id(run_rules(firm, "DE"))["DE-SAF-01"].status == "unsure"


def test_fatality_fails():
    values = _clean_values()
    values["safety_record"]["fatalities"] = 1
    assert _by_id(run_rules(_firm(values), "DE"))["DE-SAF-01"].status == "fail"


@pytest.mark.parametrize(
    ("period", "status"),
    [("2023-2025", "pass"), ("2024-2025", "fail"), ("2022-2024", "fail"), ("recent", "unsure")],
)
def test_safety_period(period, status):
    values = _clean_values()
    values["safety_record"]["period"] = period
    assert _by_id(run_rules(_firm(values), "DE"))["DE-SAF-02"].status == status


def test_sanctions_exact_match_fails():
    values = _clean_values("Hansen Elektro Trading Ltd")
    values["register_extract"]["registration_number"] = "HRB 148263"
    assert _by_id(run_rules(_firm(values), "DE"))["DE-SAN-01"].status == "fail"


def test_missing_register_extract_makes_name_rules_unsure():
    values = _clean_values()
    del values["register_extract"]
    verdicts = _by_id(run_rules(_firm(values), "DE"))
    assert verdicts["DE-DOC-01"].status == "fail"
    for rule_id in ("DE-REG-01", "DE-REG-02", "DE-INS-03", "DE-SAN-01", "DE-BNK-01"):
        assert verdicts[rule_id].status == "unsure"


def test_uk_stub_is_data():
    verdicts = run_rules(_firm(_clean_values()), "UK")
    assert [v.rule_id for v in verdicts] == ["UK-DOC-01", "UK-INS-01", "UK-INS-02"]


def test_unknown_country_raises():
    with pytest.raises(ValueError):
        run_rules(_firm(_clean_values()), "FR")


def test_unreadable_scan_makes_missing_document_unsure_not_fail():
    values = _clean_values()
    del values["insurance_certificate"]
    firm = _firm(values)
    firm.unreadable = [UnreadableFile(file="insurance_certificate.pdf", reason="no text layer (scan)")]
    verdicts = _by_id(run_rules(firm, "DE"))
    assert verdicts["DE-DOC-02"].status == "unsure"
    assert "no text layer (scan)" in verdicts["DE-DOC-02"].reason
    assert verdicts["DE-INS-01"].reason == "document missing"


@pytest.mark.parametrize(
    ("valid_until", "status", "reason"),
    [
        ("2026-12-09", "pass", "Valid for 30 more days."),
        ("2026-12-08", "unsure", "valid today, expires in 29 days"),
        ("2026-11-14", "unsure", "valid today, expires in 5 days"),
    ],
)
def test_insurance_runway(valid_until, status, reason):
    values = _clean_values()
    values["insurance_certificate"]["valid_until"] = valid_until
    verdict = _by_id(run_rules(_firm(values), "DE"))["DE-INS-04"]
    assert (verdict.status, verdict.reason) == (status, reason)


@pytest.mark.parametrize(
    ("insured_address", "status"),
    [
        (None, "pass"),
        ("Kaiserdamm 41, 22301 Hamburg", "pass"),
        ("kaiserdamm  41 22301 hamburg", "pass"),
        ("Industriestraße 9, 27568 Bremerhaven", "unsure"),
    ],
)
def test_insured_address(insured_address, status):
    values = _clean_values()
    values["insurance_certificate"]["insured_address"] = insured_address
    verdict = _by_id(run_rules(_firm(values), "DE"))["DE-INS-05"]
    assert verdict.status == status
    if insured_address is None:
        assert verdict.reason == "certificate prints no address"


def test_street_abbreviation_matches():
    values = _clean_values()
    values["register_extract"]["registered_address"] = "Hafenstraße 27, 44263 Dortmund"
    values["insurance_certificate"]["insured_address"] = "Hafenstr. 27, 44263 Dortmund"
    assert _by_id(run_rules(_firm(values), "DE"))["DE-INS-05"].status == "pass"


def test_sanctions_near_miss_with_firm_name_inside_is_unsure():
    values = _clean_values("Nordhaus Bau GmbH")
    assert _by_id(run_rules(_firm(values), "DE"))["DE-SAN-01"].status == "unsure"


def test_expired_insurance_runway_is_deferred_by_flag():
    values = _clean_values()
    values["insurance_certificate"]["valid_until"] = "2026-10-15"
    verdicts = _by_id(run_rules(_firm(values), "DE"))
    assert verdicts["DE-INS-04"].deferred
    assert not verdicts["DE-INS-01"].deferred


def test_missing_document_dependents_are_deferred_by_flag():
    values = _clean_values()
    del values["iso_45001"]
    verdicts = _by_id(run_rules(_firm(values), "DE"))
    assert verdicts["DE-ISO-02"].deferred
    assert not verdicts["DE-DOC-04"].deferred


def test_expiring_soon_is_not_deferred():
    values = _clean_values()
    values["insurance_certificate"]["valid_until"] = "2026-11-14"
    assert not _by_id(run_rules(_firm(values), "DE"))["DE-INS-04"].deferred
