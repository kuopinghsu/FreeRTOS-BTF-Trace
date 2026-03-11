<template>
  <div class="app" :class="{ dark: uiOptions.darkMode }">
    <!-- Toolbar -->
    <Toolbar
      :modelValue="uiOptions"
      @update:modelValue="v => Object.assign(uiOptions, v)"
      :traceInfo="traceInfo"
      :loading="loading"
      :loadingPct="loadingPct"
      @trace-loaded="onTraceLoaded"
      @zoom="onZoom"
      @fit="onFit"
      @clearCursors="clearCursors"
      @expandAll="onExpandAll"
      @collapseAll="onCollapseAll"
    />

    <!-- Main area -->
    <div class="main-area">
      <!-- Timeline (flex: 1) -->
      <TimelinePanel
        ref="timelinePanelRef"
        :trace="trace"
        :options="timelineOptions"
        :cursors="cursors"
        @cursorsChange="cursors = $event"
        @highlightChange="(k) => timelineOptions.highlightKey = k"
        @highlightClick="onHighlightClick"
      />

      <!-- Right panel -->
      <div class="right-panel" v-if="trace">
        <!-- Cursor panel -->
        <div class="panel-section">
          <div class="panel-header">Cursors</div>
          <CursorPanel :cursors="cursors" :timeScale="trace.timeScale" />
        </div>

        <!-- Legend -->
        <div class="panel-section flex-fill">
          <div class="panel-header">
            Legend
            <span class="task-count">({{ trace.tasks.length }})</span>
          </div>
          <LegendPanel
            :trace="trace"
            :highlightKey="timelineOptions.highlightKey"
            @highlightChange="(k) => { timelineOptions.highlightKey = k; scheduleRender() }"
            @highlightClick="onHighlightClick"
          />
        </div>
      </div>
    </div>

    <!-- Status bar -->
    <div class="status-bar">
      <span v-if="trace">
        {{ trace.tasks.length }} tasks · {{ trace.segments.length.toLocaleString() }} segments ·
        {{ trace.stiEvents.length.toLocaleString() }} STI events ·
        {{ formatTime(trace.timeMax - trace.timeMin, trace.timeScale) }} total
      </span>
      <span v-else class="status-hint">
        Open a .btf trace file to begin · Scroll = pan rows · Ctrl+scroll = zoom · Click = cursor
      </span>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch } from 'vue'
import Toolbar       from './components/Toolbar.vue'
import TimelinePanel from './components/TimelinePanel.vue'
import CursorPanel   from './components/CursorPanel.vue'
import LegendPanel   from './components/LegendPanel.vue'
import { formatTime } from './renderer/TimelineRenderer.js'

// ---- State ---------------------------------------------------------------
const trace      = ref(null)
const loading    = ref(false)
const loadingPct = ref(0)
const cursors    = ref([null, null, null, null])

const uiOptions = reactive({
  viewMode: 'task',
  darkMode: true,
  showGrid: false,
})

const timelineOptions = reactive({
  viewMode:     'task',
  darkMode:     true,
  showGrid:     false,
  highlightKey: null,
})

// Keep timelineOptions in sync with uiOptions
watch(uiOptions, (o) => {
  timelineOptions.viewMode = o.viewMode
  timelineOptions.darkMode = o.darkMode
  timelineOptions.showGrid = o.showGrid
}, { deep: true })

// ---- Refs ----------------------------------------------------------------
const timelinePanelRef = ref(null)

// ---- Trace info for toolbar -----------------------------------------------
const traceInfo = computed(() => {
  if (!trace.value) return ''
  const t = trace.value
  return `${t.meta?.creator || ''} · ${t.tasks.length}T · ${t.segments.length.toLocaleString()} segs`
})

// ---- File loading (via Web Worker; fallback to main-thread for file:// origins) --
let _parseWorker = null

async function onTraceLoaded({ text, name }) {
  // Terminate any in-progress parse
  if (_parseWorker) { _parseWorker.terminate(); _parseWorker = null }

  loading.value    = true
  loadingPct.value = 0

  // Chrome on file:// blocks Blob-URL workers (null-origin restriction).
  // Detect this by attempting a test createObjectURL worker; if it throws,
  // fall back to parsing synchronously on the main thread.
  let workerOk = true
  try {
    const testBlob = new Blob([''], { type: 'text/javascript' })
    const testUrl  = URL.createObjectURL(testBlob)
    const testW    = new Worker(testUrl)
    testW.terminate()
    URL.revokeObjectURL(testUrl)
  } catch {
    workerOk = false
  }

  if (!workerOk) {
    // Synchronous fallback – UI will be unresponsive during parse but it works
    try {
      const { parseBtf } = await import('./parser/btfParser.js')
      const result = parseBtf(text, (pct) => { loadingPct.value = pct })
      trace.value = result
      cursors.value = [null, null, null, null]
      timelineOptions.highlightKey = null
    } catch (err) {
      console.error('BTF parse error:', err)
      alert('Failed to parse BTF file: ' + err.message)
    }
    loading.value = false
    return
  }

  const Worker = (await import('./parser/btfWorker.js?worker&inline')).default
  const worker = new Worker()
  _parseWorker = worker

  worker.onmessage = ({ data }) => {
    if (data.type === 'progress') {
      loadingPct.value = data.pct
    } else if (data.type === 'done') {
      trace.value = data.trace
      cursors.value = [null, null, null, null]
      timelineOptions.highlightKey = null
      loading.value = false
      _parseWorker = null
      worker.terminate()
    } else if (data.type === 'error') {
      console.error('BTF parse error:', data.message)
      alert('Failed to parse BTF file: ' + data.message)
      loading.value = false
      _parseWorker = null
      worker.terminate()
    }
  }

  worker.onerror = (e) => {
    console.error('Worker error:', e)
    alert('Parser worker error: ' + e.message)
    loading.value = false
    _parseWorker = null
    worker.terminate()
  }

  worker.postMessage({ text })
}

// ---- Zoom ----------------------------------------------------------------
function onZoom(factor) {
  timelinePanelRef.value?.zoomCenter(factor)
}

function onFit() {
  timelinePanelRef.value?.fitToTrace()
}

function onExpandAll() {
  timelinePanelRef.value?.expandAll()
}

function onCollapseAll() {
  timelinePanelRef.value?.collapseAll()
}

function clearCursors() {
  cursors.value = [null, null, null, null]
}

function onHighlightClick(key) {
  // Toggle persistent highlight
  timelineOptions.highlightKey = timelineOptions.highlightKey === key ? null : key
}

function scheduleRender() {
  timelinePanelRef.value?.scheduleRender()
}
</script>

<style>
/* ---- CSS custom properties (dark / light themes) ---- */
:root {
  --bg:            #1E1E1E;
  --panel-bg:      #252526;
  --ruler-bg:      #2D2D2D;
  --tb-bg:         #2D2D2D;
  --tb-btn-hover:  rgba(255,255,255,0.08);
  --tb-btn-active: rgba(79,139,255,0.2);
  --border:        #3C3C3C;
  --fg:            #D4D4D4;
  --fg-dim:        #858585;
  --accent:        #4F8BFF;
}

.app:not(.dark) {
  --bg:            #FFFFFF;
  --panel-bg:      #F5F5F5;
  --ruler-bg:      #EEEEEE;
  --tb-bg:         #F0F0F0;
  --tb-btn-hover:  rgba(0,0,0,0.06);
  --tb-btn-active: rgba(0,80,200,0.15);
  --border:        #DDDDDD;
  --fg:            #1E1E1E;
  --fg-dim:        #666666;
  --accent:        #0066CC;
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
  background: var(--bg);
  color: var(--fg);
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  font-size: 13px;
  overflow: hidden;
}

.app {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: var(--bg);
  color: var(--fg);
}

.main-area {
  display: flex;
  flex: 1;
  overflow: hidden;
  min-height: 0;
}

.right-panel {
  display: flex;
  flex-direction: column;
  width: 220px;
  flex-shrink: 0;
  border-left: 1px solid var(--border);
  background: var(--panel-bg);
  overflow: hidden;
}

.panel-section {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.panel-section.flex-fill {
  flex: 1;
  overflow: hidden;
}

.panel-header {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--fg-dim);
  padding: 6px 10px 4px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.task-count {
  font-weight: normal;
  opacity: 0.7;
}

.status-bar {
  padding: 3px 12px;
  font-size: 11px;
  font-family: monospace;
  color: var(--fg-dim);
  background: var(--panel-bg);
  border-top: 1px solid var(--border);
  flex-shrink: 0;
}

.status-hint {
  opacity: 0.6;
}
</style>
