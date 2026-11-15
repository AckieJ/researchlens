"""Bright Data clients.

UnlockerClient - Web Unlocker: fetch publicly accessible, allowlisted pages (open-access full text).
ScholarClient  - Google Scholar: fetches Scholar result pages through the same Web Unlocker API and parses the HTML
                 itself (clients/scholar_parse.py). There is no prebuilt Scholar scraper to configure.

Scholar is rate limited hard (one request per SCHOLAR_MIN_INTERVAL seconds), capped per run, cached, and the client
stops for the rest of the run as soon as Google serves a CAPTCHA.
"""
import hashlib
import threading
import time
from urllib.parse import quote_plus, urljoin, urlparse

import requests

from .. import config as C
from ..db import ex, one
from ..pipeline.text import html_to_text, pdf_to_text
from .allowlist import allowed
from .scholar_parse import BASE, looks_blocked, parse_scholar_html
from .util import retry

_last = {}
_lock = threading.Lock()
SCHOLAR_HOST = "scholar.google.com"


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


class ScholarBlocked(Exception):
    pass


class BrightDataError(Exception):
    """Bright Data refused the request for a configuration reason (bad key / zone). Not retried."""


_fatal = {"msg": None}   # set once a credential/zone problem is detected; later calls fail instantly


def _unlock(url, zone):
    """POST to the Web Unlocker API and return the response. Config errors (400/401/403) fail fast with a clear message."""
    if _fatal["msg"]:
        raise BrightDataError(_fatal["msg"])

    def call():
        r = requests.post(
            "https://api.brightdata.com/request",
            headers={"Authorization": "Bearer " + C.BRIGHT_DATA_API_KEY},
            json={"zone": zone, "url": url, "format": "raw"},
            timeout=90,
        )
        if r.status_code in (400, 401, 403):
            detail = r.headers.get("x-brd-err-msg") or r.headers.get("x-luminati-error") or r.text[:200]
            _fatal["msg"] = (f"Bright Data rejected the request (HTTP {r.status_code}: {detail.strip()}). "
                             f"Check BRIGHT_DATA_API_KEY and that BRIGHT_DATA_UNLOCKER_ZONE ('{zone}') is the exact NAME "
                             "of an active Web Unlocker zone.")
            raise BrightDataError(_fatal["msg"])
        r.raise_for_status()
        return r
    return retry(call)


def _cache_get(key):
    hit = one("SELECT body FROM fetch_cache WHERE url_hash=%s AND fetched_at > now() - interval '7 days'", (key,))
    return hit["body"] if hit else None


def _cache_put(key, url, body):
    ex("INSERT INTO fetch_cache (url_hash,url,body) VALUES (%s,%s,%s) "
       "ON CONFLICT (url_hash) DO UPDATE SET body=EXCLUDED.body, fetched_at=now()", (key, url, body))


class UnlockerClient:
    def enabled(self):
        return bool(C.BRIGHT_DATA_API_KEY and C.BRIGHT_DATA_UNLOCKER_ZONE and not _fatal["msg"])

    def fetch_text(self, url):
        """Return extracted text of an allowlisted public page or PDF (cached for 7 days)."""
        if not allowed(url):
            raise NotAllowed(url)
        if not self.enabled():
            raise RuntimeError("Bright Data Web Unlocker is not configured")
        h = hashlib.sha256(url.encode()).hexdigest()
        cached = _cache_get(h)
        if cached is not None:
            return cached
        _throttle(urlparse(url).netloc)
        r = _unlock(url, C.BRIGHT_DATA_UNLOCKER_ZONE)
        text = pdf_to_text(r.content) if r.content[:5] == b"%PDF-" else html_to_text(r.text)
        _cache_put(h, url, text)
        return text


class ScholarClient:
    """Create one per pipeline stage; the request cap and the 'blocked' flag live on the instance."""

    def __init__(self):
        self.requests = 0
        self.blocked = False

    def enabled(self):
        return bool(C.BRIGHT_DATA_API_KEY and (C.BRIGHT_DATA_SCHOLAR_ZONE or C.BRIGHT_DATA_UNLOCKER_ZONE) and not _fatal["msg"])

    def _page(self, url):
        if urlparse(url).hostname != SCHOLAR_HOST:
            raise NotAllowed(url)
        if self.blocked:
            raise ScholarBlocked("Google Scholar showed a CAPTCHA earlier in this run")
        key = hashlib.sha256(("scholar:" + url).encode()).hexdigest()
        cached = _cache_get(key)
        if cached is not None:
            return cached
        if self.requests >= C.SCHOLAR_MAX_REQUESTS:
            raise RuntimeError(f"Scholar request cap reached ({C.SCHOLAR_MAX_REQUESTS})")
        self.requests += 1
        _throttle(SCHOLAR_HOST, C.SCHOLAR_MIN_INTERVAL)
        html = _unlock(url, C.BRIGHT_DATA_SCHOLAR_ZONE or C.BRIGHT_DATA_UNLOCKER_ZONE).text
        if looks_blocked(html):
            self.blocked = True
            raise ScholarBlocked("Google Scholar returned a CAPTCHA / unusual-traffic page")
        _cache_put(key, url, html)
        return html

    def search(self, query, limit=20):
        url = f"{BASE}scholar?q={quote_plus(query)}&hl=en&as_sdt=0,5&as_vis=1&num={min(max(limit, 1), 20)}"
        return parse_scholar_html(self._page(url))[:limit]

    def expand(self, url, limit=10):
        """Follow a cited-by or related-articles link returned by an earlier search."""
        url = urljoin(BASE, url)
        url += ("&" if "?" in url else "?") + f"num={min(max(limit, 1), 20)}"
        return parse_scholar_html(self._page(url))[:limit]


def fatal_message():
    return _fatal["msg"]


def reset_fatal():
    _fatal["msg"] = None
