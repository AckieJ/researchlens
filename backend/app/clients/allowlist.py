"""Only domains in config/allowlist.yaml (plus EXTRA_ALLOWED_DOMAINS) may be fetched via Bright Data."""
from functools import lru_cache
from urllib.parse import urlparse

import yaml

from .. import config as C


@lru_cache(maxsize=1)
def entries():
    try:
        with open(C.ALLOWLIST_PATH) as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        data = {}
    raw = list(data.get("allow") or []) + list(data.get("extra") or []) + C.EXTRA_ALLOWED_DOMAINS
    out = []
    for e in raw:
        e = str(e).strip().lower().replace("https://", "").replace("http://", "")
        host, _, path = e.partition("/")
        out.append((host, "/" + path if path else ""))
    return out


def allowed(url, allow=None):
    u = urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        return False
    host, path = u.hostname.lower(), (u.path or "/").lower()
    for h, p in (allow if allow is not None else entries()):
        if (host == h or host.endswith("." + h)) and path.startswith(p):
            return True
    return False
