import { useEffect, useState } from 'react'
import { api } from '../api'

const EXAMPLES = ['Do AI tutors improve learning outcomes?', 'Does intermittent fasting improve cognitive performance?', 'Does sleep after studying improve memory retention?']

export default function Setup({ onCreated, onOpen }) {
  const [question, setQuestion] = useState('')
  const [files, setFiles] = useState([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [recent, setRecent] = useState([])

  useEffect(() => { api.list().then(setRecent).catch(() => {}) }, [])

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setError('')
    try { onCreated((await api.create(question, files)).id) } catch (err) { setError(err.message); setBusy(false) }
  }

  return (
    <div className="page narrow">
      <h1 className="brand">ResearchLens</h1>
      <p className="lede">Ask one research question. See where studies agree, where they truly conflict, where they only seem to, and what is still open, with a quotation behind every judgment.</p>
      <form onSubmit={submit} className="stack">
        <label htmlFor="q">Your research question</label>
        <textarea id="q" rows={3} value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Do AI tutors improve learning outcomes?" required />
        <div className="chips">{EXAMPLES.map((x) => <button type="button" key={x} className="chip" onClick={() => setQuestion(x)}>{x}</button>)}</div>
        <label htmlFor="f">Starting papers (optional PDFs)</label>
        <input id="f" type="file" accept="application/pdf" multiple onChange={(e) => setFiles(e.target.files)} />
        <p className="muted small">Uploads stay private to this workspace. Without uploads, papers are found through OpenAlex, Google Scholar and public open-access pages.</p>
        {error && <p className="error">{error}</p>}
        <button className="primary" disabled={busy || question.trim().length < 8}>{busy ? 'Starting…' : 'Start investigation'}</button>
      </form>
      {recent.length > 0 && (
        <section>
          <h3>Recent workspaces</h3>
          <ul className="plain">{recent.map((r) => <li key={r.id}><button className="link" onClick={() => onOpen(r.id)}>{r.question}</button> <span className="muted small">{r.status}</span></li>)}</ul>
        </section>
      )}
    </div>
  )
}
