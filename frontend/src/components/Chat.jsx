import { useState } from 'react'
import { api } from '../api'

export default function Chat({ id }) {
  const [msgs, setMsgs] = useState([])
  const [q, setQ] = useState('')
  const [busy, setBusy] = useState(false)

  const send = async (e) => {
    e.preventDefault()
    const question = q.trim()
    if (!question) return
    setMsgs((m) => [...m, { role: 'user', text: question }]); setQ(''); setBusy(true)
    try {
      const r = await api.chat(id, question)
      setMsgs((m) => [...m, { role: 'assistant', text: r.answer, uncertainty: r.uncertainty, cites: r.citations }])
    } catch (err) { setMsgs((m) => [...m, { role: 'error', text: err.message }]) }
    setBusy(false)
  }

  return (
    <div className="chat">
      {msgs.length === 0 && <p className="muted">Ask about the evidence, for example: does one study disprove another, or which results depend on study length? Answers cite the claims and quotations they rely on.</p>}
      {msgs.map((m, i) => (
        <div key={i} className={`msg ${m.role}`}>
          <p>{m.text}</p>
          {m.uncertainty && <p className="small muted">Uncertain or missing: {m.uncertainty}</p>}
          {m.cites?.map((c) => <blockquote key={c.label}><strong>{c.label}</strong> {c.quote}<footer className="small muted">{c.paper}{c.location ? `, ${c.location}` : ''}</footer></blockquote>)}
        </div>
      ))}
      <form onSubmit={send} className="row">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Does Paper D disprove Paper A?" aria-label="Ask a question about this evidence" />
        <button className="primary" disabled={busy || !q.trim()}>{busy ? 'Thinking…' : 'Ask'}</button>
      </form>
    </div>
  )
}
