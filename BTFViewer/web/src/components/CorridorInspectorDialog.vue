<template>
  <div
    class="ci-overlay"
    :class="{ 'ci-overlay-free': dialogPos }"
  >
    <div
      ref="dialogEl"
      class="ci-dialog"
      role="dialog"
      aria-modal="false"
      aria-label="Migration corridor inspector"
      :style="dialogStyle"
      @keydown="onDialogKeydown"
    >
      <div
        class="ci-header"
        @pointerdown="onHeaderPointerDown"
      >
        <span class="ci-title">Migration &amp; Corridor Inspector</span>
        <button
          type="button"
          class="app-close-x"
          title="Close"
          aria-label="Close"
          @pointerdown.stop
          @click="emit('close')"
        >×</button>
      </div>

      <div class="ci-overview">
        <div class="ci-overview-headline">{{ overview.headline }}</div>
        <div class="ci-overview-grid">
          <span><strong>Scope</strong> {{ overview.scopeLabel }}</span>
          <span>
            <strong>Load balance</strong> {{ overview.loadBalance }}
            <button
              v-if="!overview.evaluated"
              type="button"
              class="ci-link-btn"
              @click="emit('open-load-balance')"
            >
              Open load-balance details
            </button>
          </span>
          <span><strong>Migrations</strong> {{ overview.migrations.toLocaleString() }} ({{ overview.migrationRateLabel }})</span>
          <span>
            <strong>Most affected task</strong>
            {{ overview.mostAffectedTask
              ? `${overview.mostAffectedTask.label} (${overview.mostAffectedShare.toFixed(0)}%)`
              : '—' }}
          </span>
          <span><strong>Hottest path</strong> {{ overview.hottestPath }}</span>
          <span :title="overview.mainConcernDetail || undefined">
            <strong>Main concern</strong> {{ overview.mainConcern }}
          </span>
        </div>
      </div>

      <div class="ci-toolbar">
        <label class="ci-field ci-field-scope">
          Analysis Scope
          <DomSelect
            v-model="analysisMode"
            :options="analysisModeOptions"
          />
        </label>
        <label class="ci-field">
          Show
          <DomSelect
            v-model="topN"
            :options="topNOptions"
          />
        </label>
        <button
          v-if="traceHasBounces"
          type="button"
          class="ci-bounce-toggle"
          :class="{ active: bounceOnly }"
          @click="bounceOnly = !bounceOnly"
        >
          {{ bounceOnly ? 'Handoff suspects only' : 'All Migrations' }}
        </button>
        <label class="ci-field ci-field-dir">
          Direction
          <DomSelect
            v-model="directionMode"
            :options="directionModeOptions"
          />
        </label>
        <label class="ci-field">
          Task filter
          <input
            v-model.trim="taskQuery"
            type="search"
            class="ci-task-filter"
            placeholder="Filter paths by task name or ID"
          >
        </label>
      </div>

      <div
        class="ci-scope-banner"
        :class="analysisScope.scoped ? 'ci-scope-viewport' : 'ci-scope-full'"
      >
        <span class="ci-scope-badge">{{ analysisScope.label }}</span>
        <span class="ci-scope-detail">{{ analysisScope.detail }}</span>
      </div>

      <div class="ci-filter-status">
        <span>Inspector filters: {{ inspectorFilterLabel }}</span>
        <span>Timeline filter: {{ timelineFilterLabel }}</span>
        <button
          type="button"
          class="ci-show-all"
          :disabled="!selectedCorridor"
          @click="filterInspectorFromSelection"
        >
          Filter Inspector
        </button>
        <button
          type="button"
          class="ci-show-all"
          :disabled="!selectedCorridor"
          @click="filterTimelineFromSelection"
        >
          Filter Timeline
        </button>
        <button
          type="button"
          class="ci-show-all"
          :disabled="!hasInspectorFilters"
          @click="clearInspectorFilters"
        >
          Clear Inspector filters
        </button>
        <button
          type="button"
          class="ci-show-all"
          :disabled="!taskFilterActive"
          @click="emit('clearFilter')"
        >
          Return timeline to all tasks
        </button>
      </div>

      <div class="ci-workspace">
        <div
          v-if="!model.hasData"
          class="ci-empty ci-empty-main"
        >
          {{ taskQuery ? 'No corridors match this task filter.' : 'No migrations in scope.' }}
        </div>
        <div
          v-else
          ref="mainRef"
          class="ci-main"
        >
          <div
            class="ci-tree-pane"
            :style="treePaneStyle"
          >
            <div
              class="ci-tree-head"
              :style="{ gridTemplateColumns: treeGridCols }"
            >
              <div
                v-for="(col, i) in treeCols"
                :key="col.key"
                class="ci-head-cell"
                :class="col.key === 'label' ? 'ci-col-name' : 'ci-col-num'"
              >
                <button
                  type="button"
                  :class="treeSortClass(col.key)"
                  :title="col.tip || ('Sort by ' + col.label)"
                  @click="onHeadClick(col.key)"
                >{{ col.label }}</button>
                <span
                  class="ci-col-resizer"
                  title="Resize column"
                  @pointerdown.stop.prevent="startColResize($event, i)"
                />
              </div>
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
                    <span
                      v-for="col in treeNumCols"
                      :key="col.key"
                      class="ci-col-num"
                    >{{ corridorTreeCell(g, col.key, 'group') }}</span>
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
                        @show-events="showEvents(c)"
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
                    @show-events="showEvents(c)"
                  />
                </div>
              </template>
            </div>
          </div>

          <div
            class="ci-split-handle"
            title="Resize panes"
            @pointerdown.prevent="startPaneResize($event, 0)"
          />

          <div
            class="ci-grid-pane"
            :style="paneFlex(1)"
          >
            <div class="ci-heatmap-meta">
              <div class="ci-axis-caption">
                {{ heatmapTitle }}
              </div>
              <div class="ci-heatmap-legend">
                Color: migration count · Hatching: synchronization handoff suspects ≥ {{ handoffHatchPct }}%
              </div>
              <div class="ci-bin-summary">
                {{ selectedBinSummary || 'Empty bins: no migrations in that interval' }}
              </div>
            </div>
            <div class="ci-grid-wrap">
              <div
                ref="gridScrollRef"
                class="ci-grid-body"
                tabindex="0"
                @scroll="onGridScroll"
                @keydown="onGridKeydown"
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
          <div
            class="ci-split-handle"
            title="Resize panes"
            @pointerdown.prevent="startPaneResize($event, 1)"
          />
          <div
            class="ci-right-pane"
            :style="paneFlex(2)"
          >
            <div class="ci-right-tabs">
              <button
                type="button"
                class="ci-tab"
                :class="{ active: rightPane === 'topology' }"
                @click="rightPane = 'topology'"
              >
                Topology
              </button>
              <button
                type="button"
                class="ci-tab"
                :class="{ active: rightPane === 'info' }"
                @click="rightPane = 'info'"
              >
                Path info
              </button>
            </div>
            <div
              v-if="rightPane === 'topology'"
              class="ci-topology"
            >
              <MiniChordPanel
                :cores="model.filteredMatrix.cores"
                :grid="model.filteredMatrix.grid"
                :focus-corridor="selectedCorridor"
                :focus-cores="focusCoreIndices"
                :direction-mode="directionMode"
                @select-core="onChordSelectCore"
                @select-pair="onChordSelectPair"
                @select-corridor="onChordSelectCorridor"
                @spotlight-corridor="onChordShowEvents"
                @hover-info="chordHover = $event"
              />
            </div>
            <div
              v-else
              class="ci-info-pane"
            >
              <div
                v-if="selectedCorridor"
                class="ci-actions"
              >
                <span class="ci-actions-label">{{ selectedPathLabel }} selected</span>
                <div class="ci-actions-row">
                  <button
                    type="button"
                    class="ci-jump"
                    @click="showEventsFromSelection"
                  >
                    Show events
                  </button>
                  <button
                    type="button"
                    class="ci-jump"
                    @click="filterTimelineFromSelection"
                  >
                    Filter timeline
                  </button>
                  <button
                    type="button"
                    class="ci-jump"
                    :disabled="!selectedTaskOrPrimary"
                    @click="inspectSelectedTask"
                  >
                    Inspect task
                  </button>
                  <button
                    type="button"
                    class="ci-jump"
                    @click="queryAi('path')"
                  >
                    Ask AI
                  </button>
                </div>
              </div>
              <div class="ci-card ci-evidence">
                <template v-if="evidenceCard">
                  <div class="ci-card-body">
                    <div class="ci-card-title">{{ evidenceCard.title }}</div>
                    <div class="ci-card-text">{{ evidenceLinesText }}</div>
                    <div class="ci-card-block">
                      <strong>Assessment</strong>
                      {{ evidenceCard.assessment }}
                    </div>
                    <div class="ci-card-block">
                      <strong>Evidence quality</strong>
                      Direct: {{ evidenceCard.evidenceQuality.direct }}.
                      Correlated: {{ evidenceCard.evidenceQuality.correlated }}.
                      {{ evidenceCard.evidenceQuality.limitation }}
                    </div>
                  </div>
                  <div class="ci-actions-row ci-card-actions">
                    <button
                      type="button"
                      class="ci-jump"
                      @click="showEventsFromSelection"
                    >
                      Show on timeline
                    </button>
                    <button
                      v-if="evidenceCard.task"
                      type="button"
                      class="ci-jump"
                      @click="inspectSelectedTask"
                    >
                      Inspect {{ evidenceCard.task.label }}
                    </button>
                    <button
                      type="button"
                      class="ci-jump"
                      @click="queryAi('path')"
                    >
                      Ask AI
                    </button>
                  </div>
                </template>
                <div
                  v-else
                  class="ci-card-line"
                >
                  Select a core path to inspect ping-pong, dwell, and handoff suspects.
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="ci-footer">
        <button
          type="button"
          class="ci-ai-btn"
          :title="aiEnabled
            ? 'Open the AI Assistant with structured migration context'
            : 'Enable AI Assistant in Settings → AI'"
          @click="queryAi('path')"
        >
          Investigate with AI
        </button>
        <div class="ci-ai-choices">
          <button
            type="button"
            class="ci-show-all"
            @click="queryAi('path')"
          >
            Investigate this path
          </button>
          <button
            type="button"
            class="ci-show-all"
            @click="queryAi('burst')"
          >
            Explain this migration burst
          </button>
          <button
            type="button"
            class="ci-show-all"
            @click="queryAi('pingpong')"
          >
            Verify possible ping-pong
          </button>
          <button
            type="button"
            class="ci-show-all"
            @click="queryAi('compare')"
          >
            Compare with another trace
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, defineComponent, h, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import DomSelect from './DomSelect.vue'
import { formatTime } from '../renderer/TimelineRenderer.js'
import {
  applyCorridorDirectionFilter,
  applyCorridorSort,
  applyCorridorTaskFilter,
  applyCorridorTopNFilter,
  buildCorridorAiContext,
  buildCorridorEvidence,
  buildCorridorInspectorModel,
  buildCorridorOverview,
  CORRIDOR_HANDOFF_HATCH_PCT,
  CORRIDOR_TREE_COLS,
  CI_SPLIT_RATIO,
  CI_SPLIT_PANE_MIN,
  CI_TREE_COL_MIN,
  corridorTreeCell,
  corridorTreeColDefaults,
  defaultCorridorTopN,
  heatmapBinRange,
  inspectorAnalysisScope,
  traceHasCoreBounceHolds,
} from '../utils/migrationAnalysis.js'
import { sortHeaderClass } from '../utils/statsTableSort.js'
import MiniChordPanel from './MiniChordPanel.vue'
import { loadSettings, saveSettings } from '../utils/settingsStore.js'

const CorridorRow = defineComponent({
  name: 'CorridorRow',
  props: {
    corridor: { type: Object, required: true },
    selected: Boolean,
    selectedTaskMk: { type: String, default: null },
    expanded: Boolean,
  },
  emits: ['toggle', 'select', 'pick-task', 'show-events'],
  setup(props, { emit }) {
    const numCols = CORRIDOR_TREE_COLS.filter((c) => c.key !== 'label')
    return () => {
      const c = props.corridor
      const rows = [
        h('button', {
          type: 'button',
          class: ['ci-row', props.selected && !props.selectedTaskMk ? 'selected' : ''],
          onClick: () => emit('select'),
          onDblclick: () => emit('show-events'),
          onKeydown: (e) => {
            if (e.key === 'Enter') { e.preventDefault(); emit('select') }
            if (e.key === ' ') { e.preventDefault(); emit('toggle') }
          },
        }, [
          h('span', { class: 'ci-col-name' }, [
            h('span', {
              class: 'ci-exp',
              onClick: (e) => { e.stopPropagation(); emit('toggle') },
            }, props.expanded ? '▼' : '▶'),
            ` ${c.label}`,
          ]),
          ...numCols.map((col) => h(
            'span', { class: 'ci-col-num' }, corridorTreeCell(c, col.key),
          )),
        ]),
      ]
      if (props.expanded) {
        for (const t of c.tasks) {
          rows.push(h('button', {
            type: 'button',
            class: ['ci-row', 'ci-task-row', props.selectedTaskMk === t.mk ? 'selected' : ''],
            onDblclick: () => emit('show-events'),
            onClick: () => emit('pick-task', t),
            onKeydown: (e) => {
              if (e.key === 'Enter') { e.preventDefault(); emit('pick-task', t) }
            },
          }, [
            h('span', { class: 'ci-col-name' }, `    └── ${t.label}`),
            ...numCols.map((col) => h(
              'span',
              { class: 'ci-col-num' },
              corridorTreeCell(t, col.key, 'task'),
            )),
          ]))
        }
      }
      return h('div', { class: 'ci-corridor-block' }, rows)
    }
  },
})

const props = defineProps({
  trace: { type: Object, required: true },
  cursors: { type: Array, default: () => [] },
  viewport: { type: Object, default: null },
  taskFilterActive: { type: Boolean, default: false },
  taskFilterLabel: { type: String, default: null },
  taskFilterCount: { type: Number, default: 0 },
  focusPair: { type: Object, default: null },
  /** 'chord'/'topology' selects the Topology pane; heatmap click selects Path info */
  initialMode: { type: String, default: 'heatmap' },
  aiEnabled: { type: Boolean, default: true },
})

const emit = defineEmits([
  'close', 'spotlight', 'clearFilter', 'jump', 'query-ai',
  'inspect-task', 'open-load-balance',
])

const GRID_ROW_H = 22
const GRID_LABEL_W = 78
const GRID_HEAD_H = 28
const GRID_FOOT_H = 16

const bounceOnly = ref(false)
const topN = ref(0)
const topNOptions = [
  { value: 5, label: 'Top 5' },
  { value: 10, label: 'Top 10' },
  { value: 25, label: 'Top 25' },
  { value: 0, label: 'All paths' },
]
const sortBy = ref('rate')
const sortDesc = ref(true)
const treeCols = CORRIDOR_TREE_COLS
const treeNumCols = CORRIDOR_TREE_COLS.filter((c) => c.key !== 'label')
const TREE_SORT_COLS = CORRIDOR_TREE_COLS.map((c) => c.key)
const paneFr = ref([...CI_SPLIT_RATIO])
const treeColW = ref(corridorTreeColDefaults())
const treeGridCols = computed(() => treeColW.value.map((w) => `${w}px`).join(' '))
const treeMinWidth = computed(() => treeColW.value.reduce((a, b) => a + b, 0))
const mainRef = ref(null)
let _layoutSaveTimer = 0
let _colDrag = null
let _paneDrag = null
let _ignoreHeadClick = false

function paneFlex(i) {
  return {
    flexGrow: paneFr.value[i],
    flexShrink: 1,
    flexBasis: '0px',
    minWidth: `${CI_SPLIT_PANE_MIN}px`,
  }
}

const treePaneStyle = computed(() => ({
  ...paneFlex(0),
  '--ci-tree-cols': treeGridCols.value,
  '--ci-tree-min': `${treeMinWidth.value}px`,
}))

function persistInspectorLayout(immediate = false) {
  const write = () => {
    const s = loadSettings()
    s.inspectorSplit = [...paneFr.value]
    s.inspectorTreeCols = [...treeColW.value]
    saveSettings(s)
  }
  clearTimeout(_layoutSaveTimer)
  if (immediate) {
    write()
    return
  }
  _layoutSaveTimer = window.setTimeout(write, 250)
}

function loadInspectorLayout() {
  const s = loadSettings()
  if (Array.isArray(s.inspectorSplit) && s.inspectorSplit.length === 3) {
    paneFr.value = s.inspectorSplit.map((n) => Math.max(0.25, Number(n) || 1))
  }
  if (Array.isArray(s.inspectorTreeCols) && s.inspectorTreeCols.length === treeCols.length) {
    treeColW.value = s.inspectorTreeCols.map((n) => (
      Math.max(CI_TREE_COL_MIN, Math.min(800, Number(n) || CI_TREE_COL_MIN))
    ))
  }
}

function toggleTreeSort(key) {
  if (sortBy.value === key) sortDesc.value = !sortDesc.value
  else {
    sortBy.value = key
    sortDesc.value = key !== 'label'
  }
}

function onHeadClick(key) {
  if (_ignoreHeadClick) {
    _ignoreHeadClick = false
    return
  }
  toggleTreeSort(key)
}

function startColResize(ev, index) {
  const startX = ev.clientX
  const startW = treeColW.value[index]
  let moved = false
  _colDrag = {
    move(e) {
      const w = Math.max(CI_TREE_COL_MIN, startW + (e.clientX - startX))
      if (Math.abs(e.clientX - startX) > 2) moved = true
      const next = [...treeColW.value]
      next[index] = w
      treeColW.value = next
    },
    up() {
      if (moved) _ignoreHeadClick = true
      persistInspectorLayout(true)
    },
  }
  window.addEventListener('pointermove', onLayoutPointerMove)
  window.addEventListener('pointerup', onLayoutPointerUp)
}

function startPaneResize(ev, handle) {
  const main = mainRef.value
  if (!main) return
  const startX = ev.clientX
  const start = [...paneFr.value]
  const total = start[0] + start[1] + start[2]
  const width = Math.max(1, main.clientWidth)
  _paneDrag = {
    move(e) {
      const dFr = ((e.clientX - startX) / width) * total
      const left = Math.max(0.25, start[handle] + dFr)
      const right = Math.max(0.25, start[handle + 1] - dFr)
      const next = [...start]
      next[handle] = left
      next[handle + 1] = right
      paneFr.value = next
    },
    up() {
      persistInspectorLayout(true)
    },
  }
  window.addEventListener('pointermove', onLayoutPointerMove)
  window.addEventListener('pointerup', onLayoutPointerUp)
}

function onLayoutPointerMove(e) {
  _colDrag?.move(e)
  _paneDrag?.move(e)
}

function onLayoutPointerUp() {
  window.removeEventListener('pointermove', onLayoutPointerMove)
  window.removeEventListener('pointerup', onLayoutPointerUp)
  _colDrag?.up()
  _paneDrag?.up()
  _colDrag = null
  _paneDrag = null
}

function treeSortClass(col) {
  return sortHeaderClass(
    { col: TREE_SORT_COLS.includes(sortBy.value) ? sortBy.value : null,
      dir: sortDesc.value ? -1 : 1 },
    col,
  )
}

watch(sortBy, (key, prev) => {
  if (key !== prev) sortDesc.value = key !== 'label'
})
const analysisMode = ref('auto')
const analysisModeOptions = computed(() => [
  { value: 'auto', label: 'Follow zoom' },
  { value: 'full', label: 'Full Trace' },
  { value: 'viewport', label: 'Viewport' },
  { value: 'cursor', label: 'Cursor C1–Cn', disabled: !analysisScope.value.canCursor },
])
const directionMode = ref('all')
const directionModeOptions = [
  { value: 'all', label: 'All' },
  { value: 'egress', label: 'Egress Only' },
  { value: 'ingress', label: 'Ingress Only' },
]
const taskQuery = ref('')
const rightPane = ref('topology')
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
const dialogEl = ref(null)
const dialogPos = ref(null)
const gridViewH = ref(200)
const gridScrollTop = ref(0)
let _drawRaf = 0
let _ro = null
let _drag = null

watch(() => props.trace, (t) => {
  bounceOnly.value = false
  selectedCorridor.value = null
  selectedTaskMk.value = null
  focusCoreIndices.value = []
  if (t) {
    t._lockBounceNs = undefined
    topN.value = defaultCorridorTopN(t.coreNames?.length || 0)
  }
}, { immediate: true })

const analysisScope = computed(() => inspectorAnalysisScope(
  analysisMode.value,
  props.cursors,
  props.trace?.timeMin,
  props.trace?.timeMax,
  props.trace?.timeScale,
  formatTime,
  props.viewport,
))

watch(() => analysisScope.value.canCursor, (ok) => {
  if (!ok && analysisMode.value === 'cursor') analysisMode.value = 'auto'
})

const traceHasBounces = computed(() => traceHasCoreBounceHolds(props.trace))
const handoffHatchPct = CORRIDOR_HANDOFF_HATCH_PCT

const baseModel = computed(() => {
  const { lo, hi } = analysisScope.value
  return buildCorridorInspectorModel(props.trace, lo, hi, {
    bounceOnly: bounceOnly.value,
    topPct: 100,
    timeBins: 32,
  })
})

const model = computed(() => {
  const q = String(taskQuery.value || '').trim()
  const scoped = q
    ? applyCorridorTaskFilter(baseModel.value, q)
    : applyCorridorTopNFilter(baseModel.value, topN.value)
  const directed = applyCorridorDirectionFilter(
    scoped,
    directionMode.value,
    selectedCorridor.value,
  )
  return applyCorridorSort(directed, sortBy.value, sortDesc.value)
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

const overview = computed(() => buildCorridorOverview(
  props.trace,
  model.value,
  analysisScope.value,
))

const resolvedCorridor = computed(() => {
  const sel = selectedCorridor.value
  if (!sel) return null
  return model.value.corridors.find(
    x => x.fromCore === sel.fromCore && x.toCore === sel.toCore,
  ) || model.value.allCorridors.find(
    x => x.fromCore === sel.fromCore && x.toCore === sel.toCore,
  ) || null
})

const selectedTask = computed(() => {
  const c = resolvedCorridor.value
  if (!c || !selectedTaskMk.value) return null
  return c.tasks.find(t => t.mk === selectedTaskMk.value) || null
})

const selectedTaskOrPrimary = computed(() => selectedTask.value || resolvedCorridor.value?.primaryTask || null)

const selectedPathLabel = computed(() => {
  const c = resolvedCorridor.value
  if (!c) return ''
  return `${c.fromCore} → ${c.toCore}`
})

const selectedBinRange = computed(() => {
  const c = resolvedCorridor.value
  const bi = highlightBin.value
  if (!c || bi == null || bi < 0) return null
  const { tMin, binW, timeBins, tMax } = model.value
  return { bi, ...heatmapBinRange(tMin, binW, timeBins, tMax, bi), timeBins }
})

const selectedBinSummary = computed(() => {
  const c = resolvedCorridor.value
  const r = selectedBinRange.value
  if (!c || !r) return ''
  const n = c.bins?.[r.bi] || 0
  const b = c.bounceBins?.[r.bi] || 0
  const lo = formatTime(r.binLo, props.trace.timeScale)
  const hi = formatTime(r.binHi, props.trace.timeScale)
  return `Selected: jump:${r.binLo}–jump:${r.binHi} · ${lo}–${hi} · ${n} migration${n === 1 ? '' : 's'}${b ? `, ${b} handoff` : ''}`
})

const heatmapTitle = computed(() => (
  `Migration activity over time — ${analysisScope.value.label}, trace unit: ${analysisScope.value.unit}`
))

const inspectorFilterParts = computed(() => {
  const parts = []
  if (taskQuery.value) parts.push(`Task ${taskQuery.value}`)
  if (directionMode.value === 'egress') parts.push('Egress only')
  if (directionMode.value === 'ingress') parts.push('Ingress only')
  if (bounceOnly.value) parts.push('Handoff suspects only')
  return parts
})

const inspectorFilterLabel = computed(() => inspectorFilterParts.value.join(' · ') || 'None')
const hasInspectorFilters = computed(() => inspectorFilterParts.value.length > 0)
const timelineFilterLabel = computed(() => (
  props.taskFilterActive
    ? (props.taskFilterLabel || `${props.taskFilterCount} tasks`)
    : 'None'
))

const evidenceCard = computed(() => {
  const c = resolvedCorridor.value
  if (!c) return null
  const r = selectedBinRange.value
  return buildCorridorEvidence(c, {
    selectedTask: selectedTask.value,
    timeScale: props.trace.timeScale,
    formatTimeFn: formatTime,
    binLo: r?.binLo,
    binHi: r?.binHi,
    scopeLabel: analysisScope.value.label,
  })
})

const evidenceLinesText = computed(() => {
  const ev = evidenceCard.value
  if (!ev) return ''
  return (ev.lines || []).map(l => `${l.key}:  ${l.value}`).join('\n')
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
  showEvents(c, c.peakBin ?? null)
}

function showEvents(c, binIndex = null) {
  if (!c) return
  const { tMin, binW, timeBins, tMax } = model.value
  let binLo = tMin
  let binHi = tMax
  const bi = binIndex != null && binIndex >= 0 ? binIndex : highlightBin.value
  if (bi != null && bi >= 0) {
    const r = heatmapBinRange(tMin, binW, timeBins, tMax, bi)
    binLo = r.binLo
    binHi = r.binHi
  } else if (c.peakBin != null) {
    const r = heatmapBinRange(tMin, binW, timeBins, tMax, c.peakBin)
    binLo = r.binLo
    binHi = r.binHi
  }
  emit('jump', {
    binLo,
    binHi,
    lockTaskKey: selectedTaskMk.value || c.primaryTask?.mk || null,
    pairLabel: c.label,
    enableCpuLoad: true,
  })
}

function spotlightCorridor(c, binIndex = null) {
  if (!c) return
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
  const picked = selectedTask.value
  const mergeKeys = picked ? [picked.mk] : c.tasks.map(t => t.mk)
  emit('spotlight', {
    fromCore: c.fromCore,
    toCore: c.toCore,
    pairLabel: picked ? `${c.label} · ${picked.label}` : c.label,
    binLo,
    binHi,
    mergeKeys,
    lockTaskKey: picked?.mk || c.primaryTask?.mk || null,
    enableCpuLoad: true,
  })
}

function showEventsFromSelection() {
  const c = resolvedCorridor.value
  if (c) showEvents(c, highlightBin.value >= 0 ? highlightBin.value : null)
}

function filterTimelineFromSelection() {
  const c = resolvedCorridor.value
  if (c) spotlightCorridor(c, highlightBin.value >= 0 ? highlightBin.value : null)
}

function filterInspectorFromSelection() {
  const t = selectedTaskOrPrimary.value
  if (t?.label) taskQuery.value = t.label
}

function clearInspectorFilters() {
  taskQuery.value = ''
  directionMode.value = 'all'
  bounceOnly.value = false
}

function inspectSelectedTask() {
  const t = selectedTaskOrPrimary.value
  if (t?.mk) emit('inspect-task', t.mk)
}

function queryAi(action = 'path') {
  const extra = buildCorridorAiContext({
    scope: analysisScope.value,
    corridor: resolvedCorridor.value,
    task: selectedTaskOrPrimary.value,
    bin: selectedBinSummary.value ? { label: selectedBinSummary.value } : null,
    overview: overview.value,
    inspectorFilters: inspectorFilterLabel.value,
    timeScale: props.trace?.timeScale,
  })
  const hints = {
    path: 'Investigate this path. Do not filter the timeline or change cursors unless asked.',
    burst: 'Explain this migration burst. Use the selected time bin if one is selected.',
    pingpong: 'Verify possible ping-pong. Cite bidirectional movement and dwell; do not declare a root cause.',
    compare: 'Compare with another trace if two traces are open; otherwise say another trace is required.',
  }
  emit('query-ai', {
    template: 'migrations',
    extra: `${extra}\n\n${hints[action] || hints.path}`,
    action,
  })
}

function onDialogKeydown(ev) {
  if (ev.key === 'Enter' && resolvedCorridor.value && ev.target === ev.currentTarget) {
    ev.preventDefault()
    selectCorridor(resolvedCorridor.value, highlightBin.value)
  }
}

function clampDialogPos(x, y) {
  const el = dialogEl.value
  const w = el?.offsetWidth || 0
  const h = el?.offsetHeight || 0
  const pad = 8
  const maxX = Math.max(pad, window.innerWidth - w - pad)
  const maxY = Math.max(pad, window.innerHeight - h - pad)
  return {
    x: Math.min(Math.max(pad, x), maxX),
    y: Math.min(Math.max(pad, y), maxY),
  }
}

const dialogStyle = computed(() => {
  if (!dialogPos.value) return {}
  return {
    position: 'fixed',
    left: `${dialogPos.value.x}px`,
    top: `${dialogPos.value.y}px`,
    margin: '0',
  }
})

function onHeaderPointerDown(ev) {
  if (ev.pointerType === 'mouse' && ev.button !== 0) return
  if (ev.target.closest('button')) return
  const el = dialogEl.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  _drag = { dx: ev.clientX - rect.left, dy: ev.clientY - rect.top }
  dialogPos.value = { x: rect.left, y: rect.top }
  window.addEventListener('pointermove', onDialogPointerMove)
  window.addEventListener('pointerup', onDialogPointerUp)
  ev.preventDefault()
}

function onDialogPointerMove(ev) {
  if (!_drag) return
  dialogPos.value = clampDialogPos(ev.clientX - _drag.dx, ev.clientY - _drag.dy)
}

function onDialogPointerUp() {
  _drag = null
  window.removeEventListener('pointermove', onDialogPointerMove)
  window.removeEventListener('pointerup', onDialogPointerUp)
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

function onChordShowEvents(payload) {
  const c = model.value.allCorridors.find(
    x => x.fromCore === payload.fromCore && x.toCore === payload.toCore,
  )
  if (c) showEvents(c)
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
  const sample = formatTime(tMax, props.trace.timeScale)
  const slot = Math.max(36, ctx.measureText(sample).width + 10)
  const axisW = Math.max(1, plotW - 8)
  const nLab = Math.max(2, Math.min(7, Math.floor(axisW / slot)))
  ctx.save()
  ctx.beginPath()
  ctx.rect(labelW, 0, plotW, headH)
  ctx.clip()
  for (let t = 0; t < nLab; t++) {
    const frac = nLab > 1 ? t / (nLab - 1) : 0
    const ns = Math.round(tMin + frac * (tMax - tMin))
    const x = labelW + frac * axisW
    ctx.textAlign = frac < 0.05 ? 'left' : frac > 0.95 ? 'right' : 'center'
    ctx.fillText(formatTime(ns, props.trace.timeScale), x, 12)
  }
  ctx.restore()
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
        if (bounceRatio >= CORRIDOR_HANDOFF_HATCH_PCT / 100) {
          ctx.fillStyle = `rgba(232,120,32,${0.2 + 0.55 * intensity})`
          ctx.fillRect(x + 0.5, y + 2, cellW - 1, rowH - 4)
          // Diagonal hatch reinforces bounce vs normal (colorblind-safe).
          ctx.save()
          ctx.beginPath()
          ctx.rect(x + 0.5, y + 2, cellW - 1, rowH - 4)
          ctx.clip()
          ctx.strokeStyle = `rgba(20,20,20,${0.35 + 0.35 * intensity})`
          ctx.lineWidth = 1
          const x0 = x + 0.5
          const y0 = y + 2
          const x1 = x0 + cellW - 1
          const y1 = y0 + rowH - 4
          for (let s = -rowH; s < cellW + rowH; s += 3) {
            ctx.beginPath()
            ctx.moveTo(x0 + s, y1)
            ctx.lineTo(x0 + s + (y1 - y0), y0)
            ctx.stroke()
          }
          ctx.restore()
        } else {
          ctx.fillStyle = `rgba(70,130,220,${0.15 + 0.75 * intensity})`
          ctx.fillRect(x + 0.5, y + 2, cellW - 1, rowH - 4)
        }
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
  if (hoverBin.value >= 0) {
    const hx = labelW + hoverBin.value * cellW
    ctx.fillStyle = 'rgba(91, 155, 213, 0.35)'
    ctx.fillRect(hx, h - footH, cellW, footH)
  }
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
  const plotBottom = rect.height - GRID_FOOT_H
  if (my < GRID_HEAD_H) return null
  const plotMy = my > plotBottom ? plotBottom - 0.5 : my
  const contentY = scroll.scrollTop + plotMy
  const ri = Math.floor((contentY - GRID_HEAD_H) / GRID_ROW_H)
  const bi = Math.floor((mx - GRID_LABEL_W) / cellW)
  if (ri < 0 || ri >= corridors.length || bi < 0 || bi >= timeBins) return null
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
    hit.bounces ? `${hit.bounces} handoff suspect${hit.bounces === 1 ? '' : 's'}` : null,
    top && hit.count ? `top task: ${top.label}` : null,
    hit.count ? 'click to select bin · double-click to show events' : 'empty bin — no migrations in this interval',
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
  if (hit) {
    selectCorridor(hit.c, hit.bi)
    rightPane.value = 'info'
  }
}

function onGridDblClick(ev) {
  const hit = gridHit(ev)
  if (hit) showEvents(hit.c, hit.bi)
}

function onGridKeydown(ev) {
  const corridors = visibleCorridors()
  if (!corridors.length) return
  const selected = resolvedCorridor.value
  let ri = selected ? corridors.findIndex(c => c.fromCore === selected.fromCore && c.toCore === selected.toCore) : 0
  if (ri < 0) ri = 0
  let bi = highlightBin.value >= 0 ? highlightBin.value : (corridors[ri]?.peakBin ?? 0)
  const bins = model.value.timeBins || 32
  if (ev.key === 'ArrowLeft') {
    ev.preventDefault()
    bi = Math.max(0, bi - 1)
    selectCorridor(corridors[ri], bi)
    rightPane.value = 'info'
  } else if (ev.key === 'ArrowRight') {
    ev.preventDefault()
    bi = Math.min(bins - 1, bi + 1)
    selectCorridor(corridors[ri], bi)
    rightPane.value = 'info'
  } else if (ev.key === 'ArrowUp') {
    ev.preventDefault()
    ri = Math.max(0, ri - 1)
    selectCorridor(corridors[ri], bi)
    rightPane.value = 'info'
  } else if (ev.key === 'ArrowDown') {
    ev.preventDefault()
    ri = Math.min(corridors.length - 1, ri + 1)
    selectCorridor(corridors[ri], bi)
    rightPane.value = 'info'
  } else if (ev.key === 'Enter') {
    ev.preventDefault()
    selectCorridor(corridors[ri], bi)
    rightPane.value = 'info'
  } else if (ev.key === ' ') {
    ev.preventDefault()
    toggleCorridor(corridors[ri])
  }
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
watch(rightPane, (pane) => {
  if (pane === 'topology') nextTick(() => scheduleGridDraw())
})

onMounted(() => {
  loadInspectorLayout()
  if (props.initialMode === 'info') rightPane.value = 'info'
  else rightPane.value = 'topology'
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
watch(() => props.initialMode, (m) => {
  if (m === 'chord' || m === 'topology') rightPane.value = 'topology'
  else if (m === 'info') rightPane.value = 'info'
})

onBeforeUnmount(() => {
  if (_drawRaf) cancelAnimationFrame(_drawRaf)
  _ro?.disconnect()
  onLayoutPointerUp()
  persistInspectorLayout(true)
  onDialogPointerUp()
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
.ci-overlay-free {
  display: block;
  padding: 0;
}
.ci-dialog {
  pointer-events: auto;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  width: clamp(960px, 96vw, 1440px);
  height: min(840px, 92vh);
  max-height: 92vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  padding: 10px 12px;
  container-type: inline-size;
}
.ci-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
  cursor: grab;
  user-select: none;
}
.ci-header:active {
  cursor: grabbing;
}
.ci-title {
  font-weight: 600;
  font-size: 14px;
}
.ci-toolbar {
  display: flex;
  flex-wrap: nowrap;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
  padding: 2px 0;
  flex-shrink: 0;
  overflow-x: auto;
  min-height: 26px;
}
.ci-toolbar .ci-field :deep(.dom-select) {
  height: 22px;
  min-height: 22px;
  min-width: 90px;
  box-sizing: border-box;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--tb-bg);
  color: var(--fg);
  padding: 0 6px;
  transition: background 0.1s;
}
.ci-toolbar .ci-field :deep(.dom-select):hover:not(.disabled) {
  border-color: var(--accent, #2a6fb2);
  background: rgba(91, 155, 213, 0.18);
}
.ci-toolbar .ci-field-scope :deep(.dom-select) {
  min-width: 128px;
}
.ci-toolbar .ci-field-dir :deep(.dom-select) {
  min-width: 108px;
  width: max-content;
}
.ci-toolbar .ci-field :deep(.dom-select.open) {
  border-color: var(--accent);
}
.ci-toolbar .ci-field :deep(.dom-select-trigger) {
  height: 22px;
  min-height: 22px;
  font-size: 12px;
}
.ci-task-filter {
  height: 22px;
  width: 140px;
  min-width: 140px;
  box-sizing: border-box;
  flex-shrink: 0;
}
.ci-field {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--fg-dim);
  white-space: nowrap;
  flex-shrink: 0;
}
.ci-field select {
  background: var(--tb-bg);
  color: var(--fg);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 2px 6px;
  font-size: 12px;
}
.ci-field :deep(.dom-select) {
  width: auto;
  min-width: 90px;
}
.ci-bounce-toggle {
  border: 1px solid var(--border);
  background: var(--tb-bg);
  color: var(--fg-dim);
  border-radius: 4px;
  padding: 3px 10px;
  cursor: pointer;
  font-size: 12px;
  flex-shrink: 0;
  min-width: 11.6em;
  box-sizing: border-box;
  transition: background 0.1s;
}
.ci-bounce-toggle:hover:not(.active) {
  border-color: var(--accent, #2a6fb2);
  background: rgba(91, 155, 213, 0.18);
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
.ci-scope-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 2px;
  padding: 8px 12px;
  font-size: 11px;
  line-height: 1.35;
  border-radius: 4px;
  flex-shrink: 0;
}
.ci-scope-viewport {
  background: color-mix(in srgb, #ff9800 18%, var(--panel-bg));
  border-left: 4px solid #ff9800;
}
.ci-scope-full {
  background: color-mix(in srgb, var(--fg-dim) 10%, var(--panel-bg));
  border-left: 4px solid var(--fg-dim);
}
.ci-scope-badge {
  flex-shrink: 0;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  font-size: 10px;
  padding: 3px 8px;
  border-radius: 4px;
}
.ci-scope-viewport .ci-scope-badge {
  background: #ff9800;
  color: #1a1200;
}
.ci-scope-full .ci-scope-badge {
  background: var(--border);
  color: var(--fg);
}
.ci-scope-viewport .ci-scope-detail {
  color: color-mix(in srgb, #ff9800 70%, var(--fg));
}
.ci-scope-full .ci-scope-detail {
  color: var(--fg-dim);
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
  transition: background 0.1s;
}
.ci-jump:hover:not(:disabled) {
  border-color: var(--accent, #2a6fb2);
  background: rgba(91, 155, 213, 0.18);
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
  width: 140px;
}
.ci-overview {
  margin-top: 8px;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: 6px;
  flex-shrink: 0;
  font-size: 12px;
}
.ci-overview-headline {
  font-weight: 600;
  margin-bottom: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ci-overview-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 4px 16px;
  color: var(--fg-dim);
}
.ci-overview-grid > span {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.ci-link-btn {
  margin-left: 6px;
  border: 1px solid var(--border);
  background: var(--tb-bg);
  color: var(--fg);
  border-radius: 4px;
  padding: 1px 8px;
  font-size: 11px;
  cursor: pointer;
  transition: background 0.1s;
}
.ci-link-btn:hover {
  border-color: var(--accent, #2a6fb2);
  background: rgba(91, 155, 213, 0.18);
}
.ci-filter-status {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
  font-size: 11px;
  color: var(--fg-dim);
  flex-shrink: 0;
}
.ci-tabs,
.ci-right-tabs {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}
.ci-right-tabs {
  padding: 4px 6px 0;
  border-bottom: 1px solid var(--border);
}
.ci-tab {
  border: 1px solid var(--border);
  background: var(--tb-bg);
  color: var(--fg-dim);
  border-radius: 4px 4px 0 0;
  padding: 4px 12px;
  font-size: 12px;
  cursor: pointer;
  transition: background 0.1s;
}
.ci-tab:hover:not(.active) {
  border-color: var(--accent, #2a6fb2);
  background: rgba(91, 155, 213, 0.18);
}
.ci-tab.active {
  color: var(--fg);
  font-weight: 600;
  border-bottom-color: var(--bg);
}
.ci-heatmap-meta {
  flex-shrink: 0;
  padding: 4px 8px 2px;
  font-size: 10px;
  line-height: 1.35;
  color: var(--fg-dim);
}
.ci-heatmap-meta .ci-axis-caption,
.ci-heatmap-meta .ci-heatmap-legend,
.ci-heatmap-meta .ci-bin-summary {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  padding: 0;
}
.ci-heatmap-legend,
.ci-bin-summary {
  font-size: 10px;
  line-height: 1.35;
  flex-shrink: 0;
}
.ci-bin-summary {
  color: var(--fg);
}
.ci-topology {
  flex: 1 1 0;
  min-height: 0;
  border: none;
  border-radius: 0;
  margin-top: 0;
}
.ci-info-pane {
  flex: 1 1 0;
  min-height: 0;
  overflow: auto;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.ci-info-pane .ci-evidence {
  flex: 1 1 0;
  min-height: 0;
  max-height: none;
}
.ci-card-text {
  white-space: pre-wrap;
  font-size: 12px;
  line-height: 1.45;
  color: var(--fg);
  margin-bottom: 6px;
}
.ci-right-pane {
  border: 1px solid var(--border);
  border-radius: 4px;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  background: var(--bg);
}
.ci-actions {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 6px;
  margin-top: 0;
  flex-shrink: 0;
}
.ci-actions-label {
  font-size: 12px;
  font-weight: 600;
  margin-right: 0;
}
.ci-actions-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}
.ci-evidence {
  margin-top: 0;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 8px 10px;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.ci-card-body {
  flex: 1 1 0;
  min-height: 0;
  overflow: auto;
}
.ci-card-actions {
  flex-shrink: 0;
  margin-top: auto;
  padding-top: 8px;
}
.ci-card-metric {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  font-size: 12px;
  color: var(--fg-dim);
  margin-bottom: 2px;
}
.ci-card-block {
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.35;
}
.ci-ai-choices {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
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
  display: flex;
  flex-direction: row;
  align-items: stretch;
  gap: 0;
  margin-top: 8px;
}
.ci-split-handle {
  flex: 0 0 6px;
  width: 6px;
  cursor: col-resize;
  position: relative;
  background: transparent;
  z-index: 2;
}
.ci-split-handle::before {
  content: '';
  position: absolute;
  top: 8px;
  bottom: 8px;
  left: 2px;
  width: 2px;
  background: var(--border);
  border-radius: 1px;
}
.ci-split-handle:hover::before {
  background: color-mix(in srgb, var(--accent) 60%, var(--border));
}
.ci-tree-pane, .ci-grid-pane {
  border: 1px solid var(--border);
  border-radius: 4px;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  background: var(--bg);
}
.ci-tree-pane {
  overflow-x: auto;
  overflow-y: hidden;
}
.ci-tree-head,
:deep(.ci-row) {
  display: grid;
  grid-template-columns: var(--ci-tree-cols);
  gap: 0;
  align-items: center;
  font-size: 11px;
  font-family: monospace;
  min-width: var(--ci-tree-min);
}
.ci-tree-head {
  padding: 0;
  color: var(--fg-dim);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.ci-head-cell {
  position: relative;
  min-width: 0;
  display: flex;
  align-items: center;
  min-height: 22px;
  padding: 4px 8px 4px 6px;
  border-right: 1px solid var(--border);
  box-sizing: border-box;
}
.ci-head-cell:last-child {
  border-right: none;
}
.ci-tree-head button {
  margin: 0;
  padding: 0;
  border: none;
  background: transparent;
  color: inherit;
  font: inherit;
  cursor: pointer;
  user-select: none;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  width: 100%;
  text-align: inherit;
}
.ci-col-resizer {
  position: absolute;
  top: 0;
  right: -3px;
  width: 7px;
  bottom: 0;
  cursor: col-resize;
  z-index: 2;
}
.ci-tree-head button:hover {
  color: var(--fg);
}
.ci-tree-head .sort-asc::after,
.ci-tree-head .sort-desc::after {
  font-size: 8px;
  opacity: 0.85;
}
.ci-tree-head .sort-asc::after {
  content: ' ▲';
}
.ci-tree-head .sort-desc::after {
  content: ' ▼';
}
.ci-tree-scroll {
  overflow-x: hidden;
  overflow-y: auto;
  flex: 1;
  min-width: var(--ci-tree-min);
}
:deep(.ci-row) {
  width: 100%;
  text-align: left;
  border: none;
  background: transparent;
  color: var(--fg);
  padding: 3px 0;
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
  padding: 0 6px;
  box-sizing: border-box;
}
.ci-head-cell.ci-col-num button {
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
  padding: 0 6px;
  box-sizing: border-box;
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
  transition: background 0.1s;
}
.ci-show-all:hover:not(:disabled) {
  border-color: var(--accent, #2a6fb2);
  background: rgba(91, 155, 213, 0.28);
}
.ci-show-all:disabled,
.ci-jump:disabled {
  color: #888888;
  opacity: 0.45;
  cursor: default;
}
.ci-footer .ci-show-all:hover:not(:disabled),
.ci-card-actions .ci-jump:hover:not(:disabled) {
  border-color: var(--accent, #2a6fb2);
  background: rgba(91, 155, 213, 0.35);
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
  background: #1a5a9a;
  border-color: #1a5a9a;
  color: #fff;
  filter: none;
}
.ci-group-row {
  font-weight: 600;
}
</style>
