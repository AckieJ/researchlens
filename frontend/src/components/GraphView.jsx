import { useCallback, useEffect, useRef, useState } from 'react'
import cytoscape from 'cytoscape'
import { LABELS } from '../api'

// The positions remain relevant to the research question: radius stays tied to
// the backend's relevance score. Local angular nudges separate colliding nodes.
const MAP_RADIUS = 650
const MAX_ZOOM_FACTOR = 6
const T = (s, n = 40) => (s && s.length > n ? `${s.slice(0, n - 1)}…` : s || '')
const color = (value) => value?.startsWith('var(')
  ? getComputedStyle(document.documentElement).getPropertyValue(value.slice(4, -1)).trim()
  : value

function makePositions(papers) {
  const nodes = papers.map((p) => {
    const theta = (Number(p.angle) || 0) * Math.PI / 180
    const radius = MAP_RADIUS * Math.max(0.14, Math.min(1.15, Number(p.radius) || 0.75))
    return { id: p.id, theta, radius, x: Math.cos(theta) * radius, y: Math.sin(theta) * radius }
  })
  // Keep the relevance radius nearly fixed, but separate labels/points within a sector.
  // This avoids drawing unrelated papers on top of one another.
  for (let pass = 0; pass < 95; pass++) {
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i], b = nodes[j]
        const dx = b.x - a.x, dy = b.y - a.y
        const length = Math.max(0.01, Math.hypot(dx, dy))
        const minimum = 90
        if (length >= minimum) continue
        const shift = (minimum - length) * 0.21
        const ux = dx / length, uy = dy / length
        const jitter = length < 1 ? (i % 2 ? 1 : -1) : 0
        a.x -= shift * (ux + jitter); a.y -= shift * uy
        b.x += shift * (ux + jitter); b.y += shift * uy
      }
    }
    for (const n of nodes) {
      const len = Math.max(1, Math.hypot(n.x, n.y))
      const target = Math.max(n.radius - 38, Math.min(n.radius + 38, len))
      n.x = (n.x / len) * target
      n.y = (n.y / len) * target
    }
  }
  return new Map(nodes.map(n => [n.id, { x: n.x, y: n.y }]))
}

function elements(graph) {
  const ps = makePositions(graph.papers || [])
  const items = [
    { data: { id: 'q', label: T(graph.question, 48) }, position: { x: 0, y: 0 }, classes: 'question', selectable: false, grabbable: false },
  ]
  // Rings are a spatial guide only, not an assertion of scientific quality.
  ;(graph.rings || []).forEach(r => {
    const rr = Math.max(0.14, 0.14 + (1 - Number(r)) * 0.86)
    items.push({ data: { id: `ring-${r}`, diameter: 2 * MAP_RADIUS * rr, label: `${Math.round(Number(r) * 100)}% relevance` }, position: { x: 0, y: 0 }, classes: 'ring', selectable: false, grabbable: false })
  })
  for (const p of (graph.papers || [])) {
    const classes = ['paper', p.text_level === 'abstract' ? 'abstract' : '', p.is_new ? 'new' : '', p.parent_paper ? 'second' : '', p.retraction_status && p.retraction_status !== 'none' ? 'retracted' : ''].filter(Boolean).join(' ')
    items.push({ data: { id: p.id, label: T(p.title, 45), short: T(p.title, 24), title: p.title, year: p.year, rel: Number(p.relevance || 0) }, position: ps.get(p.id), classes })
    items.push({ data: { id: `spoke-${p.id}`, source: 'q', target: p.id }, classes: 'spoke' })
    if (p.parent_paper && ps.has(p.parent_paper)) items.push({ data: { id: `parent-${p.id}`, source: p.parent_paper, target: p.id }, classes: 'parent' })
  }
  ;(graph.edges || []).forEach((e, i) => {
    if (ps.has(e.source) && ps.has(e.target)) items.push({
      data: { id: `edge-${i}`, source: e.source, target: e.target, edgeId: e.top_edge_id, relationship: e.label },
      classes: `relationship type-${e.label}`,
    })
  })
  return items
}

function stylesheet() {
  const root = getComputedStyle(document.documentElement)
  const get = (name) => root.getPropertyValue(name).trim()
  const teal = '#118d82', ink = '#153547'
  const styles = [
    { selector: 'node.ring', style: { 'background-opacity': 0, 'border-width': 1.2, 'border-style': 'dashed', 'border-color': '#d1e6e6', width: 'data(diameter)', height: 'data(diameter)', events: 'no', 'z-index': 0 } },
    { selector: 'node.question', style: { shape: 'round-rectangle', width: 176, height: 68, 'background-color': ink, 'border-width': 5, 'border-color': '#d1ece8', color: '#ffffff', label: 'data(label)', 'text-wrap': 'wrap', 'text-max-width': 150, 'text-valign': 'center', 'text-halign': 'center', 'font-size': 13, 'font-weight': 700, 'z-index': 15 } },
    { selector: 'node.paper', style: { width: 32, height: 32, 'background-color': teal, 'border-width': 4, 'border-color': '#ffffff', 'z-index': 10, 'overlay-padding': 14, 'overlay-opacity': 0, 'transition-property': 'background-color,border-color,opacity', 'transition-duration': '160ms', label: '', 'font-size': 13, color: ink, 'font-weight': 600, 'text-valign': 'bottom', 'text-margin-y': 10, 'text-wrap': 'wrap', 'text-max-width': 170, 'text-background-opacity': 0.94, 'text-background-color': '#ffffff', 'text-background-padding': 5, 'text-background-shape': 'roundrectangle', 'text-background-border-color': '#d8e5e8', 'text-background-border-width': 1 } },
    { selector: 'node.paper.abstract', style: { 'background-color': '#f9fdfc', 'border-color': '#188d80', 'border-style': 'dashed', 'border-width': 5 } },
    { selector: 'node.paper.second', style: { width: 24, height: 24 } },
    { selector: 'node.paper.new', style: { 'border-color': '#d1a044', 'border-width': 6 } },
    { selector: 'node.paper.retracted', style: { 'background-color': '#919fad', 'border-color': '#b54e50' } },
    { selector: 'node.paper.detail', style: { label: 'data(short)' } },
    { selector: 'node.paper.expanded', style: { label: 'data(label)' } },
    { selector: 'node.paper.highlighted', style: { label: 'data(label)', 'border-color': '#f4b650', 'border-width': 7, 'z-index': 23 } },
    { selector: 'node.paper.searchmatch', style: { label: 'data(label)', 'border-color': '#e4aa40', 'border-width': 6, 'z-index': 22 } },
    { selector: 'node.paper.dim', style: { opacity: 0.19, label: '' } },
    { selector: 'edge.spoke', style: { width: 1.25, 'line-color': '#d6e2e5', opacity: 0.48, 'curve-style': 'straight', 'z-index': 1 } },
    { selector: 'edge.parent', style: { width: 2, 'line-color': '#9cb6bd', 'line-style': 'dotted', opacity: 0.7, 'curve-style': 'straight', 'z-index': 2 } },
    { selector: 'edge.relationship', style: { width: 4.3, opacity: 0.86, 'curve-style': 'unbundled-bezier', 'control-point-distances': [37], 'control-point-weights': [0.5], 'line-cap': 'round', 'z-index': 5, 'overlay-padding': 16, 'overlay-opacity': 0 } },
    { selector: 'edge.relationship.focused', style: { width: 8, opacity: 1, 'z-index': 18 } },
    { selector: 'edge.relationship.dim', style: { opacity: 0.10 } },
    { selector: 'edge.relationship.filtered', style: { display: 'none' } },
  ]
  for (const [name, value] of Object.entries(LABELS)) {
    const stroke = color(value.color) || get('--accent')
    styles.push({ selector: `edge.type-${name}`, style: { 'line-color': stroke, 'line-style': value.dash?.length ? 'dashed' : 'solid', 'line-dash-pattern': value.dash?.length ? value.dash : [6, 3], width: name === 'genuine_contradiction' ? 6 : 4.3 } })
  }
  return styles
}

export default function GraphView({ graph, selected, onPaper, onEdge }) {
  const rootRef = useRef(null), cyRef = useRef(null), initialZoom = useRef(1)
  const callbacks = useRef({ onPaper, onEdge }); callbacks.current = { onPaper, onEdge }
  const [search, setSearch] = useState('')
  const [minRel, setMinRel] = useState(0)
  const [types, setTypes] = useState(Object.fromEntries(Object.keys(LABELS).map(k => [k, true])))
  const [showLinks, setShowLinks] = useState(true)
  const [focusOnly, setFocusOnly] = useState(false)
  const [zoom, setZoom] = useState(1)
  const [tip, setTip] = useState(null)
  const filters = useRef({ search, minRel, types, showLinks, focusOnly, selected })
  filters.current = { search, minRel, types, showLinks, focusOnly, selected }

  const updateView = useCallback(() => {
    const cy = cyRef.current
    if (!cy) return
    const { search: term, minRel: min, types: enabled, showLinks: links, focusOnly: focus, selected: pick } = filters.current
    const query = term.trim().toLowerCase()
    const zoomFactor = cy.zoom() / Math.max(initialZoom.current, 0.001)
    const selectedNode = pick?.type === 'paper' ? pick.id : null
    const selectedEdges = pick?.type === 'edge' ? cy.edges('.relationship').filter(e => e.data('edgeId') === pick.id) : cy.collection()
    const selectedEdgeNodes = new Set()
    selectedEdges.forEach(e => { selectedEdgeNodes.add(e.source().id()); selectedEdgeNodes.add(e.target().id()) })
    cy.batch(() => {
      const visible = new Set()
      cy.nodes('.paper').forEach(n => {
        const matches = !query || n.data('title').toLowerCase().includes(query)
        const show = n.data('rel') >= min
        if (show) visible.add(n.id())
        n.style('display', show ? 'element' : 'none')
        n.removeClass('detail expanded highlighted dim searchmatch')
        if (zoomFactor >= 1.7) n.addClass('detail')
        if (zoomFactor >= 2.8) n.addClass('expanded')
        if (query && matches) n.addClass('searchmatch')
        if (selectedNode === n.id() || selectedEdgeNodes.has(n.id())) n.addClass('highlighted')
        if ((focus && (selectedNode || selectedEdgeNodes.size) && n.id() !== selectedNode && !selectedEdgeNodes.has(n.id())) || (query && !matches)) n.addClass('dim')
      })
      cy.edges('.spoke,.parent').forEach(e => e.style('display', visible.has(e.target().id()) && (e.source().id() === 'q' || visible.has(e.source().id())) ? 'element' : 'none'))
      cy.edges('.relationship').forEach(e => {
        const permitted = links && enabled[e.data('relationship')] && visible.has(e.source().id()) && visible.has(e.target().id())
        e.style('display', permitted ? 'element' : 'none')
        e.removeClass('focused dim')
        const active = (selectedNode && (e.source().id() === selectedNode || e.target().id() === selectedNode)) || (pick?.type === 'edge' && e.data('edgeId') === pick.id)
        if (active) e.addClass('focused')
        else if (focus && (selectedNode || selectedEdgeNodes.size)) e.addClass('dim')
      })
    })
    setZoom(Math.round(zoomFactor * 100) / 100)
  }, [])

  useEffect(() => {
    if (!rootRef.current) return
    const cy = cytoscape({ container: rootRef.current, elements: elements(graph), style: stylesheet(), layout: { name: 'preset' }, minZoom: 0.10, maxZoom: 5, wheelSensitivity: 0.2, autoungrabify: true, boxSelectionEnabled: false })
    cyRef.current = cy
    cy.fit(cy.nodes('.paper,.question'), 72)
    initialZoom.current = cy.zoom()
    cy.on('zoom', updateView)
    cy.on('tap', 'node.paper', evt => callbacks.current.onPaper(evt.target.id()))
    cy.on('tap', 'edge.relationship', evt => { if (evt.target.data('edgeId')) callbacks.current.onEdge(evt.target.data('edgeId')) })
    cy.on('mouseover', 'node.paper', evt => {
      const p = evt.target.renderedPosition, d = evt.target.data()
      setTip({ x: p.x, y: p.y, text: `${d.title}${d.year ? ` (${d.year})` : ''} · Relevance ${d.rel.toFixed(2)}` })
      evt.target.addClass('detail')
    })
    cy.on('mouseout', 'node.paper', evt => { setTip(null); updateView() })
    cy.on('mouseover', 'edge.relationship', evt => {
      const p = evt.renderedPosition || evt.target.midpoint()
      const v = LABELS[evt.target.data('relationship')]
      if (p) setTip({ x: p.x, y: p.y, text: `${v?.name || 'Relationship'} · Click to compare the studies` })
    })
    cy.on('mouseout', 'edge.relationship', () => setTip(null))
    const observer = new ResizeObserver(() => { cy.resize() })
    observer.observe(rootRef.current)
    updateView()
    return () => { observer.disconnect(); cy.destroy(); cyRef.current = null }
  }, [graph, updateView])

  useEffect(() => { updateView() }, [search, minRel, types, showLinks, focusOnly, selected, updateView])

  const adjustZoom = (factor) => {
    const cy = cyRef.current
    if (!cy) return
    const level = Math.min(initialZoom.current * MAX_ZOOM_FACTOR, Math.max(initialZoom.current * 0.70, cy.zoom() * factor))
    cy.zoom({ level, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } })
  }
  const fit = () => { const cy = cyRef.current; if (cy) { cy.fit(cy.nodes('.paper,.question'), 72); initialZoom.current = cy.zoom(); updateView() } }
  const focusPaper = (id) => {
    const cy = cyRef.current, node = cy?.getElementById(id)
    if (!node?.length) return
    callbacks.current.onPaper(id)
    cy.animate({ center: { eles: node }, zoom: Math.min(3, initialZoom.current * 2.4) }, { duration: 420 })
  }
  const matches = (graph.papers || []).filter(p => p.title.toLowerCase().includes(search.trim().toLowerCase()) && (Number(p.relevance) || 0) >= minRel)

  return <section className="graphbox map-explorer">
    <div className="map-toolbar">
      <div className="map-top-row">
        <label className="map-search-field"><span aria-hidden="true">⌕</span><input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search papers on this map" aria-label="Search papers" />{search && <button type="button" aria-label="Clear search" onClick={() => setSearch('')}>×</button>}</label>
        <div className="map-count"><strong>{(graph.papers || []).length}</strong> papers · <strong>{(graph.edges || []).length}</strong> connections</div>
        <label className="map-minrel">Relevance ≥ <strong>{minRel.toFixed(2)}</strong><input type="range" min="0" max="0.9" step="0.05" value={minRel} onChange={e => setMinRel(+e.target.value)} aria-label="Minimum relevance" /></label>
      </div>
      {search.trim() && <div className="map-results" role="listbox" aria-label="Matching studies">{matches.slice(0, 6).map(p => <button type="button" key={p.id} onClick={() => { focusPaper(p.id); setSearch('') }}>{p.title} <span>↗</span></button>)}{!matches.length && <p>No matching papers in this investigation.</p>}</div>}
      <div className="map-filter-row">
        <span className="map-filter-caption">CONNECTIONS</span>
        {Object.entries(LABELS).map(([key, value]) => <label className={'map-filter-chip ' + (!types[key] ? 'off' : '')} key={key}><input type="checkbox" checked={types[key]} onChange={e => setTypes(old => ({ ...old, [key]: e.target.checked }))} /><span className="map-line-key" style={{ borderColor: color(value.color), borderTopStyle: value.dash?.length ? 'dashed' : 'solid' }}/>{value.name}</label>)}
        <label className="map-switch"><input type="checkbox" checked={focusOnly} onChange={e => setFocusOnly(e.target.checked)} /> Focus selection</label>
      </div>
    </div>
    <div className="map-canvas" aria-label="Interactive evidence map; drag to pan, scroll to zoom, click studies or relationships to inspect" role="application">
      <div className="map-cy" ref={rootRef} />
      <div className="map-top-hint">◎ Drag to explore <span>·</span> Scroll to zoom <span>·</span> Click a connection to compare</div>
      <div className="map-tools" aria-label="Map controls">
        <button type="button" onClick={() => adjustZoom(1.5)} title="Zoom in" aria-label="Zoom in">+</button>
        <div className="map-zoom-display" aria-label={`Zoom ${Math.round(zoom * 100)} percent`}>{Math.round(zoom * 100)}%</div>
        <button type="button" onClick={() => adjustZoom(1 / 1.5)} title="Zoom out" aria-label="Zoom out">−</button>
        <button type="button" onClick={fit} title="Fit all papers" aria-label="Fit all papers">⤢</button>
      </div>
      <div className="map-scale-hint">{zoom < 1.7 ? 'Overview · Zoom in to reveal titles' : zoom < 2.8 ? 'Detail · Zoom in for full titles' : 'Close-up · Full study titles visible'}</div>
      {tip && <div className="map-tooltip" style={{ left: Math.max(10, Math.min(tip.x + 18, (rootRef.current?.clientWidth || 600) - 280)), top: Math.max(14, tip.y - 40) }}>{tip.text}</div>}
    </div>
    <div className="map-bottom-bar"><span><b>◎</b> Distance indicates relevance, not scientific truth.</span><label><input type="checkbox" checked={showLinks} onChange={e => setShowLinks(e.target.checked)} /> Show relationship lines</label><button type="button" onClick={fit}>Reset map view ↺</button></div>
  </section>
}
