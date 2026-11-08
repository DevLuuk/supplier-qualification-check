import re
from functools import partial

from supplier_check.lookups import (
    lookup_register,
    normalise_address,
    name_status,
    sanctions_status,
    screen_sanctions,
)
from supplier_check.models import DocType, Finding, FirmFile, Rule, RuleContext, Status
from supplier_check.rules import (
    Unsure,
    missing_document,
    document,
    need_date,
    need_int,
    need_text,
)

# assumed minimum, see brief
MIN_INSURED_EUR = 5_000_000
SAFETY_YEARS = 3
INSURANCE_RUNWAY_DAYS = 30
YEAR_RANGE = re.compile(r"(\d{4})\D+(\d{4})")
STATUS_ORDER: dict[Status, int] = {"pass": 0, "unsure": 1, "fail": 2}

REGISTER: DocType = "register_extract"
INSURANCE: DocType = "insurance_certificate"
ISO_9001: DocType = "iso_9001"
ISO_45001: DocType = "iso_45001"
SAFETY: DocType = "safety_record"
BANK: DocType = "bank_letter"

DOCUMENTS: list[tuple[str, DocType, str]] = [
    ("DE-DOC-01", REGISTER, "commercial register extract"),
    ("DE-DOC-02", INSURANCE, "liability insurance certificate"),
    ("DE-DOC-03", ISO_9001, "ISO 9001 certificate (quality management)"),
    ("DE-DOC-04", ISO_45001, "ISO 45001 certificate (health and safety)"),
    ("DE-DOC-05", SAFETY, "safety record for the last three years"),
    ("DE-DOC-06", BANK, "bank letter confirming the account"),
]

NAME_REASONS: dict[Status, str] = {
    "pass": "'{found}' matches the legal name.",
    "unsure": "'{found}' is not written exactly like the legal name '{legal}' "
    "(similarity {score:.2f}).",
    "fail": "'{found}' does not match the legal name '{legal}' (similarity {score:.2f}).",
}


def document_present(context: RuleContext, doc_type: DocType, label: str) -> Finding:
    doc = document(context.firm, doc_type)
    if doc is None and context.firm.unreadable:
        reasons = " ".join(f"{u.file}: {u.reason}." for u in context.firm.unreadable)
        return Finding(status="unsure", reason=f"No {label} found, but a file could not be read. {reasons}")
    if doc is None:
        return Finding(status="fail", reason=f"No {label} was received.")
    return Finding(status="pass", reason=f"Received {doc.file}.")


def name_matches(context: RuleContext, doc_type: DocType, field_name: str) -> Finding:
    legal, legal_field = need_text(context.firm, REGISTER, "legal_name")
    found, found_field = need_text(context.firm, doc_type, field_name)
    status, score = name_status(legal, found)
    reason = NAME_REASONS[status].format(found=found, legal=legal, score=score)
    return Finding(status=status, reason=reason, evidence=[legal_field.source, found_field.source])


def _name_or_unsure(context: RuleContext, doc_type: DocType, field_name: str) -> Finding:
    try:
        return name_matches(context, doc_type, field_name)
    except Unsure as unsure:
        label = doc_type.replace("_", " ").upper()
        reason = f"{label}: {unsure.reason.rstrip('.')}."
        return Finding(status="unsure", reason=reason, evidence=unsure.evidence)


def iso_holders_match(context: RuleContext) -> Finding:
    findings = [_name_or_unsure(context, doc, "holder_name") for doc in (ISO_9001, ISO_45001)]
    worst = max(findings, key=lambda finding: STATUS_ORDER[finding.status])
    evidence = [source for finding in findings for source in finding.evidence]
    return Finding(
        status=worst.status, reason=" ".join(f.reason for f in findings), evidence=evidence
    )


def insurance_valid(context: RuleContext) -> Finding:
    start, start_field = need_date(context.firm, INSURANCE, "valid_from")
    end, end_field = need_date(context.firm, INSURANCE, "valid_until")
    as_of = context.firm.as_of
    valid = start <= as_of <= end
    reason = f"Cover runs {start} to {end}; check date is {as_of}."
    evidence = [start_field.source, end_field.source]
    return Finding(status="pass" if valid else "fail", reason=reason, evidence=evidence)


def insured_amount_enough(context: RuleContext) -> Finding:
    amount, field = need_int(context.firm, INSURANCE, "insured_amount_eur")
    enough = amount >= MIN_INSURED_EUR
    reason = f"Insured amount is {amount:,} EUR; minimum is {MIN_INSURED_EUR:,} EUR."
    return Finding(status="pass" if enough else "fail", reason=reason, evidence=[field.source])


def certificate_valid(context: RuleContext, doc_type: DocType) -> Finding:
    end, field = need_date(context.firm, doc_type, "valid_until")
    valid = end >= context.firm.as_of
    reason = f"Valid until {end}; check date is {context.firm.as_of}."
    return Finding(status="pass" if valid else "fail", reason=reason, evidence=[field.source])


def no_fatalities(context: RuleContext) -> Finding:
    count, field = need_int(context.firm, SAFETY, "fatalities")
    reason = f"{count} fatal accidents reported."
    return Finding(status="pass" if count == 0 else "fail", reason=reason, evidence=[field.source])


def safety_period_covered(context: RuleContext) -> Finding:
    period, field = need_text(context.firm, SAFETY, "period")
    years = YEAR_RANGE.search(period)
    if years is None:
        raise Unsure(f"The period '{period}' is not a year range.", [field.source])
    first, last = int(years.group(1)), int(years.group(2))
    needed_first = context.firm.as_of.year - SAFETY_YEARS
    needed_last = context.firm.as_of.year - 1
    covered = first <= needed_first and last >= needed_last
    reason = f"Record covers {first} to {last}; needed {needed_first} to {needed_last}."
    return Finding(status="pass" if covered else "fail", reason=reason, evidence=[field.source])


def register_number_found(context: RuleContext) -> Finding:
    _, field = need_text(context.firm, REGISTER, "registration_number")
    result = context.lookups["mock_register"]
    status = "pass" if result.match else "fail"
    return Finding(status=status, reason=result.note, evidence=[field.source])


def register_name_matches(context: RuleContext) -> Finding:
    legal, field = need_text(context.firm, REGISTER, "legal_name")
    need_text(context.firm, REGISTER, "registration_number")
    result = context.lookups["mock_register"]
    if result.match is None:
        raise Unsure("The register number was not found, so the name cannot be compared.")
    status, score = name_status(legal, result.match)
    reason = f"{result.note} " + NAME_REASONS[status].format(found=result.match, legal=legal, score=score)
    return Finding(status=status, reason=reason, evidence=[field.source])


def no_sanctions_match(context: RuleContext) -> Finding:
    _, field = need_text(context.firm, REGISTER, "legal_name")
    result = context.lookups["mock_sanctions"]
    return Finding(status=sanctions_status(result), reason=result.note, evidence=[field.source])


def _readable_text(firm: FirmFile, doc_type: DocType, name: str) -> str | None:
    try:
        return need_text(firm, doc_type, name)[0]
    except Unsure:
        return None


def context(firm: FirmFile) -> RuleContext:
    lookups = {}
    number = _readable_text(firm, REGISTER, "registration_number")
    if number:
        lookups["mock_register"] = lookup_register(number)
    name = _readable_text(firm, REGISTER, "legal_name")
    if name:
        lookups["mock_sanctions"] = screen_sanctions(name)
    return RuleContext(firm=firm, lookups=lookups)


def insurance_runway(context: RuleContext) -> Finding:
    end, field = need_date(context.firm, INSURANCE, "valid_until")
    days_left = (end - context.firm.as_of).days
    if days_left < 0:
        raise Unsure(f"Already expired {-days_left} days ago, see DE-INS-01.", [field.source], deferred=True)
    if days_left >= INSURANCE_RUNWAY_DAYS:
        return Finding(status="pass", reason=f"Valid for {days_left} more days.", evidence=[field.source])
    return Finding(status="unsure", reason=f"valid today, expires in {days_left} days", evidence=[field.source])


def insured_address_matches(context: RuleContext) -> Finding:
    doc = document(context.firm, INSURANCE)
    if doc is None:
        raise missing_document()
    printed = doc.fields.get("insured_address")
    if printed is not None and printed.value is None and printed.note:
        raise Unsure(f"The insured address is unclear ({printed.note}).")
    if printed is None or printed.value is None:
        return Finding(status="pass", reason="certificate prints no address")
    insured, insured_field = need_text(context.firm, INSURANCE, "insured_address")
    registered, registered_field = need_text(context.firm, REGISTER, "registered_address")
    same = normalise_address(insured) == normalise_address(registered)
    reason = f"Certificate address '{insured}', register address '{registered}'."
    evidence = [insured_field.source, registered_field.source]
    return Finding(status="pass" if same else "unsure", reason=reason, evidence=evidence)


EXACT_NAME_ASK = "in your exact legal name as it appears in the commercial register"
NOT_CONFIRMED = "We could not confirm that"

RULES: list[Rule] = [
    *(
        Rule(
            rule_id=rule_id,
            requirement=f"The firm sent its {label}.",
            ask=f"a copy of your {label}",
            external=f"We did not receive a readable copy of your {label}.",
            check=partial(document_present, doc_type=doc_type, label=label),
        )
        for rule_id, doc_type, label in DOCUMENTS
    ),
    Rule(
        rule_id="DE-REG-01",
        requirement="The register number is in the company register.",
        ask="",
        internal_only=True,
        check=register_number_found,
    ),
    Rule(
        rule_id="DE-REG-02",
        requirement="The company register shows the same legal name.",
        ask="",
        internal_only=True,
        check=register_name_matches,
    ),
    Rule(
        rule_id="DE-INS-01",
        requirement="The liability insurance is valid on the check date.",
        ask="a liability insurance certificate that is valid today",
        external=f"{NOT_CONFIRMED} your liability insurance is valid today.",
        check=insurance_valid,
    ),
    Rule(
        rule_id="DE-INS-02",
        requirement=f"The insured amount is at least {MIN_INSURED_EUR:,} EUR.",
        ask=f"proof of liability cover of at least {MIN_INSURED_EUR:,} EUR",
        external=f"{NOT_CONFIRMED} your liability cover is at least {MIN_INSURED_EUR:,} EUR.",
        check=insured_amount_enough,
    ),
    Rule(
        rule_id="DE-INS-03",
        requirement="The insurance is in the firm's legal name.",
        ask=f"an insurance certificate {EXACT_NAME_ASK}",
        external=f"{NOT_CONFIRMED} your insurance certificate is in your exact legal name.",
        check=partial(name_matches, doc_type=INSURANCE, field_name="insured_name"),
    ),
    Rule(
        rule_id="DE-INS-04",
        requirement=f"The liability insurance is still valid in {INSURANCE_RUNWAY_DAYS} days.",
        ask="confirmation that your liability insurance has been renewed",
        external=f"{NOT_CONFIRMED} your liability insurance stays valid for the next {INSURANCE_RUNWAY_DAYS} days.",
        check=insurance_runway,
    ),
    Rule(
        rule_id="DE-INS-05",
        requirement="The insured address matches the register address.",
        ask="an insurance certificate showing your registered address, or an explanation of the other address",
        external=f"{NOT_CONFIRMED} the address on your insurance certificate is your registered address.",
        check=insured_address_matches,
    ),
    Rule(
        rule_id="DE-ISO-01",
        requirement="The ISO 9001 certificate is valid on the check date.",
        ask="a valid ISO 9001 certificate",
        external=f"{NOT_CONFIRMED} your ISO 9001 certificate is valid today.",
        check=partial(certificate_valid, doc_type=ISO_9001),
    ),
    Rule(
        rule_id="DE-ISO-02",
        requirement="The ISO 45001 certificate is valid on the check date.",
        ask="a valid ISO 45001 certificate",
        external=f"{NOT_CONFIRMED} your ISO 45001 certificate is valid today.",
        check=partial(certificate_valid, doc_type=ISO_45001),
    ),
    Rule(
        rule_id="DE-ISO-03",
        requirement="Both ISO certificates are in the firm's legal name.",
        ask=f"ISO certificates {EXACT_NAME_ASK}",
        external=f"{NOT_CONFIRMED} your ISO certificates are in your exact legal name.",
        check=iso_holders_match,
    ),
    Rule(
        rule_id="DE-SAF-01",
        requirement="No fatal accidents in the safety record.",
        ask="a written explanation of any fatal accidents in your safety record",
        external=f"{NOT_CONFIRMED} your safety record shows no fatal accidents.",
        check=no_fatalities,
    ),
    Rule(
        rule_id="DE-SAF-02",
        requirement=f"The safety record covers the last {SAFETY_YEARS} full years.",
        ask=f"a safety record covering the last {SAFETY_YEARS} full years",
        external=f"{NOT_CONFIRMED} your safety record covers the last {SAFETY_YEARS} full years.",
        check=safety_period_covered,
    ),
    Rule(
        rule_id="DE-SAN-01",
        requirement="The firm is not on the sanctions list.",
        ask="",
        internal_only=True,
        check=no_sanctions_match,
    ),
    Rule(
        rule_id="DE-BNK-01",
        requirement="The bank account is in the firm's legal name.",
        ask=f"a bank letter for an account {EXACT_NAME_ASK}",
        external=f"{NOT_CONFIRMED} the bank account is in your exact legal name.",
        check=partial(name_matches, doc_type=BANK, field_name="account_holder"),
    ),
]
