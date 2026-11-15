import { useEffect, useState } from 'react'
import { api, LABELS } from '../api'

const ROWS = [['Population', 'population'], ['Sample size', 'sample_n'], ['Design', 'design'], ['Duration', 'duration'],
  ['Measure', 'measure'], ['Direction', 'direction'], ['Significance', 'significance'], ['Effect size', 'effect_size']]
const CHECK = { same_population: 'Population', same_duration: 'Duration', same_measure: 'Measure', same_design: 'Design' }

export default function Compare({ id, onPaper }) {
  const [e, setE] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => { setE(null); api.edge(id).then(setE).catch((x) => setError(x.message)) }, [id])
  if (error) return <p className="error">{error}</p>
  if (!e) return <p className="muted">Loading…</p>
  const L = LABELS[e.label] || { name: e.label, color: 'var(--muted)' }
  const a = e.claim_a, b = e.claim_b
  return (
    <div className="stack">
      <p className="verdict" style={{ borderLeftColor: L.color }}><strong>{L.name}</strong><span className="muted small"> · confidence {Math.round((e.confidence || 0) * 100)}%{e.impact ? ` · ${e.impact.replace('_', ' ')}` : ''}</span></p>
      <p>{e.reason}</p>
      {e.factors?.length > 0 && <p className="small">Differences that may explain it: {e.factors.map((f) => <span key={f} className="badge">{f.replace('_', ' ')}</span>)}</p>}
      <div className="scroll">
        <table>
          <thead><tr><th></th><th><button className="link" onClick={() => onPaper(a.paper.id)}>Study A</button></th><th><button className="link" onClick={() => onPaper(b.paper.id)}>Study B</button></th></tr></thead>
          <tbody>
            <tr><th>Paper</th><td>{a.paper.title} ({a.paper.year})</td><td>{b.paper.title} ({b.paper.year})</td></tr>
            <tr><th>Evidence</th><td>{a.paper.text_level === 'full' ? 'Full text' : 'Abstract only'}</td><td>{b.paper.text_level === 'full' ? 'Full text' : 'Abstract only'}</td></tr>
            {ROWS.map(([n, k]) => <tr key={k}><th>{n}</th><td>{a[k] ?? 'not reported'}</td><td>{b[k] ?? 'not reported'}</td></tr>)}
          </tbody>
        </table>
      </div>
      <p className="small muted">Comparability: {Object.entries(CHECK).map(([k, n]) => `${n} ${e.comparability?.[k] == null ? 'unknown' : e.comparability[k] ? 'similar' : 'different'}`).join(', ')}</p>
      {[a, b].map((c, i) => (
        <blockquote key={i}><strong>Study {i ? 'B' : 'A'}</strong>: {c.quote}<footer className="small muted">{c.paper.title}, {c.location || 'location not found'}</footer></blockquote>
      ))}
    </div>
  )
}
