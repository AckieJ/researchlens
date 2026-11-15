import logging

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
    enqueue("run_workspace_job", ws)
    return {"id": str(ws)}


@app.get("/workspaces/{ws}/status")
def status(ws: str):
    return _need(G.status(ws))


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
    enqueue("run_new_paper_job", ws, pid)
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
