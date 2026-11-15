"""The fixture below imitates the structure of a Google Scholar results page. If Scholar changes its markup,
update app/clients/scholar_parse.py and paste a freshly saved page into this fixture."""
from app.clients.scholar_parse import looks_blocked, parse_scholar_html

HTML = """
<div id="gs_res_ccl_mid">
 <div class="gs_r gs_or gs_scl">
  <div class="gs_ggs gs_fl"><div class="gs_ggsd"><a href="https://example.org/files/tutor.pdf"><span class="gs_ctg2">[PDF]</span> example.org</a></div></div>
  <div class="gs_ri">
   <h3 class="gs_rt"><span class="gs_ctg2">[PDF]</span><a href="https://doi.org/10.1234/abc.567">AI tutors and learning outcomes: a randomized trial</a></h3>
   <div class="gs_a">A Smith, B Jones&nbsp;- Journal of Learning Science, 2024 - example.org</div>
   <div class="gs_rs">Students using the tutor improved by 25% after 12 weeks compared with controls&hellip;</div>
   <div class="gs_fl"><a href="/scholar?cites=111&amp;as_sdt=2005&amp;hl=en">Cited by 42</a>
     <a href="/scholar?q=related:XYZ:scholar.google.com/&amp;hl=en">Related articles</a> <a href="/scholar?cluster=111">All 5 versions</a></div>
  </div>
 </div>
 <div class="gs_r gs_or gs_scl">
  <div class="gs_ri">
   <h3 class="gs_rt"><a href="https://arxiv.org/abs/2301.00001">Short-term effects of tutoring software</a></h3>
   <div class="gs_a">C Lee - arXiv preprint arXiv:2301.00001, 2023 - arxiv.org</div>
   <div class="gs_rs">No significant improvement after 2 weeks.</div>
   <div class="gs_fl"><a href="/scholar?q=related:ABC:scholar.google.com/&amp;hl=en">Related articles</a></div>
  </div>
 </div>
</div>
"""


def test_parses_results():
    r = parse_scholar_html(HTML)
    assert len(r) == 2
    a, b = r
    assert a["title"] == "AI tutors and learning outcomes: a randomized trial"
    assert a["year"] == 2024 and a["authors"] == "A Smith, B Jones" and a["venue"].startswith("Journal of Learning Science")
    assert a["url"] == "https://doi.org/10.1234/abc.567" and a["pdf_url"] == "https://example.org/files/tutor.pdf"
    assert a["cited_by_count"] == 42 and a["cited_by_url"].startswith("https://scholar.google.com/scholar?cites=111")
    assert a["related_url"].startswith("https://scholar.google.com/scholar?q=related:XYZ")
    assert "improved by 25%" in a["snippet"]
    assert b["year"] == 2023 and b["cited_by_count"] == 0 and b["cited_by_url"] is None and b["pdf_url"] is None


def test_empty_and_blocked_pages():
    assert parse_scholar_html("<html></html>") == []
    assert looks_blocked("<form id='gs_captcha_f'>") and looks_blocked("Our systems have detected unusual traffic")
    assert not looks_blocked(HTML)
