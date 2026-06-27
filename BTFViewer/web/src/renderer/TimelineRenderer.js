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
import {
  accelVisibleRowRange,
  accelVisibleSegIndices,
  accelLodReduceIndices,
  getWasmHandles,
} from './wasmAccel.js'
import { formatTime, formatMigrationGapTime } from '../utils/timeFormat.js'
import { cursorSortedPlaced } from '../utils/cursorAnalysis.js'
import { getTimelineLayout } from '../utils/timelineLayout.js'
import { CURSOR_COLORS } from '../utils/cursorColors.js'
import {
  intervalColor,
  isIntervalMarkerChannel,
  intervalInstancesForDraw,
  visibleIntervalInstances,
  visibleIntervalMarkerEvents,
  intervalStripeColors,
} from '../utils/intervalAnalysis.js'
import {
  taskPriorityLabelSuffix,
  visiblePriorityEpisodes,
  BOOST_BAND_COLOR,
  INVERSION_BAND_COLOR,
} from '../utils/priorityAnalysis.js'
import {
  taskPassesRowFilter,
  coreViewTaskFilterActive,
  filteredCoreViewTasks,
  stiChannelMatchesTextFilter,
  normalizeTaskFilterText,
} from '../utils/taskFilter.js'

export {
  taskPassesRowFilter,
  coreViewTaskFilterActive,
  filteredCoreViewTasks,
  filteredTaskViewTasks,
  stiChannelMatchesTextFilter,
  normalizeTaskFilterText,
} from '../utils/taskFilter.js'

export { formatTime, formatMigrationGapTime }
export { getTimelineLayout } from '../utils/timelineLayout.js'

// ---- Layout (defaults; live values from Settings via getTimelineLayout()) --
export const RULER_H        =  40  // height of ruler row (px)
export const RULER_W        = 120  // left ruler column width (px) – vertical mode
export const HEADER_H       = 160  // top label row height (px) – vertical mode
export const COL_W          =  26  // column width per task/core – vertical mode
export const MIN_SEG_W      =   1  // minimum segment paint width (px)

/** Runtime vertical header band inside canvas (0 when DOM ColumnHeaderRow is used). */
let _vertHeaderBand = HEADER_H

export function setVertHeaderBand(h) {
  _vertHeaderBand = h
}

export function vertHeaderBand() {
  return _vertHeaderBand
}

function L() {
  return getTimelineLayout()
}

// ---- Helpers ---------------------------------------------------------------
function isCoreName(name) {
  return typeof name === 'string' && name.startsWith('Core_')
}

/**
 * Returns true if the STI channel name is a tag-event waveform channel.
 * Matches: tag_event, tag0_event … tag7_event
 */
export function isStiTagChannel(name) {
  return /^tag[0-7]?_event$/.test(name)
}

// ---- Vertical mode layout constants ----------------------------------------
// (RULER_W, HEADER_H, COL_W exported above)

// LOD thresholds (ns/px). Above PAINT_LOD_COARSE, nearby sub-pixel segments are
// merged via lodReduce; below it, individual segments are drawn with outlines.
// visibleSegs() already selects the right LOD bin tier automatically.
const PAINT_LOD_COARSE = 200    // ns/px: use coarse (merged) paint above this zoom level
/** Max segment rectangles drawn per row/column per frame. */
const PAINT_SEG_BUDGET   = 5000
/** Reduced cap while panning/zooming at overview zoom (fit-to-window). */
const PAINT_SEG_BUDGET_FAST = 1800
/** WebGL (PixiJS) segment budget — GPU batching supports much larger traces. */
const GPU_PAINT_SEG_BUDGET = 120_000
const GPU_PAINT_SEG_BUDGET_FAST = 35_000
/** Minimum segment budget guaranteed per visible row/column. */
const PAINT_SEG_MIN_SLOT = 48
/** Minimum per slot during overview-zoom interaction. */
const PAINT_SEG_MIN_SLOT_FAST = 24
/** Max rows/columns that share the paint budget (avoids tiny per-slot caps). */
const PAINT_BUDGET_MAX_SLOTS = 48
const PAINT_BUDGET_MAX_SLOTS_FAST = 36
/** Fraction of budget at which outlines, labels, and core tint are skipped. */
const PAINT_BUDGET_LITE  = 0.40
/** Task rows above this count use micro bars in the navigator thumbnail. */
export const OVERVIEW_MICRO_ROWS = 128

const ORTH_BUF_HUGE_TASKS = 768
const ORTH_BUF_LARGE_TASKS = 256

/** Extra rows above/below the viewport when culling (larger on big traces). */
export function orthRowBuffer(nTasks = 0, fastPaint = false) {
  if (fastPaint) return 2
  if (nTasks > ORTH_BUF_HUGE_TASKS) return 5
  if (nTasks > ORTH_BUF_LARGE_TASKS) return 4
  return 2
}

function createPaintBudget(visibleSlots = 1, fastPaint = false, gpu = false) {
  const cap = fastPaint ? PAINT_BUDGET_MAX_SLOTS_FAST : PAINT_BUDGET_MAX_SLOTS
  const slots = Math.min(Math.max(1, visibleSlots), cap)
  const total = gpu
    ? (fastPaint ? GPU_PAINT_SEG_BUDGET_FAST : GPU_PAINT_SEG_BUDGET)
    : (fastPaint ? PAINT_SEG_BUDGET_FAST : PAINT_SEG_BUDGET)
  const minSlot = fastPaint ? PAINT_SEG_MIN_SLOT_FAST : PAINT_SEG_MIN_SLOT
  return { n: 0, max: Math.max(minSlot, Math.floor(total / slots)), fast: fastPaint }
}

/** Solid segment fill — Canvas 2D or batched WebGL rects. */
function gpuFillRect(gpuBatch, ctx, x, y, w, h, color, alpha = 1) {
  if (gpuBatch) {
    gpuBatch.addRect(x, y, w, h, color, alpha)
    return
  }
  ctx.fillStyle = color
  if (alpha < 1) {
    ctx.save()
    ctx.globalAlpha = alpha
    ctx.fillRect(x, y, w, h)
    ctx.restore()
  } else {
    ctx.fillRect(x, y, w, h)
  }
}

function budgetLite(b) {
  return b.n >= b.max * PAINT_BUDGET_LITE
}

function budgetFull(b) {
  return b.n >= b.max
}

/**
 * Merge segments that share a pixel column into one span (min start → max end).
 * Prevents gaps when lod-reduce keeps a later segment in the same column.
 * @param {Function|null} bucketKey  Optional — merge only within same key (e.g. task name on core rows).
 */
function mergeColumnSpans(segs, timeStart, nsPerPx, indices = null, bucketKey = null) {
  const result = []
  let prevKey = null
  let cur = null
  const visit = (s) => {
    if (!s) return
    const effStart = s.start < timeStart ? timeStart : s.start
    const px = s.start < timeStart ? 0 : Math.floor((s.start - timeStart) / nsPerPx)
    const colKey = bucketKey ? `${px}\0${bucketKey(s)}` : String(px)
    if (colKey !== prevKey) {
      if (cur) result.push(cur)
      cur = { ...s, start: effStart, end: s.end }
      prevKey = colKey
    } else {
      cur.start = Math.min(cur.start, effStart)
      cur.end = Math.max(cur.end, s.end)
    }
  }
  if (indices) {
    for (let k = 0; k < indices.length; k++) visit(segs[indices[k]])
  } else {
    for (const s of segs) visit(s)
  }
  if (cur) result.push(cur)
  return result
}

/** Viewport-aware lodReduce: merge to one span per pixel column. */
function lodReduceViewport(segs, nsPerPx, timeStart) {
  return mergeColumnSpans(segs, timeStart, nsPerPx)
}

/** Merge segments further when a row has more than its per-frame paint allowance. */
function segmentsForBudget(segs, nsPerPx, timeStart, timeEnd, budgetMax, forceCoarse) {
  let reduced = forceCoarse ? lodReduceViewport(segs, nsPerPx, timeStart) : segs
  if (reduced.length > budgetMax) {
    const span = Math.max(timeEnd - timeStart, 1)
    const coarseTpp = Math.max(nsPerPx, span / budgetMax)
    reduced = lodReduceViewport(reduced, coarseTpp, timeStart)
  }
  return reduced
}

/** Pick segment LOD tier for paint; use ultra when zoomed out past coarse threshold. */
function segsForPaint(lodData, timeStart, timeEnd, nsPerPx, lodTpp, ultraTpp) {
  let tpp = nsPerPx
  if (nsPerPx > PAINT_LOD_COARSE && nsPerPx < lodTpp) {
    tpp = lodTpp
  } else if (nsPerPx >= lodTpp) {
    tpp = ultraTpp
  }
  return visibleSegs(lodData, timeStart, timeEnd, tpp, lodTpp, ultraTpp)
}

const TICK_COLOR = '#E8C84A'

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
export function buildRowLayout(trace, viewMode, expanded, yStart, showSti = true, stiExpanded = new Set(), migratedOnlyFilter = false, taskFilterKeys = null, taskFilterText = '') {
  const rows = []
  let y = yStart
  const stiFilterQ = normalizeTaskFilterText(taskFilterText)

  if (viewMode === 'task') {
    for (const mk of trace.tasks) {
      if (!taskPassesRowFilter(trace, mk, migratedOnlyFilter, taskFilterKeys, taskFilterText)) continue
      const repr = trace.taskRepr.get(mk)
      const label = taskDisplayName(repr || mk) + taskPriorityLabelSuffix(trace, mk)
      const color = taskColor(mk, repr)
      rows.push({ type: 'task', key: mk, label, color, y })
      y += L().rowH + L().rowGap
    }
  } else {
    // Core view
    const cores = filteredCoreViewTasks(trace, migratedOnlyFilter, taskFilterKeys, taskFilterText)
    for (const { coreName, tasks } of cores) {
      const cc = coreColor(coreName)
      rows.push({ type: 'core', key: coreName, label: coreName, color: cc, y })
      y += L().rowH + L().rowGap
      if (expanded.has(coreName)) {
        for (const rawTask of tasks) {
          const mk = taskMergeKey(rawTask)
          const label = taskDisplayName(rawTask) + taskPriorityLabelSuffix(trace, mk)
          const color = taskColor(mk, rawTask)
          rows.push({ type: 'core-task', key: `${coreName}__${rawTask}`, coreKey: coreName, taskKey: rawTask, label, color, y })
          y += L().rowH + L().rowGap
        }
      }
    }
  }

  // STI rows (raw marker channels; interval start/stop are paired into interval rows)
  if (showSti) {
    for (const ch of trace.stiChannels) {
      if (isIntervalMarkerChannel(ch)) continue
      if (stiFilterQ && !stiChannelMatchesTextFilter(trace, ch, stiFilterQ)) continue
      const isTag = isStiTagChannel(ch)
      const isExpanded = isTag && stiExpanded.has(ch)
      const rowH = isExpanded ? L().stiWaveformH : L().stiRowH
      rows.push({ type: 'sti', key: ch, label: ch, color: '#888', y, isTag, isExpanded })
      y += rowH + L().rowGap
    }
    for (const id of (trace.intervalIds || [])) {
      rows.push({
        type: 'interval',
        key: id,
        label: `Interval ${id}`,
        color: intervalColor(id),
        y,
      })
      y += L().rowH + L().rowGap
    }
  }

  return { rows, totalHeight: y - yStart }
}

function paintPriorityBoostBands(ctx, trace, mk, rowY, rowH, timeStart, timeEnd, pxPerNs, canvasW, darkMode) {
  const episodes = trace.priorityEpisodesByMk?.get(mk)
  if (!episodes?.length) return
  const visible = visiblePriorityEpisodes(episodes, timeStart, timeEnd)
  if (!visible.length) return

  const bandH = Math.max(3, Math.floor(rowH * 0.3))
  const bandY = rowY + rowH - bandH

  ctx.save()
  for (const ep of visible) {
    const x1 = (ep.startNs - timeStart) * pxPerNs
    const x2 = (ep.stopNs - timeStart) * pxPerNs
    if (x2 < -2 || x1 > canvasW + 2) continue
    const cx = Math.max(0, Math.floor(x1))
    const cx2 = Math.min(Math.ceil(x2), canvasW)
    const drawW = cx2 - cx
    if (drawW < 0.5) continue
    const color = ep.inversionSuspect ? INVERSION_BAND_COLOR : BOOST_BAND_COLOR
    ctx.fillStyle = ep.inversionSuspect
      ? (darkMode ? 'rgba(231,76,60,0.72)' : 'rgba(231,76,60,0.52)')
      : (darkMode ? 'rgba(243,156,18,0.72)' : 'rgba(243,156,18,0.52)')
    ctx.fillRect(cx, bandY, drawW, bandH)
    if (drawW >= 4) {
      ctx.strokeStyle = color
      ctx.lineWidth = 1
      ctx.strokeRect(cx + 0.5, bandY + 0.5, drawW - 1, bandH - 1)
    }
  }
  ctx.restore()
}

/** Right-edge boost stripes for vertical task/core-task columns. */
function paintPriorityBoostBandsVertical(ctx, trace, mk, colX, colW, headerH, canvasH,
  timeStart, timeEnd, pxPerNs, darkMode) {
  const episodes = trace.priorityEpisodesByMk?.get(mk)
  if (!episodes?.length) return
  const visible = visiblePriorityEpisodes(episodes, timeStart, timeEnd)
  if (!visible.length) return

  const bodyH = canvasH - headerH
  const bandW = Math.max(3, Math.floor(colW * 0.3))
  const bandX = colX + colW - bandW

  ctx.save()
  for (const ep of visible) {
    const y1 = (ep.startNs - timeStart) * pxPerNs
    const y2 = (ep.stopNs - timeStart) * pxPerNs
    if (y2 < -2 || y1 > bodyH + 2) continue
    const cy = Math.max(0, Math.floor(y1))
    const cy2 = Math.min(Math.ceil(y2), bodyH)
    const drawH = cy2 - cy
    if (drawH < 0.5) continue
    const color = ep.inversionSuspect ? INVERSION_BAND_COLOR : BOOST_BAND_COLOR
    ctx.fillStyle = ep.inversionSuspect
      ? (darkMode ? 'rgba(231,76,60,0.72)' : 'rgba(231,76,60,0.52)')
      : (darkMode ? 'rgba(243,156,18,0.72)' : 'rgba(243,156,18,0.52)')
    ctx.fillRect(bandX, headerH + cy, bandW, drawH)
    if (drawH >= 4) {
      ctx.strokeStyle = color
      ctx.lineWidth = 1
      ctx.strokeRect(bandX + 0.5, headerH + cy + 0.5, bandW - 1, drawH - 1)
    }
  }
  ctx.restore()
}

/** Row band height in px (excludes inter-row gap — gap is encoded in row.y spacing). */
export function rowBandHeight(row) {
  if (row.type === 'sti') return row.isExpanded ? L().stiWaveformH : L().stiRowH
  return L().rowH
}

/**
 * Index range [i0, i1) of rows that intersect the vertical viewport.
 * Rows use scroll-independent y (yStart=0 layout).
 */
export function visibleRowIndexRange(rows, scrollY, bodyH, buffer = 2, packedRows = null) {
  if (!rows || rows.length === 0) return { i0: 0, i1: 0 }
  return accelVisibleRowRange(rows, scrollY, bodyH, buffer, rowBandHeight, packedRows)
}

/** Column band width in px (vertical mode). */
export function colBandWidth(col) {
  return col.colWidth ?? COL_W
}

/**
 * Index range [i0, i1) of columns that intersect the horizontal viewport.
 * Columns use scroll-independent x (scrollX=0 layout).
 */
export function visibleColumnIndexRange(cols, scrollX, canvasW, buffer = 2, rulerW = RULER_W) {
  if (!cols?.length) return { i0: 0, i1: 0 }
  const sx = scrollX || 0
  const viewLo = sx + rulerW
  const viewHi = sx + canvasW
  let i0 = 0
  let i1 = cols.length
  for (let i = 0; i < cols.length; i++) {
    const cw = colBandWidth(cols[i])
    if (cols[i].x + cw > viewLo) {
      i0 = Math.max(0, i - buffer)
      break
    }
  }
  for (let i = cols.length - 1; i >= 0; i--) {
    if (cols[i].x < viewHi) {
      i1 = Math.min(cols.length, i + 1 + buffer)
      break
    }
  }
  return { i0, i1 }
}

/** Apply scroll offset to a layout built with yStart=0. Prefer inline yOff in hot paths. */
export function offsetRowLayout(layout, yStart) {
  if (!layout || !yStart) return layout
  return {
    rows: layout.rows.map(r => ({ ...r, y: r.y + yStart })),
    totalHeight: layout.totalHeight,
  }
}

/** Cached scroll-independent row list from options, or build on demand. */
function resolveRows(trace, options, viewMode, expanded, showSti, stiExpanded, migratedOnlyFilter) {
  const taskFilterKeys = options.taskFilterKeys || null
  const taskFilterText = options.taskFilterText || ''
  if (options.rowLayout?.rows) return options.rowLayout.rows
  return buildRowLayout(trace, viewMode, expanded, 0, showSti, stiExpanded, migratedOnlyFilter, taskFilterKeys, taskFilterText).rows
}

/** Cached scroll-independent column list from options, or build on demand. */
function resolveCols(trace, options, viewMode, expanded, showSti, stiExpanded, migratedOnlyFilter) {
  const taskFilterKeys = options.taskFilterKeys || null
  const taskFilterText = options.taskFilterText || ''
  if (options.columnLayout?.cols) return options.columnLayout.cols
  return buildColumnLayout(trace, viewMode, expanded, 0, showSti, stiExpanded, migratedOnlyFilter, taskFilterKeys, taskFilterText).cols
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
    showGrid    = true,
    darkMode    = true,
    hoverTime   = null,
    marks       = [],
    showSti     = true,
    stiExpanded = new Set(),
    stiLogScale = false,
    migratedOnlyFilter = false,
    lockedTaskKey = null,
    fastPaint   = false,
    showHoverHighlight = false,
  } = options
  const highlightSegment = options.highlightSegment ?? null
  const taskFilterText = options.taskFilterText || ''
  const skipCoreSummarySegs = coreViewTaskFilterActive(migratedOnlyFilter, options.taskFilterKeys, taskFilterText)
  const gpuBatch = options.gpuBatch ?? null
  const useGpu = !!gpuBatch

  const timeSpan = timeEnd - timeStart
  if (timeSpan <= 0 || canvasW <= 0) return

  const pxPerNs      = canvasW / timeSpan
  const nsPerPx      = timeSpan / canvasW   // timescale per pixel
  const bodyH        = canvasH - RULER_H
  const paintFast    = !!fastPaint

  // DPR-aware clear — body background is on the WebGL layer when gpuBatch is set.
  ctx.clearRect(0, 0, canvasW, canvasH)

  if (!useGpu) {
    ctx.fillStyle = darkMode ? '#1E1E1E' : '#FFFFFF'
    ctx.fillRect(0, 0, canvasW, canvasH)
  }

  // Ruler background
  ctx.fillStyle = darkMode ? '#2D2D2D' : '#F0F0F0'
  ctx.fillRect(0, 0, canvasW, RULER_H)

  // ---- Row layout (scroll offset applied inline — no per-frame row copy) ----
  const rowLayoutBase = options.rowLayout
  const rows = rowLayoutBase?.rows
    ?? buildRowLayout(trace, viewMode, expanded, 0, showSti, stiExpanded, migratedOnlyFilter, options.taskFilterKeys || null, taskFilterText).rows
  const yOff = RULER_H - scrollY
  const nTasks = trace.tasks?.length ?? rows.length
  const rowBuffer = orthRowBuffer(nTasks, paintFast)
  const { i0, i1 } = visibleRowIndexRange(rows, scrollY, bodyH, rowBuffer, options.packedRows)
  const visibleRowCount = Math.max(1, i1 - i0)

  // ---- Grid lines (optional) ----
  if (showGrid && !paintFast) {
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
  drawRuler(ctx, trace, timeStart, timeEnd, pxPerNs, canvasW, darkMode, paintFast)

  // ---- Clip to body area ----
  ctx.save()
  ctx.beginPath()
  ctx.rect(0, RULER_H, canvasW, bodyH)
  ctx.clip()

  // ---- Task / Core rows (visible range only) ----
  const budgetSpec = createPaintBudget(visibleRowCount, paintFast, useGpu)
  for (let ri = i0; ri < i1; ri++) {
    const row = rows[ri]
    const rowY = row.y + yOff
    const rowH = rowBandHeight(row)
    const rowBudget = { n: 0, max: budgetSpec.max, fast: budgetSpec.fast }

    if (row.type === 'task') {
      drawTaskRow(ctx, trace, row, rowY, timeStart, timeEnd, pxPerNs, nsPerPx, highlightKey, canvasW, darkMode, highlightSegment, rowBudget, showHoverHighlight, gpuBatch)
    } else if (row.type === 'core') {
      drawCoreRow(ctx, trace, row, rowY, timeStart, timeEnd, pxPerNs, nsPerPx, canvasW, darkMode, rowBudget, skipCoreSummarySegs, gpuBatch)
    } else if (row.type === 'core-task') {
      drawCoreTaskRow(ctx, trace, row, rowY, timeStart, timeEnd, pxPerNs, nsPerPx, highlightKey, canvasW, darkMode, highlightSegment, lockedTaskKey, rowBudget, showHoverHighlight, gpuBatch)
    } else if (row.type === 'sti') {
      drawStiRow(ctx, trace, row, rowY, timeStart, timeEnd, pxPerNs, canvasW, darkMode, stiLogScale)
    } else if (row.type === 'interval') {
      drawIntervalRow(ctx, trace, row, rowY, timeStart, timeEnd, pxPerNs, canvasW, darkMode, options.highlightInterval ?? null)
    }
  }

  ctx.restore()

  // ---- Locked segment enlarged pass (unclipped, draws over row gap) ----
  if (!paintFast) {
    drawLockedSegmentHoriz(ctx, trace, rows, yOff, highlightSegment, timeStart, timeEnd, pxPerNs, nsPerPx, darkMode)
  }
  // Marks, cursors, and hover line are drawn on the overlay canvas (TimelinePanel).
}

// ---- Ruler drawing ---------------------------------------------------------

function drawRuler(ctx, trace, timeStart, timeEnd, pxPerNs, canvasW, darkMode, fastPaint = false) {
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

  // Minor ticks (skip while interacting — expensive at wide zoom)
  if (!fastPaint && minorStep > 0) {
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

  drawTickMarkersOnRulerHorizontal(ctx, trace, timeStart, timeEnd, pxPerNs, canvasW, fastPaint)
}

function drawTickMarkersOnRulerHorizontal(ctx, trace, timeStart, timeEnd, pxPerNs, canvasW, fastPaint = false) {
  if (fastPaint) return

  const bandTop = RULER_H - 10
  const bandH = 8
  ctx.save()
  ctx.fillStyle = TICK_COLOR
  ctx.globalAlpha = 0.95

  let prevPx = -2

  // Task-type TICK segments
  const tickMk = taskMergeKey('TICK')
  const segs = trace.segByMergeKey?.get(tickMk) || []
  const starts = trace.segStartByMergeKey?.get(tickMk) || []
  if (segs.length > 0 && starts.length > 0) {
    const lo = Math.max(0, bisectLeft(starts, timeStart) - 1)
    const hi = Math.min(segs.length, bisectRight(starts, timeEnd) + 1)
    for (let i = lo; i < hi; i++) {
      const seg = segs[i]
      const px = Math.round((seg.start - timeStart) * pxPerNs)
      if (px < -2 || px > canvasW + 2 || px === prevPx) continue
      prevPx = px
      ctx.fillRect(px - 0.5, bandTop, 2, bandH)
    }
  }

  // STI-type TICK events — at most one marker per pixel column
  const stiTimes = trace.tickStiTimes || []
  if (stiTimes.length > 0) {
    const lo2 = Math.max(0, bisectLeft(stiTimes, timeStart) - 1)
    const hi2 = Math.min(stiTimes.length, bisectRight(stiTimes, timeEnd) + 1)
    for (let i = lo2; i < hi2; i++) {
      const px = Math.round((stiTimes[i] - timeStart) * pxPerNs)
      if (px < -2 || px > canvasW + 2 || px === prevPx) continue
      prevPx = px
      ctx.fillRect(px - 0.5, bandTop, 2, bandH)
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

function queryPaintIndices(trace, wasmKind, wasmKey, ld, timeStart, timeEnd, nsPerPx, lodTpp, ultraTpp, budgetMax, forceCoarse, fastPaint = false) {
  const effectiveForce = forceCoarse || fastPaint
  const tierNsPerPx = (fastPaint || (effectiveForce && nsPerPx >= lodTpp))
    ? Math.max(nsPerPx, ultraTpp)
    : nsPerPx
  const handles = wasmKind ? getWasmHandles(trace, wasmKind, wasmKey) : null
  const q = accelVisibleSegIndices(handles, ld, timeStart, timeEnd, tierNsPerPx, lodTpp, ultraTpp)
  if (!q.segs?.length || q.from > q.to) return { segs: q.segs || [], indices: null }
  const visibleCount = q.to - q.from + 1
  if (!effectiveForce && visibleCount <= budgetMax) {
    const indices = new Array(visibleCount)
    for (let i = q.from, j = 0; i <= q.to; i++, j++) indices[j] = i
    return { segs: q.segs, indices }
  }
  return { segs: q.segs, indices: accelLodReduceIndices(q, timeStart, timeEnd, nsPerPx, budgetMax, true) }
}

/**
 * Paint segments for a row.
 * Handles LOD selection, sub-pixel merging, segment fill + optional core tint.
 * Each row/column gets a fair share of the per-frame paint budget.
 */
function paintSegments(ctx, segs, timeStart, timeEnd, pxPerNs, nsPerPx, rowY, rowH,
                       baseColor, trace, applyCoreTint, highlightKey, rowMk, darkMode, segLabel, hlSeg, budget,
                       segIndices = null, gpuBatch = null, fillAlpha = 1) {
  const isHighlighted = (highlightKey && rowMk === highlightKey) && !hlSeg
  const fast = budget.fast
  const forceCoarse = fast || budgetLite(budget) || nsPerPx > PAINT_LOD_COARSE
  const drawOutlines = !fast && !forceCoarse
  const drawLabels   = drawOutlines && !budgetLite(budget)
  const drawTint     = !fast && !forceCoarse && !budgetLite(budget)

  const reduced = segIndices ? null : segmentsForBudget(segs, nsPerPx, timeStart, timeEnd, budget.max, forceCoarse)
  const viewW = (timeEnd - timeStart) * pxPerNs

  const drawList = segIndices
    ? mergeColumnSpans(segs, timeStart, nsPerPx, segIndices)
    : reduced

  const labelRects = []

  // Fast path: batch same-color fills (Canvas Path2D or WebGL rects).
  if (!drawTint && !drawOutlines && !isHighlighted && !hlSeg) {
    let count = 0
    const addSeg = (seg) => {
      if (count >= budget.max) return false
      const x1raw = (seg.start - timeStart) * pxPerNs
      const x2raw = (seg.end   - timeStart) * pxPerNs
      if (x2raw < -2 || x1raw > viewW + 2) return true
      const x1 = Math.max(0, x1raw)
      const x2 = Math.min(viewW, x2raw)
      const rw = Math.ceil(Math.max(MIN_SEG_W, x2 - x1))
      const rx = Math.round(x1)
      if (gpuBatch) gpuBatch.addRect(rx, rowY, rw, rowH, baseColor, fillAlpha)
      else path.rect(rx, rowY, rw, rowH)
      count++
      return true
    }
    if (gpuBatch) {
      for (const seg of drawList) {
        if (!addSeg(seg)) break
      }
    } else {
      const path = new Path2D()
      for (const seg of drawList) {
        if (!addSeg(seg)) break
      }
      if (count > 0) {
        ctx.fillStyle = baseColor
        ctx.fill(path)
      }
    }
    if (count > 0) budget.n += count
    return
  }

  const paintOne = (seg) => {
    if (budgetFull(budget)) return false

    const x1raw = (seg.start - timeStart) * pxPerNs
    const x2raw = (seg.end   - timeStart) * pxPerNs
    if (x2raw < -2 || x1raw > viewW + 2) return true
    const x1 = Math.max(0, x1raw)
    const x2 = Math.min(viewW, x2raw)
    const w = Math.max(MIN_SEG_W, x2 - x1)

    const isSegLocked = hlSeg && seg.start === hlSeg.start && seg.end === hlSeg.end && seg.task === hlSeg.task
    const drawX  = Math.round(x1)
    const drawW  = Math.ceil(w)
    const drawY  = rowY
    const drawH  = rowH
    gpuFillRect(gpuBatch, ctx, drawX, drawY, drawW, drawH, baseColor, fillAlpha)
    budget.n++

    if (drawTint && applyCoreTint) {
      const tint = coreTint(seg.core)
      if (tint) {
        ctx.fillStyle = tint
        ctx.fillRect(drawX, drawY, drawW, drawH)
      }
    }

    if (isHighlighted) {
      ctx.fillStyle = 'rgba(255,255,200,0.25)'
      ctx.fillRect(drawX, drawY, drawW, drawH)
    }

    if (drawOutlines && w >= 3) {
      if (isSegLocked) {
        ctx.strokeStyle = complementaryColor(baseColor)
        ctx.lineWidth = 2.5
      } else {
        ctx.strokeStyle = darkMode ? 'rgba(0,0,0,0.4)' : 'rgba(0,0,0,0.3)'
        ctx.lineWidth = 0.5
      }
      ctx.strokeRect(drawX + 0.5, drawY + 0.5, drawW - 1, drawH - 1)
    }

    if (drawLabels && segLabel && w >= 40) {
      labelRects.push({ drawX, drawW })
    }
    return true
  }

  for (const seg of drawList) {
    if (!paintOne(seg)) break
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
 * Return segment arrays for hit-testing a task/core row or column.
 */
function segsForRowHit(trace, row) {
  if (row.type === 'task') {
    return {
      segs: trace.segByMergeKey.get(row.key) || [],
      starts: trace.segStartByMergeKey.get(row.key) || [],
    }
  }
  if (row.type === 'core-task') {
    const cMap = trace.coreTaskSegs.get(row.coreKey)
    const cStartMap = trace.coreTaskSegStarts.get(row.coreKey)
    return {
      segs: (cMap && cMap.get(row.taskKey)) || [],
      starts: (cStartMap && cStartMap.get(row.taskKey)) || [],
    }
  }
  if (row.type === 'core') {
    return {
      segs: trace.coreSegs.get(row.key) || [],
      starts: trace.coreSegStarts.get(row.key) || [],
    }
  }
  return { segs: [], starts: [] }
}

function segmentAtTime(segs, starts, tAt, rowType) {
  const lo = Math.max(0, bisectLeft(starts, tAt) - 1)
  for (let i = lo; i < segs.length; i++) {
    const s = segs[i]
    if (s.start > tAt) break
    if (s.end >= tAt) {
      if (rowType === 'core') {
        if (isCoreName(s.task)) continue
        if (parseTaskName(s.task).name === 'TICK') continue
      }
      return s
    }
  }
  return null
}

function rowMatchesLockedSegment(row, mk, hlSeg) {
  if (row.type === 'task' && row.key === mk) return true
  if (row.type === 'core-task' && taskMergeKey(row.taskKey) === mk) return true
  if (row.type === 'core' && hlSeg?.core === row.key && taskMergeKey(hlSeg.task) === mk) return true
  return false
}

/**
 * Draw the locked (highlighted) segment enlarged by 10% vertically,
 * unclipped, over the body area. Called after ctx.restore() in render().
 */
function drawLockedSegmentHoriz(ctx, trace, rows, yOff, hlSeg, timeStart, timeEnd, pxPerNs, nsPerPx, darkMode) {
  if (!hlSeg) return
  const mk = taskMergeKey(hlSeg.task)
  for (const row of rows) {
    if (!rowMatchesLockedSegment(row, mk, hlSeg)) continue
    const x1        = (hlSeg.start - timeStart) * pxPerNs
    const x2        = (hlSeg.end   - timeStart) * pxPerNs
    const w         = Math.max(MIN_SEG_W, x2 - x1)
    if (x1 > (timeEnd - timeStart) * pxPerNs + 2 || x1 + w < -2) return
    const baseColor = row.type === 'core'
      ? taskColor(mk, hlSeg.task)
      : row.color
    const label     = row.type === 'core' ? taskDisplayName(hlSeg.task) : row.label
    const slot       = L().rowH + L().rowGap            // full row slot including gap
    const newH       = slot * 1.10                // 10% of slot
    const canvasRowY = row.y + yOff
    const rowCenter  = canvasRowY + L().rowH / 2         // center of the row band
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
    if (label && drawW >= 40) {
      ctx.save()
      ctx.font = '10px sans-serif'
      ctx.fillStyle = darkMode ? 'rgba(255,255,255,0.85)' : 'rgba(0,0,0,0.75)'
      ctx.textBaseline = 'middle'
      const tx = drawX + 3
      ctx.beginPath()
      ctx.rect(tx, drawY, drawW - 6, newH)
      ctx.clip()
      ctx.fillText(label, tx, drawY + newH / 2)
      ctx.restore()
    }
    return
  }
}

function drawLockedSegmentVert(ctx, trace, cols, hlSeg, timeStart, timeEnd, pxPerNs, nsPerPx, headerH, canvasH, darkMode) {
  if (!hlSeg) return
  const mk = taskMergeKey(hlSeg.task)
  for (const col of cols) {
    if (!rowMatchesLockedSegment(col, mk, hlSeg)) continue
    const colX      = col.x
    const segX      = colX + 1
    const segW      = COL_W - 2
    const y1        = headerH + (hlSeg.start - timeStart) * pxPerNs
    const y2        = headerH + (hlSeg.end   - timeStart) * pxPerNs
    const h         = Math.max(1, y2 - y1)
    if (y1 > canvasH + 2 || y1 + h < headerH - 2) return
    const baseColor = col.type === 'core'
      ? taskColor(mk, hlSeg.task)
      : col.color
    const label     = col.type === 'core' ? taskDisplayName(hlSeg.task) : col.label
    const slot       = COL_W + L().rowGap            // full column slot including gap
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
    if (label && drawH >= 40) {
      ctx.save()
      ctx.font = '10px sans-serif'
      ctx.fillStyle = darkMode ? 'rgba(255,255,255,0.85)' : 'rgba(0,0,0,0.75)'
      ctx.textBaseline = 'middle'
      ctx.textAlign = 'left'
      const cx = drawX + newW / 2
      const topY = drawY + 3
      ctx.translate(cx, topY)
      ctx.rotate(Math.PI / 2)
      ctx.fillText(label, 0, 0)
      ctx.restore()
    }
    return
  }
}

function drawTaskRow(ctx, trace, row, canvasRowY, timeStart, timeEnd, pxPerNs, nsPerPx, highlightKey, canvasW, darkMode, hlSeg, budget, showHoverHighlight = false, gpuBatch = null) {
  const mk = row.key
  const ld = taskLodData(trace, mk)
  const fast = budget.fast
  const forceCoarse = fast || budgetLite(budget) || nsPerPx > PAINT_LOD_COARSE
  const { segs, indices } = queryPaintIndices(
    trace, 'task', mk, ld, timeStart, timeEnd, nsPerPx,
    trace.lodTimescalePerPx, trace.lodUltraTimescalePerPx, budget.max, forceCoarse, fast,
  )

  const rowY = canvasRowY + 1
  const rowH = L().rowH - 2
  const dim = showHoverHighlight && highlightKey && mk !== highlightKey && !hlSeg
  if (dim) ctx.save()
  if (dim) ctx.globalAlpha = 45 / 255
  const fillAlpha = dim ? 45 / 255 : 1

  if (!fast) {
    ctx.fillStyle = darkMode ? 'rgba(255,255,255,0.02)' : 'rgba(0,0,0,0.02)'
    ctx.fillRect(0, canvasRowY, canvasW, L().rowH)
  }

  paintSegments(ctx, segs, timeStart, timeEnd, pxPerNs, nsPerPx,
    rowY, rowH, row.color, trace, /* coreTint */ true, highlightKey, mk, darkMode, row.label, hlSeg, budget,
    indices, gpuBatch, fillAlpha)

  if (dim) ctx.restore()

  if (!fast) paintPriorityBoostBands(ctx, trace, mk, rowY, rowH, timeStart, timeEnd, pxPerNs, canvasW, darkMode)
}

function drawCoreRow(ctx, trace, row, canvasRowY, timeStart, timeEnd, pxPerNs, nsPerPx, canvasW, darkMode, budget, skipSummarySegs = false, gpuBatch = null) {
  const fast = budget.fast
  if (!fast) {
    ctx.fillStyle = darkMode ? 'rgba(255,255,255,0.03)' : 'rgba(0,0,0,0.03)'
    ctx.fillRect(0, canvasRowY, canvasW, L().rowH)
  }
  if (skipSummarySegs) return

  const ld = coreLodData(trace, row.key)
  const forceCoarse = fast || budgetLite(budget) || nsPerPx > PAINT_LOD_COARSE
  const { segs, indices } = queryPaintIndices(
    trace, 'core', row.key, ld, timeStart, timeEnd, nsPerPx,
    trace.lodTimescalePerPx, trace.lodUltraTimescalePerPx, budget.max, true, fast,
  )

  const rowY = canvasRowY + 1
  const rowH = L().rowH - 2
  const drawLabels = !fast && !forceCoarse && !budgetLite(budget)

  const colorCache = new Map()
  const labelRects = []
  const midY = rowY + rowH / 2

  const drawList = indices
    ? mergeColumnSpans(segs, timeStart, nsPerPx, indices, s => s.task)
    : segmentsForBudget(segs, nsPerPx, timeStart, timeEnd, budget.max, true)

  for (const seg of drawList) {
    if (budgetFull(budget)) break
    if (isCoreName(seg.task)) continue
    // TICK is shown as ruler band marks – skip it in the core summary row.
    if (parseTaskName(seg.task).name === 'TICK') continue
    const x1raw = (seg.start - timeStart) * pxPerNs
    const x2raw = (seg.end   - timeStart) * pxPerNs
    if (x2raw < -2 || x1raw > canvasW + 2) continue
    const x1 = Math.max(0, x1raw)
    const x2 = Math.min(canvasW, x2raw)
    const w  = Math.max(MIN_SEG_W, x2 - x1)

    let color = colorCache.get(seg.task)
    if (color === undefined) {
      color = taskColor(taskMergeKey(seg.task), seg.task)
      colorCache.set(seg.task, color)
    }
    const drawX = Math.round(x1)
    const drawW = Math.ceil(w)
    gpuFillRect(gpuBatch, ctx, drawX, rowY, drawW, rowH, color)
    budget.n++

    if (drawLabels && w >= 40) {
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

function drawCoreTaskRow(ctx, trace, row, canvasRowY, timeStart, timeEnd, pxPerNs, nsPerPx, highlightKey, canvasW, darkMode, hlSeg, lockedTaskKey, budget, showHoverHighlight = false, gpuBatch = null) {
  const ld = coreTaskLodData(trace, row.coreKey, row.taskKey)
  const mk = taskMergeKey(row.taskKey)
  const wasmKey = `${row.coreKey}__${row.taskKey}`
  const fast = budget.fast
  const forceCoarse = fast || budgetLite(budget) || nsPerPx > PAINT_LOD_COARSE
  const { segs, indices } = queryPaintIndices(
    trace, 'core-task', wasmKey, ld, timeStart, timeEnd, nsPerPx,
    trace.lodTimescalePerPx, trace.lodUltraTimescalePerPx, budget.max, forceCoarse, fast,
  )

  if (!fast) {
    ctx.fillStyle = darkMode ? 'rgba(255,255,255,0.01)' : 'rgba(0,0,0,0.01)'
    ctx.fillRect(0, canvasRowY, canvasW, L().rowH)
  }

  const dimLocked = lockedTaskKey && mk !== lockedTaskKey
  const dimHover = showHoverHighlight && highlightKey && mk !== highlightKey && !hlSeg && !lockedTaskKey
  const dim = dimLocked || dimHover
  if (dim) ctx.save()
  if (dim) ctx.globalAlpha = 45 / 255
  const fillAlpha = dim ? 45 / 255 : 1
  paintSegments(ctx, segs, timeStart, timeEnd, pxPerNs, nsPerPx,
    canvasRowY + 1, L().rowH - 2, row.color, trace, false, highlightKey, mk, darkMode, row.label, hlSeg, budget,
    indices, gpuBatch, fillAlpha)

  if (dim) ctx.restore()

  if (!fast) {
    paintPriorityBoostBands(
      ctx, trace, mk, canvasRowY + 1, L().rowH - 2,
      timeStart, timeEnd, pxPerNs, canvasW, darkMode,
    )
  }
}

/** Draw paired interval spans as horizontal bars (Tracealyzer-style interval lane). */
function drawIntervalRow(ctx, trace, row, canvasRowY, timeStart, timeEnd, pxPerNs, canvasW, darkMode, highlightInterval = null) {
  const rowY = canvasRowY
  const rowH = L().rowH
  ctx.fillStyle = darkMode ? 'rgba(255,255,255,0.02)' : 'rgba(0,0,0,0.02)'
  ctx.fillRect(0, canvasRowY, canvasW, rowH)
  const { instances, preCulled } = intervalInstancesForDraw(trace, row.key)
  const visible = visibleIntervalInstances(instances, timeStart, timeEnd, preCulled)
  const base = row.color || intervalColor(row.key)
  const stroke = darkMode ? lighterColor(base, 1.55) : lighterColor(base, 0.72)

  const bars = []
  for (const inst of visible) {
    const x1 = (inst.startNs - timeStart) * pxPerNs
    const x2 = (inst.stopNs - timeStart) * pxPerNs
    if (x2 < -2 || x1 > canvasW + 2) continue
    const cx = Math.max(0, Math.floor(x1))
    const cx2 = Math.min(Math.ceil(x2), canvasW)
    const drawW = cx2 - cx
    if (drawW < 0.5) continue
    bars.push({ inst, cx, drawW })
  }

  const markerEvents = visibleIntervalMarkerEvents(trace, row.key, timeStart, timeEnd)
  const barY = rowY + 2
  const barH = rowH - 4

  ctx.save()
  for (const bar of bars) {
    const { cx, drawW } = bar
    ctx.fillStyle = base
    ctx.fillRect(cx, barY, drawW, barH)
    if (drawW >= 3) {
      ctx.strokeStyle = stroke
      ctx.lineWidth = 1.25
      ctx.strokeRect(cx + 0.5, barY + 0.5, drawW - 1, barH - 1)
    }
  }
  if (markerEvents.length > 0) {
    const { dark: tickDark, light: tickLight } = intervalStripeColors(base, darkMode)
    ctx.lineWidth = 1
    for (const ev of markerEvents) {
      const x = (ev.timeNs - timeStart) * pxPerNs
      if (x < -1 || x > canvasW + 1) continue
      const xi = Math.round(x) + 0.5
      ctx.strokeStyle = ev.isStart ? tickDark : tickLight
      if (!ev.isStart) ctx.setLineDash([2, 2])
      else ctx.setLineDash([])
      ctx.beginPath()
      ctx.moveTo(xi, barY)
      ctx.lineTo(xi, barY + barH)
      ctx.stroke()
    }
    ctx.setLineDash([])
  }

  const hi = (highlightInterval && String(highlightInterval.id) === String(row.key))
    ? highlightInterval
    : null
  if (hi) {
    const markNs = hi.markNs ?? hi.stopNs
    const times = new Set([markNs, hi.startNs, hi.stopNs])
    ctx.strokeStyle = darkMode ? 'rgba(255,255,255,0.92)' : 'rgba(0,0,0,0.88)'
    ctx.lineWidth = 2
    ctx.setLineDash([])
    for (const t of times) {
      const x = (t - timeStart) * pxPerNs
      if (x < -1 || x > canvasW + 1) continue
      const xi = Math.round(x) + 0.5
      ctx.beginPath()
      ctx.moveTo(xi, barY)
      ctx.lineTo(xi, barY + barH)
      ctx.stroke()
    }
  }
  ctx.restore()
}

/** Draw paired interval spans as vertical bars (vertical timeline orientation). */
function drawIntervalColumn(ctx, trace, col, timeStart, timeEnd, pxPerNs, canvasH, darkMode, highlightInterval = null) {
  const colX = col.x
  const colW = col.colWidth ?? COL_W
  const headerH = vertHeaderBand()
  const bodyH = canvasH - headerH

  ctx.fillStyle = darkMode ? 'rgba(255,255,255,0.02)' : 'rgba(0,0,0,0.02)'
  ctx.fillRect(colX, headerH, colW, bodyH)

  const { instances, preCulled } = intervalInstancesForDraw(trace, col.key)
  const visible = visibleIntervalInstances(instances, timeStart, timeEnd, preCulled)
  const base = col.color || intervalColor(col.key)
  const stroke = darkMode ? lighterColor(base, 1.55) : lighterColor(base, 0.72)

  const bars = []
  for (const inst of visible) {
    const y1 = (inst.startNs - timeStart) * pxPerNs
    const y2 = (inst.stopNs - timeStart) * pxPerNs
    if (y2 < -2 || y1 > bodyH + 2) continue
    const cy = Math.max(0, Math.floor(y1))
    const cy2 = Math.min(Math.ceil(y2), bodyH)
    const drawH = cy2 - cy
    if (drawH < 0.5) continue
    bars.push({ inst, cy, drawH })
  }

  const markerEvents = visibleIntervalMarkerEvents(trace, col.key, timeStart, timeEnd)
  const barX = colX + 2
  const barW = colW - 4

  ctx.save()
  for (const bar of bars) {
    const { cy, drawH } = bar
    ctx.fillStyle = base
    ctx.fillRect(barX, headerH + cy, barW, drawH)
    if (drawH >= 3) {
      ctx.strokeStyle = stroke
      ctx.lineWidth = 1.25
      ctx.strokeRect(barX + 0.5, headerH + cy + 0.5, barW - 1, drawH - 1)
    }
  }
  if (markerEvents.length > 0) {
    const { dark: tickDark, light: tickLight } = intervalStripeColors(base, darkMode)
    ctx.lineWidth = 1
    for (const ev of markerEvents) {
      const y = (ev.timeNs - timeStart) * pxPerNs
      if (y < -1 || y > bodyH + 1) continue
      const yi = Math.round(headerH + y) + 0.5
      ctx.strokeStyle = ev.isStart ? tickDark : tickLight
      if (!ev.isStart) ctx.setLineDash([2, 2])
      else ctx.setLineDash([])
      ctx.beginPath()
      ctx.moveTo(barX, yi)
      ctx.lineTo(barX + barW, yi)
      ctx.stroke()
    }
    ctx.setLineDash([])
  }

  const hi = (highlightInterval && String(highlightInterval.id) === String(col.key))
    ? highlightInterval
    : null
  if (hi) {
    const markNs = hi.markNs ?? hi.stopNs
    const times = new Set([markNs, hi.startNs, hi.stopNs])
    ctx.strokeStyle = darkMode ? 'rgba(255,255,255,0.92)' : 'rgba(0,0,0,0.88)'
    ctx.lineWidth = 2
    ctx.setLineDash([])
    for (const t of times) {
      const y = (t - timeStart) * pxPerNs
      if (y < -1 || y > bodyH + 1) continue
      const yi = Math.round(headerH + y) + 0.5
      ctx.beginPath()
      ctx.moveTo(barX, yi)
      ctx.lineTo(barX + barW, yi)
      ctx.stroke()
    }
  }
  ctx.restore()
}

function drawStiRow(ctx, trace, row, canvasRowY, timeStart, timeEnd, pxPerNs, canvasW, darkMode, logScale = false) {
  if (row.isExpanded) {
    drawStiWaveformRow(ctx, trace, row, canvasRowY, timeStart, timeEnd, pxPerNs, canvasW, darkMode, logScale)
    return
  }

  const rowY = canvasRowY
  const evs = trace.stiEventsByTarget.get(row.key) || []
  const starts = trace.stiStartsByTarget.get(row.key) || []

  const lo = Math.max(0, bisectLeft(starts, timeStart) - 1)
  const hi = bisectRight(starts, timeEnd) + 1

  const markerR = 5
  const cy = rowY + L().stiRowH / 2

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
function drawStiWaveformRow(ctx, trace, row, canvasRowY, timeStart, timeEnd, pxPerNs, canvasW, darkMode, logScale = false) {
  const rowY = canvasRowY
  const rowH = L().stiWaveformH

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
      if (L().stiLineStyle === 'step' && i > 0) {
        const prevEv = slice[i - 1]
        const prevVal = evVal(prevEv)
        if (!isNaN(prevVal)) {
          const prevCx = (prevEv.time - timeStart) * pxPerNs
          const prevCy = valToY(prevVal)
          ctx.lineTo(cx, prevCy)
        }
      }
      ctx.lineTo(cx, cy)
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

function _drawCursorDeltaBadgeH(ctx, text, midX, color, canvasW, labelY) {
  ctx.save()
  ctx.font = '10px monospace'
  ctx.textBaseline = 'top'
  ctx.textAlign = 'left'
  const tw = ctx.measureText(text).width
  const pad = 3
  const bw = tw + pad * 2
  const bh = 14
  let bx = Math.round(midX - bw / 2)
  bx = Math.max(2, Math.min(bx, canvasW - bw - 2))
  const by = labelY
  ctx.fillStyle = color
  ctx.fillRect(bx, by, bw, bh)
  ctx.fillStyle = '#000'
  ctx.fillText(text, bx + pad, by + 2)
  ctx.restore()
}

function _drawCursorDeltaBadgeV(ctx, text, midY, color, canvasH, headerH) {
  ctx.save()
  ctx.font = '10px monospace'
  ctx.textBaseline = 'middle'
  ctx.textAlign = 'left'
  const tw = ctx.measureText(text).width
  const pad = 3
  const bw = tw + pad * 2
  const bh = 14
  const bx = RULER_W + 4
  let by = Math.round(midY - bh / 2)
  by = Math.max(headerH + 2, Math.min(by, canvasH - bh - 2))
  ctx.fillStyle = color
  ctx.fillRect(bx, by, bw, bh)
  ctx.fillStyle = '#000'
  ctx.fillText(text, bx + pad, by + bh / 2)
  ctx.restore()
}

export function drawCursors(ctx, cursors, trace, timeStart, pxPerNs, canvasW, canvasH, _darkMode) {
  if (!cursors || cursors.length === 0 || !trace) return
  const sorted = cursorSortedPlaced(cursors)
  if (!sorted.length) return

  ctx.save()

  for (let order = 0; order < sorted.length; order++) {
    const { t, slotIndex } = sorted[order]
    const x = Math.round((t - timeStart) * pxPerNs)
    if (x < -2 || x > canvasW + 2) continue

    ctx.font = 'bold 10px monospace'
    ctx.textBaseline = 'top'
    ctx.textAlign = 'left'

    const color = CURSOR_COLORS[slotIndex % CURSOR_COLORS.length]
    ctx.strokeStyle = color
    ctx.lineWidth = 1.5
    ctx.setLineDash([4, 3])
    ctx.beginPath()
    ctx.moveTo(x + 0.5, 0)
    ctx.lineTo(x + 0.5, canvasH)
    ctx.stroke()
    ctx.setLineDash([])

    const label = `C${slotIndex + 1}: ${formatTime(t, trace.timeScale, 3)}`
    const tw = ctx.measureText(label).width + 8
    const th = 16
    const lx = Math.min(x + 3, canvasW - tw - 2)
    const ly = 2 + (slotIndex + 1) * (th + 2)
    ctx.fillStyle = color
    ctx.fillRect(lx, ly, tw, th)
    ctx.fillStyle = '#000'
    ctx.fillText(label, lx + 4, ly + 3)

    if (order > 0) {
      const prevT = sorted[order - 1].t
      const delta = Math.abs(t - prevT)
      const dStr = `Δ ${formatTime(delta, trace.timeScale, 3)}`
      const midX = ((t + prevT) / 2 - timeStart) * pxPerNs
      if (midX >= 0 && midX <= canvasW) {
        _drawCursorDeltaBadgeH(ctx, dStr, midX, color, canvasW, ly)
      }
    }
  }
  ctx.restore()
}

/** Find-hit markers (all matches) and optional active marker highlight. */
export function drawFindHits(ctx, hitNsList, activeNs, trace, timeStart, pxPerNs, canvasW, canvasH, darkMode) {
  if (!hitNsList?.length || !trace) return
  ctx.save()
  for (const ns of hitNsList) {
    const x = Math.round((ns - timeStart) * pxPerNs)
    if (x < 0 || x > canvasW) continue
    const isActive = activeNs != null && ns === activeNs
    ctx.strokeStyle = isActive
      ? (darkMode ? '#FFD54F' : '#E65100')
      : (darkMode ? 'rgba(255, 200, 80, 0.55)' : 'rgba(200, 100, 0, 0.45)')
    ctx.lineWidth = isActive ? 2.5 : 1
    ctx.setLineDash(isActive ? [] : [2, 4])
    ctx.beginPath()
    ctx.moveTo(x + 0.5, 0)
    ctx.lineTo(x + 0.5, canvasH)
    ctx.stroke()
  }
  ctx.setLineDash([])
  ctx.restore()
}

export function drawFindHitsVertical(ctx, hitNsList, activeNs, trace, timeStart, pxPerNs, canvasW, canvasH, headerH, darkMode) {
  if (!hitNsList?.length || !trace) return
  ctx.save()
  for (const ns of hitNsList) {
    const y = Math.round(headerH + (ns - timeStart) * pxPerNs)
    if (y < headerH || y > canvasH) continue
    const isActive = activeNs != null && ns === activeNs
    ctx.strokeStyle = isActive
      ? (darkMode ? '#FFD54F' : '#E65100')
      : (darkMode ? 'rgba(255, 200, 80, 0.55)' : 'rgba(200, 100, 0, 0.45)')
    ctx.lineWidth = isActive ? 2.5 : 1
    ctx.setLineDash(isActive ? [] : [2, 4])
    ctx.beginPath()
    ctx.moveTo(0, y + 0.5)
    ctx.lineTo(canvasW, y + 0.5)
    ctx.stroke()
  }
  ctx.setLineDash([])
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

/** Gray band for right-drag (or middle-drag) time-range selection — horizontal mode. */
export function drawRangeSelect(ctx, t0, t1, timeStart, pxPerNs, canvasW, canvasH, darkMode) {
  const lo = Math.min(t0, t1)
  const hi = Math.max(t0, t1)
  const x1 = Math.round((lo - timeStart) * pxPerNs)
  const x2 = Math.round((hi - timeStart) * pxPerNs)
  const w  = Math.max(1, x2 - x1)
  ctx.save()
  ctx.fillStyle   = darkMode ? 'rgba(180,180,180,0.22)' : 'rgba(120,120,120,0.25)'
  ctx.strokeStyle = darkMode ? 'rgba(220,220,220,0.45)' : 'rgba(80,80,80,0.35)'
  ctx.lineWidth   = 1
  ctx.fillRect(x1, RULER_H, w, canvasH - RULER_H)
  ctx.strokeRect(x1 + 0.5, RULER_H + 0.5, Math.max(0, w - 1), canvasH - RULER_H - 1)
  ctx.restore()
}

/** Gray band for time-range selection — vertical mode. */
export function drawRangeSelectVertical(ctx, t0, t1, timeStart, pxPerNs, canvasW, canvasH, headerH, darkMode) {
  const lo = Math.min(t0, t1)
  const hi = Math.max(t0, t1)
  const y1 = headerH + Math.round((lo - timeStart) * pxPerNs)
  const y2 = headerH + Math.round((hi - timeStart) * pxPerNs)
  const h  = Math.max(1, y2 - y1)
  ctx.save()
  ctx.fillStyle   = darkMode ? 'rgba(180,180,180,0.22)' : 'rgba(120,120,120,0.25)'
  ctx.strokeStyle = darkMode ? 'rgba(220,220,220,0.45)' : 'rgba(80,80,80,0.35)'
  ctx.lineWidth   = 1
  ctx.fillRect(RULER_W, y1, canvasW - RULER_W, h)
  ctx.strokeRect(RULER_W + 0.5, y1 + 0.5, canvasW - RULER_W - 1, Math.max(0, h - 1))
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
  const { viewMode = 'task', expanded = new Set(), showSti = true, stiExpanded = new Set(), migratedOnlyFilter = false } = options
  if (!showSti || cy < RULER_H) return null

  const rows = resolveRows(trace, options, viewMode, expanded, showSti, stiExpanded, migratedOnlyFilter)
  const bodyH = canvasH - RULER_H
  const { i0, i1 } = visibleRowIndexRange(rows, scrollY, bodyH, 2)
  const yOff = RULER_H - scrollY

  for (let i = i0; i < i1; i++) {
    const row = rows[i]
    if (row.type !== 'sti') continue
    const rowH = rowBandHeight(row)
    const cyRow = row.y + yOff + rowH / 2
    if (Math.abs(cy - cyRow) > rowH) continue

    const evs = trace.stiEventsByTarget.get(row.key) || []
    const starts = trace.stiStartsByTarget.get(row.key) || []
    const tAtCx = timeStart + cx / pxPerNs
    const lo = Math.max(0, bisectLeft(starts, tAtCx - radius / pxPerNs) - 1)
    const hi = bisectRight(starts, tAtCx + radius / pxPerNs) + 1

    let best = null, bestDist = radius + 1
    for (let j = lo; j < Math.min(hi, evs.length); j++) {
      const ev = evs[j]
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
  const { scrollY, canvasH } = viewport
  const { viewMode = 'task', expanded = new Set(), showSti = true, stiExpanded = new Set(), migratedOnlyFilter = false } = options
  if (cy < RULER_H) return null

  const rows = resolveRows(trace, options, viewMode, expanded, showSti, stiExpanded, migratedOnlyFilter)
  const bodyH = canvasH - RULER_H
  const targetY = cy - RULER_H + scrollY
  const { i0, i1 } = visibleRowIndexRange(rows, scrollY, bodyH, 2)

  for (let i = i0; i < i1; i++) {
    const row = rows[i]
    const rh = rowBandHeight(row)
    if (targetY >= row.y && targetY < row.y + rh) return row
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
  const { timeStart, timeEnd, scrollY, canvasW, canvasH } = viewport
  const { viewMode = 'task', expanded = new Set(), showSti = true, stiExpanded = new Set(), migratedOnlyFilter = false } = options
  if (cy < RULER_H) return null
  const pxPerNs = canvasW / (timeEnd - timeStart)

  const rows = resolveRows(trace, options, viewMode, expanded, showSti, stiExpanded, migratedOnlyFilter)
  const bodyH = canvasH - RULER_H
  const targetY = cy - RULER_H + scrollY
  const { i0, i1 } = visibleRowIndexRange(rows, scrollY, bodyH, 1)

  let row = null
  for (let i = i0; i < i1; i++) {
    const r = rows[i]
    if (r.type !== 'task' && r.type !== 'core-task' && r.type !== 'core') continue
    if (viewMode !== 'core' && r.type === 'core') continue
    const rh = rowBandHeight(r)
    if (targetY >= r.y && targetY < r.y + rh) { row = r; break }
  }
  if (!row) return null

  const tAtCx = timeStart + cx / pxPerNs
  const { segs, starts } = segsForRowHit(trace, row)
  return segmentAtTime(segs, starts, tAtCx, row.type)
}

/**
 * Return the exact segment under canvas point (cx, cy) in vertical mode, or null.
 */
export function hitTestSegmentVertical(trace, viewport, options, cx, cy) {
  const { timeStart, timeEnd, scrollX = 0, canvasH } = viewport
  const { viewMode = 'task', expanded = new Set(), showSti = true, stiExpanded = new Set(), migratedOnlyFilter = false } = options
  const headerH = options.vertHeaderH ?? HEADER_H
  if (cy < headerH || cx < RULER_W) return null
  const bodyH   = canvasH - headerH
  const pxPerNs = bodyH / (timeEnd - timeStart)
  const tAtCy   = timeStart + (cy - headerH) / pxPerNs

  const cols = resolveCols(trace, options, viewMode, expanded, showSti, stiExpanded, migratedOnlyFilter)
  let col = null
  for (const c of cols) {
    if (c.type !== 'task' && c.type !== 'core-task' && c.type !== 'core') continue
    if (viewMode !== 'core' && c.type === 'core') continue
    const x = c.x - scrollX
    const cw = c.colWidth ?? COL_W
    if (cx >= x && cx < x + cw) { col = c; break }
  }
  if (!col) return null

  const { segs, starts } = segsForRowHit(trace, col)
  return segmentAtTime(segs, starts, tAtCy, col.type)
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
 * STI tag-event channels are expandable; when expanded they use L().stiWaveformH as column width.
 *
 * @param {object} trace
 * @param {string} viewMode      'task' or 'core'
 * @param {Set}    expanded      Set of expanded core names
 * @param {number} scrollX       Horizontal scroll offset in pixels
 * @param {boolean} showSti
 * @param {Set}    stiExpanded   Set of expanded STI channel names
 * @returns {{ cols: Array, totalWidth: number }}
 */
export function buildColumnLayout(trace, viewMode, expanded, scrollX = 0, showSti = true, stiExpanded = new Set(), migratedOnlyFilter = false, taskFilterKeys = null, taskFilterText = '') {
  const cols = []
  let rawIdx = 0
  let xAcc   = 0  // accumulated pixel offset from RULER_W (before scrollX)
  const stiFilterQ = normalizeTaskFilterText(taskFilterText)

  if (viewMode === 'task') {
    for (const mk of trace.tasks) {
      if (!taskPassesRowFilter(trace, mk, migratedOnlyFilter, taskFilterKeys, taskFilterText)) continue
      const repr = trace.taskRepr.get(mk)
      const label = taskDisplayName(repr || mk) + taskPriorityLabelSuffix(trace, mk)
      const color = taskColor(mk, repr)
      const x = RULER_W + xAcc - scrollX
      cols.push({ type: 'task', key: mk, label, color, x, colIdx: rawIdx, colWidth: COL_W })
      rawIdx++
      xAcc += COL_W
    }
  } else {
    // Core view
    const cores = filteredCoreViewTasks(trace, migratedOnlyFilter, taskFilterKeys, taskFilterText)
    for (const { coreName, tasks } of cores) {
      const cc = coreColor(coreName)
      const x = RULER_W + xAcc - scrollX
      cols.push({ type: 'core', key: coreName, label: coreName, color: cc, x, colIdx: rawIdx, colWidth: COL_W })
      rawIdx++
      xAcc += COL_W
      if (expanded.has(coreName)) {
        for (const rawTask of tasks) {
          const mk = taskMergeKey(rawTask)
          const lbl = taskDisplayName(rawTask) + taskPriorityLabelSuffix(trace, mk)
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
      if (isIntervalMarkerChannel(ch)) continue
      if (stiFilterQ && !stiChannelMatchesTextFilter(trace, ch, stiFilterQ)) continue
      const isExpandable = isStiTagChannel(ch)
      const isExpanded   = isExpandable && stiExpanded.has(ch)
      const cw           = isExpanded ? L().stiWaveformH : COL_W
      const x = RULER_W + xAcc - scrollX
      cols.push({ type: 'sti', key: ch, label: ch, color: '#888', x, colIdx: rawIdx, colWidth: cw, isExpanded, isExpandable })
      rawIdx++
      xAcc += cw
    }
    for (const id of (trace.intervalIds || [])) {
      const x = RULER_W + xAcc - scrollX
      cols.push({
        type: 'interval',
        key: id,
        label: `Interval ${id}`,
        color: intervalColor(id),
        x,
        colIdx: rawIdx,
        colWidth: COL_W,
      })
      rawIdx++
      xAcc += COL_W
    }
  }

  return { cols, totalWidth: RULER_W + xAcc }
}

/** Apply horizontal scroll offset to a layout built with scrollX=0. */
export function offsetColumnLayout(layout, scrollX) {
  if (!layout || !scrollX) return layout
  return {
    cols: layout.cols.map(c => ({ ...c, x: c.x - scrollX })),
    totalWidth: layout.totalWidth,
  }
}

// ---- Vertical ruler (left side) -------------------------------------------

function drawVerticalRuler(ctx, trace, timeStart, timeEnd, pxPerNs, canvasH, headerH, rulerW, darkMode, fastPaint = false) {
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
  if (!fastPaint && minorStep > 0) {
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

  drawTickMarkersOnRulerVertical(ctx, trace, timeStart, timeEnd, pxPerNs, canvasH, headerH, rulerW, fastPaint)
}

function drawTickMarkersOnRulerVertical(ctx, trace, timeStart, timeEnd, pxPerNs, canvasH, headerH, rulerW, fastPaint = false) {
  if (fastPaint) return

  const bandX = rulerW - 18
  const bandW = 8
  ctx.save()
  ctx.fillStyle = TICK_COLOR
  ctx.globalAlpha = 0.95

  let prevPy = -2

  // Task-type TICK segments
  const tickMk = taskMergeKey('TICK')
  const segs = trace.segByMergeKey?.get(tickMk) || []
  const starts = trace.segStartByMergeKey?.get(tickMk) || []
  if (segs.length > 0 && starts.length > 0) {
    const lo = Math.max(0, bisectLeft(starts, timeStart) - 1)
    const hi = Math.min(segs.length, bisectRight(starts, timeEnd) + 1)
    for (let i = lo; i < hi; i++) {
      const seg = segs[i]
      const py = Math.round(headerH + (seg.start - timeStart) * pxPerNs)
      if (py < headerH - 2 || py > canvasH + 2 || py === prevPy) continue
      prevPy = py
      ctx.fillRect(bandX, py - 0.5, bandW, 2)
    }
  }

  // STI-type TICK events — one marker per pixel row
  const stiTimes = trace.tickStiTimes || []
  if (stiTimes.length > 0) {
    const lo2 = Math.max(0, bisectLeft(stiTimes, timeStart) - 1)
    const hi2 = Math.min(stiTimes.length, bisectRight(stiTimes, timeEnd) + 1)
    for (let i = lo2; i < hi2; i++) {
      const py = Math.round(headerH + (stiTimes[i] - timeStart) * pxPerNs)
      if (py < headerH - 2 || py > canvasH + 2 || py === prevPy) continue
      prevPy = py
      ctx.fillRect(bandX, py - 0.5, bandW, 2)
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
    let color = isHl ? '#FFD700' : (darkMode ? '#D4D4D4' : '#1E1E1E')
    if (col.type === 'sti') color = '#88AABB'
    else if (col.type === 'interval') color = col.color || intervalColor(col.key)
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

function paintSegmentsVertical(ctx, segs, timeStart, timeEnd, pxPerNs, nsPerPx, colX, colW, headerH,
                               baseColor, trace, applyCoreTint, highlightKey, colMk, darkMode, segLabel, hlSeg, canvasH, budget,
                               segIndices = null, gpuBatch = null, fillAlpha = 1) {
  const isHighlighted = (highlightKey && colMk === highlightKey) && !hlSeg
  const fast = budget.fast
  const forceCoarse = fast || budgetLite(budget) || nsPerPx > PAINT_LOD_COARSE
  const drawOutlines = !fast && !forceCoarse
  const drawLabels   = drawOutlines && !budgetLite(budget)
  const drawTint     = !fast && !forceCoarse && !budgetLite(budget)
  const reduced = segIndices ? null : segmentsForBudget(segs, nsPerPx, timeStart, timeEnd, budget.max, forceCoarse)
  const drawList = segIndices
    ? mergeColumnSpans(segs, timeStart, nsPerPx, segIndices)
    : reduced

  const segX = colX + 1
  const segW = colW - 2
  const bodyH = canvasH - headerH

  const labelRects = []

  if (!drawTint && !drawOutlines && !isHighlighted && !hlSeg) {
    let count = 0
    if (gpuBatch) {
      for (const seg of drawList) {
        if (count >= budget.max) break
        const y1raw = (seg.start - timeStart) * pxPerNs
        const y2raw = (seg.end   - timeStart) * pxPerNs
        if (y2raw < -2 || y1raw > bodyH + 2) continue
        const y1 = Math.max(0, y1raw)
        const y2 = Math.min(bodyH, y2raw)
        gpuBatch.addRect(segX, headerH + Math.round(y1), segW, Math.ceil(Math.max(1, y2 - y1)), baseColor, fillAlpha)
        count++
      }
    } else {
      const path = new Path2D()
      for (const seg of drawList) {
        if (count >= budget.max) break
        const y1raw = (seg.start - timeStart) * pxPerNs
        const y2raw = (seg.end   - timeStart) * pxPerNs
        if (y2raw < -2 || y1raw > bodyH + 2) continue
        const y1 = Math.max(0, y1raw)
        const y2 = Math.min(bodyH, y2raw)
        path.rect(segX, headerH + Math.round(y1), segW, Math.ceil(Math.max(1, y2 - y1)))
        count++
      }
      if (count > 0) {
        ctx.fillStyle = baseColor
        ctx.fill(path)
      }
    }
    if (count > 0) budget.n += count
    return
  }

  const paintOne = (seg) => {
    if (budgetFull(budget)) return false

    const y1raw = (seg.start - timeStart) * pxPerNs
    const y2raw = (seg.end   - timeStart) * pxPerNs
    if (y2raw < -2 || y1raw > bodyH + 2) return true
    const y1 = Math.max(0, y1raw)
    const y2 = Math.min(bodyH, y2raw)
    const h  = Math.max(1, y2 - y1)

    const isSegLocked = hlSeg && seg.start === hlSeg.start && seg.end === hlSeg.end && seg.task === hlSeg.task
    const drawY2 = headerH + Math.round(y1)
    const drawH2 = Math.ceil(h)
    const drawX2 = segX
    const drawW2 = segW
    gpuFillRect(gpuBatch, ctx, drawX2, drawY2, drawW2, drawH2, baseColor, fillAlpha)
    budget.n++

    if (drawTint && applyCoreTint) {
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

    if (drawOutlines && h >= 3) {
      if (isSegLocked) {
        ctx.strokeStyle = complementaryColor(baseColor)
        ctx.lineWidth = 2.5
      } else {
        ctx.strokeStyle = darkMode ? 'rgba(0,0,0,0.4)' : 'rgba(0,0,0,0.3)'
        ctx.lineWidth = 0.5
      }
      ctx.strokeRect(drawX2 + 0.5, drawY2 + 0.5, drawW2 - 1, drawH2 - 1)
    }

    if (drawLabels && segLabel && h >= 40) {
      labelRects.push({ topY: drawY2 + 3 })
    }
    return true
  }

  for (const seg of drawList) {
    if (!paintOne(seg)) break
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

/** Column band behind segments — opaque stripes on Canvas2D; subtle tint when WebGL draws segments. */
function paintVertColumnBand(ctx, col, headerH, canvasH, darkMode, gpuBatch, fast) {
  if (fast) return
  const cw = col.colWidth ?? COL_W
  if (gpuBatch) {
    ctx.fillStyle = darkMode ? 'rgba(255,255,255,0.02)' : 'rgba(0,0,0,0.02)'
  } else {
    ctx.fillStyle = col.colIdx % 2 === 0
      ? (darkMode ? '#252526' : '#FAFAFA')
      : (darkMode ? '#2D2D2D' : '#F5F5F5')
  }
  ctx.fillRect(col.x, headerH, cw, canvasH - headerH)
}

// ---- Column drawing functions ----------------------------------------------

function drawTaskColumn(ctx, trace, col, timeStart, timeEnd, pxPerNs, nsPerPx, highlightKey, canvasH, darkMode, hlSeg, budget, gpuBatch = null) {
  const headerH = vertHeaderBand()
  const mk = col.key
  const ld = taskLodData(trace, mk)
  const fast = budget.fast
  const forceCoarse = fast || budgetLite(budget) || nsPerPx > PAINT_LOD_COARSE
  const { segs, indices } = queryPaintIndices(
    trace, 'task', mk, ld, timeStart, timeEnd, nsPerPx,
    trace.lodTimescalePerPx, trace.lodUltraTimescalePerPx, budget.max, forceCoarse, fast,
  )

  paintVertColumnBand(ctx, col, headerH, canvasH, darkMode, gpuBatch, fast)

  paintSegmentsVertical(ctx, segs, timeStart, timeEnd, pxPerNs, nsPerPx,
    col.x, COL_W, headerH, col.color, trace, true, highlightKey, mk, darkMode, col.label, hlSeg, canvasH, budget,
    indices, gpuBatch)

  if (!fast) {
    paintPriorityBoostBandsVertical(
      ctx, trace, mk, col.x, col.colWidth ?? COL_W, headerH, canvasH,
      timeStart, timeEnd, pxPerNs, darkMode,
    )
  }
}

function drawCoreColumn(ctx, trace, col, timeStart, timeEnd, pxPerNs, nsPerPx, canvasH, darkMode, budget, skipSummarySegs = false, gpuBatch = null) {
  const headerH = vertHeaderBand()
  paintVertColumnBand(ctx, col, headerH, canvasH, darkMode, gpuBatch, budget.fast)
  if (skipSummarySegs) return

  const ld = coreLodData(trace, col.key)
  const segs = segsForPaint(ld, timeStart, timeEnd, nsPerPx, trace.lodTimescalePerPx, trace.lodUltraTimescalePerPx)

  const forceCoarse = budgetLite(budget) || nsPerPx > PAINT_LOD_COARSE
  const drawLabels = !forceCoarse && !budgetLite(budget)
  const reduced = segmentsForBudget(segs, nsPerPx, timeStart, timeEnd, budget.max, true)
  const segX = col.x + 1
  const segW = COL_W - 2
  const cx = segX + segW / 2

  const colorCache = new Map()
  const labelRects = []

  for (const seg of reduced) {
    if (budgetFull(budget)) break
    if (isCoreName(seg.task)) continue
    if (parseTaskName(seg.task).name === 'TICK') continue
    const bodyH = canvasH - headerH
    const y1raw = (seg.start - timeStart) * pxPerNs
    const y2raw = (seg.end   - timeStart) * pxPerNs
    if (y2raw < -2 || y1raw > bodyH + 2) continue
    const y1 = Math.max(0, y1raw)
    const y2 = Math.min(bodyH, y2raw)
    const h  = Math.max(1, y2 - y1)

    let color = colorCache.get(seg.task)
    if (color === undefined) {
      color = taskColor(taskMergeKey(seg.task), seg.task)
      colorCache.set(seg.task, color)
    }
    const drawY2 = headerH + Math.round(y1)
    const drawH2 = Math.ceil(h)
    gpuFillRect(gpuBatch, ctx, segX, drawY2, segW, drawH2, color)
    budget.n++

    if (drawLabels && h >= 40) {
      labelRects.push({ topY: drawY2 + 3, name: taskDisplayName(seg.task) })
    }
  }

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

function drawCoreTaskColumn(ctx, trace, col, timeStart, timeEnd, pxPerNs, nsPerPx, highlightKey, canvasH, darkMode, hlSeg, lockedTaskKey, budget, gpuBatch = null) {
  const headerH = vertHeaderBand()
  const ld = coreTaskLodData(trace, col.coreKey, col.taskKey)
  const wasmKey = `${col.coreKey}__${col.taskKey}`
  const fast = budget.fast
  const forceCoarse = fast || budgetLite(budget) || nsPerPx > PAINT_LOD_COARSE
  const { segs, indices } = queryPaintIndices(
    trace, 'core-task', wasmKey, ld, timeStart, timeEnd, nsPerPx,
    trace.lodTimescalePerPx, trace.lodUltraTimescalePerPx, budget.max, forceCoarse, fast,
  )

  paintVertColumnBand(ctx, col, headerH, canvasH, darkMode, gpuBatch, fast)

  const mk = taskMergeKey(col.taskKey)
  const dim = lockedTaskKey && mk !== lockedTaskKey
  if (dim) ctx.save()
  if (dim) ctx.globalAlpha = 45 / 255
  const fillAlpha = dim ? 45 / 255 : 1
  paintSegmentsVertical(ctx, segs, timeStart, timeEnd, pxPerNs, nsPerPx,
    col.x, COL_W, headerH, col.color, trace, false, highlightKey, mk, darkMode, col.label, hlSeg, canvasH, budget,
    indices, gpuBatch, fillAlpha)
  if (dim) ctx.restore()

  if (!fast) {
    paintPriorityBoostBandsVertical(
      ctx, trace, mk, col.x, col.colWidth ?? COL_W, headerH, canvasH,
      timeStart, timeEnd, pxPerNs, darkMode,
    )
  }
}

function drawStiColumn(ctx, trace, col, timeStart, timeEnd, pxPerNs, canvasH, darkMode) {
  const headerH = vertHeaderBand()
  const cw = col.colWidth ?? COL_W
  ctx.fillStyle = darkMode ? '#1A1A2E' : '#F0F0FF'
  ctx.fillRect(col.x, headerH, cw, canvasH - headerH)

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
    const cy = headerH + (ev.time - timeStart) * pxPerNs
    if (cy < headerH - 8 || cy > canvasH + 8) continue

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
  const headerH = vertHeaderBand()
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
  ctx.moveTo(chartLeft + 0.5, headerH)
  ctx.lineTo(chartLeft + 0.5, canvasH)
  ctx.stroke()
  ctx.beginPath()
  ctx.moveTo(chartRight + 0.5, headerH)
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
  ctx.fillText(fmtVal(valMin), chartLeft + 2, headerH + 2)
  ctx.fillText(fmtVal(valMax), chartRight - 2, headerH + 2)
  ctx.restore()

  // Clip drawing to the timeline area so lines don't bleed into the header
  ctx.save()
  ctx.beginPath()
  ctx.rect(col.x, headerH, colW, canvasH - headerH)
  ctx.clip()

  ctx.strokeStyle = darkMode ? '#5BC8FF' : '#0070CC'
  ctx.lineWidth = 1.5
  ctx.lineJoin = 'round'

  // Build polyline connecting events with straight lines.
  // When the first event in 'slice' has a predecessor above the viewport,
  // interpolate the line back to y=headerH so there is no gap at the top.
  ctx.beginPath()
  let firstPoint = true
  for (let i = 0; i < slice.length; i++) {
    const ev  = slice[i]
    const val = evVal(ev)
    if (isNaN(val)) continue

    const cy = headerH + (ev.time - timeStart) * pxPerNs
    const cx = valToX(val)

    if (firstPoint) {
      if (lo > 0) {
        // There is an off-screen event above the viewport — interpolate to y=headerH
        const prevEv  = evs[lo - 1]
        const prevVal = evVal(prevEv)
        if (!isNaN(prevVal)) {
          const prevCy = headerH + (prevEv.time - timeStart) * pxPerNs
          const prevCx = valToX(prevVal)
          const t       = prevCy === cy ? 0 : (headerH - prevCy) / (cy - prevCy)
          const startCx = prevCx + t * (cx - prevCx)
          ctx.moveTo(startCx, headerH)
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
    const cy = headerH + (ev.time - timeStart) * pxPerNs
    if (cy < headerH - 4 || cy > canvasH + 4) continue
    ctx.beginPath()
    ctx.arc(cx, cy, 2.5, 0, Math.PI * 2)
    ctx.fill()
  }

  ctx.restore()
}

// ---- Cursors (vertical mode – horizontal lines) ----------------------------

export function drawCursorsVertical(ctx, cursors, trace, timeStart, pxPerNs, canvasW, canvasH, headerH, _darkMode) {
  if (!cursors || cursors.length === 0 || !trace) return
  const sorted = cursorSortedPlaced(cursors)
  if (!sorted.length) return

  ctx.save()

  for (let order = 0; order < sorted.length; order++) {
    const { t, slotIndex } = sorted[order]
    const y = Math.round(headerH + (t - timeStart) * pxPerNs)
    if (y < headerH - 2 || y > canvasH + 2) continue

    ctx.font = 'bold 10px monospace'
    ctx.textBaseline = 'middle'
    ctx.textAlign = 'left'

    const color = CURSOR_COLORS[slotIndex % CURSOR_COLORS.length]
    ctx.strokeStyle = color
    ctx.lineWidth = 1.5
    ctx.setLineDash([4, 3])
    ctx.beginPath()
    ctx.moveTo(0, y + 0.5)
    ctx.lineTo(canvasW, y + 0.5)
    ctx.stroke()
    ctx.setLineDash([])

    const label = `C${slotIndex + 1}: ${formatTime(t, trace.timeScale, 3)}`
    const pad = 4
    const th = 14
    const tw = ctx.measureText(label).width + pad * 2
    const ty = Math.min(y + 2, canvasH - th - 2)
    ctx.fillStyle = color
    ctx.fillRect(2, ty, tw, th)
    ctx.fillStyle = '#000'
    ctx.fillText(label, 2 + pad, ty + th / 2)

    if (order > 0) {
      const prevT = sorted[order - 1].t
      const delta = Math.abs(t - prevT)
      const dStr = `Δ ${formatTime(delta, trace.timeScale, 3)}`
      const midY = headerH + ((t + prevT) / 2 - timeStart) * pxPerNs
      if (midY >= headerH && midY <= canvasH) {
        _drawCursorDeltaBadgeV(ctx, dStr, midY, color, canvasH, headerH)
      }
    }
  }
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
    showGrid     = true,
    darkMode     = true,
    hoverTime    = null,
    marks        = [],
    showSti      = true,
    stiExpanded  = new Set(),
    migratedOnlyFilter = false,
    lockedTaskKey = null,
    fastPaint   = false,
  } = options
  const highlightSegment = options.highlightSegment ?? null
  const taskFilterText = options.taskFilterText || ''
  const skipCoreSummarySegs = coreViewTaskFilterActive(migratedOnlyFilter, options.taskFilterKeys, taskFilterText)
  const gpuBatch = options.gpuBatch ?? null
  const useGpu = !!gpuBatch
  const headerH = options.labelHeaderH ?? HEADER_H
  const prevBand = vertHeaderBand()
  setVertHeaderBand(headerH)

  const timeSpan = timeEnd - timeStart
  if (timeSpan <= 0 || canvasH <= headerH) {
    setVertHeaderBand(prevBand)
    return
  }

  const bodyH   = canvasH - headerH
  const pxPerNs = bodyH / timeSpan
  const nsPerPx = timeSpan / bodyH
  const paintFast = !!fastPaint

  try {
  // Clear — body background is on the WebGL layer when gpuBatch is set.
  ctx.clearRect(0, 0, canvasW, canvasH)

  if (!useGpu) {
    ctx.fillStyle = darkMode ? '#1E1E1E' : '#FFFFFF'
    ctx.fillRect(0, 0, canvasW, canvasH)
  }

  // Ruler background (left strip)
  ctx.fillStyle = darkMode ? '#2B2B2B' : '#E8E8E8'
  ctx.fillRect(0, 0, RULER_W, canvasH)

  // Header background (top strip, right of ruler) — labels drawn by DOM overlay when skipColumnHeaders
  ctx.fillStyle = darkMode ? '#1E1E1E' : '#F5F5F5'
  ctx.fillRect(RULER_W, 0, canvasW - RULER_W, headerH)

  // Build column layout
  const colLayoutBase = options.columnLayout
  const { cols } = colLayoutBase
    ? offsetColumnLayout(colLayoutBase, scrollX)
    : buildColumnLayout(trace, viewMode, expanded, scrollX, showSti, stiExpanded, migratedOnlyFilter, options.taskFilterKeys || null, taskFilterText)

  // Grid lines (horizontal, optional)
  if (showGrid && !paintFast) {
    const step = niceStep(timeSpan)
    const startSnap = Math.ceil(timeStart / step) * step
    ctx.strokeStyle = darkMode ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)'
    ctx.lineWidth = 1
    for (let t = startSnap; t <= timeEnd; t += step) {
      const y = headerH + (t - timeStart) * pxPerNs
      ctx.beginPath()
      ctx.moveTo(RULER_W, Math.round(y) + 0.5)
      ctx.lineTo(canvasW, Math.round(y) + 0.5)
      ctx.stroke()
    }
  }

  // Vertical ruler (left side)
  drawVerticalRuler(ctx, trace, timeStart, timeEnd, pxPerNs, canvasH, headerH, RULER_W, darkMode, paintFast)

  // Clip to column body area (right of ruler, below header)
  ctx.save()
  ctx.beginPath()
  ctx.rect(RULER_W, headerH, canvasW - RULER_W, bodyH + 1)
  ctx.clip()

  let visibleColCount = 0
  for (const col of cols) {
    const cw = col.colWidth ?? COL_W
    if (col.x + cw >= RULER_W && col.x < canvasW) visibleColCount++
  }
  visibleColCount = Math.max(1, visibleColCount)

  const colBudgetSpec = createPaintBudget(visibleColCount, paintFast, useGpu)
  for (const col of cols) {
    const cw = col.colWidth ?? COL_W
    if (col.x + cw < RULER_W || col.x >= canvasW) continue
    const colBudget = { n: 0, max: colBudgetSpec.max, fast: colBudgetSpec.fast }
    if (col.type === 'task') {
      drawTaskColumn(ctx, trace, col, timeStart, timeEnd, pxPerNs, nsPerPx, highlightKey, canvasH, darkMode, highlightSegment, colBudget, gpuBatch)
    } else if (col.type === 'core') {
      drawCoreColumn(ctx, trace, col, timeStart, timeEnd, pxPerNs, nsPerPx, canvasH, darkMode, colBudget, skipCoreSummarySegs, gpuBatch)
    } else if (col.type === 'core-task') {
      drawCoreTaskColumn(ctx, trace, col, timeStart, timeEnd, pxPerNs, nsPerPx, highlightKey, canvasH, darkMode, highlightSegment, lockedTaskKey, colBudget, gpuBatch)
    } else if (col.type === 'sti') {
      drawStiColumn(ctx, trace, col, timeStart, timeEnd, pxPerNs, canvasH, darkMode)
    } else if (col.type === 'interval') {
      drawIntervalColumn(ctx, trace, col, timeStart, timeEnd, pxPerNs, canvasH, darkMode, options.highlightInterval ?? null)
    }
  }
  ctx.restore()

  // ---- Locked segment enlarged pass (unclipped, draws over column gap) ----
  if (!paintFast) {
    drawLockedSegmentVert(ctx, trace, cols, highlightSegment, timeStart, timeEnd, pxPerNs, nsPerPx, headerH, canvasH, darkMode)
  }
  // Marks, cursors, hover — overlay canvas (TimelinePanel).

  // Column headers (DOM ColumnHeaderRow in TimelinePanel; canvas fallback for export)
  if (!options.skipColumnHeaders) {
    ctx.save()
    ctx.beginPath()
    ctx.rect(RULER_W, 0, canvasW - RULER_W, headerH)
    ctx.clip()
    drawColumnHeaders(ctx, cols, headerH, COL_W, highlightKey, darkMode)
    ctx.restore()
  }

  // Corner: covers ruler+header intersection
  ctx.fillStyle = darkMode ? '#1A1A1A' : '#E0E0E0'
  ctx.fillRect(0, 0, RULER_W, headerH)
  ctx.strokeStyle = darkMode ? '#3C3C3C' : '#CCCCCC'
  ctx.lineWidth = 1
  ctx.strokeRect(0.5, 0.5, RULER_W - 1, headerH - 1)

  } finally {
    setVertHeaderBand(prevBand)
  }
}

// ---- Hit-test (vertical mode) -----------------------------------------------

/**
 * Find the nearest STI event near (cx, cy) in vertical mode.
 * Time is on Y axis; columns are on X axis.
 */
export function hitTestStiVertical(trace, viewport, options, cx, cy, radius = 8) {
  const { timeStart, timeEnd, scrollX = 0, canvasH } = viewport
  const { viewMode = 'task', expanded = new Set(), showSti = true, stiExpanded = new Set(), migratedOnlyFilter = false } = options
  const headerH = options.vertHeaderH ?? HEADER_H
  if (!showSti || cy < headerH) return null
  const pxPerNs = (canvasH - headerH) / (timeEnd - timeStart)
  const tAtCy = timeStart + (cy - headerH) / pxPerNs

  const cols = resolveCols(trace, options, viewMode, expanded, showSti, stiExpanded, migratedOnlyFilter)
  for (const col of cols) {
    if (col.type !== 'sti') continue
    const cw = col.colWidth ?? COL_W
    const colCx = col.x - scrollX + cw / 2
    if (Math.abs(cx - colCx) > cw) continue

    const evs    = trace.stiEventsByTarget.get(col.key) || []
    const starts = trace.stiStartsByTarget.get(col.key) || []
    const lo = Math.max(0, bisectLeft(starts, tAtCy - radius / pxPerNs) - 1)
    const hi = bisectRight(starts, tAtCy + radius / pxPerNs) + 1

    let best = null, bestDist = radius + 1
    for (let i = lo; i < Math.min(hi, evs.length); i++) {
      const ev = evs[i]
      const ey = headerH + (ev.time - timeStart) * pxPerNs
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
  const { viewMode = 'task', expanded = new Set(), showSti = true, stiExpanded = new Set(), migratedOnlyFilter = false } = options
  if (cx < RULER_W) return null
  const cols = resolveCols(trace, options, viewMode, expanded, showSti, stiExpanded, migratedOnlyFilter)
  for (const col of cols) {
    const x = col.x - scrollX
    const cw = col.colWidth ?? COL_W
    if (cx >= x && cx < x + cw) return col
  }
  return null
}

