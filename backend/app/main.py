import logging
from datetime import datetime, timezone

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from . import config as C
from .db import one, q
from .jobs import enqueue
from .pipeline import chat as chat_mod
from .pipeline import graph as G
from .pipeline import stages
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
app = FastAPI(title="ResearchLens API")
app.add_middleware(CORSMiddleware, allow_origins=C.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])
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


@app.get("/workspaces")
def list_workspaces():
    if not C.PUBLIC_WORKSPACE_LIST:
        raise HTTPException(403, "Workspace listing is disabled until authentication is configured.")
    return q("SELECT id, question, status, created_at FROM workspaces ORDER BY created_at DESC LIMIT 20")


@app.post("/workspaces")
async def create_workspace(question: str = Form(...), files: list[UploadFile] = File(default=[])):
    question = question.strip()
    if len(question) < 8:
        raise HTTPException(400, "Enter a research question of at least a few words.")
    blobs = [(f.filename, await _read_pdf(f)) for f in files]
    ws = one("INSERT INTO workspaces (question) VALUES (%s) RETURNING id", (question,))["id"]
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
