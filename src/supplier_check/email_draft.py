from supplier_check.models import Verdict
from supplier_check.rules import DOCUMENT_MISSING

GREETING = "Sehr geehrte Damen und Herren,"
SIGN_OFF = "Kind regards,\nSupplier onboarding, NIG"
NOTHING_TO_ASK = "No email needed: every check passed."


def _lines(verdicts: list[Verdict], requests: dict[str, str]) -> list[str]:
    seen: set[str] = set()
    lines = []
    for verdict in verdicts:
        ask = requests[verdict.rule_id]
        if verdict.status == "pass" or verdict.reason == DOCUMENT_MISSING or ask in seen:
            continue
        seen.add(ask)
        lines.append(f"- {verdict.reason} Please send {ask}.")
    return lines


def draft_email(firm_name: str, verdicts: list[Verdict], requests: dict[str, str]) -> str:
    lines = _lines(verdicts, requests)
    if not lines:
        return NOTHING_TO_ASK
    body = "\n".join(lines)
    return (
        f"{GREETING}\n\n"
        f"thank you for the documents for {firm_name}. "
        "We checked them and need the following before we can approve you as a subcontractor:\n\n"
        f"{body}\n\n"
        "Please reply to this email with the documents.\n\n"
        f"{SIGN_OFF}"
    )
