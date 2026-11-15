# ResearchLens: Adaptive Evidence Map (v8)

This is a **frontend-only** update of the user-provided v7 repository. All backend, database, environment, and API files remain unchanged.

## Behavior

- Map-like semantic zoom: node coordinates are intentionally compressed for the wide overview and gradually spread out as you zoom in. Zooming back out restores the same overview positions deterministically.
- Article titles are **not** all rendered at once. At overview scale, most labels are hidden. At intermediate zoom, short titles appear only when they do not overlap another title. At close-up, longer titles are shown if they fit. Selected papers/edge endpoints are prioritized.
- Node marker sizes and text sizes are adjusted inversely with the camera scale to avoid enormous labels when zoomed in.
- Labels also reflow when you pan or resize the map, based on the visible viewport.
- The original relevance angles/radii from the live API are used as anchors; this only changes frontend presentation, not scientific conclusions or backend scores.
- Research gap labels are hidden in the overview and appear when zoomed in or selected.

## Changed files

`frontend/src/components/GraphView.jsx` only (plus this document).

## Deployment

From the frontend-only ZIP, replace `frontend/src/components/GraphView.jsx` in the GitHub repository and commit to `main`. Vercel will rebuild automatically. Do not change your Render API keys or backend.

## Verification

The non-JSX controller portion passed `node --check`, and the ZIP archive was tested for integrity. A full Vite build could not be performed here because the npm registry was inaccessible (`EAI_AGAIN`). Please check the Vercel build log after committing.
