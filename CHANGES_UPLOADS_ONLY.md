# Uploads-only mode (skip the web search)

On the home page, after adding 2+ PDFs, tick **"Use only my uploaded papers: skip the web search"**.

Skipped: Gemini-generated search queries are not used, OpenAlex/Scholar discovery, citation expansion, Europe PMC / Bright Data text fetching.
Still runs: Gemini interpretation of the question, embeddings, claim extraction (quote-validated), matching, verification, flags, layout.
Also still runs: one OpenAlex lookup per upload that contains a DOI (fills in title/year/references) and the Crossref retraction check.

Limits: needs >= 2 PDFs (API returns 400 otherwise); scanned/image-only PDFs have no text and are left out with a warning;
the "research gaps" view only reflects your uploaded library. API: `POST /workspaces` form field `web_search=false`.
No database change. Redeploy backend and frontend.
