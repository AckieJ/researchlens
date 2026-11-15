import os


def _b(name, default=False):
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes")


DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/researchlens")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
RUN_INLINE = _b("RUN_INLINE")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_VERIFY_MODEL = os.getenv("GEMINI_VERIFY_MODEL", GEMINI_MODEL)
GEMINI_EMBED_MODEL = os.getenv("GEMINI_EMBED_MODEL", "gemini-embedding-001")
EMBED_DIM = int(os.getenv("EMBED_DIM", "768"))

BRIGHT_DATA_API_KEY = os.getenv("BRIGHT_DATA_API_KEY", "")
BRIGHT_DATA_UNLOCKER_ZONE = os.getenv("BRIGHT_DATA_UNLOCKER_ZONE", "")
# Zone used for Google Scholar pages (defaults to the Web Unlocker zone above)
BRIGHT_DATA_SCHOLAR_ZONE = os.getenv("BRIGHT_DATA_SCHOLAR_ZONE", "")
SCHOLAR_MIN_INTERVAL = float(os.getenv("SCHOLAR_MIN_INTERVAL", "5"))   # seconds between Scholar requests
SCHOLAR_MAX_REQUESTS = int(os.getenv("SCHOLAR_MAX_REQUESTS", "20"))     # per client instance (per pipeline stage)

OPENALEX_API_KEY = os.getenv("OPENALEX_API_KEY", "").strip()
# Optional contact email for User-Agent; no longer an authentication mechanism.
OPENALEX_EMAIL = os.getenv("OPENALEX_EMAIL", "").strip()

MAX_PAPERS = int(os.getenv("MAX_PAPERS", "30"))
MAX_CANDIDATES = int(os.getenv("MAX_CANDIDATES", "150"))
MATCH_THRESHOLD = float(os.getenv("MATCH_THRESHOLD", "0.80"))
STRONG_MATCH = float(os.getenv("STRONG_MATCH", "0.88"))   # similarity that overrides an outcome-family mismatch
MAX_PAIRS = int(os.getenv("MAX_PAIRS", "300"))
WORKERS = int(os.getenv("LLM_CONCURRENCY", "4"))
MAX_TEXT_CHARS = int(os.getenv("MAX_TEXT_CHARS", "100000"))
FULL_TEXT_MIN = 3000   # fewer characters than this = treat as abstract-only

ALLOWLIST_PATH = os.getenv("ALLOWLIST_PATH", os.path.join(os.path.dirname(__file__), "..", "config", "allowlist.yaml"))
EXTRA_ALLOWED_DOMAINS = [d.strip() for d in os.getenv("EXTRA_ALLOWED_DOMAINS", "").split(",") if d.strip()]
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]
