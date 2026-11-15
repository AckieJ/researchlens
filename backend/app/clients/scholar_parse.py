"""Pure HTML helpers for Google Scholar result pages (no network, no DB).

All Scholar-specific selectors live in this one file. If Google changes its markup, fix it here;
tests/test_scholar_parse.py shows the structures this parser accepts.

parse_scholar_html()  results from the classic markup, with two fallbacks for variants
fingerprint()         what kind of page did we actually get? (results / consent wall / CAPTCHA / JS wall / unrelated page)
describe()            one-line summary of a fingerprint, used in warnings and /diagnostics/scholar
"""
import re
from urllib.parse import urljoin, urlparse

BASE = "https://scholar.google.com/"


def looks_blocked(html):
    """True when Scholar returned a CAPTCHA / 'unusual traffic' page instead of results."""
    h = (html or "").lower()
    return any(m in h for m in ("gs_captcha", "unusual traffic", "sorry/index", "not a robot", "recaptcha"))


def _text(el):
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True).replace("\xa0", " ")).strip() if el else ""


def _soup(html):
    from bs4 import BeautifulSoup
    return BeautifulSoup(html or "", "html.parser")


def _item(container, h3, base_parent=None):
    for tag in h3.select("span.gs_ctg2, span.gs_ct1, span.gs_ct2"):   # [PDF] / [HTML] / [CITATION] prefixes
        tag.decompose()
    a = h3.select_one("a")
    title = _text(a or h3)
    if not title:
        return None
    meta_el = container.select_one("div.gs_a")
    meta = _text(meta_el)                                                # "A Author, B Author - Journal, 2020 - site.com"
    if not meta:                                                         # fallback: first short line that looks like authors - venue, year
        for el in container.find_all(["div", "span", "p"]):
            t = _text(el)
            if " - " in t and re.search(r"\b(19|20)\d{2}\b", t) and len(t) < 300 and title not in t:
                meta = t
                break
    parts = [p.strip() for p in meta.split(" - ")]
    ym = re.search(r"\b(19|20)\d{2}\b", " ".join(parts[1:]) if len(parts) > 1 else meta)
    cited_n, cited_url, related_url = 0, None, None
    for link in container.select("div.gs_fl a, a"):
        t, href = _text(link), link.get("href")
        if not href:
            continue
        tl = t.lower()
        if tl.startswith("cited by") and cited_url is None:
            cited_n = int(re.sub(r"\D", "", t) or 0)
            cited_url = urljoin(BASE, href)
        elif tl.startswith("related articles") and related_url is None:
            related_url = urljoin(BASE, href)
    snip_el = container.select_one("div.gs_rs")
    snippet = _text(snip_el)
    if not snippet:
        longest = max((_text(d) for d in container.find_all("div")), key=len, default="")
        snippet = longest if longest and longest != meta and title not in longest and len(longest) > 60 else ""
    pdf = base_parent.select_one("div.gs_ggs a, div.gs_or_ggsm a") if base_parent else None
    href = a.get("href", "") if a else ""
    return {
        "title": title,
        "year": int(ym.group()) if ym else None,
        "authors": parts[0] if parts else "",
        "venue": parts[1] if len(parts) > 1 else "",
        "url": href if href.startswith("http") else None,
        "snippet": snippet,
        "pdf_url": pdf.get("href") if pdf and pdf.get("href", "").startswith("http") else None,
        "cited_by_count": cited_n,
        "cited_by_url": cited_url,
        "related_url": related_url,
    }


def parse_scholar_html(html):
    """Return a list of dicts: title, year, authors, venue, url, snippet, pdf_url, cited_by_count, cited_by_url, related_url."""
    soup = _soup(html)
    out, seen = [], set()

    def add(it):
        if it and it["title"].lower() not in seen:
            seen.add(it["title"].lower())
            out.append(it)

    # 1) classic markup: div.gs_ri inside div.gs_r
    for ri in soup.select("div.gs_ri"):
        h3 = ri.select_one("h3.gs_rt") or ri.find("h3")
        if h3:
            add(_item(ri, h3, ri.find_parent("div", class_="gs_r")))
    # 2) result blocks without the gs_ri wrapper
    if not out:
        for h3 in soup.select("div.gs_r h3, div.gs_or h3, div[data-cid] h3"):
            box = h3.find_parent("div", class_=re.compile(r"\bgs_(r|or)\b")) or h3.find_parent("div", attrs={"data-cid": True})
            if box:
                add(_item(box, h3, box))
    # 3) last resort: any heading with an external article link, using the nearest ancestor that has a body of text
    if not out:
        for h3 in soup.select("h3"):
            a = h3.find("a", href=True)
            if not a or not a["href"].startswith("http") or urlparse(a["href"]).netloc.endswith("google.com") or len(_text(a)) < 12:
                continue
            box = h3
            for _ in range(4):
                if box.parent is None:
                    break
                box = box.parent
                if len(_text(box)) > len(_text(h3)) + 80:
                    break
            add(_item(box, h3, box))
    return out


def fingerprint(html):
    """Summarise a fetched page so a '0 results' outcome can be diagnosed instead of guessed at."""
    h = html or ""
    low = h.lower()
    soup = _soup(h)
    title = _text(soup.title) if soup.title else ""
    body = _text(soup.body or soup)
    flags = []
    if looks_blocked(h):
        flags.append("captcha")
    if "before you continue" in low or "consent.google" in low:
        flags.append("consent wall")
    if "enable javascript" in low or "javascript is disabled" in low or "turn on javascript" in low:
        flags.append("javascript wall")
    if "did not match any articles" in low or "did not match any documents" in low:
        flags.append("no matching articles")
    if "scholar" not in low[:20000]:
        flags.append("not a Scholar page")
    return {
        "bytes": len(h), "title": title[:80],
        "result_blocks": len(soup.select("div.gs_r")), "gs_ri": len(soup.select("div.gs_ri")), "h3": len(soup.find_all("h3")),
        "flags": flags, "excerpt": body[:300],
    }


def describe(fp):
    if not fp:
        return "no page was fetched"
    bits = [f"page '{fp['title'] or 'untitled'}', {fp['bytes']:,} bytes", f"{fp['result_blocks']} result blocks, {fp['h3']} headings"]
    if fp["flags"]:
        bits.append("looks like: " + ", ".join(fp["flags"]))
    return "; ".join(bits)
