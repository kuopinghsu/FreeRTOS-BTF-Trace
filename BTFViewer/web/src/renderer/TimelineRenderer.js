/**
 * TimelineRenderer.js – Stateless Canvas timeline renderer.
 *
 * Mirrors the Python TimelineScene + _BatchRowItem paint logic from btf_viewer.py.
 * The renderer is fully stateless: call render() with current state to repaint.
 *
 * Coordinate system:
 *   - X axis: time (left → right)
 *   - Y axis: rows (top → bottom)
 *   - Left fixed-width column (LABEL_W px) contains task/core labels (DOM, not canvas)
 *   - Ruler row (RULER_H px high) contains time tick marks
 *   - Timeline body occupies remaining canvas area
 */

import { taskColor, taskDisplayName, taskMergeKey, coreTint, coreColor, stiNoteColor, parseTaskName } from '../utils/colors.js'
import { bisectLeft, bisectRight } from '../utils/bisect.js'
import { lodReduce } from '../utils/lod.js'
import { visibleSegs } from '../parser/btfParser.js'

// ---- Helpers ---------------------------------------------------------------
function isCoreName(name) {
  return typeof name === 'string' && name.startsWith('Core_')
}

// ---- Layout constants (must match CSS in TimelinePanel.vue) ---------------
export const LABEL_W    = 160  // width of left label column (px)  [DOM, not canvas]
export const RULER_H    =  40  // height of ruler row (px)
export const ROW_H      =  24  // task row height (px)
export const ROW_GAP    =   4  // gap between rows (px)
export const STI_ROW_H  =  18  // STI channel row height (px)
export const MIN_SEG_W  =   1  // minimum segment paint width (px)

// LOD thresholds (ns/px). Above PAINT_LOD_COARSE, nearby sub-pixel segments are
// merged via lodReduce; below it, individual segments are drawn with outlines.
// visibleSegs() already selects the right LOD bin tier automatically.
const PAINT_LOD_COARSE = 200    // ns/px: use coarse (merged) paint above this zoom level

// ---- Time formatting -------------------------------------------------------

/**
 * Format a timestamp for display on the ruler.
 * @param {number} t       Timestamp in trace time-scale units.
 * @param {string} scale   Trace timeScale string (e.g. 'ns', 'us', 'ms').
 * @returns {string}
 */
export function formatTime(t, scale) {
  if (scale === 'ns') {
    if (t >= 1e9)  return `${(t / 1e9).toFixed(3)} s`
    if (t >= 1e6)  return `${(t / 1e6).toFixed(3)} ms`
    if (t >= 1e3)  return `${(t / 1e3).toFixed(3)} µs`
    return `${t} ns`
  }
  if (scale === 'us') {
    if (t >= 1e6)  return `${(t / 1e6).toFixed(3)} s`
    if (t >= 1e3)  return `${(t / 1e3).toFixed(3)} ms`
    return `${t} µs`
  }
  if (scale === 'ms') {
    if (t >= 1e3)  return `${(t / 1e3).toFixed(3)} s`
    return `${t} ms`
  }
  return `${t} ${scale}`
}

/**
 * Pick a "nice" ruler step that produces 5–12 tick marks across the viewport.
 */
function niceStep(span) {
  const targetTicks = 8
  const rough = span / targetTicks
  const mag = Math.pow(10, Math.floor(Math.log10(rough)))
  for (const m of [1, 2, 5, 10]) {
    if (mag * m >= rough) return mag * m
  }
  return mag * 10
}

// ---- Row layout helper -----------------------------------------------------

/**
 * Build a flat row descriptor array for the current view mode.
 * Each row: { type: 'task'|'core'|'core-task'|'sti', key, label, color, y }
 *
 * @param {object}  trace      BtfTrace object from parser.
 * @param {string}  viewMode   'task' or 'core'.
 * @param {Set}     expanded   Set of expanded core names (core view only).
 * @param {number}  yStart     Top Y coordinate of the first row (after ruler).
 * @returns {{ rows: Array, totalHeight: number }}
 */
export function buildRowLayout(trace, viewMode, expanded, yStart) {
  const rows = []
  let y = yStart

  if (viewMode === 'task') {
    for (const mk of trace.tasks) {
      const repr = trace.taskRepr.get(mk)
      const label = taskDisplayName(repr || mk)
      const color = taskColor(mk, repr)
      rows.push({ type: 'task', key: mk, label, color, y })
      y += ROW_H + ROW_GAP
    }
  } else {
    // Core view
    for (const coreName of trace.coreNames) {
      const cc = coreColor(coreName)
      rows.push({ type: 'core', key: coreName, label: coreName, color: cc, y })
      y += ROW_H + ROW_GAP
      if (expanded.has(coreName)) {
        const taskOrder = trace.coreTaskOrder.get(coreName) || []
        for (const rawTask of taskOrder) {
          const label = taskDisplayName(rawTask)
          const color = taskColor(trace.taskRepr.get(trace.coreTaskSegs.get(coreName)?.get(rawTask)?.[0]?.task || rawTask) || rawTask, rawTask)
          rows.push({ type: 'core-task', key: `${coreName}__${rawTask}`, coreKey: coreName, taskKey: rawTask, label, color, y })
          y += ROW_H + ROW_GAP
        }
      }
    }
  }

  // STI rows
  for (const ch of trace.stiChannels) {
    rows.push({ type: 'sti', key: ch, label: ch, color: '#888', y })
    y += STI_ROW_H + ROW_GAP
  }

  return { rows, totalHeight: y - yStart }
}

// ---- Main render function --------------------------------------------------

/**
 * Render the full timeline onto canvas ctx.
 *
 * @param {CanvasRenderingContext2D} ctx
 * @param {object} trace        BtfTrace from parseBtf()
 * @param {object} viewport     { timeStart, timeEnd, scrollY, canvasW, canvasH }
 * @param {object} options      { viewMode, expanded, cursors, highlightKey, showGrid, darkMode }
 */
export function render(ctx, trace, viewport, options = {}) {
  const { timeStart, timeEnd, scrollY, canvasW, canvasH } = viewport
  const {
    viewMode    = 'task',
    expanded    = new Set(),
    cursors     = [],
    highlightKey = null,
    showGrid    = false,
    darkMode    = true,
    hoverTime   = null,
  } = options

  const timeSpan = timeEnd - timeStart
  if (timeSpan <= 0 || canvasW <= 0) return

  const pxPerNs      = canvasW / timeSpan
  const nsPerPx      = timeSpan / canvasW   // timescale per pixel
  const bodyW        = canvasW
  const bodyH        = canvasH - RULER_H

  // DPR-aware clear
  ctx.clearRect(0, 0, canvasW, canvasH)

  // ---- Background ----
  ctx.fillStyle = darkMode ? '#1E1E1E' : '#FFFFFF'
  ctx.fillRect(0, 0, canvasW, canvasH)

  // Ruler background
  ctx.fillStyle = darkMode ? '#2D2D2D' : '#F0F0F0'
  ctx.fillRect(0, 0, canvasW, RULER_H)

  // ---- Row layout ----
  const { rows } = buildRowLayout(trace, viewMode, expanded, RULER_H - scrollY)

  // ---- Grid lines (optional) ----
  if (showGrid) {
    const step = niceStep(timeSpan)
    const startSnap = Math.ceil(timeStart / step) * step
    ctx.strokeStyle = darkMode ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)'
    ctx.lineWidth = 1
    for (let t = startSnap; t <= timeEnd; t += step) {
      const x = Math.round((t - timeStart) * pxPerNs) + 0.5
      ctx.beginPath()
      ctx.moveTo(x, RULER_H)
      ctx.lineTo(x, canvasH)
      ctx.stroke()
    }
  }

  // ---- Ruler ticks & labels ----
  drawRuler(ctx, trace, timeStart, timeEnd, pxPerNs, canvasW, darkMode)

  // ---- Clip to body area ----
  ctx.save()
  ctx.beginPath()
  ctx.rect(0, RULER_H, canvasW, bodyH)
  ctx.clip()

  // ---- Task / Core rows ----
  for (const row of rows) {
    const rowY = row.y
    if (rowY + ROW_H < RULER_H || rowY > canvasH) continue  // row not visible

    if (row.type === 'task') {
      drawTaskRow(ctx, trace, row, timeStart, timeEnd, pxPerNs, nsPerPx, highlightKey, darkMode)
    } else if (row.type === 'core') {
      drawCoreRow(ctx, trace, row, timeStart, timeEnd, pxPerNs, nsPerPx, darkMode)
    } else if (row.type === 'core-task') {
      drawCoreTaskRow(ctx, trace, row, timeStart, timeEnd, pxPerNs, nsPerPx, highlightKey, darkMode)
    } else if (row.type === 'sti') {
      drawStiRow(ctx, trace, row, timeStart, timeEnd, pxPerNs, darkMode)
    }
  }

  ctx.restore()

  // ---- Cursors ----
  drawCursors(ctx, cursors, trace, timeStart, pxPerNs, canvasW, canvasH, darkMode)

  // ---- Hover line (mouse position indicator) ----
  if (hoverTime !== null) {
    drawHoverLine(ctx, hoverTime, trace, timeStart, pxPerNs, canvasW, canvasH, darkMode)
  }
}

// ---- Ruler drawing ---------------------------------------------------------

function drawRuler(ctx, trace, timeStart, timeEnd, pxPerNs, canvasW, darkMode) {
  const timeSpan = timeEnd - timeStart
  const step = niceStep(timeSpan)
  const startSnap = Math.ceil(timeStart / step) * step

  const textColor  = darkMode ? '#CCCCCC' : '#444444'
  const tickColor  = darkMode ? '#555555' : '#BBBBBB'
  const majorColor = darkMode ? '#888888' : '#666666'

  ctx.font = '10px monospace'
  ctx.textAlign = 'left'
  ctx.textBaseline = 'middle'

  for (let t = startSnap - step; t <= timeEnd + step; t += step) {
    const x = Math.round((t - timeStart) * pxPerNs)
    if (x < -50 || x > canvasW + 50) continue

    // Major tick
    ctx.strokeStyle = tickColor
    ctx.lineWidth = 1
    ctx.beginPath()
    ctx.moveTo(x + 0.5, RULER_H - 10)
    ctx.lineTo(x + 0.5, RULER_H)
    ctx.stroke()

    // Label
    const label = formatTime(t, trace.timeScale)
    ctx.fillStyle = textColor
    ctx.fillText(label, x + 3, RULER_H / 2)
  }

  // Ruler bottom border
  ctx.strokeStyle = darkMode ? '#444444' : '#CCCCCC'
  ctx.lineWidth = 1
  ctx.beginPath()
  ctx.moveTo(0, RULER_H - 0.5)
  ctx.lineTo(canvasW, RULER_H - 0.5)
  ctx.stroke()
}

// ---- Segment helpers -------------------------------------------------------

/**
 * Get the LOD data bundle for a merge key in task view.
 */
function taskLodData(trace, mk) {
  return {
    segs:        trace.segByMergeKey.get(mk) || [],
    starts:      trace.segStartByMergeKey.get(mk) || [],
    lodSegs:     trace.segLodByMergeKey.get(mk) || [],
    lodStarts:   trace.segLodStartsByMergeKey.get(mk) || [],
    ultraSegs:   trace.segLodUltraByMergeKey.get(mk) || [],
    ultraStarts: trace.segLodUltraStartsByMergeKey.get(mk) || [],
  }
}

function coreTaskLodData(trace, coreName, rawTask) {
  const cLod = trace.coreTaskSegLod.get(coreName)
  const cStarts = trace.coreTaskSegLodStarts.get(coreName)
  const cUltra = trace.coreTaskSegLodUltra.get(coreName)
  const cUltraStarts = trace.coreTaskSegLodUltraStarts.get(coreName)
  const cTaskStarts = trace.coreTaskSegStarts.get(coreName)
  const cSegs = trace.coreTaskSegs.get(coreName)
  return {
    segs:        (cSegs && cSegs.get(rawTask)) || [],
    starts:      (cTaskStarts && cTaskStarts.get(rawTask)) || [],
    lodSegs:     (cLod && cLod.get(rawTask)) || [],
    lodStarts:   (cStarts && cStarts.get(rawTask)) || [],
    ultraSegs:   (cUltra && cUltra.get(rawTask)) || [],
    ultraStarts: (cUltraStarts && cUltraStarts.get(rawTask)) || [],
  }
}

function coreLodData(trace, coreName) {
  return {
    segs:        trace.coreSegs.get(coreName) || [],
    starts:      trace.coreSegStarts.get(coreName) || [],
    lodSegs:     trace.coreSegLod.get(coreName) || [],
    lodStarts:   trace.coreSegLodStarts.get(coreName) || [],
    ultraSegs:   trace.coreSegLodUltra.get(coreName) || [],
    ultraStarts: trace.coreSegLodUltraStarts.get(coreName) || [],
  }
}

/**
 * Paint segments for a row.
 * Handles LOD selection, sub-pixel merging, segment fill + optional core tint.
 */
function paintSegments(ctx, segs, timeStart, timeEnd, pxPerNs, nsPerPx, rowY, rowH,
                       baseColor, trace, applyCoreTint, highlightKey, rowMk, darkMode) {
  const isHighlighted = highlightKey && rowMk === highlightKey

  const lod = nsPerPx > PAINT_LOD_COARSE ? 'coarse' : 'fine'

  const reduced = lod === 'coarse' ? lodReduce(segs, nsPerPx, trace.timeMin) : segs

  for (const seg of reduced) {
    const x1 = (seg.start - timeStart) * pxPerNs
    const x2 = (seg.end   - timeStart) * pxPerNs
    let w = Math.max(MIN_SEG_W, x2 - x1)

    // Skip completely off-screen
    if (x1 > ctx.canvas.clientWidth + 2 || x1 + w < -2) continue

    // Base colour
    ctx.fillStyle = baseColor
    ctx.fillRect(Math.round(x1), rowY, Math.ceil(w), rowH)

    // Core tint
    if (applyCoreTint) {
      const tint = coreTint(seg.core)
      if (tint) {
        ctx.fillStyle = tint
        ctx.fillRect(Math.round(x1), rowY, Math.ceil(w), rowH)
      }
    }

    // Highlight overlay
    if (isHighlighted) {
      ctx.fillStyle = 'rgba(255,255,200,0.25)'
      ctx.fillRect(Math.round(x1), rowY, Math.ceil(w), rowH)
    }

    // Outline (fine LOD only, wide enough segments)
    if (lod === 'fine' && w >= 3) {
      ctx.strokeStyle = darkMode ? 'rgba(0,0,0,0.4)' : 'rgba(0,0,0,0.3)'
      ctx.lineWidth = 0.5
      ctx.strokeRect(Math.round(x1) + 0.5, rowY + 0.5, Math.ceil(w) - 1, rowH - 1)
    }
  }
}

// ---- Row drawing functions -------------------------------------------------

function drawTaskRow(ctx, trace, row, timeStart, timeEnd, pxPerNs, nsPerPx, highlightKey, darkMode) {
  const mk = row.key
  const ld = taskLodData(trace, mk)
  const segs = visibleSegs(ld, timeStart, timeEnd, nsPerPx, trace.lodTimescalePerPx, trace.lodUltraTimescalePerPx)

  const rowY = row.y + 1
  const rowH = ROW_H - 2

  // Row background (zebra stripe)
  ctx.fillStyle = darkMode ? 'rgba(255,255,255,0.02)' : 'rgba(0,0,0,0.02)'
  ctx.fillRect(0, row.y, ctx.canvas.clientWidth, ROW_H)

  paintSegments(ctx, segs, timeStart, timeEnd, pxPerNs, nsPerPx,
    rowY, rowH, row.color, trace, /* coreTint */ true, highlightKey, mk, darkMode)
}

function drawCoreRow(ctx, trace, row, timeStart, timeEnd, pxPerNs, nsPerPx, darkMode) {
  const ld = coreLodData(trace, row.key)
  const segs = visibleSegs(ld, timeStart, timeEnd, nsPerPx, trace.lodTimescalePerPx, trace.lodUltraTimescalePerPx)

  ctx.fillStyle = darkMode ? 'rgba(255,255,255,0.03)' : 'rgba(0,0,0,0.03)'
  ctx.fillRect(0, row.y, ctx.canvas.clientWidth, ROW_H)

  // For core rows we draw each task's segments with their own task color
  // Use the raw seg colours individually (different tasks in the same row)
  const rowY = row.y + 1
  const rowH = ROW_H - 2
  const reduced = lodReduce(segs, nsPerPx, trace.timeMin)
  for (const seg of reduced) {
    if (isCoreName(seg.task)) continue
    const x1 = (seg.start - timeStart) * pxPerNs
    const x2 = (seg.end   - timeStart) * pxPerNs
    const w  = Math.max(MIN_SEG_W, x2 - x1)
    if (x1 > ctx.canvas.clientWidth + 2 || x1 + w < -2) continue
    const mk = taskMergeKey(seg.task)  // use merge key for consistent colours across views
    ctx.fillStyle = taskColor(mk, seg.task)
    ctx.fillRect(Math.round(x1), rowY, Math.ceil(w), rowH)
  }
}

function drawCoreTaskRow(ctx, trace, row, timeStart, timeEnd, pxPerNs, nsPerPx, highlightKey, darkMode) {
  const ld = coreTaskLodData(trace, row.coreKey, row.taskKey)
  const segs = visibleSegs(ld, timeStart, timeEnd, nsPerPx, trace.lodTimescalePerPx, trace.lodUltraTimescalePerPx)

  ctx.fillStyle = darkMode ? 'rgba(255,255,255,0.01)' : 'rgba(0,0,0,0.01)'
  ctx.fillRect(0, row.y, ctx.canvas.clientWidth, ROW_H)

  const mk = taskMergeKey(row.taskKey)
  paintSegments(ctx, segs, timeStart, timeEnd, pxPerNs, nsPerPx,
    row.y + 1, ROW_H - 2, row.color, trace, false, highlightKey, mk, darkMode)
}

function drawStiRow(ctx, trace, row, timeStart, timeEnd, pxPerNs, darkMode) {
  const rowY = row.y
  const evs = trace.stiEventsByTarget.get(row.key) || []
  const starts = trace.stiStartsByTarget.get(row.key) || []

  const lo = Math.max(0, bisectLeft(starts, timeStart) - 1)
  const hi = bisectRight(starts, timeEnd) + 1

  const markerR = 5
  const cy = rowY + STI_ROW_H / 2

  ctx.save()
  for (let i = lo; i < Math.min(hi, evs.length); i++) {
    const ev = evs[i]
    const cx = (ev.time - timeStart) * pxPerNs
    if (cx < -10 || cx > ctx.canvas.clientWidth + 10) continue

    const color = stiNoteColor(ev.note || ev.event || 'trigger')
    ctx.fillStyle = color
    ctx.strokeStyle = darkMode ? 'rgba(255,255,255,0.5)' : 'rgba(0,0,0,0.4)'
    ctx.lineWidth = 0.8
    ctx.beginPath()
    ctx.moveTo(cx,            cy - markerR)
    ctx.lineTo(cx + markerR,  cy)
    ctx.lineTo(cx,            cy + markerR)
    ctx.lineTo(cx - markerR,  cy)
    ctx.closePath()
    ctx.fill()
    ctx.stroke()
  }
  ctx.restore()
}

// ---- Cursors ---------------------------------------------------------------

const CURSOR_COLORS = ['#FF4444', '#44FF88', '#4499FF', '#FFAA22']

function drawCursors(ctx, cursors, trace, timeStart, pxPerNs, canvasW, canvasH, darkMode) {
  if (!cursors || cursors.length === 0) return
  ctx.save()
  ctx.font = 'bold 10px monospace'
  ctx.textBaseline = 'top'

  cursors.forEach((cursor, idx) => {
    if (cursor == null) return
    const x = Math.round((cursor - timeStart) * pxPerNs)
    if (x < 0 || x > canvasW) return

    const color = CURSOR_COLORS[idx % CURSOR_COLORS.length]
    ctx.strokeStyle = color
    ctx.lineWidth = 1.5
    ctx.setLineDash([4, 3])
    ctx.beginPath()
    ctx.moveTo(x + 0.5, 0)
    ctx.lineTo(x + 0.5, canvasH)
    ctx.stroke()
    ctx.setLineDash([])

    // Time label on ruler
    const label = formatTime(cursor, trace.timeScale)
    const tw = ctx.measureText(label).width + 8
    const lx = Math.min(x + 3, canvasW - tw - 2)
    ctx.fillStyle = color
    ctx.fillRect(lx, 2, tw, 16)
    ctx.fillStyle = '#000'
    ctx.fillText(label, lx + 4, 4)
  })
  ctx.restore()
}

// ---- Hover line (mouse position indicator) ---------------------------------

function drawHoverLine(ctx, t, trace, timeStart, pxPerNs, canvasW, canvasH, darkMode) {
  const x = Math.round((t - timeStart) * pxPerNs)
  if (x < -1 || x > canvasW + 1) return

  ctx.save()

  // Dashed vertical line through the body area
  ctx.strokeStyle = darkMode ? 'rgba(255,255,255,0.35)' : 'rgba(0,0,0,0.25)'
  ctx.lineWidth = 1
  ctx.setLineDash([3, 3])
  ctx.beginPath()
  ctx.moveTo(x + 0.5, RULER_H)
  ctx.lineTo(x + 0.5, canvasH)
  ctx.stroke()
  ctx.setLineDash([])

  // Floating time label at the bottom of the ruler
  const label = formatTime(t, trace.timeScale)
  ctx.font = '10px monospace'
  ctx.textAlign = 'left'
  ctx.textBaseline = 'middle'
  const tw = ctx.measureText(label).width + 8
  const lx = Math.max(2, Math.min(x - Math.round(tw / 2), canvasW - tw - 2))
  ctx.fillStyle = darkMode ? 'rgba(80,130,255,0.28)' : 'rgba(0,80,200,0.18)'
  ctx.fillRect(lx, RULER_H - 17, tw, 14)
  ctx.fillStyle = darkMode ? '#AAC8FF' : '#003C9A'
  ctx.fillText(label, lx + 4, RULER_H - 10)

  ctx.restore()
}

// ---- Hit-test: find STI event near canvas X,Y --------------------------------

/**
 * Find the nearest STI event within `radius` px of canvas point (cx, cy).
 * Returns the StiEvent object or null.
 *
 * @param {object} trace
 * @param {object} viewport  { timeStart, timeEnd, scrollY, canvasW, canvasH }
 * @param {object} options   { viewMode, expanded }
 * @param {number} cx        Canvas X coordinate
 * @param {number} cy        Canvas Y coordinate
 * @param {number} radius    Hit radius in pixels (default 8)
 * @returns {object|null}
 */
export function hitTestSti(trace, viewport, options, cx, cy, radius = 8) {
  const { timeStart, timeEnd, scrollY, canvasW, canvasH } = viewport
  const pxPerNs = canvasW / (timeEnd - timeStart)
  const { viewMode = 'task', expanded = new Set() } = options

  const { rows } = buildRowLayout(trace, viewMode, expanded, RULER_H - scrollY)

  for (const row of rows) {
    if (row.type !== 'sti') continue
    const cy_row = row.y + STI_ROW_H / 2
    if (Math.abs(cy - cy_row) > radius * 2) continue

    const evs = trace.stiEventsByTarget.get(row.key) || []
    const starts = trace.stiStartsByTarget.get(row.key) || []
    const tAtCx = timeStart + cx / pxPerNs
    const lo = Math.max(0, bisectLeft(starts, tAtCx - radius / pxPerNs) - 1)
    const hi = bisectRight(starts, tAtCx + radius / pxPerNs) + 1

    let best = null, bestDist = radius + 1
    for (let i = lo; i < Math.min(hi, evs.length); i++) {
      const ev = evs[i]
      const ex = (ev.time - timeStart) * pxPerNs
      const d = Math.abs(ex - cx)
      if (d < bestDist) { bestDist = d; best = ev }
    }
    if (best) return best
  }
  return null
}

/**
 * Return the row descriptor under canvas point (cx, cy), or null.
 */
export function hitTestRow(trace, viewport, options, cx, cy) {
  const { scrollY } = viewport
  const { viewMode = 'task', expanded = new Set() } = options
  const { rows } = buildRowLayout(trace, viewMode, expanded, RULER_H - scrollY)
  for (const row of rows) {
    if (cy >= row.y && cy < row.y + (row.type === 'sti' ? STI_ROW_H : ROW_H)) {
      return row
    }
  }
  return null
}
