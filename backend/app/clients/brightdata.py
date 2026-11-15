"""Bright Data clients.

UnlockerClient  - Web Unlocker: fetch publicly accessible, allowlisted pages (open-access full text).
ScholarClient   - Google Scholar scraper (Scraper APIs): find more sources and citation neighbours.

VERIFY against your Bright Data dashboard docs before the event: the Scholar request shape
(input field, sync vs. async endpoints) differs between scrapers. See README "Bright Data setup".
"""
import hashlib
import re
import threading
import time
from urllib.parse import quote_plus, urlparse

import requests

from .. import config as C
from ..db import ex, one
from ..pipeline.text import html_to_text, pdf_to_text
from .allowlist import allowed
from .util import retry

_last = {}
_lock = threading.Lock()


def _throttle(host, gap=1.0):
    """At most one request per `gap` seconds per domain."""
    with _lock:
        now = time.time()
        slot = max(now, _last.get(host, 0) + gap)
        _last[host] = slot
    if slot > now:
        time.sleep(slot - now)


class NotAllowed(Exception):
    pass


class UnlockerClient:
    def enabled(self):
        return bool(C.BRIGHT_DATA_API_KEY and C.BRIGHT_DATA_UNLOCKER_ZONE)

    def fetch_text(self, url):
        """Return extracted text of an allowlisted public page or PDF (cached for 7 days)."""
        if not allowed(url):
            raise NotAllowed(url)
        if not self.enabled():
            raise RuntimeError("Bright Data Web Unlocker is not configured")
        h = hashlib.sha256(url.encode()).hexdigest()
        hit = one("SELECT body FROM fetch_cache WHERE url_hash=%s AND fetched_at > now() - interval '7 days'", (h,))
        if hit:
            return hit["body"]
        _throttle(urlparse(url).netloc)

        def call():
            r = requests.post(
                "https://api.brightdata.com/request",
                headers={"Authorization": "Bearer " + C.BRIGHT_DATA_API_KEY},
                json={"zone": C.BRIGHT_DATA_UNLOCKER_ZONE, "url": url, "format": "raw"},
                timeout=90,
            )
            r.raise_for_status()
            return r

        r = retry(call)
        text = pdf_to_text(r.content) if r.content[:5] == b"%PDF-" else html_to_text(r.text)
        ex("INSERT INTO fetch_cache (url_hash,url,body) VALUES (%s,%s,%s) "
           "ON CONFLICT (url_hash) DO UPDATE SET body=EXCLUDED.body, fetched_at=now()", (h, url, text))
        return text


def _pick(d, *keys):
    for k in keys:
        v = d.get(k)
        if v not in (None, "", []):
            return v
    return None


def _year(v):
    m = re.search(r"\b(19|20)\d{2}\b", str(v or ""))
    return int(m.group()) if m else None


def _num(v):
    if isinstance(v, dict):
        v = _pick(v, "total", "count")
    digits = re.sub(r"\D", "", str(v or ""))
    return int(digits) if digits else 0


class ScholarClient:
    BASE = "https://api.brightdata.com/datasets/v3"

    def enabled(self):
        return bool(C.BRIGHT_DATA_API_KEY and C.BRIGHT_DATA_SCHOLAR_ID)

    def _headers(self):
        return {"Authorization": "Bearer " + C.BRIGHT_DATA_API_KEY}

    def _run(self, inputs):
        def call():
            r = requests.post(f"{self.BASE}/scrape", params={"dataset_id": C.BRIGHT_DATA_SCHOLAR_ID, "format": "json"},
                              headers=self._headers(), json=inputs, timeout=180)
            r.raise_for_status()
            return r.json()

        data = retry(call)
        if isinstance(data, dict) and data.get("snapshot_id"):       # asynchronous collection
            data = self._poll(data["snapshot_id"])
        return data if isinstance(data, list) else [data]

    def _poll(self, snapshot_id, timeout=150):
        end = time.time() + timeout
        while time.time() < end:
            p = requests.get(f"{self.BASE}/progress/{snapshot_id}", headers=self._headers(), timeout=30).json()
            if p.get("status") == "ready":
                r = requests.get(f"{self.BASE}/snapshot/{snapshot_id}", params={"format": "json"},
                                 headers=self._headers(), timeout=120)
                r.raise_for_status()
                return r.json()
            if p.get("status") == "failed":
                raise RuntimeError("Scholar scrape failed")
            time.sleep(3)
        raise TimeoutError("Scholar scrape timed out")

    @staticmethod
    def _flatten(items):
        out = []
        for it in items:
            nested = next((it[k] for k in ("results", "articles", "organic_results", "items") if isinstance(it.get(k), list)), None)
            out.extend(nested if nested is not None else [it])
        return out

    @staticmethod
    def _norm(it):
        title = _pick(it, "title", "name", "article_title")
        if not title:
            return None
        pub = _pick(it, "publication_info", "publication", "authors", "snippet_authors")
        return {
            "title": str(title),
            "year": _year(_pick(it, "year", "publication_year", "date") or pub),
            "authors": str(_pick(it, "authors", "author") or ""),
            "url": _pick(it, "url", "link", "result_url", "article_url"),
            "snippet": str(_pick(it, "snippet", "description", "abstract") or ""),
            "cited_by_count": _num(_pick(it, "cited_by", "cited_by_count", "citations")),
            "cited_by_url": _pick(it, "cited_by_url", "cited_by_link"),
            "related_url": _pick(it, "related_articles_url", "related_url", "related_articles_link"),
        }

    def search(self, query, limit=20):
        if C.BRIGHT_DATA_SCHOLAR_INPUT_MODE == "keyword":
            inp = {"keyword": query}
        else:
            inp = {"url": "https://scholar.google.com/scholar?q=" + quote_plus(query)}
        res = [self._norm(i) for i in self._flatten(self._run([inp]))]
        return [r for r in res if r][:limit]

    def expand(self, url, limit=10):
        """Follow a cited-by or related-articles link returned by an earlier search."""
        res = [self._norm(i) for i in self._flatten(self._run([{"url": url}]))]
        return [r for r in res if r][:limit]
