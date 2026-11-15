# ResearchLens UI Refresh · November 2026

This release replaces the original bare-bones interface with a responsive, professional research experience.

## Highlights
- Modern landing page with prominent research question form, PDF attachment, explanatory sections, and clickable research prompts.
- Interactive **offline preview**, reached using **Explore live preview**. This is a self-contained React/Cytoscape demonstration and requires neither backend nor credentials.
- Evidence preview with draggable/zoomable graph, interactive nodes and relationships, title search, relationship filters, and an evidence inspector.
- Side-by-side comparison, gap cards, and ask-the-evidence prototype available through dashboard navigation.
- All preview articles, findings, and quotations are deliberately fictional, visibly labeled as such. No claim of real scientific evidence is made.
- Existing live API routes and backend integrations are preserved. Core live workspace screens receive visual updates.
- GitHub Pages workflow for branch `ackiebranch`, repository `SanD-Hacks`, building the compiled Vite frontend from `frontend/`.

## Uploading to GitHub
Extract this ZIP. **Upload the contents of the `researchlens` folder to your repository root**, so the root contains `frontend/`, `backend/`, `.github/`, etc. Do not upload the outer `researchlens` directory as an extra nesting level.

In GitHub, use Settings > Pages > Build and deployment > Source: GitHub Actions. Commit files to `ackiebranch` or change the workflow branch name accordingly. The workflow sets `VITE_BASE=/SanD-Hacks/` for Pages; Docker/Vultr defaults to `/`.

Expected deployed Pages URL: `https://ackiej.github.io/SanD-Hacks/`.

## Important boundary
GitHub Pages cannot run FastAPI or Redis. The **interactive preview** works there, but live searches/upload requests require your Vultr-hosted backend. API credentials must stay only on the backend/server, never in GitHub or Vite environment variables.
