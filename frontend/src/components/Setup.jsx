import { useRef, useState } from 'react'
import { api } from '../api'

const EXAMPLES = [
  { tag: 'EDUCATION', title: 'Do AI tutors improve learning outcomes?', detail: 'Learning efficacy · RCTs · retention' },
  { tag: 'HEALTH', title: 'Does intermittent fasting improve cognitive performance?', detail: 'Cognition · intervention studies' },
  { tag: 'NEUROSCIENCE', title: 'Does sleep after studying improve memory retention?', detail: 'Sleep · consolidation · memory' },
]

export default function Setup({ onCreated, onOpen }) {
  const [question, setQuestion] = useState('')
  const [files, setFiles] = useState([])
  const [busy, setBusy] = useState(false)
  const [fresh, setFresh] = useState(false)
  const [uploadsOnly, setUploadsOnly] = useState(false)
  const canSkip = files.length >= 2
  const skip = uploadsOnly && canSkip
  const [error, setError] = useState('')
  const fileRef = useRef(null)
  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setError('')
    try { onCreated((await api.create(question, files, fresh, !skip)).id) } catch (err) { setError(err.message); setBusy(false) }
  }
  return <div className="app-shell">
    <header className="site-header wrap">
      <a href="#" className="logo-lockup" aria-label="ResearchLens home"><span className="logo-mark">✳</span><span>research<span className="logo-accent">lens</span></span><span className="logo-beta">BETA</span></a>
      <nav className="site-nav"><a href="#how-it-works">How it works</a><a href="#examples">Explore topics</a><a href="#about">About</a></nav>
      <a className="nav-cta" href="#how-it-works">How it works <span>↗</span></a>
    </header>

    <main>
      <section className="hero wrap">
        <div className="hero-copy">
          <div className="eyebrow"><span className="status-dot"/> RESEARCH INTELLIGENCE, REIMAGINED</div>
          <h1>Every study tells a story.<br/><em>See the whole picture.</em></h1>
          <p className="hero-description">Go beyond paper summaries. ResearchLens maps scientific evidence, uncovers hidden disagreements, and helps you discover the questions that still need answers.</p>
          <div className="hero-benefits"><span><b>✓</b> Traceable evidence</span><span><b>✓</b> Claim-level comparisons</span><span><b>✓</b> Research gaps</span></div>
          <form className="search-module" onSubmit={submit}>
            <div className="search-module-top"><span className="mini-orb">✧</span><strong>Start a research investigation</strong><span className="search-mode">AI-assisted discovery <span className="status-dot"/></span></div>
            <label className="sr-only" htmlFor="q">Research question</label>
            <textarea id="q" rows={2} value={question} onChange={e => setQuestion(e.target.value)} placeholder="Ask a question about the scientific literature…" required />
            <div className="search-module-bottom">
              <button className="upload-trigger" type="button" onClick={() => fileRef.current?.click()}>＋ Add papers <span className="file-count">{files.length ? `${files.length} selected` : 'PDF'}</span></button>
              <input ref={fileRef} className="sr-only" type="file" accept="application/pdf" multiple onChange={e => setFiles([...e.target.files])}/>
              <button className="primary search-submit" disabled={busy || question.trim().length < 8}>{busy ? 'Starting…' : 'Investigate'} <span>↗</span></button>
            </div>
            <label className={'fresh-toggle' + (canSkip ? '' : ' disabled')} title={canSkip ? '' : 'Add at least 2 PDFs to enable'}><input type="checkbox" disabled={!canSkip} checked={skip} onChange={e => setUploadsOnly(e.target.checked)}/> Use only my uploaded papers: skip the web search (faster{canSkip ? '' : '; add at least 2 PDFs'})</label>
            <label className="fresh-toggle"><input type="checkbox" checked={fresh} onChange={e => setFresh(e.target.checked)}/> Re-run from scratch (ignore saved results for this question)</label>
            {error && <div className="inline-error" role="alert">{error}. Check the API connection and try again.</div>}
          </form>
          <p className="privacy-hint">✦ Sources are linked to original studies. Your uploaded PDFs are limited to your workspace.</p>
        </div>
        <div className="hero-visual" aria-label="Illustrative research evidence network">
          <div className="visual-top"><span className="visual-led"/> EVIDENCE NETWORK <span className="visual-tag">ILLUSTRATIVE</span></div>
          <svg className="hero-network" viewBox="0 0 550 460" role="img" aria-label="Illustration of a research claim connected to scientific studies">
            <defs><radialGradient id="glow"><stop stopColor="#61dbc7" stopOpacity=".22"/><stop offset="1" stopColor="#61dbc7" stopOpacity="0"/></radialGradient></defs>
            <circle cx="275" cy="225" r="212" fill="url(#glow)"/><circle cx="275" cy="225" r="154" className="network-ring"/><circle cx="275" cy="225" r="92" className="network-ring"/>
            <g className="network-links"><path d="M275 225L126 96 M275 225L409 101 M275 225L447 270 M275 225L146 360 M275 225L327 404 M275 225L72 243 M275 225L352 55"/><path className="net-green" d="M126 96L72 243 M146 360L327 404"/><path className="net-orange" d="M409 101L447 270"/></g>
            <g className="network-dot green"><circle cx="126" cy="96" r="17"/><circle cx="146" cy="360" r="16"/><circle cx="327" cy="404" r="13"/></g><g className="network-dot orange"><circle cx="409" cy="101" r="17"/><circle cx="447" cy="270" r="15"/></g><g className="network-dot blue"><circle cx="72" cy="243" r="13"/><circle cx="352" cy="55" r="12"/></g>
            <circle className="network-center-halo" cx="275" cy="225" r="62"/><circle className="network-center" cx="275" cy="225" r="52"/><text x="275" y="216" className="network-center-label">RESEARCH</text><text x="275" y="237" className="network-center-label">QUESTION</text>
            <text x="92" y="70" className="network-caption">Supports</text><text x="416" y="77" className="network-caption">Conflicts</text><text x="331" y="442" className="network-caption">Unresolved</text>
          </svg>
          <div className="visual-bottom"><span><i className="legend-circle green"/> Supporting</span><span><i className="legend-circle orange"/> Conflicting</span><span><i className="legend-circle blue"/> Unresolved</span></div>
          <div className="floating-insight"><span className="insight-icon">✧</span><div><strong>Look beyond the abstract</strong><small>Discover the evidence behind every claim.</small></div></div>
        </div>
      </section>

      <section id="how-it-works" className="feature-section wrap">
        <div className="section-heading"><div><div className="eyebrow muted-eyebrow">FROM QUESTION TO CLARITY</div><h2>Research, without the blind spots.</h2></div><p>One question. A transparent path from published evidence to a clearer understanding of what's known.</p></div>
        <div className="feature-grid">
          <article className="feature-card"><span className="feature-icon aqua">⌘</span><div className="feature-step">01 / DISCOVER</div><h3>Map the literature</h3><p>Bring studies into one connected evidence map. Zoom, filter, and explore relationships between research findings.</p><span className="feature-footer">Explore connections <b>↗</b></span></article>
          <article className="feature-card"><span className="feature-icon peach">⇄</span><div className="feature-step">02 / COMPARE</div><h3>Uncover contradictions</h3><p>Compare claims side by side. Understand whether conclusions really conflict—or just measure different things.</p><span className="feature-footer">Inspect differences <b>↗</b></span></article>
          <article className="feature-card"><span className="feature-icon purple">◇</span><div className="feature-step">03 / INVESTIGATE</div><h3>Find what’s missing</h3><p>See reported limitations, weaker evidence, and unexplored angles in the papers you've collected.</p><span className="feature-footer">Spot open questions <b>↗</b></span></article>
        </div>
      </section>

      <section id="examples" className="examples-section wrap"><div className="section-heading compact"><div><div className="eyebrow muted-eyebrow">START SOMEWHERE INTERESTING</div><h2>Curiosity is a good starting point.</h2></div></div><div className="examples-grid">{EXAMPLES.map(x=><button key={x.title} className="example-card" onClick={()=>{setQuestion(x.title);scrollTo({top:0,behavior:'smooth'});document.getElementById('q')?.focus()}}><span className="example-tag">{x.tag}</span><strong>{x.title}</strong><span className="example-footer">{x.detail} <b>↗</b></span></button>)}</div></section>

      <section id="about" className="closing-cta wrap"><div><div className="eyebrow">REAL RESEARCH, TRACEABLE SOURCES</div><h2>Investigate what the evidence is really saying.</h2><p>Search scholarly literature, inspect exact source quotations, and compare studies without fictional demo results.</p></div><a href="#q" className="nav-cta">Start an investigation ↗</a></section>
    </main>
    <footer className="site-footer wrap"><span className="logo-lockup footer-logo"><span className="logo-mark">✳</span> research<span className="logo-accent">lens</span></span><span>Built for curious minds. Evidence first, always.</span><span>ResearchLens · Live analysis</span></footer>
  </div>
}
