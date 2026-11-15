"""Thin psycopg helpers. Vectors are passed as text and cast with ::vector, so no extra adapter is needed."""
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import DATABASE_URL

_pool = None


def pool():
    global _pool
    if _pool is None:
        _pool = ConnectionPool(DATABASE_URL, min_size=1, max_size=12, open=True,
                               kwargs={"row_factory": dict_row, "autocommit": True})
    return _pool


def q(sql, params=None):
    with pool().connection() as c:
        cur = c.execute(sql, params)
        return cur.fetchall() if cur.description else []


def one(sql, params=None):
    rows = q(sql, params)
    return rows[0] if rows else None


def ex(sql, params=None):
    with pool().connection() as c:
        c.execute(sql, params)


def vec(v):
    return "[" + ",".join(f"{float(x):.6f}" for x in v) + "]"
