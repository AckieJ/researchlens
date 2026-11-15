export default function GapDetail({ gap, onOpenGaps }) {
  if (!gap) return <p className="muted">This gap is no longer in the current analysis.</p>
  const one = gap.type === 'one_sided'
  return <div className="stack gap-detail">
    <span className={'type-chip ' + (one ? 'unresolved' : 'apparent')}>{one ? 'ONE-SIDED EVIDENCE' : 'GAP IN THIS LIBRARY'}</span>
    <h3>{gap.sub_question}</h3>
    <p>{gap.description}</p>
    {gap.n_papers != null && <p className="inspector-meta">{gap.n_papers} retained paper{gap.n_papers === 1 ? '' : 's'} clearly address this sub-question.</p>}
    <p className="inspector-notice">{one
      ? 'Several papers address this, but none report a null, mixed or opposing result. Real agreement is possible; so is a search that missed the critics. Try adding a paper that challenges it.'
      : 'This describes the papers retrieved for this investigation only. It does not mean the topic is unstudied.'}</p>
    <button className="primary full-button" onClick={onOpenGaps}>See all gaps and limitations ↗</button>
  </div>
}
