"""Stages 0-9: understand, discover, retrieve, extract, match, verify, flag, layout."""
import difflib
import json
import logging
import re
import time
import traceback
from concurrent.futures import ThreadPoolExecutor

from .. import config as C
from ..clients import gemini, scholarly as oa
from ..clients.allowlist import allowed
from ..clients import brightdata as bd
from ..clients.brightdata import ScholarBlocked, ScholarClient, UnlockerClient
from ..db import ex, exmany, one, pool, q, vec
from . import prompts
from .dedupe import dedupe
from .layout import assign_angles, child_angles, evidence_strength, minmax, relevance
from .text import comparability, find_doi, focus_text, guess_title, jaccard, locate, normalize, passage, pdf_to_text, quote_ok

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


def _warn(ws, msg):
    """Append a warning shown on the progress screen."""
    ex("UPDATE workspaces SET progress = jsonb_set(COALESCE(progress,'{}'::jsonb), '{warnings}', "
       "COALESCE(progress->'warnings','[]'::jsonb) || to_jsonb(%s::text)) WHERE id=%s", (msg, ws))


def pmap(fn, items, workers=None):
    with ThreadPoolExecutor(workers or C.WORKERS) as pool:
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
    exmany("INSERT INTO paper_sources (paper_id,lane,query) VALUES (%s,%s,%s)",
           [(row["id"], lane, query) for lane, query in c.get("sources") or [(c.get("lane"), c.get("query"))]])
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
def _clone_sql():
    """Statements that copy one finished workspace into another, remapping every id (run in one transaction)."""
    return [
        "CREATE TEMP TABLE pm ON COMMIT DROP AS SELECT id AS o, gen_random_uuid() AS n FROM papers WHERE workspace_id=%(src)s::uuid",
        "CREATE TEMP TABLE cm ON COMMIT DROP AS SELECT id AS o, gen_random_uuid() AS n FROM claims WHERE workspace_id=%(src)s::uuid",
        "INSERT INTO papers (id,workspace_id,doi,openalex_id,title,year,authors,venue,url,oa_url,license,text_level,full_text,abstract,"
         "retraction_status,cited_by_count,refs,lane,kept,is_upload,is_new,expanded_from,confidence,scholar_links,embedding) "
         "SELECT pm.n,%(dst)s::uuid,p.doi,p.openalex_id,p.title,p.year,p.authors,p.venue,p.url,p.oa_url,p.license,p.text_level,p.full_text,p.abstract,"
         "p.retraction_status,p.cited_by_count,p.refs,p.lane,p.kept,p.is_upload,p.is_new,"
         "(SELECT x.n FROM pm x WHERE x.o=p.expanded_from),p.confidence,p.scholar_links,p.embedding "
         "FROM papers p JOIN pm ON pm.o=p.id",
        "INSERT INTO paper_sources (paper_id,lane,query,found_at) SELECT pm.n,s.lane,s.query,s.found_at FROM paper_sources s JOIN pm ON pm.o=s.paper_id",
        "INSERT INTO claims (id,workspace_id,paper_id,claim_text,intervention,outcome,outcome_family,direction,significance,effect_size,"
         "population,sample_n,design,duration,measure,limitations,quote,location,embedding) "
         "SELECT cm.n,%(dst)s::uuid,pm.n,c.claim_text,c.intervention,c.outcome,c.outcome_family,c.direction,c.significance,c.effect_size,"
         "c.population,c.sample_n,c.design,c.duration,c.measure,c.limitations,c.quote,c.location,c.embedding "
         "FROM claims c JOIN cm ON cm.o=c.id JOIN pm ON pm.o=c.paper_id",
        "INSERT INTO claim_edges (workspace_id,claim_a,claim_b,label,factors,confidence,reason,quotes,sim,comparability,impact) "
         "SELECT %(dst)s::uuid,a.n,b.n,e.label,e.factors,e.confidence,e.reason,e.quotes,e.sim,e.comparability,e.impact "
         "FROM claim_edges e JOIN cm a ON a.o=e.claim_a JOIN cm b ON b.o=e.claim_b WHERE e.workspace_id=%(src)s::uuid",
        "INSERT INTO paper_scores (workspace_id,paper_id,relevance,sector,angle,parent_paper) "
         "SELECT %(dst)s::uuid,pm.n,s.relevance,s.sector,s.angle,(SELECT x.n FROM pm x WHERE x.o=s.parent_paper) "
         "FROM paper_scores s JOIN pm ON pm.o=s.paper_id WHERE s.workspace_id=%(src)s::uuid",
        "INSERT INTO flags (workspace_id,kind,description,claim_ids) "
         "SELECT %(dst)s::uuid,f.kind,f.description,ARRAY(SELECT cm.n FROM cm WHERE cm.o = ANY(f.claim_ids)) FROM flags f WHERE f.workspace_id=%(src)s::uuid",
    ]


def clone_workspace(src, dst):
    """Copy a finished investigation (papers, claims, verdicts, flags, layout) into `dst` in one transaction."""
    params = {"src": str(src), "dst": str(dst)}
    with pool().connection() as c:
        with c.transaction():
            for sql in _clone_sql():
                c.execute(sql, params)
            c.execute("UPDATE workspaces d SET parsed=s.parsed FROM workspaces s WHERE s.id=%(src)s::uuid AND d.id=%(dst)s::uuid", params)


def find_cached_workspace(ws):
    """A finished, upload-free investigation of the same question (exact key) or a near-identical one (embedding)."""
    me = one("SELECT question_key, embedding IS NOT NULL AS has_emb FROM workspaces WHERE id=%s", (ws,))
    if not me or one("SELECT 1 AS x FROM papers WHERE workspace_id=%s LIMIT 1", (ws,)):
        return None                                     # retrying a half-finished run, or the user uploaded PDFs: run fresh
    return one(
        "SELECT s.id, s.created_at, (s.question_key IS NOT NULL AND s.question_key = m.question_key) AS exact, "
        "coalesce(1-(s.embedding <=> m.embedding), 0) AS sim FROM workspaces s, workspaces m "
        "WHERE m.id=%s AND s.id <> m.id AND s.status='done' AND s.created_at > now() - make_interval(days => %s) "
        "AND EXISTS (SELECT 1 FROM papers p WHERE p.workspace_id=s.id AND p.kept) "
        "AND NOT EXISTS (SELECT 1 FROM papers p WHERE p.workspace_id=s.id AND (p.is_upload OR p.is_new)) "
        "AND (s.question_key = m.question_key OR 1-(s.embedding <=> m.embedding) >= %s) "
        "ORDER BY (s.question_key = m.question_key) DESC, sim DESC, s.created_at DESC LIMIT 1",
        (ws, C.CACHE_DAYS, C.SEMANTIC_CACHE_THRESHOLD))


def understand(ws):
    """Interpret the question. Returns the parsed dict, or None when a finished identical investigation was reused."""
    w = one("SELECT question, progress FROM workspaces WHERE id=%s", (ws,))
    try:
        emb = gemini.embed([w["question"]])[0]
        ex("UPDATE workspaces SET embedding=%s::vector WHERE id=%s", (vec(emb), ws))
    except Exception as e:
        raise RuntimeError("Gemini call failed while interpreting the question. " + gemini.explain(e)) from e
    if C.REUSE_CACHE and not (w["progress"] or {}).get("fresh"):
        try:                                             # a cache problem must never fail the run: fall through to a fresh analysis
            hit = find_cached_workspace(ws)
            if hit:
                clone_workspace(hit["id"], ws)
                progress(ws, cache_hit=True, cloned_from=str(hit["id"]), cache_exact=bool(hit["exact"]),
                         cache_similarity=round(float(hit["sim"]), 4),
                         cache_age_days=round((time.time() - hit["created_at"].timestamp()) / 86400, 1))
                return None
        except Exception:
            log.exception("Workspace cache lookup/clone failed; running a fresh analysis")
    try:
        parsed = gemini.generate_json(prompts.understand(w["question"]))
    except Exception as e:
        raise RuntimeError("Gemini call failed while interpreting the question. " + gemini.explain(e)) from e
    seen, qs = set(), []
    for s_ in parsed.get("search_queries") or []:
        if s_ and s_.strip().lower() not in seen:
            seen.add(s_.strip().lower())
            qs.append(s_.strip())
    parsed["search_queries"] = qs[:5] or [w["question"]]
    parsed["sub_questions"] = [s for s in parsed.get("sub_questions") or [] if s][:6] or [w["question"]]
    parsed["outcome_families"] = [s for s in parsed.get("outcome_families") or [] if s][:5]
    ex("UPDATE workspaces SET parsed=%s::jsonb WHERE id=%s", (json.dumps(parsed), ws))
    return parsed


# ---------- Stage 2: discovery (Lane A APIs + Lane B Google Scholar) ----------
def resolve_scholar_item(it, lane="B", query=None):
    """Turn a Scholar result into a candidate: resolve to a DOI via OpenAlex when possible."""
    links = {"cited_by": it.get("cited_by_url"), "related": it.get("related_url")}
    w = None
    try:
        doi = find_doi(it.get("url") or "") or find_doi(it.get("pdf_url") or "")
        w = (oa.work_by_doi(doi) if doi else None) or oa.work_by_title(it["title"], it.get("year"))
    except Exception:
        pass
    if w:
        w.update({"lane": lane, "query": query, "scholar_links": links})
        w["url"] = w.get("url") or it.get("url")
        w["oa_url"] = w.get("oa_url") or it.get("pdf_url")
        return w
    return {"title": it["title"], "year": it.get("year"), "authors": it.get("authors"), "venue": it.get("venue"),
            "url": it.get("url"), "oa_url": it.get("pdf_url"), "abstract": it.get("snippet"), "confidence": "low",
            "lane": lane, "query": query, "cited_by_count": it.get("cited_by_count", 0), "scholar_links": links}


def discover(ws, parsed):
    question = one("SELECT question FROM workspaces WHERE id=%s", (ws,))["question"]
    existing = q("SELECT id,doi,title,year FROM papers WHERE workspace_id=%s", (ws,))
    warnings, scholar = [], ScholarClient()
    queries, seen = [], set()
    for qs in parsed["search_queries"] + [question]:          # order-preserving, case-insensitive de-dup
        if qs.strip().lower() not in seen:
            seen.add(qs.strip().lower())
            queries.append(qs)

    def oa_search(qs):
        try:
            return [dict(w, lane="A", query=qs) for w in oa.search_works(qs, 25)], None
        except Exception as e:
            return [], f"OpenAlex failed for '{qs[:40]}': {e}"

    def scholar_lane():
        """Runs in parallel with the OpenAlex lane. Pages are rate limited, but DOI resolution is fanned out."""
        found, warns = [], []
        for qs in queries[:C.SCHOLAR_QUERIES]:
            try:
                items = scholar.search(qs, 20)
            except ScholarBlocked as e:
                warns.append(f"Google Scholar lane stopped: {e}")
                break
            except Exception as e:
                warns.append(f"Google Scholar fetch failed for '{qs[:40]}': {e}")
                continue
            found.extend(pmap(lambda it, qs=qs: resolve_scholar_item(it, "B", qs), items, C.IO_WORKERS))
            if not items:
                warns.append(f"Google Scholar returned 0 parsable results for '{qs[:40]}' (page layout changed or a soft block).")
        return found, warns

    use_scholar = scholar.enabled()
    with ThreadPoolExecutor(1) as side:
        fut = side.submit(scholar_lane) if use_scholar else None
        cands = []
        for found, warn in pmap(oa_search, queries, C.IO_WORKERS):      # API lane: all queries at once
            cands.extend(found)
            if warn:
                warnings.append(warn)
        if fut:
            found, warns = fut.result()
            cands.extend(found)                                          # always appended after OpenAlex: stable order
            warnings.extend(warns)
    if not use_scholar:
        warnings.append("Google Scholar lane skipped: BRIGHT_DATA_API_KEY or Web Unlocker zone not set.")
    new, dups, extra = dedupe([c for c in cands if c.get("title")], existing)
    if not new and not existing:
        raise RuntimeError("No papers were found. " + (" | ".join(warnings[:3]) or "The search APIs returned nothing for this question; try rephrasing it."))
    pmap(lambda c: insert_paper(ws, c), new[:C.MAX_CANDIDATES], C.IO_WORKERS)
    for pid, lane, query in extra:
        add_source(pid, lane, query)
    progress(ws, duplicates_removed=dups, candidates=min(len(new), C.MAX_CANDIDATES) + len(existing), warnings=warnings)


def reuse_paper_embeddings(ws):
    """Copy embeddings of papers (same DOI, else same title) already embedded in other workspaces."""
    if not C.REUSE_CACHE:
        return
    ex("UPDATE papers p SET embedding = o.embedding FROM ("
       " SELECT DISTINCT ON (k) k, embedding FROM ("
       "  SELECT coalesce(doi, lower(title)) AS k, embedding FROM papers WHERE workspace_id <> %s::uuid AND embedding IS NOT NULL) x"
       " ORDER BY k) o"
       " WHERE p.workspace_id=%s::uuid AND p.embedding IS NULL AND o.k = coalesce(p.doi, lower(p.title))", (ws, ws))


def _set_embeddings(table, rows, embs):
    """One round trip for all rows instead of one UPDATE per row (each is a network hop to the hosted database)."""
    if rows:
        ex(f"UPDATE {table} t SET embedding = v.e::vector FROM unnest(%s::uuid[], %s::text[]) AS v(id, e) WHERE t.id = v.id",
           ([str(r["id"]) for r in rows], [vec(e) for e in embs]))


def embed_papers(ws):
    reuse_paper_embeddings(ws)
    rows = q("SELECT id,title,abstract FROM papers WHERE workspace_id=%s AND embedding IS NULL ORDER BY id", (ws,))
    embs = gemini.embed([f"{r['title']}. {(r['abstract'] or '')[:C.EMBED_PAPER_CHARS]}" for r in rows])
    _set_embeddings("papers", rows, embs)


def prelim_rank(ws, cap):
    """Keep uploads plus the papers most similar to the question; returns the ranked kept ids."""
    rows = q("SELECT p.id, p.is_upload, 1-(p.embedding <=> w.embedding) AS sim FROM papers p "
             "JOIN workspaces w ON w.id=p.workspace_id WHERE p.workspace_id=%s AND p.embedding IS NOT NULL "
             "ORDER BY p.is_upload DESC, round((1-(p.embedding <=> w.embedding))::numeric, 5) DESC, coalesce(p.doi, lower(p.title))", (ws,))
    cap = max(cap, sum(1 for r in rows if r["is_upload"]))
    keep = [r["id"] for r in rows][:cap]
    ex("UPDATE papers SET kept = (id = ANY(%s::uuid[])) WHERE workspace_id=%s", ([str(k) for k in keep], ws))
    return keep


def expand(ws, keep, seeds=5):
    """Citation expansion around the top seeds -> the second ring of the graph. Seeds run in parallel; OpenAlex
    'cited by' is the default (API, fast). Scholar expansion (5 s per page) is opt-in via SCHOLAR_EXPAND."""
    scholar = ScholarClient()
    seed_rows = q("SELECT * FROM papers WHERE id = ANY(%s::uuid[]) AND NOT is_upload", ([str(k) for k in keep[:seeds * 2]],))
    order = {str(k): i for i, k in enumerate(keep)}
    seed_rows = sorted(seed_rows, key=lambda r: order.get(str(r["id"]), 1e9))[:seeds]
    use_scholar = C.SCHOLAR_EXPAND and scholar.enabled()

    def grow(s):
        out, links = [], s.get("scholar_links") or {}
        try:
            if use_scholar and not scholar.blocked and any(links.values()):
                for kind, url in links.items():
                    if url:
                        for it in scholar.expand(url, 10):
                            c = resolve_scholar_item(it, "B", f"expansion:{kind}")
                            c["_seed"] = s["id"]
                            out.append(c)
            elif s["openalex_id"]:
                for w in oa.citing(s["openalex_id"], 10):
                    w.update({"lane": "A", "query": "expansion:citing", "_seed": s["id"]})
                    out.append(w)
        except Exception as e:
            log.warning("expansion failed for %s: %s", s["title"], e)
        return out

    cands = [c for part in pmap(grow, seed_rows, C.IO_WORKERS if not use_scholar else 1) for c in part]
    existing = q("SELECT id,doi,title,year FROM papers WHERE workspace_id=%s", (ws,))
    new, dups, extra = dedupe([c for c in cands if c.get("title")], existing)
    pmap(lambda c: insert_paper(ws, c), new[:60], C.IO_WORKERS)
    for pid, lane, query in extra:
        add_source(pid, lane, query)
    progress(ws, expanded=len(new[:60]))


def retrieve_full_text(p):
    """Order: uploaded PDF -> Europe PMC API -> OpenAlex OA URL / result URL via Bright Data Web Unlocker (allowlisted) -> abstract.
    Returns (text, level, source)."""
    if p.get("full_text") and len(p["full_text"]) >= C.FULL_TEXT_MIN:
        return p["full_text"], "full", "uploaded"
    if p.get("doi"):
        try:
            t = oa.epmc_fulltext(p["doi"])
            if t and len(t) >= C.FULL_TEXT_MIN:
                return t, "full", "europepmc"
        except Exception as e:
            log.info("Europe PMC miss for %s: %s", p["doi"], e)
    unl = UnlockerClient()
    if unl.enabled():
        for u in (p.get("oa_url"), p.get("url")):
            if u and allowed(u):
                try:
                    t = unl.fetch_text(u)
                    if t and len(t) >= C.FULL_TEXT_MIN:
                        return t, "full", "brightdata"
                except Exception as e:
                    log.info("Unlocker miss for %s: %s", u, e)
    return (p.get("abstract") or ""), "abstract", "abstract"


def retrieve_all(ws):
    rows = q("SELECT * FROM papers WHERE workspace_id=%s AND kept ORDER BY id", (ws,))
    tally = {"uploaded": 0, "europepmc": 0, "brightdata": 0, "abstract": 0}

    def work(p):
        try:
            text, level, src = retrieve_full_text(p)
        except Exception:
            text, level, src = (p.get("full_text") or p.get("abstract") or ""), "abstract", "abstract"
        tally[src] += 1
        ex("UPDATE papers SET full_text=%s, text_level=%s WHERE id=%s", (text, level, p["id"]))

    pmap(work, rows, C.IO_WORKERS)
    progress(ws, text_sources=tally)
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


CLAIM_FIELDS = ("claim_text,intervention,outcome,outcome_family,direction,significance,effect_size,population,"
                "sample_n,design,duration,measure,limitations,quote,location")


def reuse_claims(p):
    """Copy claims (and their embeddings) already extracted from the same paper with the same text in another workspace.
    Quotes stay valid because the source text is identical (same text level, near-identical length)."""
    if not C.REUSE_CACHE:
        return 0
    src = one("SELECT p2.id FROM papers p2 WHERE p2.workspace_id <> %s::uuid AND p2.text_level = %s "
              "AND coalesce(p2.doi, lower(p2.title)) = coalesce(%s, lower(%s)) "
              "AND abs(coalesce(length(p2.full_text),0) - %s) < 50 "
              "AND EXISTS (SELECT 1 FROM claims c WHERE c.paper_id = p2.id) ORDER BY p2.created_at DESC LIMIT 1",
              (p["workspace_id"], p.get("text_level") or "abstract", p.get("doi"), p.get("title") or "",
               len(p.get("full_text") or "")))
    if not src:
        return 0
    ex(f"INSERT INTO claims (workspace_id,paper_id,{CLAIM_FIELDS},embedding) "
       f"SELECT %s::uuid,%s::uuid,{CLAIM_FIELDS},embedding FROM claims WHERE paper_id=%s::uuid", (p["workspace_id"], p["id"], src["id"]))
    return one("SELECT count(*) AS n FROM claims WHERE paper_id=%s", (p["id"],))["n"]


def extract_paper(p):
    full = p.get("full_text") or p.get("abstract") or ""
    if len(full) < 200:
        return 0, 0
    reused = reuse_claims(p)
    if reused:
        return reused, 0
    text = focus_text(full, C.MAX_TEXT_CHARS)            # what the model reads (findings-rich passages first)
    nt, level = normalize(full), p.get("text_level") or "abstract"   # what a quote must match: the whole paper
    prompt, valid, rejected, seen = prompts.extract(p, text, level), [], 0, set()
    for attempt in range(2):
        data = gemini.generate_json(prompt, system=prompts.EXTRACT_SYSTEM)
        for c in data.get("claims") or []:
            qt = c.get("quote") or ""
            if qt in seen:
                continue
            seen.add(qt)
            if quote_ok(qt, full, nt):                       # code-level verbatim check
                c["location"] = locate(full, qt) or c.get("location")
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
    rows = q("SELECT id,claim_text,outcome FROM claims WHERE workspace_id=%s AND embedding IS NULL ORDER BY id", (ws,))
    embs = gemini.embed([f"{r['claim_text']} (outcome: {r['outcome']})" for r in rows])
    _set_embeddings("claims", rows, embs)


def extract_all(ws):
    papers = q("SELECT * FROM papers WHERE workspace_id=%s AND kept AND NOT EXISTS "
               "(SELECT 1 FROM claims c WHERE c.paper_id=papers.id) ORDER BY id", (ws,))

    errors = []

    def work(p):
        try:
            return extract_paper(p)
        except Exception as e:
            log.error("extraction failed for %s\n%s", p["title"], traceback.format_exc())
            errors.append(gemini.explain(e))
            return 0, 0

    res = pmap(work, papers)
    progress(ws, claims_extracted=sum(r[0] for r in res), claims_rejected=sum(r[1] for r in res))
    if papers and len(errors) == len(papers):
        raise RuntimeError(f"Claim extraction failed for all {len(papers)} papers. First error: {errors[0]}")
    if errors:
        _warn(ws, f"Claim extraction failed for {len(errors)} of {len(papers)} papers. First error: {errors[0]}")
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
  AND NOT EXISTS (SELECT 1 FROM claim_edges e WHERE (e.claim_a=a.id AND e.claim_b=b.id) OR (e.claim_a=b.id AND e.claim_b=a.id))
ORDER BY round((1-(a.embedding <=> b.embedding))::numeric, 5) DESC, least(a.quote, b.quote), greatest(a.quote, b.quote) LIMIT %(lim)s
"""


def match(ws, only=None):
    return q(MATCH_SQL, {"ws": ws, "only": [str(x) for x in only] if only else None, "th": C.MATCH_THRESHOLD,
                         "strong": C.STRONG_MATCH, "lim": C.MAX_PAIRS})


# ---------- Stage 7: verify relationships ----------
def reuse_verdict(a, b):
    """A verdict for the same two quotes (same orientation) from another workspace, if any."""
    if not C.REUSE_CACHE:
        return None
    return one("SELECT e.label, e.factors, e.confidence, e.reason FROM claim_edges e "
               "JOIN claims ca ON ca.id=e.claim_a JOIN claims cb ON cb.id=e.claim_b "
               "WHERE e.workspace_id <> %s::uuid AND md5(ca.quote) = md5(%s) AND md5(cb.quote) = md5(%s) AND e.label IS NOT NULL ORDER BY e.id LIMIT 1",
               (a["workspace_id"], a["quote"], b["quote"]))


def verify_one(ws, a, b, pair):
    if (a["quote"] or "") > (b["quote"] or ""):       # canonical A/B order by quote text, so verdicts can be reused
        a, b = b, a
    comp = comparability(a, b)
    hit = reuse_verdict(a, b)
    if hit:
        conf = float(hit["confidence"] or 0.5)
        if "abstract" in (a["text_level"], b["text_level"]):
            conf = min(conf, 0.6)
        row = one("INSERT INTO claim_edges (workspace_id,claim_a,claim_b,label,factors,confidence,reason,quotes,sim,comparability) "
                  "VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s::jsonb) ON CONFLICT DO NOTHING RETURNING id",
                  (ws, a["id"], b["id"], hit["label"], hit["factors"] or [], conf, hit["reason"],
                   json.dumps({"a": a["quote"], "b": b["quote"]}), float(pair["sim"]), json.dumps(comp)))
        return row["id"] if row else None
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
    pairs = sorted(pairs, key=lambda p: (-float(p["sim"]), str(p["a_id"]), str(p["b_id"])))

    def work(p):
        try:
            return verify_one(ws, claims[str(p["a_id"])], claims[str(p["b_id"])], p)
        except Exception:
            log.error("verification failed\n%s", traceback.format_exc())
            return None

    out = pmap(work, pairs)
    progress(ws, pairs_verified=len([o for o in out if o]))
    if pairs and not any(out):
        _warn(ws, f"All {len(pairs)} claim-pair verifications failed; see Render logs for the Gemini error.")
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
    exmany("INSERT INTO paper_scores (workspace_id,paper_id,relevance,sector,angle,parent_paper) VALUES (%s,%s,%s,%s,%s,%s)",
           [(ws, i, rel[i], sector[i], angle.get(i, 0.0), parent.get(i)) for i in ids])


# ---------- orchestration ----------
class Timer:
    """Records seconds spent per stage in workspaces.progress.timings (visible in /workspaces/<id>/status)."""

    def __init__(self, ws):
        self.ws, self.name, self.t, self.d = ws, None, time.time(), {}

    def to(self, name, status=None):
        self.close()
        self.name, self.t = name, time.time()
        if status:
            set_status(self.ws, status)

    def close(self):
        if self.name:
            self.d[self.name] = round(time.time() - self.t, 1)
            progress(self.ws, timings=self.d)
            self.name = None


def _bd_progress(ws, before):
    now = bd.snapshot()
    progress(ws, bright_data={k: now[k] - before.get(k, 0) for k in now})


def run_workspace(ws):
    tm, bd0 = Timer(ws), bd.snapshot()
    try:
        set_status(ws, "understanding")
        tm.to("understand")
        parsed = understand(ws)
        if parsed is None:                              # identical investigation already finished: reused, nothing to compute
            tm.close()
            set_status(ws, "done")
            return
        tm.to("discover", "discovering")
        discover(ws, parsed)
        _bd_progress(ws, bd0)
        tm.to("embed_rank", "retrieving")
        embed_papers(ws)
        keep = prelim_rank(ws, C.MAX_PAPERS)
        tm.to("expand")
        expand(ws, keep)
        embed_papers(ws)
        prelim_rank(ws, C.MAX_PAPERS)
        tm.to("retrieve_text")
        retrieve_all(ws)
        _bd_progress(ws, bd0)
        tm.to("extract_claims", "extracting")
        extract_all(ws)
        tm.to("match", "matching")
        pairs = match(ws)
        progress(ws, candidate_pairs=len(pairs))
        tm.to("verify", "verifying")
        verify_pairs(ws, pairs)
        external_check(ws)
        tm.to("flags", "flagging")
        build_flags(ws)
        tm.to("layout", "layout")
        compute_layout(ws)
        tm.close()
        _bd_progress(ws, bd0)
        set_status(ws, "done")
    except Exception as e:
        log.error("workspace %s failed\n%s", ws, traceback.format_exc())
        try:
            tm.close()
            set_status(ws, "error", str(e)[:1500])
        except Exception:
            log.exception("could not record error status")
