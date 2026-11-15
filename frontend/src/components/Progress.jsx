const NAMES = {
  queued: 'Queued', understanding: 'Understanding the question', discovering: 'Finding papers', retrieving: 'Retrieving text',
  extracting: 'Extracting claims', matching: 'Matching comparable claims', verifying: 'Verifying relationships',
  flagging: 'Flagging limits and gaps', layout: 'Laying out the graph', done: 'Done',
}

export default function Progress({ status, onHome }) {
  const { counts = {}, progress = {}, stages = [] } = status
  const cur = stages.indexOf(status.status)
  const lanes = counts.lanes || {}
  const stats = [
    ['Found via APIs', lanes.A ?? 0], ['Found via Google Scholar', lanes.B ?? 0], ['Uploaded', lanes.D ?? 0],
    ['Duplicates removed', progress.duplicates_removed ?? 0], ['Papers kept', counts.kept ?? 0],
    ['Full text', counts.full_text ?? 0], ['Abstract only', counts.abstract_only ?? 0],
    ['Claims extracted', counts.claims ?? 0], ['Quotes rejected', progress.claims_rejected ?? 0], ['Pairs verified', progress.pairs_verified ?? 0],
  ]
  return (
    <div className="page narrow">
      <button className="link" onClick={onHome}>All workspaces</button>
      <h2 className="question">{status.question}</h2>
      <ol className="steps">
        {stages.filter((s) => s !== 'queued').map((s) => {
          const i = stages.indexOf(s)
          return <li key={s} className={i < cur ? 'done' : i === cur ? 'now' : ''}>{NAMES[s]}</li>
        })}
      </ol>
      <dl className="stats">{stats.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>
      {(progress.warnings || []).map((w, i) => <p key={i} className="warn small">{w}</p>)}
    </div>
  )
}
