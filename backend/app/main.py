import json
import logging
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import config as C
from .db import one, q
from .jobs import enqueue
from .pipeline import chat as chat_mod
from .pipeline import graph as G
from .pipeline import stages
from .pipeline.text import question_key
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("researchlens")
RUNNING_STATES = ("queued", "understanding", "discovering", "retrieving", "extracting", "matching", "verifying", "flagging", "layout", "evaluating")


def _startup_tasks():
    """Runs in the background so a slow/unreachable database never blocks the web server from binding its port."""
    for p in C.config_problems():
        log.warning("CONFIG: %s", p)
    try:
        from .init_db import apply
        log.info("Schema applied from %s", apply())
    except Exception:
        log.exception("Schema init failed (see /diagnostics)")
    if C.RUN_INLINE:
        # Inline jobs live in this process's threads. If the process restarted (Render free tier sleeps/redeploys), they are gone.
        try:
            n = q("UPDATE workspaces SET status='error', error=%s WHERE status = ANY(%s) RETURNING id",
                  ("The server restarted while this investigation was running (free hosting sleeps or redeploys). Press Retry to resume.",
                   list(RUNNING_STATES)))
            if n:
                log.warning("Marked %d interrupted workspace(s) as error", len(n))
        except Exception:
            log.exception("Startup sweep failed")


@asynccontextmanager
async def lifespan(_app):
    threading.Thread(target=_startup_tasks, daemon=True).start()
    yield


app = FastAPI(title="ResearchLens API", lifespan=lifespan)


@app.middleware("http")
async def json_errors(request, call_next):
    """Return JSON (not an HTML/plain 500) on unexpected errors, so the UI can show the real reason.
    Registered before CORSMiddleware so CORS headers are still added to these responses."""
    try:
        return await call_next(request)
    except Exception as e:  # noqa: BLE001
        log.exception("Unhandled error on %s %s", request.method, request.url.path)
        name = type(e).__name__
        if "Operational" in name or "PoolTimeout" in name or "Pool" in name:
            msg = "The database is unreachable. Check DATABASE_URL (no surrounding quotes) and that the Tiger Data service is running."
        else:
            msg = f"{name}: {str(e)[:300]}"
        return JSONResponse({"detail": msg}, status_code=503 if "database" in msg else 500)

app.add_middleware(CORSMiddleware, allow_origins=C.CORS_ORIGINS, allow_origin_regex=C.CORS_ORIGIN_REGEX or None,
                   allow_methods=["*"], allow_headers=["*"])
MAX_UPLOAD = 25 * 1024 * 1024


class ChatIn(BaseModel):
    question: str


def _need(x, what="not found"):
    if not x:
        raise HTTPException(404, what)
    return x


async def _read_pdf(f: UploadFile):
    if not (f.filename or "").lower().endswith(".pdf"):
        raise HTTPException(400, f"{f.filename}: only PDF files are supported")
    data = await f.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, f"{f.filename}: file is larger than 25 MB")
    return data


@app.get("/health")
def health():
    return {"ok": True}


_diag_cache = {"t": 0, "v": None}


def _check(fn):
    t = time.time()
    try:
        msg = fn()
        return {"ok": True, "detail": msg or "ok", "ms": int((time.time() - t) * 1000)}
    except Exception as e:
        return {"ok": False, "detail": f"{type(e).__name__}: {str(e)[:400]}", "ms": int((time.time() - t) * 1000)}


@app.get("/diagnostics")
def diagnostics(refresh: bool = False):
    """Live connectivity test of every dependency. Open https://<your-render-url>/diagnostics after deploying.
    Never returns secret values. Cached for 60 s because it makes a few tiny provider calls."""
    if not refresh and _diag_cache["v"] and time.time() - _diag_cache["t"] < 60:
        return _diag_cache["v"]
    from .clients import brightdata as bd, gemini, scholarly as oa
    from .clients.brightdata import UnlockerClient

    def db():
        r = one("SELECT (SELECT count(*) FROM pg_extension WHERE extname='vector') AS vec, "
                "(SELECT count(*) FROM information_schema.tables WHERE table_name IN ('workspaces','papers','claims','claim_edges','paper_scores','flags','fetch_cache','chat_messages','impact_reports')) AS tables")
        if not r["vec"]:
            raise RuntimeError("pgvector extension is not installed (run: CREATE EXTENSION vector;)")
        if r["tables"] < 9:
            raise RuntimeError(f"only {r['tables']}/9 tables exist; schema not applied")
        return "connected, pgvector present, 9/9 tables"

    def gen():
        if not C.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY not set")
        try:
            out = gemini.generate_json('Return JSON {"ok": true}')
        except Exception as e:
            raise RuntimeError(gemini.explain(e))
        return f"{C.GEMINI_MODEL} responded ({out})"

    def emb():
        if not C.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY not set")
        try:
            v = gemini.embed(["test"])[0]
        except Exception as e:
            raise RuntimeError(gemini.explain(e))
        if len(v) != 768:
            raise RuntimeError(f"got {len(v)} dims; schema needs 768")
        return f"{C.GEMINI_EMBED_MODEL}: {len(v)} dims"

    def alex():
        hits = oa.search_works("intelligent tutoring systems", 2)
        if not hits:
            raise RuntimeError("OpenAlex returned no results")
        return f"{len(hits)} results" + ("" if C.OPENALEX_API_KEY else " (no OPENALEX_API_KEY set)")

    def unl():
        if not (C.BRIGHT_DATA_API_KEY and C.BRIGHT_DATA_UNLOCKER_ZONE):
            raise RuntimeError("not configured (optional: Scholar lane and publisher full text are skipped)")
        bd.reset_fatal()
        text = UnlockerClient().fetch_text("https://arxiv.org/abs/1706.03762")
        return f"fetched {len(text)} chars via zone '{C.BRIGHT_DATA_UNLOCKER_ZONE}'"

    out = {
        "config_problems": C.config_problems(),
        "mode": "inline-thread" if C.RUN_INLINE else "redis-queue",
        "models": {"generate": C.GEMINI_MODEL, "verify": C.GEMINI_VERIFY_MODEL, "embed": C.GEMINI_EMBED_MODEL},
        "limits": {"max_papers": C.MAX_PAPERS, "max_pairs": C.MAX_PAIRS, "concurrency": C.WORKERS},
        "checks": {"database": _check(db), "gemini_generate": _check(gen), "gemini_embed": _check(emb),
                   "openalex": _check(alex), "bright_data": _check(unl)},
    }
    out["ok"] = not out["config_problems"] and all(v["ok"] for k, v in out["checks"].items() if k != "bright_data")
    _diag_cache.update(t=time.time(), v=out)
    return out


_scholar_diag = {"t": 0.0}


@app.get("/diagnostics/scholar")
def diagnostics_scholar(query: str = "virtual reality education", zone: str = "", raw: bool = False, token: str = ""):
    """Fetch ONE Google Scholar results page through Bright Data and report what came back: what kind of page it was,
    how many results parsed, and a text excerpt. Use it to debug the Scholar lane, or to compare zones:
      /diagnostics/scholar?zone=<zone name>      (e.g. a SERP API zone instead of the Web Unlocker zone)
      /diagnostics/scholar?raw=true              (adds the first 3,000 characters of the HTML)
    Spends one Bright Data request; limited to one call per 20 s. If ADMIN_TOKEN is set, pass ?token=<ADMIN_TOKEN>."""
    import re as _re
    from urllib.parse import quote_plus
    from .clients import brightdata as bd
    from .clients.scholar_parse import BASE, describe, fingerprint, parse_scholar_html
    if C.ADMIN_TOKEN and token != C.ADMIN_TOKEN:
        raise HTTPException(403, "Pass ?token=<ADMIN_TOKEN>.")
    if not (C.BRIGHT_DATA_API_KEY and (zone or C.BRIGHT_DATA_SCHOLAR_ZONE or C.BRIGHT_DATA_UNLOCKER_ZONE)):
        raise HTTPException(400, "Bright Data is not configured (BRIGHT_DATA_API_KEY and a zone).")
    if zone and not _re.fullmatch(r"[A-Za-z0-9_-]{1,64}", zone):
        raise HTTPException(400, "Zone names contain only letters, digits, _ and -.")
    if time.time() - _scholar_diag["t"] < 20:
        raise HTTPException(429, "Wait 20 seconds between Scholar diagnostics.")
    _scholar_diag["t"] = time.time()
    use_zone = zone or C.BRIGHT_DATA_SCHOLAR_ZONE or C.BRIGHT_DATA_UNLOCKER_ZONE
    url = f"{BASE}scholar?q={quote_plus(query[:200])}&hl=en&gl=us&as_sdt=0,5&as_vis=1&num=10"
    bd.reset_fatal()
    t0 = time.time()
    try:
        html = bd._unlock(url, use_zone).text
    except Exception as e:
        return {"ok": False, "zone": use_zone, "error": f"{type(e).__name__}: {str(e)[:400]}"}
    items = parse_scholar_html(html)
    fp = fingerprint(html)
    out = {"ok": bool(items), "zone": use_zone, "seconds": round(time.time() - t0, 1), "parsed_results": len(items),
           "summary": describe(fp), "fingerprint": fp, "first_titles": [i["title"] for i in items[:3]]}
    if raw:
        out["html_head"] = html[:3000]
    return out


@app.post("/workspaces/{ws}/retry")
def retry_workspace(ws: str):
    """Resume a failed/interrupted investigation. Completed stages are reused where the pipeline is idempotent."""
    w = _need(one("SELECT status FROM workspaces WHERE id=%s", (ws,)))
    if w["status"] not in ("error",):
        raise HTTPException(409, f"Workspace is '{w['status']}', not failed.")
    q("UPDATE workspaces SET status='queued', error=NULL WHERE id=%s", (ws,))
    enqueue("run_workspace_job", ws)
    return {"id": ws, "status": "queued"}


@app.get("/workspaces")
def list_workspaces():
    if not C.PUBLIC_WORKSPACE_LIST:
        raise HTTPException(403, "Workspace listing is disabled until authentication is configured.")
    return q("SELECT id, question, status, created_at FROM workspaces ORDER BY created_at DESC LIMIT 20")


@app.post("/workspaces")
async def create_workspace(question: str = Form(...), fresh: bool = Form(False), files: list[UploadFile] = File(default=[])):
    question = question.strip()
    if len(question) < 8:
        raise HTTPException(400, "Enter a research question of at least a few words.")
    blobs = [(f.filename, await _read_pdf(f)) for f in files]
    ws = one("INSERT INTO workspaces (question, question_key, progress) VALUES (%s,%s,%s::jsonb) RETURNING id",
             (question, question_key(question), json.dumps({"fresh": bool(fresh)})))["id"]
    for name, data in blobs:
        stages.ingest_upload(ws, name, data)
    try:
        enqueue("run_workspace_job", ws)
    except Exception as exc:
        logging.exception("Could not enqueue research job")
        q("UPDATE workspaces SET status='error', error=%s WHERE id=%s", ("Task queue unavailable. Check REDIS_URL and your Render Redis service.", ws))
        raise HTTPException(503, "Could not queue the investigation. Check the Render Redis service and REDIS_URL.") from exc
    return {"id": str(ws)}


@app.get("/workspaces/{ws}/status")
def status(ws: str):
    result = _need(G.status(ws))
    if result.get("status") == "queued":
        created = result.get("created_at")
        seconds = (datetime.now(timezone.utc) - created).total_seconds() if created else 0
        # Diagnostics are best-effort: Redis errors should not suppress workspace status.
        diagnostics = {"stalled": False}
        if seconds >= 30 and not C.RUN_INLINE:
            try:
                from redis import Redis
                from rq import Worker
                conn = Redis.from_url(C.REDIS_URL, socket_connect_timeout=2, socket_timeout=2)
                running_workers = len(Worker.all(connection=conn))
                if running_workers == 0:
                    diagnostics = {"stalled": True, "message": "No active RQ worker is connected to Redis. Start a Render Background Worker listening on the researchlens queue."}
            except Exception:
                diagnostics = {"stalled": True, "message": "The backend cannot check Redis. Confirm REDIS_URL points to the same private Redis instance used by your Render worker."}
        if seconds >= 120 and not C.RUN_INLINE:
            diagnostics.setdefault("message", "This job has been queued for over two minutes. Check the worker logs and confirm both services use the same REDIS_URL.")
            diagnostics["stalled"] = True
        result["queue"] = diagnostics
    return result


@app.get("/workspaces/{ws}/graph")
def graph(ws: str):
    _need(one("SELECT 1 AS x FROM workspaces WHERE id=%s", (ws,)))
    return G.graph(ws)


@app.get("/workspaces/{ws}/flags")
def flags(ws: str):
    return G.flags(ws)


@app.get("/papers/{pid}")
def paper(pid: str):
    return _need(G.paper_detail(pid))


@app.get("/edges/{eid}")
def edge(eid: str):
    return _need(G.edge_detail(eid))


@app.post("/workspaces/{ws}/papers")
async def add_paper(ws: str, file: UploadFile = File(...)):
    _need(one("SELECT 1 AS x FROM workspaces WHERE id=%s", (ws,)))
    pid = stages.ingest_upload(ws, file.filename, await _read_pdf(file), is_new=True)
    try:
        enqueue("run_new_paper_job", ws, pid)
    except Exception as exc:
        logging.exception("Could not enqueue new paper analysis")
        raise HTTPException(503, "Cannot queue the paper analysis. Check REDIS_URL and your background worker.") from exc
    return {"paper_id": str(pid)}


@app.get("/workspaces/{ws}/impact/{pid}")
def impact(ws: str, pid: str):
    r = one("SELECT report, summary FROM impact_reports WHERE paper_id=%s", (pid,))
    return _need(r, "No impact report yet")


@app.post("/workspaces/{ws}/chat")
def chat(ws: str, body: ChatIn):
    if not body.question.strip():
        raise HTTPException(400, "Ask a question.")
    return chat_mod.answer(ws, body.question.strip())
