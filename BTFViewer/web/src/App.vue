<template>
  <div
    class="app"
    :class="{ dark: timelineOptions.darkMode }"
  >
    <!-- Toolbar -->
    <Toolbar
      :model-value="timelineOptions"
      :trace-info="traceInfo"
      :loading="loading"
      :loading-pct="loadingPct"
      :loading-msg="loadingMsg"
      @update:model-value="v => Object.assign(timelineOptions, v)"
      @file-error="showToast($event, 'error')"
      @trace-reading="onTraceReading"
      @trace-loaded="onTraceLoaded"
      @load-demo="onLoadDemo"
      @zoom="onZoom"
      @fit="onFit"
      @expand-all="onExpandAll"
      @collapse-all="onCollapseAll"
      @add-mark="onAddMark"
      @copy-screenshot="onCopyScreenshot"
      @export-svg="onExportSvg"
      @show-help="openHelpDialog"
      @show-about="openAboutDialog"
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
          @segment-click="onSegmentClick"
        @add-bookmark="onAddBookmark"
        @add-annotation="onAddAnnotation"
        @mark-move="onMoveMark"
        @copy-screenshot="onCopyScreenshot"
        @export-svg="onExportSvg"
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
            @clear-all="clearCursors"
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
            :marks="marks"
            :time-scale="trace.timeScale"
            @add-bookmark="onAddMark"
            @add-annotation="onAddAnnotationAtCenter"
            @delete-mark="onDeleteMark"
            @jump-to="onJumpToMark"
            @update-label="onUpdateMarkLabel"
            @import-marks="onImportMarks"
            @clear-marks="onClearMarks"
            @select-mark="timelineOptions.selectedMarkId = $event"
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
      class="dialog-overlay"
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
                I
              </div><div>Show/hide STI channels</div>
              <div class="k">
                D
              </div><div>Toggle dark/light mode</div>
              <div class="k">
                B
              </div><div>Add bookmark at current position</div>
              <div class="k">
                A
              </div><div>Add annotation at current position</div>
              <div class="k">
                C
              </div><div>Clear all cursors</div>
              <div class="k">
                F
              </div><div>Fit timeline to trace</div>
              <div class="k">
                S
              </div><div>Copy screenshot to clipboard</div>
              <div class="k">
                +
              </div><div>Zoom in</div>
              <div class="k">
                -
              </div><div>Zoom out</div>
              <div class="k">
                Tab
              </div><div>Next segment</div>
              <div class="k">
                Shift+Tab
              </div><div>Previous segment</div>
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
                Context menu
              </div><div>Copy screenshot</div>
              <div class="k">
                Double-click ruler
              </div><div>Fit timeline</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- About dialog -->
    <div
      v-if="aboutOpen"
      class="dialog-overlay"
      @click.self="aboutOpen = false"
    >
      <div
        class="about-dialog"
        role="dialog"
        aria-modal="true"
        aria-label="About RTOS BTF Viewer"
      >
        <div class="about-hero">
          <div class="about-icon" aria-hidden="true">
            <span class="bar bar-1" />
            <span class="bar bar-2" />
            <span class="bar bar-3" />
            <span class="bar bar-4" />
            <span class="marker" />
          </div>
          <div class="about-title">RTOS BTF Viewer</div>
          <div class="about-subtitle">RTOS context-switch timeline visualiser · v{{ appVersion }}</div>
        </div>

        <div class="about-body">
          <div class="about-section">
            <div class="about-section-title">View Modes</div>
            <div class="about-grid">
              <div class="about-key">Task View</div><div>one row per task</div>
              <div class="about-key">Core View</div><div>expandable rows per CPU core</div>
            </div>
          </div>

          <div class="about-section">
            <div class="about-section-title">Application</div>
            <div class="about-grid">
              <div class="about-key">Product</div><div>RTOS BTF Viewer</div>
              <div class="about-key">Purpose</div><div>Interactive viewer for Best Trace Format (.btf) RTOS scheduling traces</div>
              <div class="about-key">Runtime</div><div>Vue 3 · Vite · Canvas-based timeline renderer</div>
              <div class="about-key">Build Date</div><div>{{ buildDate }}</div>
            </div>
          </div>

          <div class="about-section">
            <div class="about-section-title">License</div>
            <div class="about-grid">
              <div class="about-key">License</div><div>MIT License</div>
            </div>
          </div>
        </div>

        <div class="about-footer">
          <button
            class="about-close"
            @click="aboutOpen = false"
          >
            Close
          </button>
        </div>
      </div>
    </div>

    <!-- Snapshot editor -->
    <SnapshotEditor
      v-if="snapshotEditorOpen"
      :image-url="snapshotImageUrl"
      @close="onSnapshotEditorClose"
    />

    <!-- Toast notification -->
    <Transition name="toast">
      <div
        v-if="toastVisible"
        class="toast-notification"
        :class="toastType"
        @click="toastVisible = false"
      >
        {{ toastMsg }}
      </div>
    </Transition>

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
        Open a .btf trace file or click Demo to begin · Press ? for shortcuts/help
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
import SnapshotEditor   from './components/SnapshotEditor.vue'
import { formatTime }   from './renderer/TimelineRenderer.js'
import { taskMergeKey } from './utils/colors.js'
import exampleBtfB64   from 'virtual:example-btf'

// ---- State ---------------------------------------------------------------
const appVersion = __APP_VERSION__
const buildDate  = __BUILD_DATE__
const trace      = shallowRef(null)
const loading    = ref(false)
const loadingPct = ref(0)
const loadingMsg = ref('')
const loadingFileName = ref('')
const cursors    = ref([null, null, null, null])
const helpOpen   = ref(false)
const aboutOpen  = ref(false)

// ---- Snapshot editor -------------------------------------------------------
const snapshotEditorOpen = ref(false)
const snapshotImageUrl   = ref(null)

const toastMsg     = ref('')
const toastType    = ref('info')
const toastVisible = ref(false)
let   _toastTimer  = null

function showToast(msg, type = 'info') {
  toastMsg.value     = msg
  toastType.value    = type
  toastVisible.value = true
  clearTimeout(_toastTimer)
  _toastTimer = setTimeout(() => { toastVisible.value = false }, type === 'error' ? 5000 : 3000)
}

const timelineOptions = reactive({
  viewMode:        'task',
  darkMode:        true,
  showGrid:        false,
  showSti:         true,
  stiLogScale:     false,
  orientation:     'h',
  highlightKey:    null,
  marks:           [],
  highlightSegment: null,
  selectedMarkId:  null,
})

// Marks state (bookmarks + annotations)
const marks              = ref([])
let   _markNextId         = 1
const pinnedHighlightKey = ref(null)  // sticky highlight set by legend click
const highlightSegment = ref(null)   // single-segment lock (bar click or Tab nav)

// ---- Segment navigation cache (built lazily per trace) -------------------
let _navCache = null   // { trace, segs: TaskSegment[] sorted by time + identity }

function _sameSegment(a, b) {
  if (!a || !b) return false
  return a.start === b.start && a.end === b.end && a.task === b.task && a.core === b.core
}

function _segmentCmp(a, b) {
  if (a.start !== b.start) return a.start - b.start
  if (a.end !== b.end) return a.end - b.end
  const t = a.task.localeCompare(b.task)
  if (t !== 0) return t
  return a.core.localeCompare(b.core)
}

function _ensureNavCache() {
  if (!trace.value || _navCache?.trace === trace.value) return
  const tickMk = taskMergeKey('TICK')
  const isCoreEntity = (name) => typeof name === 'string' && name.startsWith('Core_')
  _navCache = {
    trace: trace.value,
    segs: trace.value.segments
      .filter(s => !!s.task)
      .filter(s => !isCoreEntity(s.task))
      .filter(s => taskMergeKey(s.task) !== tickMk)
      .sort(_segmentCmp),
  }
}

function cycleHighlightedSegment(forward) {
  if (!trace.value) return
  _ensureNavCache()
  const segs = _navCache?.segs
  if (!segs || segs.length === 0) return

  const cur      = highlightSegment.value
  const centerNs = timelinePanelRef.value?.getViewportCenter?.() ?? 0
  const isCoreView = timelineOptions.viewMode === 'core'
  const centerCore = isCoreView ? (timelinePanelRef.value?.getCoreAtViewportCenter?.() ?? null) : null
  const curCore = cur?.core ?? centerCore
  const navSegs = (isCoreView && curCore)
    ? segs.filter(s => s.core === curCore)
    : segs
  if (!navSegs || navSegs.length === 0) return

  const curTaskKey = cur
    ? taskMergeKey(cur.task)
    : (timelineOptions.highlightKey ?? pinnedHighlightKey.value ?? null)

  let idx = -1
  if (cur) idx = navSegs.findIndex(s => _sameSegment(s, cur))

  const pickForwardFrom = (startIdx) => {
    let i = startIdx
    for (let step = 0; step < navSegs.length; step++) {
      const seg = navSegs[i]
      if (!curTaskKey || taskMergeKey(seg.task) !== curTaskKey) return seg
      i = (i + 1) % navSegs.length
    }
    return navSegs[startIdx]
  }

  const pickBackwardFrom = (startIdx) => {
    let i = startIdx
    for (let step = 0; step < navSegs.length; step++) {
      const seg = navSegs[i]
      if (!curTaskKey || taskMergeKey(seg.task) !== curTaskKey) return seg
      i = (i - 1 + navSegs.length) % navSegs.length
    }
    return navSegs[startIdx]
  }

  let next
  if (forward) {
    if (idx >= 0) {
      let ni = (idx + 1) % navSegs.length
      next = pickForwardFrom(ni)
    } else {
      const refNs = cur?.start ?? centerNs
      let ni = navSegs.findIndex(s => s.start >= refNs)
      if (ni < 0) ni = 0
      next = pickForwardFrom(ni)
    }
  } else {
    if (idx >= 0) {
      let pi = (idx - 1 + navSegs.length) % navSegs.length
      next = pickBackwardFrom(pi)
    } else {
      const refNs = cur?.start ?? centerNs
      let pi = navSegs.length - 1
      for (let i = navSegs.length - 1; i >= 0; i--) {
        if (navSegs[i].start <= refNs) { pi = i; break }
      }
      next = pickBackwardFrom(pi)
    }
  }

  highlightSegment.value = next
  timelineOptions.highlightSegment = next
  timelinePanelRef.value?.scrollToSegmentIfNeeded(next)
}

function onSegmentClick(seg) {
  const cur = highlightSegment.value
  const isSame = cur && cur.start === seg.start && cur.end === seg.end && cur.task === seg.task
  if (isSame) {
    highlightSegment.value = null
    timelineOptions.highlightSegment = null
  } else {
    highlightSegment.value = seg
    timelineOptions.highlightSegment = seg
  }
}

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
      highlightSegment.value = null
      timelineOptions.highlightSegment = null
      _navCache = null
    } catch (err) {
      console.error('BTF parse error:', err)
      showToast('Failed to parse BTF file: ' + err.message, 'error')
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
      highlightSegment.value = null
      timelineOptions.highlightSegment = null
      _navCache = null
    } else if (data.type === 'error') {
      console.error('BTF parse error:', data.message)
      showToast('Failed to parse BTF file: ' + data.message, 'error')
      loading.value = false
      _parseWorker = null
      worker.terminate()
    }
  }

  worker.onerror = (e) => {
    console.error('Worker error:', e)
    showToast('Parser worker error: ' + e.message, 'error')
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

async function onCopyScreenshot() {
  const blob = await timelinePanelRef.value?.captureScreenshotBlob?.()
  if (!blob) {
    showToast('Unable to capture screenshot.', 'error')
    return
  }
  // Open snapshot editor so user can annotate before copying/saving
  if (snapshotImageUrl.value) URL.revokeObjectURL(snapshotImageUrl.value)
  snapshotImageUrl.value   = URL.createObjectURL(blob)
  snapshotEditorOpen.value = true
}

function onSnapshotEditorClose() {
  snapshotEditorOpen.value = false
  if (snapshotImageUrl.value) {
    URL.revokeObjectURL(snapshotImageUrl.value)
    snapshotImageUrl.value = null
  }
}

function onExportSvg() {
  const blob = timelinePanelRef.value?.captureAsSvg?.()
  if (!blob) {
    showToast('Unable to generate SVG export.', 'error')
    return
  }
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'timeline-export.svg'
  a.click()
  URL.revokeObjectURL(url)
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

function openHelpDialog() {
  aboutOpen.value = false
  helpOpen.value = true
}

function openAboutDialog() {
  helpOpen.value = false
  aboutOpen.value = true
}

function onGlobalKeydown(e) {
  if (isTypingTarget(e.target)) return

  if (e.key === 'Tab') {
    e.preventDefault()
    cycleHighlightedSegment(!e.shiftKey)
    return
  }

  if (e.key === '?' || (e.key === '/' && e.shiftKey)) {
    e.preventDefault()
    aboutOpen.value = false
    helpOpen.value = !helpOpen.value
    return
  }

  if (e.key === 'Escape') {
    if (helpOpen.value) {
      helpOpen.value = false
      e.preventDefault()
    } else if (aboutOpen.value) {
      aboutOpen.value = false
      e.preventDefault()
    }
    return
  }

  if (helpOpen.value || aboutOpen.value) return

  const key = e.key.toLowerCase()
  switch (key) {
    case '1':
      timelineOptions.viewMode = 'task'
      e.preventDefault()
      break
    case '2':
      timelineOptions.viewMode = 'core'
      e.preventDefault()
      break
    case 'h':
      timelineOptions.orientation = 'h'
      e.preventDefault()
      break
    case 'v':
      timelineOptions.orientation = 'v'
      e.preventDefault()
      break
    case 'g':
      timelineOptions.showGrid = !timelineOptions.showGrid
      e.preventDefault()
      break
    case 'i':
      timelineOptions.showSti = !timelineOptions.showSti
      e.preventDefault()
      break
    case 'd':
      timelineOptions.darkMode = !timelineOptions.darkMode
      e.preventDefault()
      break
    case 'b':
      onAddMark()
      e.preventDefault()
      break
    case 'a':
      onAddAnnotationAtCenter()
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
    case 's':
      onCopyScreenshot()
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
  if (typeof DecompressionStream === 'undefined') {
    showToast('Demo trace loading requires gzip decompression support. Open a .btf file directly instead.', 'error')
    return
  }

  // Decode base64 → gzip bytes → UTF-8 text.
  const binStr  = atob(exampleBtfB64)
  const bytes   = new Uint8Array(binStr.length)
  for (let i = 0; i < binStr.length; i++) bytes[i] = binStr.charCodeAt(i)

  const compressed = new Blob([bytes], { type: 'application/gzip' })
  const decompressedStream = compressed.stream().pipeThrough(new DecompressionStream('gzip'))
  const text = await new Response(decompressedStream).text()
  await onTraceLoaded({ text, name: 'example.btf' })
}

function onLoadDemo() {
  loadExampleBtf()
}

// Prevent Firefox from intercepting Ctrl+scroll for page-zoom so the
// canvas wheel handler (non-passive) can handle it exclusively.
function _onDocWheel(e) {
  if (e.ctrlKey || e.metaKey) e.preventDefault()
}

onMounted(() => {
  window.addEventListener('keydown', onGlobalKeydown)
  document.addEventListener('wheel', _onDocWheel, { passive: false, capture: true })
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onGlobalKeydown)
  document.removeEventListener('wheel', _onDocWheel, { capture: true })
})

// ---- Marks (bookmarks + annotations) -------------------------------------
function onAddMark() {
  // Priority: mouse hover position → last-moved/placed cursor → viewport center
  if (!trace.value) return
  const hoverNs  = timelinePanelRef.value?.getHoverTime?.() ?? null
  const cursorNs = timelinePanelRef.value?.getLastActiveCursorTime?.() ?? null
  const ns = hoverNs ?? cursorNs ?? (timelinePanelRef.value?.getViewportCenter?.()
    ?? (trace.value.timeMin + (trace.value.timeMax - trace.value.timeMin) / 2))
  addMarkAtNs(ns, 'bookmark')
}

function onAddAnnotationAtCenter() {
  if (!trace.value) return
  const hoverNs  = timelinePanelRef.value?.getHoverTime?.() ?? null
  const cursorNs = timelinePanelRef.value?.getLastActiveCursorTime?.() ?? null
  const ns = hoverNs ?? cursorNs ?? (timelinePanelRef.value?.getViewportCenter?.()
    ?? (trace.value.timeMin + (trace.value.timeMax - trace.value.timeMin) / 2))
  addMarkAtNs(ns, 'annotation')
}

function onAddBookmark(ns) {
  // Called from TimelinePanel right-click context menu
  addMarkAtNs(ns, 'bookmark')
}

function onAddAnnotation(ns) {
  addMarkAtNs(ns, 'annotation')
}

function addMarkAtNs(ns, type = 'bookmark') {
  if (!trace.value) return
  // Clamp to trace time range
  const clamped = Math.max(trace.value.timeMin, Math.min(trace.value.timeMax, ns))
  marks.value.push({ id: _markNextId++, ns: clamped, label: '', type: type === 'annotation' ? 'annotation' : 'bookmark' })
  marks.value.sort((a, b) => a.ns - b.ns)
}

function onDeleteMark(id) {
  marks.value = marks.value.filter(m => m.id !== id)
}

function onMoveMark({ id, ns }) {
  if (!trace.value) return
  const m = marks.value.find(mk => mk.id === id)
  if (!m) return
  const clamped = Math.max(trace.value.timeMin, Math.min(trace.value.timeMax, ns))
  m.ns = clamped
  marks.value.sort((a, b) => a.ns - b.ns)
}

function onJumpToMark(ns) {
  timelinePanelRef.value?.jumpToNs(ns)
}

function onUpdateMarkLabel({ id, label }) {
  const m = marks.value.find(m => m.id === id)
  if (m) m.label = label
}

function onImportMarks(imported) {
  for (const { ns, label, type } of imported) {
    marks.value.push({
      id: _markNextId++,
      ns,
      label: label || '',
      type: type === 'annotation' ? 'annotation' : 'bookmark',
    })
  }
  marks.value.sort((a, b) => a.ns - b.ns)
}

function onClearMarks() {
  marks.value = []
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
  --sb-thumb:       rgba(160, 160, 160, 0.40);
  --sb-thumb-hover: rgba(160, 160, 160, 0.65);
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
  --sb-thumb:       rgba(80, 80, 80, 0.38);
  --sb-thumb-hover: rgba(80, 80, 80, 0.62);
}

* { box-sizing: border-box; margin: 0; padding: 0; }

/* ---- Native scrollbar theming (all panels) ---- */
* {
  scrollbar-width: thin;
  scrollbar-color: var(--sb-thumb) transparent;
}
*::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}
*::-webkit-scrollbar-track {
  background: transparent;
}
*::-webkit-scrollbar-thumb {
  background: var(--sb-thumb);
  border-radius: 4px;
}
*::-webkit-scrollbar-thumb:hover {
  background: var(--sb-thumb-hover);
}
*::-webkit-scrollbar-corner {
  background: transparent;
}

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

.dialog-overlay {
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

.about-dialog {
  width: min(520px, 92vw);
  max-height: min(82vh, 720px);
  background: var(--panel-bg);
  border: 1px solid var(--border);
  border-radius: 12px;
  box-shadow: 0 12px 36px rgba(0, 0, 0, 0.45);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.about-hero {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 24px 24px 20px;
  border-bottom: 1px solid var(--border);
  background: linear-gradient(180deg, color-mix(in srgb, var(--accent) 16%, var(--panel-bg)), var(--panel-bg));
}

.about-icon {
  position: relative;
  width: 72px;
  height: 72px;
  border-radius: 16px;
  background: #1c3a6e;
  box-shadow: inset 0 0 0 1px rgba(255,255,255,0.08);
}

.about-icon .bar {
  position: absolute;
  left: 12px;
  height: 7px;
  border-radius: 999px;
}

.about-icon .bar-1 {
  top: 14px;
  width: 29px;
  background: #5b9bd5;
}

.about-icon .bar-2 {
  top: 26px;
  left: 18px;
  width: 22px;
  background: #7ec8e3;
}

.about-icon .bar-3 {
  top: 38px;
  width: 36px;
  background: #5b9bd5;
}

.about-icon .bar-4 {
  top: 50px;
  left: 22px;
  width: 18px;
  background: #7ec8e3;
}

.about-icon .marker {
  position: absolute;
  top: 10px;
  right: 24px;
  width: 2px;
  height: 46px;
  background: #ffc107;
}

.about-icon .marker::before {
  content: '';
  position: absolute;
  top: 0;
  left: -3px;
  width: 0;
  height: 0;
  border-left: 4px solid transparent;
  border-right: 4px solid transparent;
  border-top: 8px solid #ffc107;
}

.about-title {
  font-size: 18px;
  font-weight: 700;
}

.about-subtitle {
  color: var(--fg-dim);
  font-size: 12px;
  text-align: center;
}

.about-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 18px 20px;
  overflow: auto;
}

.about-section {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px;
}

.about-section-title {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--fg-dim);
  margin-bottom: 10px;
}

.about-grid {
  display: grid;
  grid-template-columns: 120px 1fr;
  gap: 8px 12px;
}

.about-key {
  color: var(--accent);
  font-weight: 600;
}

.about-footer {
  display: flex;
  justify-content: flex-end;
  padding: 0 20px 18px;
}

.about-close {
  border: 1px solid transparent;
  background: var(--accent);
  color: white;
  border-radius: 8px;
  min-width: 84px;
  height: 34px;
  padding: 0 16px;
  font-weight: 600;
  cursor: pointer;
}

.about-close:hover {
  filter: brightness(1.08);
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

  .about-grid {
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

/* ---- Toast notification ---- */
.toast-notification {
  position: fixed;
  bottom: 40px;
  left: 50%;
  transform: translateX(-50%);
  padding: 8px 18px;
  border-radius: 6px;
  font-size: 12px;
  z-index: 10000;
  cursor: pointer;
  max-width: 520px;
  text-align: center;
  pointer-events: auto;
  box-shadow: 0 4px 16px rgba(0,0,0,0.4);
}

.toast-notification.info {
  background: var(--panel-bg);
  color: var(--fg);
  border: 1px solid var(--border);
}

.toast-notification.error {
  background: #3a1010;
  color: #ff9090;
  border: 1px solid #7a3333;
}

.app:not(.dark) .toast-notification.info {
  background: #f5f5f5;
  color: #1e1e1e;
  border: 1px solid #ccc;
}

.app:not(.dark) .toast-notification.error {
  background: #fff0f0;
  color: #b00;
  border: 1px solid #e99;
}

.toast-enter-active,
.toast-leave-active {
  transition: opacity 0.2s ease;
}

.toast-enter-from,
.toast-leave-to {
  opacity: 0;
}
</style>
