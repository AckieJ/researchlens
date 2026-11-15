const NAMES = {
  queued:'Job queued',understanding:'Interpreting your research question',discovering:'Finding scientific papers',retrieving:'Retrieving available source text',
  extracting:'Extracting verifiable claims',matching:'Matching comparable findings',verifying:'Checking evidence relationships',
  flagging:'Identifying limitations and gaps',layout:'Building the evidence map',done:'Analysis complete',
}
export default function Progress({status,onHome,error,onRetry}) {
  const {counts={},progress={},stages=[]}=status
  const index=Math.max(0,stages.indexOf(status.status))
  const steps=stages.filter(k=>k!=='done')
  const lanes=counts.lanes||{}
  const stale=Boolean(status.queue?.stalled)
  return <div className="app-shell live-progress-shell">
    <header className="dashboard-header"><button className="logo-lockup header-home" onClick={onHome}><span className="logo-mark">✳</span> research<span className="logo-accent">lens</span></button><span className="header-spacer"/><span className="live-indicator"><span className="status-dot"/> LIVE ANALYSIS</span><button className="outline-button" onClick={onHome}>← Home</button></header>
    <main className="live-progress wrap">
      <div className="eyebrow"><span className="status-dot"/> RESEARCH INVESTIGATION</div><h1>Connecting the dots across research.</h1><p className="live-progress-question">{status.question}</p>
      <div className="live-progress-layout"><section className="live-progress-card"><div className="panel-heading"><div><h2>{NAMES[status.status]||status.status}</h2><p>Live job status from the ResearchLens API</p></div><span className="spinner"/></div><div className="live-progress-inner"><div className="live-progress-track"><span style={{width:`${Math.min(95,Math.round(index/Math.max(1,stages.length-1)*100))}%`}}/></div><div className="live-progress-stage-list">{steps.map((k,i)=><div key={k} className={'live-step '+(i<index?'finished':i===index?'active':'')}><span>{i<index?'✓':String(i+1).padStart(2,'0')}</span><div><strong>{NAMES[k]||k}</strong>{i===index&&<small>Current stage</small>}</div></div>)}</div></div></section>
      <aside className="live-progress-right"><div className="live-progress-card"><div className="panel-heading"><div><h2>Live collection</h2><p>Counts are updated by the processing pipeline</p></div></div><div className="live-collection-stats">{[['API papers',lanes.A||0],['Scholar papers',lanes.B||0],['Uploaded',lanes.D||0],['Papers retained',counts.kept||0],['Extracted claims',counts.claims||0],['Verified pairs',progress.pairs_verified||0]].map(([label,n])=><div key={label}><span>{label}</span><strong>{n}</strong></div>)}</div></div>
      {stale&&<div className="live-queue-alert" role="alert"><h3>Queue is not processing</h3><p>{status.queue?.message||'No worker has started this job.'}</p><p>On Render free tier set <code>RUN_INLINE=true</code> (no worker or Redis needed). Otherwise both web and worker must share the same <code>REDIS_URL</code>.</p></div>}
      {error&&<div className="live-queue-alert" role="alert"><h3>Connection issue</h3><p>{error}</p><button onClick={onRetry}>Retry status</button></div>}
      {(progress.warnings||[]).map((w,i)=><div className="live-queue-alert" key={i}>{w}</div>)}
      </aside></div>
      <p className="dashboard-footer">Processing may take several minutes depending on API response times and the number of papers. You can bookmark the current workspace URL.</p>
    </main>
  </div>
}
