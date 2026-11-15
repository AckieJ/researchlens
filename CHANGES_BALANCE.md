# v7: the map now shows criticism, conflicts and gaps, not only agreement

## Why the map only showed compatible sources
Reading the code, the bias was not one bug but four small ones that all push the same way:

| Where | What happened | Effect |
|---|---|---|
| Search (`stages.discover`) | Every query was phrased like the question. | Papers that challenge the premise (null results, failed replications, harms) were never retrieved. |
| Cut-offs (`discover`, `prelim_rank`) | Candidates were cut from the *end* of the list, then the top N were kept by similarity to the question. | The critical papers sat at the end and ranked lowest, so they were dropped first. |
| Pair matching (`stages.match`) | Pairs were taken in order of embedding similarity, capped by `MAX_PAIRS` (40 in `render.env.example`). | The most similar pairs are near-paraphrases, i.e. agreement. Opposing claims were crowded out before the verifier saw them. |
| Map (frontend) | Gaps lived only in a separate tab, and "supports" lines were as thick as conflict lines. | Even found conflicts were visually drowned out. |

Extraction also asked for "findings" without asking for null or contrary results.

## What changed
**Backend**
- `prompts.understand` also returns `critical_queries` (null results, criticism, harms, replication failures). A deterministic fallback is used if the model omits them.
- `discover` runs them on OpenAlex (and one on Scholar). `reserve_quota` guarantees `CRITICAL_SHARE` (30 %) of the candidate slots and of the kept-paper slots to papers those queries found.
- `match` first reserves `CONTRA_PAIR_SHARE` (50 %) of `MAX_PAIRS` for "tension" pairs (same topic, different direction or significance, lower similarity threshold), then fills the rest by similarity.
- Extraction prompt now asks for null, negative, mixed and hypothesis-contradicting findings.
- `build_flags` stores gap metadata (`flags.meta`) and adds a new **one-sided** flag: a sub-question with several papers but no null, mixed or opposing result.
- `GET /workspaces/{id}/graph` now also returns per-paper `conflict_level`, `conflicts`, `n_limitations`, `n_weak`, plus `gaps` (positioned in their sub-question's wedge) and `balance`.
- Cache safety: `PIPELINE_VERSION` is stamped on every workspace. Finished workspaces, extracted claims from older versions are no longer cloned or reused, so the same question gets a fresh, balanced run.
- Verifier prompts are unchanged. Nothing tells the model to find contradictions; it still judges each pair on its quotes.

**Frontend**
- Gap markers on the map (amber diamond = little or no evidence; purple hexagon = only agreeing evidence), clickable, with an inspector view.
- Papers get halos: red = genuine conflict, orange = apparent, purple = unresolved, amber = stated limitations or weak evidence.
- Conflict lines are thicker and drawn on top; agreement lines are thinner and lighter.
- **Tensions only** button, **Show gaps** toggle, a legend, and counts on every connection chip (a visible `0` is information).
- New **Evidence balance** panel: stacked bar of compared pairs, gap count, and a plain warning when no conflict surfaced ("may mean critical studies were not retrieved").
- Progress screen shows critical-angle papers kept and opposing-direction pairs checked.

## How to apply
1. Redeploy the backend on Render. The `flags.meta` column is added automatically on startup.
2. Redeploy the frontend on Vercel.
3. **Run your question again.** Old workspaces keep their old, biased graph (their gaps still appear on the map, but the conflicts were never searched for).
4. Optional env vars (defaults are fine): `CRITICAL_QUERIES=3`, `CRITICAL_SHARE=0.30`, `CONTRA_PAIR_SHARE=0.50`, `CONTRA_MATCH_THRESHOLD=0.68`, `CONTRA_STRONG_MATCH=0.76`, `SCHOLAR_CRITICAL_QUERIES=1`. With `MAX_PAPERS=15` keep `MAX_PAIRS` at 40 or more.

## Verification and limits
- Added `backend/tests/test_balance.py` (quota, gap geometry, dissent logic). It passes, and the new SQL and `match()` merge logic were checked with stubs.
- Python compiles; every JSX file parses and the frontend bundles with esbuild.
- **Not run against live Gemini, OpenAlex, Bright Data or Tiger Data.** Whether a given topic now shows conflicts depends on what the literature and the retrieved text contain. If a run still shows none, the balance panel says how many critical-angle papers and opposing pairs were checked, which tells you where to look.
- "One-sided" is a heuristic about the retrieved papers, never a claim about the whole field.
