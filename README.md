# ResearchLens

A claim-level evidence graph for one research question. It gathers papers, extracts testable claims with **verbatim quotes**, compares only claims that address the same hypothesis, and shows where findings agree, genuinely conflict, only *appear* to conflict, or remain unresolved. The graph is radial: the question sits in the center and **distance from the center = relevance** (a navigation aid, not a truth score).

Stack: React + Cytoscape (frontend) · FastAPI + RQ workers (backend) · Tiger Data (Postgres + pgvector) · Gemini · Bright Data · Vultr.

> **Status:** the backend logic that needs no external services is unit-tested (`backend/tests`). The full pipeline, the Bright Data Scholar request format, and the frontend build were **not run against live services** when this repo was generated. Follow "First run checklist" below and expect to adjust small details.

## How it works

```
Browser (React + Cytoscape) -> FastAPI -> Redis/RQ worker -> OpenAlex / Crossref / Europe PMC (APIs)
                                   |                      -> Bright Data Google Scholar scraper (more sources)
                                   |                      -> Bright Data Web Unlocker (allowlisted public pages)
                                   |                      -> Gemini (extract, verify, embed, chat)
                                   v
                       Tiger Data: papers, claims, edges, scores, cache
```

| Stage | Code | What it does |
|---|---|---|
| 0 | `pipeline/stages.ingest_upload` | Parse uploaded PDFs, find DOI, add to library |
| 1 | `stages.understand` | Gemini turns the question into queries, outcome families, sub-questions |
| 2 | `stages.discover` | Lane A (OpenAlex) + Lane B (Google Scholar via Bright Data), resolve to DOIs, de-duplicate |
| 3 | `embed_papers`, `prelim_rank`, `expand`, `retrieve_all` | Rank, citation expansion (second ring), full text via Europe PMC then Web Unlocker, else abstract-only |
| 4 | `extract_all` | Gemini claims; **code rejects any claim whose quote is not found in the source text** |
| 6 | `match` | SQL + pgvector candidate pairs with a comparability checklist |
| 7 | `verify_pairs` | Gemini five-way label + self-check on every genuine contradiction |
| 8 | `build_flags`, `external_check` | Limitations, weak claims, retractions, and library gaps (three separate lists) |
| 9 | `compute_layout` | Relevance score, sectors per sub-question, angles, second ring |
| 10 | `pipeline/impact.py` | New paper: strengthens / challenges / qualifies / leaves unanswered |
| 11 | `pipeline/chat.py` | GraphRAG chat: vector search, one hop along edges, quotes, cited answer |

Relevance = 0.45 cosine(claims, question) + 0.20 outcome match + 0.20 citation centrality + 0.15 evidence strength (each normalized; weights in `pipeline/layout.py`, a starting guess). Radius = `R_MIN + (1 - relevance) * (R_MAX - R_MIN)`; the frontend uses the same constants.

## First run checklist

1. **Accounts and keys:** Gemini API key; Tiger Data service (Postgres with pgvector); Bright Data API key.
2. `cp .env.example .env` and fill it in (see below).
3. **Bright Data setup**
   - Create a **Web Unlocker zone** and put its name in `BRIGHT_DATA_UNLOCKER_ZONE`.
   - In **Scraper APIs**, open the **Google Scholar scraper**, run one query in the playground, and note: the input field it expects (`url` or `keyword`), the output field names, and the dataset/scraper ID. Put the ID in `BRIGHT_DATA_SCHOLAR_ID` and set `BRIGHT_DATA_SCHOLAR_INPUT_MODE`.
   - **Verify and adjust** `ScholarClient` in `backend/app/clients/brightdata.py` (endpoint `datasets/v3/scrape`, async polling, and the field mapping in `_norm`) to match what the playground shows. The Web Unlocker call (`POST https://api.brightdata.com/request`) should work as written; confirm against the current docs.
   - If Scholar is not configured the pipeline still runs on OpenAlex and logs a warning on the progress screen.
4. **Database:** `DATABASE_URL` from Tiger Data. The schema is applied automatically on API start (`python -m app.init_db`). `vector(768)` in `db/schema.sql` must match `EMBED_DIM`.
5. **Run it** (Docker): `docker compose up --build`, then open http://localhost. Without Docker, see "Local development".
6. **Smoke test:** ask a question, watch the progress screen: lane counts, full text vs abstract-only, claims extracted, **quotes rejected** (should be small). Open a red or dashed-red line and confirm both quotations appear in the source.

## Local development

```bash
# backend
cd backend && python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
export $(grep -v '^#' ../.env | xargs)       # or use your own env loader
RUN_INLINE=true python -m app.init_db && RUN_INLINE=true uvicorn app.main:app --reload
# RUN_INLINE=true runs jobs in a thread, so Redis is not needed. For production use `rq worker researchlens`.

# frontend (separate terminal)
cd frontend && npm install && npm run dev      # http://localhost:5173, proxies /api to :8000
```

Tests (no keys or database needed): `cd backend && pytest` (or run the functions in `tests/test_core.py` directly).

## Deploy on Vultr

1. Provision an Ubuntu VM; open ports 80 and 443. Install Docker and the compose plugin.
2. `git clone` the repo, `cp .env.example .env`, fill it in (`RUN_INLINE=false`, `REDIS_URL=redis://redis:6379/0`).
3. `docker compose up -d --build`. Tiger Data stays external; allow the VM's IP if the service restricts connections.
4. For HTTPS, put Caddy or nginx with a certificate in front of the `web` service.
5. Smoke test from the VM: create a workspace and confirm both Bright Data calls succeed (watch `docker compose logs worker`).

## Rules for public pages (enforced in code where possible)

- Only publicly accessible pages; no login, payment or access-control circumvention. `UnlockerClient` refuses any URL not in `backend/config/allowlist.yaml` (or `EXTRA_ALLOWED_DOMAINS`). Google Scholar is reached only via the Scholar scraper, never the Unlocker.
- Check each site's robots.txt and terms before adding a domain. Using Bright Data does not remove that responsibility from the team.
- Requests are limited to one per second per domain, retried with backoff, and cached for 7 days (`fetch_cache`).
- Stored: metadata, extracted claims, and short quotations with a link and DOI. Uploaded PDFs belong to the workspace; do not expose them publicly.
- Every claim records whether it came from full text or an abstract; abstract-only evidence caps verification confidence at 0.6.
- Scholar results that cannot be matched to a DOI are kept at low confidence and **excluded from verdicts unless full text was retrieved**.

## API

| Endpoint | Purpose |
|---|---|
| `POST /workspaces` (form: `question`, `files`) | Create workspace, queue the pipeline |
| `GET /workspaces`, `GET /workspaces/{id}/status` | List; progress counters and stage |
| `GET /workspaces/{id}/graph` | Papers (relevance, radius, angle, parent) and paper-level edges |
| `GET /papers/{id}`, `GET /edges/{id}` | Claims with quotes; side-by-side comparison and verdict |
| `GET /workspaces/{id}/flags` | Limitations, weak claims, library gaps |
| `POST /workspaces/{id}/papers`, `GET /workspaces/{id}/impact/{paper_id}` | Add a paper; impact report |
| `POST /workspaces/{id}/chat` | GraphRAG question and cited answer |

## Validation

Pick a demo topic with documented disagreement and read the key papers yourself. Fill `eval/gold_set.csv` (8-12 hand-labeled pairs, at least three apparent contradictions) and run `cd backend && python ../eval/run_eval.py <workspace_id>`. Report one honest number, e.g. "matched 9 of 11 hand-labeled pairs".

## Differences from the proposal (small, deliberate)

- Extra columns and tables for operation (workspace `status/progress/embedding`, `paper_scores`, `impact_reports`, `claims.workspace_id`, etc.); a `paper_edges` view provides the paper-level summaries.
- Matching requires the same outcome family **or** very high similarity (`STRONG_MATCH`, default 0.88), because model-written family names rarely match exactly.
- When Scholar is not configured, citation expansion falls back to OpenAlex "cited by".
- Entity normalization is lightweight (embeddings do the matching; no alias table yet).
- Second-ring papers that cannot get text are dropped rather than back-filled.

## Known limits

- Scholar scraper field mapping and the model names in `.env` (`GEMINI_MODEL`, etc.) may need adjusting to what your accounts offer.
- Library gaps always mean "not found in the papers examined", never "unstudied".
- A non-significant result never refutes a significant one; the prompts and the self-check pass enforce this, but review verdicts by hand before presenting them.
- No authentication: workspaces are reachable by id. Add auth before exposing the app publicly with private uploads.
