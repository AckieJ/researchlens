import { useEffect, useRef, useState } from 'react'
import { api } from '../api'

const ORDER = ['strengthens', 'challenges', 'qualifies', 'leaves_unanswered']
const TITLE = { strengthens: 'Strengthens', challenges: 'Challenges', qualifies: 'Qualifies', leaves_unanswered: 'Leaves unanswered' }

export default function AddPaper({ id, onUpdated, onViewGraph }) {
  const [phase, setPhase] = useState('idle')
  const [error, setError] = useState('')
  const [report, setReport] = useState(null)
  const timer = useRef(null)
  useEffect(() => () => clearTimeout(timer.current), [])

  const poll = (pid, tries = 0) => {
    timer.current = setTimeout(async () => {
      try { setReport(await api.impact(id, pid)); setPhase('done'); onUpdated() }
      catch (e) {
        const st = await api.status(id).catch(() => null)
        if (st?.status === 'error') { setError(st.error || 'Evaluation failed'); setPhase('idle') }
        else if (tries > 120) { setError('This is taking longer than expected.'); setPhase('idle') }
        else poll(pid, tries + 1)
      }
    }, 3000)
  }

  const upload = async (e) => {
    const f = e.target.files[0]
    if (!f) return
    setPhase('working'); setError(''); setReport(null)
    try { poll((await api.addPaper(id, f)).paper_id) } catch (err) { setError(err.message); setPhase('idle') }
  }

  const groups = report ? ORDER.map((k) => [k, report.report.items.filter((i) => i.impact === k)]) : []
  return (
    <div className="stack narrowcol">
      <h3>Add a paper</h3>
      <p className="muted">Upload a new PDF. ResearchLens compares its claims with the existing graph and shows which earlier findings it strengthens, challenges, qualifies, or leaves unanswered.</p>
      <input type="file" accept="application/pdf" onChange={upload} disabled={phase === 'working'} aria-label="Choose a PDF" />
      {phase === 'working' && <p className="banner">Extracting claims and comparing them with the library…</p>}
      {error && <p className="error">{error}</p>}
      {report && (
        <section className="stack">
          <p>{report.summary || 'Comparison complete.'}</p>
          {groups.map(([k, items]) => items.length > 0 && (
            <div key={k}><h4>{TITLE[k]} ({items.length})</h4>
              {items.map((i) => (
                <article key={i.edge_id} className="claim">
                  <p><strong>New:</strong> {i.new_claim.claim_text}</p>
                  <p><strong>Earlier ({i.prior_claim.title}):</strong> {i.prior_claim.claim_text}</p>
                  <p className="small muted">{i.reason}</p>
                </article>
              ))}
            </div>
          ))}
          {report.report.no_prior_match.length > 0 && <p className="small muted">{report.report.no_prior_match.length} claim(s) in the new paper had no comparable earlier claim.</p>}
          <button className="primary" onClick={onViewGraph}>View updated graph</button>
        </section>
      )}
    </div>
  )
}
