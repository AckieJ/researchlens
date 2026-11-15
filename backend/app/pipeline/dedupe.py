"""De-duplicate paper candidates by normalized DOI, then by title similarity + year."""
from .text import norm_doi, title_sim

FILL = ("doi", "abstract", "oa_url", "openalex_id", "license", "venue", "authors", "url")


def _match(c, pool):
    cd = norm_doi(c.get("doi"))
    for m in pool:
        md = norm_doi(m.get("doi"))
        if cd and md and cd == md:
            return m
        yc, ym = c.get("year"), m.get("year")
        if title_sim(c.get("title"), m.get("title")) >= 0.9 and (not yc or not ym or yc == ym):
            return m
    return None


def dedupe(cands, existing=()):
    """Return (new_candidates, duplicates_removed, extra_sources).

    existing: dicts with 'id', 'doi', 'title', 'year' (already stored).
    extra_sources: (paper_id, lane, query) rows to add for duplicates of stored papers.
    """
    pool = [dict(e) for e in existing]
    new, dups, extra = [], 0, []
    for c in cands:
        m = _match(c, pool)
        if m is None:
            c = dict(c)
            c["sources"] = [(c.get("lane"), c.get("query"))]
            pool.append(c)
            new.append(c)
            continue
        dups += 1
        for k in FILL:
            if not m.get(k) and c.get(k):
                m[k] = c[k]
        if c.get("scholar_links") and not m.get("scholar_links"):
            m["scholar_links"] = c["scholar_links"]
        if "id" in m:
            extra.append((m["id"], c.get("lane"), c.get("query")))
        else:
            m.setdefault("sources", []).append((c.get("lane"), c.get("query")))
    return new, dups, extra
