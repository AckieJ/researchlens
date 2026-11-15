from app.clients import gemini
from app.clients.util import is_rate_limited, retry, retry_delay

MSG = "429 RESOURCE_EXHAUSTED. {'error': {'message': 'Please retry in 51.488519608s.', 'details': [{'retryDelay': '51s'}]}}"


def test_retry_delay_parsing():
    assert abs(retry_delay(Exception(MSG)) - 51.49) < 0.01
    assert retry_delay(Exception("'retryDelay': '34s'")) == 34.0
    assert retry_delay(Exception("boom")) is None
    assert is_rate_limited(Exception(MSG)) and not is_rate_limited(Exception("boom"))


def test_retry_waits_for_server_delay(monkeypatch=None):
    import app.clients.util as u
    waits, calls = [], {"n": 0}
    real = u.time.sleep
    u.time.sleep = lambda s: waits.append(s)
    try:
        def fn():
            calls["n"] += 1
            if calls["n"] < 3:
                raise Exception(MSG)
            return "ok"
        assert retry(fn, tries=5) == "ok"
    finally:
        u.time.sleep = real
    assert len(waits) == 2 and all(50 < w <= 90 for w in waits)


def test_batches_respect_token_budget():
    texts = ["x" * 3000] * 20            # ~1000 est. tokens each
    batches = list(gemini._batches(texts, max_items=50, max_tokens=8000))
    assert sum(len(b) for b in batches) == 20 and all(len(b) <= 8 for b in batches)


def test_budget_gate_blocks_then_releases():
    gemini._window.clear()
    old, sleeps = gemini.C.EMBED_TOKENS_PER_MIN, []
    gemini.C.EMBED_TOKENS_PER_MIN = 1000
    real = gemini.time.sleep
    def fake_sleep(s):
        sleeps.append(s)
        gemini._window.clear()           # pretend the 60 s window passed
    gemini.time.sleep = fake_sleep
    try:
        gemini._wait_for_budget(800)     # fits
        gemini._wait_for_budget(800)     # does not fit -> must sleep once
    finally:
        gemini.time.sleep = real
        gemini.C.EMBED_TOKENS_PER_MIN = old
        gemini._window.clear()
    assert len(sleeps) == 1
