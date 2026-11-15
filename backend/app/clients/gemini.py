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
        r = client().models.generate_content(
            model=model or C.GEMINI_MODEL, contents=prompt,
            config=types.GenerateContentConfig(system_instruction=system, response_mime_type="application/json", temperature=0.0))
        return parse_json(r.text)

    return retry(call, tries=3)


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
            return [e.values for e in r.embeddings]

        out.extend(retry(call, tries=3))
    return out
