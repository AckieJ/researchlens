"""Gemini wrapper: JSON generation and embeddings."""
import json
import re
import threading
import time

from .. import config as C
from .util import retry

_client = None


def client():
    global _client
    if _client is None:
        from google import genai
        _client = genai.Client(api_key=C.GEMINI_API_KEY)
    return _client


def parse_json(text):
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?|```$", "", t, flags=re.M).strip()
    a, b = t.find("{"), t.rfind("}")
    return json.loads(t[a:b + 1] if a >= 0 and b > a else t)


def generate_json(prompt, system=None, model=None):
    from google.genai import types

    def call():
        kw = {}
        if C.GEMINI_TEMPERATURE:
            kw["temperature"] = float(C.GEMINI_TEMPERATURE)
        elif C.GEMINI_MODEL.startswith("gemini-2"):
            kw["temperature"] = 0.0
        r = client().models.generate_content(
            model=model or C.GEMINI_MODEL, contents=prompt,
            config=types.GenerateContentConfig(system_instruction=system, response_mime_type="application/json", **kw))
        return parse_json(r.text)

    return retry(call, tries=5)


def _unit(v):
    """Truncated (output_dimensionality < 3072) embeddings are not unit length; normalise so cosine scores are consistent."""
    n = sum(x * x for x in v) ** 0.5
    return [x / n for x in v] if n else list(v)


def explain(exc):
    """Short, actionable description of a Gemini failure."""
    code = getattr(exc, "code", None)
    msg = str(exc)[:300]
    hint = ""
    if code in (400, 401, 403) or "API key" in msg or "ACCESS_TOKEN" in msg or "UNAUTHENTICATED" in msg:
        hint = (" -> The key was rejected. Create a fresh key at https://aistudio.google.com/apikey "
                "(if it starts with 'AQ.' and still fails, create the key from a project in AI Studio or use a legacy 'AIza' key) "
                "and update GEMINI_API_KEY on Render.")
    elif code == 404 or "not found" in msg.lower():
        hint = " -> Model name not found for this key. Check GEMINI_MODEL / GEMINI_EMBED_MODEL spelling."
    elif code == 429:
        hint = " -> Rate/quota limit hit. The app now waits and retries; if it still fails, lower MAX_CANDIDATES / LLM_CONCURRENCY or enable billing on the Gemini API key (free-tier quotas are small)."
    return f"{type(exc).__name__}: {msg}{hint}"


_window = []          # (timestamp, estimated_tokens) for requests sent in the last 60 s
_wlock = threading.Lock()


def _est_tokens(text):
    return max(1, len(text) // 3)      # deliberately pessimistic (~3 characters per token)


def _wait_for_budget(tokens):
    """Block until sending `tokens` more keeps us under EMBED_TOKENS_PER_MIN in any 60-second window."""
    budget = C.EMBED_TOKENS_PER_MIN
    while True:
        with _wlock:
            now = time.time()
            _window[:] = [(t, n) for t, n in _window if now - t < 60]
            if not _window or sum(n for _, n in _window) + tokens <= budget:
                _window.append((now, tokens))
                return
            wait = 60 - (now - _window[0][0]) + 0.5
        time.sleep(max(wait, 0.5))


def _batches(texts, max_items=50, max_tokens=8000):
    batch, tok = [], 0
    for t in texts:
        n = _est_tokens(t)
        if batch and (len(batch) >= max_items or tok + n > max_tokens):
            yield batch
            batch, tok = [], 0
        batch.append(t)
        tok += n
    if batch:
        yield batch


def embed(texts):
    """Embed texts with one consistent task type so any two vectors are comparable.
    Requests are paced to stay under the embedding tokens-per-minute quota, and 429s wait as long as Google asks."""
    from google.genai import types
    out = []
    clean = [(t or " ")[:8000] for t in texts]
    for chunk in _batches(clean):
        _wait_for_budget(sum(_est_tokens(t) for t in chunk))

        def call():
            r = client().models.embed_content(
                model=C.GEMINI_EMBED_MODEL, contents=chunk,
                config=types.EmbedContentConfig(task_type="SEMANTIC_SIMILARITY", output_dimensionality=C.EMBED_DIM))
            return [_unit(e.values) for e in r.embeddings]

        out.extend(retry(call, tries=5))
    return out
