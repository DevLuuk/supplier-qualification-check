from datetime import date

import pytest

from supplier_check.extract import _to_field, value_supported

PAGE = "versicherungsende 15.10.2026 deckungssumme 10.000.000,00 eur"


def _raw(value: object, quote: str) -> dict:
    return {"value": value, "quote": quote, "page": 1, "confidence": "high"}


@pytest.mark.parametrize(
    ("value", "quote"),
    [
        (10_000_000, "Deckungssumme 10.000.000,00 EUR"),
        (5_000_000, "Deckungssumme EUR 5 Mio."),
        (2_500_000, "Deckungssumme 2,5 Mio. EUR"),
        (0, "There were no fatalities in the period."),
        (24, "Meldepflichtige Arbeitsunfälle gesamt 24"),
        (date(2026, 10, 15), "Versicherungsende 15.10.2026"),
        (date(2028, 3, 14), "Valid until 14 March 2028"),
        ("DE31600903000045128873", "IBAN DE31 6009 0300 0045 1288 73"),
        ("2023-2025", "Berichtszeitraum 2023 bis 2025"),
        ("GmbH", "Rechtsform Gesellschaft mit beschränkter Haftung (GmbH)"),
        ("Weber Stahlbau GmbH", "Versicherungsnehmer Weber  Stahlbau GmbH"),
    ],
)
def test_value_backed_by_quote(value, quote):
    assert value_supported(value, quote)


@pytest.mark.parametrize(
    ("value", "quote"),
    [
        (10_000_000, "Deckungssumme 1.000.000,00 EUR"),
        (date(2026, 10, 16), "Versicherungsende 15.10.2026"),
        ("Weber Stahlbau Handels GmbH", "Versicherungsnehmer Weber Stahlbau GmbH"),
        (3, "Tödliche Arbeitsunfälle gesamt 0"),
    ],
)
def test_value_not_in_quote(value, quote):
    assert not value_supported(value, quote)


def test_made_up_amount_gets_low_confidence():
    field = _to_field(_raw(1_000_000, "Deckungssumme 10.000.000,00 EUR"), "insurance.pdf", PAGE)
    assert field.confidence == "low"


def test_matching_amount_keeps_high_confidence():
    field = _to_field(_raw(10_000_000, "Deckungssumme 10.000.000,00 EUR"), "insurance.pdf", PAGE)
    assert field.confidence == "high"


def test_quote_not_on_page_gets_low_confidence():
    field = _to_field(_raw(date(2026, 10, 15), "Versicherungsende 15.10.2026 ok"), "insurance.pdf", PAGE)
    assert field.confidence == "low"


def test_page_image_is_never_trusted():
    field = _to_field(_raw(10_000_000, "Deckungssumme 10.000.000,00 EUR"), "insurance.pdf", None)
    assert field.confidence == "low"
    assert field.source.kind == "page_image"
