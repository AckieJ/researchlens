# v5: faster and consistent runs

## How to apply
1. Redeploy the backend (Render). The schema migration is idempotent and runs on startup (new tables `llm_cache`, `embed_cache`, new indexes, `workspaces.question_key`).
2. Add the new env vars from `render.env.example` (all optional; defaults are sensible). On a paid Gemini key set `LLM_CONCURRENCY=6`; on the free tier set `GEMINI_RPM=9`.
3. Redeploy the frontend (Vercel).

## Consistency
| Cause of different answers | Fix |
|---|---|
| Model sampled differently each call (Gemini 3.x ran at its default temperature) | temperature 0 + fixed seed for every call |
| Same prompt re-sent to the model | `llm_cache`: identical (model, settings, system, prompt) is answered from the database. Same question -> same search queries -> same papers -> same claims -> same verdicts |
| Same question, new workspace | Finished workspace of the same question (normalised text) or a near-identical one (embedding similarity >= 0.97) is cloned in one transaction |
| Ranking ties / unordered rows | deterministic tie-breaks in ranking, pair matching and verification order; Scholar results always merged after OpenAlex |
| Extraction read a different slice of the paper | deterministic `focus_text`; quotes validated against the FULL text |

## Speed
- Whole-investigation reuse (seconds instead of minutes on repeats).
- Scholar lane runs in parallel with OpenAlex, only for the first 2 queries; Scholar DOI resolution fans out; citation expansion defaults to OpenAlex and runs in parallel.
- Extractor reads at most 40k chars (was 100k) chosen for result density; Gemini 2.5 Flash thinking budget 0.
- Embeddings cached by text (`embed_cache`) and written in one statement; paper inserts parallel; layout rows inserted in one batch.
- Optional `GEMINI_RPM` pacing instead of 429 retry sleeps.
- New DB indexes for the cross-workspace reuse lookups.

## Visibility
`GET /workspaces/<id>/status` -> `progress.timings` (seconds per stage), `progress.text_sources` (how many papers got text from upload / Europe PMC / Bright Data / abstract only), `progress.bright_data` (Scholar + Unlocker requests, cache hits, blocks). The progress screen shows them.
