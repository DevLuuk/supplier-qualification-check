import json
import re
from functools import cache
from pathlib import Path

from rapidfuzz import fuzz

from supplier_check.models import LookupResult, Status

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
REGISTER_FILE = DATA_DIR / "mock_register.json"
SANCTIONS_FILE = DATA_DIR / "mock_sanctions.json"

NAME_PASS_SCORE = 0.9
NAME_UNSURE_SCORE = 0.75
SANCTIONS_UNSURE_SCORE = 0.85
EXACT_SCORE = 1.0
NO_MATCH_SCORE = 0.0
PERCENT = 100

UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})
LEGAL_FORMS = re.compile(r"&\s*co\.?|\b(gmbh|mbh|ag|kg|ltd|llc)\b")
NON_WORD = re.compile(r"[^\w\s]")
SPACES = re.compile(r"\s+")


def normalise(name: str) -> str:
    folded = name.casefold().translate(UMLAUTS)
    stripped = NON_WORD.sub(" ", LEGAL_FORMS.sub(" ", folded))
    return SPACES.sub(" ", stripped).strip()


def name_score(a: str, b: str) -> float:
    return fuzz.token_sort_ratio(normalise(a), normalise(b)) / PERCENT


def _printed(name: str) -> str:
    return SPACES.sub(" ", name).strip().casefold()


def name_status(expected: str, found: str) -> tuple[Status, float]:
    score = name_score(expected, found)
    if score < NAME_UNSURE_SCORE:
        return "fail", score
    if score < NAME_PASS_SCORE or _printed(expected) != _printed(found):
        return "unsure", score
    return "pass", score


@cache
def _load(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def lookup_register(registration_number: str) -> LookupResult:
    wanted = _printed(registration_number)
    for entry in _load(REGISTER_FILE):
        if _printed(entry["registration_number"]) == wanted:
            return LookupResult(
                source="mock_register",
                query=registration_number,
                match=entry["legal_name"],
                score=EXACT_SCORE,
                note=f"MOCK: {entry['register_court']} lists {registration_number} "
                f"as {entry['legal_name']}, status {entry['status']}.",
            )
    return LookupResult(
        source="mock_register",
        query=registration_number,
        match=None,
        score=NO_MATCH_SCORE,
        note=f"MOCK: {registration_number} is not in the register.",
    )


def screen_sanctions(name: str) -> LookupResult:
    scored = [(name_score(name, entry["name"]), entry) for entry in _load(SANCTIONS_FILE)]
    score, entry = max(scored, key=lambda pair: pair[0])
    return LookupResult(
        source="mock_sanctions",
        query=name,
        match=entry["name"],
        score=round(score, 3),
        note=f"MOCK: closest sanctions entry is {entry['name']} "
        f"(score {score:.2f}, listed for: {entry['reason'].removeprefix('MOCK: ')}).",
    )


def sanctions_status(result: LookupResult) -> Status:
    if result.score >= EXACT_SCORE:
        return "fail"
    if result.score >= SANCTIONS_UNSURE_SCORE:
        return "unsure"
    return "pass"
