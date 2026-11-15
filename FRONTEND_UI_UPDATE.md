# ResearchLens — Evidence map & inspector usability update

Only frontend code was changed. The API contract, backend, Gemini, OpenAlex, Bright Data, Tiger Data and Vercel rewrite remain unchanged.

## What changed
- Evidence graph now behaves like a map: drag/pan, scroll or +/- zoom, fit/reset view, zoom percentage, and progressive labels (overview → short titles → longer titles).
- Crowded graph nodes have a bounded local separation pass; their radius remains near the relevance-provided radial position. This is a presentation aid, **not** a re-scoring of evidence.
- Relationship links are wider and visually distinguishable with color and line patterns. Select a node or edge to emphasize related connections; optionally enable **Focus selection** to fade unrelated nodes and edges.
- Searching papers shows clickable results; choosing a result zooms the map to the paper.
- Left-hand graph controls are arranged as a toolbar; paper details in the right inspector now scroll **independently**, with a visible scrollbar and keyboard focus. Switching papers resets the inspector scroll to the top.
- Responsive layout puts the inspector below the graph when necessary.

## Deployment
If `frontend/` is already the Vercel project root, replace the two changed files below, then commit to the deployment branch:

- `frontend/src/components/GraphView.jsx`
- `frontend/src/components/Workspace.jsx`
- `frontend/src/styles.css`

No new environment variables, dependencies, or backend deployment are required.

## Verification
- JavaScript/JSX source parsing verified with TypeScript parser.
- Dependency install/build could not be completed in this environment; run `npm install && npm run build` in `frontend/` or check Vercel deployment logs.
- Test with a real workspace containing multiple papers: zoom, pan, label reveal, filters, clicking nodes/edges, inspector scroll, and mobile viewport.
