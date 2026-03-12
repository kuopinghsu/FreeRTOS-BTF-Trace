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

import { taskColor, taskDisplayName, taskMergeKey, coreTint, coreColor, stiNoteColor } from '../utils/colors.js'
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

// ---- Vertical mode layout constants ----------------------------------------
export const RULER_W    = 120  // left ruler column width (px) – vertical mode
export const HEADER_H   = 160  // top label row height (px) – vertical mode
export const COL_W      =  26  // column width per task/core – vertical mode

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
    marks       = [],
  } = options

  const timeSpan = timeEnd - timeStart
  if (timeSpan <= 0 || canvasW <= 0) return

  const pxPerNs      = canvasW / timeSpan
  const nsPerPx      = timeSpan / canvasW   // timescale per pixel
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

  // ---- Marks (bookmarks) ----
  drawMarksHorizontal(ctx, marks, trace, timeStart, pxPerNs, canvasW, canvasH, darkMode)

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

export function drawCursors(ctx, cursors, trace, timeStart, pxPerNs, canvasW, canvasH, _darkMode) {
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

export function drawHoverLine(ctx, t, trace, timeStart, pxPerNs, canvasW, canvasH, darkMode) {
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
  const { timeStart, timeEnd, scrollY, canvasW } = viewport
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

// ===========================================================================
// MARKS (bookmarks)
// ===========================================================================

const MARK_COLOR = '#FF9933'

/**
 * Draw bookmark marks as vertical dashed lines in horizontal mode.
 */
export function drawMarksHorizontal(ctx, marks, trace, timeStart, pxPerNs, canvasW, canvasH, _darkMode) {
  if (!marks || marks.length === 0) return
  ctx.save()
  ctx.font = '10px monospace'
  ctx.textBaseline = 'top'

  for (const bm of marks) {
    const x = Math.round((bm.ns - timeStart) * pxPerNs)
    if (x < -2 || x > canvasW + 2) continue

    ctx.strokeStyle = MARK_COLOR
    ctx.lineWidth = 1.5
    ctx.setLineDash([6, 3])
    ctx.globalAlpha = 0.75
    ctx.beginPath()
    ctx.moveTo(x + 0.5, RULER_H)
    ctx.lineTo(x + 0.5, canvasH)
    ctx.stroke()
    ctx.setLineDash([])
    ctx.globalAlpha = 1.0

    // Label on ruler
    const label = bm.label || formatTime(bm.ns, trace.timeScale)
    const tw = ctx.measureText(label).width + 8
    const lx = Math.min(x + 3, canvasW - tw - 2)
    ctx.fillStyle = MARK_COLOR
    ctx.globalAlpha = 0.85
    ctx.fillRect(lx, RULER_H - 16, tw, 13)
    ctx.globalAlpha = 1.0
    ctx.fillStyle = '#000'
    ctx.fillText(label, lx + 4, RULER_H - 14)
  }
  ctx.restore()
}

// ===========================================================================
// VERTICAL MODE
// ===========================================================================

/**
 * Build a flat column descriptor array for the current view mode (vertical orientation).
 * Each col: { type: 'task'|'core'|'core-task'|'sti', key, label, color, x, colIdx }
 *
 * @param {object} trace
 * @param {string} viewMode   'task' or 'core'
 * @param {Set}    expanded   Set of expanded core names
 * @param {number} scrollX    Horizontal scroll offset in pixels
 * @returns {{ cols: Array, totalWidth: number }}
 */
export function buildColumnLayout(trace, viewMode, expanded, scrollX = 0) {
  const cols = []
  let rawIdx = 0

  if (viewMode === 'task') {
    for (const mk of trace.tasks) {
      const repr = trace.taskRepr.get(mk)
      const label = taskDisplayName(repr || mk)
      const color = taskColor(mk, repr)
      const x = RULER_W + rawIdx * COL_W - scrollX
      cols.push({ type: 'task', key: mk, label, color, x, colIdx: rawIdx })
      rawIdx++
    }
  } else {
    // Core view
    for (const coreName of trace.coreNames) {
      const cc = coreColor(coreName)
      const x = RULER_W + rawIdx * COL_W - scrollX
      cols.push({ type: 'core', key: coreName, label: coreName, color: cc, x, colIdx: rawIdx })
      rawIdx++
      if (expanded.has(coreName)) {
        const taskOrder = trace.coreTaskOrder.get(coreName) || []
        for (const rawTask of taskOrder) {
          const lbl = taskDisplayName(rawTask)
          const mk = taskMergeKey(rawTask)
          const col = taskColor(mk, rawTask)
          const cx = RULER_W + rawIdx * COL_W - scrollX
          cols.push({
            type: 'core-task', key: `${coreName}__${rawTask}`,
            coreKey: coreName, taskKey: rawTask, label: lbl, color: col, x: cx, colIdx: rawIdx,
          })
          rawIdx++
        }
      }
    }
  }

  // STI columns
  for (const ch of trace.stiChannels) {
    const x = RULER_W + rawIdx * COL_W - scrollX
    cols.push({ type: 'sti', key: ch, label: ch, color: '#888', x, colIdx: rawIdx })
    rawIdx++
  }

  return { cols, totalWidth: RULER_W + rawIdx * COL_W }
}

// ---- Vertical ruler (left side) -------------------------------------------

function drawVerticalRuler(ctx, trace, timeStart, timeEnd, pxPerNs, canvasH, headerH, rulerW, darkMode) {
  const timeSpan = timeEnd - timeStart
  const step = niceStep(timeSpan)
  const startSnap = Math.ceil(timeStart / step) * step

  const textColor = darkMode ? '#CCCCCC' : '#444444'
  const tickColor = darkMode ? '#555555' : '#BBBBBB'

  // Right border
  ctx.strokeStyle = darkMode ? '#444444' : '#CCCCCC'
  ctx.lineWidth = 1
  ctx.beginPath()
  ctx.moveTo(rulerW - 0.5, headerH)
  ctx.lineTo(rulerW - 0.5, canvasH)
  ctx.stroke()

  ctx.font = '10px monospace'
  ctx.textAlign = 'right'
  ctx.textBaseline = 'middle'

  for (let t = startSnap - step; t <= timeEnd + step; t += step) {
    const y = headerH + (t - timeStart) * pxPerNs
    if (y < headerH - 5 || y > canvasH + 5) continue

    ctx.strokeStyle = tickColor
    ctx.lineWidth = 1
    ctx.beginPath()
    ctx.moveTo(rulerW - 8, Math.round(y) + 0.5)
    ctx.lineTo(rulerW,     Math.round(y) + 0.5)
    ctx.stroke()

    const label = formatTime(t, trace.timeScale)
    ctx.fillStyle = textColor
    ctx.fillText(label, rulerW - 10, Math.round(y))
  }
}

// ---- Column header labels (rotated text) -----------------------------------

function drawColumnHeaders(ctx, cols, headerH, colW, highlightKey, darkMode) {
  for (const col of cols) {
    const x = col.x
    const cx = x + colW / 2

    // Column separator line
    ctx.strokeStyle = darkMode ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)'
    ctx.lineWidth = 1
    ctx.beginPath()
    ctx.moveTo(x + 0.5, 0)
    ctx.lineTo(x + 0.5, headerH)
    ctx.stroke()

    // Rotated label
    const isHl = highlightKey === col.key
    const color = isHl ? '#FFD700' : (col.type === 'sti' ? '#88AABB' : (darkMode ? '#D4D4D4' : '#1E1E1E'))
    ctx.save()
    ctx.translate(cx, headerH - 10)
    ctx.rotate(-Math.PI / 2)
    ctx.font = isHl ? 'bold 11px monospace' : '11px monospace'
    ctx.textAlign = 'left'
    ctx.textBaseline = 'middle'
    ctx.fillStyle = color
    // Elide to available header height
    const maxChars = Math.max(1, Math.floor((headerH - 20) / 7))
    const label = col.label.length > maxChars ? col.label.substring(0, maxChars - 1) + '…' : col.label
    ctx.fillText(label, 0, 0)
    ctx.restore()
  }
}

// ---- Segment drawing helpers (vertical) ------------------------------------

function paintSegmentsVertical(ctx, segs, timeStart, pxPerNs, nsPerPx, colX, colW, headerH,
                               baseColor, trace, applyCoreTint, highlightKey, colMk, darkMode) {
  const isHighlighted = highlightKey && colMk === highlightKey
  const lod = nsPerPx > PAINT_LOD_COARSE ? 'coarse' : 'fine'
  const reduced = lod === 'coarse' ? lodReduce(segs, nsPerPx, trace.timeMin) : segs

  const segX = colX + 1
  const segW = colW - 2

  for (const seg of reduced) {
    const y1 = headerH + (seg.start - timeStart) * pxPerNs
    const y2 = headerH + (seg.end   - timeStart) * pxPerNs
    const h  = Math.max(1, y2 - y1)

    if (y1 > ctx.canvas.clientHeight + 2 || y1 + h < headerH - 2) continue

    ctx.fillStyle = baseColor
    ctx.fillRect(segX, Math.round(y1), segW, Math.ceil(h))

    if (applyCoreTint) {
      const tint = coreTint(seg.core)
      if (tint) {
        ctx.fillStyle = tint
        ctx.fillRect(segX, Math.round(y1), segW, Math.ceil(h))
      }
    }

    if (isHighlighted) {
      ctx.fillStyle = 'rgba(255,255,200,0.25)'
      ctx.fillRect(segX, Math.round(y1), segW, Math.ceil(h))
    }

    if (lod === 'fine' && h >= 3) {
      ctx.strokeStyle = darkMode ? 'rgba(0,0,0,0.4)' : 'rgba(0,0,0,0.3)'
      ctx.lineWidth = 0.5
      ctx.strokeRect(segX + 0.5, Math.round(y1) + 0.5, segW - 1, Math.ceil(h) - 1)
    }
  }
}

// ---- Column drawing functions ----------------------------------------------

function drawTaskColumn(ctx, trace, col, timeStart, timeEnd, pxPerNs, nsPerPx, highlightKey, darkMode) {
  const mk = col.key
  const ld = taskLodData(trace, mk)
  const segs = visibleSegs(ld, timeStart, timeEnd, nsPerPx, trace.lodTimescalePerPx, trace.lodUltraTimescalePerPx)

  // Column background stripe
  ctx.fillStyle = col.colIdx % 2 === 0
    ? (darkMode ? '#252526' : '#FAFAFA')
    : (darkMode ? '#2D2D2D' : '#F5F5F5')
  ctx.fillRect(col.x, HEADER_H, COL_W, ctx.canvas.clientHeight)

  paintSegmentsVertical(ctx, segs, timeStart, pxPerNs, nsPerPx,
    col.x, COL_W, HEADER_H, col.color, trace, true, highlightKey, mk, darkMode)
}

function drawCoreColumn(ctx, trace, col, timeStart, timeEnd, pxPerNs, nsPerPx, darkMode) {
  const ld = coreLodData(trace, col.key)
  const segs = visibleSegs(ld, timeStart, timeEnd, nsPerPx, trace.lodTimescalePerPx, trace.lodUltraTimescalePerPx)

  ctx.fillStyle = col.colIdx % 2 === 0
    ? (darkMode ? '#252526' : '#FAFAFA')
    : (darkMode ? '#2D2D2D' : '#F5F5F5')
  ctx.fillRect(col.x, HEADER_H, COL_W, ctx.canvas.clientHeight)

  const reduced = lodReduce(segs, nsPerPx, trace.timeMin)
  const segX = col.x + 1
  const segW = COL_W - 2
  for (const seg of reduced) {
    if (isCoreName(seg.task)) continue
    const y1 = HEADER_H + (seg.start - timeStart) * pxPerNs
    const y2 = HEADER_H + (seg.end   - timeStart) * pxPerNs
    const h  = Math.max(1, y2 - y1)
    if (y1 > ctx.canvas.clientHeight + 2 || y1 + h < HEADER_H - 2) continue
    const mk = taskMergeKey(seg.task)
    ctx.fillStyle = taskColor(mk, seg.task)
    ctx.fillRect(segX, Math.round(y1), segW, Math.ceil(h))
  }
}

function drawCoreTaskColumn(ctx, trace, col, timeStart, timeEnd, pxPerNs, nsPerPx, highlightKey, darkMode) {
  const ld = coreTaskLodData(trace, col.coreKey, col.taskKey)
  const segs = visibleSegs(ld, timeStart, timeEnd, nsPerPx, trace.lodTimescalePerPx, trace.lodUltraTimescalePerPx)

  ctx.fillStyle = col.colIdx % 2 === 0
    ? (darkMode ? '#252526' : '#FAFAFA')
    : (darkMode ? '#2D2D2D' : '#F5F5F5')
  ctx.fillRect(col.x, HEADER_H, COL_W, ctx.canvas.clientHeight)

  const mk = taskMergeKey(col.taskKey)
  paintSegmentsVertical(ctx, segs, timeStart, pxPerNs, nsPerPx,
    col.x, COL_W, HEADER_H, col.color, trace, false, highlightKey, mk, darkMode)
}

function drawStiColumn(ctx, trace, col, timeStart, timeEnd, pxPerNs, darkMode) {
  ctx.fillStyle = darkMode ? '#1A1A2E' : '#F0F0FF'
  ctx.fillRect(col.x, HEADER_H, COL_W, ctx.canvas.clientHeight)

  const evs    = trace.stiEventsByTarget.get(col.key) || []
  const starts = trace.stiStartsByTarget.get(col.key) || []
  const lo = Math.max(0, bisectLeft(starts, timeStart) - 1)
  const hi = bisectRight(starts, timeEnd) + 1
  const cx = col.x + COL_W / 2
  const markerR = 4

  ctx.save()
  for (let i = lo; i < Math.min(hi, evs.length); i++) {
    const ev = evs[i]
    const cy = HEADER_H + (ev.time - timeStart) * pxPerNs
    if (cy < HEADER_H - 8 || cy > ctx.canvas.clientHeight + 8) continue

    const color = stiNoteColor(ev.note || ev.event || 'trigger')
    ctx.fillStyle = color
    ctx.strokeStyle = darkMode ? 'rgba(255,255,255,0.5)' : 'rgba(0,0,0,0.4)'
    ctx.lineWidth = 0.8
    ctx.beginPath()
    ctx.moveTo(cx,             cy - markerR)
    ctx.lineTo(cx + markerR,   cy)
    ctx.lineTo(cx,             cy + markerR)
    ctx.lineTo(cx - markerR,   cy)
    ctx.closePath()
    ctx.fill()
    ctx.stroke()
  }
  ctx.restore()
}

// ---- Cursors (vertical mode – horizontal lines) ----------------------------

export function drawCursorsVertical(ctx, cursors, trace, timeStart, pxPerNs, canvasW, canvasH, headerH, _darkMode) {
  if (!cursors || cursors.length === 0) return
  ctx.save()
  ctx.font = 'bold 10px monospace'
  ctx.textBaseline = 'middle'
  ctx.textAlign = 'right'

  cursors.forEach((cursor, idx) => {
    if (cursor == null) return
    const y = Math.round(headerH + (cursor - timeStart) * pxPerNs)
    if (y < headerH - 2 || y > canvasH + 2) return

    const color = CURSOR_COLORS[idx % CURSOR_COLORS.length]
    ctx.strokeStyle = color
    ctx.lineWidth = 1.5
    ctx.setLineDash([4, 3])
    ctx.beginPath()
    ctx.moveTo(0,       y + 0.5)
    ctx.lineTo(canvasW, y + 0.5)
    ctx.stroke()
    ctx.setLineDash([])

    // Time label on left ruler
    const label = formatTime(cursor, trace.timeScale)
    const tw = ctx.measureText(label).width + 8
    const ty = Math.min(y + 2, canvasH - 14)
    ctx.fillStyle = color
    ctx.fillRect(2, ty, tw, 14)
    ctx.fillStyle = '#000'
    ctx.fillText(label, tw - 2, ty + 7)
  })
  ctx.restore()
}

// ---- Hover line (vertical mode – horizontal dashed line) -------------------

export function drawHoverLineVertical(ctx, t, trace, timeStart, pxPerNs, canvasW, canvasH, headerH, darkMode) {
  const y = Math.round(headerH + (t - timeStart) * pxPerNs)
  if (y < headerH - 2 || y > canvasH + 2) return

  ctx.save()
  ctx.strokeStyle = darkMode ? 'rgba(255,255,255,0.35)' : 'rgba(0,0,0,0.25)'
  ctx.lineWidth = 1
  ctx.setLineDash([3, 3])
  ctx.beginPath()
  ctx.moveTo(RULER_W, y + 0.5)
  ctx.lineTo(canvasW, y + 0.5)
  ctx.stroke()
  ctx.setLineDash([])

  // Time label on ruler
  const label = formatTime(t, trace.timeScale)
  ctx.font = '10px monospace'
  ctx.textAlign = 'right'
  ctx.textBaseline = 'middle'
  const tw = ctx.measureText(label).width + 8
  const ly = Math.max(headerH + 3, Math.min(y - 7, canvasH - 17))
  ctx.fillStyle = darkMode ? 'rgba(80,130,255,0.28)' : 'rgba(0,80,200,0.18)'
  ctx.fillRect(RULER_W - 2 - tw, ly, tw, 14)
  ctx.fillStyle = darkMode ? '#AAC8FF' : '#003C9A'
  ctx.fillText(label, RULER_W - 4, ly + 7)

  ctx.restore()
}

// ---- Marks in vertical mode (horizontal dashed lines) ----------------------

export function drawMarksVertical(ctx, marks, trace, timeStart, pxPerNs, canvasW, canvasH, headerH, _darkMode) {
  if (!marks || marks.length === 0) return
  ctx.save()
  ctx.font = '10px monospace'
  ctx.textAlign = 'right'
  ctx.textBaseline = 'middle'

  for (const bm of marks) {
    const y = Math.round(headerH + (bm.ns - timeStart) * pxPerNs)
    if (y < headerH - 2 || y > canvasH + 2) continue

    ctx.strokeStyle = MARK_COLOR
    ctx.lineWidth = 1.5
    ctx.setLineDash([6, 3])
    ctx.globalAlpha = 0.75
    ctx.beginPath()
    ctx.moveTo(RULER_W, y + 0.5)
    ctx.lineTo(canvasW, y + 0.5)
    ctx.stroke()
    ctx.setLineDash([])
    ctx.globalAlpha = 1.0

    // Label on ruler
    const label = bm.label || formatTime(bm.ns, trace.timeScale)
    const tw = ctx.measureText(label).width + 8
    const ly = Math.max(headerH + 3, Math.min(y - 7, canvasH - 17))
    ctx.fillStyle = MARK_COLOR
    ctx.globalAlpha = 0.85
    ctx.fillRect(RULER_W - 2 - tw, ly, tw, 13)
    ctx.globalAlpha = 1.0
    ctx.fillStyle = '#000'
    ctx.fillText(label, RULER_W - 4, ly + 6)
  }
  ctx.restore()
}

// ===========================================================================
// VERTICAL MODE – Main render function
// ===========================================================================

/**
 * Render the full timeline in vertical orientation (time flows top→bottom).
 * Tasks/cores are columns; the left strip is a time ruler.
 *
 * @param {CanvasRenderingContext2D} ctx
 * @param {object} trace        BtfTrace from parseBtf()
 * @param {object} viewport     { timeStart, timeEnd, scrollX, canvasW, canvasH }
 * @param {object} options      { viewMode, expanded, cursors, highlightKey, showGrid, darkMode, marks }
 */
export function renderVertical(ctx, trace, viewport, options = {}) {
  const { timeStart, timeEnd, scrollX = 0, canvasW, canvasH } = viewport
  const {
    viewMode     = 'task',
    expanded     = new Set(),
    cursors      = [],
    highlightKey = null,
    showGrid     = false,
    darkMode     = true,
    hoverTime    = null,
    marks        = [],
  } = options

  const timeSpan = timeEnd - timeStart
  if (timeSpan <= 0 || canvasH <= HEADER_H) return

  const bodyH   = canvasH - HEADER_H
  const pxPerNs = bodyH / timeSpan
  const nsPerPx = timeSpan / bodyH

  // Clear
  ctx.clearRect(0, 0, canvasW, canvasH)

  // Background
  ctx.fillStyle = darkMode ? '#1E1E1E' : '#FFFFFF'
  ctx.fillRect(0, 0, canvasW, canvasH)

  // Ruler background (left strip)
  ctx.fillStyle = darkMode ? '#2B2B2B' : '#E8E8E8'
  ctx.fillRect(0, 0, RULER_W, canvasH)

  // Header background (top strip, right of ruler)
  ctx.fillStyle = darkMode ? '#1E1E1E' : '#F5F5F5'
  ctx.fillRect(RULER_W, 0, canvasW - RULER_W, HEADER_H)

  // Build column layout
  const { cols } = buildColumnLayout(trace, viewMode, expanded, scrollX)

  // Grid lines (horizontal, optional)
  if (showGrid) {
    const step = niceStep(timeSpan)
    const startSnap = Math.ceil(timeStart / step) * step
    ctx.strokeStyle = darkMode ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)'
    ctx.lineWidth = 1
    for (let t = startSnap; t <= timeEnd; t += step) {
      const y = HEADER_H + (t - timeStart) * pxPerNs
      ctx.beginPath()
      ctx.moveTo(RULER_W, Math.round(y) + 0.5)
      ctx.lineTo(canvasW, Math.round(y) + 0.5)
      ctx.stroke()
    }
  }

  // Vertical ruler (left side)
  drawVerticalRuler(ctx, trace, timeStart, timeEnd, pxPerNs, canvasH, HEADER_H, RULER_W, darkMode)

  // Clip to column body area (right of ruler, below header)
  ctx.save()
  ctx.beginPath()
  ctx.rect(RULER_W, HEADER_H, canvasW - RULER_W, bodyH + 1)
  ctx.clip()

  for (const col of cols) {
    if (col.x + COL_W < RULER_W || col.x >= canvasW) continue
    if (col.type === 'task') {
      drawTaskColumn(ctx, trace, col, timeStart, timeEnd, pxPerNs, nsPerPx, highlightKey, darkMode)
    } else if (col.type === 'core') {
      drawCoreColumn(ctx, trace, col, timeStart, timeEnd, pxPerNs, nsPerPx, darkMode)
    } else if (col.type === 'core-task') {
      drawCoreTaskColumn(ctx, trace, col, timeStart, timeEnd, pxPerNs, nsPerPx, highlightKey, darkMode)
    } else if (col.type === 'sti') {
      drawStiColumn(ctx, trace, col, timeStart, timeEnd, pxPerNs, darkMode)
    }
  }
  ctx.restore()

  // Marks (horizontal lines at bookmark timestamps)
  drawMarksVertical(ctx, marks, trace, timeStart, pxPerNs, canvasW, canvasH, HEADER_H, darkMode)

  // Cursors (horizontal lines)
  drawCursorsVertical(ctx, cursors, trace, timeStart, pxPerNs, canvasW, canvasH, HEADER_H, darkMode)

  // Hover line (horizontal)
  if (hoverTime !== null) {
    drawHoverLineVertical(ctx, hoverTime, trace, timeStart, pxPerNs, canvasW, canvasH, HEADER_H, darkMode)
  }

  // Column headers (drawn last, on top)
  ctx.save()
  ctx.beginPath()
  ctx.rect(RULER_W, 0, canvasW - RULER_W, HEADER_H)
  ctx.clip()
  drawColumnHeaders(ctx, cols, HEADER_H, COL_W, highlightKey, darkMode)
  ctx.restore()

  // Corner: covers ruler+header intersection
  ctx.fillStyle = darkMode ? '#1A1A1A' : '#E0E0E0'
  ctx.fillRect(0, 0, RULER_W, HEADER_H)
  ctx.strokeStyle = darkMode ? '#3C3C3C' : '#CCCCCC'
  ctx.lineWidth = 1
  ctx.strokeRect(0.5, 0.5, RULER_W - 1, HEADER_H - 1)
}

// ---- Hit-test (vertical mode) -----------------------------------------------

/**
 * Find the nearest STI event near (cx, cy) in vertical mode.
 * Time is on Y axis; columns are on X axis.
 */
export function hitTestStiVertical(trace, viewport, options, cx, cy, radius = 8) {
  const { timeStart, timeEnd, scrollX = 0, canvasH } = viewport
  const { viewMode = 'task', expanded = new Set() } = options
  if (cy < HEADER_H) return null
  const pxPerNs = (canvasH - HEADER_H) / (timeEnd - timeStart)
  const tAtCy = timeStart + (cy - HEADER_H) / pxPerNs

  const { cols } = buildColumnLayout(trace, viewMode, expanded, scrollX)
  for (const col of cols) {
    if (col.type !== 'sti') continue
    if (Math.abs(cx - (col.x + COL_W / 2)) > COL_W) continue

    const evs    = trace.stiEventsByTarget.get(col.key) || []
    const starts = trace.stiStartsByTarget.get(col.key) || []
    const lo = Math.max(0, bisectLeft(starts, tAtCy - radius / pxPerNs) - 1)
    const hi = bisectRight(starts, tAtCy + radius / pxPerNs) + 1

    let best = null, bestDist = radius + 1
    for (let i = lo; i < Math.min(hi, evs.length); i++) {
      const ev = evs[i]
      const ey = HEADER_H + (ev.time - timeStart) * pxPerNs
      const d = Math.abs(ey - cy)
      if (d < bestDist) { bestDist = d; best = ev }
    }
    if (best) return best
  }
  return null
}

/**
 * Return the column descriptor under canvas point (cx, cy) in vertical mode, or null.
 */
export function hitTestColumn(trace, viewport, options, cx, _cy) {
  const { scrollX = 0 } = viewport
  const { viewMode = 'task', expanded = new Set() } = options
  if (cx < RULER_W) return null
  const { cols } = buildColumnLayout(trace, viewMode, expanded, scrollX)
  for (const col of cols) {
    if (cx >= col.x && cx < col.x + COL_W) return col
  }
  return null
}

