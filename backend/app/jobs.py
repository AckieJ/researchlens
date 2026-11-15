import threading

from . import config as C


def enqueue(fn_name, *args):
    """Run a job on the RQ worker (default) or in a background thread when RUN_INLINE=true."""
    if C.RUN_INLINE:
        from . import workers
        threading.Thread(target=getattr(workers, fn_name), args=args, daemon=True).start()
        return
    from redis import Redis
    from rq import Queue
    Queue("researchlens", connection=Redis.from_url(C.REDIS_URL)).enqueue(
        f"app.workers.{fn_name}", *[str(a) for a in args], job_timeout=3600)
