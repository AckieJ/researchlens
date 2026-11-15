"""Stages 0-9: understand, discover, retrieve, extract, match, verify, flag, layout."""
import difflib
import json
import logging
import re
import traceback
from concurrent.futures import ThreadPoolExecutor

from .. import config as C
from ..clients import gemini, scholarly as oa
from ..clients.allowlist import allowed
from ..clients.brightdata import ScholarClient, UnlockerClient
from ..db import ex, one, q, vec
from . import prompts
from .dedupe import dedupe
from .layout import assign_angles, child_angles, evidence_strength, minmax, relevance
from .text import comparability, find_doi, guess_title, jaccard, locate, normalize, passage, pdf_to_text, quote_ok

log = logging.getLogger("researchlens")

CLAIM_COLS = ("c.id,c.paper_id,c.workspace_id,c.claim_text,c.intervention,c.outcome,c.outcome_family,c.direction,"
              "c.significance,c.effect_size,c.population,c.sample_n,c.design,c.duration,c.measure,c.limitations,"
              "c.quote,c.location")
CLAIM_Q = (f"SELECT {CLAIM_COLS}, p.title AS p_title, p.year AS p_year, p.text_level, p.full_text "
           "FROM claims c JOIN papers p ON p.id=c.paper_id WHERE c.id = ANY(%s::uuid[])")
PCOLS = ("doi", "openalex_id", "title", "year", "authors", "venue", "url", "oa_url", "license", "abstract",
         "cited_by_count", "refs", "retraction_status", "confidence")


# ---------- helpers ----------
def set_status(ws, status, error=None):
    ex("UPDATE workspaces SET status=%s, error=%s WHERE id=%s", (status, error, ws))


def progress(ws, **kv):
    ex("UPDATE workspaces SET progress = COALESCE(progress,'{}'::jsonb) || %s::jsonb WHERE id=%s", (json.dumps(kv), ws))


def pmap(fn, items):
    with ThreadPoolExecutor(C.WORKERS) as pool:
        return list(pool.map(fn, items))


def add_source(pid, lane, query):
    ex("INSERT INTO paper_sources (paper_id,lane,query) VALUES (%s,%s,%s)", (pid, lane, query))


def insert_paper(ws, c, kept=False, expanded_from=None):
    d = {k: c.get(k) for k in PCOLS}
    d["refs"] = d["refs"] or []
    d["cited_by_count"] = d["cited_by_count"] or 0
    d["retraction_status"] = d["retraction_status"] or "none"
    d["confidence"] = d["confidence"] or "high"
    cols = ",".join(PCOLS)
    row = one(f"INSERT INTO papers (workspace_id,{cols},lane,kept,expanded_from,scholar_links) "
              f"VALUES (%s,{','.join(['%s'] * len(PCOLS))},%s,%s,%s,%s::jsonb) RETURNING id",
              (ws, *[d[k] for k in PCOLS], c.get("lane"), kept, expanded_from or c.get("_seed"),
               json.dumps(c["scholar_links"]) if c.get("scholar_links") else None))
    for lane, query in c.get("sources") or [(c.get("lane"), c.get("query"))]:
        add_source(row["id"], lane, query)
    return row["id"]


# ---------- Stage 0: uploads ----------
def ingest_upload(ws, filename, content, is_new=False):
    text = pdf_to_text(content)
    meta, doi = {}, find_doi(text[:8000])
    if doi:
        try:
            meta = oa.work_by_doi(doi) or {}
        except Exception:
            log.warning("OpenAlex lookup failed for uploaded DOI %s", doi)
    c = dict(meta)
    c.update({"title": meta.get("title") or guess_title(text) or filename, "doi": doi or meta.get("doi"),
              "lane": "D", "query": filename, "confidence": "high"})
    pid = insert_paper(ws, c, kept=True)
    ex("UPDATE papers SET is_upload=true, is_new=%s, full_text=%s, text_level=%s WHERE id=%s",
       (is_new, text, "full" if len(text) >= C.FULL_TEXT_MIN else "abstract", pid))
    return pid


# ---------- Stage 1 ----------
def understand(ws):
    w = one("SELECT question FROM workspaces WHERE id=%s", (ws,))
    parsed = gemini.generate_json(prompts.understand(w["question"]))
    parsed["search_queries"] = [s for s in parsed.get("search_queries") or [] if s][:5] or [w["question"]]
    parsed["sub_questions"] = [s for s in parsed.get("sub_questions") or [] if s][:6] or [w["question"]]
    parsed["outcome_families"] = [s for s in parsed.get("outcome_families") or [] if s][:5]
    emb = gemini.embed([w["question"]])[0]
    ex("UPDATE workspaces SET parsed=%s::jsonb, embedding=%s::vector WHERE id=%s", (json.dumps(parsed), vec(emb), ws))
    return parsed


# ---------- Stage 2: discovery (Lane A APIs + Lane B Google Scholar) ----------
def resolve_scholar_item(it, lane="B", query=None):
    """Turn a Scholar result into a candidate: resolve to a DOI via OpenAlex when possible."""
    links = {"cited_by": it.get("cited_by_url"), "related": it.get("related_url")}
    w = None
    try:
        w = oa.work_by_title(it["title"], it.get("year"))
    except Exception:
        pass
    if w:
        w.update({"lane": lane, "query": query, "scholar_links": links})
        w["url"] = w.get("url") or it.get("url")
        return w
    return {"title": it["title"], "year": it.get("year"), "authors": it.get("authors"), "url": it.get("url"),
            "abstract": it.get("snippet"), "confidence": "low", "lane": lane, "query": query,
            "cited_by_count": it.get("cited_by_count", 0), "scholar_links": links}


def discover(ws, parsed):
    question = one("SELECT question FROM workspaces WHERE id=%s", (ws,))["question"]
    existing = q("SELECT id,doi,title,year FROM papers WHERE workspace_id=%s", (ws,))
    cands, warnings, scholar = [], [], ScholarClient()
    for qs in parsed["search_queries"] + [question]:
        try:
            for w in oa.search_works(qs, 25):
                w.update({"lane": "A", "query": qs})
                cands.append(w)
        except Exception as e:
            warnings.append(f"OpenAlex failed for '{qs[:40]}': {e}")
        if scholar.enabled():
            try:
                for it in scholar.search(qs, 20):
                    cands.append(resolve_scholar_item(it, "B", qs))
            except Exception as e:
                warnings.append(f"Google Scholar scraper failed for '{qs[:40]}': {e}")
    if not scholar.enabled():
        warnings.append("Google Scholar lane skipped: BRIGHT_DATA_SCHOLAR_ID / API key not set.")
    new, dups, extra = dedupe([c for c in cands if c.get("title")], existing)
    for c in new[:C.MAX_CANDIDATES]:
        insert_paper(ws, c)
    for pid, lane, query in extra:
        add_source(pid, lane, query)
    progress(ws, duplicates_removed=dups, candidates=min(len(new), C.MAX_CANDIDATES) + len(existing), warnings=warnings)


def embed_papers(ws):
    rows = q("SELECT id,title,abstract FROM papers WHERE workspace_id=%s AND embedding IS NULL", (ws,))
    for r, e in zip(rows, gemini.embed([f"{r['title']}. {r['abstract'] or ''}" for r in rows])):
        ex("UPDATE papers SET embedding=%s::vector WHERE id=%s", (vec(e), r["id"]))


def prelim_rank(ws, cap):
    """Keep uploads plus the papers most similar to the question; returns the ranked kept ids."""
    rows = q("SELECT p.id, p.is_upload, 1-(p.embedding <=> w.embedding) AS sim FROM papers p "
             "JOIN workspaces w ON w.id=p.workspace_id WHERE p.workspace_id=%s AND p.embedding IS NOT NULL "
             "ORDER BY p.is_upload DESC, sim DESC", (ws,))
    cap = max(cap, sum(1 for r in rows if r["is_upload"]))
    keep = [r["id"] for r in rows][:cap]
    ex("UPDATE papers SET kept = (id = ANY(%s::uuid[])) WHERE workspace_id=%s", ([str(k) for k in keep], ws))
    return keep


def expand(ws, keep, seeds=5):
    """Citation expansion around the top seeds -> the second ring of the graph."""
    scholar = ScholarClient()
    seed_rows = q("SELECT * FROM papers WHERE id = ANY(%s::uuid[]) AND NOT is_upload LIMIT %s", ([str(k) for k in keep[:seeds * 2]], seeds))
    cands = []
    for s in seed_rows:
        links = s.get("scholar_links") or {}
        try:
            if scholar.enabled() and any(links.values()):
                for kind, url in links.items():
                    if url:
                        for it in scholar.expand(url, 10):
                            c = resolve_scholar_item(it, "B", f"expansion:{kind}")
                            c["_seed"] = s["id"]
                            cands.append(c)
            elif s["openalex_id"]:
                for w in oa.citing(s["openalex_id"], 10):
                    w.update({"lane": "A", "query": "expansion:citing", "_seed": s["id"]})
                    cands.append(w)
        except Exception as e:
            log.warning("expansion failed for %s: %s", s["title"], e)
    existing = q("SELECT id,doi,title,year FROM papers WHERE workspace_id=%s", (ws,))
    new, dups, extra = dedupe([c for c in cands if c.get("title")], existing)
    for c in new[:60]:
        insert_paper(ws, c)
    for pid, lane, query in extra:
        add_source(pid, lane, query)
    progress(ws, expanded=len(new[:60]))


def retrieve_full_text(p):
    """Order: uploaded PDF -> Europe PMC API -> OpenAlex OA URL / result URL via Web Unlocker (allowlisted) -> abstract."""
    if p.get("full_text") and len(p["full_text"]) >= C.FULL_TEXT_MIN:
        return p["full_text"], "full"
    if p.get("doi"):
        try:
            t = oa.epmc_fulltext(p["doi"])
            if t and len(t) >= C.FULL_TEXT_MIN:
                return t, "full"
        except Exception as e:
            log.info("Europe PMC miss for %s: %s", p["doi"], e)
    unl = UnlockerClient()
    if unl.enabled():
        for u in (p.get("oa_url"), p.get("url")):
            if u and allowed(u):
                try:
                    t = unl.fetch_text(u)
                    if t and len(t) >= C.FULL_TEXT_MIN:
                        return t, "full"
                except Exception as e:
                    log.info("Unlocker miss for %s: %s", u, e)
    return (p.get("abstract") or ""), "abstract"


def retrieve_all(ws):
    rows = q("SELECT * FROM papers WHERE workspace_id=%s AND kept", (ws,))

    def work(p):
        try:
            text, level = retrieve_full_text(p)
        except Exception:
            text, level = (p.get("full_text") or p.get("abstract") or ""), "abstract"
        ex("UPDATE papers SET full_text=%s, text_level=%s WHERE id=%s", (text, level, p["id"]))

    pmap(work, rows)
    ex("UPDATE papers SET kept=false WHERE workspace_id=%s AND kept AND coalesce(length(full_text),0) < 200", (ws,))
    # Scholar-only results that never resolved to a DOI stay out of verdicts unless full text was retrieved.
    ex("UPDATE papers SET kept=false WHERE workspace_id=%s AND kept AND confidence='low' AND text_level<>'full'", (ws,))


# ---------- Stage 4: claim extraction ----------
def _enum(v, allowed_vals, default):
    v = (v or "").strip().lower()
    return v if v in allowed_vals else default


def _int(v):
    try:
        return int(re.sub(r"[^\d]", "", str(v))) if v not in (None, "") else None
    except ValueError:
        return None


def extract_paper(p):
    text = (p.get("full_text") or p.get("abstract") or "")[:C.MAX_TEXT_CHARS]
    if len(text) < 200:
        return 0, 0
    nt, level = normalize(text), p.get("text_level") or "abstract"
    prompt, valid, rejected, seen = prompts.extract(p, text, level), [], 0, set()
    for attempt in range(2):
        data = gemini.generate_json(prompt, system=prompts.EXTRACT_SYSTEM)
        for c in data.get("claims") or []:
            qt = c.get("quote") or ""
            if qt in seen:
                continue
            seen.add(qt)
            if quote_ok(qt, text, nt):                       # code-level verbatim check
                c["location"] = locate(text, qt) or c.get("location")
                valid.append(c)
            else:
                rejected += 1
        if len(valid) >= 3:
            break
        prompt += "\n\nREMINDER: every quote must be copied exactly from the text above. Retry with exact quotes."
    for c in valid[:6]:
        ex("INSERT INTO claims (workspace_id,paper_id,claim_text,intervention,outcome,outcome_family,direction,significance,"
           "effect_size,population,sample_n,design,duration,measure,limitations,quote,location) "
           "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
           (p["workspace_id"], p["id"], c.get("claim_text"), c.get("intervention"), c.get("outcome"),
            c.get("outcome_family"), _enum(c.get("direction"), ("increase", "decrease", "no_effect", "mixed"), "mixed"),
            _enum(c.get("significance"), ("significant", "not_significant", "not_reported"), "not_reported"),
            c.get("effect_size"), c.get("population"), _int(c.get("sample_n")), c.get("design"), c.get("duration"),
            c.get("measure"), c.get("limitations"), c.get("quote"), c.get("location")))
    return len(valid[:6]), rejected


def embed_claims(ws):
    rows = q("SELECT id,claim_text,outcome FROM claims WHERE workspace_id=%s AND embedding IS NULL", (ws,))
    for r, e in zip(rows, gemini.embed([f"{r['claim_text']} (outcome: {r['outcome']})" for r in rows])):
        ex("UPDATE claims SET embedding=%s::vector WHERE id=%s", (vec(e), r["id"]))


def extract_all(ws):
    papers = q("SELECT * FROM papers WHERE workspace_id=%s AND kept AND NOT EXISTS "
               "(SELECT 1 FROM claims c WHERE c.paper_id=papers.id)", (ws,))

    def work(p):
        try:
            return extract_paper(p)
        except Exception:
            log.error("extraction failed for %s\n%s", p["title"], traceback.format_exc())
            return 0, 0

    res = pmap(work, papers)
    progress(ws, claims_extracted=sum(r[0] for r in res), claims_rejected=sum(r[1] for r in res))
    embed_claims(ws)


# ---------- Stage 6: match claims before comparing ----------
MATCH_SQL = """
SELECT a.id AS a_id, b.id AS b_id, 1-(a.embedding <=> b.embedding) AS sim
FROM claims a JOIN claims b ON a.id < b.id AND a.paper_id <> b.paper_id
JOIN papers pa ON pa.id=a.paper_id JOIN papers pb ON pb.id=b.paper_id
WHERE pa.workspace_id=%(ws)s AND pb.workspace_id=%(ws)s AND pa.kept AND pb.kept
  AND a.embedding IS NOT NULL AND b.embedding IS NOT NULL
  AND (%(only)s::uuid[] IS NULL OR a.paper_id = ANY(%(only)s::uuid[]) OR b.paper_id = ANY(%(only)s::uuid[]))
  AND 1-(a.embedding <=> b.embedding) >= %(th)s
  AND (lower(coalesce(a.outcome_family,'')) = lower(coalesce(b.outcome_family,'')) OR 1-(a.embedding <=> b.embedding) >= %(strong)s)
  AND NOT EXISTS (SELECT 1 FROM claim_edges e WHERE e.claim_a=a.id AND e.claim_b=b.id)
ORDER BY sim DESC LIMIT %(lim)s
"""


def match(ws, only=None):
    return q(MATCH_SQL, {"ws": ws, "only": [str(x) for x in only] if only else None, "th": C.MATCH_THRESHOLD,
                         "strong": C.STRONG_MATCH, "lim": C.MAX_PAIRS})


# ---------- Stage 7: verify relationships ----------
def verify_one(ws, a, b, pair):
    comp = comparability(a, b)
    pa, pb = passage(a["full_text"] or "", a["quote"]), passage(b["full_text"] or "", b["quote"])
    d = gemini.generate_json(prompts.verify(a, b, comp, pa, pb), system=prompts.VERIFY_SYSTEM, model=C.GEMINI_VERIFY_MODEL)
    label = d.get("label") if d.get("label") in prompts.LABELS else "unresolved"
    try:
        conf = max(0.0, min(1.0, float(d.get("confidence", 0.5))))
    except (TypeError, ValueError):
        conf = 0.5
    reason = d.get("reason") or ""
    if "abstract" in (a["text_level"], b["text_level"]):
        conf = min(conf, 0.6)                                  # abstract-only evidence caps confidence
    if label == "genuine_contradiction":                       # second self-check pass
        chk = gemini.generate_json(prompts.selfcheck(a, b, d), system=prompts.VERIFY_SYSTEM, model=C.GEMINI_VERIFY_MODEL)
        if not chk.get("confirm"):
            label = chk.get("downgrade_to") if chk.get("downgrade_to") in ("apparent_contradiction", "unresolved") else "apparent_contradiction"
            conf, reason = min(conf, 0.6), (reason + " " + (chk.get("note") or "")).strip()
    row = one("INSERT INTO claim_edges (workspace_id,claim_a,claim_b,label,factors,confidence,reason,quotes,sim,comparability) "
              "VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s::jsonb) ON CONFLICT DO NOTHING RETURNING id",
              (ws, a["id"], b["id"], label, [str(f) for f in d.get("factors") or []], conf, reason,
               json.dumps({"a": a["quote"], "b": b["quote"]}), float(pair["sim"]), json.dumps(comp)))
    return row["id"] if row else None


def verify_pairs(ws, pairs):
    ids = list({str(x) for p in pairs for x in (p["a_id"], p["b_id"])})
    if not ids:
        return []
    claims = {str(r["id"]): r for r in q(CLAIM_Q, (ids,))}

    def work(p):
        try:
            return verify_one(ws, claims[str(p["a_id"])], claims[str(p["b_id"])], p)
        except Exception:
            log.error("verification failed\n%s", traceback.format_exc())
            return None

    out = pmap(work, pairs)
    progress(ws, pairs_verified=len([o for o in out if o]))
    return [o for o in out if o]


# ---------- Stage 8: flags and gaps (three separate lists) ----------
def build_flags(ws):
    ex("DELETE FROM flags WHERE workspace_id=%s", (ws,))
    seen = set()
    # (1) limitations / future work stated by the authors
    for r in q("SELECT c.id, c.limitations FROM claims c JOIN papers p ON p.id=c.paper_id "
               "WHERE c.workspace_id=%s AND p.kept AND coalesce(c.limitations,'') <> ''", (ws,)):
        key = normalize(r["limitations"])
        if key in seen or key in ("not_reported", "none"):
            continue
        seen.add(key)
        ex("INSERT INTO flags (workspace_id,kind,description,claim_ids) VALUES (%s,'limitation',%s,%s::uuid[])",
           (ws, r["limitations"], [str(r["id"])]))
    # (2) weakly supported claims: abstract-only or small sample, with no compatible support from another paper
    for r in q("SELECT c.id, c.claim_text, c.sample_n, p.text_level, p.title FROM claims c JOIN papers p ON p.id=c.paper_id "
               "WHERE c.workspace_id=%s AND p.kept AND (p.text_level='abstract' OR coalesce(c.sample_n,1000) < 30) "
               "AND NOT EXISTS (SELECT 1 FROM claim_edges e WHERE e.label='supports_compatible' AND (e.claim_a=c.id OR e.claim_b=c.id))", (ws,)):
        why = "abstract only" if r["text_level"] == "abstract" else f"small sample (n={r['sample_n']})"
        ex("INSERT INTO flags (workspace_id,kind,description,claim_ids) VALUES (%s,'weak_claim',%s,%s::uuid[])",
           (ws, f"{r['claim_text']} ({why}; no compatible support found in this library)", [str(r["id"])]))
    for r in q("SELECT id,title,retraction_status FROM papers WHERE workspace_id=%s AND kept AND retraction_status<>'none'", (ws,)):
        ex("INSERT INTO flags (workspace_id,kind,description) VALUES (%s,'retraction',%s)",
           (ws, f"{r['title']} has a {r['retraction_status']} notice. Treat its claims with caution."))
    # (3) topics unrepresented in THIS library (never a claim about all research)
    w = one("SELECT parsed FROM workspaces WHERE id=%s", (ws,))
    subs = (w["parsed"] or {}).get("sub_questions") or []
    if subs:
        for sq, e in zip(subs, gemini.embed(subs)):
            r = one("SELECT count(DISTINCT c.paper_id) AS n FROM claims c JOIN papers p ON p.id=c.paper_id "
                    "WHERE c.workspace_id=%s AND p.kept AND c.embedding IS NOT NULL AND 1-(c.embedding <=> %s::vector) >= 0.68", (ws, vec(e)))
            if r["n"] < 2:
                ex("INSERT INTO flags (workspace_id,kind,description) VALUES (%s,'library_gap',%s)",
                   (ws, f"Not found in the papers examined: {sq} ({r['n']} paper(s) clearly address it)."))


def external_check(ws):
    """Crossref update notices for papers that sit on a contradiction edge."""
    rows = q("SELECT DISTINCT p.id, p.doi FROM papers p JOIN claims c ON c.paper_id=p.id JOIN claim_edges e ON (e.claim_a=c.id OR e.claim_b=c.id) "
             "WHERE p.workspace_id=%s AND p.doi IS NOT NULL AND e.label IN ('genuine_contradiction','apparent_contradiction') "
             "AND p.retraction_status='none'", (ws,))
    for r in rows:
        try:
            types = oa.crossref_updates(r["doi"])
        except Exception:
            continue
        status = next((s for k, s in (("retract", "retracted"), ("correct", "corrected"), ("concern", "concern")) if any(k in t for t in types)), None)
        if status:
            ex("UPDATE papers SET retraction_status=%s WHERE id=%s", (status, r["id"]))


# ---------- Stage 9: relevance and layout ----------
def _outcome_match(fams, outcomes):
    if not fams or not outcomes:
        return 0.0
    hits = sum(1 for o in outcomes if any(jaccard(o, f) >= 0.3 or difflib.SequenceMatcher(None, o.lower(), f.lower()).ratio() >= 0.6 for f in fams))
    return hits / len(outcomes)


def compute_layout(ws):
    w = one("SELECT parsed FROM workspaces WHERE id=%s", (ws,))
    parsed = w["parsed"] or {}
    papers = q("SELECT id, openalex_id, refs, text_level, expanded_from FROM papers WHERE workspace_id=%s AND kept", (ws,))
    if not papers:
        return
    ids = [p["id"] for p in papers]
    cos = {r["paper_id"]: r["s"] for r in q(
        "SELECT paper_id, avg(sim) AS s FROM (SELECT c.paper_id, 1-(c.embedding <=> w.embedding) AS sim, "
        "row_number() OVER (PARTITION BY c.paper_id ORDER BY c.embedding <=> w.embedding) AS rn FROM claims c "
        "JOIN workspaces w ON w.id=c.workspace_id WHERE c.workspace_id=%s AND c.embedding IS NOT NULL) t WHERE rn<=3 GROUP BY paper_id", (ws,))}
    claims = q("SELECT paper_id, outcome_family, design, sample_n FROM claims WHERE workspace_id=%s", (ws,))
    by_paper = {i: [c for c in claims if c["paper_id"] == i] for i in ids}
    oa_ids = {p["openalex_id"] for p in papers if p["openalex_id"]}
    cited_in = {}
    for p in papers:
        for r in set(p["refs"] or []) & oa_ids:
            cited_in[r] = cited_in.get(r, 0) + 1
    cos_n = minmax([float(cos.get(i, 0.0)) for i in ids])
    cent_raw = [cited_in.get(p["openalex_id"], 0) + len(set(p["refs"] or []) & oa_ids) for p in papers]
    cent_n = minmax([float(x) for x in cent_raw]) if any(cent_raw) else [0.0] * len(ids)
    rel = {}
    for k, p in enumerate(papers):
        cl = by_paper[p["id"]]
        om = _outcome_match(parsed.get("outcome_families") or [], [c["outcome_family"] or "" for c in cl])
        es = sum(evidence_strength(c["design"], c["sample_n"], p["text_level"]) for c in cl) / len(cl) if cl else 0.0
        rel[p["id"]] = relevance(cos_n[k], om, cent_n[k], es)
    # sectors = sub-questions
    subs = parsed.get("sub_questions") or [""]
    sector_sim = {i: [0.0] * len(subs) for i in ids}
    for s, e in enumerate(gemini.embed(subs)):
        for r in q("SELECT paper_id, max(1-(embedding <=> %s::vector)) AS s FROM claims WHERE workspace_id=%s AND embedding IS NOT NULL GROUP BY paper_id", (vec(e), ws)):
            if r["paper_id"] in sector_sim:
                sector_sim[r["paper_id"]][s] = float(r["s"])
    sector = {i: max(range(len(subs)), key=lambda s: sector_sim[i][s]) for i in ids}
    kept_ids = set(ids)
    first = [p for p in papers if not (p["expanded_from"] and p["expanded_from"] in kept_ids)]
    groups = {}
    for p in sorted(first, key=lambda p: -rel[p["id"]]):
        groups.setdefault(sector[p["id"]], []).append(p["id"])
    angle = assign_angles(groups, len(subs))
    parent = {}
    kids = {}
    for p in papers:
        if p["expanded_from"] and p["expanded_from"] in kept_ids:
            kids.setdefault(p["expanded_from"], []).append(p["id"])
    for par, ch in kids.items():
        base = angle.get(par, 0.0)
        for cid, a in zip(sorted(ch, key=lambda i: -rel[i]), child_angles(base, len(ch))):
            angle[cid], parent[cid], sector[cid] = a, par, sector.get(par, sector[cid])
    ex("DELETE FROM paper_scores WHERE workspace_id=%s", (ws,))
    for i in ids:
        ex("INSERT INTO paper_scores (workspace_id,paper_id,relevance,sector,angle,parent_paper) VALUES (%s,%s,%s,%s,%s,%s)",
           (ws, i, rel[i], sector[i], angle.get(i, 0.0), parent.get(i)))


# ---------- orchestration ----------
def run_workspace(ws):
    try:
        set_status(ws, "understanding")
        parsed = understand(ws)
        set_status(ws, "discovering")
        discover(ws, parsed)
        set_status(ws, "retrieving")
        embed_papers(ws)
        keep = prelim_rank(ws, C.MAX_PAPERS)
        expand(ws, keep)
        embed_papers(ws)
        prelim_rank(ws, C.MAX_PAPERS)
        retrieve_all(ws)
        set_status(ws, "extracting")
        extract_all(ws)
        set_status(ws, "matching")
        pairs = match(ws)
        progress(ws, candidate_pairs=len(pairs))
        set_status(ws, "verifying")
        verify_pairs(ws, pairs)
        external_check(ws)
        set_status(ws, "flagging")
        build_flags(ws)
        set_status(ws, "layout")
        compute_layout(ws)
        set_status(ws, "done")
    except Exception as e:
        log.error("workspace %s failed\n%s", ws, traceback.format_exc())
        set_status(ws, "error", str(e))
