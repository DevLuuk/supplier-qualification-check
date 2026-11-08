import pytest
from pydantic import BaseModel

from supplier_check import llm
from supplier_check.models import CallLog


class Answer(BaseModel):
    text: str


@pytest.fixture
def fake_model(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(llm, "calls", [])
    asked = []

    def ask(model, level, request, schema):
        asked.append(model)
        log = CallLog(step=schema.__name__, model=model, tokens_in=10, tokens_out=5, seconds=1.0)
        return '{"text": "live answer"}', log

    monkeypatch.setattr(llm, "_ask_model", ask)
    return asked


def _cache_file() -> "llm.Path":
    request = llm._contents("prompt", ["page"], [])
    return llm._cache_file(llm.MODELS["careful"], llm.thinking, request, Answer)


def test_cached_answer_is_used_when_not_live(fake_model, monkeypatch):
    monkeypatch.setattr(llm, "live", False)
    llm.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _cache_file().write_text('{"text": "cached answer"}', encoding="utf-8")
    assert llm.complete("prompt", Answer, ["page"], "careful").text == "cached answer"
    assert fake_model == []
    assert llm.calls[-1].model.endswith(llm.CACHED_SUFFIX)


def test_live_run_ignores_cache_and_rewrites_it(fake_model, monkeypatch):
    monkeypatch.setattr(llm, "live", True)
    llm.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _cache_file().write_text('{"text": "cached answer"}', encoding="utf-8")
    assert llm.complete("prompt", Answer, ["page"], "careful").text == "live answer"
    assert fake_model == [llm.MODELS["careful"]]
    assert llm.calls[-1].tokens_in == 10
    assert "live answer" in _cache_file().read_text(encoding="utf-8")


def test_use_live_switches_flag(monkeypatch):
    monkeypatch.setattr(llm, "live", False)
    llm.use_live(True)
    assert llm.live is True
    llm.use_live(False)
    assert llm.live is False


def test_cost_is_in_rappen_at_the_chf_rate():
    call = CallLog(step="x", model="gemini-3.8-flash", tokens_in=1_000_000, tokens_out=0, seconds=0.0)
    assert llm.cost_rappen(call) == pytest.approx(0.75 * llm.CHF_PER_USD * 100)
    cached = call.model_copy(update={"model": "gemini-3.8-flash (cached)", "tokens_in": 0})
    assert llm.cost_rappen(cached) == 0
