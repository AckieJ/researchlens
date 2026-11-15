"""Stage 10: evaluate a newly uploaded paper against the existing evidence graph."""
import json
import logging
import traceback

from .. import config as C
from ..clients import gemini
from ..db import ex, one, q
from . import prompts, stages

log = logging.getLogger("researchlens")

IMPACT = {"supports_compatible": "strengthens", "genuine_contradiction": "challenges",
          "apparent_contradiction": "qualifies", "related_not_comparable": "leaves_unanswered", "unresolved": "leaves_unanswered"}


def run_new_paper(ws, pid):
    try:
        stages.set_status(ws, "evaluating")
        p = one("SELECT * FROM papers WHERE id=%s", (pid,))
        stages.embed_papers(ws)
        stages.extract_paper(p)
        stages.embed_claims(ws)
        stages.verify_pairs(ws, stages.match(ws, only=[pid]))
        mine = [str(r["id"]) for r in q("SELECT id FROM claims WHERE paper_id=%s", (pid,))]
        items, linked = [], set()
        for e in (q("SELECT e.id, e.claim_a, e.claim_b, e.label, e.confidence, e.reason FROM claim_edges e "
                    "WHERE e.claim_a = ANY(%s::uuid[]) OR e.claim_b = ANY(%s::uuid[])", (mine, mine)) if mine else []):
            new_id, old_id = (e["claim_a"], e["claim_b"]) if str(e["claim_a"]) in mine else (e["claim_b"], e["claim_a"])
            imp = IMPACT.get(e["label"], "leaves_unanswered")
            ex("UPDATE claim_edges SET impact=%s WHERE id=%s", (imp, e["id"]))
            linked.add(str(new_id))
            n = one("SELECT claim_text, quote FROM claims WHERE id=%s", (new_id,))
            o = one("SELECT c.claim_text, c.quote, p.id AS paper_id, p.title FROM claims c JOIN papers p ON p.id=c.paper_id WHERE c.id=%s", (old_id,))
            items.append({"edge_id": str(e["id"]), "impact": imp, "label": e["label"], "confidence": e["confidence"], "reason": e["reason"],
                          "new_claim": n, "prior_claim": {**o, "paper_id": str(o["paper_id"])}})
        none = [r for r in q("SELECT id, claim_text, quote FROM claims WHERE paper_id=%s", (pid,)) if str(r["id"]) not in linked]
        counts = {}
        for i in items:
            counts[i["impact"]] = counts.get(i["impact"], 0) + 1
        title = p["title"]
        try:
            summary = gemini.generate_json(prompts.impact_summary(title, items)).get("summary", "")
        except Exception:
            summary = ""
        report = {"items": items, "no_prior_match": [{"claim_text": r["claim_text"], "quote": r["quote"]} for r in none], "counts": counts}
        ex("INSERT INTO impact_reports (paper_id, workspace_id, report, summary) VALUES (%s,%s,%s::jsonb,%s) "
           "ON CONFLICT (paper_id) DO UPDATE SET report=EXCLUDED.report, summary=EXCLUDED.summary",
           (pid, ws, json.dumps(report, default=str), summary))
        stages.external_check(ws)
        stages.build_flags(ws)
        stages.compute_layout(ws)
        stages.set_status(ws, "done")
    except Exception as e:
        log.error("impact run failed\n%s", traceback.format_exc())
        stages.set_status(ws, "error", str(e))
