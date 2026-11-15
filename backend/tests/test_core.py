"""Pure-logic tests (no database, network, or API keys needed): run `pytest` from backend/."""
from app.clients.allowlist import allowed
from app.pipeline.dedupe import dedupe
from app.pipeline.layout import assign_angles, child_angles, evidence_strength, minmax, radius, relevance
from app.pipeline.text import (comparability, find_doi, locate, norm_doi, normalize, passage, quote_ok, title_sim)
from app.pipeline import prompts

TEXT = "[[page 1]]\nIntro text.\n[[page 2]]\nParticipants in the tutor group improved by 25% after 12 weeks (p < 0.01), compared with\ncontrols."


def test_quote_validation_is_verbatim_but_whitespace_tolerant():
    assert quote_ok("Participants in the tutor group improved by 25% after 12 weeks (p < 0.01), compared with controls.", TEXT)
    assert not quote_ok("Participants in the tutor group improved by 40% after 12 weeks.", TEXT)
    assert not quote_ok("too short", TEXT)


def test_quote_handles_curly_quotes_and_hyphenation():
    assert quote_ok("The students\u2019 scores im-\nproved substantially over the term", "x The students' scores improved substantially over the term y")


def test_locate_page():
    assert locate(TEXT, "Participants in the tutor group improved by 25% after 12 weeks") == "p. 2"
    assert locate(TEXT, "this is not in the paper at all, really") is None


def test_passage_contains_quote():
    assert "improved by 25%" in passage(TEXT, "improved by 25% after 12 weeks", width=20)


def test_doi_helpers():
    assert norm_doi("https://doi.org/10.1000/ABC") == "10.1000/abc"
    assert find_doi("see doi 10.1234/xyz.5678, thanks") == "10.1234/xyz.5678"


def test_dedupe_by_doi_and_title():
    existing = [{"id": "p1", "doi": "10.1/a", "title": "AI tutors and learning", "year": 2024}]
    cands = [
        {"doi": "https://doi.org/10.1/A", "title": "x", "year": 2024, "lane": "A", "query": "q1"},
        {"title": "AI Tutors and Learning.", "year": 2024, "lane": "B", "query": "q2"},
        {"title": "Something else entirely", "year": 2020, "lane": "A", "query": "q1"},
    ]
    new, dups, extra = dedupe(cands, existing)
    assert dups == 2 and len(new) == 1 and len(extra) == 2


def test_dedupe_merges_fields_and_sources_within_candidates():
    new, dups, _ = dedupe([{"title": "Same paper title here", "year": 2022, "lane": "A", "query": "a"},
                           {"title": "Same paper title here", "year": 2022, "lane": "B", "query": "b", "doi": "10.1/z"}])
    assert dups == 1 and new[0]["doi"] == "10.1/z" and len(new[0]["sources"]) == 2


def test_comparability_flags_duration_mismatch_not_false_match():
    c = comparability({"duration": "12 weeks", "population": "adults"}, {"duration": "2 weeks", "population": "adults"})
    assert c["same_duration"] is False and c["same_population"] is True and c["same_measure"] is None


def test_radius_closer_for_more_relevant():
    assert radius(0.9) < radius(0.5) < radius(0.1)


def test_angles_do_not_overlap_and_stay_in_sector():
    ang = assign_angles({0: ["a", "b", "c"], 1: ["d"]}, 2)
    assert 0 <= ang["a"] < ang["b"] < ang["c"] < 180 and 180 <= ang["d"] < 360
    assert len(set(child_angles(90, 3))) == 3


def test_relevance_bounds_and_evidence():
    assert 0 <= relevance(1, 1, 1, 1) <= 1
    assert evidence_strength("randomized controlled trial", 1000, "full") > evidence_strength("case report", 5, "abstract")
    assert minmax([1, 1]) == [0.5, 0.5]


def test_allowlist():
    allow = [("ncbi.nlm.nih.gov", "/pmc"), ("arxiv.org", "")]
    assert allowed("https://www.ncbi.nlm.nih.gov/pmc/articles/PMC1/", allow)
    assert not allowed("https://www.ncbi.nlm.nih.gov/books/x", allow)
    assert allowed("https://arxiv.org/pdf/1234.5678", allow)
    assert not allowed("https://scholar.google.com/scholar?q=x", allow)
    assert not allowed("ftp://arxiv.org/x", allow)


def test_title_sim():
    assert title_sim("Hello, World!", "hello world") > 0.95


def test_prompts_contain_non_negotiable_rules():
    assert "VERBATIM" in prompts.EXTRACT_SYSTEM
    assert "does NOT refute" in prompts.VERIFY_SYSTEM
    assert "Never say a paper is simply right" in prompts.CHAT_SYSTEM
