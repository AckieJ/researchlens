"""Gemini wrapper: JSON generation and embeddings."""
import json
import re

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

    return retry(call, tries=3)


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
        hint = " -> Rate/quota limit hit. Lower LLM_CONCURRENCY or wait; free-tier quotas are small."
    return f"{type(exc).__name__}: {msg}{hint}"


def embed(texts, batch=50):
    """Embed texts with one consistent task type so any two vectors are comparable."""
    from google.genai import types
    out = []
    clean = [(t or " ")[:8000] for t in texts]
    for i in range(0, len(clean), batch):
        chunk = clean[i:i + batch]

        def call():
            r = client().models.embed_content(
                model=C.GEMINI_EMBED_MODEL, contents=chunk,
                config=types.EmbedContentConfig(task_type="SEMANTIC_SIMILARITY", output_dimensionality=C.EMBED_DIM))
            return [_unit(e.values) for e in r.embeddings]

        out.extend(retry(call, tries=3))
    return out
