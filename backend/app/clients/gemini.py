"""Gemini wrapper: JSON generation and embeddings."""
import hashlib
import json
import logging
import re
import threading
import time

from .. import config as C
from .util import retry

log = logging.getLogger("researchlens")
CACHE_VERSION = "v1"      # bump to invalidate every cached model response

_client = None


def client():
    global _client
    if _client is None:
        from google import genai
        _client = genai.Client(api_key=C.GEMINI_API_KEY)
    return _client


class BadModelReply(ValueError):
    """The model answered, but not with usable JSON. With temperature 0 and a fixed seed an identical retry would
    reproduce the same text, so retry() must not repeat it; generate_json re-asks once with a changed seed instead."""
    no_retry = True


def parse_json(text):
    """Parse the model's reply. Tolerates code fences, text around the JSON, and the model emitting several JSON
    objects back to back ('Extra data' errors): the first value is used, and dict replies are merged key by key."""
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?|```$", "", t, flags=re.M).strip()
    dec, vals, i = json.JSONDecoder(), [], 0
    while i < len(t):
        starts = [x for x in (t.find("{", i), t.find("[", i)) if x >= 0]
        if not starts:
            break
        j = min(starts)
        try:
            v, end = dec.raw_decode(t, j)
        except json.JSONDecodeError:
            i = j + 1
            continue
        vals.append(v)
        i = end
    if not vals:
        raise json.JSONDecodeError("no JSON value found in the model reply", t, 0)
    dicts = [v for v in vals if isinstance(v, dict)]
    if len(dicts) > 1:
        merged = {}
        for d in dicts:
            for k, v in d.items():
                if isinstance(v, list) and isinstance(merged.get(k), list):
                    merged[k] = merged[k] + v
                else:
                    merged.setdefault(k, v)
        return merged
    return dicts[0] if dicts else vals[0]


def _as_object(data, list_key=None):
    """Models occasionally answer with a bare list or a one-element list instead of the requested object.
    Accept those shapes; anything else raises, so retry() asks again and the bad reply is never cached."""
    if isinstance(data, list):
        if len(data) == 1 and isinstance(data[0], dict):
            data = data[0]
        elif list_key:
            data = {list_key: data}
    if not isinstance(data, dict):
        raise ValueError(f"Gemini returned {type(data).__name__} instead of a JSON object")
    return data


_gate_lock = threading.Lock()
_next_slot = [0.0]


def _pace():
    """Space generation calls so we never exceed GEMINI_RPM (avoids 429s, whose retries cost 30+ s each)."""
    if C.GEMINI_RPM <= 0:
        return
    gap = 60.0 / C.GEMINI_RPM
    with _gate_lock:
        now = time.time()
        slot = max(now, _next_slot[0])
        _next_slot[0] = slot + gap
    if slot > now:
        time.sleep(slot - now)


def _gen_settings():
    kw = {}
    t = (C.GEMINI_TEMPERATURE or "").strip().lower()
    if t != "default":
        kw["temperature"] = float(t) if t else 0.0
        kw["seed"] = C.GEMINI_SEED
    return kw


def _cache_key(model, system, prompt, kw):
    raw = json.dumps([CACHE_VERSION, model, system, prompt, kw], sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def _cache_get(key):
    from ..db import one
    try:
        hit = one("SELECT response FROM llm_cache WHERE key=%s", (key,))
        return hit["response"] if hit else None
    except Exception:
        log.warning("llm_cache read failed", exc_info=True)
        return None


def _cache_put(key, value):
    from ..db import ex
    try:
        ex("INSERT INTO llm_cache (key, response) VALUES (%s, %s::jsonb) ON CONFLICT (key) DO NOTHING", (key, json.dumps(value)))
    except Exception:
        log.warning("llm_cache write failed", exc_info=True)


STATS = {"llm_calls": 0, "llm_cache_hits": 0, "llm_bad_replies": 0, "llm_seconds": 0.0}
_THINKING_OFF = set()      # models that rejected our thinking setting (we stop sending it)


def snapshot():
    with _gate_lock:
        return {k: (round(v, 1) if isinstance(v, float) else v) for k, v in STATS.items()}


def _bump(key, n=1):
    with _gate_lock:
        STATS[key] += n


def _thinking_config(model):
    from google.genai import types
    if model in _THINKING_OFF:
        return None
    if model.startswith("gemini-2.5") and "pro" not in model and C.GEMINI_THINKING_BUDGET >= 0:
        return types.ThinkingConfig(thinking_budget=C.GEMINI_THINKING_BUDGET)
    if model.startswith("gemini-3") and C.GEMINI_THINKING_LEVEL:
        return types.ThinkingConfig(thinking_level=C.GEMINI_THINKING_LEVEL.lower())
    return None


def _request(model, system, prompt, kw):
    from google.genai import types
    tc = _thinking_config(model)
    for with_thinking in ((True, False) if tc is not None else (False,)):
        cfg = dict(kw)
        if with_thinking:
            cfg["thinking_config"] = tc
        try:
            return client().models.generate_content(
                model=model, contents=prompt,
                config=types.GenerateContentConfig(system_instruction=system, response_mime_type="application/json", **cfg))
        except Exception as e:
            if with_thinking and getattr(e, "code", None) == 400 and "think" in str(e).lower():
                log.warning("%s rejected the thinking setting (%s); sending requests without it from now on", model, str(e)[:160])
                _THINKING_OFF.add(model)
                continue
            raise


def _once(model, system, prompt, kw, list_key):
    def call():
        _pace()
        t0 = time.time()
        r = _request(model, system, prompt, kw)
        _bump("llm_calls")
        _bump("llm_seconds", time.time() - t0)
        try:
            return _as_object(parse_json(r.text), list_key)
        except ValueError as e:                      # includes JSONDecodeError
            _bump("llm_bad_replies")
            raise BadModelReply(f"unusable JSON from {model}: {str(e)[:120]}") from e
    return retry(call, tries=5)


def generate_json(prompt, system=None, model=None, cache=True, list_key=None):
    """JSON generation. Deterministic settings, and identical (model, settings, system, prompt) input is answered from the
    database: the same question always sees the same interpretation, claims and verdicts, and costs no API call."""
    model = model or C.GEMINI_MODEL
    kw = _gen_settings()
    use_cache = cache and C.REUSE_CACHE
    key = _cache_key(model, system, prompt, kw) if use_cache else None
    if key:
        hit = _cache_get(key)
        if hit is not None:
            _bump("llm_cache_hits")
            return hit
    try:
        out = _once(model, system, prompt, kw, list_key)
    except BadModelReply as first:
        # temperature 0 + a fixed seed would give the same malformed text again, so change the seed and tighten the instruction once.
        log.warning("%s; re-asking once with a different seed", first)
        kw2 = dict(kw)
        if "seed" in kw2:
            kw2["seed"] = int(kw2["seed"]) + 1
        out = _once(model, system, prompt + "\n\nReturn exactly ONE valid JSON object and nothing else. Keep every string value short.",
                    kw2, list_key)
    if key:
        _cache_put(key, out)
    return out


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


def _ekey(text):
    return hashlib.sha256(f"{C.GEMINI_EMBED_MODEL}|{C.EMBED_DIM}|{text}".encode()).hexdigest()


def _embed_cached(keys):
    from ..db import q
    if not (C.REUSE_CACHE and keys):
        return {}
    try:
        return {r["key"]: json.loads(r["e"]) for r in q("SELECT key, embedding::text AS e FROM embed_cache WHERE key = ANY(%s)", (list(keys),))}
    except Exception:
        log.warning("embed_cache read failed", exc_info=True)
        return {}


def _embed_store(pairs):
    from ..db import exmany
    from ..db import vec
    if not (C.REUSE_CACHE and pairs):
        return
    try:
        exmany("INSERT INTO embed_cache (key, embedding) VALUES (%s, %s::vector) ON CONFLICT (key) DO NOTHING",
               [(k, vec(v)) for k, v in pairs])
    except Exception:
        log.warning("embed_cache write failed", exc_info=True)


def embed(texts):
    """Embed texts with one consistent task type so any two vectors are comparable.
    Texts already embedded before are read from the database (no API call, no quota). The rest are paced to stay
    under the embedding tokens-per-minute quota, and 429s wait as long as Google asks."""
    from google.genai import types
    clean = [(t or " ")[:8000] for t in texts]
    keys = [_ekey(t) for t in clean]
    have = _embed_cached(set(keys))
    todo = [(k, t) for k, t in dict(zip(keys, clean)).items() if k not in have]
    fresh = []
    for chunk in _batches([t for _, t in todo]):
        _wait_for_budget(sum(_est_tokens(t) for t in chunk))

        def call():
            r = client().models.embed_content(
                model=C.GEMINI_EMBED_MODEL, contents=chunk,
                config=types.EmbedContentConfig(task_type="SEMANTIC_SIMILARITY", output_dimensionality=C.EMBED_DIM))
            return [_unit(e.values) for e in r.embeddings]

        fresh.extend(retry(call, tries=5))
    new = {k: [round(x, 6) for x in v] for (k, _), v in zip(todo, fresh)}   # same precision as the cached copy
    _embed_store(list(new.items()))
    have.update(new)
    return [have[k] for k in keys]
