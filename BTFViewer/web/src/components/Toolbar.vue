<template>
  <div
    ref="toolbarEl"
    class="toolbar"
  >
    <!-- Brand / About (web-only) -->
    <button
      class="app-name-btn"
      title="About RTOS BTF Viewer"
      aria-label="About RTOS BTF Viewer"
      @click="emit('showAbout')"
    >
      <span
        class="app-name-icon"
        aria-hidden="true"
        v-html="appIconSvg"
      />
    </button>

    <div class="tb-sep" />

    <!-- Open stays outside overflow so demo live targets always resolve. -->
    <label
      v-if="!useFsaOpen"
      class="tb-btn file-btn"
      data-demo-target="toolbar_open"
      title="Open a BTF trace, demo XML, or .xtf pack (Ctrl+O)"
      aria-label="Open a BTF trace, demo XML, or .xtf pack (Ctrl+O)"
    >
      <svg
        viewBox="0 0 16 16"
        width="16"
        height="16"
        fill="currentColor"
        aria-hidden="true"
      >
        <path
          fill-rule="evenodd"
          :d="IC.open"
        />
      </svg>
      <input
        ref="fileInputRef"
        type="file"
        :accept="OPEN_FILE_ACCEPT"
        multiple
        style="display:none"
        @change="onFileChange"
      >
    </label>
    <button
      v-else
      class="tb-btn"
      data-demo-target="toolbar_open"
      title="Open a BTF trace, demo XML, or .xtf pack (Ctrl+O)"
      aria-label="Open a BTF trace, demo XML, or .xtf pack (Ctrl+O)"
      @click="onOpenClick"
    >
      <svg
        viewBox="0 0 16 16"
        width="16"
        height="16"
        fill="currentColor"
        aria-hidden="true"
      >
        <path
          fill-rule="evenodd"
          :d="IC.open"
        />
      </svg>
    </button>

    <!-- g1: File extras — Snapshot · SVG · Perfetto · Slice -->
    <Teleport
      :to="overflowPanelEl ?? 'body'"
      :disabled="!overflow.g1"
    >
      <div
        :ref="el => setGroupRef('g1', el)"
        class="tb-group"
      >
        <button
          v-if="traceInfo"
          class="tb-btn"
          title="Open snapshot editor (Ctrl+S)"
          aria-label="Open snapshot editor (Ctrl+S)"
          @click="emit('copyScreenshot')"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
            aria-hidden="true"
          >
            <path
              fill-rule="evenodd"
              :d="IC.shot"
            />
          </svg>
        </button>
        <button
          v-if="traceInfo"
          class="tb-btn"
          title="Save viewport as SVG (Ctrl+Shift+S)"
          @click="emit('exportSvg')"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
            aria-hidden="true"
          >
            <path
              fill-rule="evenodd"
              :d="IC.saveSvg"
            />
          </svg>
        </button>
        <button
          v-if="traceInfo"
          class="tb-btn"
          title="Export Perfetto (Chrome Trace JSON for ui.perfetto.dev) (Ctrl+Shift+E)"
          @click="emit('exportPerfetto')"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
            aria-hidden="true"
          >
            <path
              fill-rule="evenodd"
              :d="IC.perfetto"
            />
          </svg>
        </button>
        <button
          v-if="traceInfo"
          class="tb-btn"
          :class="{ disabled: !rangeEnabled }"
          :disabled="!rangeEnabled"
          title="Save cursor range as BTF (C1–Cn)"
          @click="rangeEnabled && emit('exportSlice')"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
            aria-hidden="true"
          >
            <path
              fill-rule="evenodd"
              :d="IC.exportSlice"
            />
          </svg>
        </button>
        <div class="tb-sep" />
      </div>
    </Teleport>

    <!-- g2: Orientation — Horizontal · Vertical -->
    <Teleport
      :to="overflowPanelEl ?? 'body'"
      :disabled="!overflow.g2"
    >
      <div
        :ref="el => setGroupRef('g2', el)"
        class="tb-group"
      >
        <button
          type="button"
          class="tb-btn"
          :class="{ active: (modelValue.orientation || 'h') === 'h' }"
          title="Horizontal layout — time runs left → right"
          @click="emit('update:modelValue', { ...modelValue, orientation: 'h' })"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
            aria-hidden="true"
          >
            <path
              fill-rule="evenodd"
              :d="IC.horiz"
            />
          </svg>
        </button>
        <button
          type="button"
          class="tb-btn"
          :class="{ active: (modelValue.orientation || 'h') === 'v' }"
          title="Vertical layout — time runs top → bottom"
          @click="emit('update:modelValue', { ...modelValue, orientation: 'v' })"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
            aria-hidden="true"
          >
            <path
              fill-rule="evenodd"
              :d="IC.vert"
            />
          </svg>
        </button>
        <div class="tb-sep" />
      </div>
    </Teleport>

    <!-- g3: Zoom — In · Out · 1:1 · Fit · Range · Find · preset -->
    <Teleport
      :to="overflowPanelEl ?? 'body'"
      :disabled="!overflow.g3"
    >
      <div
        :ref="el => setGroupRef('g3', el)"
        class="tb-group"
      >
        <button
          class="tb-btn"
          title="Zoom in (Ctrl++)"
          @click="emit('zoom', 0.7)"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
            aria-hidden="true"
          >
            <path
              fill-rule="evenodd"
              :d="IC.zin"
            />
          </svg>
        </button>
        <button
          class="tb-btn"
          :class="{ disabled: !zoomOutEnabled }"
          :disabled="!zoomOutEnabled"
          :title="zoomOutEnabled ? 'Zoom out (Ctrl+-)' : 'Already fitted to window'"
          @click="zoomOutEnabled && emit('zoom', 1.43)"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
            aria-hidden="true"
          >
            <path
              fill-rule="evenodd"
              :d="IC.zout"
            />
          </svg>
        </button>
        <button
          v-if="traceInfo"
          class="tb-btn"
          data-demo-target="toolbar_1to1"
          :title="zoom1to1Title"
          :aria-label="zoom1to1Title"
          @click="emit('zoom1to1')"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
            aria-hidden="true"
          >
            <path
              fill-rule="evenodd"
              :d="IC.oneToOne"
            />
          </svg>
        </button>
        <button
          class="tb-btn"
          data-demo-target="toolbar_fit"
          title="Fit Trace — zoom to show the entire trace (Ctrl+0)"
          @click="emit('fit')"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
            aria-hidden="true"
          >
            <path
              fill-rule="evenodd"
              :d="IC.fit"
            />
          </svg>
        </button>
        <button
          v-if="traceInfo"
          class="tb-btn"
          :class="{ disabled: !rangeEnabled }"
          :disabled="!rangeEnabled"
          title="Fit Cursors — zoom to the C1–Cn cursor Scope (Ctrl+R)"
          @click="rangeEnabled && emit('zoomRange')"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
            aria-hidden="true"
          >
            <path
              fill-rule="evenodd"
              :d="IC.expand"
            />
          </svg>
        </button>
        <DomSelect
          class="tb-zoom-preset"
          title="Zoom preset — pick a fixed scale or Fit"
          aria-label="Zoom preset"
          :model-value="zoomPresetValue"
          :options="zoomPresetOptions"
          :disabled="!traceInfo"
          @update:model-value="v => emit('zoomPreset', v)"
        />
        <div class="tb-sep" />
      </div>
    </Teleport>

    <!-- g4: View Mode — Task · Core · Expand All · Load -->
    <Teleport
      :to="overflowPanelEl ?? 'body'"
      :disabled="!overflow.g4"
    >
      <div
        :ref="el => setGroupRef('g4', el)"
        class="tb-group"
      >
        <button
          type="button"
          class="tb-btn tb-btn-labeled"
          data-demo-target="toolbar_task"
          :class="{ active: modelValue.viewMode === 'task' }"
          title="Task View — one row per task, merges across cores"
          @click="emit('update:modelValue', { ...modelValue, viewMode: 'task' })"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
            aria-hidden="true"
          >
            <path
              fill-rule="evenodd"
              :d="IC.task"
            />
          </svg>
          <span class="tb-label">Task</span>
        </button>
        <button
          type="button"
          class="tb-btn tb-btn-labeled"
          data-demo-target="toolbar_core"
          :class="{ active: modelValue.viewMode === 'core' }"
          title="Core View — one expandable row per CPU core"
          @click="emit('update:modelValue', { ...modelValue, viewMode: 'core' })"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
            aria-hidden="true"
          >
            <path
              fill-rule="evenodd"
              :d="IC.core"
            />
          </svg>
          <span class="tb-label">Core</span>
        </button>

        <button
          class="tb-btn"
          :class="{
            active: coresExpanded,
            disabled: modelValue.viewMode !== 'core',
          }"
          :disabled="modelValue.viewMode !== 'core'"
          title="Expand / collapse all cores (only in Core View)"
          @click="modelValue.viewMode === 'core' && toggleExpandAll()"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
            aria-hidden="true"
          >
            <path
              fill-rule="evenodd"
              :d="IC.expandAll"
            />
          </svg>
        </button>

        <button
          type="button"
          class="tb-btn tb-btn-labeled"
          data-demo-target="toolbar_load"
          :class="{ active: modelValue.showCpuLoad !== false }"
          title="Show / hide CPU load graph"
          @click="emit('update:modelValue', { ...modelValue, showCpuLoad: modelValue.showCpuLoad === false })"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
            aria-hidden="true"
          >
            <path
              fill-rule="evenodd"
              :d="IC.cpuLoad"
            />
          </svg>
          <span class="tb-label">Load</span>
        </button>
        <div class="tb-sep" />
      </div>
    </Teleport>

    <!-- g4b: Investigation entry points — Find · Heatmap · All · Analysis · Compare -->
    <Teleport
      :to="overflowPanelEl ?? 'body'"
      :disabled="!overflow.g4b"
    >
      <div
        :ref="el => setGroupRef('g4b', el)"
        class="tb-group"
      >
        <button
          v-if="traceInfo"
          class="tb-btn"
          title="Find task, annotation, or migration (Ctrl+F)"
          @click="emit('showFind')"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
            aria-hidden="true"
          >
            <path
              fill-rule="evenodd"
              :d="IC.find"
            />
          </svg>
        </button>

        <button
          class="tb-btn"
          data-demo-target="toolbar_heatmap"
          :class="{ disabled: !heatmapEnabled }"
          :disabled="!heatmapEnabled"
          :title="heatmapEnabled
            ? 'Migration & Corridor Inspector — topology + timeline (multi-core traces only)'
            : 'Open a multi-core trace first'"
          @click="heatmapEnabled && emit('showHeatmap')"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
            aria-hidden="true"
          >
            <path
              fill-rule="evenodd"
              :d="IC.heatmap"
            />
          </svg>
        </button>

        <button
          v-if="taskFilterActive"
          class="tb-btn active tb-btn-labeled"
          title="Clear Migration Filter and show all tasks"
          @click="emit('clearTaskFilter')"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            aria-hidden="true"
          >
            <path
              fill="currentColor"
              fill-rule="evenodd"
              :d="IC.heatmap"
            />
            <line
              x1="2"
              y1="14"
              x2="14"
              y2="2"
              class="tb-heatmap-slash-outline"
              stroke-width="3.4"
              stroke-linecap="round"
            />
            <line
              x1="2"
              y1="14"
              x2="14"
              y2="2"
              class="tb-heatmap-slash"
              stroke-width="2"
              stroke-linecap="round"
            />
          </svg>
          <span class="tb-label">All tasks</span>
        </button>

        <button
          class="tb-btn tb-btn-labeled"
          data-demo-target="toolbar_analysis"
          :class="{ disabled: !analysisEnabled }"
          :disabled="!analysisEnabled"
          :title="analysisEnabled
            ? 'Analysis Findings — heuristic load balance, WCET, blocking, thrashing, deadlines, tick, sync'
            : 'Open a trace first'"
          @click="analysisEnabled && emit('showAnalysis')"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
            aria-hidden="true"
          >
            <path
              fill-rule="evenodd"
              :d="IC.analysis"
            />
          </svg>
          <span class="tb-label">Analysis</span>
        </button>

        <button
          class="tb-btn tb-btn-labeled"
          :class="{ disabled: !compareEnabled }"
          :disabled="!compareEnabled"
          :title="compareEnabled
            ? 'Trace Compare — summary, top tasks, and core migrations between two open trace tabs'
            : 'Open at least two traces to compare'"
          @click="compareEnabled && emit('showCompare')"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
            aria-hidden="true"
          >
            <path
              fill-rule="evenodd"
              :d="IC.compare"
            />
          </svg>
          <span class="tb-label">Compare</span>
        </button>
        <div class="tb-sep" />
      </div>
    </Teleport>

    <!-- g5: Log₂ -->
    <Teleport
      :to="overflowPanelEl ?? 'body'"
      :disabled="!overflow.g5"
    >
      <div
        :ref="el => setGroupRef('g5', el)"
        class="tb-group"
      >
        <button
          type="button"
          class="tb-btn tb-btn-text"
          :class="{ active: modelValue.stiLogScale }"
          title="STI waveform y-axis: toggle between linear and log₂ scale (only active when an STI row is expanded)"
          @click="emit('update:modelValue', { ...modelValue, stiLogScale: !modelValue.stiLogScale })"
        >
          Log₂
        </button>
        <div class="tb-sep" />
      </div>
    </Teleport>

    <!-- g6: Theme -->
    <Teleport
      :to="overflowPanelEl ?? 'body'"
      :disabled="!overflow.g6"
    >
      <div
        :ref="el => setGroupRef('g6', el)"
        class="tb-group"
      >
        <button
          type="button"
          class="tb-btn"
          :title="modelValue.darkMode ? 'Switch to light theme' : 'Switch to dark theme'"
          @click="emit('update:modelValue', { ...modelValue, darkMode: !modelValue.darkMode })"
        >
          <svg
            v-if="modelValue.darkMode"
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
            aria-hidden="true"
          >
            <path
              fill-rule="evenodd"
              :d="IC.themeLight"
            />
          </svg>
          <svg
            v-else
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
            aria-hidden="true"
          >
            <path
              fill-rule="evenodd"
              :d="IC.themeDark"
            />
          </svg>
        </button>
      </div>
    </Teleport>

    <div
      v-show="anyOverflow"
      class="tb-overflow"
    >
      <button
        ref="overflowBtnEl"
        class="tb-btn tb-overflow-btn"
        :class="{ active: overflowMenuOpen }"
        title="More toolbar options"
        @click="overflowMenuOpen = !overflowMenuOpen"
      >
        ⋯
      </button>
      <div
        v-show="overflowMenuOpen"
        ref="overflowPanelEl"
        class="tb-overflow-panel"
      />
    </div>

    <div class="spacer" />

    <button
      type="button"
      class="tb-limit-badge"
      :class="{ on: limitOn }"
      :disabled="!rangeEnabled"
      :title="limitBadgeTitle"
      :aria-pressed="limitOn"
      :aria-label="limitBadgeTitle"
      data-demo-target="toolbar_limit"
      @click="emit('toggleLimit')"
    >
      C1–Cn
    </button>

    <span
      v-if="loading"
      class="loading-badge"
    >
      <span class="loading-badge-text">
        {{ loadingMsg || 'Parsing…' }}
        <span
          v-if="loadingPct > 0"
          class="loading-badge-pct"
        >{{ loadingPct }}%</span>
      </span>
      <span class="loading-badge-bar">
        <span
          class="loading-badge-fill"
          :style="{ width: Math.max(4, loadingPct) + '%' }"
        />
      </span>
    </span>

    <button
      class="tb-btn"
      title="Load the bundled demo trace"
      aria-label="Load the bundled demo trace"
      @click="emit('loadDemo')"
    >
      <svg
        viewBox="0 0 16 16"
        width="16"
        height="16"
        fill="currentColor"
        aria-hidden="true"
      >
        <path
          fill-rule="evenodd"
          :d="IC.demo"
        />
      </svg>
    </button>
    <button
      class="tb-btn"
      :class="{ recording: recording }"
      :title="recording ? 'Stop recording and download WebM' : 'Record this tab (share the tab and include tab audio)'"
      :aria-label="recording ? 'Stop recording and download WebM' : 'Record this tab'"
      @click="emit('toggleRecord')"
    >
      <svg
        viewBox="0 0 16 16"
        width="16"
        height="16"
        fill="currentColor"
        aria-hidden="true"
      >
        <circle
          cx="8"
          cy="8"
          r="5"
        />
      </svg>
    </button>

    <button
      class="tb-btn"
      title="Open Settings (Ctrl+,)"
      @click="emit('showSettings')"
    >
      <svg
        viewBox="0 0 16 16"
        width="16"
        height="16"
        fill="currentColor"
        aria-hidden="true"
      >
        <path
          fill-rule="evenodd"
          :d="IC.settings"
        />
      </svg>
    </button>

    <button
      class="tb-btn"
      title="Help & keyboard shortcuts (?)"
      @click="emit('showHelp')"
    >
      <svg
        viewBox="0 0 16 16"
        width="16"
        height="16"
        fill="currentColor"
        aria-hidden="true"
      >
        <path
          fill-rule="evenodd"
          :d="IC.help"
        />
      </svg>
    </button>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
import DomSelect from './DomSelect.vue'
import { IC } from '../utils/toolbarIcons.js'
import { getTimelineLayout } from '../utils/timelineLayout.js'
import { supportsFileHandles, pickAndReadOpen, OPEN_FILE_ACCEPT } from '../utils/fileOpen.js'
import { loadBtfEntriesFromFile } from '../utils/btfLoad.js'
import { classifyPickedOpen } from '../utils/demoPack.js'
import { appIconSvgMarkup } from '../utils/htmlReport.js'

const appIconSvg = appIconSvgMarkup(16)

const props = defineProps({
  modelValue:  { type: Object,  required: true },
  traceInfo:   { type: String,  default: '' },
  heatmapEnabled: { type: Boolean, default: false },
  analysisEnabled: { type: Boolean, default: false },
  compareEnabled: { type: Boolean, default: false },
  taskFilterActive: { type: Boolean, default: false },
  rangeEnabled: { type: Boolean, default: false },
  zoomOutEnabled: { type: Boolean, default: false },
  loading:     { type: Boolean, default: false },
  loadingPct:  { type: Number,  default: 0 },
  loadingMsg:  { type: String,  default: '' },
  timeScale:   { type: String, default: 'ns' },
  recording:   { type: Boolean, default: false },
  zoomPresetValue: { type: String, default: 'fit' },
  zoomPresetOptions: { type: Array, default: () => [{ value: 'fit', label: 'Fit' }] },
  limitOn: { type: Boolean, default: false },
})

const emit = defineEmits([
  'update:modelValue', 'trace-reading', 'trace-loaded', 'traces-loaded', 'loadDemo', 'demoPack',
  'demoFolder',
  'toggleRecord', 'zoom', 'fit', 'zoomPreset',
  'zoom1to1', 'zoomRange', 'showFind',
  'expandAll', 'collapseAll', 'addMark', 'copyScreenshot', 'exportSvg', 'exportPerfetto',
  'exportSlice',
  'showHelp', 'showAbout', 'showSettings', 'showHeatmap', 'showAnalysis',
  'showCompare',
  'clearTaskFilter', 'file-error', 'toggleLimit',
])

const limitBadgeTitle = computed(() => {
  if (!props.rangeEnabled) {
    return 'Limit to C1–Cn is Off — place at least two cursors to enable'
  }
  return props.limitOn
    ? 'Limit to C1–Cn is On — Statistics use the cursor range. Click to turn off.'
    : 'Limit to C1–Cn is Off — Statistics use the full trace. Click to turn on.'
})

const useFsaOpen = supportsFileHandles()
const coresExpanded = ref(true)

function toggleExpandAll() {
  if (props.modelValue.viewMode !== 'core') return
  coresExpanded.value = !coresExpanded.value
  if (coresExpanded.value) emit('expandAll')
  else emit('collapseAll')
}

const zoom1to1Title = computed(() => {
  const tspx = getTimelineLayout().timescalePerPxDefault
  const u = props.timeScale || 'ns'
  return `Zoom to 1:1 scale (${tspx} ${u}/px)`
})


async function emitLoadedEntries(file) {
  emit('trace-reading', { name: file.name })
  try {
    const entries = await loadBtfEntriesFromFile(file)
    emit('traces-loaded', { entries, sourceName: file.name })
  } catch (err) {
    emit('file-error', `Failed to read "${file.name}"${err?.message ? `: ${err.message}` : ''}`)
  }
}

async function emitPickedOpen(picked) {
  if (!picked) return
  if (picked.kind === 'demo') {
    emit('demoPack', picked.pack)
    return
  }
  if (picked.kind === 'demo-folder') {
    emit('demoFolder', {
      xmlName: picked.xmlName,
      traceName: picked.traceName || '',
      startIn: picked.startIn || null,
      files: picked.files || null,
    })
    return
  }
  if (picked.kind === 'btf' && picked.file) await emitLoadedEntries(picked.file)
}

async function onOpenClick() {
  try {
    await emitPickedOpen(await pickAndReadOpen())
  } catch (err) {
    emit('file-error', err?.message || 'Failed to open file')
  }
}

async function onFileChange(e) {
  const list = [...(e.target.files || [])]
  e.target.value = ''
  if (!list.length) return
  const files = new Map(list.map(f => [f.name, f]))
  try {
    await emitPickedOpen(await classifyPickedOpen(files))
  } catch (err) {
    emit('file-error', err?.message || 'Failed to open file')
  }
}

function triggerOpen() {
  if (useFsaOpen) onOpenClick()
  else fileInputRef.value?.click()
}

const fileInputRef = ref(null)
defineExpose({ triggerOpen })

// ---- Responsive overflow (groups → ⋯) -------------------------------------
const toolbarEl = ref(null)
const overflowBtnEl = ref(null)
const overflowPanelEl = ref(null)
const overflowMenuOpen = ref(false)

const GROUP_ORDER = ['g1', 'g2', 'g3', 'g4', 'g4b', 'g5', 'g6']
const overflow = reactive(Object.fromEntries(GROUP_ORDER.map(k => [k, false])))
const anyOverflow = computed(() => GROUP_ORDER.some(k => overflow[k]))

const groupEls = {}
function setGroupRef(key, el) {
  if (el) groupEls[key] = el
}

async function recomputeOverflow() {
  const toolbar = toolbarEl.value
  if (!toolbar) return

  let resetAny = false
  for (const k of GROUP_ORDER) {
    if (overflow[k]) { overflow[k] = false; resetAny = true }
  }
  if (resetAny) await nextTick()

  for (let i = GROUP_ORDER.length - 1; i >= 0; i--) {
    if (toolbar.scrollWidth <= toolbar.clientWidth + 1) break
    overflow[GROUP_ORDER[i]] = true
    await nextTick()
  }
}

let recomputeQueued = false
function queueRecompute() {
  if (recomputeQueued) return
  recomputeQueued = true
  requestAnimationFrame(() => {
    recomputeQueued = false
    recomputeOverflow()
  })
}

function onDocumentClick(e) {
  if (!overflowMenuOpen.value) return
  if (overflowBtnEl.value?.contains(e.target)) return
  if (overflowPanelEl.value?.contains(e.target)) return
  overflowMenuOpen.value = false
}

let resizeObserver = null

onMounted(() => {
  queueRecompute()
  resizeObserver = new ResizeObserver(queueRecompute)
  if (toolbarEl.value) resizeObserver.observe(toolbarEl.value)
  document.addEventListener('click', onDocumentClick, true)
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  document.removeEventListener('click', onDocumentClick, true)
})

watch(
  () => [
    props.modelValue.viewMode, !!props.traceInfo, props.taskFilterActive,
    props.zoomPresetOptions?.length,
  ],
  queueRecompute,
)
</script>

<style scoped>
/* Match desktop QToolBar: 18px icons, 4px spacing, compact padding, 3px radius. */
.toolbar {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 2px 6px;
  background: var(--tb-bg);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  user-select: none;
  container-type: inline-size;
  container-name: toolbar;
  font-size: 11px;
}

.tb-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 3px;
  min-width: 24px;
  min-height: 24px;
  border: none;
  border-radius: 3px;
  background: transparent;
  color: var(--fg);
  font-size: inherit;
  font-family: inherit;
  cursor: pointer;
  white-space: nowrap;
  flex-shrink: 0;
  transition: background 0.1s;
}
.tb-btn svg {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
}
.tb-btn:hover {
  background: var(--tb-btn-hover);
}
.tb-btn.active {
  background: var(--tb-btn-active);
  color: var(--accent);
}
.tb-btn.recording {
  background: var(--tb-btn-active);
  color: #E24B4A;
}
.tb-btn.disabled,
.tb-btn:disabled {
  opacity: 0.38;
  cursor: not-allowed;
}
.tb-btn-text {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  min-width: 28px;
  padding-inline: 6px;
}
.tb-btn-labeled {
  padding-inline: 6px;
}
.tb-label {
  font-size: inherit;
  font-weight: 400;
  line-height: 1;
}
.tb-heatmap-slash-outline {
  stroke: var(--tb-bg, var(--bg));
}
.tb-heatmap-slash {
  stroke: #E24B4A;
}

/* Hybrid: drop short labels when the bar is tight (desktop keeps icon+text for Task/Core/Load/Analysis/Compare) */
@container toolbar (max-width: 1100px) {
  .tb-label {
    display: none;
  }
}

.tb-sep {
  width: 1px;
  height: 18px;
  background: var(--border);
  margin: 3px 2px;
  flex-shrink: 0;
}
.tb-zoom-preset {
  height: 24px;
  min-width: 100px;
  max-width: 110px;
  margin: 0;
  padding: 1px 4px;
  border: 1px solid var(--border);
  border-radius: 3px;
  background: var(--tb-bg);
  color: var(--fg);
  font-size: inherit;
  font-family: inherit;
  cursor: pointer;
  flex-shrink: 0;
}
.tb-zoom-preset:hover:not(.disabled) {
  background: var(--tb-btn-hover);
}
.tb-zoom-preset.disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.tb-overflow-panel .tb-zoom-preset {
  max-width: none;
  width: 100%;
}
.tb-group {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.tb-overflow {
  position: relative;
  flex-shrink: 0;
}
.tb-overflow-btn {
  font-weight: 700;
  letter-spacing: 1px;
}
.tb-overflow-panel {
  position: absolute;
  top: calc(100% + 4px);
  right: 0;
  z-index: 50;
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 200px;
  max-height: 70vh;
  overflow-y: auto;
  padding: 6px;
  background: var(--tb-bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
}
.tb-overflow-panel .tb-group {
  flex-wrap: wrap;
}
.tb-overflow-panel .tb-group + .tb-group {
  border-top: 1px solid var(--border);
  padding-top: 4px;
}
.tb-overflow-panel .tb-sep {
  display: none;
}
.tb-overflow-panel .tb-label {
  display: inline;
}

.spacer {
  flex: 1;
}
.loading-badge {
  display: inline-flex;
  flex-direction: column;
  align-items: stretch;
  gap: 2px;
  font-size: 11px;
  background: var(--accent);
  color: #000;
  padding: 3px 8px 4px;
  border-radius: 6px;
  min-width: 110px;
}
.loading-badge-text {
  display: flex;
  justify-content: space-between;
  gap: 6px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.loading-badge-pct {
  opacity: 0.7;
  flex-shrink: 0;
}
.loading-badge-bar {
  height: 3px;
  border-radius: 2px;
  background: rgba(0,0,0,0.2);
  overflow: hidden;
}
.loading-badge-fill {
  display: block;
  height: 100%;
  background: rgba(0,0,0,0.55);
  border-radius: 2px;
  transition: width 0.15s ease;
}
.file-btn {
  cursor: pointer;
}

.app-name-btn {
  background: none;
  border: none;
  color: var(--accent);
  font-size: 13px;
  font-weight: 700;
  font-family: inherit;
  cursor: pointer;
  padding: 3px;
  min-width: 24px;
  min-height: 24px;
  border-radius: 3px;
  white-space: nowrap;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s;
}
.app-name-icon {
  display: inline-flex;
  line-height: 0;
}
.app-name-icon :deep(svg) {
  display: block;
  width: 18px;
  height: 18px;
}
.app-name-btn:hover {
  background: var(--tb-btn-hover);
}

.tb-limit-badge {
  appearance: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 22px;
  padding: 2px 7px;
  margin: 0 2px;
  border-radius: 8px;
  border: 1px solid var(--badge-detail-border, #565B61);
  background: var(--badge-detail-bg, #303337);
  color: var(--badge-detail-fg, #C0C4C9);
  font: inherit;
  font-size: inherit;
  font-weight: 400;
  letter-spacing: 0;
  line-height: 1.2;
  white-space: nowrap;
  cursor: pointer;
  flex-shrink: 0;
}
.tb-limit-badge.on {
  color: var(--badge-scope-fg, #9EC5E8);
  background: var(--badge-scope-bg, #283A47);
  border-color: var(--badge-scope-border, #3A6A8A);
}
.tb-limit-badge:hover:not(:disabled) {
  filter: brightness(1.12);
}
.tb-limit-badge:disabled {
  opacity: 0.55;
  cursor: not-allowed;
  filter: none;
}
</style>
