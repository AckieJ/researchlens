import { LABELS } from '../api'

const ORDER = ['genuine_contradiction', 'apparent_contradiction', 'unresolved', 'supports_compatible', 'related_not_comparable']

// Shows how the compared claim pairs split between agreement and everything else, and says plainly
// when "no conflict" may simply mean that dissent was not found rather than that it does not exist.
export default function Balance({ graph }) {
  const b = graph?.balance
  if (!b) return null
  const edges = b.claim_edges || {}
  const total = ORDER.reduce((n, k) => n + (edges[k] || 0), 0)
  const genuine = edges.genuine_contradiction || 0
  const apparent = edges.apparent_contradiction || 0
  const conflicts = genuine + apparent
  const s = b.search || {}
  const queries = s.critical_queries || []
  const missing = b.gaps?.missing || 0
  const oneSided = b.gaps?.one_sided || 0
  const searched = s.critical_kept != null || s.tension_pairs != null

  return <section className="balance-panel" aria-label="Evidence balance">
    <div className="balance-head">
      <div><h2>Evidence balance</h2><p>Agreement is only part of the picture. This shows how the compared claims split, and where the evidence is missing or one-sided.</p></div>
      <div className="balance-gaps"><strong>{missing + oneSided}</strong><small>gaps on the map{oneSided ? ` (${oneSided} one-sided)` : ''}</small></div>
    </div>
    {total > 0 ? <>
      <div className="balance-bar" role="img" aria-label="Share of compared claim pairs by relationship type">
        {ORDER.filter(k => edges[k]).map(k => <span key={k} style={{ flexGrow: edges[k], background: LABELS[k].color }} title={`${LABELS[k].name}: ${edges[k]}`} />)}
      </div>
      <div className="balance-legend">
        {ORDER.map(k => <span key={k} className={edges[k] ? '' : 'zero'}><i style={{ background: LABELS[k].color }} />{LABELS[k].name} <b>{edges[k] || 0}</b></span>)}
      </div>
    </> : <p className="balance-note warn">No claim pairs were compared in this investigation, so nothing can be said yet about agreement or conflict.</p>}
    {total > 0 && conflicts === 0 && <p className="balance-note warn"><b>No conflicts surfaced.</b> That is not proof the field agrees: it can also mean that critical studies were not retrieved or that their claims were not comparable. {searched && <>The search included {queries.length} critical-angle {queries.length === 1 ? 'query' : 'queries'}{s.critical_kept != null && <>, {s.critical_kept} retained paper{s.critical_kept === 1 ? '' : 's'} came from them</>}{s.tension_pairs != null && <>, and {s.tension_pairs} claim pair{s.tension_pairs === 1 ? '' : 's'} reporting different directions or significance {s.tension_pairs === 1 ? 'was' : 'were'} checked</>}.</>}</p>}
    {conflicts > 0 && <p className="balance-note">{genuine} genuine and {apparent} apparent conflict{conflicts === 1 ? '' : 's'} across {b.papers_in_conflict} paper{b.papers_in_conflict === 1 ? '' : 's'}. An <i>apparent</i> conflict is one that differences in population, duration, measure or method may explain. Use <b>Tensions only</b> on the map to see just these.</p>}
    {oneSided > 0 && <p className="balance-note warn">{oneSided} sub-question{oneSided === 1 ? '' : 's'} look one-sided: only agreeing evidence surfaced. Look for the purple hexagons on the map.</p>}
    {queries.length > 0 && <details className="balance-details"><summary>How dissent was searched for</summary>
      <p>Besides queries phrased like your question, these critical-angle queries looked for null results, failed replications, harms and criticism, and a share of the retained papers was reserved for what they found:</p>
      <ul>{queries.map(q => <li key={q}>{q}</li>)}</ul>
    </details>}
  </section>
}
