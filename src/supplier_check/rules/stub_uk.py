from functools import partial

from supplier_check.models import FirmFile, Rule, RuleContext
from supplier_check.rules.germany import (
    INSURANCE,
    REGISTER,
    document_present,
    insurance_valid,
    name_matches,
)

RULES: list[Rule] = [
    Rule(
        rule_id="UK-DOC-01",
        requirement="The firm sent a Companies House extract.",
        ask="a current Companies House extract",
        external="We did not receive a readable Companies House extract.",
        check=partial(document_present, doc_type=REGISTER, label="Companies House extract"),
    ),
    Rule(
        rule_id="UK-INS-01",
        requirement="The public liability insurance is valid on the check date.",
        ask="a public liability insurance certificate that is valid today",
        external="We could not confirm that your public liability insurance is valid today.",
        check=insurance_valid,
    ),
    Rule(
        rule_id="UK-INS-02",
        requirement="The insurance is in the firm's registered name.",
        ask="an insurance certificate in your registered name at Companies House",
        external="We could not confirm that your insurance is in your registered name.",
        check=partial(name_matches, doc_type=INSURANCE, field_name="insured_name"),
    ),
]


def context(firm: FirmFile) -> RuleContext:
    return RuleContext(firm=firm)
