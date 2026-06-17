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
          @click="goLevel0"
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
        v-if="!hasData"
        class="heatmap-empty"
      >
        {{ emptyText }}
      </div>
      <div
        v-else
        ref="scrollRef"
        class="heatmap-scroll"
      >
        <div class="heatmap-body">
          <div
            v-for="(row, ri) in displayRows"
            :key="row.key"
            class="hm-row"
          >
            <span class="hm-label">{{ row.label }}</span>
            <div class="hm-cells">
              <button
                v-for="(v, bi) in row.grid"
                :key="bi"
                type="button"
                class="hm-cell"
                :class="{ 'hm-cell-active': v > 0 }"
                :style="{ background: cellColor(v) }"
                :title="cellTitle(ri, bi, v, row)"
                :disabled="v <= 0"
                @click="onCellClick(ri, bi)"
              />
            </div>
          </div>
        </div>
      </div>
      <p class="heatmap-hint">
        {{ hintText }}
      </p>
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
import { computed, nextTick, ref, watch } from 'vue'
import { formatTime } from '../renderer/TimelineRenderer.js'
import {
  migrationHeatmapGrid,
  migrationTaskHeatmapGrid,
  heatmapBinRange,
} from '../utils/migrationAnalysis.js'
import { getPlacedCursors, getStatsRange } from '../utils/statsRange.js'

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
const scrollRef = ref(null)
const overviewScopeCache = new Map()

function overviewScopeKey(lo, hi) {
  return `${lo ?? ''}:${hi ?? ''}`
}

watch(() => props.taskFilterActive, (active) => {
  if (!active) goLevel0()
})

watch(() => props.trace, () => {
  overviewScopeCache.clear()
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

const overviewHeatmap = computed(() => {
  const r = statsRange.value
  const lo = r?.lo ?? null
  const hi = r?.hi ?? null
  const key = overviewScopeKey(lo, hi)
  const cached = overviewScopeCache.get(key)
  if (cached) return cached
  const hm = migrationHeatmapGrid(props.trace, lo, hi)
  overviewScopeCache.set(key, hm)
  return hm
})

const taskHeatmap = computed(() => {
  const ctx = drillCtx.value
  if (!ctx) return { rows: [], timeBins: 32, tMin: 0, tMax: 0, binW: 0 }
  return migrationTaskHeatmapGrid(
    props.trace,
    ctx.fromCore,
    ctx.toCore,
    ctx.binLo,
    ctx.binHi,
    ctx.parentTimeBins ?? 32,
    ctx.parentBinIndex ?? 0,
    ctx.parentTimeBins ?? 32,
  )
})

const activeGrid = computed(() =>
  drillLevel.value === 0 ? overviewHeatmap.value : taskHeatmap.value)

const displayRows = computed(() => {
  if (drillLevel.value === 0) {
    const hm = overviewHeatmap.value
    return hm.pairs.map((p, i) => ({
      key: `${p.from}→${p.to}`,
      label: p.label,
      fromCore: p.from,
      toCore: p.to,
      pairLabel: p.label,
      grid: hm.grid[i],
    }))
  }
  return taskHeatmap.value.rows.map(r => ({
    key: r.mk,
    label: r.label,
    mk: r.mk,
    grid: r.grid,
  }))
})

const heatMax = computed(() => {
  let m = 0
  for (const row of displayRows.value) {
    for (const v of row.grid) if (v > m) m = v
  }
  return m
})

const hasData = computed(() =>
  displayRows.value.length > 0
  && displayRows.value.some(row => row.grid.some(v => v > 0)))

const subtitle = computed(() => {
  if (drillLevel.value === 0) {
    return `Core-pair migrations over time bins${scopeSuffix.value}`
  }
  const ctx = drillCtx.value
  const scale = props.trace.timeScale
  return `Tasks · ${ctx.pairLabel} · ${formatTime(ctx.binLo, scale)} … ${formatTime(ctx.binHi, scale)}`
})

const emptyText = computed(() =>
  drillLevel.value === 0 ? 'No migrations in scope.' : 'No task migrations in this cell.')

const hintText = computed(() =>
  drillLevel.value === 0
    ? 'Rows: from→to core pairs · Columns: time bins · Click a cell to drill into tasks'
    : 'Rows: tasks · Columns: sub-bins · Click a cell to zoom and filter in Task View')

function scrollHeatmapToTop() {
  nextTick(() => {
    const el = scrollRef.value
    if (el) {
      el.scrollTop = 0
      el.scrollLeft = 0
    }
  })
}

function goLevel0() {
  drillLevel.value = 0
  drillCtx.value = null
  scrollHeatmapToTop()
}

function onShowAll() {
  emit('clearFilter')
}

function cellColor(v) {
  if (!v) return 'rgba(91, 155, 213, 0.06)'
  const alpha = heatMax.value ? 0.2 + 0.7 * (v / heatMax.value) : 0.3
  return `rgba(91, 155, 213, ${alpha})`
}

function cellTitle(ri, bi, count, row) {
  const hm = activeGrid.value
  const { binLo, binHi } = heatmapBinRange(
    hm.tMin,
    hm.binW,
    hm.timeBins,
    hm.tMax,
    bi,
  )
  const scale = props.trace.timeScale
  if (drillLevel.value === 0) {
    return `${row.pairLabel} · ${formatTime(binLo, scale)}–${formatTime(binHi, scale)} · ${count} migration(s) · Click to drill into tasks`
  }
  return `${row.label} · ${formatTime(binLo, scale)}–${formatTime(binHi, scale)} · ${count} migration(s) · Click to drill down`
}

function onCellClick(ri, bi) {
  const row = displayRows.value[ri]
  const count = row.grid[bi]
  if (!row || count <= 0) return
  const hm = activeGrid.value
  const { binLo, binHi } = heatmapBinRange(hm.tMin, hm.binW, hm.timeBins, hm.tMax, bi)

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
  max-height: 85vh;
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
}
.heatmap-empty {
  padding: 24px 0;
  text-align: center;
  color: var(--fg-dim);
  font-size: 13px;
}
.heatmap-scroll {
  overflow: auto;
  flex: 1;
  min-height: 0;
  max-height: 60vh;
}
.heatmap-body {
  min-width: max-content;
  padding: 4px 0;
}
.hm-row {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 16px;
  margin-bottom: 2px;
}
.hm-label {
  flex: 0 0 auto;
  min-width: 3.5em;
  font-size: 11px;
  color: var(--fg-dim);
  text-align: left;
  white-space: nowrap;
  padding-left: 2px;
}
.hm-cells {
  display: flex;
  flex: 1;
  gap: 1px;
  min-width: 0;
}
.hm-cell {
  flex: 1 1 8px;
  min-width: 6px;
  height: 13px;
  border-radius: 1px;
  border: none;
  padding: 0;
  margin: 0;
}
.hm-cell-active {
  cursor: pointer;
}
.hm-cell-active:hover {
  outline: 1px solid rgba(255, 255, 255, 0.45);
  outline-offset: 0;
}
.hm-cell:disabled {
  cursor: default;
}
.heatmap-hint {
  margin: 8px 0 0;
  font-size: 11px;
  color: var(--fg-dim);
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
</style>
