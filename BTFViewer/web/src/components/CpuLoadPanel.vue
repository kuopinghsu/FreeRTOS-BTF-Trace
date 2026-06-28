<template>
  <div
    ref="panelRef"
    class="cpu-load-panel"
    :class="{ dark: darkMode }"
  >
    <div class="cpu-load-title-row">
      <div class="cpu-load-title">CPU LOAD</div>
      <button
        v-if="selectedTask"
        type="button"
        class="cpu-load-clear-btn"
        @click="emit('clearSelection')"
      >
        Clear Selection
      </button>
    </div>
    <div
      ref="rowsRef"
      class="cpu-load-rows"
    >
      <div
        v-for="row in rowModels"
        :key="row.key"
        class="cpu-load-row"
        :class="{ collapsed: row.collapsed }"
        :style="{ height: `${row.height}px`, minHeight: `${row.height}px` }"
      >
        <button
          type="button"
          class="cpu-load-label"
          :class="{ clickable: row.kind === 'core' }"
          :style="{ width: `${labelWidth}px` }"
          :title="row.kind === 'core' ? 'Toggle row collapse' : ''"
          @click="onRowLabelClick(row)"
        >
          <span class="cpu-load-chevron">{{ row.kind === 'core' ? (row.collapsed ? '▶' : '▼') : '' }}</span>
          <span
            class="cpu-load-dot"
            :style="{ backgroundColor: row.color }"
          />
          <span class="cpu-load-name">{{ row.label }}</span>
          <span
            class="cpu-load-pct"
            :title="row.pctTitle"
          >
            <span class="cpu-load-pct-vis">{{ row.pctVis }}</span><span
              v-if="row.pctCursor"
              class="cpu-load-pct-cursor"
            >{{ row.pctCursor }}</span>
          </span>
        </button>

        <div
          v-if="!row.collapsed"
          class="cpu-load-plot"
        >
          <svg
            class="cpu-load-svg"
            :viewBox="`0 0 ${PLOT_W} ${row.height}`"
            preserveAspectRatio="none"
          >
            <line
              v-for="grid in row.gridLines"
              :key="`${row.key}-grid-${grid.pct}`"
              x1="0"
              :x2="PLOT_W"
              :y1="grid.y"
              :y2="grid.y"
              class="cpu-load-grid"
            />
            <text
              v-for="grid in row.gridLabels"
              :key="`${row.key}-label-${grid.pct}`"
              x="4"
              :y="grid.y - 2"
              class="cpu-load-grid-label"
            >
              {{ grid.label }}
            </text>
            <rect
              v-for="rect in row.rects"
              :key="`${row.key}-${rect.index}`"
              :x="rect.x"
              :y="rect.y"
              :width="rect.width"
              :height="rect.height"
              :fill="row.color"
            />
            <rect
              v-if="row.cursorRangeShade"
              :x="row.cursorRangeShade.x"
              y="0"
              :width="row.cursorRangeShade.width"
              :height="row.height"
              :fill="rangeShadePaint.fill"
              :fill-opacity="rangeShadePaint.fillOpacity"
              pointer-events="none"
            />
            <line
              v-if="row.hoverCursor"
              :x1="row.hoverCursor.x"
              :x2="row.hoverCursor.x"
              y1="0"
              :y2="row.height"
              class="cpu-load-hover-line"
            />
            <g
              v-if="row.hoverCursor?.label"
              class="cpu-load-hover-badge"
            >
              <rect
                :x="row.hoverCursor.badgeX"
                y="2"
                :width="row.hoverCursor.badgeW"
                height="12"
                rx="2"
                class="cpu-load-hover-badge-bg"
              />
              <text
                :x="row.hoverCursor.badgeX + 4"
                y="8"
                class="cpu-load-hover-text"
              >
                {{ row.hoverCursor.label }}
              </text>
            </g>
            <line
              v-for="cursor in row.cursors"
              :key="`${row.key}-cursor-${cursor.index}`"
              :x1="cursor.x"
              :x2="cursor.x"
              y1="0"
              :y2="row.height"
              class="cpu-load-cursor-line"
              :style="{ stroke: cursor.color }"
            />
            <line
              v-for="mark in row.marks"
              :key="`${row.key}-mark-${mark.id}`"
              :x1="mark.x"
              :x2="mark.x"
              y1="0"
              :y2="row.height"
              class="cpu-load-mark-line"
              :class="{ annotation: mark.isAnnotation }"
              :style="{ stroke: mark.color }"
            />
          </svg>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { coreColor, taskColor, taskDisplayName } from '../utils/colors.js'
import {
  coreViewTaskFilterActive,
  filteredCoreViewTasks,
  filteredTaskViewTasks,
} from '../utils/taskFilter.js'
import {
  avgBinsForNsRange,
  aggregateFilteredTaskBins,
  aggregateFilteredTaskCoreBins,
  CPU_LOAD_COLLAPSED_H,
  CPU_LOAD_ROW_GAP,
  cursorRangeShade,
  cpuLoadRangeShadePaint,
  getPlacedCursorRange,
  loadAtNs,
} from '../utils/cpuLoadHelpers.js'
import { CPU_LOAD_NUM_BINS } from '../parser/cpuLoadBins.js'
import {
  applyPanPlotX,
  applyPanPlotY,
  applyZoomAroundPlotX,
  applyZoomAroundPlotY,
} from '../utils/viewportWheel.js'

const NUM_BINS = CPU_LOAD_NUM_BINS
const TITLE_H = 22
const PLOT_W = 1000
const CURSOR_COLORS = ['#FF4444', '#44FF88', '#4499FF', '#FFAA22', '#FF44FF', '#44FFFF', '#FFFF44', '#CC44FF']
const BOOKMARK_COLOR = '#FFD700'
const ANNOTATION_COLOR = '#FF8C00'

const props = defineProps({
  trace: { type: Object, default: null },
  viewport: { type: Object, required: true },
  viewMode: { type: String, default: 'task' },
  orientation: { type: String, default: 'h' },
  darkMode: { type: Boolean, default: true },
  selectedTask: { type: String, default: null },
  allExpanded: { type: Boolean, default: true },
  cursors: { type: Array, default: () => [] },
  hoverTime: { type: Number, default: null },
  marks: { type: Array, default: () => [] },
  cpuLoadRowH: { type: Number, default: 30 },
  layoutRev: { type: Number, default: 0 },
  migratedOnlyFilter: { type: Boolean, default: false },
  taskFilterKeys: { type: Array, default: null },
  taskFilterText: { type: String, default: '' },
  labelWidth: { type: Number, default: 160 },
})
const emit = defineEmits(['clearSelection', 'viewportChange'])

const panelRef = ref(null)
const rowsRef = ref(null)
const collapsedCores = ref(new Set())

const binsState = computed(() => {
  const trace = props.trace
  const empty = {
    binWNs: 1,
    coreBins: {},
    taskBins: {},
    taskCoreBins: {},
    totalBins: [],
    avgLoad: {},
  }
  if (!trace?.cpuLoadBins) return empty
  const b = trace.cpuLoadBins
  return {
    binWNs: b.binWNs,
    coreBins: b.coreBins,
    taskBins: b.taskBins,
    taskCoreBins: b.taskCoreBins,
    totalBins: b.totalBins,
    avgLoad: b.avgLoad,
  }
})

const filterOpts = computed(() => ({
  migratedOnlyFilter: props.migratedOnlyFilter,
  taskFilterKeys: props.taskFilterKeys,
  taskFilterText: props.taskFilterText,
}))

const filterActive = computed(() => coreViewTaskFilterActive(
  filterOpts.value.migratedOnlyFilter,
  filterOpts.value.taskFilterKeys,
  filterOpts.value.taskFilterText,
))

const rangeShadePaint = computed(() => cpuLoadRangeShadePaint(props.darkMode))

const filteredTaskKeys = computed(() => {
  if (!props.trace || !filterActive.value) return []
  return filteredTaskViewTasks(
    props.trace,
    filterOpts.value.migratedOnlyFilter,
    filterOpts.value.taskFilterKeys,
    filterOpts.value.taskFilterText,
  )
})

const filteredBins = computed(() => {
  void props.layoutRev
  const trace = props.trace
  if (!trace || !filteredTaskKeys.value.length) return null
  return aggregateFilteredTaskBins(
    binsState.value.taskBins,
    filteredTaskKeys.value,
    trace.coreNames?.length ?? 1,
    NUM_BINS,
  )
})

const rows = computed(() => {
  void props.layoutRev
  const trace = props.trace
  if (!trace) return []
  const selectedTask = props.selectedTask

  // Highlighted task: task view = that task's total load; core view = per-core load for it.
  if (selectedTask) {
    if (props.viewMode === 'core') {
      return (trace.coreNames || []).map(coreName => ({
        kind: 'core',
        key: coreName,
        label: coreName,
        color: coreColor(coreName),
      }))
    }
    const raw = trace.taskRepr.get(selectedTask) || selectedTask
    return [{ kind: 'task', key: selectedTask, label: 'CPU Load', color: taskColor(selectedTask, raw) }]
  }

  // Legend filter: task view = combined filtered load; core view = per-core filtered load.
  if (filterActive.value && filteredTaskKeys.value.length) {
    if (props.viewMode === 'task') {
      return [{ kind: 'filtered', key: 'filtered', label: 'CPU Load', color: '#4CAF50' }]
    }
    return filteredCoreViewTasks(
      trace,
      filterOpts.value.migratedOnlyFilter,
      filterOpts.value.taskFilterKeys,
      filterOpts.value.taskFilterText,
    ).map(({ coreName }) => ({
      kind: 'core',
      key: coreName,
      label: coreName,
      color: coreColor(coreName),
    }))
  }

  if (props.viewMode === 'task') {
    return [{ kind: 'total', key: 'total', label: 'CPU Load', color: '#4CAF50' }]
  }

  return (trace.coreNames || []).map(coreName => ({
    kind: 'core',
    key: coreName,
    label: coreName,
    color: coreColor(coreName),
  }))
})

const rowModels = computed(() => {
  void props.cpuLoadRowH
  const trace = props.trace
  const { timeStart, timeEnd } = props.viewport
  if (!trace || timeEnd <= timeStart) return []

  const visibleStart = Math.max(trace.timeMin, timeStart)
  const visibleEnd = Math.min(trace.timeMax, timeEnd)
  const visibleSpan = Math.max(1, visibleEnd - visibleStart)
  const binW = binsState.value.binWNs
  const startBin = Math.max(0, Math.floor((visibleStart - trace.timeMin) / binW))
  const endBin = Math.min(NUM_BINS - 1, Math.ceil((visibleEnd - trace.timeMin) / binW))
  const cursorRange = getPlacedCursorRange(props.cursors)
  const rangeShade = cursorRangeShade(cursorRange, visibleStart, visibleEnd, visibleSpan, PLOT_W)

  return rows.value.map(row => {
    const collapsed = row.kind === 'core' && collapsedCores.value.has(row.key)
    const height = collapsed ? CPU_LOAD_COLLAPSED_H : props.cpuLoadRowH
    const bins = binsForRow(row.kind, row.key)
    const rects = []

    if (!collapsed && bins) {
      for (let bin = startBin; bin <= endBin; bin++) {
        const load = bins[bin] || 0
        if (load <= 0.001) continue
        const binStart = trace.timeMin + bin * binW
        const binEnd = binStart + binW
        const x0 = ((Math.max(binStart, visibleStart) - visibleStart) / visibleSpan) * PLOT_W
        const x1 = ((Math.min(binEnd, visibleEnd) - visibleStart) / visibleSpan) * PLOT_W
        if (x1 <= x0) continue
        const barH = Math.max(1, load * (height - 2))
        rects.push({
          index: bin,
          x: x0,
          y: height - barH,
          width: Math.max(1, x1 - x0),
          height: barH,
        })
      }
    }

    const visAvg = bins
      ? avgBinsForNsRange(bins, trace, binW, visibleStart, visibleEnd, NUM_BINS)
      : 0
    const pctVis = `${Math.round(visAvg * 100)}%`
    let pctCursor = ''
    let pctTitle = `Visible-window average: ${(visAvg * 100).toFixed(1)}%`
    if (cursorRange) {
      const crAvg = avgBinsForNsRange(
        bins, trace, binW, cursorRange.lo, cursorRange.hi, NUM_BINS)
      pctCursor = ` · C:${Math.round(crAvg * 100)}%`
      pctTitle += `\nCursor-range average (C1–C${cursorRange.nCursors}): ${(crAvg * 100).toFixed(1)}%`
    }

    const hoverLoad = (props.hoverTime != null && bins)
      ? loadAtNs(bins, trace, binW, props.hoverTime, NUM_BINS)
      : null

    return {
      ...row,
      collapsed,
      height,
      rects,
      cursorRangeShade: collapsed ? null : rangeShade,
      hoverCursor: collapsed
        ? null
        : buildHoverCursor(visibleStart, visibleEnd, visibleSpan, hoverLoad),
      cursors: collapsed ? [] : buildCursorOverlays(visibleStart, visibleEnd, visibleSpan),
      marks: collapsed ? [] : buildMarkOverlays(visibleStart, visibleEnd, visibleSpan),
      pctVis,
      pctCursor,
      pctTitle,
      gridLines: collapsed ? [] : [0.25, 0.5, 0.75, 1].map(pct => ({ pct, y: height - pct * height })),
      gridLabels: collapsed ? [] : [0, 25, 50, 75].map(pct => ({ pct, label: `${pct}`, y: height - (pct / 100) * height })),
    }
  })
})

function binsForRow(kind, key) {
  const selectedTask = props.selectedTask
  if (kind === 'filtered') return filteredBins.value
  if (kind === 'total') return binsState.value.totalBins
  if (kind === 'task') return binsState.value.taskBins[key] || null
  if (selectedTask) return binsState.value.taskCoreBins[selectedTask]?.[key] || null
  if (kind === 'core' && filterActive.value && filteredTaskKeys.value.length) {
    return aggregateFilteredTaskCoreBins(
      binsState.value.taskCoreBins,
      filteredTaskKeys.value,
      key,
      NUM_BINS,
    )
  }
  return binsState.value.coreBins[key] || null
}

function onRowLabelClick(row) {
  if (row.kind !== 'core') return
  const next = new Set(collapsedCores.value)
  if (next.has(row.key)) next.delete(row.key)
  else next.add(row.key)
  collapsedCores.value = next
}

let _wheelQueue = null
let _wheelFlushRaf = null
let _rowsScrollDelta = 0

function _flushWheel() {
  _wheelFlushRaf = null
  if (_rowsScrollDelta !== 0) {
    const rowsEl = rowsRef.value
    if (rowsEl) rowsEl.scrollTop += _rowsScrollDelta
    _rowsScrollDelta = 0
    return
  }
  const queue = _wheelQueue
  _wheelQueue = null
  if (!queue?.length || !props.trace || !props.viewport) return
  let vp = { ...props.viewport }
  for (const fn of queue) {
    vp = fn(vp) ?? vp
  }
  emit('viewportChange', vp)
}

function _queueWheel(updateFn) {
  if (!_wheelQueue) _wheelQueue = []
  _wheelQueue.push(updateFn)
  if (!_wheelFlushRaf) {
    _wheelFlushRaf = requestAnimationFrame(_flushWheel)
  }
}

function _buildWheelMutator(e) {
  const panel = panelRef.value
  if (!panel) return null
  const rect = panel.getBoundingClientRect()
  const vert = props.orientation === 'v'
  const plotLeft = vert ? rect.left : rect.left + props.labelWidth
  const plotTop = rect.top + (vert ? TITLE_H : 0)
  const plotWidth = vert ? rect.width : Math.max(1, rect.right - plotLeft)
  const plotHeight = vert ? Math.max(1, rect.bottom - plotTop) : rect.height
  const plotX = e.clientX - plotLeft
  const plotY = e.clientY - plotTop

  if (e.ctrlKey || e.metaKey) {
    const factor = e.deltaY > 0 ? 1.15 : 0.87
    return vp => (vert
      ? applyZoomAroundPlotY(vp, props.trace, plotY, plotHeight, TITLE_H, factor)
      : applyZoomAroundPlotX(vp, props.trace, plotX, plotWidth, factor))
  }
  if (vert) {
    const isHorizInput = e.shiftKey || Math.abs(e.deltaX) > Math.abs(e.deltaY)
    if (isHorizInput) {
      const dx = e.shiftKey ? e.deltaY : e.deltaX
      return vp => ({ ...vp, scrollX: Math.max(0, (vp.scrollX || 0) + dx) })
    }
    const dy = e.deltaMode === 1 ? e.deltaY * props.cpuLoadRowH : e.deltaY
    return vp => applyPanPlotY(vp, props.trace, dy, plotHeight, TITLE_H)
  }
  const isHorizInput = Math.abs(e.deltaX) > Math.abs(e.deltaY)
  if (isHorizInput) {
    return vp => applyPanPlotX(vp, props.trace, e.deltaX, plotWidth)
  }
  if (e.shiftKey) {
    return vp => applyPanPlotX(vp, props.trace, e.deltaY, plotWidth)
  }
  const dy = e.deltaMode === 1 ? e.deltaY * props.cpuLoadRowH : e.deltaY
  return vp => ({ ...vp, scrollY: Math.max(0, (vp.scrollY || 0) + dy) })
}

function onWheel(e) {
  if (!props.trace || !props.viewport) return
  e.preventDefault()
  e.stopPropagation()

  const rowsEl = rowsRef.value
  if (rowsEl
      && rowsEl.scrollHeight > rowsEl.clientHeight + 1
      && !e.ctrlKey && !e.metaKey && !e.shiftKey
      && Math.abs(e.deltaY) >= Math.abs(e.deltaX)) {
    _wheelQueue = null
    const dy = e.deltaMode === 1 ? e.deltaY * props.cpuLoadRowH : e.deltaY
    _rowsScrollDelta += dy
    if (!_wheelFlushRaf) {
      _wheelFlushRaf = requestAnimationFrame(_flushWheel)
    }
    return
  }

  _rowsScrollDelta = 0
  const mutator = _buildWheelMutator(e)
  if (mutator) _queueWheel(mutator)
}

onMounted(() => {
  panelRef.value?.addEventListener('wheel', onWheel, { passive: false })
})

onBeforeUnmount(() => {
  if (_wheelFlushRaf) {
    cancelAnimationFrame(_wheelFlushRaf)
    _wheelFlushRaf = null
  }
  _wheelQueue = null
  _rowsScrollDelta = 0
  panelRef.value?.removeEventListener('wheel', onWheel)
})

function timeToPlotX(ns, visibleStart, visibleEnd, visibleSpan) {
  if (ns < visibleStart || ns > visibleEnd) return null
  return ((ns - visibleStart) / visibleSpan) * PLOT_W
}

function buildCursorOverlays(visibleStart, visibleEnd, visibleSpan) {
  return (props.cursors || []).flatMap((ns, index) => {
    if (ns == null) return []
    const x = timeToPlotX(ns, visibleStart, visibleEnd, visibleSpan)
    if (x == null) return []
    return [{
      index,
      x,
      color: CURSOR_COLORS[index % CURSOR_COLORS.length],
    }]
  })
}

function buildHoverCursor(visibleStart, visibleEnd, visibleSpan, load) {
  if (props.hoverTime == null) return null
  const x = timeToPlotX(props.hoverTime, visibleStart, visibleEnd, visibleSpan)
  if (x == null) return null
  const label = load != null ? `${Math.round(load * 100)}%` : ''
  const badgeW = label ? Math.max(22, label.length * 6 + 8) : 0
  return {
    x,
    label,
    badgeW,
    badgeX: label ? clampBadgeX(x - Math.round(badgeW / 2), badgeW) : 0,
  }
}

function buildMarkOverlays(visibleStart, visibleEnd, visibleSpan) {
  return (props.marks || []).flatMap(mark => {
    const x = timeToPlotX(mark.ns, visibleStart, visibleEnd, visibleSpan)
    if (x == null) return []
    const isAnnotation = mark.type === 'annotation'
    return [{
      id: mark.id,
      x,
      color: isAnnotation ? ANNOTATION_COLOR : BOOKMARK_COLOR,
      isAnnotation,
    }]
  })
}

function clampBadgeX(x, width) {
  return Math.max(2, Math.min(PLOT_W - width - 2, x))
}

watch(() => props.allExpanded, (expanded) => {
  if (!props.trace || props.viewMode !== 'core') return
  collapsedCores.value = expanded ? new Set() : new Set(props.trace.coreNames || [])
}, { immediate: true })

watch(() => props.trace, () => {
  collapsedCores.value = props.allExpanded ? new Set() : new Set(props.trace?.coreNames || [])
})

defineExpose({ panelRef })
</script>

<style scoped>
.cpu-load-panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
  background: color-mix(in srgb, var(--panel-bg) 88%, var(--bg));
}

.cpu-load-title {
  color: var(--fg-dim);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.cpu-load-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 6px 10px 4px;
  border-bottom: 1px solid var(--border);
}

.cpu-load-clear-btn {
  appearance: none;
  border: 1px solid var(--border);
  background: transparent;
  color: var(--fg-dim);
  border-radius: 4px;
  padding: 2px 8px;
  font-size: 10px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  cursor: pointer;
}

.cpu-load-clear-btn:hover,
.cpu-load-clear-btn:focus-visible {
  background: var(--tb-btn-hover);
  color: var(--fg);
  outline: none;
}

.cpu-load-rows {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 6px 0 0;
  overflow-y: auto;
  flex: 1;
  min-height: 0;
}

.cpu-load-row {
  display: flex;
  flex-shrink: 0;
  border-bottom: 1px solid var(--border);
}

.cpu-load-label {
  flex-shrink: 0;
  box-sizing: border-box;
  display: grid;
  grid-template-columns: 10px 9px minmax(0, 1fr) 96px;
  column-gap: 6px;
  align-items: center;
  padding: 0 8px;
  border: 0;
  border-right: 1px solid var(--border);
  background: color-mix(in srgb, var(--panel-bg) 84%, var(--bg));
  color: var(--fg);
  font: inherit;
  text-align: left;
  overflow: hidden;
}

.cpu-load-label.clickable {
  cursor: pointer;
}

.cpu-load-label.clickable:hover {
  background: var(--tb-btn-hover);
}

.cpu-load-chevron {
  width: 10px;
  color: var(--fg);
  flex-shrink: 0;
}

.cpu-load-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  flex-shrink: 0;
}

.cpu-load-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 11px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}

.cpu-load-pct {
  color: #4CAF50;
  font-size: 10px;
  text-align: right;
  white-space: nowrap;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}

.cpu-load-pct-vis,
.cpu-load-pct-cursor {
  white-space: nowrap;
}

.cpu-load-range-shade {
  fill: rgba(68, 153, 255, 0.28);
  pointer-events: none;
}

:global(.app:not(.dark)) .cpu-load-range-shade {
  fill: rgba(42, 111, 178, 0.22);
}

.cpu-load-plot {
  flex: 1;
  min-width: 0;
  height: 100%;
  min-height: 0;
  background: var(--bg);
}

.cpu-load-svg {
  display: block;
  width: 100%;
  height: 100%;
}

.cpu-load-grid {
  stroke: var(--border);
  stroke-dasharray: 3 4;
}

.cpu-load-grid-label {
  fill: var(--fg-dim);
  font-size: 7px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}

.cpu-load-cursor-line {
  stroke-width: 1.5;
  stroke-dasharray: 4 3;
}

.cpu-load-hover-line {
  stroke: rgba(255, 255, 255, 0.35);
  stroke-width: 1;
  stroke-dasharray: 3 3;
}

.cpu-load-hover-badge-bg {
  stroke: none;
}

.cpu-load-panel.dark .cpu-load-hover-badge-bg {
  fill: rgba(40, 40, 40, 0.82);
}

.cpu-load-panel:not(.dark) .cpu-load-hover-badge-bg {
  fill: rgba(255, 255, 255, 0.9);
}

.cpu-load-hover-text {
  font: 400 8px monospace;
  dominant-baseline: middle;
}

.cpu-load-panel.dark .cpu-load-hover-text {
  fill: #ffffff;
}

.cpu-load-panel:not(.dark) .cpu-load-hover-text {
  fill: #111111;
}

:global(.app:not(.dark)) .cpu-load-hover-line {
  stroke: rgba(0, 0, 0, 0.25);
}

.cpu-load-mark-line {
  stroke-width: 1.2;
  opacity: 0.75;
}

.cpu-load-mark-line.annotation {
  stroke-dasharray: 6 3;
}

@media (max-width: 760px) {
  .cpu-load-panel {
    max-height: 42vh;
  }

  .cpu-load-label {
    grid-template-columns: 10px 9px minmax(0, 1fr) 88px;
    padding: 0 6px;
  }
}
</style>
