"""Pure text helpers: quote validation, page location, parsing, similarity. No network or DB access."""
import difflib
import io
import re
import unicodedata

MARK = re.compile(r"\[\[page (\d+)\]\]")
_MAP = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u2013": "-",
                      "\u2014": "-", "\u2212": "-", "\u00a0": " ", "\u00ad": ""})
DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+")


def normalize(s):
    """Lowercase, unify quotes/dashes/ligatures, drop page markers and line-break hyphenation, collapse whitespace."""
    s = MARK.sub(" ", s or "")
    s = unicodedata.normalize("NFKC", s).translate(_MAP)
    s = re.sub(r"-\s*\n\s*", "", s)
    return re.sub(r"\s+", " ", s).strip().casefold()


def quote_ok(quote, text, norm_text=None, min_len=20):
    """The evidence is the verbatim quote: it must literally occur in the source text."""
    nq = normalize(quote)
    if len(nq) < min_len:
        return False
    return nq in (norm_text if norm_text is not None else normalize(text))


def locate(text, quote):
    """Return 'p. N' for the page whose text contains the quote, else None."""
    nq = normalize(quote)
    parts = re.split(r"\[\[page (\d+)\]\]", text or "")
    for i in range(1, len(parts) - 1, 2):
        if nq in normalize(parts[i + 1]):
            return f"p. {parts[i]}"
    return None


def passage(text, quote, width=700):
    """Normalized text surrounding the quote, for the verifier's context."""
    nt, nq = normalize(text), normalize(quote)
    i = nt.find(nq)
    if i < 0:
        return nq
    return nt[max(0, i - width): i + len(nq) + width]


def norm_doi(d):
    if not d:
        return None
    d = str(d).strip().lower()
    for p in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "doi:"):
        if d.startswith(p):
            d = d[len(p):]
    return d or None


def find_doi(text):
    m = DOI_RE.search(text or "")
    return norm_doi(m.group().rstrip(".,;)")) if m else None


def guess_title(text):
    for line in MARK.sub("", text or "").splitlines():
        line = line.strip()
        if len(line) >= 15:
            return line[:200]
    return None


def title_sim(a, b):
    na = re.sub(r"[^a-z0-9 ]", "", (a or "").lower())
    nb = re.sub(r"[^a-z0-9 ]", "", (b or "").lower())
    return difflib.SequenceMatcher(None, na, nb).ratio() if na and nb else 0.0


def jaccard(a, b):
    ta, tb = set(re.findall(r"[a-z0-9]+", (a or "").lower())), set(re.findall(r"[a-z0-9]+", (b or "").lower()))
    return len(ta & tb) / len(ta | tb) if ta and tb else 0.0


def duration_days(s):
    m = re.search(r"(\d+(?:\.\d+)?)\s*[- ]?\s*(hour|day|week|month|year|session)", (s or "").lower())
    if not m:
        return None
    return float(m.group(1)) * {"hour": 1 / 24, "day": 1, "week": 7, "month": 30, "year": 365, "session": 1}[m.group(2)]


def comparability(a, b):
    """Checklist passed to the verifier. None = unknown (never silently treated as 'same')."""
    da, db = duration_days(a.get("duration")), duration_days(b.get("duration"))
    return {
        "same_population": (jaccard(a.get("population"), b.get("population")) >= 0.25) if a.get("population") and b.get("population") else None,
        "same_duration": (0.75 <= da / db <= 1.34) if da and db else None,
        "same_measure": (jaccard(a.get("measure"), b.get("measure")) >= 0.3) if a.get("measure") and b.get("measure") else None,
        "same_design": (jaccard(a.get("design"), b.get("design")) >= 0.3) if a.get("design") and b.get("design") else None,
    }


def pdf_to_text(data):
    import fitz  # PyMuPDF
    doc = fitz.open(stream=data, filetype="pdf")
    return "\n".join(f"[[page {i + 1}]]\n{p.get_text()}" for i, p in enumerate(doc))


def html_to_text(html):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html or "", "html.parser")
    for t in soup(["script", "style", "nav", "footer", "header", "form", "noscript", "aside"]):
        t.decompose()
    root = soup.find("article") or soup.find("main") or soup.body or soup
    return re.sub(r"\n{3,}", "\n\n", root.get_text("\n"))


def xml_to_text(xml):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(xml or "", "lxml-xml")
    root = soup.find("body") or soup
    return re.sub(r"\n{3,}", "\n\n", root.get_text("\n"))
