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
from .scholar_parse import BASE, describe, fingerprint, parse_scholar_html
from .util import retry

_last = {}
_lock = threading.Lock()
# Usage counters so the UI / status endpoint can show whether Bright Data is really being used.
STATS = {"scholar_requests": 0, "scholar_cache_hits": 0, "scholar_blocked": 0,
         "unlocker_requests": 0, "unlocker_cache_hits": 0}


def bump(key, n=1):
    with _lock:
        STATS[key] = STATS.get(key, 0) + n


def snapshot():
    with _lock:
        return dict(STATS)

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
            bump("unlocker_cache_hits")
            return cached
        bump("unlocker_requests")
        _throttle(urlparse(url).netloc)
        r = _unlock(url, C.BRIGHT_DATA_UNLOCKER_ZONE)
        text = pdf_to_text(r.content) if r.content[:5] == b"%PDF-" else html_to_text(r.text)
        _cache_put(h, url, text)
        return text


class ScholarClient:
    """Create one per pipeline stage; the request cap and the 'blocked' flag live on the instance.

    Pages are cached only when they contain parsable results, so a CAPTCHA, consent wall or changed layout is never
    remembered for a week. The first unusable page stops the lane for this run and says what it saw."""

    def __init__(self):
        self.requests = 0
        self.blocked = False
        self.failed = None          # reason string once a page was unusable
        self.last = None            # fingerprint of the most recent page

    def enabled(self):
        return bool(C.BRIGHT_DATA_API_KEY and (C.BRIGHT_DATA_SCHOLAR_ZONE or C.BRIGHT_DATA_UNLOCKER_ZONE) and not _fatal["msg"])

    def describe_last(self):
        return describe(self.last)

    def _fetch(self, url):
        """Return (html, cache_key, from_cache). Raises ScholarBlocked for CAPTCHA/consent/JS walls and after an unusable page."""
        if urlparse(url).hostname != SCHOLAR_HOST:
            raise NotAllowed(url)
        if self.blocked or self.failed:
            raise ScholarBlocked(self.failed or "Google Scholar showed a CAPTCHA earlier in this run")
        key = hashlib.sha256(("scholar2:" + url).encode()).hexdigest()     # scholar2: = only good pages are stored
        cached = _cache_get(key)
        if cached is not None:
            bump("scholar_cache_hits")
            return cached, key, True
        if self.requests >= C.SCHOLAR_MAX_REQUESTS:
            raise RuntimeError(f"Scholar request cap reached ({C.SCHOLAR_MAX_REQUESTS})")
        self.requests += 1
        bump("scholar_requests")
        _throttle(SCHOLAR_HOST, C.SCHOLAR_MIN_INTERVAL)
        html = _unlock(url, C.BRIGHT_DATA_SCHOLAR_ZONE or C.BRIGHT_DATA_UNLOCKER_ZONE).text
        return html, key, False

    def _results(self, url, limit):
        html, key, cached = self._fetch(url)
        items = parse_scholar_html(html)[:limit]
        self.last = fingerprint(html)
        if items:
            if not cached:
                _cache_put(key, url, html)
            return items
        flags = self.last["flags"]
        if "captcha" in flags or "consent wall" in flags or "javascript wall" in flags or "not a Scholar page" in flags:
            self.blocked = True
            bump("scholar_blocked")
            self.failed = f"Google Scholar did not serve results ({describe(self.last)})"
            raise ScholarBlocked(self.failed)
        if "no matching articles" not in flags:                              # a page with no results and no explanation
            bump("scholar_blocked")
            self.failed = f"Google Scholar page could not be parsed ({describe(self.last)})"
            raise ScholarBlocked(self.failed)
        return []                                                            # a legitimate empty search

    def search(self, query, limit=20):
        url = f"{BASE}scholar?q={quote_plus(query)}&hl=en&gl=us&as_sdt=0,5&as_vis=1&num={min(max(limit, 1), 20)}"
        return self._results(url, limit)

    def expand(self, url, limit=10):
        """Follow a cited-by or related-articles link returned by an earlier search."""
        url = urljoin(BASE, url)
        url += ("&" if "?" in url else "?") + f"num={min(max(limit, 1), 20)}"
        return self._results(url, limit)


def fatal_message():
    return _fatal["msg"]


def reset_fatal():
    _fatal["msg"] = None
