"""Thin psycopg helpers. Vectors are passed as text and cast with ::vector, so no extra adapter is needed."""
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import DATABASE_URL

_pool = None


def pool():
    global _pool
    if _pool is None:
        # check_connection: free hosts/DBs drop idle connections; test each one before handing it out.
        # open=False + explicit open avoids crashing at import time when the DB is briefly unreachable.
        _pool = ConnectionPool(
            DATABASE_URL, min_size=1, max_size=12, open=False, check=ConnectionPool.check_connection,
            max_idle=120, max_lifetime=1800, timeout=30,
            kwargs={"row_factory": dict_row, "autocommit": True, "connect_timeout": 15,
                    "keepalives": 1, "keepalives_idle": 30, "keepalives_interval": 10, "keepalives_count": 3},
        )
        _pool.open(wait=False)
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


def exmany(sql, rows):
    """Run one statement for many parameter rows in a single round trip (psycopg pipelines executemany)."""
    if not rows:
        return
    with pool().connection() as c:
        with c.cursor() as cur:
            cur.executemany(sql, rows)
