# v9: extraction failures, speed, and Google Scholar diagnosis

## What was wrong
* **"JSONDecodeError: Extra data"** - the model sometimes returns one JSON object followed by more JSON. The old parser cut from the first `{` to the last `}` and failed.
  Worse, with temperature 0 and a fixed seed every retry reproduced the same malformed text, so each failing paper cost **five** identical (slow) calls.
* **Scholar "0 parsable results"** - the app could not tell a CAPTCHA, a cookie-consent page, a JavaScript wall, a changed layout and a real empty search apart, and it cached the useless page for 7 days.

## What changed (backend only)
| Area | Change |
|---|---|
| Claim extraction | `parse_json` reads the first JSON value and merges back-to-back objects; a bad reply is re-asked **once** with a different seed (never 5 identical calls) and is never cached |
| Speed | `GEMINI_THINKING_LEVEL` (Gemini 3.x; rejected values are auto-disabled); extractor text default 40k -> 30k characters; `progress.llm` shows calls / cache hits / bad replies / seconds |
| Scholar parsing | classic markup plus two fallbacks; only pages that contain results are cached (new cache key, old junk ignored); the lane stops after the first unusable page and says what it saw |
| Scholar diagnosis | `GET /diagnostics/scholar` fetches one page and reports its type, parsed count and an excerpt (`?raw=true` adds the HTML head, `?zone=NAME` tests another zone) |
| Reuse | `PIPELINE_VERSION` bumped so earlier runs that lost papers to the parse bug are not cloned |

## Apply
Redeploy the backend and add the env lines from `render.env.example` (new section at the bottom). No frontend change.

## Debug Scholar in two minutes
1. Open `https://<your-api>/diagnostics/scholar?raw=true`
2. `parsed_results > 0` -> Scholar works. `summary` says "consent wall", "captcha" or "javascript wall" -> Google is not serving results to that zone.
3. Try another zone: create a **SERP API** zone in Bright Data and open `/diagnostics/scholar?zone=<that zone>`. If it parses, set `BRIGHT_DATA_SCHOLAR_ZONE` to it.
4. If nothing parses, send the `summary` and `html_head` fields and the selectors in `clients/scholar_parse.py` can be adjusted.
