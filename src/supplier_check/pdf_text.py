from pathlib import Path

from pypdf import PdfReader


def read_pages(path: Path) -> list[str]:
    return [page.extract_text() or "" for page in PdfReader(path).pages]


def has_text(pages: list[str]) -> bool:
    return any(page.strip() for page in pages)


def read_page_images(path: Path) -> list[bytes]:
    return [image.data for page in PdfReader(path).pages for image in page.images]
