import hashlib
import json
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from functools import cache
from pathlib import Path
from typing import TypeVar

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel

from supplier_check.models import CallLog, Thinking, Tier

MODELS: dict[Tier, str] = {
    "fast": "gemini-3.5-flash-lite",
    "careful": "gemini-3.8-flash",
}
# USD per million tokens, paid tier, from https://aistudio.google.com/docs/pricing on 2026-11-08
# (gemini-3.8-flash price valid until 2026-12-31, doubles from 2027-01-01)
PRICE_USD_PER_MILLION: dict[str, tuple[float, float]] = {
    "gemini-3.5-flash-lite": (0.30, 2.50),
    "gemini-3.8-flash": (0.75, 3.75),
}
# assumed exchange rate, not verified
EUR_PER_USD = 0.92
CENTS_PER_EURO = 100
TOKENS_PER_MILLION = 1_000_000

DEFAULT_THINKING: Thinking = "minimal"
FAST_THINKING: Thinking = "normal"
# gemini-3.8-flash accepts only low, medium (its default) and high; MINIMAL returns 400 INVALID_ARGUMENT
THINKING_MINIMAL = types.ThinkingLevel.LOW
THINKING_LEVELS: dict[Thinking, types.ThinkingLevel | None] = {
    "normal": None,
    "minimal": THINKING_MINIMAL,
}
TEMPERATURE = 0.0
TIMEOUT_MS = 120_000
SERVER_BUSY_ATTEMPTS = 3
SERVER_BUSY_CODES = [500, 503, 504]
CACHE_DIR = Path(__file__).resolve().parents[2] / "eval" / "cache"
CACHED_SUFFIX = " (cached)"
MEDIA_SIGNATURES = {b"%PDF": "application/pdf", b"\x89PNG": "image/png", b"\xff\xd8": "image/jpeg"}
DEFAULT_MEDIA_MIME = "image/png"
MEDIA_RESOLUTION = types.MediaResolution.MEDIA_RESOLUTION_MEDIUM

calls: list[CallLog] = []
thinking: Thinking = DEFAULT_THINKING

T = TypeVar("T", bound=BaseModel)

_client_lock = threading.Lock()
_tags = threading.local()


@cache
def _new_client() -> genai.Client:
    load_dotenv()
    retry = types.HttpRetryOptions(
        attempts=SERVER_BUSY_ATTEMPTS, http_status_codes=SERVER_BUSY_CODES
    )
    return genai.Client(http_options=types.HttpOptions(timeout=TIMEOUT_MS, retry_options=retry))


def _client() -> genai.Client:
    # a second Client built by a racing thread is garbage-collected mid-request and closes its connection
    with _client_lock:
        return _new_client()


@contextmanager
def tagged(file: str) -> Iterator[None]:
    _tags.file = file
    try:
        yield
    finally:
        _tags.file = ""


def use_thinking(level: Thinking) -> None:
    global thinking
    thinking = level


def cost_cents(call: CallLog) -> float:
    price_in, price_out = PRICE_USD_PER_MILLION.get(call.model, (0.0, 0.0))
    usd = (call.tokens_in * price_in + call.tokens_out * price_out) / TOKENS_PER_MILLION
    return usd * EUR_PER_USD * CENTS_PER_EURO


def _thinking_for(tier: Tier) -> Thinking:
    return thinking if tier == "careful" else FAST_THINKING


def _mime(image: bytes) -> str:
    for signature, mime in MEDIA_SIGNATURES.items():
        if image.startswith(signature):
            return mime
    return DEFAULT_MEDIA_MIME


def _contents(prompt: str, pages: list[str], images: list[bytes]) -> list:
    page_block = "\n\n".join(f"--- page {n} ---\n{text}" for n, text in enumerate(pages, 1))
    parts = [types.Part.from_bytes(data=image, mime_type=_mime(image)) for image in images]
    return [f"{prompt}\n\n{page_block}", *parts]


def _fingerprint(part: str | types.Part) -> str:
    if isinstance(part, str):
        return part
    return hashlib.sha256(part.inline_data.data).hexdigest()


def _cache_file(model: str, level: Thinking, request: list, schema: type[BaseModel]) -> Path:
    shape = json.dumps(schema.model_json_schema(), sort_keys=True)
    texts = [_fingerprint(part) for part in request]
    media = [MEDIA_RESOLUTION.value] if len(request) > 1 else []
    key = json.dumps([model, level, texts, shape, *media], ensure_ascii=False)
    return CACHE_DIR / f"{hashlib.sha256(key.encode()).hexdigest()}.json"


def _log(schema: type[BaseModel], model: str, level: Thinking, usage: object, seconds: float) -> CallLog:
    return CallLog(
        step=schema.__name__,
        model=model,
        tokens_in=getattr(usage, "prompt_token_count", 0) or 0,
        tokens_out=(getattr(usage, "candidates_token_count", 0) or 0)
        + (getattr(usage, "thoughts_token_count", 0) or 0),
        seconds=round(seconds, 2),
        file=getattr(_tags, "file", ""),
        thinking=level,
    )


def _ask_model(model: str, level: Thinking, request: list, schema: type[T]) -> tuple[str, CallLog]:
    budget = THINKING_LEVELS[level]
    config = types.GenerateContentConfig(
        temperature=TEMPERATURE,
        response_mime_type="application/json",
        response_schema=schema,
        thinking_config=types.ThinkingConfig(thinking_level=budget, include_thoughts=False) if budget else None,
        media_resolution=MEDIA_RESOLUTION if len(request) > 1 else None,
    )
    started = time.perf_counter()
    response = _client().models.generate_content(model=model, contents=request, config=config)
    log = _log(schema, model, level, response.usage_metadata, time.perf_counter() - started)
    if not response.text:
        raise ValueError(f"{model} returned no text for {schema.__name__}")
    return response.text, log


def complete(
    prompt: str,
    schema: type[T],
    pages: list[str],
    tier: Tier,
    images: list[bytes] | None = None,
) -> T:
    model, level = MODELS[tier], _thinking_for(tier)
    request = _contents(prompt, pages, images or [])
    cache_file = _cache_file(model, level, request, schema)
    if cache_file.exists():
        calls.append(_log(schema, model + CACHED_SUFFIX, level, None, 0.0))
        return schema.model_validate_json(cache_file.read_text(encoding="utf-8"))
    text, log = _ask_model(model, level, request, schema)
    calls.append(log)
    result = schema.model_validate_json(text)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(text, encoding="utf-8")
    return result
