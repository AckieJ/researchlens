import random
import time


def _permanent(exc):
    """HTTP 4xx (except 408/429) will not succeed on retry: fail fast instead of burning time and quota."""
    resp = getattr(exc, "response", None)
    code = getattr(resp, "status_code", None)
    if code is None:
        code = getattr(exc, "code", None) if isinstance(getattr(exc, "code", None), int) else None
    return isinstance(code, int) and 400 <= code < 500 and code not in (408, 429)


def retry(fn, tries=4, base=1.8):
    """Call fn(); on failure wait base**i seconds (plus jitter) and try again. Permanent 4xx errors are not retried."""
    for i in range(tries):
        try:
            return fn()
        except Exception as e:
            if i == tries - 1 or _permanent(e):
                raise
            time.sleep(base ** i + random.random())
