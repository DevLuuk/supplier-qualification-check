from supplier_check.models import Rule, Verdict
from supplier_check.rules import COVERED_ELSEWHERE, DOCUMENT_MISSING

GREETING = "Sehr geehrte Damen und Herren,"
SIGN_OFF = "Kind regards,\nSupplier onboarding, NIG"
NOTHING_TO_ASK = "No email needed: every check passed."
NOTHING_FOR_FIRM = "No email needed for the firm."
OFFICER_DIVIDER = "----- for the officer, remove before sending -----"


def _lines(verdicts: list[Verdict], rules: dict[str, Rule]) -> list[str]:
    seen: set[str] = set()
    lines = []
    for verdict in verdicts:
        rule = rules[verdict.rule_id]
        deferred = verdict.reason == DOCUMENT_MISSING or COVERED_ELSEWHERE in verdict.reason
        skip = verdict.status == "pass" or rule.internal_only or deferred
        if skip or rule.ask in seen:
            continue
        seen.add(rule.ask)
        lines.append(f"- {rule.external} Please send {rule.ask}.")
    return lines


def _officer_note(verdicts: list[Verdict], rules: dict[str, Rule]) -> str:
    count = sum(v.status != "pass" and rules[v.rule_id].internal_only for v in verdicts)
    if not count:
        return ""
    noun = "finding" if count == 1 else "findings"
    return f"\n\n{OFFICER_DIVIDER}\ninternal: {count} screening {noun} not included, route to compliance"


def draft_email(firm_name: str, verdicts: list[Verdict], rules: dict[str, Rule]) -> str:
    lines = _lines(verdicts, rules)
    note = _officer_note(verdicts, rules)
    if not lines:
        return (NOTHING_FOR_FIRM + note) if note else NOTHING_TO_ASK
    body = "\n".join(lines)
    return (
        f"{GREETING}\n\n"
        f"thank you for the documents for {firm_name}. "
        "We checked them and need the following before we can approve you as a subcontractor:\n\n"
        f"{body}\n\n"
        "Please reply to this email with the documents.\n\n"
        f"{SIGN_OFF}{note}"
    )
