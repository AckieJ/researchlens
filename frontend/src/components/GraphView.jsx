import { useEffect, useRef, useState } from 'react'
import cytoscape from 'cytoscape'
import { LABELS } from '../api'

const R = 380          // pixel radius for normalized radius 1.0
const RMIN = 0.14      // must match backend layout.R_MIN
const rad = (rel) => RMIN + (1 - rel) * (1 - RMIN)
const cssVar = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim()
const col = (v) => (v.startsWith('var(') ? cssVar(v.slice(4, -1)) : v)
const cut = (s, n) => (s && s.length > n ? s.slice(0, n - 1) + '…' : s || '')

function build(g) {
  const els = [{ group: 'nodes', data: { id: 'q', label: cut(g.question, 46) }, position: { x: 0, y: 0 }, classes: 'q', selectable: false, grabbable: false }]
  g.rings.forEach((r) => els.unshift({ group: 'nodes', data: { id: `ring-${r}`, d: 2 * R * rad(r), label: `relevance ${r}` }, position: { x: 0, y: 0 }, classes: 'ring', selectable: false, grabbable: false }))
  g.papers.forEach((p) => {
    const a = (p.angle * Math.PI) / 180, d = R * p.radius
    const cls = ['paper', p.text_level === 'abstract' ? 'abstract' : '', p.retraction_status !== 'none' ? 'retracted' : '', p.is_new ? 'new' : '', p.parent_paper ? 'second' : ''].join(' ')
    els.push({ group: 'nodes', data: { id: p.id, label: cut(p.title, 26), title: p.title, year: p.year, rel: p.relevance }, position: { x: d * Math.cos(a), y: d * Math.sin(a) }, classes: cls, grabbable: false })
    els.push({ group: 'edges', data: { id: `s-${p.id}`, source: 'q', target: p.id }, classes: 'spoke' })
    if (p.parent_paper) els.push({ group: 'edges', data: { id: `p-${p.id}`, source: p.parent_paper, target: p.id }, classes: 'parent' })
  })
  g.edges.forEach((e, i) => els.push({ group: 'edges', data: { id: `e-${i}`, source: e.source, target: e.target, edgeId: e.top_edge_id, label: e.label }, classes: `rel l-${e.label}` }))
  return els
}

function sheet() {
  const ink = cssVar('--ink'), line = cssVar('--line'), panel = cssVar('--panel'), accent = cssVar('--accent'), muted = cssVar('--muted'), red = cssVar('--red'), gold = cssVar('--gold')
  const s = [
    { selector: 'node.ring', style: { 'background-opacity': 0, 'border-width': 1, 'border-style': 'dashed', 'border-color': line, width: 'data(d)', height: 'data(d)', label: 'data(label)', 'text-valign': 'top', 'text-margin-y': -5, 'font-size': 10, color: muted, events: 'no' } },
    { selector: 'node.q', style: { shape: 'round-rectangle', width: 150, height: 54, 'background-color': ink, color: panel, label: 'data(label)', 'text-wrap': 'wrap', 'text-max-width': 136, 'text-valign': 'center', 'font-size': 11, 'font-weight': 600, 'z-index': 20 } },
    { selector: 'node.paper', style: { width: 22, height: 22, 'background-color': accent, 'border-width': 2, 'border-color': panel, label: 'data(label)', 'font-size': 9, color: ink, 'text-valign': 'bottom', 'text-margin-y': 4, 'text-background-color': panel, 'text-background-opacity': 0.8, 'text-background-padding': 1, 'min-zoomed-font-size': 7, 'z-index': 10 } },
    { selector: 'node.second', style: { width: 16, height: 16 } },
    { selector: 'node.abstract', style: { 'border-style': 'dashed', 'border-color': accent, 'background-color': panel, 'border-width': 3 } },
    { selector: 'node.retracted', style: { 'background-color': muted, 'border-color': red, 'border-width': 3 } },
    { selector: 'node.new', style: { 'border-color': gold, 'border-width': 4 } },
    { selector: 'node.sel', style: { 'border-color': ink, 'border-width': 4, width: 28, height: 28 } },
    { selector: 'edge.spoke', style: { width: 1, 'line-color': line, 'curve-style': 'straight', opacity: 0.8 } },
    { selector: 'edge.parent', style: { width: 1.5, 'line-color': muted, 'line-style': 'dotted', 'curve-style': 'straight', opacity: 0.7 } },
    { selector: 'edge.rel', style: { width: 2.5, 'curve-style': 'unbundled-bezier', 'control-point-distances': [28], 'control-point-weights': [0.5], 'overlay-padding': 7, 'z-index': 5 } },
    { selector: 'edge.rel.sel', style: { width: 5 } },
  ]
  Object.entries(LABELS).forEach(([k, v]) => s.push({ selector: `edge.l-${k}`, style: { 'line-color': col(v.color), 'line-style': v.dash.length ? 'dashed' : 'solid', 'line-dash-pattern': v.dash.length ? v.dash : [1], width: k === 'genuine_contradiction' ? 3.5 : 2.5 } }))
  return s
}

function apply(cy, { minRel, on }) {
  cy.batch(() => {
    cy.nodes('.paper').forEach((n) => n.style('display', n.data('rel') >= minRel ? 'element' : 'none'))
    cy.edges('.rel').forEach((e) => e.style('display', on[e.data('label')] ? 'element' : 'none'))
  })
}

export default function GraphView({ graph, selected, onPaper, onEdge }) {
  const box = useRef(null), cyRef = useRef(null)
  const [minRel, setMinRel] = useState(0)
  const [on, setOn] = useState(Object.fromEntries(Object.keys(LABELS).map((k) => [k, true])))
  const [tip, setTip] = useState(null)
  const cb = useRef({}); cb.current = { onPaper, onEdge }
  const filt = useRef({}); filt.current = { minRel, on }

  useEffect(() => {
    const cy = cytoscape({ container: box.current, elements: build(graph), style: sheet(), layout: { name: 'preset' }, minZoom: 0.3, maxZoom: 3, wheelSensitivity: 0.25 })
    cyRef.current = cy
    cy.on('tap', 'node.paper', (e) => cb.current.onPaper(e.target.id()))
    cy.on('tap', 'edge.rel', (e) => cb.current.onEdge(e.target.data('edgeId')))
    cy.on('mouseover', 'node.paper', (e) => { const d = e.target.data(), p = e.renderedPosition; setTip({ x: p.x, y: p.y, t: `${d.title} (${d.year || 'n.d.'}), relevance ${d.rel.toFixed(2)}` }) })
    cy.on('mouseout', 'node.paper', () => setTip(null))
    cy.fit(undefined, 40)
    apply(cy, filt.current)
    return () => cy.destroy()
  }, [graph])

  useEffect(() => { if (cyRef.current) apply(cyRef.current, { minRel, on }) }, [minRel, on])

  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return
    cy.elements().removeClass('sel')
    if (selected?.type === 'paper') cy.getElementById(selected.id).addClass('sel')
    if (selected?.type === 'edge') cy.edges('.rel').filter((e) => e.data('edgeId') === selected.id).addClass('sel')
  }, [selected])

  return (
    <section className="graphbox">
      <div className="controls">
        <label>Minimum relevance <input type="range" min="0" max="0.9" step="0.05" value={minRel} onChange={(e) => setMinRel(+e.target.value)} /> <span className="muted small">{minRel.toFixed(2)}</span></label>
        <div className="toggles">
          {Object.entries(LABELS).map(([k, v]) => (
            <label key={k} className="tog"><input type="checkbox" checked={on[k]} onChange={(e) => setOn({ ...on, [k]: e.target.checked })} />
              <svg width="26" height="8" aria-hidden="true"><line x1="0" y1="4" x2="26" y2="4" stroke={v.color} strokeWidth="3" strokeDasharray={v.dash.join(' ')} /></svg>{v.name}</label>
          ))}
        </div>
      </div>
      <div className="canvas" role="img" aria-label="Radial evidence graph. Papers closer to the center are more relevant to the question.">
        <div ref={box} className="cy" />
        {tip && <div className="tip" style={{ left: tip.x + 14, top: tip.y + 10 }}>{tip.t}</div>}
      </div>
      <p className="muted small legend">Closer to the center = more relevant to the question. Dashed outline = abstract only. Gold ring = newly added paper. Small nodes joined by dotted lines were found by following citations. Relevance helps you navigate; it is not a measure of truth.</p>
    </section>
  )
}
