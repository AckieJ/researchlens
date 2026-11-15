import logging
import threading
import time

from . import config as C

log = logging.getLogger("researchlens")


def _keepalive(stop):
    """Render's free web service sleeps after 15 min without *inbound* traffic, which would kill an inline job.
    While a job runs, ping our own public URL so the instance stays awake."""
    if not C.SELF_URL:
        return
    import requests
    while not stop.wait(240):
        try:
            requests.get(C.SELF_URL.rstrip("/") + "/health", timeout=20)
        except Exception:
            pass


def _run_inline(fn, args):
    stop = threading.Event()
    threading.Thread(target=_keepalive, args=(stop,), daemon=True).start()
    try:
        fn(*args)
    except Exception:
        log.exception("inline job crashed")
    finally:
        stop.set()


def enqueue(fn_name, *args):
    """Run a job on the RQ worker (default) or in a background thread when RUN_INLINE=true."""
    if C.RUN_INLINE:
        from . import workers
        threading.Thread(target=_run_inline, args=(getattr(workers, fn_name), args), daemon=True).start()
        return
    from redis import Redis
    from rq import Queue
    Queue("researchlens", connection=Redis.from_url(C.REDIS_URL)).enqueue(
        f"app.workers.{fn_name}", *[str(a) for a in args], job_timeout=3600)
