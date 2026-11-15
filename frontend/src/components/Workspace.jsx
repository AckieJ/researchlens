import { useEffect, useState } from 'react'
import { api } from '../api'
import GraphView from './GraphView.jsx'
import PaperPanel from './PaperPanel.jsx'
import Compare from './Compare.jsx'
import Gaps from './Gaps.jsx'
import Chat from './Chat.jsx'
import AddPaper from './AddPaper.jsx'

const TABS = [['graph', 'Evidence graph'], ['gaps', 'Gaps and flags'], ['chat', 'Ask'], ['add', 'Add a paper']]

export default function Workspace({ id, status, onHome }) {
  const [tab, setTab] = useState('graph')
  const [graph, setGraph] = useState(null)
  const [sel, setSel] = useState(null) // {type:'paper'|'edge', id}
  const [error, setError] = useState('')
  const [rev, setRev] = useState(0)
  const evaluating = status.status === 'evaluating'

  useEffect(() => { api.graph(id).then(setGraph).catch((e) => setError(e.message)) }, [id, evaluating, rev])

  const c = status.counts || {}
  return (
    <div className="page wide">
      <header className="top">
        <button className="link" onClick={onHome}>All workspaces</button>
        <h2 className="question">{status.question}</h2>
        <p className="muted small">{c.kept} papers ({c.full_text} full text, {c.abstract_only} abstract only) · {c.claims} claims · {c.edges ? Object.values(c.edges).reduce((a, b) => a + b, 0) : 0} relationships</p>
        <nav className="tabs" role="tablist">{TABS.map(([k, n]) => <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}>{n}</button>)}</nav>
      </header>
      {evaluating && <p className="banner">Evaluating the new paper against the graph…</p>}
      {error && <p className="error">{error}</p>}
      {tab === 'graph' && graph && (
        <div className="split">
          <GraphView graph={graph} selected={sel} onPaper={(pid) => setSel({ type: 'paper', id: pid })} onEdge={(eid) => setSel({ type: 'edge', id: eid })} />
          <aside className="side">
            {!sel && <p className="muted">Select a paper to see its claims, or a line between papers to compare the evidence. Distance from the center shows relevance to your question; it is a way to navigate, not a measure of truth.</p>}
            {sel?.type === 'paper' && <PaperPanel id={sel.id} onEdge={(eid) => setSel({ type: 'edge', id: eid })} />}
            {sel?.type === 'edge' && <Compare id={sel.id} onPaper={(pid) => setSel({ type: 'paper', id: pid })} />}
          </aside>
        </div>
      )}
      {tab === 'gaps' && <Gaps id={id} />}
      {tab === 'chat' && <Chat id={id} />}
      {tab === 'add' && <AddPaper id={id} onUpdated={() => setRev((r) => r + 1)} onViewGraph={() => setTab('graph')} />}
    </div>
  )
}
