from supplier_check.email_draft import NOTHING_FOR_FIRM, NOTHING_TO_ASK, draft_email, officer_note
from supplier_check.models import Source, Verdict
from supplier_check.rules import rule_book

RULES = rule_book("DE")
SCREENING_NOTE = "MOCK: closest sanctions entry is Nordhaus Bau Trading FZE (score 1.00)"


def _verdict(rule_id: str, status: str, reason: str, deferred: bool = False) -> Verdict:
    evidence = [Source(file="register_extract.pdf", page=1, quote="Firma Nordhaus Bau GmbH")]
    return Verdict(
        rule_id=rule_id, requirement="", status=status, reason=reason, evidence=evidence, deferred=deferred
    )


NORDHAUS = [
    _verdict("DE-SAN-01", "unsure", SCREENING_NOTE),
    _verdict("DE-REG-02", "fail", "MOCK: Amtsgericht Bremen lists HRB 118204 as Weserland Tiefbau GmbH"),
    _verdict("DE-INS-04", "unsure", "valid today, expires in 5 days"),
]


def test_email_text_says_nothing_about_screening():
    email = draft_email("Nordhaus Bau GmbH", NORDHAUS, RULES)
    for leaked in ("MOCK", "Trading FZE", "Weserland", "sanction", "screening", "internal", "compliance"):
        assert leaked.casefold() not in email.casefold()
    assert "stays valid for the next 30 days" in email


def test_officer_note_is_separate():
    assert officer_note(NORDHAUS, RULES) == "internal: 2 screening findings not included, route to compliance"


def test_only_screening_finding_gives_no_firm_email_but_a_note():
    verdicts = [_verdict("DE-SAN-01", "unsure", SCREENING_NOTE)]
    assert draft_email("Nordhaus Bau GmbH", verdicts, RULES) == NOTHING_FOR_FIRM
    assert officer_note(verdicts, RULES) == "internal: 1 screening finding not included, route to compliance"


def test_deferred_flag_skips_line_whatever_the_reason_says():
    verdicts = [
        _verdict("DE-INS-01", "fail", "Cover ended."),
        _verdict("DE-INS-04", "unsure", "any wording at all", deferred=True),
    ]
    email = draft_email("Weber Stahlbau GmbH", verdicts, RULES)
    assert "valid today" in email
    assert "next 30 days" not in email


def test_reason_text_alone_does_not_defer():
    verdicts = [_verdict("DE-ISO-02", "unsure", "document missing")]
    assert "ISO 45001 certificate is valid today" in draft_email("Firm", verdicts, RULES)


def test_firm_lines_use_external_message_not_internal_reason():
    verdicts = [_verdict("DE-INS-02", "fail", "Insured amount is 3,000,000 EUR (internal detail).")]
    email = draft_email("Müller Gerüstbau GmbH", verdicts, RULES)
    assert "internal detail" not in email
    assert "We could not confirm that your liability cover is at least 5,000,000 EUR." in email


def test_all_pass_needs_no_email_and_no_note():
    verdicts = [_verdict("DE-INS-01", "pass", "ok")]
    assert draft_email("Hansen", verdicts, RULES) == NOTHING_TO_ASK
    assert officer_note(verdicts, RULES) == ""
