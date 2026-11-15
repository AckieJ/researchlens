# ResearchLens: deploy the LIVE application to Render + Vercel

This repository deliberately **has no offline demo route or fabricated research results**. The user-facing investigation and graph require a functioning backend, Gemini, OpenAlex, Tiger Data, and a processing mechanism.

## 1. Render: API web service

In Render → `researchlens` → Settings → Build:

- Git repository: `AckieJ/researchlens`, branch: `main`
- Root Directory: blank, assuming `backend/` and `frontend/` are at the repo root
- Runtime: Docker
- Dockerfile Path: `./backend/Dockerfile`
- Docker Build Context Directory: `.`
- Docker Command: leave **blank**, so the Dockerfile starts the app and initializes `db/schema.sql`. If you previously set an override, remove it.
- Render Environment variables: `DATABASE_URL`, `GEMINI_API_KEY`, `OPENALEX_API_KEY`, `BRIGHT_DATA_API_KEY`, `BRIGHT_DATA_UNLOCKER_ZONE`, `REDIS_URL`, `RUN_INLINE=false`; optionally `GEMINI_MODEL`, `GEMINI_VERIFY_MODEL`, `GEMINI_EMBED_MODEL`, `EMBED_DIM=768`, `MAX_PAPERS=10`, `MAX_PAIRS=20`, `LLM_CONCURRENCY=2`.
- Tiger Data PostgreSQL must support pgvector and allow the Render service to connect over TLS. The DB user must be able to create or use the `vector` extension.

Try `https://researchlens-mhuq.onrender.com/health`: expected `{"ok":true}`. This confirms only that the API process is serving HTTP, not that background jobs are working.

## 2. Render: **two more resources are required**

**A. Render Key Value (Redis)**

1. Render → New → Key Value.
2. Deploy it in **Oregon**, the same region as the API and worker.
3. Copy its **Internal URL**. In the API service, set `REDIS_URL` to this URL (not `redis://redis:6379/0`, which only works within Docker Compose).
4. Keep Redis private.

**B. Render Background Worker**

1. Render → New → Background Worker → GitHub `AckieJ/researchlens` → `main`.
2. Select Docker, Dockerfile `./backend/Dockerfile`, context `.`, root directory blank.
3. Override Docker Command with **`rq worker researchlens --url "$REDIS_URL"`**. If Render's Docker Command editor does not interpret shell variable expansion, use **`sh -c 'rq worker researchlens --url "$REDIS_URL"'`**.
4. Set the **same** Redis URL, Tiger Data URL, Gemini/OpenAlex/Bright Data credentials, and AI model settings as the web service.
5. The worker logs must show that it is listening to the `researchlens` queue. It needs a worker-capable plan.

Do not assume a successful API deployment means the worker exists. Without it, jobs remain `queued`.

**Temporary diagnostic only:** Set `RUN_INLINE=true` on the Render API, redeploy, and submit a new question. This avoids Redis but runs analysis in a daemon thread inside the web process. Free Render instances can sleep or restart and lose those jobs; DO NOT use this for a reliable public demo. Set it back to `false` for queue processing.

## 3. Vercel: frontend only

Vercel → New Project → import `AckieJ/researchlens`, branch `main` → **Import single project: frontend**.

- Root Directory: `frontend` (if repository has an outer `researchlens/` directory, use `researchlens/frontend` instead)
- Framework: Vite
- Build: `npm run build`
- Output: `dist`
- Install: `npm install`
- No Gemini/Bright Data/OpenAlex/Tiger Data secrets belong in Vercel.

The file `frontend/vercel.json` already proxies `/api/:path*` to `https://researchlens-mhuq.onrender.com/:path*` and serves `index.html` for app routes. If the Render service URL changes, edit this file in GitHub and commit. Vercel will redeploy automatically.

**Check URLs in this order:**

1. `https://researchlens-mhuq.onrender.com/health` → `{"ok":true}`.
2. `https://YOUR-VERCEL-DOMAIN.vercel.app/api/health` → exactly the same JSON (not an HTML homepage).
3. Create a new investigation using the **Investigate** button.
4. Open browser developer tools → Network → `POST /api/workspaces` should return an `id`.
5. `GET /api/workspaces/{id}/status` should advance past `queued`. If it remains queued for 30 seconds, the UI now checks for inactive workers and explains the failure.
6. On Render → Background Worker → Logs, confirm it receives the job.
7. Once complete, real papers appear in the evidence graph. If no papers are retrieved, the UI shows an explicit empty result instead of sample studies.

## 4. Expected behavior and limitations

- **No demo mode:** `#/preview` no longer renders a fictional dashboard; the application opens the live homepage instead.
- **No fake results:** All counts, paper claims, relationships, gaps, and chat answers originate from live backend responses.
- **Errors are visible:** Queue enqueue failure returns HTTP 503; prolonged queued jobs show a worker warning; database/API analysis errors show the actual workspace failure.
- **Source verification:** The existing Gemini pipeline validates verbatim source quotes in code, but model relationship labels remain provisional and should be reviewed by humans.
- **Bright Data:** This code uses Web Unlocker to fetch Scholar HTML and parse it. It does not need a Scholar dataset ID. Its effectiveness depends on zone permissions, source access, and live markup. If unavailable, OpenAlex still supplies candidates.
- **Security:** The global workspace list is disabled by default, but individual workspace endpoints still have no user authentication or rate limiting. Do not publicly promote this deployment or allow unknown users to spend paid API quota before adding accounts, abuse protection, and job quotas. Secrets remain in Render, never in Vite browser variables.
- **Render free tier:** Sleeping, restarts, and shared performance limits still apply to free web services; use persistent paid services for reliability.

## 5. Useful command-free troubleshooting

- Render → API → Logs: Docker start, schema initialization, connection failures.
- Render → Worker → Logs: RQ worker startup and pipeline errors.
- Render → Key Value → Connect: internal Redis URL.
- Vercel → Deployments → Build Logs: frontend compilation.
- Browser → developer tools → Network: confirm that `/api/health` returns JSON and `/api/workspaces` responds.

**Not provided automatically by this ZIP:** running Render worker/Redis, working provider credentials and quotas, DB network/firewall setup, secret management, a live deployment, or authentication.
