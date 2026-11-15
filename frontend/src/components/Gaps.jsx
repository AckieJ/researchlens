import { useEffect, useState } from 'react'
import { api } from '../api'

function List({ title, note, items }) {
  return (
    <section className="stack">
      <h3>{title}</h3>
      <p className="muted small">{note}</p>
      {items.length === 0 && <p className="muted">Nothing flagged.</p>}
      {items.map((f) => (
        <article key={f.id} className="claim">
          <p>{f.description}</p>
          {f.evidence.map((x, i) => <blockquote key={i}>{x.quote}<footer className="small muted">{x.paper}{x.location ? `, ${x.location}` : ''}</footer></blockquote>)}
        </article>
      ))}
    </section>
  )
}

export default function Gaps({ id }) {
  const [d, setD] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => { api.flags(id).then(setD).catch((e) => setError(e.message)) }, [id])
  if (error) return <p className="error">{error}</p>
  if (!d) return <p className="muted">Loading…</p>
  return (
    <div className="three">
      <List title="Stated limitations" note="Limits the authors themselves reported." items={d.limitations} />
      <List title="Weakly supported claims" note="Abstract-only, small samples, or retraction notices, with no compatible support elsewhere in this library." items={d.weak_claims} />
      <List title="Not found in this library" note="Topics the papers examined do not clearly address. This is about the current collection only, not all of science." items={d.library_gaps} />
    </div>
  )
}
