"""RQ job entry points. Start a worker with:  rq worker researchlens --url $REDIS_URL"""
from .pipeline import impact, stages


def run_workspace_job(ws_id):
    stages.run_workspace(ws_id)


def run_new_paper_job(ws_id, paper_id):
    impact.run_new_paper(ws_id, paper_id)
