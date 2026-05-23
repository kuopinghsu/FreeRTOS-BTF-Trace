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

import { taskColor, taskDisplayName, taskMergeKey, parseTaskName, coreTint, coreColor, stiNoteColor, lighterColor, complementaryColor } from '../utils/colors.js'
import { bisectLeft, bisectRight } from '../utils/bisect.js'
import { lodReduce } from '../utils/lod.js'
import { visibleSegs } from '../parser/btfParser.js'

// ---- Helpers ---------------------------------------------------------------
function isCoreName(name) {
  return typeof name === 'string' && name.startsWith('Core_')
}

// ---- Layout constants (must match CSS in TimelinePanel.vue) ---------------
export const LABEL_W        = 160  // width of left label column (px)  [DOM, not canvas]
export const RULER_H        =  40  // height of ruler row (px)
export const ROW_H          =  24  // task row height (px)
export const ROW_GAP        =   4  // gap between rows (px)
export const STI_ROW_H      =  18  // STI channel row height (px)
export const STI_WAVEFORM_H =  64  // expanded tag-event waveform row height (px)
export const MIN_SEG_W      =   1  // minimum segment paint width (px)

/**
 * Returns true if the STI channel name is a tag-event waveform channel.
 * Matches: tag_event, tag0_event … tag7_event
 */
export function isStiTagChannel(name) {
  return /^tag[0-7]?_event$/.test(name)
}

// ---- Vertical mode layout constants ----------------------------------------
export const RULER_W    = 120  // left ruler column width (px) – vertical mode
export const HEADER_H   = 160  // top label row height (px) – vertical mode
export const COL_W      =  26  // column width per task/core – vertical mode

// LOD thresholds (ns/px). Above PAINT_LOD_COARSE, nearby sub-pixel segments are
// merged via lodReduce; below it, individual segments are drawn with outlines.
// visibleSegs() already selects the right LOD bin tier automatically.
const PAINT_LOD_COARSE = 200    // ns/px: use coarse (merged) paint above this zoom level
const TICK_COLOR = '#E8C84A'

// ---- Time formatting -------------------------------------------------------

/**
 * Format a timestamp for display on the ruler.
 * @param {number} t       Timestamp in trace time-scale units.
 * @param {string} scale   Trace timeScale string (e.g. 'ns', 'us', 'ms').
 * @returns {string}
 */
export function formatTime(t, scale, decimals = 3) {
  if (scale === 'ns') {
    if (t >= 1e9)  return `${(t / 1e9).toFixed(decimals)} s`
    if (t >= 1e6)  return `${(t / 1e6).toFixed(decimals)} ms`
    if (t >= 1e3)  return `${(t / 1e3).toFixed(decimals)} µs`
    return `${t} ns`
  }
  if (scale === 'us') {
    if (t >= 1e6)  return `${(t / 1e6).toFixed(decimals)} s`
    if (t >= 1e3)  return `${(t / 1e3).toFixed(decimals)} ms`
    return `${t} µs`
  }
  if (scale === 'ms') {
    if (t >= 1e3)  return `${(t / 1e3).toFixed(decimals)} s`
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
export function buildRowLayout(trace, viewMode, expanded, yStart, showSti = true, stiExpanded = new Set()) {
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
        // TICK is rendered on the ruler band – exclude it from per-task sub-rows.
        const taskOrder = (trace.coreTaskOrder.get(coreName) || [])
          .filter(t => parseTaskName(t).name !== 'TICK')
        for (const rawTask of taskOrder) {
          const label = taskDisplayName(rawTask)
          const color = taskColor(taskMergeKey(rawTask), rawTask)
          rows.push({ type: 'core-task', key: `${coreName}__${rawTask}`, coreKey: coreName, taskKey: rawTask, label, color, y })
          y += ROW_H + ROW_GAP
        }
      }
    }
  }

  // STI rows
  if (showSti) {
    for (const ch of trace.stiChannels) {
      const isTag = isStiTagChannel(ch)
      const isExpanded = isTag && stiExpanded.has(ch)
      const rowH = isExpanded ? STI_WAVEFORM_H : STI_ROW_H
      rows.push({ type: 'sti', key: ch, label: ch, color: '#888', y, isTag, isExpanded })
      y += rowH + ROW_GAP
    }
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
    showSti     = true,
    stiExpanded = new Set(),
    stiLogScale = false,
  } = options
  const highlightSegment = options.highlightSegment ?? null

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
  const { rows } = buildRowLayout(trace, viewMode, expanded, RULER_H - scrollY, showSti, stiExpanded)

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
    const rowH = row.type === 'sti' ? (row.isExpanded ? STI_WAVEFORM_H : STI_ROW_H) : ROW_H
    if (rowY + rowH < RULER_H || rowY > canvasH) continue  // row not visible

    if (row.type === 'task') {
      drawTaskRow(ctx, trace, row, timeStart, timeEnd, pxPerNs, nsPerPx, highlightKey, canvasW, darkMode, highlightSegment)
    } else if (row.type === 'core') {
      drawCoreRow(ctx, trace, row, timeStart, timeEnd, pxPerNs, nsPerPx, canvasW, darkMode)
    } else if (row.type === 'core-task') {
      drawCoreTaskRow(ctx, trace, row, timeStart, timeEnd, pxPerNs, nsPerPx, highlightKey, canvasW, darkMode, highlightSegment)
    } else if (row.type === 'sti') {
      drawStiRow(ctx, trace, row, timeStart, timeEnd, pxPerNs, canvasW, darkMode, stiLogScale)
    }
  }

  ctx.restore()

  // ---- Locked segment enlarged pass (unclipped, draws over row gap) ----
  drawLockedSegmentHoriz(ctx, trace, rows, highlightSegment, timeStart, timeEnd, pxPerNs, nsPerPx, darkMode)

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
  const minorStep = step / 5
  const startSnap = Math.ceil(timeStart / step) * step

  const textColor  = darkMode ? '#CCCCCC' : '#444444'
  const tickColor  = darkMode ? '#555555' : '#BBBBBB'
  const minorTickColor = darkMode ? '#4A4A4A' : '#CFCFCF'

  ctx.font = '10px monospace'
  ctx.textAlign = 'left'
  ctx.textBaseline = 'middle'

  // Minor ticks
  if (minorStep > 0) {
    const minorStart = Math.ceil(timeStart / minorStep) * minorStep
    ctx.strokeStyle = minorTickColor
    ctx.lineWidth = 1
    for (let t = minorStart; t <= timeEnd + minorStep; t += minorStep) {
      // Skip major positions; they are rendered below with longer ticks.
      const k = Math.round(t / step)
      if (Math.abs(t - k * step) < minorStep * 0.08) continue
      const x = Math.round((t - timeStart) * pxPerNs)
      if (x < -10 || x > canvasW + 10) continue
      ctx.beginPath()
      ctx.moveTo(x + 0.5, RULER_H - 6)
      ctx.lineTo(x + 0.5, RULER_H)
      ctx.stroke()
    }
  }

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

  drawTickMarkersOnRulerHorizontal(ctx, trace, timeStart, timeEnd, pxPerNs, canvasW)
}

function drawTickMarkersOnRulerHorizontal(ctx, trace, timeStart, timeEnd, pxPerNs, canvasW) {
  const bandTop = RULER_H - 10
  const bandH = 8
  ctx.save()
  ctx.fillStyle = TICK_COLOR
  ctx.globalAlpha = 0.95

  // Task-type TICK segments
  const tickMk = taskMergeKey('TICK')
  const segs = trace.segByMergeKey?.get(tickMk) || []
  const starts = trace.segStartByMergeKey?.get(tickMk) || []
  if (segs.length > 0 && starts.length > 0) {
    const lo = Math.max(0, bisectLeft(starts, timeStart) - 1)
    const hi = Math.min(segs.length, bisectRight(starts, timeEnd) + 1)
    for (let i = lo; i < hi; i++) {
      const seg = segs[i]
      const x1 = (seg.start - timeStart) * pxPerNs
      if (x1 < -2 || x1 > canvasW + 2) continue
      ctx.fillRect(Math.round(x1) - 0.5, bandTop, 2, bandH)
    }
  }

  // STI-type TICK events
  const stiTimes = trace.tickStiTimes || []
  if (stiTimes.length > 0) {
    const lo2 = Math.max(0, bisectLeft(stiTimes, timeStart) - 1)
    const hi2 = Math.min(stiTimes.length, bisectRight(stiTimes, timeEnd) + 1)
    for (let i = lo2; i < hi2; i++) {
      const x1 = (stiTimes[i] - timeStart) * pxPerNs
      if (x1 < -2 || x1 > canvasW + 2) continue
      ctx.fillRect(Math.round(x1) - 0.5, bandTop, 2, bandH)
    }
  }

  ctx.restore()
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
                       baseColor, trace, applyCoreTint, highlightKey, rowMk, darkMode, segLabel, hlSeg) {
  const isHighlighted = (highlightKey && rowMk === highlightKey) && !hlSeg

  const lod = nsPerPx > PAINT_LOD_COARSE ? 'coarse' : 'fine'

  const reduced = lod === 'coarse' ? lodReduce(segs, nsPerPx, trace.timeMin) : segs

  // Collect label rects for a deferred single-setup text pass.
  const labelRects = []

  for (const seg of reduced) {
    const x1 = (seg.start - timeStart) * pxPerNs
    const x2 = (seg.end   - timeStart) * pxPerNs
    let w = Math.max(MIN_SEG_W, x2 - x1)

    // Skip completely off-screen (derive width from time params, not DOM, to avoid racing a resize)
    if (x1 > (timeEnd - timeStart) * pxPerNs + 2 || x1 + w < -2) continue

    // Base colour
    const isSegLocked = hlSeg && seg.start === hlSeg.start && seg.end === hlSeg.end && seg.task === hlSeg.task
    const drawX  = Math.round(x1)
    const drawW  = Math.ceil(w)
    const drawY  = rowY
    const drawH  = rowH
    ctx.fillStyle = baseColor
    ctx.fillRect(drawX, drawY, drawW, drawH)

    // Core tint
    if (applyCoreTint) {
      const tint = coreTint(seg.core)
      if (tint) {
        ctx.fillStyle = tint
        ctx.fillRect(drawX, drawY, drawW, drawH)
      }
    }

    // Highlight overlay
    if (isHighlighted) {
      ctx.fillStyle = 'rgba(255,255,200,0.25)'
      ctx.fillRect(drawX, drawY, drawW, drawH)
    }

    // Outline (fine LOD only, wide enough segments)
    if (lod === 'fine' && w >= 3) {
      if (isSegLocked) {
        ctx.strokeStyle = complementaryColor(baseColor)
        ctx.lineWidth = 2.5
      } else {
        ctx.strokeStyle = darkMode ? 'rgba(0,0,0,0.4)' : 'rgba(0,0,0,0.3)'
        ctx.lineWidth = 0.5
      }
      ctx.strokeRect(drawX + 0.5, drawY + 0.5, drawW - 1, drawH - 1)
    }

    // Collect label info for deferred pass
    if (segLabel && w >= 40) {
      labelRects.push({ drawX, drawW })
    }
  }

  // Deferred text-label pass: set font/color once, clip-and-draw each label.
  if (labelRects.length > 0) {
    ctx.font = '10px sans-serif'
    ctx.fillStyle = darkMode ? 'rgba(255,255,255,0.85)' : 'rgba(0,0,0,0.75)'
    ctx.textBaseline = 'middle'
    const midY = rowY + rowH / 2
    for (const lb of labelRects) {
      const tx = lb.drawX + 3
      ctx.save()
      ctx.beginPath()
      ctx.rect(tx, rowY, lb.drawW - 6, rowH)
      ctx.clip()
      ctx.fillText(segLabel, tx, midY)
      ctx.restore()
    }
  }
}

// ---- Row drawing functions -------------------------------------------------

/**
 * Draw the locked (highlighted) segment enlarged by 10% vertically,
 * unclipped, over the body area. Called after ctx.restore() in render().
 */
function drawLockedSegmentHoriz(ctx, trace, rows, hlSeg, timeStart, timeEnd, pxPerNs, nsPerPx, darkMode) {
  if (!hlSeg) return
  const mk = taskMergeKey(hlSeg.task)
  for (const row of rows) {
    if (row.key !== mk && !(row.taskKey && taskMergeKey(row.taskKey) === mk)) continue
    const x1        = (hlSeg.start - timeStart) * pxPerNs
    const x2        = (hlSeg.end   - timeStart) * pxPerNs
    const w         = Math.max(MIN_SEG_W, x2 - x1)
    if (x1 > (timeEnd - timeStart) * pxPerNs + 2 || x1 + w < -2) return
    const baseColor = row.color
    const slot       = ROW_H + ROW_GAP            // full row slot including gap
    const newH       = slot * 1.10                // 10% of slot
    const rowCenter  = row.y + ROW_H / 2         // center of the row band
    const drawY     = rowCenter - newH / 2
    const drawX     = Math.round(x1)
    const drawW     = Math.ceil(w)
    ctx.fillStyle   = baseColor
    ctx.fillRect(drawX, drawY, drawW, newH)
    if (nsPerPx <= PAINT_LOD_COARSE && w >= 3) {
      ctx.strokeStyle = complementaryColor(baseColor)
      ctx.lineWidth   = 2.5
      ctx.strokeRect(drawX + 0.5, drawY + 0.5, drawW - 1, newH - 1)
    }
    // Redraw label on top of enlarged segment
    if (row.label && drawW >= 40) {
      ctx.save()
      ctx.font = '10px sans-serif'
      ctx.fillStyle = darkMode ? 'rgba(255,255,255,0.85)' : 'rgba(0,0,0,0.75)'
      ctx.textBaseline = 'middle'
      const tx = drawX + 3
      ctx.beginPath()
      ctx.rect(tx, drawY, drawW - 6, newH)
      ctx.clip()
      ctx.fillText(row.label, tx, drawY + newH / 2)
      ctx.restore()
    }
    return
  }
}

function drawLockedSegmentVert(ctx, trace, cols, hlSeg, timeStart, timeEnd, pxPerNs, nsPerPx, headerH, canvasH, darkMode) {
  if (!hlSeg) return
  const mk = taskMergeKey(hlSeg.task)
  for (const col of cols) {
    if (col.key !== mk && !(col.taskKey && taskMergeKey(col.taskKey) === mk)) continue
    const colX      = col.x
    const segX      = colX + 1
    const segW      = COL_W - 2
    const y1        = headerH + (hlSeg.start - timeStart) * pxPerNs
    const y2        = headerH + (hlSeg.end   - timeStart) * pxPerNs
    const h         = Math.max(1, y2 - y1)
    if (y1 > canvasH + 2 || y1 + h < headerH - 2) return
    const baseColor = col.color
    const slot       = COL_W + ROW_GAP            // full column slot including gap
    const newW       = slot * 1.10
    const colCenter  = col.x + COL_W / 2
    const drawX     = colCenter - newW / 2
    const drawY     = Math.round(y1)
    const drawH     = Math.ceil(h)
    ctx.fillStyle   = baseColor
    ctx.fillRect(drawX, drawY, newW, drawH)
    if (nsPerPx <= PAINT_LOD_COARSE && h >= 3) {
      ctx.strokeStyle = complementaryColor(baseColor)
      ctx.lineWidth   = 2.5
      ctx.strokeRect(drawX + 0.5, drawY + 0.5, newW - 1, drawH - 1)
    }
    // Redraw label on top of enlarged segment (rotated, as in vertical mode)
    if (col.label && drawH >= 40) {
      ctx.save()
      ctx.font = '10px sans-serif'
      ctx.fillStyle = darkMode ? 'rgba(255,255,255,0.85)' : 'rgba(0,0,0,0.75)'
      ctx.textBaseline = 'middle'
      ctx.textAlign = 'left'
      const cx = drawX + newW / 2
      const topY = drawY + 3
      ctx.translate(cx, topY)
      ctx.rotate(Math.PI / 2)
      ctx.fillText(col.label, 0, 0)
      ctx.restore()
    }
    return
  }
}

function drawTaskRow(ctx, trace, row, timeStart, timeEnd, pxPerNs, nsPerPx, highlightKey, canvasW, darkMode, hlSeg) {
  const mk = row.key
  const ld = taskLodData(trace, mk)
  const segs = visibleSegs(ld, timeStart, timeEnd, nsPerPx, trace.lodTimescalePerPx, trace.lodUltraTimescalePerPx)

  const rowY = row.y + 1
  const rowH = ROW_H - 2

  // Row background (zebra stripe)
  ctx.fillStyle = darkMode ? 'rgba(255,255,255,0.02)' : 'rgba(0,0,0,0.02)'
  ctx.fillRect(0, row.y, canvasW, ROW_H)

  paintSegments(ctx, segs, timeStart, timeEnd, pxPerNs, nsPerPx,
    rowY, rowH, row.color, trace, /* coreTint */ true, highlightKey, mk, darkMode, row.label, hlSeg)
}

function drawCoreRow(ctx, trace, row, timeStart, timeEnd, pxPerNs, nsPerPx, canvasW, darkMode) {
  const ld = coreLodData(trace, row.key)
  const segs = visibleSegs(ld, timeStart, timeEnd, nsPerPx, trace.lodTimescalePerPx, trace.lodUltraTimescalePerPx)

  ctx.fillStyle = darkMode ? 'rgba(255,255,255,0.03)' : 'rgba(0,0,0,0.03)'
  ctx.fillRect(0, row.y, canvasW, ROW_H)

  const rowY = row.y + 1
  const rowH = ROW_H - 2
  const reduced = lodReduce(segs, nsPerPx, trace.timeMin)

  // Cache seg.task → fill-color to avoid repeated taskMergeKey + taskColor hash
  const colorCache = new Map()
  // Collect label draws for a deferred single-setup text pass
  const labelRects = []
  const midY = rowY + rowH / 2

  for (const seg of reduced) {
    if (isCoreName(seg.task)) continue
    // TICK is shown as ruler band marks – skip it in the core summary row.
    if (parseTaskName(seg.task).name === 'TICK') continue
    const x1 = (seg.start - timeStart) * pxPerNs
    const x2 = (seg.end   - timeStart) * pxPerNs
    const w  = Math.max(MIN_SEG_W, x2 - x1)
    if (x1 > canvasW + 2 || x1 + w < -2) continue

    let color = colorCache.get(seg.task)
    if (color === undefined) {
      color = taskColor(taskMergeKey(seg.task), seg.task)
      colorCache.set(seg.task, color)
    }
    const drawX = Math.round(x1)
    const drawW = Math.ceil(w)
    ctx.fillStyle = color
    ctx.fillRect(drawX, rowY, drawW, rowH)

    if (w >= 40) {
      labelRects.push({ drawX, drawW, name: taskDisplayName(seg.task) })
    }
  }

  // Deferred text pass: single font/color setup for all labels
  if (labelRects.length > 0) {
    ctx.font = '10px sans-serif'
    ctx.fillStyle = darkMode ? 'rgba(255,255,255,0.85)' : 'rgba(0,0,0,0.75)'
    ctx.textBaseline = 'middle'
    for (const lb of labelRects) {
      const tx = lb.drawX + 3
      ctx.save()
      ctx.beginPath()
      ctx.rect(tx, rowY, lb.drawW - 6, rowH)
      ctx.clip()
      ctx.fillText(lb.name, tx, midY)
      ctx.restore()
    }
  }
}

function drawCoreTaskRow(ctx, trace, row, timeStart, timeEnd, pxPerNs, nsPerPx, highlightKey, canvasW, darkMode, hlSeg) {
  const ld = coreTaskLodData(trace, row.coreKey, row.taskKey)
  const segs = visibleSegs(ld, timeStart, timeEnd, nsPerPx, trace.lodTimescalePerPx, trace.lodUltraTimescalePerPx)

  ctx.fillStyle = darkMode ? 'rgba(255,255,255,0.01)' : 'rgba(0,0,0,0.01)'
  ctx.fillRect(0, row.y, canvasW, ROW_H)

  const mk = taskMergeKey(row.taskKey)
  paintSegments(ctx, segs, timeStart, timeEnd, pxPerNs, nsPerPx,
    row.y + 1, ROW_H - 2, row.color, trace, false, highlightKey, mk, darkMode, row.label, hlSeg)
}

function drawStiRow(ctx, trace, row, timeStart, timeEnd, pxPerNs, canvasW, darkMode, logScale = false) {
  if (row.isExpanded) {
    drawStiWaveformRow(ctx, trace, row, timeStart, timeEnd, pxPerNs, canvasW, darkMode, logScale)
    return
  }

  const rowY = row.y
  const evs = trace.stiEventsByTarget.get(row.key) || []
  const starts = trace.stiStartsByTarget.get(row.key) || []

  const lo = Math.max(0, bisectLeft(starts, timeStart) - 1)
  const hi = bisectRight(starts, timeEnd) + 1

  const markerR = 5
  const cy = rowY + STI_ROW_H / 2

  ctx.save()
  ctx.strokeStyle = darkMode ? 'rgba(255,255,255,0.5)' : 'rgba(0,0,0,0.4)'
  ctx.lineWidth = 0.8
  const stiColorCache = new Map()
  for (let i = lo; i < Math.min(hi, evs.length); i++) {
    const ev = evs[i]
    const cx = (ev.time - timeStart) * pxPerNs
    if (cx < -10 || cx > canvasW + 10) continue

    const noteKey = ev.note || ev.event || 'trigger'
    let color = stiColorCache.get(noteKey)
    if (color === undefined) { color = stiNoteColor(noteKey); stiColorCache.set(noteKey, color) }
    ctx.fillStyle = color
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

/**
 * Draw an expanded tag-event STI channel as an analog line-chart waveform.
 * Values are mapped: 0 → bottom of row, 100 → top of row.
 * Points outside [0,100] are clamped. The line holds the last value (step-hold)
 * until the next event.
 */
function drawStiWaveformRow(ctx, trace, row, timeStart, timeEnd, pxPerNs, canvasW, darkMode, logScale = false) {
  const rowY = row.y
  const rowH = STI_WAVEFORM_H

  const evs = trace.stiEventsByTarget.get(row.key) || []
  const starts = trace.stiStartsByTarget.get(row.key) || []

  // Row background
  ctx.fillStyle = darkMode ? 'rgba(255,255,255,0.03)' : 'rgba(0,0,0,0.03)'
  ctx.fillRect(0, rowY, canvasW, rowH)

  // Axis lines at scale 0 and scale 100
  const PAD = 4
  const chartTop    = rowY + PAD
  const chartBottom = rowY + rowH - PAD
  const chartH      = chartBottom - chartTop

  const axisColor = darkMode ? 'rgba(255,255,255,0.12)' : 'rgba(0,0,0,0.12)'
  ctx.strokeStyle = axisColor
  ctx.lineWidth = 0.5
  ctx.setLineDash([3, 3])
  ctx.beginPath()
  ctx.moveTo(0, chartBottom + 0.5)
  ctx.lineTo(canvasW, chartBottom + 0.5)
  ctx.stroke()
  ctx.beginPath()
  ctx.moveTo(0, chartTop + 0.5)
  ctx.lineTo(canvasW, chartTop + 0.5)
  ctx.stroke()
  ctx.setLineDash([])

  // Scale labels — will be replaced with real min/max after we compute them,
  // so we defer the label draw to after evVal/valMin/valMax are known.
  // (labels are drawn later in this function)

  if (evs.length === 0) return

  // Helper: extract numeric value from an event (note field holds the value,
  // e.g. "12345,Core_0,0,STI,tag0_event,0,trigger,42" → note="42")
  function evVal(ev) {
    return parseFloat(ev.note !== '' ? ev.note : ev.event)
  }

  // Use precomputed min/max from the parser (O(1)) so every render frame
  // avoids an O(N) scan over the full event list.
  const preRange = trace.stiValRange?.get(row.key)
  let valMin, valMax
  if (preRange) {
    valMin = preRange.min
    valMax = preRange.max
  } else {
    // Fallback: compute on-the-fly (trace predates stiValRange field)
    valMin = Infinity; valMax = -Infinity
    for (let i = 0; i < evs.length; i++) {
      const v = evVal(evs[i])
      if (isNaN(v)) continue
      if (v < valMin) valMin = v
      if (v > valMax) valMax = v
    }
    if (!isFinite(valMin)) return   // no numeric values at all — nothing to draw
  }
  if (!isFinite(valMin)) return   // no numeric values at all — nothing to draw

  // If all values are identical give a tiny ±1 padding so the line is visible
  if (valMin === valMax) { valMin -= 1; valMax += 1 }

  // Log₂ transform: signed log2 so it handles zero and negatives gracefully.
  // signedLog2(v) = sign(v) * log2(1 + |v|)
  function signedLog2(v) {
    return Math.sign(v) * Math.log2(1 + Math.abs(v))
  }

  const mappedMin = logScale ? signedLog2(valMin) : valMin
  const mappedMax = logScale ? signedLog2(valMax) : valMax
  const mappedRange = mappedMax - mappedMin

  // Helper: map a numeric value to canvas Y (valMin = bottom, valMax = top)
  function valToY(v) {
    const mapped = logScale ? signedLog2(v) : v
    return chartBottom - ((mapped - mappedMin) / mappedRange) * chartH
  }

  // Find events in the visible range (extend one step before/after for step-hold)
  const lo = Math.max(0, bisectLeft(starts, timeStart) - 1)
  const hi = Math.min(evs.length, bisectRight(starts, timeEnd) + 1)

  // Gather the slice we'll draw
  const slice = evs.slice(lo, hi)
  if (slice.length === 0) return

  const lineColor = darkMode ? '#5BC8FF' : '#0070CC'
  const dotColor  = darkMode ? '#80DFFF' : '#0050AA'

  // Draw axis labels now that we know the real scale
  function fmtVal(v) {
    if (Math.abs(v) >= 1e6) return (v / 1e6).toFixed(2) + 'M'
    if (Math.abs(v) >= 1e3) return (v / 1e3).toFixed(1) + 'k'
    return String(Math.round(v))
  }
  ctx.font = '9px monospace'
  ctx.textAlign = 'right'
  ctx.textBaseline = 'bottom'
  ctx.fillStyle = darkMode ? 'rgba(255,255,255,0.3)' : 'rgba(0,0,0,0.3)'
  ctx.fillText(fmtVal(valMax), canvasW - 2, chartTop + 10)
  ctx.textBaseline = 'top'
  ctx.fillText(fmtVal(valMin), canvasW - 2, chartBottom - 10)
  if (logScale) {
    ctx.textAlign = 'left'
    ctx.textBaseline = 'top'
    ctx.fillStyle = darkMode ? 'rgba(91,200,255,0.55)' : 'rgba(0,100,200,0.55)'
    ctx.fillText('log₂', 4, chartTop + 2)
  }

  ctx.save()
  ctx.beginPath()
  ctx.rect(0, rowY, canvasW, rowH)
  ctx.clip()

  ctx.strokeStyle = lineColor
  ctx.lineWidth = 1.5
  ctx.lineJoin = 'round'

  let firstPoint = true
  for (let i = 0; i < slice.length; i++) {
    const ev = slice[i]
    const val = evVal(ev)
    if (isNaN(val)) continue

    const cx = (ev.time - timeStart) * pxPerNs
    const cy = valToY(val)

    if (firstPoint) {
      // If there is a prior event off-screen to the left, start the line from
      // the interpolated position at the canvas left edge.
      if (lo > 0) {
        const prevEv  = evs[lo - 1]
        const prevVal = evVal(prevEv)
        if (!isNaN(prevVal)) {
          const prevCx = (prevEv.time - timeStart) * pxPerNs
          const prevCy = valToY(prevVal)
          // Linear interpolation to x=0
          const t = prevCx === cx ? 0 : (0 - prevCx) / (cx - prevCx)
          const startCy = prevCy + t * (cy - prevCy)
          ctx.beginPath()
          ctx.moveTo(0, startCy)
          ctx.lineTo(cx, cy)
          firstPoint = false
          continue
        }
      }
      ctx.beginPath()
      ctx.moveTo(cx, cy)
      firstPoint = false
    } else {
      ctx.lineTo(cx, cy)   // straight line to next point
    }
  }
  ctx.stroke()

  // Draw dots at each sample point
  ctx.fillStyle = dotColor
  for (let i = 0; i < slice.length; i++) {
    const ev = slice[i]
    const val = evVal(ev)
    if (isNaN(val)) continue
    const cx = (ev.time - timeStart) * pxPerNs
    const cy = valToY(val)
    ctx.beginPath()
    ctx.arc(cx, cy, 2.5, 0, Math.PI * 2)
    ctx.fill()
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
  const { viewMode = 'task', expanded = new Set(), showSti = true, stiExpanded = new Set() } = options
  if (!showSti) return null

  const { rows } = buildRowLayout(trace, viewMode, expanded, RULER_H - scrollY, showSti, stiExpanded)

  for (const row of rows) {
    if (row.type !== 'sti') continue
    const rowH = row.isExpanded ? STI_WAVEFORM_H : STI_ROW_H
    const cy_row = row.y + rowH / 2
    if (Math.abs(cy - cy_row) > rowH) continue

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
  const { viewMode = 'task', expanded = new Set(), showSti = true, stiExpanded = new Set() } = options
  const { rows } = buildRowLayout(trace, viewMode, expanded, RULER_H - scrollY, showSti, stiExpanded)
  for (const row of rows) {
    const rowH = row.type === 'sti' ? (row.isExpanded ? STI_WAVEFORM_H : STI_ROW_H) : ROW_H
    if (cy >= row.y && cy < row.y + rowH) {
      return row
    }
  }
  return null
}

// ===========================================================================
// MARKS (bookmarks + annotations)
// ===========================================================================

/**
 * Return the exact segment (raw object) under canvas point (cx, cy) in
 * horizontal mode, or null if no segment bar was clicked.
 */
export function hitTestSegment(trace, viewport, options, cx, cy) {
  const { timeStart, timeEnd, scrollY, canvasW } = viewport
  const { viewMode = 'task', expanded = new Set(), showSti = true, stiExpanded = new Set() } = options
  if (cy < RULER_H) return null
  const pxPerNs = canvasW / (timeEnd - timeStart)
  const { rows } = buildRowLayout(trace, viewMode, expanded, RULER_H - scrollY, showSti, stiExpanded)

  let row = null
  for (const r of rows) {
    if (r.type !== 'task' && r.type !== 'core-task') continue
    if (cy >= r.y && cy < r.y + ROW_H) { row = r; break }
  }
  if (!row) return null

  const tAtCx = timeStart + cx / pxPerNs
  let segs, starts
  if (row.type === 'task') {
    segs   = trace.segByMergeKey.get(row.key) || []
    starts = trace.segStartByMergeKey.get(row.key) || []
  } else {
    const cMap      = trace.coreTaskSegs.get(row.coreKey)
    const cStartMap = trace.coreTaskSegStarts.get(row.coreKey)
    segs   = (cMap      && cMap.get(row.taskKey))      || []
    starts = (cStartMap && cStartMap.get(row.taskKey)) || []
  }

  const lo = Math.max(0, bisectLeft(starts, tAtCx) - 1)
  for (let i = lo; i < segs.length; i++) {
    const s = segs[i]
    if (s.start > tAtCx) break
    if (s.end >= tAtCx) return s
  }
  return null
}

/**
 * Return the exact segment under canvas point (cx, cy) in vertical mode, or null.
 */
export function hitTestSegmentVertical(trace, viewport, options, cx, cy) {
  const { timeStart, timeEnd, scrollX = 0, canvasH } = viewport
  const { viewMode = 'task', expanded = new Set(), showSti = true } = options
  if (cy < HEADER_H || cx < RULER_W) return null
  const bodyH   = canvasH - HEADER_H
  const pxPerNs = bodyH / (timeEnd - timeStart)
  const tAtCy   = timeStart + (cy - HEADER_H) / pxPerNs

  const { cols } = buildColumnLayout(trace, viewMode, expanded, scrollX, showSti)
  let col = null
  for (const c of cols) {
    if (c.type !== 'task' && c.type !== 'core-task') continue
    if (cx >= c.x && cx < c.x + COL_W) { col = c; break }
  }
  if (!col) return null

  let segs, starts
  if (col.type === 'task') {
    segs   = trace.segByMergeKey.get(col.key) || []
    starts = trace.segStartByMergeKey.get(col.key) || []
  } else {
    const cMap      = trace.coreTaskSegs.get(col.coreKey)
    const cStartMap = trace.coreTaskSegStarts.get(col.coreKey)
    segs   = (cMap      && cMap.get(col.taskKey))      || []
    starts = (cStartMap && cStartMap.get(col.taskKey)) || []
  }

  const lo = Math.max(0, bisectLeft(starts, tAtCy) - 1)
  for (let i = lo; i < segs.length; i++) {
    const s = segs[i]
    if (s.start > tAtCy) break
    if (s.end >= tAtCy) return s
  }
  return null
}

const BOOKMARK_COLOR = '#FFD700'
const ANNOTATION_COLOR = '#FF8C00'

function markKind(mark) {
  return mark?.type === 'annotation' ? 'annotation' : 'bookmark'
}

function markColor(mark) {
  return markKind(mark) === 'annotation' ? ANNOTATION_COLOR : BOOKMARK_COLOR
}

function markLabel(mark, trace) {
  const txt = mark?.label || mark?.note || ''
  return txt || formatTime(mark.ns, trace.timeScale)
}

function drawMarkFlagHorizontal(ctx, x, kind) {
  const halfW = 4
  const tipY = RULER_H - 2
  const baseY = tipY - 6
  const color = kind === 'annotation' ? '#FFA500' : '#FFD700'
  ctx.fillStyle = color
  ctx.beginPath()
  if (kind === 'annotation') {
    const midY = (baseY + tipY) / 2
    ctx.moveTo(x, baseY)
    ctx.lineTo(x + halfW, midY)
    ctx.lineTo(x, tipY)
    ctx.lineTo(x - halfW, midY)
  } else {
    ctx.moveTo(x - halfW, baseY)
    ctx.lineTo(x + halfW, baseY)
    ctx.lineTo(x, tipY)
  }
  ctx.closePath()
  ctx.fill()
}

function drawMarkFlagVertical(ctx, y, kind) {
  const halfW = 4
  const rightX = RULER_W - 2
  const leftX = rightX - 6
  const color = kind === 'annotation' ? '#FFA500' : '#FFD700'
  ctx.fillStyle = color
  ctx.beginPath()
  if (kind === 'annotation') {
    const midX = (leftX + rightX) / 2
    ctx.moveTo(leftX, y)
    ctx.lineTo(midX, y - halfW)
    ctx.lineTo(rightX, y)
    ctx.lineTo(midX, y + halfW)
  } else {
    ctx.moveTo(leftX, y - halfW)
    ctx.lineTo(leftX, y + halfW)
    ctx.lineTo(rightX, y)
  }
  ctx.closePath()
  ctx.fill()
}

/**
 * Draw marks as vertical lines in horizontal mode.
 */
export function drawMarksHorizontal(ctx, marks, trace, timeStart, pxPerNs, canvasW, canvasH, _darkMode, selectedId = null) {
  if (!marks || marks.length === 0) return
  ctx.save()
  ctx.font = '10px monospace'
  ctx.textBaseline = 'top'

  for (const mark of marks) {
    const x = Math.round((mark.ns - timeStart) * pxPerNs)
    if (x < -2 || x > canvasW + 2) continue
    const kind = markKind(mark)
    const color = markColor(mark)
    const isSelected = selectedId !== null && mark.id === selectedId

    if (isSelected) {
      ctx.strokeStyle = 'rgba(255,255,255,0.35)'
      ctx.lineWidth = 5
      ctx.setLineDash([])
      ctx.beginPath()
      ctx.moveTo(x + 0.5, RULER_H)
      ctx.lineTo(x + 0.5, canvasH)
      ctx.stroke()
    }
    ctx.strokeStyle = color
    ctx.lineWidth = isSelected ? 2.5 : (kind === 'annotation' ? 1.0 : 1.2)
    ctx.setLineDash(isSelected ? [] : (kind === 'annotation' ? [6, 3] : []))
    ctx.globalAlpha = isSelected ? 1.0 : 0.75
    ctx.beginPath()
    ctx.moveTo(x + 0.5, RULER_H)
    ctx.lineTo(x + 0.5, canvasH)
    ctx.stroke()
    ctx.setLineDash([])
    ctx.globalAlpha = 1.0

    drawMarkFlagHorizontal(ctx, x, kind)

    // Label on ruler
    const label = markLabel(mark, trace)
    const tw = ctx.measureText(label).width + 8
    const lx = Math.min(x + 3, canvasW - tw - 2)
    ctx.fillStyle = color
    ctx.globalAlpha = isSelected ? 1.0 : 0.85
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
 * Each col: { type: 'task'|'core'|'core-task'|'sti', key, label, color, x, colIdx, colWidth,
 *             isExpanded?, isExpandable? }
 *
 * STI tag-event channels are expandable; when expanded they use STI_WAVEFORM_H as column width.
 *
 * @param {object} trace
 * @param {string} viewMode      'task' or 'core'
 * @param {Set}    expanded      Set of expanded core names
 * @param {number} scrollX       Horizontal scroll offset in pixels
 * @param {boolean} showSti
 * @param {Set}    stiExpanded   Set of expanded STI channel names
 * @returns {{ cols: Array, totalWidth: number }}
 */
export function buildColumnLayout(trace, viewMode, expanded, scrollX = 0, showSti = true, stiExpanded = new Set()) {
  const cols = []
  let rawIdx = 0
  let xAcc   = 0  // accumulated pixel offset from RULER_W (before scrollX)

  if (viewMode === 'task') {
    for (const mk of trace.tasks) {
      const repr = trace.taskRepr.get(mk)
      const label = taskDisplayName(repr || mk)
      const color = taskColor(mk, repr)
      const x = RULER_W + xAcc - scrollX
      cols.push({ type: 'task', key: mk, label, color, x, colIdx: rawIdx, colWidth: COL_W })
      rawIdx++
      xAcc += COL_W
    }
  } else {
    // Core view
    for (const coreName of trace.coreNames) {
      const cc = coreColor(coreName)
      const x = RULER_W + xAcc - scrollX
      cols.push({ type: 'core', key: coreName, label: coreName, color: cc, x, colIdx: rawIdx, colWidth: COL_W })
      rawIdx++
      xAcc += COL_W
      if (expanded.has(coreName)) {
        // TICK is rendered on the ruler band – exclude it from per-task sub-columns.
        const taskOrder = (trace.coreTaskOrder.get(coreName) || [])
          .filter(t => parseTaskName(t).name !== 'TICK')
        for (const rawTask of taskOrder) {
          const lbl = taskDisplayName(rawTask)
          const mk = taskMergeKey(rawTask)
          const col = taskColor(mk, rawTask)
          const cx = RULER_W + xAcc - scrollX
          cols.push({
            type: 'core-task', key: `${coreName}__${rawTask}`,
            coreKey: coreName, taskKey: rawTask, label: lbl, color: col, x: cx, colIdx: rawIdx, colWidth: COL_W,
          })
          rawIdx++
          xAcc += COL_W
        }
      }
    }
  }

  // STI columns — tag-event channels can be expanded to show a wider waveform column
  if (showSti) {
    for (const ch of trace.stiChannels) {
      const isExpandable = isStiTagChannel(ch)
      const isExpanded   = isExpandable && stiExpanded.has(ch)
      const cw           = isExpanded ? STI_WAVEFORM_H : COL_W
      const x = RULER_W + xAcc - scrollX
      cols.push({ type: 'sti', key: ch, label: ch, color: '#888', x, colIdx: rawIdx, colWidth: cw, isExpanded, isExpandable })
      rawIdx++
      xAcc += cw
    }
  }

  return { cols, totalWidth: RULER_W + xAcc }
}

// ---- Vertical ruler (left side) -------------------------------------------

function drawVerticalRuler(ctx, trace, timeStart, timeEnd, pxPerNs, canvasH, headerH, rulerW, darkMode) {
  const timeSpan = timeEnd - timeStart
  const step = niceStep(timeSpan)
  const minorStep = step / 5
  const startSnap = Math.ceil(timeStart / step) * step

  const textColor = darkMode ? '#CCCCCC' : '#444444'
  const tickColor = darkMode ? '#555555' : '#BBBBBB'
  const minorTickColor = darkMode ? '#4A4A4A' : '#CFCFCF'

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

  // Minor ticks
  if (minorStep > 0) {
    const minorStart = Math.ceil(timeStart / minorStep) * minorStep
    ctx.strokeStyle = minorTickColor
    ctx.lineWidth = 1
    for (let t = minorStart; t <= timeEnd + minorStep; t += minorStep) {
      const k = Math.round(t / step)
      if (Math.abs(t - k * step) < minorStep * 0.08) continue
      const y = headerH + (t - timeStart) * pxPerNs
      if (y < headerH - 10 || y > canvasH + 10) continue
      ctx.beginPath()
      ctx.moveTo(rulerW - 5, Math.round(y) + 0.5)
      ctx.lineTo(rulerW,     Math.round(y) + 0.5)
      ctx.stroke()
    }
  }

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

  drawTickMarkersOnRulerVertical(ctx, trace, timeStart, timeEnd, pxPerNs, canvasH, headerH, rulerW)
}

function drawTickMarkersOnRulerVertical(ctx, trace, timeStart, timeEnd, pxPerNs, canvasH, headerH, rulerW) {
  const bandX = rulerW - 18
  const bandW = 8
  ctx.save()
  ctx.fillStyle = TICK_COLOR
  ctx.globalAlpha = 0.95

  // Task-type TICK segments
  const tickMk = taskMergeKey('TICK')
  const segs = trace.segByMergeKey?.get(tickMk) || []
  const starts = trace.segStartByMergeKey?.get(tickMk) || []
  if (segs.length > 0 && starts.length > 0) {
    const lo = Math.max(0, bisectLeft(starts, timeStart) - 1)
    const hi = Math.min(segs.length, bisectRight(starts, timeEnd) + 1)
    for (let i = lo; i < hi; i++) {
      const seg = segs[i]
      const y1 = headerH + (seg.start - timeStart) * pxPerNs
      if (y1 < headerH - 2 || y1 > canvasH + 2) continue
      ctx.fillRect(bandX, Math.round(y1) - 0.5, bandW, 2)
    }
  }

  // STI-type TICK events
  const stiTimes = trace.tickStiTimes || []
  if (stiTimes.length > 0) {
    const lo2 = Math.max(0, bisectLeft(stiTimes, timeStart) - 1)
    const hi2 = Math.min(stiTimes.length, bisectRight(stiTimes, timeEnd) + 1)
    for (let i = lo2; i < hi2; i++) {
      const y1 = headerH + (stiTimes[i] - timeStart) * pxPerNs
      if (y1 < headerH - 2 || y1 > canvasH + 2) continue
      ctx.fillRect(bandX, Math.round(y1) - 0.5, bandW, 2)
    }
  }

  ctx.restore()
}

// ---- Column header labels (rotated text) -----------------------------------

function drawColumnHeaders(ctx, cols, headerH, colW, highlightKey, darkMode) {
  for (const col of cols) {
    const cw = col.colWidth ?? colW
    const x = col.x
    const cx = x + cw / 2

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
    let rawLabel = col.label
    if (col.isExpandable) rawLabel = (col.isExpanded ? '▼ ' : '▶ ') + rawLabel
    const label = rawLabel.length > maxChars ? rawLabel.substring(0, maxChars - 1) + '…' : rawLabel
    ctx.fillText(label, 0, 0)
    ctx.restore()
  }
}

// ---- Segment drawing helpers (vertical) ------------------------------------

function paintSegmentsVertical(ctx, segs, timeStart, pxPerNs, nsPerPx, colX, colW, headerH,
                               baseColor, trace, applyCoreTint, highlightKey, colMk, darkMode, segLabel, hlSeg, canvasH) {
  const isHighlighted = (highlightKey && colMk === highlightKey) && !hlSeg
  const lod = nsPerPx > PAINT_LOD_COARSE ? 'coarse' : 'fine'
  const reduced = lod === 'coarse' ? lodReduce(segs, nsPerPx, trace.timeMin) : segs

  const segX = colX + 1
  const segW = colW - 2

  // Collect label rects for a deferred single-setup text pass.
  const labelRects = []

  for (const seg of reduced) {
    const y1 = headerH + (seg.start - timeStart) * pxPerNs
    const y2 = headerH + (seg.end   - timeStart) * pxPerNs
    const h  = Math.max(1, y2 - y1)

    if (y1 > canvasH + 2 || y1 + h < headerH - 2) continue

    const isSegLocked = hlSeg && seg.start === hlSeg.start && seg.end === hlSeg.end && seg.task === hlSeg.task
    const drawY2 = Math.round(y1)
    const drawH2 = Math.ceil(h)
    const drawX2 = segX
    const drawW2 = segW
    ctx.fillStyle = baseColor
    ctx.fillRect(drawX2, drawY2, drawW2, drawH2)

    if (applyCoreTint) {
      const tint = coreTint(seg.core)
      if (tint) {
        ctx.fillStyle = tint
        ctx.fillRect(drawX2, drawY2, drawW2, drawH2)
      }
    }

    if (isHighlighted) {
      ctx.fillStyle = 'rgba(255,255,200,0.25)'
      ctx.fillRect(drawX2, drawY2, drawW2, drawH2)
    }

    if (lod === 'fine' && h >= 3) {
      if (isSegLocked) {
        ctx.strokeStyle = complementaryColor(baseColor)
        ctx.lineWidth = 2.5
      } else {
        ctx.strokeStyle = darkMode ? 'rgba(0,0,0,0.4)' : 'rgba(0,0,0,0.3)'
        ctx.lineWidth = 0.5
      }
      ctx.strokeRect(drawX2 + 0.5, drawY2 + 0.5, drawW2 - 1, drawH2 - 1)
    }

    // Collect label info for deferred pass
    if (segLabel && h >= 40) {
      labelRects.push({ topY: drawY2 + 3 })
    }
  }

  // Deferred text-label pass: set font/color once, then translate-rotate-draw each.
  if (labelRects.length > 0) {
    const cx = segX + segW / 2
    ctx.font = '10px sans-serif'
    ctx.fillStyle = darkMode ? 'rgba(255,255,255,0.85)' : 'rgba(0,0,0,0.75)'
    ctx.textBaseline = 'middle'
    ctx.textAlign = 'left'
    for (const lb of labelRects) {
      ctx.save()
      ctx.translate(cx, lb.topY)
      ctx.rotate(Math.PI / 2)
      ctx.fillText(segLabel, 0, 0)
      ctx.restore()
    }
  }
}

// ---- Column drawing functions ----------------------------------------------

function drawTaskColumn(ctx, trace, col, timeStart, timeEnd, pxPerNs, nsPerPx, highlightKey, canvasH, darkMode, hlSeg) {
  const mk = col.key
  const ld = taskLodData(trace, mk)
  const segs = visibleSegs(ld, timeStart, timeEnd, nsPerPx, trace.lodTimescalePerPx, trace.lodUltraTimescalePerPx)

  // Column background stripe
  ctx.fillStyle = col.colIdx % 2 === 0
    ? (darkMode ? '#252526' : '#FAFAFA')
    : (darkMode ? '#2D2D2D' : '#F5F5F5')
  ctx.fillRect(col.x, HEADER_H, COL_W, canvasH)

  paintSegmentsVertical(ctx, segs, timeStart, pxPerNs, nsPerPx,
    col.x, COL_W, HEADER_H, col.color, trace, true, highlightKey, mk, darkMode, col.label, hlSeg, canvasH)
}

function drawCoreColumn(ctx, trace, col, timeStart, timeEnd, pxPerNs, nsPerPx, canvasH, darkMode) {
  const ld = coreLodData(trace, col.key)
  const segs = visibleSegs(ld, timeStart, timeEnd, nsPerPx, trace.lodTimescalePerPx, trace.lodUltraTimescalePerPx)

  ctx.fillStyle = col.colIdx % 2 === 0
    ? (darkMode ? '#252526' : '#FAFAFA')
    : (darkMode ? '#2D2D2D' : '#F5F5F5')
  ctx.fillRect(col.x, HEADER_H, COL_W, canvasH)

  const reduced = lodReduce(segs, nsPerPx, trace.timeMin)
  const segX = col.x + 1
  const segW = COL_W - 2
  const cx = segX + segW / 2

  // Cache seg.task → color to avoid repeated taskMergeKey + taskColor hash calls.
  const colorCache = new Map()
  // Collect label draws for a deferred single-setup text pass.
  const labelRects = []

  for (const seg of reduced) {
    if (isCoreName(seg.task)) continue
    // TICK is shown as ruler band marks – skip it in the core summary column.
    if (parseTaskName(seg.task).name === 'TICK') continue
    const y1 = HEADER_H + (seg.start - timeStart) * pxPerNs
    const y2 = HEADER_H + (seg.end   - timeStart) * pxPerNs
    const h  = Math.max(1, y2 - y1)
    if (y1 > canvasH + 2 || y1 + h < HEADER_H - 2) continue

    let color = colorCache.get(seg.task)
    if (color === undefined) {
      color = taskColor(taskMergeKey(seg.task), seg.task)
      colorCache.set(seg.task, color)
    }
    const drawY2 = Math.round(y1)
    const drawH2 = Math.ceil(h)
    ctx.fillStyle = color
    ctx.fillRect(segX, drawY2, segW, drawH2)

    if (h >= 40) {
      labelRects.push({ topY: drawY2 + 3, name: taskDisplayName(seg.task) })
    }
  }

  // Deferred text pass: single font/color setup for all labels.
  if (labelRects.length > 0) {
    ctx.font = '10px sans-serif'
    ctx.fillStyle = darkMode ? 'rgba(255,255,255,0.85)' : 'rgba(0,0,0,0.75)'
    ctx.textBaseline = 'middle'
    ctx.textAlign = 'left'
    for (const lb of labelRects) {
      ctx.save()
      ctx.translate(cx, lb.topY)
      ctx.rotate(Math.PI / 2)
      ctx.fillText(lb.name, 0, 0)
      ctx.restore()
    }
  }
}

function drawCoreTaskColumn(ctx, trace, col, timeStart, timeEnd, pxPerNs, nsPerPx, highlightKey, canvasH, darkMode, hlSeg) {
  const ld = coreTaskLodData(trace, col.coreKey, col.taskKey)
  const segs = visibleSegs(ld, timeStart, timeEnd, nsPerPx, trace.lodTimescalePerPx, trace.lodUltraTimescalePerPx)

  ctx.fillStyle = col.colIdx % 2 === 0
    ? (darkMode ? '#252526' : '#FAFAFA')
    : (darkMode ? '#2D2D2D' : '#F5F5F5')
  ctx.fillRect(col.x, HEADER_H, COL_W, canvasH)

  const mk = taskMergeKey(col.taskKey)
  paintSegmentsVertical(ctx, segs, timeStart, pxPerNs, nsPerPx,
    col.x, COL_W, HEADER_H, col.color, trace, false, highlightKey, mk, darkMode, col.label, hlSeg, canvasH)
}

function drawStiColumn(ctx, trace, col, timeStart, timeEnd, pxPerNs, canvasH, darkMode) {
  const cw = col.colWidth ?? COL_W
  ctx.fillStyle = darkMode ? '#1A1A2E' : '#F0F0FF'
  ctx.fillRect(col.x, HEADER_H, cw, canvasH)

  if (col.isExpanded) {
    drawStiColumnWaveform(ctx, trace, col, cw, timeStart, timeEnd, pxPerNs, canvasH, darkMode)
    return
  }

  const evs    = trace.stiEventsByTarget.get(col.key) || []
  const starts = trace.stiStartsByTarget.get(col.key) || []
  const lo = Math.max(0, bisectLeft(starts, timeStart) - 1)
  const hi = bisectRight(starts, timeEnd) + 1
  const cx = col.x + cw / 2
  const markerR = 4

  ctx.save()
  ctx.strokeStyle = darkMode ? 'rgba(255,255,255,0.5)' : 'rgba(0,0,0,0.4)'
  ctx.lineWidth = 0.8
  const stiColorCache = new Map()
  for (let i = lo; i < Math.min(hi, evs.length); i++) {
    const ev = evs[i]
    const cy = HEADER_H + (ev.time - timeStart) * pxPerNs
    if (cy < HEADER_H - 8 || cy > canvasH + 8) continue

    const noteKey = ev.note || ev.event || 'trigger'
    let color = stiColorCache.get(noteKey)
    if (color === undefined) { color = stiNoteColor(noteKey); stiColorCache.set(noteKey, color) }
    ctx.fillStyle = color
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

/**
 * Draw an expanded STI waveform inside a vertical column (time on Y, values on X).
 */
function drawStiColumnWaveform(ctx, trace, col, colW, timeStart, timeEnd, pxPerNs, canvasH, darkMode) {
  const evs    = trace.stiEventsByTarget.get(col.key) || []
  const starts = trace.stiStartsByTarget.get(col.key) || []
  if (evs.length === 0) return

  const PAD        = 4
  const chartLeft  = col.x + PAD
  const chartRight = col.x + colW - PAD
  const chartW     = chartRight - chartLeft
  if (chartW <= 0) return

  // Axis guide lines
  const axisColor = darkMode ? 'rgba(255,255,255,0.12)' : 'rgba(0,0,0,0.12)'
  ctx.save()
  ctx.strokeStyle = axisColor
  ctx.lineWidth = 0.5
  ctx.setLineDash([3, 3])
  ctx.beginPath()
  ctx.moveTo(chartLeft + 0.5, HEADER_H)
  ctx.lineTo(chartLeft + 0.5, canvasH)
  ctx.stroke()
  ctx.beginPath()
  ctx.moveTo(chartRight + 0.5, HEADER_H)
  ctx.lineTo(chartRight + 0.5, canvasH)
  ctx.stroke()
  ctx.setLineDash([])
  ctx.restore()

  function evVal(ev) { return parseFloat(ev.note !== '' ? ev.note : ev.event) }

  const preRange = trace.stiValRange?.get(col.key)
  let valMin, valMax
  if (preRange) {
    valMin = preRange.min
    valMax = preRange.max
  } else {
    valMin = Infinity; valMax = -Infinity
    for (const ev of evs) {
      const v = evVal(ev)
      if (isNaN(v)) continue
      if (v < valMin) valMin = v
      if (v > valMax) valMax = v
    }
  }
  if (!isFinite(valMin)) return
  if (valMin === valMax) { valMin -= 1; valMax += 1 }
  const valRange = valMax - valMin
  function valToX(v) { return chartLeft + ((v - valMin) / valRange) * chartW }

  const lo = Math.max(0, bisectLeft(starts, timeStart) - 1)
  const hi = Math.min(evs.length, bisectRight(starts, timeEnd) + 1)
  const slice = evs.slice(lo, hi)
  if (slice.length === 0) return

  // Scale labels at top of chart area
  function fmtVal(v) {
    if (Math.abs(v) >= 1e6) return (v / 1e6).toFixed(2) + 'M'
    if (Math.abs(v) >= 1e3) return (v / 1e3).toFixed(1) + 'k'
    return String(Math.round(v))
  }
  ctx.save()
  ctx.font = '9px monospace'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'top'
  ctx.fillStyle = darkMode ? 'rgba(255,255,255,0.3)' : 'rgba(0,0,0,0.3)'
  ctx.fillText(fmtVal(valMin), chartLeft + 2, HEADER_H + 2)
  ctx.fillText(fmtVal(valMax), chartRight - 2, HEADER_H + 2)
  ctx.restore()

  // Clip drawing to the timeline area so lines don't bleed into the header
  ctx.save()
  ctx.beginPath()
  ctx.rect(col.x, HEADER_H, colW, canvasH - HEADER_H)
  ctx.clip()

  ctx.strokeStyle = darkMode ? '#5BC8FF' : '#0070CC'
  ctx.lineWidth = 1.5
  ctx.lineJoin = 'round'

  // Build polyline connecting events with straight lines.
  // When the first event in 'slice' has a predecessor above the viewport,
  // interpolate the line back to y=HEADER_H so there is no gap at the top.
  ctx.beginPath()
  let firstPoint = true
  for (let i = 0; i < slice.length; i++) {
    const ev  = slice[i]
    const val = evVal(ev)
    if (isNaN(val)) continue

    const cy = HEADER_H + (ev.time - timeStart) * pxPerNs
    const cx = valToX(val)

    if (firstPoint) {
      if (lo > 0) {
        // There is an off-screen event above the viewport — interpolate to y=HEADER_H
        const prevEv  = evs[lo - 1]
        const prevVal = evVal(prevEv)
        if (!isNaN(prevVal)) {
          const prevCy = HEADER_H + (prevEv.time - timeStart) * pxPerNs
          const prevCx = valToX(prevVal)
          const t       = prevCy === cy ? 0 : (HEADER_H - prevCy) / (cy - prevCy)
          const startCx = prevCx + t * (cx - prevCx)
          ctx.moveTo(startCx, HEADER_H)
          ctx.lineTo(cx, cy)
          firstPoint = false
          continue
        }
      }
      ctx.moveTo(cx, cy)
      firstPoint = false
    } else {
      ctx.lineTo(cx, cy)
    }
  }
  // Hold last value to canvas bottom
  if (!firstPoint) {
    const lastSliceEv = slice[slice.length - 1]
    const lastVal = evVal(lastSliceEv)
    if (!isNaN(lastVal)) ctx.lineTo(valToX(lastVal), canvasH)
  }
  ctx.stroke()

  // Dots at each event
  ctx.fillStyle = darkMode ? '#80DFFF' : '#0050AA'
  for (let i = 0; i < slice.length; i++) {
    const ev  = slice[i]
    const val = evVal(ev)
    if (isNaN(val)) continue
    const cx = valToX(val)
    const cy = HEADER_H + (ev.time - timeStart) * pxPerNs
    if (cy < HEADER_H - 4 || cy > canvasH + 4) continue
    ctx.beginPath()
    ctx.arc(cx, cy, 2.5, 0, Math.PI * 2)
    ctx.fill()
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

export function drawMarksVertical(ctx, marks, trace, timeStart, pxPerNs, canvasW, canvasH, headerH, _darkMode, selectedId = null) {
  if (!marks || marks.length === 0) return
  ctx.save()
  ctx.font = '10px monospace'
  ctx.textAlign = 'right'
  ctx.textBaseline = 'middle'

  for (const mark of marks) {
    const y = Math.round(headerH + (mark.ns - timeStart) * pxPerNs)
    if (y < headerH - 2 || y > canvasH + 2) continue
    const kind = markKind(mark)
    const color = markColor(mark)
    const isSelected = selectedId !== null && mark.id === selectedId

    if (isSelected) {
      ctx.strokeStyle = 'rgba(255,255,255,0.35)'
      ctx.lineWidth = 5
      ctx.setLineDash([])
      ctx.beginPath()
      ctx.moveTo(RULER_W, y + 0.5)
      ctx.lineTo(canvasW, y + 0.5)
      ctx.stroke()
    }
    ctx.strokeStyle = color
    ctx.lineWidth = isSelected ? 2.5 : (kind === 'annotation' ? 1.0 : 1.2)
    ctx.setLineDash(isSelected ? [] : (kind === 'annotation' ? [6, 3] : []))
    ctx.globalAlpha = isSelected ? 1.0 : 0.75
    ctx.beginPath()
    ctx.moveTo(RULER_W, y + 0.5)
    ctx.lineTo(canvasW, y + 0.5)
    ctx.stroke()
    ctx.setLineDash([])
    ctx.globalAlpha = 1.0

    drawMarkFlagVertical(ctx, y, kind)

    // Label on ruler
    const label = markLabel(mark, trace)
    const tw = ctx.measureText(label).width + 8
    const ly = Math.max(headerH + 3, Math.min(y - 7, canvasH - 17))
    ctx.fillStyle = color
    ctx.globalAlpha = isSelected ? 1.0 : 0.85
    ctx.fillRect(RULER_W - 2 - tw, ly, tw, 13)
    ctx.globalAlpha = 1.0
    ctx.fillStyle = '#000'
    ctx.fillText(label, RULER_W - 4, ly + 6)
  }
  ctx.restore()
}

// ---- Hit-test helpers for draggable overlays ------------------------------

export function findNearestCursorIndex(cursors, t, snapNs) {
  if (!cursors || cursors.length === 0) return -1
  let bestIdx = -1
  let bestDist = Infinity
  for (let i = 0; i < cursors.length; i++) {
    const c = cursors[i]
    if (c == null) continue
    const d = Math.abs(c - t)
    if (d <= snapNs && d < bestDist) {
      bestDist = d
      bestIdx = i
    }
  }
  return bestIdx
}

export function findNearestMark(marks, t, snapNs) {
  if (!marks || marks.length === 0) return null
  let best = null
  let bestDist = Infinity
  for (const mark of marks) {
    const d = Math.abs(mark.ns - t)
    if (d <= snapNs && d < bestDist) {
      bestDist = d
      best = mark
    }
  }
  return best
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
    showSti      = true,
    stiExpanded  = new Set(),
  } = options
  const highlightSegment = options.highlightSegment ?? null

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
  const { cols } = buildColumnLayout(trace, viewMode, expanded, scrollX, showSti, stiExpanded)

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
      drawTaskColumn(ctx, trace, col, timeStart, timeEnd, pxPerNs, nsPerPx, highlightKey, canvasH, darkMode, highlightSegment)
    } else if (col.type === 'core') {
      drawCoreColumn(ctx, trace, col, timeStart, timeEnd, pxPerNs, nsPerPx, canvasH, darkMode)
    } else if (col.type === 'core-task') {
      drawCoreTaskColumn(ctx, trace, col, timeStart, timeEnd, pxPerNs, nsPerPx, highlightKey, canvasH, darkMode, highlightSegment)
    } else if (col.type === 'sti') {
      drawStiColumn(ctx, trace, col, timeStart, timeEnd, pxPerNs, canvasH, darkMode)
    }
  }
  ctx.restore()

  // ---- Locked segment enlarged pass (unclipped, draws over column gap) ----
  drawLockedSegmentVert(ctx, trace, cols, highlightSegment, timeStart, timeEnd, pxPerNs, nsPerPx, HEADER_H, canvasH, darkMode)

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
  const { viewMode = 'task', expanded = new Set(), showSti = true, stiExpanded = new Set() } = options
  if (!showSti) return null
  if (cy < HEADER_H) return null
  const pxPerNs = (canvasH - HEADER_H) / (timeEnd - timeStart)
  const tAtCy = timeStart + (cy - HEADER_H) / pxPerNs

  const { cols } = buildColumnLayout(trace, viewMode, expanded, scrollX, showSti, stiExpanded)
  for (const col of cols) {
    if (col.type !== 'sti') continue
    const cw = col.colWidth ?? COL_W
    if (Math.abs(cx - (col.x + cw / 2)) > cw) continue

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
  const { viewMode = 'task', expanded = new Set(), showSti = true, stiExpanded = new Set() } = options
  if (cx < RULER_W) return null
  const { cols } = buildColumnLayout(trace, viewMode, expanded, scrollX, showSti, stiExpanded)
  for (const col of cols) {
    if (cx >= col.x && cx < col.x + (col.colWidth ?? COL_W)) return col
  }
  return null
}

