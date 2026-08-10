<template>
  <div class="ci-overlay">
    <div
      class="ci-dialog"
      role="dialog"
      aria-modal="false"
      aria-label="Migration corridor inspector"
    >
      <div class="ci-header">
        <span class="ci-title">Migration &amp; Corridor Inspector</span>
        <button
          type="button"
          class="ci-close"
          @click="emit('close')"
        >
          Close
        </button>
      </div>

      <div class="ci-toolbar">
        <label class="ci-field">
          Top corridors
          <select
            v-model.number="topPct"
          >
            <option :value="10">
              Top 10%
            </option>
            <option :value="25">
              Top 25%
            </option>
            <option :value="50">
              Top 50%
            </option>
            <option :value="100">
              All
            </option>
          </select>
        </label>
        <button
          v-if="traceHasBounces"
          type="button"
          class="ci-bounce-toggle"
          :class="{ active: bounceOnly }"
          @click="bounceOnly = !bounceOnly"
        >
          {{ bounceOnly ? 'Lock Bounces Only' : 'All Migrations' }}
        </button>
        <label class="ci-field">
          Direction
          <select v-model="directionMode">
            <option value="all">
              All
            </option>
            <option value="egress">
              Egress Only
            </option>
            <option value="ingress">
              Ingress Only
            </option>
          </select>
        </label>
        <label class="ci-field">
          Task filter
          <input
            v-model.trim="taskQuery"
            type="search"
            class="ci-task-filter"
            placeholder="name or exact id"
          >
        </label>
      </div>
      <div class="ci-sub">{{ subtitle }}</div>

      <div
        v-if="model.hotspot"
        class="ci-triage"
      >
        <span class="ci-triage-text">{{ model.hotspot.summary }}</span>
        <button
          type="button"
          class="ci-jump"
          @click="jumpHotspot"
        >
          Jump To
        </button>
      </div>

      <div
        class="ci-workspace"
        :class="'dock-' + sidebarDock"
      >
        <div
          v-if="!model.hasData"
          class="ci-empty ci-empty-main"
        >
          {{ taskQuery ? 'No corridors match this task filter.' : 'No migrations in scope.' }}
        </div>
        <div
          v-else
          class="ci-main"
        >
          <div class="ci-tree-pane">
            <div class="ci-tree-head">
              <span class="ci-col-name">Corridor / Task</span>
              <span class="ci-col-num">Vol</span>
              <span class="ci-col-num">Bounce</span>
              <span class="ci-col-num">Net</span>
            </div>
            <div
              ref="treeScrollRef"
              class="ci-tree-scroll"
            >
              <template v-if="model.groupBySource">
                <div
                  v-for="g in model.groups"
                  :key="g.source"
                  class="ci-group"
                >
                  <button
                    type="button"
                    class="ci-row ci-group-row"
                    @click="toggleGroup(g.source)"
                  >
                    <span class="ci-col-name">{{ expandedGroups.has(g.source) ? '▼' : '▶' }} {{ g.label }}</span>
                    <span class="ci-col-num">{{ fmtVol(g.count) }}</span>
                    <span class="ci-col-num">—</span>
                    <span class="ci-col-num">—</span>
                  </button>
                  <template v-if="expandedGroups.has(g.source)">
                    <div
                      v-for="c in g.corridors"
                      :key="c.label"
                    >
                      <CorridorRow
                        :corridor="c"
                        :selected="isCorridorSelected(c)"
                        :selected-task-mk="taskMkIfSelected(c)"
                        :expanded="expandedCorridors.has(c.label)"
                        @toggle="toggleCorridor(c)"
                        @select="selectCorridor(c)"
                        @pick-task="(t) => selectTask(c, t)"
                        @spotlight="spotlightCorridor(c)"
                        @select-task="(t) => spotlightTask(c, t)"
                      />
                    </div>
                  </template>
                </div>
              </template>
              <template v-else>
                <div
                  v-for="c in model.corridors"
                  :key="c.label"
                >
                  <CorridorRow
                    :corridor="c"
                    :selected="isCorridorSelected(c)"
                    :selected-task-mk="taskMkIfSelected(c)"
                    :expanded="expandedCorridors.has(c.label)"
                    @toggle="toggleCorridor(c)"
                    @select="selectCorridor(c)"
                    @pick-task="(t) => selectTask(c, t)"
                    @spotlight="spotlightCorridor(c)"
                    @select-task="(t) => spotlightTask(c, t)"
                  />
                </div>
              </template>
            </div>
          </div>

          <div class="ci-grid-pane">
            <div class="ci-axis-caption">
              Y = directed corridor (source → dest) · X = time bins in scope · color = migration count · hatch = lock bounce
            </div>
            <div class="ci-grid-wrap">
              <div
                ref="gridScrollRef"
                class="ci-grid-body"
                @scroll="onGridScroll"
              >
                <canvas
                  ref="gridCanvasRef"
                  class="ci-grid-canvas"
                  @mousemove="onGridMove"
                  @mouseleave="onGridLeave"
                  @dblclick="onGridDblClick"
                  @click="onGridClick"
                  @wheel.prevent="onGridWheel"
                />
                <div
                  class="ci-grid-spacer"
                  :style="{ height: Math.max(0, gridContentH - gridViewH) + 'px' }"
                />
              </div>
              <div
                v-if="gridHover"
                class="ci-grid-tip"
                :style="gridHoverStyle"
              >
                {{ gridHover.text }}
              </div>
            </div>
          </div>
        </div>

        <div
          class="ci-sidebar"
          :class="{ collapsed: sidebarCollapsed }"
        >
          <div class="ci-sidebar-chrome">
            <button
              type="button"
              class="ci-sidebar-toggle"
              @click="sidebarCollapsed = !sidebarCollapsed"
            >
              {{ sidebarCollapsed ? 'Show topology' : 'Hide topology' }}
            </button>
            <label
              v-if="!sidebarCollapsed"
              class="ci-field ci-dock-field"
            >
              Dock
              <select v-model="sidebarDock">
                <option value="bottom">
                  Bottom
                </option>
                <option value="right">
                  Right
                </option>
              </select>
            </label>
          </div>
          <div
            v-if="!sidebarCollapsed"
            class="ci-sidebar-body"
          >
            <div class="ci-chord-wrap">
              <MiniChordPanel
                :cores="model.filteredMatrix.cores"
                :grid="model.filteredMatrix.grid"
                :focus-corridor="selectedCorridor"
                :focus-cores="focusCoreIndices"
                :direction-mode="directionMode"
                @select-core="onChordSelectCore"
                @select-pair="onChordSelectPair"
                @select-corridor="onChordSelectCorridor"
                @spotlight-corridor="onChordSpotlight"
                @hover-info="chordHover = $event"
              />
            </div>
            <div class="ci-card">
              <template v-if="selectionCard">
                <div class="ci-card-title">
                  {{ selectionCard.title }}
                </div>
                <div
                  v-for="(line, i) in selectionCard.lines"
                  :key="i"
                  class="ci-card-line"
                >
                  {{ line }}
                </div>
                <button
                  v-if="selectionCard.canSpotlight"
                  type="button"
                  class="ci-jump"
                  @click="selectionCard.onSpotlight()"
                >
                  Inspect in Timeline
                </button>
              </template>
              <template v-else>
                <div class="ci-card-line">
                  Click a corridor or chord ribbon to inspect.
                </div>
              </template>
            </div>
          </div>
        </div>
        </div>

        <p class="ci-tip">
          {{ tipText }}
        </p>

      <div
        v-if="taskFilterActive"
        class="ci-filter-bar"
      >
        <span>
          Showing {{ taskFilterCount }} task{{ taskFilterCount === 1 ? '' : 's' }}: {{ taskFilterLabel || 'filtered' }}
        </span>
        <button
          type="button"
          class="ci-show-all"
          @click="emit('clearFilter')"
        >
          Show all tasks
        </button>
      </div>

      <div class="ci-footer">
        <button
          type="button"
          class="ci-ai-btn"
          :title="aiEnabled
            ? 'Open the AI Assistant and walk through migration / corridor findings'
            : 'Enable AI Assistant in Settings → AI'"
          @click="emit('query-ai')"
        >
          Query with AI…
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, defineComponent, h, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { formatTime } from '../renderer/TimelineRenderer.js'
import {
  applyCorridorDirectionFilter,
  applyCorridorTaskFilter,
  applyCorridorTopFilter,
  buildCorridorInspectorModel,
  coreShortName,
  defaultCorridorTopPct,
  heatmapBinRange,
  traceHasCoreBounceHolds,
} from '../utils/migrationAnalysis.js'
import MiniChordPanel from './MiniChordPanel.vue'

const CorridorRow = defineComponent({
  name: 'CorridorRow',
  props: {
    corridor: { type: Object, required: true },
    selected: Boolean,
    selectedTaskMk: { type: String, default: null },
    expanded: Boolean,
  },
  emits: ['toggle', 'select', 'pick-task', 'spotlight', 'select-task'],
  setup(props, { emit }) {
    return () => {
      const c = props.corridor
      const netStr = c.net > 0 ? `+${c.net} ▲` : c.net < 0 ? `${c.net} ▼` : '0'
      const rows = [
        h('button', {
          type: 'button',
          class: ['ci-row', props.selected && !props.selectedTaskMk ? 'selected' : ''],
          onClick: () => emit('select'),
          onDblclick: () => emit('spotlight'),
        }, [
          h('span', { class: 'ci-col-name' }, [
            h('span', {
              class: 'ci-exp',
              onClick: (e) => { e.stopPropagation(); emit('toggle') },
            }, props.expanded ? '▼' : '▶'),
            ` ${c.label}`,
          ]),
          h('span', { class: 'ci-col-num' }, fmtVol(c.count)),
          h('span', { class: 'ci-col-num' }, `${c.bouncePct.toFixed(0)}%`),
          h('span', { class: 'ci-col-num' }, netStr),
        ]),
      ]
      if (props.expanded) {
        for (const t of c.tasks) {
          rows.push(h('button', {
            type: 'button',
            class: ['ci-row', 'ci-task-row', props.selectedTaskMk === t.mk ? 'selected' : ''],
            onDblclick: () => emit('select-task', t),
            onClick: () => emit('pick-task', t),
          }, [
            h('span', { class: 'ci-col-name' }, `    └── ${t.label}`),
            h('span', { class: 'ci-col-num' }, fmtVol(t.count)),
            h('span', { class: 'ci-col-num' }, `${t.bouncePct.toFixed(0)}%`),
            h('span', { class: 'ci-col-num' }, `${t.sharePct.toFixed(0)}%`),
          ]))
        }
      }
      return h('div', { class: 'ci-corridor-block' }, rows)
    }
  },
})

function fmtVol(n) {
  if (n >= 1000) return `${(n / 1000).toFixed(n >= 10000 ? 0 : 1)}k`
  return String(n)
}

const props = defineProps({
  trace: { type: Object, required: true },
  viewport: { type: Object, default: null },
  viewportProgrammatic: { type: Boolean, default: false },
  taskFilterActive: { type: Boolean, default: false },
  taskFilterLabel: { type: String, default: null },
  taskFilterCount: { type: Number, default: 0 },
  focusPair: { type: Object, default: null },
  /** 'heatmap' focuses tree/grid; 'chord' expands topology sidebar */
  initialMode: { type: String, default: 'heatmap' },
  aiEnabled: { type: Boolean, default: true },
})

const emit = defineEmits(['close', 'spotlight', 'clearFilter', 'jump', 'query-ai'])

const GRID_ROW_H = 22
const GRID_LABEL_W = 78
const GRID_HEAD_H = 28
const GRID_FOOT_H = 16

const bounceOnly = ref(false)
const topPct = ref(100)
const directionMode = ref('all')
const taskQuery = ref('')
const sidebarCollapsed = ref(false)
const sidebarDock = ref('bottom')
const expandedCorridors = reactive(new Set())
const expandedGroups = reactive(new Set())
const selectedCorridor = ref(null)
const selectedTaskMk = ref(null)
const focusCoreIndices = ref([])
const highlightBin = ref(-1)
const hoverBin = ref(-1)
const hoverRow = ref(-1)
const gridHover = ref(null)
const gridHoverStyle = ref({})
const chordHover = ref(null)
const treeScrollRef = ref(null)
const gridScrollRef = ref(null)
const gridCanvasRef = ref(null)
const gridViewH = ref(200)
const gridScrollTop = ref(0)
let _drawRaf = 0
let _ro = null

watch(() => props.trace, (t) => {
  bounceOnly.value = false
  selectedCorridor.value = null
  selectedTaskMk.value = null
  focusCoreIndices.value = []
  if (t) {
    t._lockBounceNs = undefined
    topPct.value = defaultCorridorTopPct(t.coreNames?.length || 0)
  }
}, { immediate: true })

const viewportLoHi = computed(() => {
  const vp = props.viewport
  const lo = Math.floor(Number(vp?.timeStart))
  const hi = Math.ceil(Number(vp?.timeEnd))
  if (!Number.isFinite(lo) || !Number.isFinite(hi) || hi <= lo) {
    return { lo: null, hi: null }
  }
  // Uninitialized tab viewport placeholder {0, 1} — treat as full trace.
  if (lo === 0 && hi === 1) return { lo: null, hi: null }
  return { lo, hi }
})

const scopeLoHi = ref({ lo: null, hi: null })
const scopeFrozen = ref(false)
let _scopeTimer = 0
let _frozenAt = 0

function freezeInspectorScope() {
  scopeFrozen.value = true
  _frozenAt = (typeof performance !== 'undefined' ? performance.now() : Date.now())
}

watch([viewportLoHi, () => props.viewportProgrammatic], ([next, programmatic]) => {
  if (programmatic) {
    scopeFrozen.value = true
    return
  }
  if (scopeFrozen.value) {
    const now = typeof performance !== 'undefined' ? performance.now() : Date.now()
    if (now - _frozenAt < 400) return
    scopeFrozen.value = false
  }
  if (_scopeTimer) clearTimeout(_scopeTimer)
  const apply = () => {
    if (scopeLoHi.value.lo === next.lo && scopeLoHi.value.hi === next.hi) return
    scopeLoHi.value = { lo: next.lo, hi: next.hi }
  }
  if (scopeLoHi.value.lo == null && scopeLoHi.value.hi == null) apply()
  else _scopeTimer = window.setTimeout(apply, 80)
}, { immediate: true })

const scopeSuffix = computed(() => {
  const { lo, hi } = scopeLoHi.value
  if (lo == null || hi == null) return ''
  return ` (viewport: ${formatTime(lo, props.trace.timeScale)} … ${formatTime(hi, props.trace.timeScale)})`
})

const traceHasBounces = computed(() => traceHasCoreBounceHolds(props.trace))

const baseModel = computed(() => {
  const q = String(taskQuery.value || '').trim()
  // A task-id search must not be limited to the current zoom window.
  const { lo, hi } = q ? { lo: null, hi: null } : scopeLoHi.value
  return buildCorridorInspectorModel(props.trace, lo, hi, {
    bounceOnly: bounceOnly.value,
    topPct: 100,
    timeBins: 32,
  })
})

const model = computed(() => {
  const q = String(taskQuery.value || '').trim()
  // Name/id search uses every in-scope corridor; Top-N applies only when idle.
  const scoped = q
    ? applyCorridorTaskFilter(baseModel.value, q)
    : applyCorridorTopFilter(baseModel.value, topPct.value)
  return applyCorridorDirectionFilter(
    scoped,
    directionMode.value,
    selectedCorridor.value,
  )
})

watch(
  () => [taskQuery.value, model.value.corridors],
  () => {
    const q = String(taskQuery.value || '').trim()
    if (!q) return
    for (const c of model.value.corridors || []) {
      expandedCorridors.add(c.label)
      if (model.value.groupBySource) expandedGroups.add(c.fromCore)
    }
  },
)

const gridContentH = computed(() => {
  const n = model.value.corridors?.length || 0
  return GRID_HEAD_H + n * GRID_ROW_H + GRID_FOOT_H
})

const subtitle = computed(() => {
  const n = model.value.cores.length
  const focus = selectedCorridor.value
    ? ` · ${coreShortName(selectedCorridor.value.fromCore)}→${coreShortName(selectedCorridor.value.toCore)}`
    : ''
  const nCorr = model.value.corridors?.length || 0
  const q = taskQuery.value ? ` · filter “${taskQuery.value}”` : ''
  return `${n} cores · ${nCorr} corridors · Top ${topPct.value}%${q}${focus}${scopeSuffix.value}`
})

const tipText = computed(() => {
  if (chordHover.value?.type === 'corridor') {
    return `${coreShortName(chordHover.value.fromCore)}→${coreShortName(chordHover.value.toCore)}: ${chordHover.value.count}`
  }
  return 'Click a time cell to select that bin · double-click for Spotlight · outer ring = egress · inner ring = ingress'
})

const selectionCard = computed(() => {
  const sel = selectedCorridor.value
  if (!sel) {
    if (focusCoreIndices.value.length === 1) {
      const i = focusCoreIndices.value[0]
      const st = model.value.coreStats?.[i]
      if (!st) return null
      const net = st.net > 0 ? `+${st.net} net gain` : st.net < 0 ? `${st.net} net loss` : 'balanced'
      return {
        title: coreShortName(st.core),
        lines: [
          `Outgoing ${st.out} / Incoming ${st.in}`,
          `Net: ${net}`,
          ...(st.topTasks || []).slice(0, 3).map(t => `${t.label}: ${t.count}`),
        ],
        canSpotlight: false,
        onSpotlight: () => {},
      }
    }
    return null
  }
  const c = model.value.corridors.find(
    x => x.fromCore === sel.fromCore && x.toCore === sel.toCore,
  ) || model.value.allCorridors.find(
    x => x.fromCore === sel.fromCore && x.toCore === sel.toCore,
  )
  if (!c) return null
  const offender = c.primaryTask
  const picked = selectedTaskMk.value
    ? c.tasks.find(t => t.mk === selectedTaskMk.value)
    : null
  const lines = [
    `Directed Vol: ${c.count.toLocaleString()} migrations (${c.ratePerS.toFixed(1)}/s)`,
    `Lock Bounces: ${c.bounces} (${c.bouncePct.toFixed(0)}% cache-line bounces)`,
    picked
      ? `Selected task: ${picked.label} (${picked.count} mig, ${picked.sharePct.toFixed(0)}% share)`
      : offender
        ? `Primary Offender: ${offender.label} (${offender.sharePct.toFixed(0)}% share)`
        : 'No task attribution',
  ]
  const bi = highlightBin.value
  if (bi != null && bi >= 0 && c.bins) {
    const { tMin, binW, timeBins, tMax } = model.value
    const { binLo, binHi } = heatmapBinRange(tMin, binW, timeBins, tMax, bi)
    const n = c.bins[bi] || 0
    const b = c.bounceBins?.[bi] || 0
    lines.push(
      `Selected bin ${bi + 1}/${timeBins}: ${formatTime(binLo, props.trace.timeScale)}–${formatTime(binHi, props.trace.timeScale)} · ${n} mig${b ? `, ${b} bounce` : ''}`,
    )
  }
  return {
    title: `Corridor: ${c.label}`,
    lines,
    canSpotlight: true,
    onSpotlight: () => spotlightCorridor(c, highlightBin.value >= 0 ? highlightBin.value : null),
  }
})

function isCorridorSelected(c) {
  const s = selectedCorridor.value
  return s && s.fromCore === c.fromCore && s.toCore === c.toCore
}

function taskMkIfSelected(c) {
  return isCorridorSelected(c) ? selectedTaskMk.value : null
}

function toggleCorridor(c) {
  if (expandedCorridors.has(c.label)) expandedCorridors.delete(c.label)
  else expandedCorridors.add(c.label)
}

function toggleGroup(source) {
  if (expandedGroups.has(source)) expandedGroups.delete(source)
  else expandedGroups.add(source)
}

function selectCorridor(c, binIndex = null) {
  selectedCorridor.value = { fromCore: c.fromCore, toCore: c.toCore }
  selectedTaskMk.value = null
  focusCoreIndices.value = []
  highlightBin.value = binIndex != null && binIndex >= 0 ? binIndex : (c.peakBin ?? -1)
  scheduleGridDraw()
}

function selectTask(c, t) {
  expandedCorridors.add(c.label)
  selectedCorridor.value = { fromCore: c.fromCore, toCore: c.toCore }
  selectedTaskMk.value = t?.mk ?? null
  focusCoreIndices.value = []
  highlightBin.value = c.peakBin ?? -1
  scheduleGridDraw()
}

function jumpHotspot() {
  const h = model.value.hotspot
  if (!h) return
  const c = model.value.allCorridors.find(
    x => x.fromCore === h.fromCore && x.toCore === h.toCore,
  )
  if (!c) return
  if (model.value.groupBySource) expandedGroups.add(c.fromCore)
  expandedCorridors.add(c.label)
  selectCorridor(c, c.peakBin ?? null)
  const { tMin, binW, timeBins, tMax } = model.value
  const bi = c.peakBin ?? 0
  const { binLo, binHi } = heatmapBinRange(tMin, binW, timeBins, tMax, bi)
  freezeInspectorScope()
  emit('jump', {
    binLo,
    binHi,
    lockTaskKey: c.primaryTask?.mk || null,
    pairLabel: c.label,
  })
}

function spotlightCorridor(c, binIndex = null) {
  const { tMin, binW, timeBins, tMax } = model.value
  let binLo = tMin
  let binHi = tMax
  if (binIndex != null && binIndex >= 0) {
    const r = heatmapBinRange(tMin, binW, timeBins, tMax, binIndex)
    binLo = r.binLo
    binHi = r.binHi
  } else if (c.peakBin != null) {
    const r = heatmapBinRange(tMin, binW, timeBins, tMax, c.peakBin)
    binLo = r.binLo
    binHi = r.binHi
  }
  const mergeKeys = c.tasks.map(t => t.mk)
  freezeInspectorScope()
  emit('spotlight', {
    fromCore: c.fromCore,
    toCore: c.toCore,
    pairLabel: c.label,
    binLo,
    binHi,
    mergeKeys,
    lockTaskKey: c.primaryTask?.mk || null,
    enableCpuLoad: true,
  })
}

function spotlightTask(c, t) {
  const { tMin, tMax } = model.value
  freezeInspectorScope()
  emit('spotlight', {
    fromCore: c.fromCore,
    toCore: c.toCore,
    pairLabel: `${c.label} · ${t.label}`,
    binLo: tMin,
    binHi: tMax,
    mergeKeys: [t.mk],
    lockTaskKey: t.mk,
    enableCpuLoad: true,
  })
}

function onChordSelectCore(payload) {
  if (payload.clear) {
    focusCoreIndices.value = []
    selectedCorridor.value = null
    selectedTaskMk.value = null
    return
  }
  focusCoreIndices.value = [payload.coreIndex]
  selectedCorridor.value = null
  selectedTaskMk.value = null
}

function onChordSelectPair(payload) {
  const cur = focusCoreIndices.value
  if (cur.length === 1 && cur[0] !== payload.coreIndex) {
    focusCoreIndices.value = [cur[0], payload.coreIndex]
    const a = model.value.cores[cur[0]]
    const b = model.value.cores[payload.coreIndex]
    selectedCorridor.value = { fromCore: a, toCore: b }
    selectedTaskMk.value = null
  } else {
    focusCoreIndices.value = [payload.coreIndex]
    selectedTaskMk.value = null
  }
}

function onChordSelectCorridor(payload) {
  const c = model.value.corridors.find(
    x => x.fromCore === payload.fromCore && x.toCore === payload.toCore,
  ) || model.value.allCorridors.find(
    x => x.fromCore === payload.fromCore && x.toCore === payload.toCore,
  )
  if (c) selectCorridor(c)
  else {
    selectedCorridor.value = payload
    selectedTaskMk.value = null
  }
}

function onChordSpotlight(payload) {
  const c = model.value.allCorridors.find(
    x => x.fromCore === payload.fromCore && x.toCore === payload.toCore,
  )
  if (c) spotlightCorridor(c)
}

function visibleCorridors() {
  return model.value.corridors
}

function scheduleGridDraw() {
  if (_drawRaf) return
  _drawRaf = requestAnimationFrame(() => {
    _drawRaf = 0
    drawGrid()
  })
}

function drawGrid() {
  const canvas = gridCanvasRef.value
  const scroll = gridScrollRef.value
  if (!canvas || !scroll) return
  const corridors = visibleCorridors()
  const { timeBins, maxBin, tMin, tMax } = model.value
  const rowH = GRID_ROW_H
  const labelW = GRID_LABEL_W
  const headH = GRID_HEAD_H
  const footH = GRID_FOOT_H
  const w = scroll.clientWidth
  const h = scroll.clientHeight
  gridViewH.value = h
  if (w < 1 || h < 1) return
  const dpr = window.devicePixelRatio || 1
  const maxPx = 8192
  canvas.width = Math.max(1, Math.min(maxPx, Math.floor(w * dpr)))
  canvas.height = Math.max(1, Math.min(maxPx, Math.floor(h * dpr)))
  canvas.style.width = `${w}px`
  canvas.style.height = `${h}px`
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  const sx = canvas.width / w
  const sy = canvas.height / h
  ctx.setTransform(sx, 0, 0, sy, 0, 0)
  ctx.clearRect(0, 0, w, h)

  const fg = getComputedStyle(scroll).getPropertyValue('--fg-dim').trim() || '#888'
  const plotW = Math.max(1, w - labelW)
  const cellW = plotW / timeBins
  const scrollTop = scroll.scrollTop
  gridScrollTop.value = scrollTop

  ctx.fillStyle = fg
  ctx.font = '10px monospace'
  ctx.fillText('src→dst', 4, 12)
  const tickCount = Math.min(timeBins, 6)
  for (let t = 0; t <= tickCount; t++) {
    const frac = t / tickCount
    const ns = Math.round(tMin + frac * (tMax - tMin))
    const x = labelW + frac * plotW
    ctx.textAlign = frac < 0.05 ? 'left' : frac > 0.95 ? 'right' : 'center'
    ctx.fillText(formatTime(ns, props.trace.timeScale), x, 12)
  }
  ctx.textAlign = 'left'

  const firstRow = Math.max(0, Math.floor((scrollTop - headH) / rowH))
  const visCount = Math.ceil(h / rowH) + 2
  const lastRow = Math.min(corridors.length - 1, firstRow + visCount)

  for (let ri = firstRow; ri <= lastRow; ri++) {
    const c = corridors[ri]
    if (!c) continue
    const y = headH + ri * rowH - scrollTop
    if (y + rowH < headH || y > h - footH) continue
    const selected = isCorridorSelected(c)
    if (selected) {
      ctx.fillStyle = 'rgba(100,160,255,0.12)'
      ctx.fillRect(0, y, w, rowH)
    }
    ctx.fillStyle = fg
    ctx.font = selected ? 'bold 10px monospace' : '10px monospace'
    ctx.textAlign = 'right'
    ctx.fillText(c.label, labelW - 6, y + rowH * 0.68)
    ctx.textAlign = 'left'
    for (let b = 0; b < timeBins; b++) {
      const v = c.bins[b] || 0
      const bv = c.bounceBins[b] || 0
      const x = labelW + b * cellW
      if (v > 0) {
        const intensity = Math.min(1, v / (maxBin || 1))
        const bounceRatio = bv > 0 ? bv / v : 0
        if (bounceRatio >= 0.15) {
          ctx.fillStyle = `rgba(232,120,32,${0.2 + 0.55 * intensity})`
        } else {
          ctx.fillStyle = `rgba(70,130,220,${0.15 + 0.75 * intensity})`
        }
        ctx.fillRect(x + 0.5, y + 2, cellW - 1, rowH - 4)
      } else {
        ctx.fillStyle = 'rgba(127,127,127,0.06)'
        ctx.fillRect(x + 0.5, y + 2, cellW - 1, rowH - 4)
      }
      if (highlightBin.value === b && selected) {
        ctx.strokeStyle = 'rgba(255,220,80,0.9)'
        ctx.strokeRect(x + 0.5, y + 1, cellW - 1, rowH - 2)
      } else if (hoverRow.value === ri && hoverBin.value === b) {
        ctx.strokeStyle = 'rgba(180,200,255,0.7)'
        ctx.strokeRect(x + 0.5, y + 1, cellW - 1, rowH - 2)
      }
    }
  }

  ctx.fillStyle = getComputedStyle(scroll).getPropertyValue('--bg').trim() || '#1e1e1e'
  ctx.fillRect(0, h - footH, w, footH)
  ctx.fillStyle = fg
  ctx.font = '10px monospace'
  ctx.textAlign = 'center'
  ctx.fillText('Time →', labelW + plotW / 2, h - 4)
  ctx.textAlign = 'left'
}

function gridHit(ev) {
  const canvas = gridCanvasRef.value
  const scroll = gridScrollRef.value
  if (!canvas || !scroll) return null
  const rect = canvas.getBoundingClientRect()
  const mx = ev.clientX - rect.left
  const my = ev.clientY - rect.top
  const corridors = visibleCorridors()
  const { timeBins, tMin, binW, tMax } = model.value
  const plotW = Math.max(1, rect.width - GRID_LABEL_W)
  const cellW = plotW / timeBins
  const contentY = scroll.scrollTop + my
  const ri = Math.floor((contentY - GRID_HEAD_H) / GRID_ROW_H)
  const bi = Math.floor((mx - GRID_LABEL_W) / cellW)
  if (ri < 0 || ri >= corridors.length || bi < 0 || bi >= timeBins) return null
  if (my < GRID_HEAD_H || my > rect.height - GRID_FOOT_H) return null
  const c = corridors[ri]
  const { binLo, binHi } = heatmapBinRange(tMin, binW, timeBins, tMax, bi)
  return {
    c, ri, bi, binLo, binHi,
    count: c.bins[bi] || 0,
    bounces: c.bounceBins[bi] || 0,
    mx, my,
  }
}

function onGridScroll() {
  const el = gridScrollRef.value
  if (el) gridScrollTop.value = el.scrollTop
  scheduleGridDraw()
}

function onGridWheel(ev) {
  const el = gridScrollRef.value
  if (!el) return
  el.scrollTop += ev.deltaY
}

function onGridMove(ev) {
  const hit = gridHit(ev)
  if (!hit) {
    gridHover.value = null
    hoverBin.value = -1
    hoverRow.value = -1
    scheduleGridDraw()
    return
  }
  hoverBin.value = hit.bi
  hoverRow.value = hit.ri
  const top = hit.c.tasks[0]
  const text = [
    `${hit.c.label}`,
    `${formatTime(hit.binLo, props.trace.timeScale)} – ${formatTime(hit.binHi, props.trace.timeScale)}`,
    `${hit.count} migration${hit.count === 1 ? '' : 's'}`,
    hit.bounces ? `${hit.bounces} lock bounce${hit.bounces === 1 ? '' : 's'}` : null,
    top && hit.count ? `top task: ${top.label}` : null,
    'click to select bin · double-click to spotlight',
  ].filter(Boolean).join('\n')
  gridHover.value = { text }
  const pad = 12
  gridHoverStyle.value = {
    left: `${Math.min(hit.mx + pad, (gridCanvasRef.value?.clientWidth || 200) - 180)}px`,
    top: `${hit.my + pad}px`,
  }
  scheduleGridDraw()
}

function onGridLeave() {
  gridHover.value = null
  hoverBin.value = -1
  hoverRow.value = -1
  scheduleGridDraw()
}

function onGridClick(ev) {
  const hit = gridHit(ev)
  if (hit) selectCorridor(hit.c, hit.bi)
}

function onGridDblClick(ev) {
  const hit = gridHit(ev)
  if (hit && hit.count > 0) spotlightCorridor(hit.c, hit.bi)
}

function applyFocusPair(focus) {
  if (!focus?.fromCore || !focus?.toCore) return
  bounceOnly.value = !!focus.bounceOnly
  nextTick(() => {
    const c = model.value.allCorridors.find(
      x => x.fromCore === focus.fromCore && x.toCore === focus.toCore,
    )
    if (c) {
      if (model.value.groupBySource) expandedGroups.add(c.fromCore)
      expandedCorridors.add(c.label)
      selectCorridor(c)
    }
  })
}

watch(model, () => scheduleGridDraw())
watch([selectedCorridor, highlightBin], () => scheduleGridDraw())

onMounted(() => {
  sidebarCollapsed.value = props.initialMode !== 'chord'
  if (props.focusPair) applyFocusPair(props.focusPair)
  nextTick(() => {
    scheduleGridDraw()
    const pane = gridScrollRef.value
    if (pane && typeof ResizeObserver !== 'undefined') {
      _ro = new ResizeObserver(() => scheduleGridDraw())
      _ro.observe(pane)
    }
  })
})

watch(() => props.focusPair, (f) => { if (f) applyFocusPair(f) })

onBeforeUnmount(() => {
  if (_drawRaf) cancelAnimationFrame(_drawRaf)
  if (_scopeTimer) clearTimeout(_scopeTimer)
  _ro?.disconnect()
})
</script>

<style scoped>
.ci-overlay {
  position: fixed;
  inset: 0;
  z-index: 2000;
  background: transparent;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  pointer-events: none;
}
.ci-dialog {
  pointer-events: auto;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  width: clamp(720px, 92vw, 1100px);
  height: min(680px, 78vh);
  max-height: 78vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  padding: 10px 12px;
}
.ci-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
}
.ci-title {
  font-weight: 600;
  font-size: 14px;
}
.ci-close {
  border: 1px solid var(--border);
  background: var(--tb-bg);
  color: var(--fg);
  border-radius: 4px;
  padding: 4px 10px;
  cursor: pointer;
  font-size: 12px;
}
.ci-toolbar {
  display: flex;
  flex-wrap: nowrap;
  align-items: center;
  gap: 10px;
  margin-top: 8px;
  flex-shrink: 0;
}
.ci-field {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--fg-dim);
}
.ci-field select {
  background: var(--tb-bg);
  color: var(--fg);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 2px 6px;
  font-size: 12px;
}
.ci-bounce-toggle {
  border: 1px solid var(--border);
  background: var(--tb-bg);
  color: var(--fg-dim);
  border-radius: 4px;
  padding: 3px 10px;
  cursor: pointer;
  font-size: 12px;
}
.ci-bounce-toggle.active {
  border-color: #e8a020;
  background: rgba(232, 160, 32, 0.12);
  color: #e8a020;
  font-weight: 600;
}
.ci-sub {
  font-size: 11px;
  color: var(--fg-dim);
  margin-top: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex-shrink: 0;
}
.ci-triage {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 6px;
  padding: 6px 8px;
  background: rgba(232, 160, 32, 0.1);
  border: 1px solid rgba(232, 160, 32, 0.35);
  border-radius: 4px;
  flex-shrink: 0;
}
.ci-triage-text {
  flex: 1;
  font-size: 12px;
  color: var(--fg);
}
.ci-jump {
  border: 1px solid var(--border);
  background: var(--tb-bg);
  color: var(--fg);
  border-radius: 4px;
  padding: 3px 10px;
  cursor: pointer;
  font-size: 12px;
  flex-shrink: 0;
}
.ci-empty {
  padding: 32px;
  text-align: center;
  color: var(--fg-dim);
}
.ci-empty-main {
  flex: 1 1 0;
  min-height: 80px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.ci-workspace.dock-right .ci-empty-main {
  flex: 1 1 0;
  min-width: 0;
}
.ci-task-filter {
  background: var(--tb-bg);
  color: var(--fg);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 2px 6px;
  font-size: 12px;
  width: 120px;
}
.ci-workspace {
  flex: 1 1 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.ci-workspace.dock-right {
  flex-direction: row;
  align-items: stretch;
}
.ci-workspace.dock-right .ci-sidebar {
  width: min(340px, 38%);
  margin-top: 8px;
  margin-left: 8px;
  display: flex;
  flex-direction: column;
}
.ci-workspace.dock-right .ci-sidebar-body {
  grid-template-columns: 1fr;
  height: auto;
  flex: 1 1 0;
  min-height: 0;
}
.ci-workspace.dock-right .ci-main {
  flex: 1 1 0;
  min-width: 0;
}
.ci-main {
  flex: 1 1 0;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(280px, 38%) 1fr;
  gap: 8px;
  margin-top: 8px;
}
.ci-tree-pane, .ci-grid-pane {
  border: 1px solid var(--border);
  border-radius: 4px;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  background: var(--bg);
}
.ci-tree-head,
:deep(.ci-row) {
  display: grid;
  grid-template-columns: 1fr 48px 56px 56px;
  gap: 4px;
  align-items: center;
  font-size: 11px;
  font-family: monospace;
}
.ci-tree-head {
  padding: 4px 6px;
  color: var(--fg-dim);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.ci-tree-scroll {
  overflow: auto;
  flex: 1;
}
:deep(.ci-row) {
  width: 100%;
  text-align: left;
  border: none;
  background: transparent;
  color: var(--fg);
  padding: 3px 6px;
  cursor: pointer;
}
:deep(.ci-row:hover) {
  background: rgba(127, 127, 127, 0.12);
}
:deep(.ci-row.selected) {
  background: rgba(100, 160, 255, 0.18);
}
:deep(.ci-row.selected:hover) {
  background: rgba(100, 160, 255, 0.28);
}
:deep(.ci-task-row) {
  color: var(--fg-dim);
}
.ci-col-num,
:deep(.ci-col-num) {
  text-align: right;
}
:deep(.ci-exp) {
  cursor: pointer;
  user-select: none;
}
:deep(.ci-col-name) {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ci-grid-pane {
  position: relative;
}
.ci-axis-caption {
  flex-shrink: 0;
  padding: 4px 8px 2px;
  font-size: 10px;
  color: var(--fg-dim);
  line-height: 1.35;
}
.ci-grid-wrap {
  position: relative;
  flex: 1 1 0;
  min-height: 0;
}
.ci-grid-body {
  position: absolute;
  inset: 0;
  overflow: auto;
}
.ci-grid-canvas {
  display: block;
  position: sticky;
  top: 0;
  left: 0;
  width: 100%;
  cursor: crosshair;
  z-index: 1;
}
.ci-grid-spacer {
  width: 1px;
  pointer-events: none;
}
.ci-grid-tip {
  position: absolute;
  z-index: 3;
  max-width: 280px;
  padding: 6px 8px;
  border-radius: 4px;
  border: 1px solid var(--border);
  background: var(--bg);
  color: var(--fg);
  font-size: 11px;
  font-family: monospace;
  line-height: 1.4;
  white-space: pre-line;
  pointer-events: none;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.35);
}
.ci-sidebar {
  flex-shrink: 0;
  margin-top: 8px;
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 6px;
}
.ci-sidebar.collapsed {
  padding: 4px 6px;
}
.ci-sidebar-chrome {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.ci-sidebar-toggle {
  border: none;
  background: transparent;
  color: var(--fg-dim);
  font-size: 11px;
  cursor: pointer;
  padding: 2px 0;
}
.ci-dock-field {
  margin-left: auto;
}
.ci-sidebar-body {
  display: grid;
  grid-template-columns: minmax(200px, 1fr) minmax(180px, 0.7fr);
  gap: 8px;
  height: 220px;
  margin-top: 4px;
}
.ci-chord-wrap {
  min-height: 0;
  position: relative;
}
.ci-card {
  border-left: 1px solid var(--border);
  padding-left: 10px;
  font-size: 12px;
  overflow: auto;
}
.ci-card-title {
  font-weight: 600;
  margin-bottom: 6px;
}
.ci-card-line {
  color: var(--fg-dim);
  margin-bottom: 4px;
  line-height: 1.35;
}
.ci-tip {
  margin: 6px 0 0;
  font-size: 11px;
  color: var(--fg-dim);
  height: 15px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex-shrink: 0;
}
.ci-filter-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-top: 6px;
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: 4px;
  font-size: 12px;
  flex-shrink: 0;
}
.ci-show-all {
  border: 1px solid var(--border);
  background: var(--tb-bg);
  color: var(--fg);
  border-radius: 4px;
  padding: 3px 8px;
  cursor: pointer;
  font-size: 12px;
}
.ci-footer {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 8px;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--border);
  flex-shrink: 0;
}
.ci-ai-btn {
  border: 1px solid var(--accent);
  background: var(--accent);
  color: #000;
  font-weight: 600;
  border-radius: 6px;
  padding: 6px 14px;
  font-size: 12px;
  cursor: pointer;
}
.ci-ai-btn:hover {
  filter: brightness(1.08);
}
.ci-group-row {
  font-weight: 600;
}
</style>
