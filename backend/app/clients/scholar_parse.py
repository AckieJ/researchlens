"""Pure HTML parser for Google Scholar result pages (no network, no DB).

All Scholar-specific selectors live in this one file. If Google changes its markup, fix it here;
tests/test_scholar_parse.py shows the structure this parser expects.
"""
import re
from urllib.parse import urljoin

BASE = "https://scholar.google.com/"


def looks_blocked(html):
    """True when Scholar returned a CAPTCHA / 'unusual traffic' page instead of results."""
    h = (html or "").lower()
    return any(m in h for m in ("gs_captcha", "unusual traffic", "sorry/index", "not a robot", "recaptcha"))


def _text(el):
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True).replace("\xa0", " ")).strip() if el else ""


def parse_scholar_html(html):
    """Return a list of dicts: title, year, authors, venue, url, snippet, pdf_url,
    cited_by_count, cited_by_url, related_url."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html or "", "html.parser")
    out = []
    for ri in soup.select("div.gs_ri"):
        h3 = ri.select_one("h3.gs_rt")
        if not h3:
            continue
        for tag in h3.select("span.gs_ctg2, span.gs_ct1, span.gs_ct2"):   # [PDF] / [HTML] / [CITATION] prefixes
            tag.decompose()
        a = h3.select_one("a")
        title = _text(a or h3)
        if not title:
            continue
        meta = _text(ri.select_one("div.gs_a"))                            # "A Author, B Author - Journal, 2020 - site.com"
        parts = [p.strip() for p in meta.split(" - ")]
        ym = re.search(r"\b(19|20)\d{2}\b", " ".join(parts[1:]) if len(parts) > 1 else meta)
        cited_n, cited_url, related_url = 0, None, None
        for link in ri.select("div.gs_fl a"):
            t, href = _text(link), link.get("href")
            if not href:
                continue
            if t.lower().startswith("cited by"):
                cited_n = int(re.sub(r"\D", "", t) or 0)
                cited_url = urljoin(BASE, href)
            elif t.lower().startswith("related articles"):
                related_url = urljoin(BASE, href)
        parent = ri.find_parent("div", class_="gs_r")
        pdf = parent.select_one("div.gs_ggs a, div.gs_or_ggsm a") if parent else None
        out.append({
            "title": title,
            "year": int(ym.group()) if ym else None,
            "authors": parts[0] if parts else "",
            "venue": parts[1] if len(parts) > 1 else "",
            "url": a.get("href") if a and a.get("href", "").startswith("http") else None,
            "snippet": _text(ri.select_one("div.gs_rs")),
            "pdf_url": pdf.get("href") if pdf and pdf.get("href", "").startswith("http") else None,
            "cited_by_count": cited_n,
            "cited_by_url": cited_url,
            "related_url": related_url,
        })
    return out
