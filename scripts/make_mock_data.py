"""Generate mock supplier documents, answer keys and lookup lists.

Everything here is fictional and mock. Output is deterministic.
Run: uv run python scripts/make_mock_data.py
"""

from __future__ import annotations

import json
import re
import sys
import zlib
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm, mm
from PIL import Image, ImageDraw, ImageFont
import reportlab
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.platypus import (
    HRFlowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
FIRMS_DIR = DATA_DIR / "firms"
AS_OF = date(2026, 11, 9)
COUNTRY = "DE"
CURRENCY = "EUR"
IBAN_COUNTRY_DIGITS = "131400"
IBAN_MOD = 97
IBAN_CHECK_BASE = 98
IBAN_GROUP = 4
SCAN_WIDTH = 1240
SCAN_HEIGHT = 1754
SCAN_MARGIN = 130
SCAN_LABEL_WIDTH = 420
SCAN_ROW_HEIGHT = 62
SCAN_TEXT_SIZE = 28
SCAN_HEAD_SIZE = 40
SCAN_SMALL_SIZE = 22
SCAN_INK = 35
SCAN_RULE = 120
SCAN_PAPER = 248
SCAN_SKEW_DEGREES = 0.6
REF_MODULO = 90000
REF_OFFSET = 10000
PAGE_MARGIN = 2.2 * cm
LABEL_COL_WIDTH = 5.6 * cm
FOOTER_Y = 1.2 * cm
FOOTER_FONT_SIZE = 7
BODY_FONT_SIZE = 10
LEADING = 14
MOCK_NOTE_DE = "Fiktives Beispieldokument (MOCK) für einen Prototyp. Keine echte Urkunde."
MOCK_NOTE_EN = "Fictional sample document (MOCK) for a prototype. Not a real certificate."
MOCK_NOTE_EN_RECORD = "Fictional sample document (MOCK) for a prototype. Not a real record."
MONTHS_EN = (
    "January February March April May June July August September October November December"
).split()

DOC_FILES = {
    "register_extract": "register_extract.pdf",
    "insurance_certificate": "insurance_certificate.pdf",
    "iso_9001": "iso_9001.pdf",
    "iso_45001": "iso_45001.pdf",
    "safety_record": "safety_record.pdf",
    "bank_letter": "bank_letter.pdf",
}
DOC_LANGUAGE = {name: "de" for name in DOC_FILES} | {"iso_9001": "en", "iso_45001": "en"}


@dataclass(frozen=True)
class Field:
    value: object
    printed: str
    label: str | None = None


@dataclass(frozen=True)
class Party:
    name: str
    street: str
    city_line: str


@dataclass(frozen=True)
class Style:
    font: str
    bold: str
    accent: str
    header: str  # rule | band | right
    grid: str  # lines | box | zebra


@dataclass(frozen=True)
class Insurance:
    party: Party
    policy: str
    insured_name: str
    amount: int
    valid_from: date
    valid_until: date
    amount_printed: str | None = None
    insured_address: str | None = None
    scanned: bool = False


@dataclass(frozen=True)
class Cert:
    party: Party
    number: str
    holder: str
    scope: str
    valid_until: date
    issued: date | None = None
    initial: date | None = None
    cover_letter: bool = False


@dataclass(frozen=True)
class Safety:
    firm_name: str
    years: tuple[tuple[int, int, int], ...]  # year, accidents, lost-time injuries
    signer: str
    narrative: bool = False


@dataclass(frozen=True)
class Bank:
    party: Party
    holder: str
    bank_code: str
    account: str
    letter_date: date


@dataclass(frozen=True)
class Firm:
    slug: str
    legal_name: str
    trade: str
    street: str
    zip_city: str
    court: str
    hrb: str
    director: str
    extract_date: date
    variant: int
    style: Style
    insurance: Insurance
    iso_9001: Cert
    iso_45001: Cert | None
    safety: Safety
    bank: Bank
    issues: tuple[str, ...]
    registry_hrb: str = ""


@dataclass
class Doc:
    key: str
    story: list
    fields: dict[str, Field]
    issuer: Party
    note: str
    title: str
    language: str = ""
    scan: Image.Image | None = None
    doc_extra: dict = field(default_factory=dict)
    field_extra: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Page:
    issuer: Party
    title: str
    ref: str
    body: str
    rows: list[tuple[str, str]]
    signer: tuple[str, str]
    subtitle: str = ""
    lead_in: str = ""


# ---------------------------------------------------------------- formatting


def de_date(d: date) -> str:
    return d.strftime("%d.%m.%Y")


def en_date(d: date) -> str:
    return f"{d.day} {MONTHS_EN[d.month - 1]} {d.year}"


def de_amount(amount: int) -> str:
    return f"{amount:,}".replace(",", ".") + f",00 {CURRENCY}"


def date_field(d: date, printer) -> Field:
    return Field(d.isoformat(), printer(d))


def text_field(text: str) -> Field:
    return Field(text, text)


def int_field(number: int, label: str) -> Field:
    return Field(number, str(number), label)


def make_iban(bank_code: str, account: str) -> str:
    bban = bank_code + account
    check = IBAN_CHECK_BASE - int(bban + IBAN_COUNTRY_DIGITS) % IBAN_MOD
    return f"{COUNTRY}{check:02d}{bban}"


def group_iban(iban: str) -> str:
    return " ".join(iban[i : i + IBAN_GROUP] for i in range(0, len(iban), IBAN_GROUP))


def reference(prefix: str, slug: str, doc: str) -> str:
    return f"{prefix}-{zlib.crc32((slug + doc).encode()) % REF_MODULO + REF_OFFSET}"


# ---------------------------------------------------------------- layout


def make_styles(st: Style) -> dict[str, ParagraphStyle]:
    base = ParagraphStyle("base", fontName=st.font, fontSize=BODY_FONT_SIZE, leading=LEADING)
    head_align = {"rule": TA_LEFT, "band": TA_CENTER, "right": TA_RIGHT}[st.header]
    accent = colors.HexColor(st.accent)
    return {
        "body": base,
        "small": ParagraphStyle("small", parent=base, fontSize=8, leading=10, alignment=head_align),
        "issuer": ParagraphStyle(
            "issuer", parent=base, fontName=st.bold, fontSize=15, leading=18,
            textColor=accent, alignment=head_align,
        ),
        "band": ParagraphStyle(
            "band", parent=base, fontName=st.bold, fontSize=15, leading=20,
            textColor=colors.white, alignment=TA_CENTER,
        ),
        "title": ParagraphStyle(
            "title", parent=base, fontName=st.bold, fontSize=17, leading=22,
            spaceBefore=14, spaceAfter=4,
        ),
        "subtitle": ParagraphStyle("subtitle", parent=base, fontSize=11, textColor=colors.grey),
        "label": ParagraphStyle("label", parent=base, fontName=st.bold),
        "ref": ParagraphStyle("ref", parent=base, fontSize=8, textColor=colors.grey),
    }


def letterhead(issuer: Party, st: Style, styles: dict) -> list:
    accent = colors.HexColor(st.accent)
    address = f"{escape(issuer.street)} | {escape(issuer.city_line)}"
    if st.header == "band":
        band = Table([[Paragraph(escape(issuer.name), styles["band"])]], colWidths=[None])
        band.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), accent),
                                  ("TOPPADDING", (0, 0), (-1, -1), 8),
                                  ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
        return [band, Spacer(1, 4), Paragraph(address, styles["small"])]
    return [
        Paragraph(escape(issuer.name), styles["issuer"]),
        Paragraph(address, styles["small"]),
        Spacer(1, 4),
        HRFlowable(width="100%", thickness=1.5, color=accent),
    ]


def info_table(rows: list[tuple[str, str]], st: Style, styles: dict) -> Table:
    cells = [[Paragraph(escape(k), styles["label"]), Paragraph(escape(v), styles["body"])]
             for k, v in rows]
    table = Table(cells, colWidths=[LABEL_COL_WIDTH, None], hAlign="LEFT")
    commands = [("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]
    commands += GRID_COMMANDS[st.grid](len(rows))
    table.setStyle(TableStyle(commands))
    return table


def _lines(_: int) -> list:
    return [("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.lightgrey)]


def _box(_: int) -> list:
    return [("GRID", (0, 0), (-1, -1), 0.5, colors.grey), ("BOX", (0, 0), (-1, -1), 1, colors.black)]


def _zebra(count: int) -> list:
    return [("ROWBACKGROUNDS", (0, 0), (-1, count - 1), [colors.whitesmoke, colors.white])]


GRID_COMMANDS = {"lines": _lines, "box": _box, "zebra": _zebra}


def signature_block(signer: tuple[str, str], styles: dict) -> list:
    name, role = signer
    return [
        Spacer(1, 40),
        HRFlowable(width=6 * cm, thickness=0.6, color=colors.black, hAlign="LEFT"),
        Paragraph(escape(name), styles["label"]),
        Paragraph(escape(role), styles["body"]),
    ]


def assemble(page: Page, st: Style) -> list:
    styles = make_styles(st)
    story = letterhead(page.issuer, st, styles)
    story += [Paragraph(escape(page.title), styles["title"])]
    if page.subtitle:
        story.append(Paragraph(escape(page.subtitle), styles["subtitle"]))
    story += [Spacer(1, 6), Paragraph(escape(page.ref), styles["ref"]), Spacer(1, 10)]
    story += [Paragraph(escape(page.body), styles["body"]), Spacer(1, 12)]
    story += [info_table(page.rows, st, styles)]
    return story + signature_block(page.signer, styles)


def assemble_letter(page: Page, paragraphs: list[str], st: Style) -> list:
    styles = make_styles(st)
    story = letterhead(page.issuer, st, styles)
    story += [Paragraph(escape(page.title), styles["title"]), Spacer(1, 4)]
    story += [Paragraph(escape(page.ref), styles["ref"]), Spacer(1, 12)]
    for text in paragraphs:
        story += [Paragraph(escape(text), styles["body"]), Spacer(1, 10)]
    return story + signature_block(page.signer, styles)


def scan_font(bold: bool, size: int) -> ImageFont.FreeTypeFont:
    name = "VeraBd.ttf" if bold else "Vera.ttf"
    return ImageFont.truetype(str(Path(reportlab.__file__).parent / "fonts" / name), size)


def wrap_words(draw: ImageDraw.ImageDraw, text: str, font, width: int) -> list[str]:
    lines, current = [], ""
    for word in text.split():
        trial = f"{current} {word}".strip()
        if current and draw.textlength(trial, font=font) > width:
            lines.append(current)
            current = word
        else:
            current = trial
    return lines + [current]


def draw_scan_rows(draw: ImageDraw.ImageDraw, page: Page, top: int) -> int:
    label_font, value_font = scan_font(True, SCAN_TEXT_SIZE), scan_font(False, SCAN_TEXT_SIZE)
    y = top
    for label, value in page.rows:
        draw.text((SCAN_MARGIN, y), label, font=label_font, fill=SCAN_INK)
        draw.text((SCAN_MARGIN + SCAN_LABEL_WIDTH, y), value, font=value_font, fill=SCAN_INK)
        y += SCAN_ROW_HEIGHT
        draw.line([(SCAN_MARGIN, y - 14), (SCAN_WIDTH - SCAN_MARGIN, y - 14)], fill=SCAN_RULE, width=2)
    return y


def render_scan(page: Page, st: Style, note: str) -> Image.Image:
    img = Image.new("L", (SCAN_WIDTH, SCAN_HEIGHT), SCAN_PAPER)
    draw = ImageDraw.Draw(img)
    head, small = scan_font(True, SCAN_HEAD_SIZE), scan_font(False, SCAN_SMALL_SIZE)
    draw.text((SCAN_MARGIN, SCAN_MARGIN), page.issuer.name, font=head, fill=SCAN_INK)
    address = f"{page.issuer.street} | {page.issuer.city_line}"
    draw.text((SCAN_MARGIN, SCAN_MARGIN + 60), address, font=small, fill=SCAN_INK)
    draw.line([(SCAN_MARGIN, SCAN_MARGIN + 90), (SCAN_WIDTH - SCAN_MARGIN, SCAN_MARGIN + 90)],
              fill=SCAN_INK, width=4)
    draw.text((SCAN_MARGIN, 330), page.title, font=head, fill=SCAN_INK)
    draw.text((SCAN_MARGIN, 395), page.ref, font=small, fill=SCAN_RULE)
    body_font, y = scan_font(False, SCAN_TEXT_SIZE), 470
    for line in wrap_words(draw, page.body, body_font, SCAN_WIDTH - 2 * SCAN_MARGIN):
        draw.text((SCAN_MARGIN, y), line, font=body_font, fill=SCAN_INK)
        y += SCAN_TEXT_SIZE + 12
    y = draw_scan_rows(draw, page, y + 50)
    draw.line([(SCAN_MARGIN, y + 160), (SCAN_MARGIN + 500, y + 160)], fill=SCAN_INK, width=3)
    draw.text((SCAN_MARGIN, y + 175), page.signer[0], font=body_font, fill=SCAN_INK)
    draw.text((SCAN_MARGIN, SCAN_HEIGHT - 150), note, font=small, fill=SCAN_RULE)
    return img.rotate(SCAN_SKEW_DEGREES, fillcolor=SCAN_PAPER, resample=Image.BICUBIC)


def write_scan_pdf(path: Path, doc: Doc) -> None:
    canvas = pdf_canvas.Canvas(str(path), pagesize=A4, invariant=1)
    canvas.setTitle(doc.title)
    canvas.drawImage(ImageReader(doc.scan), 0, 0, width=A4[0], height=A4[1])
    canvas.showPage()
    canvas.save()


def write_pdf(path: Path, doc: Doc, st: Style) -> None:
    if doc.scan is not None:
        write_scan_pdf(path, doc)
        return
    def footer(canvas, pdf):
        canvas.saveState()
        canvas.setFont(st.font, FOOTER_FONT_SIZE)
        canvas.setFillColor(colors.grey)
        canvas.drawString(PAGE_MARGIN, FOOTER_Y + 10, doc.note)
        line = f"{doc.issuer.name} | {doc.issuer.street} | {doc.issuer.city_line}"
        canvas.drawString(PAGE_MARGIN, FOOTER_Y, line)
        canvas.drawRightString(A4[0] - PAGE_MARGIN, FOOTER_Y, f"{pdf.page}")
        canvas.restoreState()

    template = SimpleDocTemplate(
        str(path), pagesize=A4, leftMargin=PAGE_MARGIN, rightMargin=PAGE_MARGIN,
        topMargin=PAGE_MARGIN, bottomMargin=2.4 * cm, invariant=1,
        title=doc.title, author=doc.issuer.name,
    )
    template.build(doc.story, onFirstPage=footer, onLaterPages=footer)


# ---------------------------------------------------------------- wording (varies per firm)

BODY_TEXT = {
    "register_extract": (
        "Hiermit wird ein aktueller Auszug aus dem Handelsregister, Abteilung B, für das "
        "nachstehend bezeichnete Unternehmen erteilt.",
        "Der folgende Registerauszug gibt den Eintragungsstand des Unternehmens zum Zeitpunkt "
        "des Abrufs wieder.",
        "Auf Antrag des Unternehmens wird nachstehender Auszug aus dem Handelsregister B "
        "erteilt. Maßgeblich ist der Stand der Eintragung am Tag des Abrufs.",
    ),
    "insurance_certificate": (
        "Wir bestätigen, dass für den nachstehend genannten Versicherungsnehmer bei uns eine "
        "Haftpflichtversicherung für den Betrieb besteht. Die Versicherung wird für die "
        "Vorlage bei Auftraggebern ausgestellt.",
        "Hiermit bescheinigen wir, dass der unten aufgeführte Betrieb bei uns haftpflichtversichert "
        "ist. Die Versicherung ist nicht gekündigt, die Prämien sind bezahlt.",
        "Gern bestätigen wir Ihnen den Bestand des folgenden Versicherungsschutzes. Die Angaben "
        "entsprechen dem Versicherungsschein.",
    ),
    "iso_9001": (
        "This is to certify that the quality management system of the organisation named below "
        "has been assessed and found to conform to the standard shown.",
        "The certification body confirms that the organisation below operates a management "
        "system that meets the requirements of the standard stated in this certificate.",
        "Following an independent audit, the management system of the holder named below is "
        "certified against the standard listed. This certificate remains subject to annual "
        "surveillance audits.",
    ),
    "iso_45001": (
        "This is to certify that the occupational health and safety management system of the "
        "organisation named below has been assessed and found to conform to the standard shown.",
        "The certification body confirms that the organisation below operates an occupational "
        "health and safety system that meets the requirements of the standard stated here.",
        "Following an independent audit, the health and safety management system of the holder "
        "named below is certified against the standard listed. Annual surveillance audits apply.",
    ),
    "safety_record": (
        "Nachstehend die Unfallstatistik unseres Unternehmens für den angegebenen Zeitraum. Die "
        "Angaben beruhen auf den Unfallanzeigen an die Berufsgenossenschaft.",
        "Wir legen die Arbeitsunfallstatistik für den genannten Berichtszeitraum vor. Erfasst "
        "sind alle meldepflichtigen Ereignisse.",
        "Für die Prüfung durch den Auftraggeber stellen wir die Unfallzahlen der letzten drei "
        "Jahre zusammen.",
    ),
    "bank_letter": (
        "Wir bestätigen hiermit, dass das nachstehend genannte Konto bei uns geführt wird und "
        "der Kontoinhaber bei uns in ordnungsgemäßer Geschäftsverbindung steht.",
        "Auf Wunsch unseres Kunden bestätigen wir die folgende Bankverbindung. Die Bestätigung "
        "erfolgt ohne Obligo für die Bank.",
        "Hiermit bestätigen wir die Richtigkeit der unten genannten Kontoverbindung für "
        "Zahlungen an unseren Kunden.",
    ),
}
LEGAL_FORM_PRINTED = "Gesellschaft mit beschränkter Haftung (GmbH)"
ISO_TITLE ="Certificate of Registration"
CERT_SIGNERS = ("Head of Certification", "Lead Auditor", "Managing Director")
DE_SIGNERS = ("Prokuristin", "Sachbearbeiter Firmenkunden", "Leiterin Kundenservice")


# ---------------------------------------------------------------- document builders


def build_register(firm: Firm) -> Doc:
    court = Party(firm.court, "Handelsregister", firm.zip_city)
    fields = {
        "legal_name": text_field(firm.legal_name),
        "registration_number": text_field(firm.hrb),
        "register_court": text_field(firm.court),
        "legal_form": Field("GmbH", LEGAL_FORM_PRINTED),
        "registered_address": text_field(f"{firm.street}, {firm.zip_city}"),
        "managing_director": text_field(firm.director),
        "date_of_extract": date_field(firm.extract_date, de_date),
    }
    rows = [("Firma", fields["legal_name"].printed),
            ("Handelsregisternummer", fields["registration_number"].printed),
            ("Registergericht", fields["register_court"].printed),
            ("Rechtsform", fields["legal_form"].printed),
            ("Geschäftsanschrift", fields["registered_address"].printed),
            ("Geschäftsführer", fields["managing_director"].printed),
            ("Gegenstand", f"Ausführung von Arbeiten im Bereich {firm.trade}"),
            ("Datum des Abrufs", fields["date_of_extract"].printed)]
    page = Page(court, "Handelsregisterauszug", reference("HR", firm.slug, "reg"),
                BODY_TEXT["register_extract"][firm.variant], rows,
                ("Frau Brandt", "Urkundsbeamtin der Geschäftsstelle"),
                subtitle="Amtlicher Abdruck, Abteilung B")
    return Doc("register_extract", assemble(page, firm.style), fields, court, MOCK_NOTE_DE,
               page.title)


def build_insurance(firm: Firm) -> Doc:
    ins = firm.insurance
    fields = {
        "insurer": text_field(ins.party.name),
        "policy_number": text_field(ins.policy),
        "insured_name": text_field(ins.insured_name),
        "coverage_type": text_field("Betriebshaftpflichtversicherung"),
        "insured_amount_eur": Field(ins.amount, ins.amount_printed or de_amount(ins.amount)),
        "valid_from": date_field(ins.valid_from, de_date),
        "valid_until": date_field(ins.valid_until, de_date),
    }
    rows = [("Versicherer", fields["insurer"].printed),
            ("Versicherungsnummer", fields["policy_number"].printed),
            ("Versicherungsnehmer", fields["insured_name"].printed),
            ("Versicherungsart", fields["coverage_type"].printed),
            ("Deckungssumme", fields["insured_amount_eur"].printed),
            ("Versicherungsbeginn", fields["valid_from"].printed),
            ("Versicherungsende", fields["valid_until"].printed)]
    if ins.insured_address:
        fields["insured_address"] = text_field(ins.insured_address)
        rows.insert(3, ("Anschrift des Versicherungsnehmers", ins.insured_address))
    page = Page(ins.party, "Versicherungsbestätigung", reference("VB", firm.slug, "ins"),
                BODY_TEXT["insurance_certificate"][firm.variant], rows,
                (DE_SIGNERS[firm.variant], "Gewerbekundenservice"),
                subtitle="Bestätigung für Auftraggeber")
    if ins.scanned:
        scan = render_scan(page, firm.style, MOCK_NOTE_DE)
        return Doc("insurance_certificate", [], fields, ins.party, MOCK_NOTE_DE, page.title,
                   scan=scan, doc_extra={"text_layer": False})
    return Doc("insurance_certificate", story=assemble(page, firm.style), fields=fields,
               issuer=ins.party, note=MOCK_NOTE_DE, title=page.title)


def build_iso(firm: Firm, cert: Cert, key: str, standard: str) -> Doc:
    fields = {
        "certificate_number": text_field(cert.number),
        "holder_name": text_field(cert.holder),
        "standard": text_field(standard),
        "scope": text_field(cert.scope),
        "issuer": text_field(cert.party.name),
        "valid_until": date_field(cert.valid_until, en_date),
    }
    rows = iso_rows(cert, standard, fields)
    page = Page(cert.party, ISO_TITLE, reference("CERT", firm.slug, key),
                BODY_TEXT[key][firm.variant], rows,
                (CERT_SIGNERS[firm.variant], cert.party.name), subtitle=standard)
    story = assemble(page, firm.style)
    extra = {}
    if cert.cover_letter:
        story = cover_letter_story(firm, cert, standard) + [PageBreak()] + story
        extra = {name: {"page": 2} for name in fields}
    return Doc(key, story, fields, cert.party, MOCK_NOTE_EN, page.title, field_extra=extra)


def iso_rows(cert: Cert, standard: str, fields: dict[str, Field]) -> list[tuple[str, str]]:
    rows = [("Certificate number", cert.number), ("Holder", cert.holder),
            ("Standard", standard), ("Scope", cert.scope), ("Issued by", cert.party.name)]
    expires = fields["valid_until"].printed
    if cert.issued is None or cert.initial is None:
        return rows + [("Valid until", expires)]
    return rows + [("Initial certification:", en_date(cert.initial)),
                   ("Issued:", en_date(cert.issued)), ("Expires:", expires)]


def cover_letter_story(firm: Firm, cert: Cert, standard: str) -> list:
    page = Page(cert.party, "Your certificate", reference("CL", firm.slug, standard), "", [],
                (CERT_SIGNERS[0], cert.party.name))
    paragraphs = [
        "Dear Sir or Madam,",
        f"Please find enclosed the certificate for {cert.holder} under {standard}. "
        "Please keep it with your quality records and show it to clients on request.",
        "The certificate stays valid as long as the yearly surveillance audits are passed. "
        "If you have questions about the enclosed document, please contact our office.",
        "Kind regards",
    ]
    return assemble_letter(page, paragraphs, firm.style)


def build_safety_narrative(firm: Firm) -> Doc:
    data = firm.safety
    first, last = data.years[0][0], data.years[-1][0]
    accidents = sum(y[1] for y in data.years)
    lost_time = sum(y[2] for y in data.years)
    fields = {
        "firm_name": text_field(data.firm_name),
        "period": Field(f"{first}-{last}", f"{first} to {last}"),
        "reportable_accidents": Field(accidents, str(accidents), "recorded"),
        "lost_time_injuries": Field(lost_time, str(lost_time), "of which"),
        "fatalities": Field(0, "no fatalities"),
    }
    by_year = ", ".join(f"in {y} there were {a}" for y, a, _ in data.years[:-1])
    last_year, last_count, _ = data.years[-1]
    paragraphs = [
        f"This statement is issued by {data.firm_name} for clients who check our record "
        "before work on site starts.",
        f"During {first} to {last} the company recorded {accidents} reportable accidents, "
        f"of which {lost_time} led to lost time. There were no fatalities.",
        f"By year, {by_year} and in {last_year} there were {last_count}.",
        "All figures come from the accident reports filed with the employers' liability "
        "insurance association and cover every site of the company.",
    ]
    issuer = Party(data.firm_name, firm.street, firm.zip_city)
    page = Page(issuer, "Statement on Accident Statistics",
                reference("UNF", firm.slug, "saf"), "", [],
                (data.signer, "Health and Safety Manager"))
    return Doc("safety_record", assemble_letter(page, paragraphs, firm.style), fields, issuer,
               MOCK_NOTE_EN_RECORD, page.title, language="en")


def build_safety(firm: Firm) -> Doc:
    data = firm.safety
    if data.narrative:
        return build_safety_narrative(firm)
    first, last = data.years[0][0], data.years[-1][0]
    accidents = sum(y[1] for y in data.years)
    lost_time = sum(y[2] for y in data.years)
    fields = {
        "firm_name": text_field(data.firm_name),
        "period": Field(f"{first}-{last}", f"{first} bis {last}"),
        "reportable_accidents": int_field(accidents, "Meldepflichtige Arbeitsunfälle gesamt"),
        "lost_time_injuries": int_field(lost_time, "Unfälle mit Ausfalltagen gesamt"),
        "fatalities": int_field(0, "Tödliche Arbeitsunfälle gesamt"),
    }
    rows = [("Firma", data.firm_name), ("Berichtszeitraum", fields["period"].printed)]
    rows += [(f"Jahr {y}", f"{a} meldepflichtige Unfälle, davon {lt} mit Ausfalltagen")
             for y, a, lt in data.years]
    rows += [(f.label, f.printed) for f in
             (fields["reportable_accidents"], fields["lost_time_injuries"], fields["fatalities"])]
    issuer = Party(data.firm_name, firm.street, firm.zip_city)
    page = Page(issuer, f"Unfallstatistik {first} bis {last}", reference("UNF", firm.slug, "saf"),
                BODY_TEXT["safety_record"][firm.variant], rows,
                (data.signer, "Fachkraft für Arbeitssicherheit"))
    return Doc("safety_record", assemble(page, firm.style), fields, issuer, MOCK_NOTE_DE,
               page.title)


def build_bank(firm: Firm) -> Doc:
    bank = firm.bank
    iban = make_iban(bank.bank_code, bank.account)
    fields = {
        "bank_name": text_field(bank.party.name),
        "account_holder": text_field(bank.holder),
        "iban": Field(iban, group_iban(iban)),
        "date": date_field(bank.letter_date, de_date),
    }
    rows = [("Kreditinstitut", bank.party.name), ("Kontoinhaber", bank.holder),
            ("IBAN", fields["iban"].printed), ("Datum", fields["date"].printed)]
    page = Page(bank.party, "Bankbestätigung", reference("BK", firm.slug, "bank"),
                BODY_TEXT["bank_letter"][firm.variant], rows,
                (DE_SIGNERS[firm.variant], bank.party.name))
    return Doc("bank_letter", assemble(page, firm.style), fields, bank.party, MOCK_NOTE_DE,
               page.title)


def build_documents(firm: Firm) -> list[Doc]:
    docs = [
        build_register(firm),
        build_insurance(firm),
        build_iso(firm, firm.iso_9001, "iso_9001", "ISO 9001:2015"),
    ]
    if firm.iso_45001 is not None:
        docs.append(build_iso(firm, firm.iso_45001, "iso_45001", "ISO 45001:2018"))
    return docs + [build_safety(firm), build_bank(firm)]


# ---------------------------------------------------------------- firm data (all invented)

HANSEN_STYLE = Style("Helvetica", "Helvetica-Bold", "#1F4E79", "rule", "lines")
WEBER_STYLE = Style("Times-Roman", "Times-Bold", "#7A1F1F", "band", "box")
MUELLER_STYLE = Style("Helvetica", "Helvetica-Bold", "#2E6B3A", "right", "zebra")

HANSEN = Firm(
    slug="hansen-elektrotechnik", legal_name="Hansen Elektrotechnik GmbH",
    trade="electrical installation", street="Kaiserdamm 41", zip_city="22301 Hamburg",
    court="Amtsgericht Hamburg", hrb="HRB 148263", director="Jan Hansen",
    extract_date=date(2026, 10, 19), variant=0, style=HANSEN_STYLE, issues=("none",),
    insurance=Insurance(
        Party("Nordlicht Versicherung AG", "Hafenstraße 8", "20457 Hamburg"),
        "NL-BHV-5521907", "Hansen Elektrotechnik GmbH", 5_000_000,
        date(2026, 1, 1), date(2026, 12, 31)),
    iso_9001=Cert(
        Party("Nordzert GmbH", "Speicherweg 3", "20457 Hamburg"),
        "NZ-Q-2024-08812", "Hansen Elektrotechnik GmbH",
        "Planning, installation and maintenance of electrical systems in commercial buildings.",
        date(2027, 6, 30)),
    iso_45001=Cert(
        Party("Nordzert GmbH", "Speicherweg 3", "20457 Hamburg"),
        "NZ-S-2024-03377", "Hansen Elektrotechnik GmbH",
        "Occupational health and safety in electrical installation work on construction sites.",
        date(2027, 6, 30)),
    safety=Safety("Hansen Elektrotechnik GmbH", ((2023, 3, 1), (2024, 2, 1), (2025, 2, 0)),
                  "Tom Lindqvist"),
    bank=Bank(Party("Alsterbank eG", "Ballindamm 17", "20095 Hamburg"),
              "Hansen Elektrotechnik GmbH", "20050550", "1234567890", date(2026, 10, 27)),
)

WEBER = Firm(
    slug="weber-stahlbau", legal_name="Weber Stahlbau GmbH", trade="structural steel",
    street="Zeppelinstraße 112", zip_city="70193 Stuttgart", court="Amtsgericht Stuttgart",
    hrb="HRB 774102", director="Katrin Weber", extract_date=date(2026, 10, 12), variant=1,
    style=WEBER_STYLE, issues=("insurance certificate expired",),
    insurance=Insurance(
        Party("Schwabenwacht Versicherungs-AG", "Königstraße 60", "70173 Stuttgart"),
        "SW/HP/0098-4471", "Weber Stahlbau GmbH", 10_000_000,
        date(2025, 10, 16), date(2026, 10, 15)),
    iso_9001=Cert(
        Party("Süddeutsche Zertifizierung SZQ GmbH", "Gablenberger Hauptstraße 9",
              "70186 Stuttgart"),
        "SZQ 9001/26-1450", "Weber Stahlbau GmbH",
        "Design, fabrication and erection of structural steel for buildings and bridges.",
        date(2028, 3, 14)),
    iso_45001=Cert(
        Party("Süddeutsche Zertifizierung SZQ GmbH", "Gablenberger Hauptstraße 9",
              "70186 Stuttgart"),
        "SZQ 45001/26-0317", "Weber Stahlbau GmbH",
        "Safe fabrication and erection of structural steel, including work at height.",
        date(2028, 3, 14)),
    safety=Safety("Weber Stahlbau GmbH", ((2023, 6, 2), (2024, 5, 2), (2025, 4, 1)),
                  "Dr. Anja Roth"),
    bank=Bank(Party("Neckarwerk Bank eG", "Marktplatz 5", "70173 Stuttgart"),
              "Weber Stahlbau GmbH", "60090300", "0045128873", date(2026, 10, 22)),
)

MUELLER = Firm(
    slug="mueller-geruestbau", legal_name="Müller Gerüstbau GmbH", trade="scaffolding",
    street="Hafenstraße 27", zip_city="44263 Dortmund", court="Amtsgericht Dortmund",
    hrb="HRB 209317", director="Stefan Müller", extract_date=date(2026, 10, 26), variant=2,
    style=MUELLER_STYLE,
    issues=("name mismatch", "missing document: iso_45001", "insured amount below 5,000,000 EUR minimum"),
    insurance=Insurance(
        Party("Ruhrland Assekuranz AG", "Kampstraße 14", "44137 Dortmund"),
        "RA-2026-HV-300518", "Mueller Geruestbau GmbH", 3_000_000,
        date(2026, 3, 1), date(2027, 2, 28)),
    iso_9001=Cert(
        Party("WestCert Prüf- und Zertifizierungsgesellschaft mbH", "Rheinische Straße 80",
              "44137 Dortmund"),
        "WC-QMS-0067421", "Müller Gerüstbau GmbH & Co. KG",
        "Erection and dismantling of facade, working and protective scaffolding.",
        date(2027, 9, 1)),
    iso_45001=None,
    safety=Safety("Müller Gerüstbau GmbH", ((2023, 9, 3), (2024, 8, 2), (2025, 7, 2)),
                  "Uwe Kaczmarek"),
    bank=Bank(Party("Emscher Bank AG", "Westenhellweg 40", "44137 Dortmund"),
              "Mueller Geruestbau GmbH", "44050199", "0003917744", date(2026, 10, 30)),
)

BALTIC_STYLE = Style("Times-Roman", "Times-Bold", "#0B5563", "rule", "zebra")
NORDHAUS_STYLE = Style("Helvetica", "Helvetica-Bold", "#8A5A00", "band", "box")
BALTIC_ISO = Party("Küstenzert Zertifizierungs GmbH", "Lange Straße 71", "18055 Rostock")
NORDHAUS_ISO = Party("Hanse Qualitätszertifizierung GmbH", "Schlachte 21", "28195 Bremen")

BALTIC = Firm(
    slug="baltic-krane", legal_name="Baltic Krane GmbH", trade="crane hire",
    street="Warnowkai 18", zip_city="18057 Rostock", court="Amtsgericht Rostock",
    hrb="HRB 507731", director="Ines Brandenburg", extract_date=date(2026, 10, 28),
    variant=2, style=BALTIC_STYLE,
    issues=(
        "scanned insurance certificate: no text layer",
        "cover letter as page one",
        "amount written in words",
        "two dates on certificate",
        "english safety record",
    ),
    insurance=Insurance(
        Party("Ostsee Haftpflicht Versicherung VVaG", "Am Strande 2", "18055 Rostock"),
        "OHV-BHV-7730412", "Baltic Krane GmbH", 5_000_000,
        date(2026, 4, 1), date(2027, 3, 31), amount_printed="EUR 5 Mio.", scanned=True),
    iso_9001=Cert(
        BALTIC_ISO, "KZ-9001-20-04418", "Baltic Krane GmbH",
        "Provision of mobile and tower cranes with operators for construction sites.",
        date(2028, 5, 20), cover_letter=True),
    iso_45001=Cert(
        BALTIC_ISO, "KZ-45001-20-01190", "Baltic Krane GmbH",
        "Safe operation and lifting work with mobile and tower cranes on construction sites.",
        date(2029, 11, 2), issued=date(2026, 11, 3), initial=date(2020, 11, 4)),
    safety=Safety("Baltic Krane GmbH", ((2023, 5, 2), (2024, 4, 1), (2025, 2, 0)),
                  "Henrik Struck", narrative=True),
    bank=Bank(Party("Hansebank Rostock eG", "Neuer Markt 9", "18055 Rostock"),
              "Baltic Krane GmbH", "13050001", "0021784456", date(2026, 10, 29)),
)

NORDHAUS = Firm(
    slug="nordhaus-bau", legal_name="Nordhaus Bau GmbH", trade="general construction",
    street="Am Deich 3", zip_city="28199 Bremen", court="Amtsgericht Bremen",
    hrb="HRB 118204", registry_hrb="HRB 118240", director="Lars Nordhaus",
    extract_date=date(2026, 10, 21), variant=1, style=NORDHAUS_STYLE,
    issues=(
        "registration number belongs to another firm",
        "insurance address differs",
        "sanctions near miss",
        "insurance expires in 5 days",
    ),
    insurance=Insurance(
        Party("Weserschutz Versicherung AG", "Obernstraße 33", "28195 Bremen"),
        "WS-BHV-0451882", "Nordhaus Bau GmbH", 8_000_000,
        date(2025, 11, 15), date(2026, 11, 14),
        insured_address="Industriestraße 9, 27568 Bremerhaven"),
    iso_9001=Cert(
        NORDHAUS_ISO, "HQZ-9001-24-0771", "Nordhaus Bau GmbH",
        "General construction of residential and commercial buildings, including project "
        "management.", date(2027, 8, 31)),
    iso_45001=Cert(
        NORDHAUS_ISO, "HQZ-45001-24-0212", "Nordhaus Bau GmbH",
        "Safe execution of general construction work on building sites.", date(2027, 8, 31)),
    safety=Safety("Nordhaus Bau GmbH", ((2023, 7, 3), (2024, 6, 2), (2025, 5, 2)),
                  "Petra Lührs"),
    bank=Bank(Party("Weserbank eG", "Domshof 4", "28195 Bremen"),
              "Nordhaus Bau GmbH", "29050101", "0078123456", date(2026, 10, 28)),
)
FIRMS = (HANSEN, WEBER, MUELLER, BALTIC, NORDHAUS)


# ---------------------------------------------------------------- answer keys and lists


def answer_key(firm: Firm, docs: list[Doc]) -> dict:
    return {
        "slug": firm.slug,
        "legal_name": firm.legal_name,
        "country": COUNTRY,
        "trade": firm.trade,
        "as_of": AS_OF.isoformat(),
        "planted_issues": list(firm.issues),
        "documents": {d.key: document_entry(d) for d in docs},
    }


def document_entry(doc: Doc) -> dict:
    fields = {
        name: {"value": f.value, "printed": f.printed} | doc.field_extra.get(name, {})
        for name, f in doc.fields.items()
    }
    return {
        "file": DOC_FILES[doc.key],
        "language": doc.language or DOC_LANGUAGE[doc.key],
        **doc.doc_extra,
        "fields": fields,
    }


def register_entries() -> list[dict]:
    firms = [(f.registry_hrb or f.hrb, f.legal_name, f.court) for f in FIRMS]
    others = [
        ("HRB 512044", "Brandt Fliesenlegerei GmbH", "Amtsgericht Köln"),
        ("HRB 338871", "Schneider Bautechnik GmbH", "Amtsgericht Frankfurt am Main"),
        ("HRB 906215", "Koch Tiefbau GmbH", "Amtsgericht München"),
        ("HRB 774210", "Weber Stahlbau Handels GmbH", "Amtsgericht Stuttgart"),
        ("HRB 120958", "Lindner Dachdeckerei GmbH", "Amtsgericht Leipzig"),
        ("HRB 118204", "Weserland Tiefbau GmbH", "Amtsgericht Bremen"),
    ]
    return [
        {"registration_number": n, "legal_name": name, "register_court": court, "status": "active"}
        for n, name, court in firms + others
    ]


def sanctions_entries() -> list[dict]:
    rows = [
        ("Hansen Elektro Trading Ltd", "2024-03-18", "Export control breach"),
        ("Baltmark Industrial Supply FZE", "2023-11-02", "Dual-use goods diversion"),
        ("Kesselring Beteiligungs AG", "2025-01-27", "Ownership by listed persons"),
        ("Orlov Metallhandel OOO", "2022-09-14", "Supply to listed entities"),
        ("Sundgau Marine Services SA", "2024-08-05", "Sanctions evasion by shipping"),
        ("Tal Engineering Partners LLC", "2025-06-11", "Procurement network for listed state"),
        ("Nordhaus Bau Trading FZE", "2025-09-23", "Trade in goods for listed buyers"),
    ]
    return [{"name": n, "listed_since": d, "reason": f"MOCK: {r}"} for n, d, r in rows]


README_HEAD = """# Mock data
All of this is fictional and mock. Firms, people, numbers, IBANs and addresses are invented.
- `firms/<slug>/`: text PDFs a procurement officer would receive, plus `answer_key.json`.
- `answer_key.json`: the exact field values printed in the PDFs, for scoring extraction.
- The "as of" date for validity checks is 2026-11-09.
- `mock_register.json`: fake company register. Near miss: "Weber Stahlbau Handels GmbH".
  Nordhaus Bau GmbH is listed under HRB 118240; HRB 118204 belongs to Weserland Tiefbau GmbH.
- `mock_sanctions.json`: fake sanctions list. Near misses: "Hansen Elektro Trading Ltd",
  "Nordhaus Bau Trading FZE".
- Regenerate everything: `uv run python scripts/make_mock_data.py`
- The script is deterministic and checks every printed value against the PDF text.
- Each PDF carries a MOCK note in its footer.

| Firm | Slug | Planted issues |
|---|---|---|
"""


def readme_text() -> str:
    rows = [f"| {f.legal_name} | `{f.slug}` | {'; '.join(f.issues)} |" for f in FIRMS]
    return README_HEAD + "\n".join(rows) + "\n"


def write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_firm(firm: Firm) -> None:
    folder = FIRMS_DIR / firm.slug
    folder.mkdir(parents=True, exist_ok=True)
    docs = build_documents(firm)
    for stale in set(DOC_FILES.values()) - {DOC_FILES[d.key] for d in docs}:
        (folder / stale).unlink(missing_ok=True)
    for doc in docs:
        write_pdf(folder / DOC_FILES[doc.key], doc, firm.style)
    write_json(folder / "answer_key.json", answer_key(firm, docs))


def write_all() -> None:
    for firm in FIRMS:
        write_firm(firm)
    write_json(DATA_DIR / "mock_register.json", register_entries())
    write_json(DATA_DIR / "mock_sanctions.json", sanctions_entries())
    (DATA_DIR / "README.md").write_text(readme_text(), encoding="utf-8")


# ---------------------------------------------------------------- verification


@dataclass
class Check:
    slug: str
    document: str
    checked: int = 0
    missing: list[str] = field(default_factory=list)
    pages: int = 0
    note: str = ""


def normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def field_found(text: str, spec: dict, label: str | None) -> bool:
    printed = normalise(spec["printed"])
    if label:
        return normalise(f"{label} {printed}") in text
    return printed in text


def verify_image_only(check: Check, reader: PdfReader, texts: list[str]) -> Check:
    if any(texts):
        check.missing.append("text layer should be empty")
    if check.pages != 1:
        check.missing.append("page count should be 1")
    if len(reader.pages[0].images) != 1:
        check.missing.append("page should hold one image")
    check.note = "image only: empty text, 1 page, 1 image"
    return check


def verify_document(slug: str, key: str, entry: dict, labels: dict) -> Check:
    reader = PdfReader(FIRMS_DIR / slug / entry["file"])
    texts = [normalise(page.extract_text() or "") for page in reader.pages]
    check = Check(slug, key, pages=len(texts))
    if entry.get("text_layer", True) is False:
        return verify_image_only(check, reader, texts)
    everything = " ".join(texts)
    for name, spec in entry["fields"].items():
        check.checked += 1
        text = texts[spec["page"] - 1] if "page" in spec else everything
        if not field_found(text, spec, labels.get(name)):
            check.missing.append(name)
    return check


def label_map(firm: Firm) -> dict:
    return {f: fld.label for f, fld in build_safety(firm).fields.items() if fld.label}


def verify_all() -> list[Check]:
    results = []
    for firm in FIRMS:
        key = json.loads((FIRMS_DIR / firm.slug / "answer_key.json").read_text(encoding="utf-8"))
        for doc_key, entry in key["documents"].items():
            labels = label_map(firm) if doc_key == "safety_record" else {}
            results.append(verify_document(firm.slug, doc_key, entry, labels))
    return results


def print_table(results: list[Check]) -> bool:
    print(f"{'firm':24} {'document':22} {'fields':>6}  {'pages':>5}  all found")
    for r in results:
        verdict = "yes" if not r.missing else "NO: " + ", ".join(r.missing)
        if r.note and not r.missing:
            verdict = f"yes ({r.note})"
        print(f"{r.slug:24} {r.document:22} {r.checked:>6}  {r.pages:>5}  {verdict}")
    print(f"PDFs: {len(results)}, pages: {sum(r.pages for r in results)}")
    return all(not r.missing for r in results)


def main() -> int:
    write_all()
    return 0 if print_table(verify_all()) else 1


if __name__ == "__main__":
    sys.exit(main())
