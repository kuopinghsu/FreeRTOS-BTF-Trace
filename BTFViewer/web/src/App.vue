<template>
  <div class="app" :class="{ dark: uiOptions.darkMode }">
    <!-- Toolbar -->
    <Toolbar
      :modelValue="uiOptions"
      @update:modelValue="v => Object.assign(uiOptions, v)"
      :traceInfo="traceInfo"
      :loading="loading"
      :loadingPct="loadingPct"
      :loadingMsg="loadingMsg"
      @trace-reading="onTraceReading"
      @trace-loaded="onTraceLoaded"
      @zoom="onZoom"
      @fit="onFit"
      @clearCursors="clearCursors"
      @expandAll="onExpandAll"
      @collapseAll="onCollapseAll"
      @addMark="onAddMark"
    />

    <!-- Main area -->
    <div class="main-area">
      <!-- Loading overlay -->
      <div v-if="loading" class="loading-overlay">
        <div class="loading-card">
          <div class="loading-filename">{{ loadingFileName || 'Loading trace…' }}</div>
          <div class="loading-msg">{{ loadingMsg || 'Please wait…' }}</div>
          <div class="loading-bar-track">
            <div class="loading-bar-fill" :style="{ width: loadingPct + '%' }" />
          </div>
          <div class="loading-pct">{{ loadingPct }}%</div>
        </div>
      </div>
      <!-- Timeline (flex: 1) -->
      <TimelinePanel
        ref="timelinePanelRef"
        :trace="trace"
        :options="timelineOptions"
        :cursors="cursors"
        @cursorsChange="cursors = $event"
        @highlightChange="(k) => timelineOptions.highlightKey = k ?? pinnedHighlightKey"
        @highlightClick="onHighlightClick"
        @addBookmark="onAddBookmark"
      />

      <!-- Right panel -->
      <div class="right-panel" v-if="trace">
        <!-- Cursor panel -->
        <div class="panel-section">
          <div class="panel-header">Cursors</div>
          <CursorPanel :cursors="cursors" :timeScale="trace.timeScale" @deleteCursor="onDeleteCursor" @jumpToCursor="timelinePanelRef?.jumpToNs($event)" />
        </div>

        <!-- Statistics -->
        <div class="panel-section">
          <div class="panel-header">Statistics</div>
          <StatisticsPanel :trace="trace" :cursors="cursors" />
        </div>

        <!-- Marks / Bookmarks -->
        <div class="panel-section">
          <div class="panel-header">Marks</div>
          <MarksPanel
            :bookmarks="marks"
            :timeScale="trace.timeScale"
            @addBookmark="onAddMark"
            @deleteBookmark="onDeleteBookmark"
            @jumpTo="onJumpToMark"
            @updateLabel="onUpdateMarkLabel"
            @importBookmarks="onImportBookmarks"
          />
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
            @highlightChange="(k) => { timelineOptions.highlightKey = k ?? pinnedHighlightKey; scheduleRender() }"
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
import { ref, shallowRef, reactive, computed, watch, onMounted } from 'vue'
import Toolbar          from './components/Toolbar.vue'
import TimelinePanel    from './components/TimelinePanel.vue'
import CursorPanel      from './components/CursorPanel.vue'
import LegendPanel      from './components/LegendPanel.vue'
import StatisticsPanel  from './components/StatisticsPanel.vue'
import MarksPanel       from './components/MarksPanel.vue'
import { formatTime }   from './renderer/TimelineRenderer.js'
import exampleBtfB64   from 'virtual:example-btf'

// ---- State ---------------------------------------------------------------
const trace      = shallowRef(null)
const loading    = ref(false)
const loadingPct = ref(0)
const loadingMsg = ref('')
const loadingFileName = ref('')
const cursors    = ref([null, null, null, null])

const uiOptions = reactive({
  viewMode:    'task',
  darkMode:    true,
  showGrid:    false,
  orientation: 'h',
})

const timelineOptions = reactive({
  viewMode:     'task',
  darkMode:     true,
  showGrid:     false,
  orientation:  'h',
  highlightKey: null,
  marks:        [],
})

// Bookmarks state
const marks              = ref([])
let   _markNextId         = 1
const pinnedHighlightKey = ref(null)  // sticky highlight set by legend click

// Keep timelineOptions in sync with uiOptions + marks
watch(uiOptions, (o) => {
  timelineOptions.viewMode    = o.viewMode
  timelineOptions.darkMode    = o.darkMode
  timelineOptions.showGrid    = o.showGrid
  timelineOptions.orientation = o.orientation
}, { deep: true })

watch(marks, (m) => {
  timelineOptions.marks = m
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

function onTraceReading({ name }) {
  // Show the loading overlay immediately while FileReader is still reading the file
  if (_parseWorker) { _parseWorker.terminate(); _parseWorker = null }
  loading.value         = true
  loadingPct.value      = 0
  loadingMsg.value      = 'Reading file…'
  loadingFileName.value = name || 'trace.btf'
}

async function onTraceLoaded({ text, name }) {
  // Terminate any in-progress parse
  if (_parseWorker) { _parseWorker.terminate(); _parseWorker = null }

  loading.value         = true
  loadingPct.value      = 0
  loadingMsg.value      = 'Reading file…'
  loadingFileName.value = name || 'trace.btf'

  // Yield one animation frame so the browser can paint the loading overlay
  // before any heavy synchronous work (or worker creation) begins.
  await new Promise(r => requestAnimationFrame(r))

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
    // Synchronous fallback – runs on main thread (no Workers on file://)
    // Yield another frame so the overlay is guaranteed to be painted before
    // parseBtf() blocks the main thread for potentially several seconds.
    await new Promise(r => requestAnimationFrame(r))
    try {
      const { parseBtf } = await import('./parser/btfParser.js')
      const result = parseBtf(text, (pct, msg) => { loadingPct.value = pct; loadingMsg.value = msg || '' })
      trace.value = result
      cursors.value = [null, null, null, null]
      timelineOptions.highlightKey = null
      pinnedHighlightKey.value = null
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
      loadingMsg.value = data.msg || ''
    } else if (data.type === 'done') {
      trace.value = data.trace
      cursors.value = [null, null, null, null]
      timelineOptions.highlightKey = null
      pinnedHighlightKey.value = null
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

function onDeleteCursor(idx) {
  const c = [...cursors.value]
  c[idx] = null
  cursors.value = c
}

function onHighlightClick(key) {
  // Pin the clicked task; click same task again to unpin
  pinnedHighlightKey.value = pinnedHighlightKey.value === key ? null : key
  timelineOptions.highlightKey = pinnedHighlightKey.value
  // Scroll & center the task row in the timeline
  if (pinnedHighlightKey.value) timelinePanelRef.value?.scrollToTask(pinnedHighlightKey.value)
  scheduleRender()
}

function scheduleRender() {
  timelinePanelRef.value?.scheduleRender()
}

// ---- Auto-load embedded example on startup --------------------------------
async function loadExampleBtf() {
  // Decode base64 → gzip bytes → text via native DecompressionStream
  const binStr  = atob(exampleBtfB64)
  const bytes   = new Uint8Array(binStr.length)
  for (let i = 0; i < binStr.length; i++) bytes[i] = binStr.charCodeAt(i)

  const ds     = new DecompressionStream('gzip')
  const writer = ds.writable.getWriter()
  const reader = ds.readable.getReader()
  writer.write(bytes)
  writer.close()

  const chunks = []
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    chunks.push(value)
  }
  const totalLen = chunks.reduce((s, c) => s + c.length, 0)
  const merged   = new Uint8Array(totalLen)
  let offset = 0
  for (const c of chunks) { merged.set(c, offset); offset += c.length }
  const text = new TextDecoder().decode(merged)
  await onTraceLoaded({ text, name: 'example.btf' })
}

onMounted(() => {
  loadExampleBtf()
})

// ---- Bookmarks -----------------------------------------------------------
function onAddMark() {
  // Add bookmark at the current viewport center
  if (!trace.value) return
  const center = timelinePanelRef.value?.getViewportCenter?.()
    ?? (trace.value.timeMin + (trace.value.timeMax - trace.value.timeMin) / 2)
  addMarkAtNs(center)
}

function onAddBookmark(ns) {
  // Called from TimelinePanel right-click context menu
  addMarkAtNs(ns)
}

function addMarkAtNs(ns) {
  if (!trace.value) return
  // Clamp to trace time range
  const clamped = Math.max(trace.value.timeMin, Math.min(trace.value.timeMax, ns))
  marks.value.push({ id: _markNextId++, ns: clamped, label: '' })
  marks.value.sort((a, b) => a.ns - b.ns)
}

function onDeleteBookmark(id) {
  marks.value = marks.value.filter(m => m.id !== id)
}

function onJumpToMark(ns) {
  timelinePanelRef.value?.jumpToNs(ns)
}

function onUpdateMarkLabel({ id, label }) {
  const m = marks.value.find(m => m.id === id)
  if (m) m.label = label
}

function onImportBookmarks(imported) {
  for (const { ns, label } of imported) {
    marks.value.push({ id: _markNextId++, ns, label: label || '' })
  }
  marks.value.sort((a, b) => a.ns - b.ns)
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
  position: relative;
}

.loading-overlay {
  position: absolute;
  inset: 0;
  z-index: 200;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.55);
  backdrop-filter: blur(2px);
}

.loading-card {
  background: var(--panel-bg);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 24px 32px;
  min-width: 320px;
  max-width: 480px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.5);
}

.loading-filename {
  font-size: 13px;
  font-weight: 600;
  color: var(--fg);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.loading-msg {
  font-size: 11px;
  color: var(--fg-dim);
  font-family: monospace;
  min-height: 1.4em;
}

.loading-bar-track {
  height: 6px;
  border-radius: 3px;
  background: var(--border);
  overflow: hidden;
}

.loading-bar-fill {
  height: 100%;
  border-radius: 3px;
  background: var(--accent);
  transition: width 0.15s ease;
}

.loading-pct {
  font-size: 11px;
  font-family: monospace;
  color: var(--accent);
  text-align: right;
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
