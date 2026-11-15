import random
import re
import time


def _code(exc):
    resp = getattr(exc, "response", None)
    code = getattr(resp, "status_code", None)
    if code is None and isinstance(getattr(exc, "code", None), int):
        code = exc.code
    return code


def _permanent(exc):
    """HTTP 4xx (except 408/429) will not succeed on retry: fail fast instead of burning time and quota."""
    code = _code(exc)
    return isinstance(code, int) and 400 <= code < 500 and code not in (408, 429)


def retry_delay(exc):
    """Seconds the server asked us to wait. Gemini 429s say 'Please retry in 51.4s' / 'retryDelay': '51s'."""
    msg = str(exc)
    m = re.search(r"retry in ([\d.]+)\s*s", msg, re.I) or re.search(r"retryDelay['\"]?\s*:\s*['\"]?([\d.]+)s", msg)
    return float(m.group(1)) if m else None


def is_rate_limited(exc):
    return _code(exc) == 429 or "RESOURCE_EXHAUSTED" in str(exc)


def retry(fn, tries=4, base=1.8, max_wait=90):
    """Call fn(); on failure wait and try again. Permanent 4xx errors are not retried.
    429 rate limits wait for the delay the server asked for; 503 overloads wait longer than ordinary errors."""
    for i in range(tries):
        try:
            return fn()
        except Exception as e:
            if i == tries - 1 or _permanent(e):
                raise
            if is_rate_limited(e):
                wait = min(max_wait, (retry_delay(e) or 30.0) + 1 + random.random())
            elif _code(e) == 503 or "UNAVAILABLE" in str(e):
                wait = min(max_wait, 6.0 * (i + 1) + random.random())
            else:
                wait = base ** i + random.random()
            time.sleep(wait)
