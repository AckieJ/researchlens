import { useCallback, useEffect, useRef, useState } from 'react'
import cytoscape from 'cytoscape'
import { GAPS, LABELS, TENSION_TYPES } from '../api'

// The positions remain relevant to the research question: radius stays tied to
// the backend's relevance score. Local angular nudges separate colliding nodes.
const MAP_RADIUS = 790
const MAX_ZOOM_FACTOR = 6
const GAP_RADIUS = MAP_RADIUS * 1.14          // gap markers sit just outside the outermost relevance ring, in their sub-question's wedge
const TENSIONS = new Set(TENSION_TYPES)
// Agreement must not visually drown out disagreement: conflicts are heavier, more opaque and drawn on top.
const LINE = {
  genuine_contradiction: { width: 7, opacity: 0.96, z: 9 },
  apparent_contradiction: { width: 6, opacity: 0.94, z: 8 },
  unresolved: { width: 4.8, opacity: 0.9, z: 7 },
  supports_compatible: { width: 3, opacity: 0.5, z: 5 },
  related_not_comparable: { width: 2.6, opacity: 0.55, z: 3 },
}
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
    const classes = ['paper', p.text_level === 'abstract' ? 'abstract' : '', p.is_new ? 'new' : '', p.parent_paper ? 'second' : '', p.retraction_status && p.retraction_status !== 'none' ? 'retracted' : '', p.conflict_level ? `conflict-${p.conflict_level}` : '', (Number(p.n_limitations) || 0) + (Number(p.n_weak) || 0) > 0 ? 'flagged' : ''].filter(Boolean).join(' ')
    items.push({ data: { id: p.id, label: T(p.title, 45), short: T(p.title, 24), title: p.title, year: p.year, rel: Number(p.relevance || 0), tension: p.conflict_level ? 1 : 0, level: p.conflict_level || '', flags: (Number(p.n_limitations) || 0) + (Number(p.n_weak) || 0) }, position: ps.get(p.id), classes })
    items.push({ data: { id: `spoke-${p.id}`, source: 'q', target: p.id }, classes: 'spoke' })
    if (p.parent_paper && ps.has(p.parent_paper)) items.push({ data: { id: `parent-${p.id}`, source: p.parent_paper, target: p.id }, classes: 'parent' })
  }
  for (const g of (graph.gaps || [])) {
    const th = (Number(g.angle) || 0) * Math.PI / 180
    items.push({ data: { id: `gap-${g.id}`, gapId: g.id, label: T(g.label || g.sub_question, 34), full: g.sub_question, gtype: g.type }, position: { x: Math.cos(th) * GAP_RADIUS, y: Math.sin(th) * GAP_RADIUS }, classes: `gap gap-${g.type}`, grabbable: false })
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
    { selector: 'node.paper.flagged', style: { 'underlay-color': '#d9a441', 'underlay-opacity': 0.28, 'underlay-padding': 7, 'underlay-shape': 'ellipse' } },
    { selector: 'node.paper.conflict-open', style: { 'border-color': '#8b7fc4', 'underlay-color': '#8b7fc4', 'underlay-opacity': 0.3, 'underlay-padding': 9, 'underlay-shape': 'ellipse' } },
    { selector: 'node.paper.conflict-apparent', style: { 'border-color': '#e0864f', 'border-width': 6, 'underlay-color': '#e0864f', 'underlay-opacity': 0.32, 'underlay-padding': 10, 'underlay-shape': 'ellipse' } },
    { selector: 'node.paper.conflict-genuine', style: { 'border-color': '#cf3f38', 'border-width': 6, 'underlay-color': '#cf3f38', 'underlay-opacity': 0.36, 'underlay-padding': 12, 'underlay-shape': 'ellipse' } },
    { selector: 'node.gap', style: { shape: 'diamond', width: 34, height: 34, 'background-color': '#fff6e3', 'border-width': 3.5, 'border-style': 'dashed', 'border-color': '#c98a22', label: '', color: '#7a5314', 'font-size': 12, 'font-weight': 700, 'text-valign': 'bottom', 'text-margin-y': 9, 'text-wrap': 'wrap', 'text-max-width': 150, 'text-background-opacity': 0.95, 'text-background-color': '#fff9ec', 'text-background-padding': 4, 'text-background-shape': 'roundrectangle', 'text-background-border-color': '#ecd4a0', 'text-background-border-width': 1, 'z-index': 12, 'underlay-color': '#e8b04a', 'underlay-opacity': 0.25, 'underlay-padding': 10, 'underlay-shape': 'ellipse' } },
    { selector: 'node.gap.gap-one_sided', style: { shape: 'hexagon', 'border-style': 'solid', 'border-color': '#8b7fc4', color: '#4f4688', 'background-color': '#f3f1fc', 'text-background-color': '#f7f6fd', 'text-background-border-color': '#d6d1ee', 'underlay-color': '#8b7fc4' } },
    { selector: 'node.gap.detail', style: { label: 'data(label)' } },
    { selector: 'node.gap.highlighted', style: { label: 'data(label)', 'border-width': 6, 'z-index': 23 } },
    { selector: 'node.paper.detail', style: { label: 'data(short)' } },
    { selector: 'node.paper.expanded', style: { label: 'data(label)' } },
    { selector: 'node.paper.highlighted', style: { label: 'data(label)', 'border-color': '#f4b650', 'border-width': 7, 'z-index': 23 } },
    { selector: 'node.paper.searchmatch', style: { label: '', 'border-color': '#e4aa40', 'border-width': 6, 'z-index': 22 } },
    { selector: 'node.paper.dim', style: { opacity: 0.19, label: '', 'underlay-opacity': 0 } },
    { selector: 'edge.spoke', style: { width: 1.25, 'line-color': '#d6e2e5', opacity: 0.48, 'curve-style': 'straight', 'z-index': 1 } },
    { selector: 'edge.parent', style: { width: 2, 'line-color': '#9cb6bd', 'line-style': 'dotted', opacity: 0.7, 'curve-style': 'straight', 'z-index': 2 } },
    { selector: 'edge.relationship', style: { width: 4.3, opacity: 0.86, 'curve-style': 'unbundled-bezier', 'control-point-distances': [37], 'control-point-weights': [0.5], 'line-cap': 'round', 'z-index': 5, 'overlay-padding': 16, 'overlay-opacity': 0 } },
  ]
  for (const [name, value] of Object.entries(LABELS)) {
    const stroke = color(value.color) || get('--accent')
    const L = LINE[name] || { width: 4.3, opacity: 0.86, z: 5 }
    styles.push({ selector: `edge.type-${name}`, style: { 'line-color': stroke, 'line-style': value.dash?.length ? 'dashed' : 'solid', 'line-dash-pattern': value.dash?.length ? value.dash : [6, 3], width: L.width, opacity: L.opacity, 'z-index': L.z } })
  }
  styles.push(
    { selector: 'edge.relationship.focused', style: { width: 9, opacity: 1, 'z-index': 18 } },
    { selector: 'edge.relationship.dim', style: { opacity: 0.10 } },
    { selector: 'edge.relationship.filtered', style: { display: 'none' } },
  )
  return styles
}

export default function GraphView({ graph, selected, onPaper, onEdge, onGap }) {
  const rootRef = useRef(null), cyRef = useRef(null), initialZoom = useRef(1)
  const positionsRef = useRef(new Map())
  const drawRef = useRef(0)
  const callbacks = useRef({ onPaper, onEdge, onGap }); callbacks.current = { onPaper, onEdge, onGap }
  const [search, setSearch] = useState('')
  const [minRel, setMinRel] = useState(0)
  const [types, setTypes] = useState(Object.fromEntries(Object.keys(LABELS).map(k => [k, true])))
  const [showLinks, setShowLinks] = useState(true)
  const [focusOnly, setFocusOnly] = useState(false)
  const [spotlight, setSpotlight] = useState(false)
  const [showGaps, setShowGaps] = useState(true)
  const [zoom, setZoom] = useState(1)
  const [tip, setTip] = useState(null)
  const filters = useRef({ search, minRel, types, showLinks, focusOnly, selected, spotlight, showGaps })
  filters.current = { search, minRel, types, showLinks, focusOnly, selected, spotlight, showGaps }
  const counts = graph.balance?.paper_links || {}
  const hasTension = (graph.papers || []).some(p => p.conflict_level) || TENSION_TYPES.some(k => counts[k])

  // Semantic map zoom: a wide-area view packs studies together; close-up views
  // spread their *graph coordinates* as well as increasing the camera zoom.
  // The original relevance/sector coordinates are never overwritten, so the
  // layout is deterministic and reversible when zooming back out.
  const applyAdaptivePositions = (cy, factor) => {
    const density = Math.max(0.66, Math.min(1.78, 0.72 + 0.36 * Math.log2(Math.max(0.6, factor))))
    cy.batch(() => {
      cy.nodes('.paper,.gap,.ring').forEach(node => {
        const anchor = positionsRef.current.get(node.id())
        if (!anchor) return
        node.position({ x: anchor.x * density, y: anchor.y * density })
        if (node.hasClass('ring')) node.style({ width: anchor.diameter * density, height: anchor.diameter * density })
      })
    })
  }

  // Cytoscape can render every title at once, but at low zoom levels those labels
  // overlap. Only labels that fit in the *current screen viewport* are enabled.
  // Selection, searches, conflicts, and relevance get priority over other labels.
  const placeNonOverlappingLabels = (cy, factor, pick, query, min) => {
    const selectedId = pick?.type === 'paper' ? pick.id : null
    const relatedSelectedIds = new Set()
    if (pick?.type === 'edge') cy.edges('.relationship').filter(e => e.data('edgeId') === pick.id).forEach(e => {
      relatedSelectedIds.add(e.source().id())
      relatedSelectedIds.add(e.target().id())
    })
    const searchHits = query ? query.toLowerCase() : ''
    const candidates = cy.nodes('.paper').filter(n => n.data('rel') >= min).toArray().map(n => {
      const matched = searchHits && n.data('title').toLowerCase().includes(searchHits)
      const priority = (n.id() === selectedId ? 10000 : 0) + (relatedSelectedIds.has(n.id()) ? 8000 : 0) + (matched ? 6000 : 0) + (n.data('tension') ? 100 : 0) + (n.data('rel') || 0) * 50
      return { n, priority, pinned: n.id() === selectedId || relatedSelectedIds.has(n.id()) }
    }).sort((a, b) => b.priority - a.priority || a.n.id().localeCompare(b.n.id()))
    const occupied = []
    const full = factor >= 2.5
    const short = factor >= 1.3
    const viewportWidth = cy.width(), viewportHeight = cy.height()
    cy.batch(() => {
      candidates.forEach(({ n, pinned }) => {
        n.removeClass('detail expanded map-labeled')
        if (!short && !pinned) return
        const r = n.renderedPosition()
        const label = full || pinned ? n.data('label') : n.data('short')
        // Approximate text boxes conservatively. Preserve a minimum gap so title
        // backgrounds never obscure neighboring nodes or other paper titles.
        const width = Math.min(186, Math.max(85, label.length * (full ? 6.1 : 6.3) + 19))
        const lines = Math.max(1, Math.ceil(label.length * 6.3 / 174))
        const height = full || pinned ? 24 + (lines - 1) * 17 : 28
        const rect = { x1: r.x - width / 2 - 10, x2: r.x + width / 2 + 10,
          y1: r.y + 18, y2: r.y + 18 + height + 10 }
        const onScreen = rect.x2 >= 6 && rect.x1 <= viewportWidth - 6 && rect.y2 >= 8 && rect.y1 <= viewportHeight - 8
        if (!onScreen) return
        const overlaps = occupied.some(b => rect.x1 < b.x2 && rect.x2 > b.x1 && rect.y1 < b.y2 && rect.y2 > b.y1)
        if (overlaps && !pinned) return
        occupied.push(rect)
        n.addClass(full || pinned ? 'expanded map-labeled' : 'detail map-labeled')
      })
    })
  }

  const scheduleMapRefresh = () => {
    if (drawRef.current) cancelAnimationFrame(drawRef.current)
    drawRef.current = requestAnimationFrame(() => {
      drawRef.current = 0
      updateView()
    })
  }

  const updateView = useCallback(() => {
    const cy = cyRef.current
    if (!cy) return
    const { search: term, minRel: min, types: enabled, showLinks: links, focusOnly: focus, selected: pick, spotlight: spot, showGaps: gaps } = filters.current
    const query = term.trim().toLowerCase()
    const zoomFactor = cy.zoom() / Math.max(initialZoom.current, 0.001)
    if (Math.abs((cy.scratch('_adaptiveFactor') || 0) - zoomFactor) > 0.012) {
      applyAdaptivePositions(cy, zoomFactor)
      cy.scratch('_adaptiveFactor', zoomFactor)
    }
    const selectedNode = pick?.type === 'paper' ? pick.id : null
    const selectedEdges = pick?.type === 'edge' ? cy.edges('.relationship').filter(e => e.data('edgeId') === pick.id) : cy.collection()
    const selectedEdgeNodes = new Set()
    selectedEdges.forEach(e => { selectedEdgeNodes.add(e.source().id()); selectedEdgeNodes.add(e.target().id()) })
    cy.batch(() => {
      // Map pins and titles retain a readable screen size at every scale.
      // Without inverse zoom sizing, article text becomes enormous when zoomed in.
      const unit = 1 / Math.max(0.08, cy.zoom())
      cy.nodes('.paper').forEach(n => {
        const diameter = n.hasClass('second') ? 24 : 30
        n.style({ width: diameter * unit, height: diameter * unit, 'font-size': 12.5 * unit, 'text-margin-y': 10 * unit, 'text-background-padding': 5 * unit })
      })
      cy.nodes('.gap').forEach(n => n.style({ width: 30 * unit, height: 30 * unit, 'font-size': 12 * unit, 'text-margin-y': 9 * unit, 'text-background-padding': 4 * unit }))
      cy.nodes('.question').style({ width: 172 * unit, height: 64 * unit, 'font-size': 13 * unit, 'text-max-width': 148 * unit })
      cy.edges('.relationship').forEach(e => e.style('width', (LINE[e.data('relationship')]?.width || 4) * unit))
      cy.edges('.spoke').style('width', 1.15 * unit)
      cy.edges('.parent').style('width', 1.8 * unit)
      const visible = new Set()
      cy.nodes('.paper').forEach(n => {
        const matches = !query || n.data('title').toLowerCase().includes(query)
        const show = n.data('rel') >= min
        if (show) visible.add(n.id())
        n.style('display', show ? 'element' : 'none')
        n.removeClass('detail expanded highlighted dim searchmatch')
        // Label visibility is calculated below from screen-space collisions.
        if (query && matches) n.addClass('searchmatch')
        if (selectedNode === n.id() || selectedEdgeNodes.has(n.id())) n.addClass('highlighted')
        if ((focus && (selectedNode || selectedEdgeNodes.size) && n.id() !== selectedNode && !selectedEdgeNodes.has(n.id())) || (query && !matches) || (spot && !n.data('tension'))) n.addClass('dim')
      })
      cy.nodes('.gap').forEach(n => {
        n.style('display', gaps ? 'element' : 'none')
        n.removeClass('highlighted detail')
        if (pick?.type === 'gap' && pick.id === n.data('gapId')) n.addClass('highlighted')
        else if (gaps && zoomFactor >= 1.8) n.addClass('detail')
      })
      cy.edges('.spoke,.parent').forEach(e => e.style('display', visible.has(e.target().id()) && (e.source().id() === 'q' || visible.has(e.source().id())) ? 'element' : 'none'))
      cy.edges('.relationship').forEach(e => {
        const permitted = links && enabled[e.data('relationship')] && (!spot || TENSIONS.has(e.data('relationship'))) && visible.has(e.source().id()) && visible.has(e.target().id())
        e.style('display', permitted ? 'element' : 'none')
        e.removeClass('focused dim')
        const active = (selectedNode && (e.source().id() === selectedNode || e.target().id() === selectedNode)) || (pick?.type === 'edge' && e.data('edgeId') === pick.id)
        if (active) { e.addClass('focused'); e.style('width', 7.5 / Math.max(0.08, cy.zoom())) }
        else if (focus && (selectedNode || selectedEdgeNodes.size)) e.addClass('dim')
      })
    })
    placeNonOverlappingLabels(cy, zoomFactor, pick, query, min)
    setZoom(old => Math.abs(old - zoomFactor) > 0.025 ? Math.round(zoomFactor * 100) / 100 : old)
  }, [])

  useEffect(() => {
    if (!rootRef.current) return
    const cy = cytoscape({ container: rootRef.current, elements: elements(graph), style: stylesheet(), layout: { name: 'preset' }, minZoom: 0.10, maxZoom: 5, wheelSensitivity: 0.2, autoungrabify: true, boxSelectionEnabled: false })
    cyRef.current = cy
    positionsRef.current = new Map(cy.nodes('.paper,.gap,.ring').map(n => [n.id(), { ...n.position(), diameter: n.data('diameter') }]))
    // Start with an overview that still has enough room for meaningful navigation.
    applyAdaptivePositions(cy, 1)
    cy.scratch('_adaptiveFactor', 1)
    cy.fit(cy.nodes('.paper,.question,.gap'), 72)
    initialZoom.current = cy.zoom()
    cy.on('zoom pan', scheduleMapRefresh)
    cy.on('tap', 'node.paper', evt => callbacks.current.onPaper(evt.target.id()))
    cy.on('tap', 'node.gap', evt => callbacks.current.onGap?.(evt.target.data('gapId')))
    cy.on('tap', 'edge.relationship', evt => { if (evt.target.data('edgeId')) callbacks.current.onEdge(evt.target.data('edgeId')) })
    cy.on('mouseover', 'node.paper', evt => {
      const p = evt.target.renderedPosition, d = evt.target.data()
      setTip({ x: p.x, y: p.y, text: `${d.title}${d.year ? ` (${d.year})` : ''} · Relevance ${d.rel.toFixed(2)}` })
      evt.target.addClass('detail')
    })
    cy.on('mouseout', 'node.paper', evt => { setTip(null); scheduleMapRefresh() })
    cy.on('mouseover', 'node.gap', evt => {
      const p = evt.target.renderedPosition, d = evt.target.data()
      setTip({ x: p.x, y: p.y, text: `${GAPS[d.gtype]?.name || 'Gap'} · ${d.full} · Click for details` })
    })
    cy.on('mouseout', 'node.gap', () => setTip(null))
    cy.on('mouseover', 'edge.relationship', evt => {
      const p = evt.renderedPosition || evt.target.midpoint()
      const v = LABELS[evt.target.data('relationship')]
      if (p) setTip({ x: p.x, y: p.y, text: `${v?.name || 'Relationship'} · Click to compare the studies` })
    })
    cy.on('mouseout', 'edge.relationship', () => setTip(null))
    const observer = new ResizeObserver(() => { cy.resize(); scheduleMapRefresh() })
    observer.observe(rootRef.current)
    updateView()
    return () => { if (drawRef.current) cancelAnimationFrame(drawRef.current); observer.disconnect(); cy.destroy(); cyRef.current = null }
  }, [graph, updateView])

  useEffect(() => { updateView() }, [search, minRel, types, showLinks, focusOnly, selected, spotlight, showGaps, updateView])

  const adjustZoom = (factor) => {
    const cy = cyRef.current
    if (!cy) return
    const level = Math.min(initialZoom.current * MAX_ZOOM_FACTOR, Math.max(initialZoom.current * 0.70, cy.zoom() * factor))
    cy.zoom({ level, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } })
  }
  const fit = () => { const cy = cyRef.current; if (cy) { applyAdaptivePositions(cy, 1); cy.scratch('_adaptiveFactor', 1); cy.fit(cy.nodes('.paper,.question,.gap'), 72); initialZoom.current = cy.zoom(); updateView() } }
  const focusPaper = (id) => {
    const cy = cyRef.current, node = cy?.getElementById(id)
    if (!node?.length) return
    callbacks.current.onPaper(id)
    cy.animate({ center: { eles: node }, zoom: Math.min(cy.maxZoom(), initialZoom.current * 3.1) }, { duration: 420 })
  }
  const matches = (graph.papers || []).filter(p => p.title.toLowerCase().includes(search.trim().toLowerCase()) && (Number(p.relevance) || 0) >= minRel)

  return <section className="graphbox map-explorer">
    <div className="map-toolbar">
      <div className="map-top-row">
        <label className="map-search-field"><span aria-hidden="true">⌕</span><input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search papers on this map" aria-label="Search papers" />{search && <button type="button" aria-label="Clear search" onClick={() => setSearch('')}>×</button>}</label>
        <div className="map-count"><strong>{(graph.papers || []).length}</strong> papers · <strong>{(graph.edges || []).length}</strong> connections · <strong>{(graph.gaps || []).length}</strong> gaps</div>
        <label className="map-minrel">Relevance ≥ <strong>{minRel.toFixed(2)}</strong><input type="range" min="0" max="0.9" step="0.05" value={minRel} onChange={e => setMinRel(+e.target.value)} aria-label="Minimum relevance" /></label>
      </div>
      {search.trim() && <div className="map-results" role="listbox" aria-label="Matching studies">{matches.slice(0, 6).map(p => <button type="button" key={p.id} onClick={() => { focusPaper(p.id); setSearch('') }}>{p.title} <span>↗</span></button>)}{!matches.length && <p>No matching papers in this investigation.</p>}</div>}
      <div className="map-filter-row">
        <span className="map-filter-caption">CONNECTIONS</span>
        {Object.entries(LABELS).map(([key, value]) => <label className={'map-filter-chip ' + (!types[key] ? 'off' : '')} key={key}><input type="checkbox" checked={types[key]} onChange={e => setTypes(old => ({ ...old, [key]: e.target.checked }))} /><span className="map-line-key" style={{ borderColor: color(value.color), borderTopStyle: value.dash?.length ? 'dashed' : 'solid' }}/>{value.name} <b className="map-chip-count">{counts[key] || 0}</b></label>)}
        <div className="map-switch-group">
          <button type="button" className={'map-spotlight ' + (spotlight ? 'on' : '')} disabled={!hasTension} aria-pressed={spotlight} onClick={() => setSpotlight(v => !v)} title={hasTension ? 'Hide agreeing links and fade papers that are not part of any conflict' : 'No conflicting or unresolved claim pairs were found in this investigation'}>◇ Tensions only</button>
          <label className="map-switch"><input type="checkbox" checked={showGaps} onChange={e => setShowGaps(e.target.checked)} /> Show gaps</label>
          <label className="map-switch"><input type="checkbox" checked={focusOnly} onChange={e => setFocusOnly(e.target.checked)} /> Focus selection</label>
        </div>
      </div>
      <div className="map-legend" aria-label="Map legend">
        <span><i className="lg-halo genuine"/>Paper in a genuine conflict</span>
        <span><i className="lg-halo apparent"/>Apparent conflict (may be explained by methods)</span>
        <span><i className="lg-halo open"/>Unresolved comparison</span>
        <span><i className="lg-halo flagged"/>Stated limitations / weak evidence</span>
        <span><i className="lg-gap"/>Gap: little or no evidence</span>
        <span><i className="lg-gap one"/>One-sided: only agreement found</span>
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
      <div className="map-scale-hint">{zoom < 1.7 ? 'Overview · Studies grouped, titles hidden' : zoom < 2.5 ? 'Neighborhood · More study titles appear' : 'Close-up · Titles displayed where space allows'}</div>
      {tip && <div className="map-tooltip" style={{ left: Math.max(10, Math.min(tip.x + 18, (rootRef.current?.clientWidth || 600) - 280)), top: Math.max(14, tip.y - 40) }}>{tip.text}</div>}
    </div>
    <div className="map-bottom-bar"><span><b>◎</b> Distance indicates relevance, not scientific truth.</span><label><input type="checkbox" checked={showLinks} onChange={e => setShowLinks(e.target.checked)} /> Show relationship lines</label><button type="button" onClick={fit}>Reset map view ↺</button></div>
  </section>
}
