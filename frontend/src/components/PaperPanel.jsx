import { useEffect, useState } from 'react'
import { api, LABELS } from '../api'

export default function PaperPanel({ id, onEdge }) {
  const [p, setP] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => { setP(null); api.paper(id).then(setP).catch((e) => setError(e.message)) }, [id])
  if (error) return <p className="error">{error}</p>
  if (!p) return <p className="muted">Loading…</p>
  const link = p.doi ? `https://doi.org/${p.doi}` : p.url
  return (
    <div className="stack">
      <h3 className="ptitle">{p.title}</h3>
      <p className="muted small">{[p.authors, p.venue, p.year].filter(Boolean).join(' · ')}</p>
      <p className="badges">
        <span className={`badge ${p.text_level === 'full' ? 'ok' : 'warn'}`}>{p.text_level === 'full' ? 'Full text' : 'Abstract only'}</span>
        {p.retraction_status !== 'none' && <span className="badge bad">{p.retraction_status}</span>}
        {p.confidence === 'low' && <span className="badge warn">Not matched to a DOI</span>}
        {p.is_new && <span className="badge gold">New</span>}
        {p.relevance != null && <span className="badge">Relevance {Number(p.relevance).toFixed(2)}</span>}
        {link && <a href={link} target="_blank" rel="noreferrer">Open source</a>}
      </p>
      <h4>Claims ({p.claims.length})</h4>
      {p.claims.map((c) => (
        <article key={c.id} className="claim">
          <p>{c.claim_text}</p>
          <blockquote>{c.quote}<footer className="small muted">{c.location || 'location not found'}</footer></blockquote>
          <p className="small muted">{[c.population, c.sample_n && `n=${c.sample_n}`, c.design, c.duration, c.measure].filter(Boolean).join(' · ')}</p>
          {c.edges.map((e) => (
            <button key={e.id} className="edgebtn" onClick={() => onEdge(e.id)} style={{ borderLeftColor: LABELS[e.label]?.color }}>
              {LABELS[e.label]?.name}{e.impact ? ` (${e.impact.replace('_', ' ')})` : ''} with {e.other_title}
            </button>
          ))}
        </article>
      ))}
    </div>
  )
}
