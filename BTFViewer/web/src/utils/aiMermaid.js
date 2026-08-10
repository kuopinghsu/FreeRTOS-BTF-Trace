/**
 * Mermaid sequence/flowchart subset → SVG.
 * Keep layout rules in sync with btf_viewer_pkg/ai_mermaid.py.
 */

import { btfHighlightHref, btfJumpHref } from './aiTools.js'

const PARTICIPANT_RE = /^participant\s+(\S+)(?:\s+as\s+(.+))?$/i
const ARROW_RE = /^(\S+)\s*(-->>|->>|->|--x|-x|-->)\s*(\S+)\s*:\s*(.*)$/
const NOTE_RE = /^Note\s+(?:over|left of|right of)\s+([^:]+):\s*(.*)$/i
const NODE_RE = /^([A-Za-z0-9_]+)\s*(?:\[([^\]]+)\]|\(([^\)]+)\)|\{([^}]+)\})?\s*$/
const EDGE_RE = /^([A-Za-z0-9_]+)\s*(?:\[([^\]]+)\]|\(([^\)]+)\))?\s*-->(?:\|([^|]+)\|)?\s*([A-Za-z0-9_]+)\s*(?:\[([^\]]+)\]|\(([^\)]+)\))?\s*$/

const JUMP_RE = /jump:([0-9]+(?:\.[0-9]+)?)/g

function esc(text) {
  return String(text || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function noteBoxW(note) {
  return Math.min(200, 16 + 6 * Math.min(String(note || '').length, 36))
}

function nodeBoxW(label) {
  return Math.max(72, Math.min(130, 12 + 7 * Math.min(String(label || '').length, 18)))
}

/** Triangle at (x2,y2). Qt paints SVG <marker> as a stray blob at the origin. */
function svgArrowhead(x1, y1, x2, y2, color, size = 8) {
  const dx = x2 - x1
  const dy = y2 - y1
  const length = Math.hypot(dx, dy) || 1
  const ux = dx / length
  const uy = dy / length
  const bx = x2 - ux * size
  const by = y2 - uy * size
  const px = -uy * size * 0.45
  const py = ux * size * 0.45
  return `<polygon points="${x2.toFixed(1)},${y2.toFixed(1)} ${(bx + px).toFixed(1)},${(by + py).toFixed(1)} ${(bx - px).toFixed(1)},${(by - py).toFixed(1)}" fill="${color}"/>`
}

export function extractMermaidFences(text) {
  const out = []
  const lines = String(text || '').replace(/\r\n/g, '\n').split('\n')
  let i = 0
  while (i < lines.length) {
    const stripped = lines[i].trim()
    if (stripped.startsWith('```')) {
      const lang = stripped.slice(3).trim().toLowerCase()
      i += 1
      const body = []
      while (i < lines.length && !lines[i].trim().startsWith('```')) {
        body.push(lines[i])
        i += 1
      }
      if (i < lines.length) i += 1
      if (lang === 'mermaid') out.push(body.join('\n').trim())
      continue
    }
    i += 1
  }
  return out
}

export function mermaidLinkTargets(source) {
  const found = []
  const seen = new Set()
  const src = String(source || '')
  const addHl = (raw) => {
    const label = String(raw || '').trim()
    const key = `hl:${label}`
    if (!label || seen.has(key)) return
    seen.add(key)
    found.push({ kind: 'highlight', value: label })
  }
  JUMP_RE.lastIndex = 0
  let m
  while ((m = JUMP_RE.exec(src))) {
    const key = `jump:${m[1]}`
    if (!seen.has(key)) {
      seen.add(key)
      found.push({ kind: 'jump', value: m[1] })
    }
  }
  for (const line of src.split('\n')) {
    const s = line.trim().replace(/;$/, '')
    const low = s.toLowerCase()
    if (!s || low.startsWith('graph ') || low.startsWith('flowchart ')
      || low.startsWith('sequencediagram') || s.startsWith('%%')) continue
    const pm = PARTICIPANT_RE.exec(s)
    if (pm) {
      addHl(pm[2] || pm[1] || '')
      continue
    }
    const em = EDGE_RE.exec(s)
    if (em) {
      addHl(em[2] || em[3] || em[1] || '')
      addHl(em[6] || em[7] || em[5] || '')
      continue
    }
    const nm = NODE_RE.exec(s)
    if (nm) addHl(nm[2] || nm[3] || nm[4] || nm[1] || '')
  }
  return found
}

export function mermaidHitRegions(source) {
  const text = String(source || '').trim()
  if (!text) return []
  let first = ''
  for (const line of text.split('\n')) {
    const s = line.trim()
    if (s && !s.startsWith('%%')) {
      first = s.toLowerCase()
      break
    }
  }
  if (first.startsWith('sequencediagram')) return sequenceHits(text)
  if (first.startsWith('graph ') || first.startsWith('flowchart ')) return flowchartHits(text)
  return []
}

export function hitTestMermaid(source, localX, localY, scale = 1) {
  const sx = Number(scale) > 0 ? Number(scale) : 1
  const px = Number(localX)
  const py = Number(localY)
  for (const hit of mermaidHitRegions(source)) {
    const x = hit.x * sx
    const y = hit.y * sx
    const w = hit.w * sx
    const h = hit.h * sx
    if (px >= x && px <= x + w && py >= y && py <= y + h) {
      return { kind: hit.kind, value: hit.value }
    }
  }
  return null
}

export function mermaidToSvg(source, { interactive = true } = {}) {
  const text = String(source || '').trim()
  if (!text) return ''
  let first = ''
  for (const line of text.split('\n')) {
    const s = line.trim()
    if (s && !s.startsWith('%%')) {
      first = s.toLowerCase()
      break
    }
  }
  if (first.startsWith('sequencediagram')) return sequenceSvg(text, interactive)
  if (first.startsWith('graph ') || first.startsWith('flowchart ')) {
    return flowchartSvg(text, interactive)
  }
  return ''
}

function svgDataUri(svg) {
  const bytes = new TextEncoder().encode(svg)
  let bin = ''
  bytes.forEach((b) => { bin += String.fromCharCode(b) })
  const b64 = typeof btoa === 'function' ? btoa(bin) : Buffer.from(svg, 'utf8').toString('base64')
  return `data:image/svg+xml;base64,${b64}`
}

export function mermaidBlockHtml(source, { inlineSvg = true, zoomable = true } = {}) {
  const svg = mermaidToSvg(source, { interactive: inlineSvg })
  if (!svg) {
    return `<pre><code class="language-mermaid">${esc(source)}</code></pre>`
  }
  let body = inlineSvg
    ? `<div class="ai-mermaid-svg">${svg}</div>`
    : `<img class="ai-mermaid-img" alt="mermaid diagram" src="${svgDataUri(svg)}">`
  if (zoomable) {
    body = `<a href="#mermaid-zoom" class="ai-mermaid-zoom" title="Open larger view">${body}</a>`
  }
  const links = linkRowHtml(source)
  return `<div class="ai-mermaid">${body}${links}</div>`
}

function linkRowHtml(source) {
  const parts = []
  for (const { kind, value } of mermaidLinkTargets(source)) {
    const e = esc(value)
    if (kind === 'jump') {
      parts.push(`<a href="${btfJumpHref(value)}" class="ai-jump" data-jump="${e}">jump:${e}</a>`)
    } else {
      parts.push(`<a href="${btfHighlightHref(value)}" class="ai-hl" data-highlight="${e}">${e}</a>`)
    }
  }
  if (!parts.length) return ''
  return `<p class="ai-mermaid-links">${parts.join(' · ')}</p>`
}

function parseSequence(source) {
  const participants = []
  const index = new Map()
  const rows = []

  function ensure(pid, label) {
    const key = String(pid || '').trim()
    if (!key) return
    if (!index.has(key)) {
      index.set(key, participants.length)
      participants.push({ id: key, label: String(label || key).trim() || key })
    } else if (label) {
      participants[index.get(key)].label = String(label).trim() || participants[index.get(key)].label
    }
  }

  for (const raw of source.split('\n')) {
    const line = raw.trim()
    if (!line || line.toLowerCase() === 'sequencediagram' || line.toLowerCase() === 'autonumber') continue
    if (line.toLowerCase().startsWith('title ')) continue
    const pm = PARTICIPANT_RE.exec(line)
    if (pm) {
      ensure(pm[1], pm[2])
      continue
    }
    const am = ARROW_RE.exec(line)
    if (am) {
      ensure(am[1])
      ensure(am[3])
      rows.push({ kind: 'arrow', src: am[1], dst: am[3], arrow: am[2], msg: am[4].trim() })
      continue
    }
    const nm = NOTE_RE.exec(line)
    if (nm) {
      const who = nm[1].split(',')[0].trim()
      ensure(who)
      rows.push({ kind: 'note', who, note: nm[2].trim() })
    }
  }
  return { participants, index, rows }
}

function sequenceGeom(source) {
  const parsed = parseSequence(source)
  const { participants, index, rows } = parsed
  if (!participants.length) return null
  const boxW = 120
  const colW = 150
  const top = 32
  const rowH = 40
  let half = boxW / 2
  for (const row of rows) {
    if (row.kind === 'note') half = Math.max(half, noteBoxW(row.note) / 2)
  }
  const pad = half + 16
  const width = pad * 2 + Math.max(participants.length - 1, 0) * colW
  const height = top + 36 + Math.max(rows.length, 1) * rowH + 24
  const xs = participants.map((_, i) => pad + i * colW)
  return { participants, index, rows, boxW, top, rowH, width, height, xs }
}

function sequenceHits(source) {
  const geom = sequenceGeom(source)
  if (!geom) return []
  const { participants, boxW, top, xs } = geom
  return participants.map((p, i) => ({
    x: xs[i] - boxW / 2, y: top - 14, w: boxW, h: 28,
    kind: 'highlight', value: p.label,
  }))
}

function sequenceSvg(source, interactive) {
  const geom = sequenceGeom(source)
  if (!geom) return ''
  const { participants, index, rows, boxW, top, rowH, width, height, xs } = geom
  const parts = [
    `<svg xmlns="http://www.w3.org/2000/svg" width="${Math.round(width)}" height="${Math.round(height)}" viewBox="0 0 ${Math.round(width)} ${Math.round(height)}" class="ai-mermaid-seq">`,
    `<rect x="0" y="0" width="${Math.round(width)}" height="${Math.round(height)}" fill="#12161d"/>`,
  ]
  participants.forEach((p, i) => {
    const x = xs[i]
    const bx = x - boxW / 2
    const href = interactive ? ` href="btfhighlight:${esc(p.label)}" data-highlight="${esc(p.label)}"` : ''
    parts.push(`<line x1="${x}" y1="${top + 22}" x2="${x}" y2="${height - 12}" stroke="#3a4658" stroke-dasharray="4 3"/>`)
    parts.push(
      `<a${href}><rect x="${bx}" y="${top - 14}" width="${boxW}" height="28" rx="4" fill="#1e3348" stroke="#5b9bd5"/>`
      + `<text x="${x}" y="${top + 5}" text-anchor="middle" fill="#dbe2ea" font-size="11" font-family="sans-serif">${esc(p.label.slice(0, 28))}</text></a>`,
    )
  })
  let y = top + 44
  for (const row of rows) {
    if (row.kind === 'arrow') {
      const x1 = xs[index.get(row.src)]
      const x2 = xs[index.get(row.dst)]
      const dashed = row.arrow.startsWith('--') ? ' stroke-dasharray="5 3"' : ''
      const tip = x2 >= x1 ? 8 : -8
      parts.push(`<line x1="${x1}" y1="${y}" x2="${x2 - tip}" y2="${y}" stroke="#6fbf9a" stroke-width="1.4"${dashed}/>`)
      parts.push(svgArrowhead(x1, y, x2, y, '#6fbf9a'))
      parts.push(`<text x="${(x1 + x2) / 2}" y="${y - 6}" text-anchor="middle" fill="#a8b4c4" font-size="10" font-family="sans-serif">${esc(row.msg.slice(0, 48))}</text>`)
    } else {
      const x = xs[index.get(row.who)]
      const nw = noteBoxW(row.note)
      parts.push(`<rect x="${x - nw / 2}" y="${y - 16}" width="${nw}" height="28" rx="3" fill="#2a2418" stroke="#c9a227"/>`)
      parts.push(`<text x="${x}" y="${y + 3}" text-anchor="middle" fill="#e6d48a" font-size="10" font-family="sans-serif">${esc(row.note.slice(0, 40))}</text>`)
    }
    y += rowH
  }
  parts.push('</svg>')
  return parts.join('')
}

function parseFlowchart(source) {
  const nodes = new Map()
  const order = []
  const edges = []

  function addNode(nid, label) {
    const key = String(nid || '').trim()
    if (!key) return
    if (!nodes.has(key)) {
      nodes.set(key, String(label || key).trim() || key)
      order.push(key)
    } else if (label) {
      nodes.set(key, String(label).trim())
    }
  }

  for (const raw of source.split('\n')) {
    const line = raw.trim().replace(/;$/, '')
    if (!line || line.toLowerCase().startsWith('graph ') || line.toLowerCase().startsWith('flowchart ')) continue
    if (line.startsWith('%%')) continue
    const em = EDGE_RE.exec(line)
    if (em) {
      addNode(em[1], em[2] || em[3])
      addNode(em[5], em[6] || em[7])
      edges.push({ src: em[1], dst: em[5], label: String(em[4] || '').trim() })
      continue
    }
    const nm = NODE_RE.exec(line)
    if (nm) addNode(nm[1], nm[2] || nm[3] || nm[4])
  }
  return { nodes, order, edges }
}

function flowchartGeom(source) {
  const { nodes, order, edges } = parseFlowchart(source)
  if (!nodes.size) return null
  const colW = 160
  const rowH = 78
  const cols = Math.min(4, Math.max(1, order.length))
  let maxHalf = 40
  for (const nid of order) maxHalf = Math.max(maxHalf, nodeBoxW(nodes.get(nid)) / 2)
  const pad = maxHalf + 18
  const top = 36
  const pos = new Map()
  order.forEach((nid, i) => {
    const c = i % cols
    const r = Math.floor(i / cols)
    pos.set(nid, { x: pad + c * colW, y: top + r * rowH })
  })
  let right = 0
  let bottom = 0
  for (const nid of order) {
    const { x, y } = pos.get(nid)
    right = Math.max(right, x + nodeBoxW(nodes.get(nid)) / 2)
    bottom = Math.max(bottom, y + 20)
  }
  return {
    nodes, order, edges, pos,
    width: right + pad,
    height: bottom + 24,
  }
}

function flowchartEdgePaths(geom) {
  const { nodes, edges, pos } = geom
  const pairs = new Set(edges.map(e => `${e.src}\0${e.dst}`))
  return edges.map((e) => {
    const a = pos.get(e.src)
    const b = pos.get(e.dst)
    const dx = b.x - a.x
    const dy = b.y - a.y
    const length = Math.hypot(dx, dy) || 1
    const ux = dx / length
    const uy = dy / length
    const nx = -uy
    const ny = ux
    const sep = pairs.has(`${e.dst}\0${e.src}`) ? 12 : 0
    const ox = nx * sep
    const oy = ny * sep
    const srcR = nodeBoxW(nodes.get(e.src)) / 2 + 2
    const dstR = nodeBoxW(nodes.get(e.dst)) / 2 + 2
    const sx = a.x + ux * srcR + ox
    const sy = a.y + uy * srcR + oy
    const ex = b.x - ux * dstR + ox
    const ey = b.y - uy * dstR + oy
    const extra = sep ? 10 : 8
    return {
      sx, sy, ex, ey,
      lx: (sx + ex) / 2 + nx * extra,
      ly: (sy + ey) / 2 + ny * extra,
      label: e.label,
    }
  })
}

function flowchartHits(source) {
  const geom = flowchartGeom(source)
  if (!geom) return []
  return geom.order.map((nid) => {
    const { x, y } = geom.pos.get(nid)
    const label = geom.nodes.get(nid)
    const bw = nodeBoxW(label)
    return {
      x: x - bw / 2, y: y - 16, w: bw, h: 32,
      kind: 'highlight', value: label,
    }
  })
}

function flowchartSvg(source, interactive) {
  const geom = flowchartGeom(source)
  if (!geom) return ''
  const { nodes, order, pos, width, height } = geom
  const parts = [
    `<svg xmlns="http://www.w3.org/2000/svg" width="${Math.round(width)}" height="${Math.round(height)}" viewBox="0 0 ${Math.round(width)} ${Math.round(height)}" class="ai-mermaid-flow">`,
    `<rect x="0" y="0" width="${Math.round(width)}" height="${Math.round(height)}" fill="#12161d"/>`,
  ]
  for (const edge of flowchartEdgePaths(geom)) {
    parts.push(`<line x1="${edge.sx.toFixed(1)}" y1="${edge.sy.toFixed(1)}" x2="${edge.ex.toFixed(1)}" y2="${edge.ey.toFixed(1)}" stroke="#5b9bd5" stroke-width="1.3"/>`)
    parts.push(svgArrowhead(edge.sx, edge.sy, edge.ex, edge.ey, '#5b9bd5'))
    if (edge.label) {
      parts.push(`<text x="${edge.lx.toFixed(1)}" y="${edge.ly.toFixed(1)}" text-anchor="middle" fill="#c5d0dc" font-size="10" font-family="sans-serif">${esc(String(edge.label).slice(0, 16))}</text>`)
    }
  }
  for (const nid of order) {
    const { x, y } = pos.get(nid)
    const label = nodes.get(nid)
    const href = interactive ? ` href="btfhighlight:${esc(label)}" data-highlight="${esc(label)}"` : ''
    const bw = nodeBoxW(label)
    parts.push(
      `<a${href}><rect x="${x - bw / 2}" y="${y - 16}" width="${bw}" height="32" rx="6" fill="#1e3348" stroke="#5b9bd5"/>`
      + `<text x="${x}" y="${y + 5}" text-anchor="middle" fill="#dbe2ea" font-size="11" font-family="sans-serif">${esc(label.slice(0, 18))}</text></a>`,
    )
  }
  parts.push('</svg>')
  return parts.join('')
}
