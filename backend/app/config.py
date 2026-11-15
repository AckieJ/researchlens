import os
import re


def _env(*names, default=""):
    """First non-empty env var among `names`, stripped of whitespace and accidental wrapping quotes.
    (Render's UI keeps quotes literally, so DATABASE_URL="postgres://..." would otherwise fail.)"""
    for n in names:
        v = os.getenv(n)
        if v is not None and v.strip().strip("\"'").strip():
            return v.strip().strip("\"'").strip()
    return default


def _b(name, default=False):
    return _env(name, default=str(default)).lower() in ("1", "true", "yes")


def _i(name, default):
    try:
        return int(float(_env(name, default=str(default))))
    except ValueError:
        return default


def _f(name, default):
    try:
        return float(_env(name, default=str(default)))
    except ValueError:
        return default


DATABASE_URL = _env("DATABASE_URL", default="postgresql://postgres:postgres@localhost:5432/researchlens")
if DATABASE_URL.startswith("postgres://"):          # psycopg accepts both, normalise anyway
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://"):]
REDIS_URL = _env("REDIS_URL", default="redis://localhost:6379/0")
RUN_INLINE = _b("RUN_INLINE")

GEMINI_API_KEY = _env("GEMINI_API_KEY", "GOOGLE_API_KEY")
GEMINI_MODEL = _env("GEMINI_MODEL", default="gemini-2.5-flash")
GEMINI_VERIFY_MODEL = _env("GEMINI_VERIFY_MODEL", default=GEMINI_MODEL)
# EMBEDDING_MODEL is accepted as an alias of GEMINI_EMBED_MODEL
GEMINI_EMBED_MODEL = _env("GEMINI_EMBED_MODEL", "EMBEDDING_MODEL", default="gemini-embedding-001")
EMBED_DIM = _i("EMBED_DIM", 768)
# Free-tier embedding quota is ~30,000 tokens per minute. Stay under it by pacing requests.
EMBED_TOKENS_PER_MIN = _i("EMBED_TOKENS_PER_MIN", 22000)
EMBED_PAPER_CHARS = _i("EMBED_PAPER_CHARS", 1200)   # abstract characters embedded per paper
# Gemini 3.x models recommend leaving temperature at its default; set GEMINI_TEMPERATURE=0 to force it.
GEMINI_TEMPERATURE = _env("GEMINI_TEMPERATURE", default="")

BRIGHT_DATA_API_KEY = _env("BRIGHT_DATA_API_KEY")
BRIGHT_DATA_UNLOCKER_ZONE = _env("BRIGHT_DATA_UNLOCKER_ZONE")
# Zone used for Google Scholar pages (defaults to the Web Unlocker zone above)
BRIGHT_DATA_SCHOLAR_ZONE = _env("BRIGHT_DATA_SCHOLAR_ZONE")
SCHOLAR_MIN_INTERVAL = _f("SCHOLAR_MIN_INTERVAL", 5)   # seconds between Scholar requests
SCHOLAR_MAX_REQUESTS = _i("SCHOLAR_MAX_REQUESTS", 20)     # per client instance (per pipeline stage)

OPENALEX_API_KEY = _env("OPENALEX_API_KEY")
# Optional contact email for User-Agent; no longer an authentication mechanism.
OPENALEX_EMAIL = _env("OPENALEX_EMAIL")

MAX_PAPERS = _i("MAX_PAPERS", 30)
MAX_CANDIDATES = _i("MAX_CANDIDATES", 150)
MATCH_THRESHOLD = _f("MATCH_THRESHOLD", 0.80)
STRONG_MATCH = _f("STRONG_MATCH", 0.88)   # similarity that overrides an outcome-family mismatch
MAX_PAIRS = _i("MAX_PAIRS", 300)
WORKERS = _i("LLM_CONCURRENCY", 4)
MAX_TEXT_CHARS = _i("MAX_TEXT_CHARS", 100000)
FULL_TEXT_MIN = 3000   # fewer characters than this = treat as abstract-only

ALLOWLIST_PATH = os.getenv("ALLOWLIST_PATH", os.path.join(os.path.dirname(__file__), "..", "config", "allowlist.yaml"))
EXTRA_ALLOWED_DOMAINS = [d.strip() for d in os.getenv("EXTRA_ALLOWED_DOMAINS", "").split(",") if d.strip()]
CORS_ORIGINS = [o.strip().strip("\"'").rstrip("/") for o in _env("CORS_ORIGINS", default="http://localhost:5173").split(",") if o.strip()]

# Do not list all user research questions publicly without authentication.
PUBLIC_WORKSPACE_LIST = _b("PUBLIC_WORKSPACE_LIST", False)

# Any *.vercel.app origin (production + preview deployments) may call the API directly when VITE_API_URL is used.
CORS_ORIGIN_REGEX = _env("CORS_ORIGIN_REGEX", default=r"https://.*\.vercel\.app")

# Render sets RENDER_EXTERNAL_URL automatically; used for a self-ping so a running job keeps the free instance awake.
SELF_URL = _env("SELF_URL", "RENDER_EXTERNAL_URL")


def config_problems():
    """Human-readable list of misconfigurations that would otherwise fail silently or confusingly."""
    out = []
    uuid = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
    if not GEMINI_API_KEY:
        out.append("GEMINI_API_KEY is not set.")
    if not DATABASE_URL or "localhost" in DATABASE_URL and os.getenv("RENDER"):
        out.append("DATABASE_URL is not set (still the localhost default).")
    if BRIGHT_DATA_API_KEY and not BRIGHT_DATA_UNLOCKER_ZONE:
        out.append("BRIGHT_DATA_UNLOCKER_ZONE is empty; Scholar and full-text lanes are disabled.")
    for name, z in (("BRIGHT_DATA_UNLOCKER_ZONE", BRIGHT_DATA_UNLOCKER_ZONE), ("BRIGHT_DATA_SCHOLAR_ZONE", BRIGHT_DATA_SCHOLAR_ZONE)):
        if z and (z == BRIGHT_DATA_API_KEY or uuid.match(z)):
            out.append(f"{name} looks like an API key, not a zone name. Use the zone NAME from the Bright Data dashboard "
                       "(Proxies & Scraping Infrastructure -> your Web Unlocker zone, e.g. 'web_unlocker1').")
    if EMBED_DIM != 768:
        out.append(f"EMBED_DIM={EMBED_DIM} but db/schema.sql uses vector(768); they must match.")
    if RUN_INLINE is False and REDIS_URL.startswith("redis://localhost") and os.getenv("RENDER"):
        out.append("RUN_INLINE is false but REDIS_URL is not configured; jobs cannot run. Set RUN_INLINE=true on Render free tier.")
    return out
