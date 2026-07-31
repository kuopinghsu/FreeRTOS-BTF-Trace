<template>
  <div
    class="heatmap-overlay"
    @click.self="emit('close')"
  >
    <div
      class="heatmap-dialog"
      role="dialog"
      aria-modal="true"
      aria-label="Migration heatmap"
    >
      <div class="heatmap-header">
        <button
          v-if="drillLevel > 0"
          type="button"
          class="heatmap-back"
          @click="goBack"
        >
          ← Back
        </button>
        <span class="heatmap-title">Migration Heatmap</span>
        <button
          type="button"
          class="heatmap-close"
          @click="emit('close')"
        >
          Close
        </button>
      </div>
      <p class="heatmap-sub">
        {{ subtitle }}
      </p>
      <div
        v-if="traceHasBounces && drillLevel === 0"
        class="heatmap-bounce-bar"
      >
        <button
          type="button"
          class="heatmap-bounce-toggle"
          :class="{ active: bounceOnly }"
          :title="bounceOnly ? 'Showing only migrations that occurred while a mutex was held across cores' : 'Showing all migrations'"
          @click="bounceOnly = !bounceOnly"
        >
          {{ bounceOnly ? 'Show: Lock-Bounce Only' : 'Show: All Migrations' }}
        </button>
      </div>
      <div
        v-if="!hasData"
        class="heatmap-empty"
      >
        {{ emptyText }}
      </div>
      <div
        v-else
        ref="viewportRef"
        class="heatmap-viewport"
      >
        <div
          ref="scrollRef"
          class="heatmap-scroll"
          @scroll="scheduleDraw"
        >
          <div
            class="heatmap-spacer"
            :style="spacerStyle"
          />
        </div>
        <canvas
          ref="canvasRef"
          class="heatmap-canvas"
          @click="onCanvasClick"
          @mousemove="onCanvasMove"
          @mouseleave="hoverCell = null; hoverRow = null"
          @wheel.prevent="onCanvasWheel"
        />
      </div>
      <p
        v-if="hoverTitle"
        class="heatmap-cell-tip"
      >
        {{ hoverTitle }}
      </p>
      <p class="heatmap-hint">
        {{ hintText }}
      </p>
      <div
        v-if="hasData"
        class="heatmap-export-row"
      >
        <button
          type="button"
          class="heatmap-export-btn"
          @click="exportHeatmapPng"
        >
          Export PNG
        </button>
        <button
          type="button"
          class="heatmap-export-btn"
          @click="exportHeatmapSvg"
        >
          Export SVG
        </button>
      </div>
      <div
        v-if="taskFilterActive"
        class="heatmap-filter-bar"
      >
        <span>
          Showing {{ taskFilterCount }} task{{ taskFilterCount === 1 ? '' : 's' }}: {{ taskFilterLabel || 'filtered' }}
        </span>
        <button
          type="button"
          class="heatmap-show-all"
          @click="onShowAll"
        >
          Show all tasks
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { formatTime } from '../renderer/TimelineRenderer.js'
import {
  coreShortName,
  migrationHeatmapGrid,
  migrationHeatmapMatrix,
  migrationHeatmapUsesMatrix,
  migrationCoreOutgoingHeatmap,
  migrationTaskHeatmapGrid,
  heatmapBinRange,
  traceHasCoreBounceHolds,
} from '../utils/migrationAnalysis.js'
import { getPlacedCursors, getStatsRange } from '../utils/statsRange.js'

const ROW_H = 16
const CELL_MIN_W = 8
const MATRIX_CELL_MIN_W = 8
const LEFT_PAD = 6
const LABEL_MIN_W = 52
const COL_HEADER_H = 40
const MATRIX_HEADER_FONT = '9px monospace'
const MATRIX_HEADER_LABEL_PITCH = 12

const props = defineProps({
  trace:   { type: Object, required: true },
  cursors: { type: Array, default: () => [] },
  taskFilterActive: { type: Boolean, default: false },
  taskFilterLabel:  { type: String, default: null },
  taskFilterCount:  { type: Number, default: 0 },
})

const emit = defineEmits(['close', 'drillDown', 'clearFilter'])

const drillLevel = ref(0)
const drillCtx = ref(null)
const bounceOnly = ref(false)
const scrollRef = ref(null)
const viewportRef = ref(null)
const canvasRef = ref(null)
const hoverCell = ref(null)
const hoverRow = ref(null)
const overviewScopeCache = new Map()
let _drawRaf = 0
let _scrollResizeObserver = null

function overviewScopeKey(lo, hi) {
  return `${lo ?? ''}:${hi ?? ''}`
}

watch(() => props.taskFilterActive, (active) => {
  if (!active) goLevel0()
})

watch(() => props.trace, (t) => {
  overviewScopeCache.clear()
  bounceOnly.value = false
  if (t) t._lockBounceNs = undefined
})

const statsRange = computed(() => {
  const placed = getPlacedCursors(props.cursors)
  if (placed.length < 2) return null
  return getStatsRange(props.cursors, true)
})

const scopeSuffix = computed(() => {
  const r = statsRange.value
  if (!r) return ''
  return ` (C1–C${r.nCursors}: ${formatTime(r.lo, props.trace.timeScale)} … ${formatTime(r.hi, props.trace.timeScale)})`
})

const traceHasBounces = computed(() => traceHasCoreBounceHolds(props.trace))

const usesMatrixOverview = computed(() => migrationHeatmapUsesMatrix(props.trace))

const taskDrillLevel = computed(() => (usesMatrixOverview.value ? 2 : 1))

const scopeLoHi = computed(() => {
  const r = statsRange.value
  return { lo: r?.lo ?? null, hi: r?.hi ?? null }
})

const matrixHeatmap = computed(() => {
  const { lo, hi } = scopeLoHi.value
  const key = `matrix:${overviewScopeKey(lo, hi)}:b=${bounceOnly.value}`
  const cached = overviewScopeCache.get(key)
  if (cached) return cached
  const hm = migrationHeatmapMatrix(props.trace, lo, hi, bounceOnly.value)
  overviewScopeCache.set(key, hm)
  return hm
})

const overviewHeatmap = computed(() => {
  const { lo, hi } = scopeLoHi.value
  const key = `pairs:${overviewScopeKey(lo, hi)}:b=${bounceOnly.value}`
  const cached = overviewScopeCache.get(key)
  if (cached) return cached
  const hm = migrationHeatmapGrid(props.trace, lo, hi, 32, bounceOnly.value)
  overviewScopeCache.set(key, hm)
  return hm
})

const coreOutgoingHeatmap = computed(() => {
  const ctx = drillCtx.value
  if (!ctx?.fromCore) {
    return { pairs: [], grid: [], timeBins: 32, tMin: 0, tMax: 0, binW: 0 }
  }
  const { lo, hi } = scopeLoHi.value
  return migrationCoreOutgoingHeatmap(props.trace, ctx.fromCore, lo, hi, 32, bounceOnly.value)
})

const taskHeatmap = computed(() => {
  const ctx = drillCtx.value
  if (!ctx) return { rows: [], timeBins: 32, tMin: 0, tMax: 0, binW: 0 }
  const { lo, hi } = scopeLoHi.value
  return migrationTaskHeatmapGrid(
    props.trace,
    ctx.fromCore,
    ctx.toCore,
    ctx.binLo,
    ctx.binHi,
    ctx.parentTimeBins ?? 32,
    ctx.parentBinIndex ?? 0,
    ctx.parentTimeBins ?? 32,
    lo,
    hi,
  )
})

const isMatrixLevel = computed(() =>
  usesMatrixOverview.value && drillLevel.value === 0)

const isOutgoingLevel = computed(() =>
  usesMatrixOverview.value && drillLevel.value === 1)

const activeGrid = computed(() => {
  if (isMatrixLevel.value) return null
  if (isOutgoingLevel.value) return coreOutgoingHeatmap.value
  if (drillLevel.value >= taskDrillLevel.value) return taskHeatmap.value
  return overviewHeatmap.value
})

const displayRows = computed(() => {
  if (isMatrixLevel.value) {
    const hm = matrixHeatmap.value
    return hm.cores.map((fromCore, i) => ({
      key: fromCore,
      label: coreShortName(fromCore),
      fromCore,
      toCores: hm.cores,
      grid: hm.grid[i],
    }))
  }
  if (isOutgoingLevel.value) {
    const hm = coreOutgoingHeatmap.value
    return hm.pairs.map((p, i) => ({
      key: `${p.from}→${p.to}`,
      label: p.label,
      fromCore: p.from,
      toCore: p.to,
      pairLabel: p.label,
      grid: hm.grid[i] || [],
    }))
  }
  if (drillLevel.value >= taskDrillLevel.value) {
    return taskHeatmap.value.rows.map(r => ({
      key: r.mk,
      label: r.label,
      mk: r.mk,
      grid: r.grid,
    }))
  }
  const hm = overviewHeatmap.value
  return hm.pairs.map((p, i) => ({
    key: `${p.from}→${p.to}`,
    label: p.label,
    fromCore: p.from,
    toCore: p.to,
    pairLabel: p.label,
    grid: hm.grid[i],
  }))
})

const columnCount = computed(() => {
  if (isMatrixLevel.value) return matrixHeatmap.value.cores.length
  const hm = activeGrid.value
  return hm?.timeBins || displayRows.value[0]?.grid?.length || 1
})

const heatMax = computed(() => {
  let m = 0
  for (const row of displayRows.value) {
    for (const v of row.grid) if (v > m) m = v
  }
  return m
})

const labelWidth = computed(() => {
  let max = LABEL_MIN_W
  for (const row of displayRows.value) {
    max = Math.max(max, row.label.length * 7 + 10)
  }
  if (isMatrixLevel.value) {
    for (const c of matrixHeatmap.value.cores) {
      max = Math.max(max, coreShortName(c).length * 7 + 10)
    }
  }
  return max
})

const rowLabelRight = computed(() => LEFT_PAD + labelWidth.value)

const layout = computed(() => {
  const nBins = columnCount.value || 1
  const rowCount = displayRows.value.length
  const viewW = scrollRef.value?.clientWidth || viewportRef.value?.clientWidth || 480
  const minCellW = isMatrixLevel.value ? MATRIX_CELL_MIN_W : CELL_MIN_W
  const cellW = isMatrixLevel.value
    ? minCellW
    : Math.max(minCellW, (viewW - LEFT_PAD - labelWidth.value - 4) / nBins)
  const contentW = LEFT_PAD + labelWidth.value + nBins * cellW + 8
  const headerH = isMatrixLevel.value ? COL_HEADER_H : 0
  const contentH = Math.max(60, headerH + rowCount * ROW_H + 8)
  return {
    nBins,
    rowCount,
    cellW,
    contentW,
    contentH,
    headerH,
    x0: LEFT_PAD + labelWidth.value,
  }
})

const spacerStyle = computed(() => ({
  width: `${layout.value.contentW}px`,
  height: `${layout.value.contentH}px`,
}))

const hasData = computed(() => {
  if (!displayRows.value.length) return false
  if (isMatrixLevel.value) {
    return displayRows.value.some(row => row.grid.some((v, bi) => v > 0 && row.fromCore !== row.toCores[bi]))
  }
  return displayRows.value.some(row => row.grid.some(v => v > 0))
})

const subtitle = computed(() => {
  if (isMatrixLevel.value) {
    const n = matrixHeatmap.value.cores.length
    return `Core × core migration counts (${n} cores, row = from, column = to)${scopeSuffix.value}`
  }
  if (isOutgoingLevel.value) {
    const ctx = drillCtx.value
    const src = ctx?.fromCore ? coreShortName(ctx.fromCore) : '?'
    return `Outgoing migrations from ${src} · rows = destination cores · columns = time bins${scopeSuffix.value}`
  }
  if (drillLevel.value >= taskDrillLevel.value) {
    const ctx = drillCtx.value
    const scale = props.trace.timeScale
    return `Tasks · ${ctx.pairLabel} · ${formatTime(ctx.binLo, scale)} … ${formatTime(ctx.binHi, scale)}`
  }
  return `Core-pair migrations over time bins${scopeSuffix.value}`
})

const emptyText = computed(() => {
  if (isMatrixLevel.value || drillLevel.value === 0) return 'No migrations in scope.'
  return 'No task migrations in this cell.'
})

const hintText = computed(() => {
  if (isMatrixLevel.value) {
    return 'Rows: source (from) core · Columns: destination (to) core · Hover a row to highlight · Click a row for outgoing pairs'
  }
  if (isOutgoingLevel.value) {
    return 'Rows: outgoing core pairs · Columns: time bins · Hover a row to highlight · Click a cell to drill into tasks'
  }
  if (drillLevel.value >= taskDrillLevel.value) {
    return 'Rows: tasks · Columns: sub-bins · Click a cell to zoom and filter in Task View'
  }
  return 'Rows: from→to core pairs · Columns: time bins · Click a cell to drill into tasks'
})

const hoverTitle = computed(() => {
  const hit = hoverCell.value
  const ri = hit?.ri ?? hoverRow.value
  if (ri == null) return ''
  const row = displayRows.value[ri]
  if (!row) return ''
  if (hit) {
    const count = row.grid[hit.bi] || 0
    return cellTitle(hit.ri, hit.bi, count, row)
  }
  if (isMatrixLevel.value) {
    const total = row.grid.reduce((sum, v, bi) => (
      row.fromCore === row.toCores?.[bi] ? sum : sum + v
    ), 0)
    return `${row.label} · ${total} migration(s) · Click row for outgoing pairs`
  }
  const total = row.grid.reduce((sum, v) => sum + v, 0)
  return `${row.label} · ${total} migration(s) in scope`
})

function scheduleDraw() {
  if (_drawRaf) return
  _drawRaf = requestAnimationFrame(() => {
    _drawRaf = 0
    drawHeatmap()
  })
}

function cellTitle(ri, bi, count, row) {
  const scale = props.trace.timeScale
  if (isMatrixLevel.value) {
    const toCore = row.toCores[bi]
    const pairLabel = `${coreShortName(row.fromCore)}→${coreShortName(toCore)}`
    return `${pairLabel} · ${count} migration(s)`
  }
  const hm = activeGrid.value
  const { binLo, binHi } = heatmapBinRange(
    hm.tMin,
    hm.binW,
    hm.timeBins,
    hm.tMax,
    bi,
  )
  if (drillLevel.value >= taskDrillLevel.value) {
    return `${row.label} · ${formatTime(binLo, scale)}–${formatTime(binHi, scale)} · ${count} migration(s) · Click to drill down`
  }
  return `${row.pairLabel} · ${formatTime(binLo, scale)}–${formatTime(binHi, scale)} · ${count} migration(s) · Click to drill into tasks`
}

function rowTopY(ri, scrollTop, headerH) {
  return headerH + 4 + ri * ROW_H - scrollTop
}

function matrixColLabelStep(cellW) {
  return Math.max(1, Math.ceil(MATRIX_HEADER_LABEL_PITCH / Math.max(cellW, 1)))
}

function drawMatrixColumnHeaders(ctx, cols, nBins, cellW, x0, scrollLeft, scrollTop, viewW, viewH, labelColor, labelRight, labelBg) {
  if (scrollTop > COL_HEADER_H) return

  const step = matrixColLabelStep(cellW)
  const biStart = Math.max(0, Math.floor((scrollLeft - x0) / cellW))
  const biEnd = Math.min(nBins, Math.ceil((scrollLeft + viewW - x0) / cellW) + 1)

  const axisY = COL_HEADER_H - 3 - scrollTop
  if (axisY >= -4 && axisY <= viewH) {
    ctx.fillStyle = labelBg
    ctx.fillRect(0, 0, labelRight, COL_HEADER_H - scrollTop)
    ctx.font = MATRIX_HEADER_FONT
    ctx.fillStyle = labelColor
    ctx.textAlign = 'right'
    ctx.textBaseline = 'middle'
    ctx.fillText('to→', labelRight - 4, axisY)
  }

  ctx.font = MATRIX_HEADER_FONT
  ctx.fillStyle = labelColor
  ctx.textAlign = 'left'
  ctx.textBaseline = 'bottom'

  for (let bi = biStart; bi < biEnd; bi++) {
    if (bi % step !== 0) continue
    const hx = x0 + bi * cellW - scrollLeft
    if (hx + cellW <= labelRight) continue
    if (hx + cellW < 0 || hx > viewW) continue
    const cx = hx + (cellW * step) / 2
    const cy = COL_HEADER_H - 4 - scrollTop
    if (cy < -20 || cy > viewH) continue

    ctx.save()
    ctx.translate(cx, cy)
    ctx.rotate(-Math.PI / 2)
    ctx.fillText(coreShortName(cols[bi]), 0, 0)
    ctx.restore()
  }
}

function drawHeatmap() {
  const canvas = canvasRef.value
  const scrollEl = scrollRef.value
  const rows = displayRows.value
  if (!canvas || !scrollEl || !rows.length) return

  const viewW = scrollEl.clientWidth
  const viewH = scrollEl.clientHeight
  if (viewW < 1 || viewH < 1) return

  const dpr = window.devicePixelRatio || 1
  canvas.width = Math.max(1, Math.floor(viewW * dpr))
  canvas.height = Math.max(1, Math.floor(viewH * dpr))
  canvas.style.width = `${viewW}px`
  canvas.style.height = `${viewH}px`

  const ctx = canvas.getContext('2d')
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  paintHeatmap(ctx, {
    viewW,
    viewH,
    scrollLeft: scrollEl.scrollLeft,
    scrollTop: scrollEl.scrollTop,
    showHover: true,
  })
}

function paintHeatmap(ctx, {
  viewW,
  viewH,
  scrollLeft = 0,
  scrollTop = 0,
  showHover = false,
  fullExport = false,
} = {}) {
  const rows = displayRows.value
  if (!ctx || !rows.length) return

  const { nBins, rowCount, cellW, x0, headerH } = layout.value
  ctx.clearRect(0, 0, viewW, viewH)

  const maxVal = heatMax.value
  const scrollEl = scrollRef.value
  const labelColor = scrollEl
    ? getComputedStyle(scrollEl).getPropertyValue('--fg-dim').trim() || '#888888'
    : '#888888'
  const labelBg = scrollEl
    ? getComputedStyle(scrollEl).getPropertyValue('--bg').trim() || '#1e1e1e'
    : '#1e1e1e'
  const labelRight = rowLabelRight.value

  ctx.font = '11px monospace'
  ctx.textBaseline = 'middle'

  if (isMatrixLevel.value) {
    drawMatrixColumnHeaders(
      ctx,
      matrixHeatmap.value.cores,
      nBins,
      cellW,
      x0,
      scrollLeft,
      scrollTop,
      viewW,
      viewH,
      labelColor,
      labelRight,
      labelBg,
    )
  }

  const riStart = fullExport ? 0 : Math.max(0, Math.floor((scrollTop - headerH - 4) / ROW_H))
  const riEnd = fullExport ? rowCount : Math.min(rowCount, Math.ceil((scrollTop + viewH - headerH - 4) / ROW_H) + 1)

  for (let ri = riStart; ri < riEnd; ri++) {
    const row = rows[ri]
    const y = rowTopY(ri, scrollTop, headerH)
    if (!fullExport && (y + ROW_H < 0 || y > viewH)) continue

    ctx.fillStyle = labelBg
    ctx.fillRect(0, y, labelRight, ROW_H - 1)

    ctx.fillStyle = labelColor
    ctx.textAlign = 'left'
    ctx.fillText(row.label, LEFT_PAD, y + ROW_H * 0.45)

    let x = x0 - scrollLeft
    for (let bi = 0; bi < nBins; bi++) {
      const v = row.grid[bi] || 0
      const isDiag = isMatrixLevel.value && row.fromCore === row.toCores?.[bi]
      const cellRight = x + cellW
      if (cellRight > labelRight && x < viewW && x + cellW > 0) {
        if (isDiag) {
          ctx.fillStyle = 'rgba(91, 155, 213, 0.03)'
        } else {
          const alpha = maxVal && v ? 0.2 + 0.7 * (v / maxVal) : 0.3
          ctx.fillStyle = v
            ? `rgba(91, 155, 213, ${alpha})`
            : 'rgba(91, 155, 213, 0.06)'
        }
        ctx.fillRect(x, y, Math.max(1, cellW - 1), ROW_H - 3)
      }
      x += cellW
    }

    if (showHover && hoverRow.value === ri) {
      ctx.fillStyle = 'rgba(91, 155, 213, 0.18)'
      ctx.fillRect(0, y, Math.min(labelRight, viewW), ROW_H - 1)
      const cellsX = x0 - scrollLeft
      const cellsW = nBins * cellW
      const cellLeft = Math.max(cellsX, labelRight)
      const cellRight = cellsX + cellsW
      const drawW = Math.min(cellRight, viewW) - cellLeft
      if (drawW > 0) {
        ctx.fillRect(cellLeft, y, drawW, ROW_H - 1)
      }
    }
  }
}

function _xmlEsc(v) {
  return String(v ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function _exportStamp() {
  const d = new Date()
  const pad = n => String(n).padStart(2, '0')
  return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`
}

function _exportBaseName() {
  const level = isMatrixLevel.value
    ? 'matrix'
    : isOutgoingLevel.value
      ? 'outgoing'
      : drillLevel.value >= taskDrillLevel.value
        ? 'tasks'
        : 'pairs'
  return `migration-heatmap-${level}-${_exportStamp()}`
}

function _downloadBlob(filename, blob) {
  if (!blob) return
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

function _downloadText(filename, text, mime) {
  const blob = new Blob([text], { type: mime })
  _downloadBlob(filename, blob)
}

function exportHeatmapPng() {
  if (!hasData.value) return
  const { contentW, contentH } = layout.value
  if (contentW < 1 || contentH < 1) return
  const canvas = document.createElement('canvas')
  const dpr = Math.max(1, window.devicePixelRatio || 1)
  canvas.width = Math.max(1, Math.floor(contentW * dpr))
  canvas.height = Math.max(1, Math.floor(contentH * dpr))
  const ctx = canvas.getContext('2d')
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  paintHeatmap(ctx, {
    viewW: contentW,
    viewH: contentH,
    scrollLeft: 0,
    scrollTop: 0,
    showHover: false,
    fullExport: true,
  })
  canvas.toBlob(blob => {
    if (!blob) return
    _downloadBlob(`${_exportBaseName()}.png`, blob)
  }, 'image/png')
}

function exportHeatmapSvg() {
  if (!hasData.value) return
  const { contentW, contentH, nBins, rowCount, cellW, x0, headerH } = layout.value
  const rows = displayRows.value
  const maxVal = heatMax.value
  const labelRight = rowLabelRight.value
  const bg = scrollRef.value
    ? getComputedStyle(scrollRef.value).getPropertyValue('--bg').trim() || '#1e1e1e'
    : '#1e1e1e'
  const labelColor = scrollRef.value
    ? getComputedStyle(scrollRef.value).getPropertyValue('--fg-dim').trim() || '#888888'
    : '#888888'

  const parts = [
    `<svg xmlns="http://www.w3.org/2000/svg" width="${contentW}" height="${contentH}" viewBox="0 0 ${contentW} ${contentH}">`,
    `<title>${_xmlEsc(subtitle.value)}</title>`,
    `<rect width="100%" height="100%" fill="${_xmlEsc(bg)}"/>`,
  ]

  if (isMatrixLevel.value) {
    const step = matrixColLabelStep(cellW)
    parts.push(`<text x="${labelRight - 4}" y="${headerH - 3}" fill="${_xmlEsc(labelColor)}" font-family="monospace" font-size="9" text-anchor="end">to→</text>`)
    for (let bi = 0; bi < nBins; bi++) {
      if (bi % step !== 0) continue
      const hx = x0 + bi * cellW
      if (hx + cellW <= labelRight) continue
      const cx = hx + (cellW * step) / 2
      const cy = headerH - 4
      const lbl = coreShortName(matrixHeatmap.value.cores[bi])
      parts.push(
        `<text x="${cx}" y="${cy}" fill="${_xmlEsc(labelColor)}" font-family="monospace" font-size="9" text-anchor="start" transform="rotate(-90 ${cx} ${cy})">${_xmlEsc(lbl)}</text>`,
      )
    }
  }

  for (let ri = 0; ri < rowCount; ri++) {
    const row = rows[ri]
    const y = rowTopY(ri, 0, headerH)
    parts.push(`<rect x="0" y="${y}" width="${labelRight}" height="${ROW_H - 1}" fill="${_xmlEsc(bg)}"/>`)
    parts.push(`<text x="${LEFT_PAD}" y="${y + ROW_H * 0.45}" fill="${_xmlEsc(labelColor)}" font-family="monospace" font-size="11" dominant-baseline="middle">${_xmlEsc(row.label)}</text>`)
    let x = x0
    for (let bi = 0; bi < nBins; bi++) {
      const v = row.grid[bi] || 0
      const isDiag = isMatrixLevel.value && row.fromCore === row.toCores?.[bi]
      if (x + cellW > labelRight) {
        if (isDiag) {
          parts.push(`<rect x="${x}" y="${y}" width="${Math.max(1, cellW - 1)}" height="${ROW_H - 3}" fill="#5B9BD5" fill-opacity="0.03"/>`)
        } else {
          const opacity = maxVal && v ? 0.2 + 0.7 * (v / maxVal) : (v ? 0.3 : 0.06)
          parts.push(`<rect x="${x}" y="${y}" width="${Math.max(1, cellW - 1)}" height="${ROW_H - 3}" fill="#5B9BD5" fill-opacity="${opacity.toFixed(3)}"/>`)
        }
      }
      x += cellW
    }
  }

  parts.push('</svg>')
  _downloadText(`${_exportBaseName()}.svg`, parts.join('\n'), 'image/svg+xml;charset=utf-8')
}

function hitTestRow(clientX, clientY) {
  const canvas = canvasRef.value
  const scrollEl = scrollRef.value
  if (!canvas || !scrollEl) return null

  const rect = canvas.getBoundingClientRect()
  const y = clientY - rect.top + scrollEl.scrollTop
  const { rowCount, headerH } = layout.value

  if (y < headerH + 4) return null
  const ri = Math.floor((y - headerH - 4) / ROW_H)
  if (ri < 0 || ri >= rowCount) return null
  return { ri }
}

function hitTestCanvas(clientX, clientY) {
  const canvas = canvasRef.value
  const scrollEl = scrollRef.value
  if (!canvas || !scrollEl) return null

  const rect = canvas.getBoundingClientRect()
  const x = clientX - rect.left + scrollEl.scrollLeft
  const y = clientY - rect.top + scrollEl.scrollTop
  const { nBins, rowCount, cellW, x0, headerH } = layout.value

  if (y < headerH + 4) return null
  const ri = Math.floor((y - headerH - 4) / ROW_H)
  if (ri < 0 || ri >= rowCount) return null
  if (x < x0) return null
  const bi = Math.floor((x - x0) / cellW)
  if (bi < 0 || bi >= nBins) return null
  const row = displayRows.value[ri]
  if (!row) return null
  if (isMatrixLevel.value && row.fromCore === row.toCores[bi]) return null
  const count = row.grid[bi] || 0
  if (!isMatrixLevel.value && count <= 0) return null
  return { ri, bi }
}

function onCanvasWheel(e) {
  const el = scrollRef.value
  if (!el) return
  el.scrollTop += e.deltaY
  el.scrollLeft += e.deltaX
  scheduleDraw()
}

function onCanvasMove(e) {
  const rowHit = hitTestRow(e.clientX, e.clientY)
  hoverRow.value = rowHit?.ri ?? null
  const hit = hitTestCanvas(e.clientX, e.clientY)
  hoverCell.value = hit
  if (canvasRef.value) {
    const clickable = isMatrixLevel.value
      ? matrixRowHasMigrations(hoverRow.value)
      : !!hit
    canvasRef.value.style.cursor = clickable ? 'pointer' : 'default'
  }
}

function matrixRowHasMigrations(ri) {
  if (ri == null) return false
  const row = displayRows.value[ri]
  if (!row) return false
  return row.grid.some((v, bi) => v > 0 && row.fromCore !== row.toCores?.[bi])
}

function onCanvasClick(e) {
  if (isMatrixLevel.value) {
    const rowHit = hitTestRow(e.clientX, e.clientY)
    if (rowHit && matrixRowHasMigrations(rowHit.ri)) {
      onMatrixRowClick(rowHit.ri)
      return
    }
  }
  const hit = hitTestCanvas(e.clientX, e.clientY)
  if (!hit) return
  onCellClick(hit.ri, hit.bi)
}

function onMatrixRowClick(ri) {
  const row = displayRows.value[ri]
  if (!row?.fromCore) return
  drillCtx.value = {
    fromCore: row.fromCore,
    pairLabel: coreShortName(row.fromCore),
  }
  drillLevel.value = 1
  scrollHeatmapToTop()
}

function scrollHeatmapToTop() {
  nextTick(() => {
    const el = scrollRef.value
    if (el) {
      el.scrollTop = 0
      el.scrollLeft = 0
    }
    scheduleDraw()
  })
}

function goBack() {
  if (drillLevel.value <= 0) return
  drillLevel.value -= 1
  if (drillLevel.value === 0) {
    drillCtx.value = null
  } else if (drillLevel.value === 1 && usesMatrixOverview.value) {
    const { fromCore, pairLabel } = drillCtx.value || {}
    drillCtx.value = { fromCore, pairLabel }
  }
  scrollHeatmapToTop()
}

function goLevel0() {
  drillLevel.value = 0
  drillCtx.value = null
  scrollHeatmapToTop()
}

function onShowAll() {
  emit('clearFilter')
}

function onCellClick(ri, bi) {
  const row = displayRows.value[ri]
  const count = row.grid[bi]
  if (!row || count <= 0) return

  const hm = activeGrid.value
  const { binLo, binHi } = heatmapBinRange(hm.tMin, hm.binW, hm.timeBins, hm.tMax, bi)

  if (isOutgoingLevel.value) {
    drillCtx.value = {
      ...drillCtx.value,
      fromCore: row.fromCore,
      toCore: row.toCore,
      pairLabel: row.pairLabel,
      binLo,
      binHi,
      parentBinIndex: bi,
      parentTimeBins: hm.timeBins,
    }
    drillLevel.value = 2
    scrollHeatmapToTop()
    return
  }

  if (drillLevel.value === 0) {
    drillCtx.value = {
      fromCore: row.fromCore,
      toCore: row.toCore,
      pairLabel: row.pairLabel,
      binLo,
      binHi,
      parentBinIndex: bi,
      parentTimeBins: hm.timeBins,
    }
    drillLevel.value = 1
    scrollHeatmapToTop()
    return
  }

  const ctx = drillCtx.value
  emit('drillDown', {
    fromCore: ctx.fromCore,
    toCore: ctx.toCore,
    pairLabel: `${ctx.pairLabel} · ${row.label}`,
    binIndex: bi,
    binLo,
    binHi,
    mergeKeys: [row.mk],
    count,
  })
}

watch([displayRows, activeGrid, labelWidth, hoverRow], () => {
  nextTick(() => scheduleDraw())
})

watch(hasData, (ready) => {
  if (ready) nextTick(() => scheduleDraw())
})

onMounted(() => {
  nextTick(() => {
    scheduleDraw()
    const el = viewportRef.value || scrollRef.value
    if (el && typeof ResizeObserver !== 'undefined') {
      _scrollResizeObserver = new ResizeObserver(() => scheduleDraw())
      _scrollResizeObserver.observe(el)
    }
  })
  window.addEventListener('resize', scheduleDraw)
})

onBeforeUnmount(() => {
  if (_drawRaf) cancelAnimationFrame(_drawRaf)
  window.removeEventListener('resize', scheduleDraw)
  _scrollResizeObserver?.disconnect()
})
</script>

<style scoped>
.heatmap-overlay {
  position: fixed;
  inset: 0;
  z-index: 2000;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}
.heatmap-dialog {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  min-width: 420px;
  max-width: min(92vw, 720px);
  height: 85vh;
  max-height: 85vh;
  min-height: 320px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  padding: 12px 14px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.35);
}
.heatmap-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-shrink: 0;
}
.heatmap-back {
  border: 1px solid var(--border);
  background: var(--tb-bg);
  color: var(--fg);
  border-radius: 4px;
  padding: 4px 8px;
  cursor: pointer;
  font-size: 12px;
  flex-shrink: 0;
}
.heatmap-title {
  font-weight: 600;
  font-size: 14px;
  flex: 1;
}
.heatmap-close {
  border: 1px solid var(--border);
  background: var(--tb-bg);
  color: var(--fg);
  border-radius: 4px;
  padding: 4px 10px;
  cursor: pointer;
  font-size: 12px;
  flex-shrink: 0;
}
.heatmap-sub {
  margin: 8px 0 6px;
  font-size: 12px;
  color: var(--fg-dim);
  flex-shrink: 0;
}
.heatmap-empty {
  padding: 24px 0;
  text-align: center;
  color: var(--fg-dim);
  font-size: 13px;
  flex-shrink: 0;
}
.heatmap-viewport {
  flex: 1 1 0;
  min-height: 0;
  position: relative;
  overflow: hidden;
}
.heatmap-scroll {
  width: 100%;
  height: 100%;
  overflow: auto;
  -webkit-overflow-scrolling: touch;
}
.heatmap-spacer {
  pointer-events: none;
  display: block;
}
.heatmap-canvas {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  z-index: 1;
  pointer-events: auto;
}
.heatmap-cell-tip {
  margin: 4px 0 0;
  font-size: 11px;
  color: var(--fg-dim);
  min-height: 1.2em;
  flex-shrink: 0;
}
.heatmap-hint {
  margin: 8px 0 0;
  font-size: 11px;
  color: var(--fg-dim);
  flex-shrink: 0;
}
.heatmap-export-row {
  display: flex;
  gap: 8px;
  margin-top: 8px;
  flex-shrink: 0;
}
.heatmap-export-btn {
  border: 1px solid var(--border);
  background: var(--tb-bg);
  color: var(--fg);
  border-radius: 4px;
  padding: 4px 10px;
  cursor: pointer;
  font-size: 12px;
}
.heatmap-export-btn:hover {
  border-color: var(--accent);
}
.heatmap-filter-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 10px;
  padding: 8px 10px;
  border-radius: 4px;
  background: rgba(91, 155, 213, 0.12);
  border: 1px solid rgba(91, 155, 213, 0.35);
  font-size: 12px;
  flex-shrink: 0;
}
.heatmap-show-all {
  flex-shrink: 0;
  border: 1px solid var(--accent);
  background: var(--accent);
  color: #000;
  border-radius: 4px;
  padding: 4px 10px;
  cursor: pointer;
  font-size: 12px;
  font-weight: 600;
}
.heatmap-show-all:hover {
  filter: brightness(1.08);
}
.heatmap-bounce-bar {
  display: flex;
  align-items: center;
  margin: 6px 0 2px;
  flex-shrink: 0;
}
.heatmap-bounce-toggle {
  border: 1px solid var(--border);
  background: var(--tb-bg);
  color: var(--fg-dim);
  border-radius: 4px;
  padding: 3px 10px;
  cursor: pointer;
  font-size: 12px;
  transition: border-color 0.12s, color 0.12s, background 0.12s;
}
.heatmap-bounce-toggle:hover {
  border-color: var(--accent);
  color: var(--fg);
}
.heatmap-bounce-toggle.active {
  border-color: #e8a020;
  background: rgba(232, 160, 32, 0.12);
  color: #e8a020;
  font-weight: 600;
}
</style>
