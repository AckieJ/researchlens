"""Apply db/schema.sql. Run: python -m app.init_db"""
from pathlib import Path

from .db import ex


def find_schema():
    here = Path(__file__).resolve()
    for base in (here.parents[1], here.parents[2]):
        p = base / "db" / "schema.sql"
        if p.exists():
            return p
    raise FileNotFoundError("db/schema.sql not found")


if __name__ == "__main__":
    path = find_schema()
    ex(path.read_text())
    print(f"Schema applied from {path}")
