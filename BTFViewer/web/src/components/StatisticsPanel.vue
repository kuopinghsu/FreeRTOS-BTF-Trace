<template>
  <div class="stats-panel">
    <!-- Summary -->
    <div class="stats-summary">
      <div class="summary-row">
        <span class="summary-key">Span</span>
        <span class="summary-val">{{ spanStr }}</span>
      </div>
      <div class="summary-row">
        <span class="summary-key">Tasks</span>
        <span class="summary-val">{{ trace.tasks.length }}</span>
      </div>
      <div class="summary-row">
        <span class="summary-key">Segments</span>
        <span class="summary-val">{{ trace.segments.length.toLocaleString() }}</span>
      </div>
      <div class="summary-row">
        <span class="summary-key">STI Events</span>
        <span class="summary-val">{{ trace.stiEvents.length.toLocaleString() }}</span>
      </div>
    </div>

    <!-- Range stats (from cursors) -->
    <template v-if="rangeStats">
      <div class="stats-sep" />
      <div class="stats-section-title">
        Cursor Range
      </div>
      <div class="summary-row">
        <span class="summary-key">Span</span>
        <span class="summary-val">{{ rangeStats.span }}</span>
      </div>
      <div class="summary-row">
        <span class="summary-key">Slices</span>
        <span class="summary-val">{{ rangeStats.switches }}</span>
      </div>
      <div
        v-if="rangeStats.topTask"
        class="summary-row"
      >
        <span class="summary-key">Top task</span>
        <span class="summary-val">{{ rangeStats.topTask }} ({{ rangeStats.topPct }}%)</span>
      </div>
      <div
        v-if="rangeStats.dMin"
        class="summary-row"
      >
        <span class="summary-key">Seg min</span>
        <span class="summary-val">{{ rangeStats.dMin }}</span>
      </div>
      <div
        v-if="rangeStats.dMax"
        class="summary-row"
      >
        <span class="summary-key">Seg max</span>
        <span class="summary-val">{{ rangeStats.dMax }}</span>
      </div>
      <div
        v-if="rangeStats.dAvg"
        class="summary-row"
      >
        <span class="summary-key">Seg avg</span>
        <span class="summary-val">{{ rangeStats.dAvg }}</span>
      </div>
    </template>
    <template v-else>
      <div class="stats-sep" />
      <div class="range-hint">
        Place 2+ cursors to measure range
      </div>
    </template>

    <!-- Core utilization -->
    <template v-if="trace.coreNames && trace.coreNames.length > 0">
      <div class="stats-sep" />
      <div
        class="stats-section-title collapsible"
        @click="coresCollapsed = !coresCollapsed"
      >
        <svg
          class="chevron"
          :class="{ collapsed: coresCollapsed }"
          viewBox="0 0 10 10"
          width="10"
          height="10"
        >
          <polyline
            points="2,3 5,7 8,3"
            fill="none"
            stroke="currentColor"
            stroke-width="1.5"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        </svg>
        Core Utilisation (excl. IDLE/TICK)
      </div>
      <template v-if="!coresCollapsed">
        <div
          v-for="cs in coreStats"
          :key="cs.core"
          class="core-stat-row"
        >
          <span class="core-name">{{ cs.core }}</span>
          <div class="prog-bar">
            <div
              class="prog-fill"
              :style="{ width: clampPct(cs.pct) + '%' }"
            />
          </div>
          <span class="core-pct">{{ cs.pct.toFixed(1) }}%</span>
        </div>
      </template>
    </template>

    <!-- Top tasks -->
    <div class="stats-sep" />
    <div
      class="stats-section-title collapsible"
      @click="tasksCollapsed = !tasksCollapsed"
    >
      <svg
        class="chevron"
        :class="{ collapsed: tasksCollapsed }"
        viewBox="0 0 10 10"
        width="10"
        height="10"
      >
        <polyline
          points="2,3 5,7 8,3"
          fill="none"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
      </svg>
      Top Tasks by CPU (excl. IDLE/TICK)
    </div>
    <template v-if="!tasksCollapsed">
      <div
        v-if="topTasks.length === 0"
        class="range-hint"
      >
        No user tasks found
      </div>
      <div
        v-for="t in topTasks"
        :key="t.mk"
        class="task-stat-row"
      >
        <span class="task-stat-name">{{ t.name }}</span>
        <div class="prog-bar">
          <div
            class="prog-fill"
            :style="{ width: clampPct(t.pct) + '%' }"
          />
        </div>
        <span class="task-stat-pct">{{ t.pct.toFixed(1) }}%</span>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { formatTime } from '../renderer/TimelineRenderer.js'
import { taskDisplayName, parseTaskName, taskMergeKey } from '../utils/colors.js'

const props = defineProps({
  trace:   { type: Object, required: true },
  cursors: { type: Array, default: () => [] },
})

const coresCollapsed = ref(true)
const tasksCollapsed = ref(true)

function clampPct(v) { return Math.max(0, Math.min(100, v)).toFixed(1) }

const spanStr = computed(() => formatTime(props.trace.timeMax - props.trace.timeMin, props.trace.timeScale))

// ---- Core utilisation (excl. IDLE/TICK) — only computed when visible ----
const coreStats = computed(() => {
  if (coresCollapsed.value) return []
  const tr = props.trace  // explicit dep on the trace object
  if (!tr || !tr.coreNames || tr.coreNames.length === 0) return []
  const total = tr.timeMax - tr.timeMin
  if (total <= 0) return []
  return tr.coreNames.map(core => {
    const segs = tr.coreSegs.get(core) || []
    let active = 0
    for (const s of segs) {
      const { name } = parseTaskName(s.task)
      if (name === 'TICK' || name.startsWith('IDLE')) continue
      active += s.end - s.start
    }
    return { core, pct: 100.0 * active / total }
  })
})

// ---- Top 10 tasks by CPU — only computed when visible ------------------
const topTasks = computed(() => {
  if (tasksCollapsed.value) return []
  const tr = props.trace  // explicit dep on the trace object
  if (!tr || !tr.segByMergeKey) return []
  const total = tr.timeMax - tr.timeMin
  if (total <= 0) return []
  const accum = new Map()
  for (const [mk, segs] of tr.segByMergeKey) {
    const repr = tr.taskRepr.get(mk) || mk
    const { name } = parseTaskName(repr)
    if (name.startsWith('IDLE') || name === 'TICK') continue
    let t = 0
    for (const s of segs) t += s.end - s.start
    if (t > 0) accum.set(mk, t)
  }
  return [...accum.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10)
    .map(([mk, t]) => ({
      mk,
      name: taskDisplayName(tr.taskRepr.get(mk) || mk),
      pct: 100.0 * t / total,
    }))
})

// ---- Range statistics (from 2+ cursor positions) -----------------------
// Computed via a debounced watcher so cursor placement never blocks the UI.
const rangeStats = ref(null)
let _rangeTimer = null

function _computeRangeStats(cursors) {
  const placed = cursors.filter(c => c !== null)
  if (placed.length < 2) return null
  const sorted = [...placed].sort((a, b) => a - b)
  const lo = sorted[0]
  const hi = sorted[sorted.length - 1]
  const dt = hi - lo
  if (dt <= 0) return null

  const scale = props.trace.timeScale
  const taskAcc = new Map()
  const durations = []
  let switches = 0

  for (const seg of props.trace.segments) {
    if (seg.end <= lo || seg.start >= hi) continue
    const ov = Math.min(seg.end, hi) - Math.max(seg.start, lo)
    if (ov <= 0) continue
    switches++
    durations.push(seg.end - seg.start)
    const mk = taskMergeKey(seg.task)
    const repr = props.trace.taskRepr.get(mk) || seg.task
    const disp = taskDisplayName(repr)
    taskAcc.set(disp, (taskAcc.get(disp) || 0) + ov)
  }

  let topTask = null, topNs = 0
  for (const [k, v] of taskAcc) {
    if (v > topNs) { topNs = v; topTask = k }
  }

  const result = {
    span:     formatTime(dt, scale),
    switches,
    topTask,
    topPct:   topTask ? (100.0 * topNs / dt).toFixed(1) : null,
  }

  if (durations.length > 0) {
    const minD = Math.min(...durations)
    const maxD = Math.max(...durations)
    const avgD = Math.round(durations.reduce((a, b) => a + b, 0) / durations.length)
    result.dMin = formatTime(minD, scale)
    result.dMax = formatTime(maxD, scale)
    result.dAvg = formatTime(avgD, scale)
  }
  return result
}

watch(() => props.cursors, (cursors) => {
  clearTimeout(_rangeTimer)
  const placed = cursors.filter(c => c !== null)
  if (placed.length < 2) {
    rangeStats.value = null
    return
  }
  // Defer heavy segment scan so cursor placement feels instant
  _rangeTimer = setTimeout(() => {
    rangeStats.value = _computeRangeStats(cursors)
  }, 200)
}, { deep: true })
</script>

<style scoped>
.stats-panel {
  display: flex;
  flex-direction: column;
  padding: 8px 10px;
  font-size: 11px;
  font-family: monospace;
  overflow-y: auto;
  flex: 1;
  gap: 0;
}

.stats-summary {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.summary-row {
  display: flex;
  justify-content: space-between;
  gap: 4px;
}

.summary-key {
  color: var(--fg-dim);
  flex-shrink: 0;
}

.summary-val {
  color: var(--fg);
  text-align: right;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.stats-sep {
  height: 1px;
  background: var(--border);
  margin: 6px 0;
  flex-shrink: 0;
}

.stats-section-title {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--fg-dim);
  margin-bottom: 4px;
}

.stats-section-title.collapsible {
  cursor: pointer;
  user-select: none;
}

.stats-section-title.collapsible:hover {
  color: var(--fg);
}

.chevron {
  flex-shrink: 0;
  transition: transform 0.15s;
  color: var(--fg-dim);
}

.chevron.collapsed {
  transform: rotate(-90deg);
}

.range-hint {
  color: var(--fg-dim);
  opacity: 0.6;
  font-size: 10px;
  font-style: italic;
}

.core-stat-row,
.task-stat-row {
  display: flex;
  align-items: center;
  gap: 5px;
  margin-bottom: 3px;
}

.core-name {
  color: var(--fg-dim);
  min-width: 56px;
  flex-shrink: 0;
}

.task-stat-name {
  color: var(--fg);
  min-width: 0;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.prog-bar {
  flex: 1;
  height: 8px;
  border-radius: 4px;
  background: var(--border);
  overflow: hidden;
  flex-shrink: 0;
  min-width: 30px;
}

.prog-fill {
  height: 100%;
  background: #5FCF6F;
  border-radius: 4px;
  transition: width 0.2s;
}

.core-pct,
.task-stat-pct {
  color: #77BB77;
  min-width: 38px;
  text-align: right;
  flex-shrink: 0;
}
</style>
