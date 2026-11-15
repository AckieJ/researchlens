"""Read models for the API: graph, edge detail, paper detail, flags, status."""
from ..db import one, q
from .layout import radius

PRIORITY = ["genuine_contradiction", "apparent_contradiction", "unresolved", "supports_compatible", "related_not_comparable"]
STAGES = ["queued", "understanding", "discovering", "retrieving", "extracting", "matching", "verifying", "flagging", "layout", "done"]


def status(ws):
    w = one("SELECT id, question, status, progress, error, created_at FROM workspaces WHERE id=%s", (ws,))
    if not w:
        return None
    c = one("SELECT count(*) AS total, count(*) FILTER (WHERE kept) AS kept, "
            "count(*) FILTER (WHERE kept AND text_level='full') AS full_text, "
            "count(*) FILTER (WHERE kept AND text_level='abstract') AS abstract_only FROM papers WHERE workspace_id=%s", (ws,))
    lanes = {r["lane"]: r["n"] for r in q("SELECT s.lane, count(DISTINCT s.paper_id) AS n FROM paper_sources s "
                                          "JOIN papers p ON p.id=s.paper_id WHERE p.workspace_id=%s GROUP BY s.lane", (ws,))}
    nclaims = one("SELECT count(*) AS n FROM claims WHERE workspace_id=%s", (ws,))["n"]
    edges = {r["label"]: r["n"] for r in q("SELECT label, count(*) AS n FROM claim_edges WHERE workspace_id=%s GROUP BY label", (ws,))}
    return {**w, "stages": STAGES, "counts": {**c, "claims": nclaims, "lanes": lanes, "edges": edges}}


def graph(ws):
    w = one("SELECT question, parsed FROM workspaces WHERE id=%s", (ws,))
    papers = q("SELECT p.id, p.title, p.year, p.doi, p.url, p.text_level, p.retraction_status, p.is_new, p.is_upload, p.lane, "
               "p.confidence, s.relevance, s.sector, s.angle, s.parent_paper, "
               "(SELECT count(*) FROM claims c WHERE c.paper_id=p.id) AS n_claims "
               "FROM papers p JOIN paper_scores s ON s.paper_id=p.id WHERE p.workspace_id=%s AND p.kept", (ws,))
    for p in papers:
        p["radius"] = radius(p["relevance"])
    rows = q("SELECT e.id, e.label, e.confidence, ca.paper_id AS pa, cb.paper_id AS pb FROM claim_edges e "
             "JOIN claims ca ON ca.id=e.claim_a JOIN claims cb ON cb.id=e.claim_b WHERE e.workspace_id=%s", (ws,))
    agg = {}
    for r in rows:
        key = tuple(sorted((str(r["pa"]), str(r["pb"]))))
        a = agg.setdefault(key, {"source": key[0], "target": key[1], "counts": {}, "top": {}})
        a["counts"][r["label"]] = a["counts"].get(r["label"], 0) + 1
        best = a["top"].get(r["label"])
        if not best or (r["confidence"] or 0) > best[1]:
            a["top"][r["label"]] = (str(r["id"]), r["confidence"] or 0)
    edges = []
    for a in agg.values():
        label = next(l for l in PRIORITY if l in a["counts"])
        edges.append({"source": a["source"], "target": a["target"], "label": label, "counts": a["counts"],
                      "top_edge_id": a["top"][label][0]})
    parsed = w["parsed"] or {}
    return {"question": w["question"], "sub_questions": parsed.get("sub_questions") or [], "rings": [0.8, 0.6, 0.4, 0.2],
            "papers": papers, "edges": edges}


def _claim_view(c):
    return {k: c[k] for k in ("id", "claim_text", "intervention", "outcome", "direction", "significance", "effect_size",
                              "population", "sample_n", "design", "duration", "measure", "limitations", "quote", "location")} | {
        "paper": {"id": c["paper_id"], "title": c["p_title"], "year": c["p_year"], "doi": c["p_doi"], "url": c["p_url"],
                  "text_level": c["text_level"], "retraction_status": c["retraction_status"]}}


CLAIM_JOIN = ("SELECT c.id,c.paper_id,c.claim_text,c.intervention,c.outcome,c.direction,c.significance,c.effect_size,c.population,"
              "c.sample_n,c.design,c.duration,c.measure,c.limitations,c.quote,c.location,p.title AS p_title,p.year AS p_year,"
              "p.doi AS p_doi,p.url AS p_url,p.text_level,p.retraction_status FROM claims c JOIN papers p ON p.id=c.paper_id ")


def edge_detail(eid):
    e = one("SELECT id, claim_a, claim_b, label, factors, confidence, reason, quotes, sim, comparability, impact FROM claim_edges WHERE id=%s", (eid,))
    if not e:
        return None
    a = _claim_view(one(CLAIM_JOIN + "WHERE c.id=%s", (e["claim_a"],)))
    b = _claim_view(one(CLAIM_JOIN + "WHERE c.id=%s", (e["claim_b"],)))
    return {**{k: e[k] for k in ("id", "label", "factors", "confidence", "reason", "quotes", "sim", "comparability", "impact")},
            "claim_a": a, "claim_b": b}


def paper_detail(pid):
    p = one("SELECT p.id, p.workspace_id, p.title, p.year, p.authors, p.venue, p.doi, p.url, p.oa_url, p.license, p.text_level, "
            "p.retraction_status, p.confidence, p.is_new, s.relevance FROM papers p LEFT JOIN paper_scores s ON s.paper_id=p.id WHERE p.id=%s", (pid,))
    if not p:
        return None
    claims = q(CLAIM_JOIN + "WHERE c.paper_id=%s ORDER BY c.location", (pid,))
    out = []
    for c in claims:
        edges = q("SELECT e.id, e.label, e.confidence, e.impact, o.p_title AS other_title, o.id AS other_claim FROM claim_edges e "
                  "JOIN (SELECT c2.id, p2.title AS p_title FROM claims c2 JOIN papers p2 ON p2.id=c2.paper_id) o "
                  "ON o.id = CASE WHEN e.claim_a=%s THEN e.claim_b ELSE e.claim_a END WHERE e.claim_a=%s OR e.claim_b=%s", (c["id"], c["id"], c["id"]))
        out.append({**_claim_view(c), "edges": edges})
    return {**p, "claims": out}


def flags(ws):
    rows = q("SELECT id, kind, description, claim_ids FROM flags WHERE workspace_id=%s ORDER BY kind", (ws,))
    for r in rows:
        ids = [str(i) for i in (r["claim_ids"] or [])][:3]
        r["evidence"] = [{"paper": x["title"], "quote": x["quote"], "location": x["location"], "paper_id": x["paper_id"]} for x in
                         (q("SELECT p.title, p.id AS paper_id, c.quote, c.location FROM claims c JOIN papers p ON p.id=c.paper_id WHERE c.id = ANY(%s::uuid[])", (ids,)) if ids else [])]
        r.pop("claim_ids", None)
    return {"limitations": [r for r in rows if r["kind"] == "limitation"],
            "weak_claims": [r for r in rows if r["kind"] in ("weak_claim", "retraction")],
            "library_gaps": [r for r in rows if r["kind"] == "library_gap"]}
