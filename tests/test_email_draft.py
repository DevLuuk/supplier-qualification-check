from supplier_check.email_draft import NOTHING_TO_ASK, draft_email
from supplier_check.models import Source, Verdict
from supplier_check.rules import rule_book

RULES = rule_book("DE")
SCREENING_NOTE = "MOCK: closest sanctions entry is Nordhaus Bau Trading FZE (score 1.00)"


def _verdict(rule_id: str, status: str, reason: str) -> Verdict:
    evidence = [Source(file="register_extract.pdf", page=1, quote="Firma Nordhaus Bau GmbH")]
    return Verdict(rule_id=rule_id, requirement="", status=status, reason=reason, evidence=evidence)


def test_screening_findings_never_reach_the_firm():
    verdicts = [
        _verdict("DE-SAN-01", "unsure", SCREENING_NOTE),
        _verdict("DE-REG-02", "fail", "MOCK: Amtsgericht Bremen lists HRB 118204 as Weserland Tiefbau GmbH"),
        _verdict("DE-INS-04", "unsure", "valid today, expires in 5 days"),
    ]
    email = draft_email("Nordhaus Bau GmbH", verdicts, RULES)
    firm_part, officer_part = email.split("----- for the officer")
    assert "MOCK" not in firm_part
    assert "Trading FZE" not in firm_part and "Weserland" not in firm_part
    assert "sanction" not in firm_part.casefold() and "register" not in firm_part.casefold()
    assert "stays valid for the next 30 days" in firm_part
    assert "internal: 2 screening findings not included, route to compliance" in officer_part


def test_only_screening_finding_gives_officer_note_without_firm_email():
    email = draft_email("Nordhaus Bau GmbH", [_verdict("DE-SAN-01", "unsure", SCREENING_NOTE)], RULES)
    assert email.startswith("No email needed for the firm.")
    assert "internal: 1 screening finding not included, route to compliance" in email
    assert "Trading FZE" not in email


def test_firm_lines_use_external_message_not_internal_reason():
    verdicts = [_verdict("DE-INS-02", "fail", "Insured amount is 3,000,000 EUR (internal detail).")]
    email = draft_email("Müller Gerüstbau GmbH", verdicts, RULES)
    assert "internal detail" not in email
    assert "We could not confirm that your liability cover is at least 5,000,000 EUR." in email


def test_all_pass_needs_no_email():
    assert draft_email("Hansen", [_verdict("DE-INS-01", "pass", "ok")], RULES) == NOTHING_TO_ASK
