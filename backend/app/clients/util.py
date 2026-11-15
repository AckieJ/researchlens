import random
import time


def retry(fn, tries=4, base=1.8):
    """Call fn(); on failure wait base**i seconds (plus jitter) and try again."""
    for i in range(tries):
        try:
            return fn()
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(base ** i + random.random())
