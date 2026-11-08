from datetime import date
from importlib import import_module
from types import ModuleType

from supplier_check.models import (
    DocType,
    ExtractedDocument,
    Field,
    FirmFile,
    LookupResult,
    Rule,
    RuleContext,
    Source,
    Verdict,
)

COUNTRY_MODULES = {"DE": "germany", "UK": "stub_uk"}
DOCUMENT_MISSING = "document missing"
COVERED_ELSEWHERE = "covered by another rule"


class Unsure(Exception):
    def __init__(self, reason: str, evidence: list[Source] | None = None):
        super().__init__(reason)
        self.reason = reason
        self.evidence = evidence or []


def document(firm: FirmFile, doc_type: DocType) -> ExtractedDocument | None:
    return next((doc for doc in firm.documents if doc.doc_type == doc_type), None)


def need(firm: FirmFile, doc_type: DocType, name: str) -> Field:
    doc = document(firm, doc_type)
    if doc is None:
        raise Unsure(DOCUMENT_MISSING)
    field = doc.fields.get(name)
    label = f"{name.replace('_', ' ')} on the {doc_type.replace('_', ' ')}"
    if field is None or field.value is None:
        raise Unsure(f"No {label} was found.")
    if field.source is None:
        raise Unsure(f"The {label} has no quote to prove it.")
    if field.confidence == "low":
        raise Unsure(f"The {label} could not be read with confidence.", [field.source])
    return field


def need_date(firm: FirmFile, doc_type: DocType, name: str) -> tuple[date, Field]:
    field = need(firm, doc_type, name)
    if not isinstance(field.value, date):
        raise Unsure(f"'{field.value}' is not a date.", [field.source])
    return field.value, field


def need_int(firm: FirmFile, doc_type: DocType, name: str) -> tuple[int, Field]:
    field = need(firm, doc_type, name)
    if not isinstance(field.value, int):
        raise Unsure(f"'{field.value}' is not a whole number.", [field.source])
    return field.value, field


def need_text(firm: FirmFile, doc_type: DocType, name: str) -> tuple[str, Field]:
    field = need(firm, doc_type, name)
    return str(field.value), field


def evaluate(rules: list[Rule], context: RuleContext) -> list[Verdict]:
    verdicts = []
    for rule in rules:
        try:
            finding = rule.check(context)
            status, reason, evidence = finding.status, finding.reason, finding.evidence
        except Unsure as unsure:
            status, reason, evidence = "unsure", unsure.reason, unsure.evidence
        verdicts.append(
            Verdict(
                rule_id=rule.rule_id,
                requirement=rule.requirement,
                status=status,
                reason=reason,
                evidence=evidence,
            )
        )
    return verdicts


def _rule_set(country: str) -> ModuleType:
    if country not in COUNTRY_MODULES:
        raise ValueError(f"No rule set for country '{country}'.")
    return import_module(f"{__name__}.{COUNTRY_MODULES[country]}")


def run_rules(firm_file: FirmFile, country: str) -> list[Verdict]:
    rule_set = _rule_set(country)
    return evaluate(rule_set.RULES, rule_set.context(firm_file))


def run_lookups(firm_file: FirmFile, country: str) -> list[LookupResult]:
    return list(_rule_set(country).context(firm_file).lookups.values())


def rule_book(country: str) -> dict[str, Rule]:
    return {rule.rule_id: rule for rule in _rule_set(country).RULES}
