"""No database, network or API keys needed."""
from app.pipeline.balance import (clean_queries, fallback_critical_queries, gap_angle, gap_sector, has_dissent,
                                  paper_conflict_level, reserve_quota, summarize_edges)


def test_reserve_quota_keeps_critical_papers_that_a_plain_cut_would_drop():
    items = [("agree", i) for i in range(20)] + [("critic", i) for i in range(5)]     # critics sit at the END of the list
    plain = items[:10]
    assert not any(k == "critic" for k, _ in plain)                                    # the old behaviour
    out = reserve_quota(items, lambda x: x[0] == "critic", 10, 0.3)
    assert len(out) == 10 and sum(1 for k, _ in out if k == "critic") == 3
    assert [x for x in out if x[0] == "agree"] == items[:7]                            # order preserved, best agreeing ones kept


def test_reserve_quota_edge_cases():
    items = list(range(5))
    assert reserve_quota(items, lambda x: True, 10, 0.3) == items                       # under the cap: untouched
    assert reserve_quota(range(10), lambda x: False, 4, 0.5) == [0, 1, 2, 3]            # no priority items: plain cut
    assert len(reserve_quota(range(10), lambda x: x >= 8, 4, 1.0)) == 4                 # fewer priority items than slots


def test_fallback_and_clean_queries():
    q = fallback_critical_queries(["vr in education"], 3)
    assert len(q) == 3 and all(x.startswith("vr in education") for x in q)
    assert fallback_critical_queries([], 3) == []
    assert clean_queries(["A", "a ", "", None, "B"], 5) == ["A", "B"]
    assert clean_queries("single string", 3) == ["single string"]


def test_gap_geometry_matches_layout_wedges():
    assert gap_angle(0, 4) == 45 and gap_angle(3, 4) == 315 and gap_angle(0, 1) == 180


def test_gap_sector_recovers_index_from_old_flag_text():
    subs = ["Does it work for adults?", "Long-term retention", "Cost"]
    assert gap_sector("Not found in the papers examined: Long-term retention (1 paper(s) clearly address it).", subs) == 1
    assert gap_sector("unrelated text", subs) is None


def test_has_dissent():
    up = {"direction": "increase", "significance": "significant"}
    assert not has_dissent([up, dict(up)], False)
    assert has_dissent([up, dict(up)], True)                                             # verified conflict edge
    assert has_dissent([up, {"direction": "decrease", "significance": "significant"}], False)
    assert has_dissent([up, {"direction": "no_effect", "significance": "not_significant"}], False)
    assert has_dissent([up, {"direction": "increase", "significance": "not_significant"}], False)


def test_edge_summary_and_conflict_level():
    rows = [{"label": "supports_compatible", "pa": "a", "pb": "b"}, {"label": "genuine_contradiction", "pa": "a", "pb": "c"},
            {"label": "unresolved", "pa": "b", "pb": "c"}]
    counts, touched = summarize_edges(rows)
    assert counts["supports_compatible"] == 1 and counts["genuine_contradiction"] == 1
    assert "supports_compatible" not in touched["a"]                                     # agreement is not a conflict marker
    assert paper_conflict_level(touched["a"]) == "genuine"
    assert paper_conflict_level(touched["b"]) == "open"
    assert paper_conflict_level(None) is None
