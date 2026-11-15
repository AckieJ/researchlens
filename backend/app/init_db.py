"""Apply db/schema.sql. Run: python -m app.init_db  (also called from the API on startup; failures are non-fatal there)."""
import sys
from pathlib import Path

from .db import ex


def find_schema():
    here = Path(__file__).resolve()
    for base in (here.parents[1], here.parents[2]):
        p = base / "db" / "schema.sql"
        if p.exists():
            return p
    raise FileNotFoundError("db/schema.sql not found")


def apply():
    path = find_schema()
    ex(path.read_text())
    return path


if __name__ == "__main__":
    try:
        print(f"Schema applied from {apply()}")
    except Exception as e:  # do not stop the web server: /diagnostics will show the DB problem
        print(f"WARNING: schema init failed: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(0)
