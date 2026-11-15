import { useEffect, useMemo, useState } from 'react'
import { api, LABELS } from '../api'
import GraphView from './GraphView.jsx'
import PaperPanel from './PaperPanel.jsx'
import Compare from './Compare.jsx'
import Gaps from './Gaps.jsx'
import Chat from './Chat.jsx'
import AddPaper from './AddPaper.jsx'

const NAV = [
  ['graph', '◎', 'Evidence map'],
  ['compare', '⇄', 'Compare studies'],
  ['gaps', '◇', 'Research gaps'],
  ['chat', '✧', 'Ask the evidence'],
  ['add', '＋', 'Add a paper'],
]
const count = obj => Object.values(obj || {}).reduce((a,b)=>a+Number(b||0),0)

export default function Workspace({ id, status, onHome }) {
  const [tab, setTab] = useState('graph')
  const [graph, setGraph] = useState(null)
  const [selection, setSelection] = useState(null)
  const [error, setError] = useState('')
  const [revision, setRevision] = useState(0)
  const [help, setHelp] = useState(false)
  const [compareId, setCompareId] = useState('')
  const evaluating = status.status === 'evaluating'

  useEffect(() => {
    let active = true
    setError('')
    api.graph(id).then(data => {if (active) setGraph(data)}).catch(e=>{if(active)setError(e.message)})
    return ()=>{active=false}
  }, [id, evaluating, revision])
  const papers = graph?.papers || []
  const edges = graph?.edges || []
  const c = status.counts || {}
  const relationships = count(c.edges)
  const contradictionCount = Number(c.edges?.genuine_contradiction || 0) + Number(c.edges?.apparent_contradiction || 0)
  const selectedEdgeId = selection?.type === 'edge' ? selection.id : compareId
  const ordered = useMemo(()=>edges.filter(e=>e.top_edge_id).sort((a,b)=>{
    const priority = ['genuine_contradiction','apparent_contradiction','unresolved','supports_compatible','related_not_comparable']
    return priority.indexOf(a.label) - priority.indexOf(b.label)
  }),[graph])
  const chooseEdge = (edgeId) => {setSelection({type:'edge',id:edgeId});setCompareId(edgeId)}
  const choosePaper = paperId => setSelection({type:'paper',id:paperId})

  return <div className="app-shell dashboard-shell live-dashboard">
    <header className="dashboard-header">
      <button className="logo-lockup header-home" onClick={onHome}><span className="logo-mark">✳</span> research<span className="logo-accent">lens</span></button>
      <span className="header-divider"/><span className="header-subtitle">Evidence workspace</span>
      <span className="header-spacer"/><span className="live-indicator"><span className="status-dot"/> LIVE RESEARCH</span>
      <button className="outline-button" onClick={onHome}>← New investigation</button>
    </header>
    <div className="dashboard-layout">
      <aside className="dashboard-sidebar" aria-label="Workspace navigation">
        <div className="sidebar-caption">CURRENT WORKSPACE</div>
        <div className="workspace-selector"><span>✳</span><div><b>Research investigation</b><small>{papers.length} retrieved papers</small></div></div>
        <div className="sidebar-caption">EXPLORE</div>
        {NAV.map(([key,icon,label])=><button key={key} className={'sidebar-item '+(tab===key?'current':'')} onClick={()=>setTab(key)} aria-current={tab===key?'page':undefined}><span>{icon}</span>{label}{tab===key&&<b>›</b>}</button>)}
        <div className="sidebar-bottom"><div className="sidebar-tip"><span>✧</span><b>Evidence-first analysis</b><p>Every displayed extracted claim is grounded in a source quotation. A disagreement is not automatically a contradiction.</p></div><span>ResearchLens · Live workspace</span></div>
      </aside>
      <main className="dashboard-main">
        <div className="workspace-header"><div className="eyebrow muted-eyebrow">CURRENT INVESTIGATION <span className="crumb-slash">/</span> LIVE EVIDENCE</div><h1>{status.question}</h1><p>Explore real scholarly sources, claim relationships, methodological differences, and unresolved questions.</p><div className="workspace-labels"><span>◉ Live workspace</span><span>◷ {c.full_text || 0} full-text studies</span><span>⊙ {c.abstract_only || 0} abstracts</span></div></div>
        <div className="metric-row">
          {[["◈",papers.length,'Papers analyzed'],['⌘',c.claims || 0,'Extracted claims'],['⇄',relationships,'Claim relationships'],['◇',contradictionCount,'Potential conflicts']].map(([icon,value,label])=><div className="metric-card" key={label}><span className="metric-icon">{icon}</span><div><strong>{value}</strong><small>{label}</small></div></div>)}
        </div>
        {evaluating&&<div className="live-banner">A newly uploaded paper is being evaluated. This view will update when processing finishes.</div>}
        {error&&<div className="live-banner error" role="alert">Unable to load the evidence graph: {error} <button onClick={()=>setRevision(r=>r+1)}>Retry</button></div>}

        {tab==='graph'&&<div className="dashboard-content">
          <section className="graph-workspace" aria-label="Evidence network">
            <div className="panel-heading"><div><h2>Evidence network</h2><p>Select a paper or connection to inspect real source evidence.</p></div><button className="help-trigger" onClick={()=>setHelp(v=>!v)} aria-expanded={help}>ⓘ How to read this</button></div>
            {help&&<div className="help-note">Distance from the center indicates relevance to your research question, not scientific truth. Solid red edges indicate model-flagged genuine contradictions; dashed red indicate apparent contradictions. Inspect both source quotations before drawing conclusions.</div>}
            {graph ? (papers.length ? <GraphView graph={graph} selected={selection} onPaper={choosePaper} onEdge={chooseEdge}/> : <div className="live-empty"><div className="empty-symbol">◇</div><h3>No papers in this evidence graph</h3><p>The investigation completed without retained papers. Try a narrower question, check retrieval access, or add a PDF.</p><button className="primary" onClick={()=>setTab('add')}>Upload a paper ↗</button></div>) : <div className="live-empty"><div className="spinner"/><h3>Loading your evidence network…</h3></div>}
          </section>
          <aside className="inspector-panel"><div className="panel-heading"><div><h2>Evidence inspector</h2><p>{selection ? selection.type === 'paper' ? 'Selected scientific paper' : 'Selected relationship' : 'Select a paper or connection'}</p></div><span className="inspector-symbol">✧</span></div>
            <div className="inspector-body">
              {!selection&&<div className="inspector-empty"><div className="empty-symbol">◎</div><h3>Explore the evidence</h3><p>Click a paper to read its extracted claims and source quotations. Click a relationship to compare the study methods and findings.</p><p className="inspector-notice">Every item in this workspace comes from your live backend, not example data.</p></div>}
              {selection?.type==='paper'&&<PaperPanel id={selection.id} onEdge={chooseEdge}/>}
              {selection?.type==='edge'&&<><Compare id={selection.id} onPaper={choosePaper}/><button className="primary full-button" onClick={()=>setTab('compare')}>Open full comparison ↗</button></>}
            </div>
          </aside>
        </div>}
        {tab==='compare'&&<div className="demo-page-panel live-content-panel"><div className="panel-heading"><div><h2>Compare studies</h2><p>Review evidence-backed relationships between comparable claims.</p></div><span className="type-chip supports">SOURCE-LINKED</span></div><div className="live-panel-content">
          {ordered.length>0?<><label htmlFor="edge-select">Choose a study relationship</label><select id="edge-select" value={selectedEdgeId || ordered[0].top_edge_id} onChange={e=>{chooseEdge(e.target.value)}}>{ordered.map((e,i)=><option key={e.top_edge_id} value={e.top_edge_id}>{i+1}. {LABELS[e.label]?.name || e.label} · {papers.find(p=>p.id===e.source)?.title?.slice(0,48) || 'Study A'} vs {papers.find(p=>p.id===e.target)?.title?.slice(0,48)||'Study B'}</option>)}</select><Compare id={selectedEdgeId || ordered[0].top_edge_id} onPaper={pid=>{choosePaper(pid);setTab('graph')}}/></>:<div className="live-empty"><h3>No comparable claim pairs identified</h3><p>This library did not produce verified claim relationships. That is not evidence that the research agrees.</p></div>}
        </div></div>}
        {tab==='gaps'&&<div className="demo-page-panel live-content-panel"><div className="panel-heading"><div><h2>Gaps & limitations</h2><p>Based only on this workspace's retrieved papers.</p></div><span className="type-chip unresolved">LIBRARY-SCOPED</span></div><div className="live-panel-content"><Gaps id={id}/></div></div>}
        {tab==='chat'&&<div className="demo-page-panel live-content-panel"><div className="panel-heading"><div><h2>Ask the evidence</h2><p>AI answers must reference validated claims and source quotations.</p></div><span className="type-chip supports">CITED ANSWERS</span></div><div className="live-panel-content"><Chat id={id}/></div></div>}
        {tab==='add'&&<div className="demo-page-panel live-content-panel"><div className="panel-heading"><div><h2>Add a new paper</h2><p>Evaluate how a new publication changes your library.</p></div></div><div className="live-panel-content"><AddPaper id={id} onUpdated={()=>setRevision(r=>r+1)} onViewGraph={()=>setTab('graph')}/></div></div>}
        <div className="dashboard-footer">ResearchLens helps investigate evidence; it does not determine scientific truth. <span>Results are limited to retrieved papers and source access.</span></div>
      </main>
    </div>
  </div>
}
