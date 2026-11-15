// Default: same-origin '/api' (Vercel rewrite -> Render). Set VITE_API_URL=https://<your-service>.onrender.com in Vercel
// to call Render directly instead; this avoids Vercel's rewrite timeout/body limits (needed for PDF uploads and cold starts).
const RAW = (import.meta.env.VITE_API_URL || '').trim().replace(/\/+$/, '')
export const B = RAW || '/api'

// Render's free tier sleeps; poke it as soon as the page loads so it is awake by the time the user submits.
export const wake = () => fetch(B + '/health', { cache: 'no-store' }).then((r) => r.ok).catch(() => false)

async function j(r) {
  const contentType = r.headers.get('content-type') || ''
  if (!contentType.includes('application/json')) {
    const waking = [502, 503, 504].includes(r.status)
    throw new Error(waking
      ? `The backend is not responding yet (HTTP ${r.status}). Free Render servers take up to a minute to wake up; try again shortly.`
      : `Backend returned ${r.status} ${contentType || 'unknown content'} instead of JSON. Check the Vercel /api rewrite (or VITE_API_URL) and the Render deployment.`)
  }
  let body
  try { body = await r.json() }
  catch { throw new Error(`Invalid JSON from backend (HTTP ${r.status}). Check Render logs.`) }
  if (!r.ok) {
    const detail = body?.detail || body?.message || r.statusText
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  return body
}

const get = async (p) => {
  // one quick retry smooths over a just-woken server
  try { return await fetch(B + p).then(j) } catch (e) {
    await new Promise((r) => setTimeout(r, 1500))
    return fetch(B + p).then(j)
  }
}

export const api = {
  create: (question, files, fresh = false, webSearch = true) => {
    const f = new FormData()
    f.append('question', question)
    if (fresh) f.append('fresh', 'true')
    if (!webSearch) f.append('web_search', 'false')
    ;[...files].forEach((x) => f.append('files', x))
    return fetch(B + '/workspaces', { method: 'POST', body: f }).then(j)
  },
  diagnostics: (refresh) => get('/diagnostics' + (refresh ? '?refresh=true' : '')),
  retry: (id) => fetch(`${B}/workspaces/${id}/retry`, { method: 'POST' }).then(j),
  list: () => get('/workspaces'),
  status: (id) => get(`/workspaces/${id}/status`),
  graph: (id) => get(`/workspaces/${id}/graph`),
  flags: (id) => get(`/workspaces/${id}/flags`),
  paper: (id) => get(`/papers/${id}`),
  edge: (id) => get(`/edges/${id}`),
  addPaper: (id, file) => {
    const f = new FormData()
    f.append('file', file)
    return fetch(`${B}/workspaces/${id}/papers`, { method: 'POST', body: f }).then(j)
  },
  impact: (id, pid) => get(`/workspaces/${id}/impact/${pid}`),
  chat: (id, question) =>
    fetch(`${B}/workspaces/${id}/chat`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question }),
    }).then(j),
}

export const LABELS = {
  genuine_contradiction: { name: 'Genuine contradiction', color: 'var(--red)', dash: [] },
  apparent_contradiction: { name: 'Apparent contradiction', color: 'var(--red)', dash: [8, 5] },
  supports_compatible: { name: 'Supports / compatible', color: 'var(--teal)', dash: [] },
  related_not_comparable: { name: 'Related, not comparable', color: 'var(--muted)', dash: [2, 5] },
  unresolved: { name: 'Unresolved', color: 'var(--amber)', dash: [3, 4] },
}

// Gaps are drawn on the map as markers in the wedge of the sub-question they belong to.
export const GAPS = {
  missing: { name: 'Gap: little or no evidence found', color: 'var(--amber)' },
  one_sided: { name: 'One-sided: only agreeing evidence found', color: 'var(--amber)' },
}
// Everything that is NOT plain agreement. Used by the "tensions only" view and the balance panel.
export const TENSION_TYPES = ['genuine_contradiction', 'apparent_contradiction', 'unresolved']
