from supplier_check.llm import complete
from supplier_check.models import Classification

PROMPT = """You sort documents that a construction subcontractor sent for onboarding.
Say which type this document is. A cover letter may come first; judge by the main document.
- register_extract: commercial register extract (Handelsregisterauszug)
- insurance_certificate: liability insurance confirmation (Versicherungsbestaetigung)
- iso_9001: ISO 9001 quality management certificate
- iso_45001: ISO 45001 occupational health and safety certificate
- safety_record: accident statistics or safety record (Unfallstatistik)
- bank_letter: bank confirmation of account details (Bankbestaetigung)
- other: anything else"""


def classify(pages: list[str], images: list[bytes] | None = None) -> Classification:
    return complete(PROMPT, Classification, pages, "fast", images)
