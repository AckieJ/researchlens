"""uploads-only mode: run_workspace must not touch discovery/expansion/web text retrieval. Uses stubs, no DB or network."""
import sys
import types

for name in ("psycopg", "psycopg.rows", "psycopg_pool"):
    if name not in sys.modules:
        m = types.ModuleType(name)
        m.dict_row = None
        m.ConnectionPool = object
        sys.modules[name] = m

from app.pipeline import stages  # noqa: E402


def _run(monkeypatch, web_search):
    calls = []
    for fn in ("set_status", "progress", "embed_papers", "prelim_rank", "expand", "discover", "retrieve_all", "extract_all",
               "verify_pairs", "external_check", "build_flags", "compute_layout", "_bd_progress", "_count_critical_kept"):
        monkeypatch.setattr(stages, fn, lambda *a, _n=fn, **k: calls.append((_n, k)) or ([] if _n in ("prelim_rank",) else 0))
    monkeypatch.setattr(stages, "understand", lambda ws: {"search_queries": ["x"], "critical_queries": []})
    monkeypatch.setattr(stages, "match", lambda ws: [])
    monkeypatch.setattr(stages, "uploads_only", lambda ws: not web_search)
    monkeypatch.setattr(stages.bd, "snapshot", lambda: {}, raising=False)
    monkeypatch.setattr(stages, "Timer", lambda ws: types.SimpleNamespace(to=lambda *a, **k: None, close=lambda: None))
    stages.run_workspace("ws1")
    return calls


def test_uploads_only_skips_web(monkeypatch):
    names = [c[0] for c in _run(monkeypatch, web_search=False)]
    assert "discover" not in names and "expand" not in names
    assert ("retrieve_all", {"offline": True}) in _run(monkeypatch, web_search=False)
    assert "extract_all" in names and "compute_layout" in names


def test_normal_mode_still_searches(monkeypatch):
    names = [c[0] for c in _run(monkeypatch, web_search=True)]
    assert "discover" in names and "expand" in names
