from supplier_check.models import Rule, Verdict

GREETING = "Sehr geehrte Damen und Herren,"
SIGN_OFF = "Kind regards,\nSupplier onboarding, NIG"
NOTHING_TO_ASK = "No email needed: every check passed."
NOTHING_FOR_FIRM = "No email needed for the firm."


def _lines(verdicts: list[Verdict], rules: dict[str, Rule]) -> list[str]:
    seen: set[str] = set()
    lines = []
    for verdict in verdicts:
        rule = rules[verdict.rule_id]
        if verdict.status == "pass" or verdict.deferred or rule.internal_only or rule.ask in seen:
            continue
        seen.add(rule.ask)
        lines.append(f"- {rule.external} Please send {rule.ask}.")
    return lines


def officer_note(verdicts: list[Verdict], rules: dict[str, Rule]) -> str:
    count = sum(v.status != "pass" and rules[v.rule_id].internal_only for v in verdicts)
    if not count:
        return ""
    noun = "finding" if count == 1 else "findings"
    return f"internal: {count} screening {noun} not included, route to compliance"


def draft_email(firm_name: str, verdicts: list[Verdict], rules: dict[str, Rule]) -> str:
    lines = _lines(verdicts, rules)
    if not lines:
        all_pass = all(verdict.status == "pass" for verdict in verdicts)
        return NOTHING_TO_ASK if all_pass else NOTHING_FOR_FIRM
    body = "\n".join(lines)
    return (
        f"{GREETING}\n\n"
        f"thank you for the documents for {firm_name}. "
        "We checked them and need the following before we can approve you as a subcontractor:\n\n"
        f"{body}\n\n"
        "Please reply to this email with the documents.\n\n"
        f"{SIGN_OFF}"
    )
