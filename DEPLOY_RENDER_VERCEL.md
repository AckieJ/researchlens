# Deploy: Render (free) backend + Vercel frontend

Free-tier design: **one** Render web service, `RUN_INLINE=true` (jobs run in a thread inside the API; no Redis, no worker).
Tiger Data = database. Vercel = static frontend.

## 1. Render web service
- Runtime **Docker**, Dockerfile path `./backend/Dockerfile`, build context `.`, Docker Command **blank**.
- Environment variables: see `render.env.example` (copy values in WITHOUT quotes).
- After deploy open `https://<your-service>.onrender.com/diagnostics` — every line must say `"ok": true`
  (Bright Data is optional). Each failure names the exact fix. Add `?refresh=true` to re-run.

## 2. Vercel frontend
- Root Directory `frontend`, Framework Vite.
- Easiest: leave as is; `frontend/vercel.json` proxies `/api/*` to Render (edit the URL in that file to YOUR Render URL).
- Recommended: add Vercel env var `VITE_API_URL=https://<your-service>.onrender.com` and redeploy. The browser then calls Render
  directly (CORS for `*.vercel.app` is already allowed; for a custom domain set `CORS_ORIGINS` on Render). This avoids rewrite
  timeouts when Render is waking up and size limits on PDF uploads.

## 3. Free-tier behaviour you should know
- Render sleeps after 15 min idle; first request takes ~1 min. The site pings `/health` on page load to wake it.
- While a job runs, the server pings itself every 4 min to stay awake. If it is restarted/redeployed mid-job, the investigation is
  marked **error** on boot and the UI shows **Retry this investigation** (resumes; finished claims are reused).
- A full run takes several minutes. Keep `MAX_PAPERS`/`MAX_PAIRS` small (15/40) on free Gemini quotas, `LLM_CONCURRENCY=2`.
- Optional: an UptimeRobot monitor on `/health` every 10 min keeps it awake permanently.

## 4. Troubleshooting
| Symptom | Look at |
|---|---|
| Red error screen with a message | The message is the real cause (Gemini key rejected, DB unreachable, no papers found...). |
| Stuck on "Connecting" | Render still waking, or Vercel rewrite URL wrong: open `<vercel>/api/health`. |
| Zero papers / claims | `/diagnostics` -> openalex, gemini_generate. Progress screen warnings list lane failures. |
| Scholar lane warnings | Bright Data zone name wrong (see `render.env.example`). Pipeline still works on OpenAlex alone. |

Security: there is no login or rate limiting. Anyone with the URL can spend your Gemini/Bright Data quota. Do not share it widely.
Never paste real keys into chats, issues or commits; rotate any key that has been exposed.
