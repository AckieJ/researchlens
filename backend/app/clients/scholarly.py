"""Scholarly APIs (Lane A): OpenAlex, Crossref, Europe PMC. Free, structured, preferred over scraping."""
import requests

from .. import config as C
from ..pipeline.text import norm_doi, title_sim, xml_to_text
from .util import retry

OA = "https://api.openalex.org"
UA = {"User-Agent": f"ResearchLens/0.1 (mailto:{C.OPENALEX_EMAIL or 'unknown@example.com'})"}


def _get(url, params=None, timeout=40):
    params = dict(params or {})
    if C.OPENALEX_EMAIL and "openalex" in url:
        params["mailto"] = C.OPENALEX_EMAIL

    def call():
        r = requests.get(url, params=params, headers=UA, timeout=timeout)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r

    return retry(call, tries=3)


def _abstract(inv):
    if not inv:
        return ""
    pos = [(p, w) for w, ps in inv.items() for p in ps]
    return " ".join(w for _, w in sorted(pos))


def normalize_work(w):
    loc = w.get("best_oa_location") or {}
    prim = w.get("primary_location") or {}
    return {
        "doi": norm_doi(w.get("doi")),
        "openalex_id": (w.get("id") or "").rsplit("/", 1)[-1] or None,
        "title": w.get("title") or w.get("display_name"),
        "year": w.get("publication_year"),
        "authors": ", ".join(a["author"]["display_name"] for a in (w.get("authorships") or [])[:8] if a.get("author")),
        "venue": (prim.get("source") or {}).get("display_name"),
        "url": prim.get("landing_page_url") or w.get("doi"),
        "oa_url": loc.get("pdf_url") or loc.get("landing_page_url") or (w.get("open_access") or {}).get("oa_url"),
        "license": loc.get("license"),
        "abstract": _abstract(w.get("abstract_inverted_index")),
        "cited_by_count": w.get("cited_by_count") or 0,
        "refs": [r.rsplit("/", 1)[-1] for r in (w.get("referenced_works") or [])],
        "retraction_status": "retracted" if w.get("is_retracted") else "none",
        "confidence": "high",
    }


def search_works(query, per_page=25):
    r = _get(f"{OA}/works", {"search": query, "per_page": per_page, "filter": "has_abstract:true"})
    return [normalize_work(w) for w in (r.json().get("results", []) if r else [])]


def work_by_doi(doi):
    r = _get(f"{OA}/works/doi:{norm_doi(doi)}")
    return normalize_work(r.json()) if r else None


def work_by_title(title, year=None):
    r = _get(f"{OA}/works", {"search": title, "per_page": 5})
    best = None
    for w in (r.json().get("results", []) if r else []):
        n = normalize_work(w)
        if title_sim(title, n["title"] or "") >= 0.88 and (not year or not n["year"] or abs(year - n["year"]) <= 1):
            best = best or n
    return best


def citing(openalex_id, n=10):
    r = _get(f"{OA}/works", {"filter": f"cites:{openalex_id}", "per_page": n, "sort": "cited_by_count:desc"})
    return [normalize_work(w) for w in (r.json().get("results", []) if r else [])]


def crossref_updates(doi):
    """Retraction/correction notices recorded for a DOI. Returns a list of update types."""
    r = _get(f"https://api.crossref.org/works/{norm_doi(doi)}")
    if not r:
        return []
    msg = r.json().get("message", {})
    items = msg.get("updated-by") or []
    return [str(i.get("type", "")).lower() for i in items]


def epmc_fulltext(doi):
    """Open-access full text from the Europe PMC API (public API, no scraping)."""
    s = _get("https://www.ebi.ac.uk/europepmc/webservices/rest/search",
             {"query": f'DOI:"{norm_doi(doi)}"', "format": "json", "resultType": "lite"})
    res = (s.json().get("resultList", {}).get("result", []) if s else [])
    if not res or res[0].get("isOpenAccess") != "Y" or not res[0].get("pmcid"):
        return None
    x = _get(f"https://www.ebi.ac.uk/europepmc/webservices/rest/{res[0]['pmcid']}/fullTextXML", timeout=60)
    return xml_to_text(x.text) if x else None
