<template>
  <div
    class="app"
    :class="{ dark: uiOptions.darkMode }"
  >
    <!-- Toolbar -->
    <Toolbar
      :model-value="uiOptions"
      :trace-info="traceInfo"
      :loading="loading"
      :loading-pct="loadingPct"
      :loading-msg="loadingMsg"
      @update:model-value="v => Object.assign(uiOptions, v)"
      @trace-reading="onTraceReading"
      @trace-loaded="onTraceLoaded"
      @zoom="onZoom"
      @fit="onFit"
      @clear-cursors="clearCursors"
      @expand-all="onExpandAll"
      @collapse-all="onCollapseAll"
      @add-mark="onAddMark"
      @show-help="helpOpen = true"
    />

    <!-- Main area -->
    <div class="main-area">
      <!-- Loading overlay -->
      <div
        v-if="loading"
        class="loading-overlay"
      >
        <div class="loading-card">
          <div class="loading-filename">
            {{ loadingFileName || 'Loading trace…' }}
          </div>
          <div class="loading-msg">
            {{ loadingMsg || 'Please wait…' }}
          </div>
          <div class="loading-bar-track">
            <div
              class="loading-bar-fill"
              :style="{ width: loadingPct + '%' }"
            />
          </div>
          <div class="loading-pct">
            {{ loadingPct }}%
          </div>
        </div>
      </div>
      <!-- Timeline (flex: 1) -->
      <TimelinePanel
        ref="timelinePanelRef"
        :trace="trace"
        :options="timelineOptions"
        :cursors="cursors"
        @cursors-change="cursors = $event"
        @highlight-change="(k) => timelineOptions.highlightKey = k ?? pinnedHighlightKey"
        @highlight-click="onHighlightClick"
        @add-bookmark="onAddBookmark"
      />

      <!-- Right panel -->
      <div
        v-if="trace"
        class="right-panel"
      >
        <!-- Cursor panel -->
        <div class="panel-section">
          <div class="panel-header">
            Cursors
          </div>
          <CursorPanel
            :cursors="cursors"
            :time-scale="trace.timeScale"
            @delete-cursor="onDeleteCursor"
            @jump-to-cursor="timelinePanelRef?.jumpToNs($event)"
          />
        </div>

        <!-- Statistics -->
        <div class="panel-section">
          <div class="panel-header">
            Statistics
          </div>
          <StatisticsPanel
            :trace="trace"
            :cursors="cursors"
          />
        </div>

        <!-- Marks / Bookmarks -->
        <div class="panel-section">
          <div class="panel-header">
            Marks
          </div>
          <MarksPanel
            :bookmarks="marks"
            :time-scale="trace.timeScale"
            @add-bookmark="onAddMark"
            @delete-bookmark="onDeleteBookmark"
            @jump-to="onJumpToMark"
            @update-label="onUpdateMarkLabel"
            @import-bookmarks="onImportBookmarks"
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
            :highlight-key="timelineOptions.highlightKey"
            @highlight-change="(k) => { timelineOptions.highlightKey = k ?? pinnedHighlightKey; scheduleRender() }"
            @highlight-click="onHighlightClick"
          />
        </div>
      </div>
    </div>

    <!-- Help dialog -->
    <div
      v-if="helpOpen"
      class="help-overlay"
      @click.self="helpOpen = false"
    >
      <div
        class="help-dialog"
        role="dialog"
        aria-modal="true"
        aria-label="Help and keyboard shortcuts"
      >
        <div class="help-header">
          <div class="help-title">
            Help & Shortcuts
          </div>
          <button
            class="help-close"
            @click="helpOpen = false"
          >
            ✕
          </button>
        </div>

        <div class="help-body">
          <div class="help-section">
            <div class="help-section-title">
              Keyboard
            </div>
            <div class="help-grid">
              <div class="k">
                ?
              </div><div>Open/close this help</div>
              <div class="k">
                Esc
              </div><div>Close help</div>
              <div class="k">
                1
              </div><div>Task view</div>
              <div class="k">
                2
              </div><div>Core view</div>
              <div class="k">
                H
              </div><div>Horizontal layout</div>
              <div class="k">
                V
              </div><div>Vertical layout</div>
              <div class="k">
                G
              </div><div>Toggle grid</div>
              <div class="k">
                D
              </div><div>Toggle dark/light mode</div>
              <div class="k">
                M
              </div><div>Add bookmark at viewport center</div>
              <div class="k">
                C
              </div><div>Clear all cursors</div>
              <div class="k">
                F
              </div><div>Fit timeline to trace</div>
              <div class="k">
                +
              </div><div>Zoom in</div>
              <div class="k">
                -
              </div><div>Zoom out</div>
            </div>
          </div>

          <div class="help-section">
            <div class="help-section-title">
              Mouse / Trackpad
            </div>
            <div class="help-grid">
              <div class="k">
                Wheel
              </div><div>Scroll task rows</div>
              <div class="k">
                Shift + Wheel
              </div><div>Pan timeline left/right</div>
              <div class="k">
                Ctrl/Cmd + Wheel
              </div><div>Zoom at pointer</div>
              <div class="k">
                Middle-drag
              </div><div>Pan timeline</div>
              <div class="k">
                Click timeline
              </div><div>Place/remove cursor</div>
              <div class="k">
                Right-click timeline
              </div><div>Open context menu</div>
              <div class="k">
                Double-click ruler
              </div><div>Fit timeline</div>
            </div>
          </div>
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
      <span
        v-else
        class="status-hint"
      >
        Open a .btf trace file to begin · Press ? for shortcuts/help
      </span>
    </div>
  </div>
</template>

<script setup>
import { ref, shallowRef, reactive, computed, watch, onMounted, onBeforeUnmount } from 'vue'
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
const helpOpen   = ref(false)

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

function isTypingTarget(el) {
  if (!el) return false
  const tag = el.tagName
  return el.isContentEditable || tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT'
}

function onGlobalKeydown(e) {
  if (isTypingTarget(e.target)) return

  if (e.key === '?' || (e.key === '/' && e.shiftKey)) {
    e.preventDefault()
    helpOpen.value = !helpOpen.value
    return
  }

  if (e.key === 'Escape') {
    if (helpOpen.value) {
      helpOpen.value = false
      e.preventDefault()
    }
    return
  }

  if (helpOpen.value) return

  const key = e.key.toLowerCase()
  switch (key) {
    case '1':
      uiOptions.viewMode = 'task'
      e.preventDefault()
      break
    case '2':
      uiOptions.viewMode = 'core'
      e.preventDefault()
      break
    case 'h':
      uiOptions.orientation = 'h'
      e.preventDefault()
      break
    case 'v':
      uiOptions.orientation = 'v'
      e.preventDefault()
      break
    case 'g':
      uiOptions.showGrid = !uiOptions.showGrid
      e.preventDefault()
      break
    case 'd':
      uiOptions.darkMode = !uiOptions.darkMode
      e.preventDefault()
      break
    case 'm':
      onAddMark()
      e.preventDefault()
      break
    case 'c':
      clearCursors()
      e.preventDefault()
      break
    case 'f':
      onFit()
      e.preventDefault()
      break
    case '+':
    case '=':
      onZoom(0.7)
      e.preventDefault()
      break
    case '-':
    case '_':
      onZoom(1.43)
      e.preventDefault()
      break
  }
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
  window.addEventListener('keydown', onGlobalKeydown)
  loadExampleBtf()
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onGlobalKeydown)
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

.help-overlay {
  position: absolute;
  inset: 0;
  z-index: 300;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(2px);
}

.help-dialog {
  width: min(760px, 92vw);
  max-height: min(82vh, 760px);
  background: var(--panel-bg);
  border: 1px solid var(--border);
  border-radius: 10px;
  box-shadow: 0 12px 36px rgba(0, 0, 0, 0.45);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.help-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  border-bottom: 1px solid var(--border);
}

.help-title {
  font-size: 14px;
  font-weight: 700;
}

.help-close {
  border: 1px solid var(--border);
  background: transparent;
  color: var(--fg);
  border-radius: 6px;
  width: 28px;
  height: 28px;
  cursor: pointer;
}

.help-close:hover {
  background: var(--tb-btn-hover);
}

.help-body {
  padding: 14px;
  overflow: auto;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}

.help-section {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px;
}

.help-section-title {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--fg-dim);
  margin-bottom: 8px;
}

.help-grid {
  display: grid;
  grid-template-columns: 140px 1fr;
  gap: 6px 10px;
  align-items: center;
}

.k {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 11px;
  color: var(--accent);
  background: var(--tb-btn-hover);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 2px 6px;
  justify-self: start;
}

@media (max-width: 760px) {
  .help-body {
    grid-template-columns: 1fr;
  }
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
