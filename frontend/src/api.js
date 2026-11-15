const B = '/api'

async function j(r) {
  if (!r.ok) {
    let m = r.statusText
    try { m = (await r.json()).detail || m } catch { /* keep status text */ }
    throw new Error(m)
  }
  return r.json()
}

const get = (p) => fetch(B + p).then(j)

export const api = {
  create: (question, files) => {
    const f = new FormData()
    f.append('question', question)
    ;[...files].forEach((x) => f.append('files', x))
    return fetch(B + '/workspaces', { method: 'POST', body: f }).then(j)
  },
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
