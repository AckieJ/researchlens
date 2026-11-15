"""No database, network or API keys needed."""
import json
import sys
import types as pytypes

from app import config as C
from app.clients import gemini
from app.pipeline.text import focus_text, question_key, quote_ok


def test_question_key_ignores_case_punctuation_spacing():
    assert question_key("Does virtual reality help in education?") == question_key("  does VIRTUAL reality help,  in education ")
    assert question_key("does virtual reality help in education") != question_key("does virtual reality harm education")


def test_focus_text_is_deterministic_and_keeps_findings():
    text = ("Background sentence about the field. " * 300) + ("Students improved by 25% (p < 0.01) after 12 weeks. " * 4) + ("Methods filler text. " * 3000)
    a, b = focus_text(text, 6000), focus_text(text, 6000)
    assert a == b and len(a) <= 6200
    assert "improved by 25% (p < 0.01) after 12 weeks" in a
    assert focus_text("short text", 6000) == "short text"


def test_quotes_are_checked_against_the_full_paper_not_the_trimmed_view():
    full = ("Filler. " * 2000) + "Participants who used VR scored 12% higher on the retention test (p = 0.003)." + (" Filler." * 2000)
    assert quote_ok("Participants who used VR scored 12% higher on the retention test (p = 0.003).", full)


def test_generation_is_deterministic_by_default():
    kw = gemini._gen_settings()
    assert kw["temperature"] == 0.0 and kw["seed"] == C.GEMINI_SEED


def test_llm_cache_key_changes_with_any_input():
    kw = gemini._gen_settings()
    base = gemini._cache_key("m", "sys", "prompt", kw)
    assert base == gemini._cache_key("m", "sys", "prompt", kw)
    assert base != gemini._cache_key("m", "sys", "prompt2", kw)
    assert base != gemini._cache_key("m2", "sys", "prompt", kw)
    assert base != gemini._cache_key("m", "sys2", "prompt", kw)


def test_identical_prompt_is_served_from_cache_without_calling_the_model(monkeypatch):
    store, calls = {}, []
    monkeypatch.setattr(gemini, "_cache_get", lambda k: store.get(k))
    monkeypatch.setattr(gemini, "_cache_put", lambda k, v: store.__setitem__(k, v))

    class FakeModels:
        def generate_content(self, **kw):
            calls.append(1)
            return type("R", (), {"text": json.dumps({"ok": len(calls)})})()

    monkeypatch.setattr(gemini, "client", lambda: type("C", (), {"models": FakeModels()})())
    fake_types = pytypes.SimpleNamespace(GenerateContentConfig=lambda **kw: kw, ThinkingConfig=lambda **kw: kw)
    fake_genai = pytypes.SimpleNamespace(types=fake_types)
    monkeypatch.setitem(sys.modules, "google", pytypes.SimpleNamespace(genai=fake_genai))
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)
    monkeypatch.setitem(sys.modules, "google.genai.types", fake_types)
    monkeypatch.setattr(C, "REUSE_CACHE", True)
    first = gemini.generate_json("same prompt", system="s")
    second = gemini.generate_json("same prompt", system="s")
    assert first == second == {"ok": 1} and len(calls) == 1


def test_bare_list_replies_are_accepted_or_rejected_never_crash():
    import pytest
    assert gemini._as_object([{"claims": [1]}]) == {"claims": [1]}
    assert gemini._as_object([{"a": 1}, {"b": 2}], "claims") == {"claims": [{"a": 1}, {"b": 2}]}
    assert gemini._as_object([], "claims") == {"claims": []}
    with pytest.raises(ValueError):
        gemini._as_object([], None)
