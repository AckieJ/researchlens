# ResearchLens — OpenAlex API key and hosting

This repository combines Claude's **Bright Data Web Unlocker + Google Scholar HTML parser** backend with the refreshed **professional ResearchLens UI**. It does *not* require a Bright Data Scholar Dataset ID.

## OpenAlex (updated API-key authentication)

1. Sign up at https://openalex.org/ and verify your email.
2. Go to **Settings → API key** (https://openalex.org/settings/api) and copy your key.
3. On **Render** (web service **and** background worker), or in **Coolify** (both API and worker containers), set an environment variable named `OPENALEX_API_KEY` to that value.
4. Optionally set `OPENALEX_EMAIL` to a contact email. This is *not* used for authentication anymore.
5. Redeploy/restart the backend and worker so they receive the new setting.

The server-side scholarly client sends `Authorization: Bearer <key>` **only** to `https://api.openalex.org`. Crossref and Europe PMC do not receive the key. A missing key allows limited keyless queries, subject to OpenAlex's current quota. Never create `VITE_OPENALEX_API_KEY` and never commit your actual key to GitHub.

Official OpenAlex documentation: https://help.openalex.org/api/authentication/

## Frontend — choose ONE hosting option

### GitHub Pages (interactive preview only)

The workflow `.github/workflows/deploy.yml` builds the `frontend/` directory on `ackiebranch` with `VITE_BASE=/SanD-Hacks/`. In GitHub → **Settings → Pages**, set the source to **GitHub Actions**. The working offline preview is at `https://ackiej.github.io/SanD-Hacks/#/preview` after a successful deployment. Live investigations require a backend and API routing.

### Vercel frontend + Render backend

- Import the GitHub repository to Vercel; set **Root Directory = `frontend`**, **Framework = Vite**, **Build = `npm run build`**, **Output = `dist`**. `VITE_BASE` should be omitted (the default is `/`).
- Deploy the FastAPI service and **separate RQ background worker** on Render with the **same** `DATABASE_URL`, `REDIS_URL`, `GEMINI_API_KEY`, `OPENALEX_API_KEY`, and Bright Data configuration. Use Render Key Value or another reachable Redis-compatible queue.
- To forward browser `/api` calls to Render, create `frontend/vercel.json` in your own deployment branch with the following, replacing the hostname with the actual HTTPS Render domain:

```json
{
  "rewrites": [
    {"source":"/api/:path*","destination":"https://YOUR-API.onrender.com/:path*"},
    {"source":"/(.*)","destination":"/index.html"}
  ]
}
```

The backend exposes routes under `/workspaces`, `/health` etc.; Vercel strips `/api/` with the rewrite above.

### Vultr + Coolify (full stack)

Import the repository into Coolify as a Docker Compose resource. The existing `docker-compose.yml` expects a **private `.env` file** on the host; alternatively replace its `env_file` entries with explicit Compose environment substitutions managed in Coolify (for both `api` and `worker`). Add `OPENALEX_API_KEY` alongside the existing API keys. Connect only the `web` service to a public domain, and do not expose Redis or database ports.

## Environment keys

| Name | Used by | Required for |
| --- | --- | --- |
| `OPENALEX_API_KEY` | Backend and worker | OpenAlex API authentication |
| `OPENALEX_EMAIL` | Backend and worker | Optional contact User-Agent |
| `GEMINI_API_KEY` | Backend and worker | Claim extraction, comparisons, chat |
| `BRIGHT_DATA_API_KEY` | Backend and worker | Bright Data Web Unlocker |
| `BRIGHT_DATA_UNLOCKER_ZONE` | Backend and worker | Public-page Web Unlocker zone |
| `BRIGHT_DATA_SCHOLAR_ZONE` | Backend and worker | Optional Scholar-specific zone; blank reuses Unlocker |
| `DATABASE_URL` | Backend and worker | Tiger Data PostgreSQL (+ pgvector) |
| `REDIS_URL` | Backend and worker | Shared RQ queue |

Keep these in hosting-provider secret/environment-variable settings; never put them in React or commit a populated `.env`.

## Testing and limitations

- Run `pytest backend/tests` after installing the backend dependencies with `PYTHONPATH=backend` (or run from the `backend` directory).
- Run `npm install && npm run build` from `frontend/`.
- The **preview** uses fictional studies and works without external credentials.
- The *live* application still requires operational Gemini/Bright Data/OpenAlex/Tiger Data accounts; this ZIP cannot validate your private credentials.
- The Web Unlocker + Scholar HTML parser is best-effort. Use only public content in compliance with target websites' terms; this repo does not bypass paywalls or access controls.
- There is no user authentication or rate limiting in this hackathon MVP; protect API access before public release.
