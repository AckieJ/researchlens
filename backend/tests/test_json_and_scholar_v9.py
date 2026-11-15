import json

from app.clients import gemini
from app.clients.scholar_parse import describe, fingerprint, parse_scholar_html
from app.clients.util import retry


def test_parse_json_extra_data_two_objects():
    # the real failure: a valid object followed by more JSON ("Extra data: line 17 column 4")
    txt = '{"claims":[{"quote":"a"}]}\n{"claims":[{"quote":"b"}]}'
    assert [c["quote"] for c in gemini.parse_json(txt)["claims"]] == ["a", "b"]


def test_parse_json_trailing_text_and_fences():
    assert gemini.parse_json('```json\n{"x": 1}\n```\nHope this helps!') == {"x": 1}
    assert gemini.parse_json('Here you go: {"x": {"y": [1,2]}} thanks') == {"x": {"y": [1, 2]}}
    assert gemini.parse_json('[{"claims": []}]') == [{"claims": []}]


def test_parse_json_nothing_raises_and_is_not_retried():
    try:
        gemini.parse_json("sorry, no json")
        assert False
    except json.JSONDecodeError:
        pass
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        raise gemini.BadModelReply("bad")
    try:
        retry(fn, tries=5)
    except gemini.BadModelReply:
        pass
    assert calls["n"] == 1            # identical retries would reproduce the same text: do not repeat


def test_generate_json_reasks_once_with_changed_seed(monkeypatch=None):
    seen = []
    orig = gemini._once
    gemini._once = lambda model, system, prompt, kw, lk: (seen.append((kw.get("seed"), prompt)) or (_ for _ in ()).throw(gemini.BadModelReply("x"))) if len(seen) == 0 else (seen.append((kw.get("seed"), prompt)) or {"ok": True})
    old = gemini.C.REUSE_CACHE
    gemini.C.REUSE_CACHE = False
    try:
        import sys, types as _t
        out = gemini.generate_json("p")
    finally:
        gemini._once = orig
        gemini.C.REUSE_CACHE = old
    assert out == {"ok": True} and len(seen) == 2 and seen[1][0] == seen[0][0] + 1 and "ONE valid JSON" in seen[1][1]


CLASSIC = """<html><head><title>virtual reality - Google Scholar</title></head><body>
<div class="gs_r gs_or gs_scl"><div class="gs_ri"><h3 class="gs_rt"><a href="https://doi.org/10.1/x">VR in classrooms: a randomized trial</a></h3>
<div class="gs_a">A Lee - Computers &amp; Education, 2023 - elsevier.com</div><div class="gs_rs">Students improved.</div>
<div class="gs_fl"><a href="/scholar?cites=1">Cited by 9</a></div></div></div></body></html>"""

NO_WRAPPER = """<html><head><title>x - Google Scholar</title></head><body>
<div class="gs_r gs_or"><h3 class="gs_rt"><a href="https://example.org/p">Immersive learning environments and retention</a></h3>
<div class="gs_a">B Kim - Journal of Learning, 2022 - example.org</div><div class="gs_rs">Retention did not differ between groups after six weeks of use.</div></div></body></html>"""

GENERIC = """<html><head><title>Scholar</title></head><body><div class="result"><h3><a href="https://example.org/q">Head-mounted displays in secondary education: a review</a></h3>
<div>C Roe - Educational Review, 2021 - example.org</div><div>This review of 40 studies found mixed evidence for learning gains across subjects and ages.</div></div></body></html>"""

CONSENT = "<html><head><title>Before you continue to Google</title></head><body>Before you continue to Google. We use cookies</body></html>"
EMPTY_OK = "<html><head><title>q - Google Scholar</title></head><body><p>Your search did not match any articles.</p></body></html>"


def test_parser_variants():
    a = parse_scholar_html(CLASSIC)[0]
    assert a["title"].startswith("VR in classrooms") and a["year"] == 2023 and a["cited_by_count"] == 9
    b = parse_scholar_html(NO_WRAPPER)
    assert len(b) == 1 and b[0]["year"] == 2022 and "Retention did not differ" in b[0]["snippet"]
    c = parse_scholar_html(GENERIC)
    assert len(c) == 1 and c[0]["year"] == 2021 and c[0]["authors"].startswith("C Roe")


def test_fingerprint_classifies_pages():
    assert "consent wall" in fingerprint(CONSENT)["flags"]
    assert fingerprint(EMPTY_OK)["flags"] == ["no matching articles"]
    assert fingerprint(CLASSIC)["flags"] == [] and fingerprint(CLASSIC)["gs_ri"] == 1
    assert "consent wall" in describe(fingerprint(CONSENT))
    assert parse_scholar_html(CONSENT) == [] and parse_scholar_html("") == []
