<template>
  <div
    ref="panelEl"
    class="timeline-panel"
  >
    <!-- Left: sticky label column (hidden in vertical mode) -->
    <LabelColumn
      v-if="orientation === 'h'"
      :trace="trace"
      :view-mode="options.viewMode"
      :expanded="expanded"
      :scroll-y="viewport.scrollY"
      :highlight-key="options.highlightKey"
      :show-sti="options.showSti !== false"
      @expand-toggle="onExpandToggle"
      @highlight-change="(k) => emit('highlightChange', k)"
      @highlight-click="(k) => emit('highlightClick', k)"
    />

    <!-- Right: canvas -->
    <div
      ref="canvasWrapEl"
      class="canvas-wrap"
    >
      <canvas ref="canvasEl" />
      <!-- Overlay canvas: hover line only — redraws without triggering a full repaint -->
      <canvas
        ref="overlayEl"
        class="overlay-canvas"
      />
      <StiTooltip
        :sti-event="stiHover"
        :x="stiHoverPos.x"
        :y="stiHoverPos.y"
        :time-scale="trace?.timeScale || 'ns'"
      />
      <!-- Right-click context menu -->
      <div
        v-if="contextMenu.visible"
        class="context-menu"
        :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }"
        @mouseleave="contextMenu.visible = false"
      >
        <div
          class="ctx-item"
          @click="onAddBookmark"
        >
          <svg
            viewBox="0 0 16 16"
            width="12"
            height="12"
            fill="currentColor"
            style="flex-shrink:0"
          >
            <path d="M2 2a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v13.5a.5.5 0 0 1-.74.439L8 13.069l-5.26 2.87A.5.5 0 0 1 2 15.5V2zm2-1a1 1 0 0 0-1 1v12.566l4.26-2.325a.5.5 0 0 1 .48 0L12 14.566V2a1 1 0 0 0-1-1H4z" />
          </svg>
          Add Bookmark
        </div>
        <div
          class="ctx-item"
          @click="onAddAnnotation"
        >
          <svg
            viewBox="0 0 16 16"
            width="12"
            height="12"
            fill="currentColor"
            style="flex-shrink:0"
          >
            <path d="M8 0 12 4 8 8 4 4 8 0zm0 9 4 4-4 3-4-3 4-4z" />
          </svg>
          Add Annotation
        </div>
        <div
          class="ctx-item"
          @click="onCopyCursorTime"
        >
          <svg
            viewBox="0 0 16 16"
            width="12"
            height="12"
            fill="currentColor"
            style="flex-shrink:0"
          >
            <path d="M4 1.5H3a2 2 0 0 0-2 2V14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V3.5a2 2 0 0 0-2-2h-1v1h1a1 1 0 0 1 1 1V14a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V3.5a1 1 0 0 1 1-1h1v-1zM5 0h6a1 1 0 0 1 1 1v3H4V1a1 1 0 0 1 1-1z" />
          </svg>
          Copy Time
        </div>
        <div
          class="ctx-item"
          @click="onCopyScreenshot"
        >
          <svg
            viewBox="0 0 16 16"
            width="12"
            height="12"
            fill="currentColor"
            style="flex-shrink:0"
          >
            <path d="M3 3.5A1.5 1.5 0 0 1 4.5 2h7A1.5 1.5 0 0 1 13 3.5V5h1a1 1 0 0 1 1 1v6.5a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 1 12.5V6a1 1 0 0 1 1-1h1V3.5zm1 0V5h8V3.5a.5.5 0 0 0-.5-.5h-7a.5.5 0 0 0-.5.5zM8 7a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5z" />
          </svg>
          Copy Screenshot
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { toBlob as domToBlob } from 'html-to-image'
import LabelColumn from './LabelColumn.vue'
import StiTooltip  from './StiTooltip.vue'
import { render as renderTimeline, renderVertical, buildRowLayout, buildColumnLayout, drawHoverLine, drawHoverLineVertical, drawCursors, drawCursorsVertical, drawMarksHorizontal, drawMarksVertical, RULER_H, ROW_H, STI_ROW_H, HEADER_H, formatTime } from '../renderer/TimelineRenderer.js'
import { InteractionHandler } from '../renderer/InteractionHandler.js'
import { taskMergeKey } from '../utils/colors.js'

// ---- Props & emits -------------------------------------------------------
const props = defineProps({
  trace:   { type: Object, default: null },
  options: { type: Object, required: true },  // { viewMode, highlightKey, showGrid, darkMode, orientation, marks }
  cursors: { type: Array, default: () => [] },
})
const emit = defineEmits(['viewportChange', 'cursorsChange', 'highlightChange', 'highlightClick', 'addBookmark', 'addAnnotation', 'markMove', 'copyScreenshot'])

// ---- Template refs -------------------------------------------------------
const panelEl     = ref(null)
const canvasWrapEl = ref(null)
const canvasEl    = ref(null)
const overlayEl   = ref(null)

// ---- Local state ----------------------------------------------------------
const expanded = reactive(new Set())

const orientation = computed(() => props.options.orientation || 'h')

const viewport = reactive({
  timeStart: 0,
  timeEnd:   1,
  scrollY:   0,
  scrollX:   0,
  canvasW:   1,
  canvasH:   1,
})

const stiHover    = ref(null)
const stiHoverPos = reactive({ x: 0, y: 0 })
const hoverTime   = ref(null)

// Right-click context menu
const contextMenu = reactive({ visible: false, x: 0, y: 0, ns: 0 })

// ---- Renderer loop --------------------------------------------------------
let _rafId = null
let _dirty = false

function scheduleRender() {
  _dirty = true
  if (!_rafId) {
    _rafId = requestAnimationFrame(() => {
      _rafId = null
      if (_dirty) {
        _dirty = false
        paint()
      }
    })
  }
}

function paint() {
  const canvas = canvasEl.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  const dpr = window.devicePixelRatio || 1
  const w   = canvas.clientWidth
  const h   = canvas.clientHeight

  if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
    canvas.width  = Math.round(w * dpr)
    canvas.height = Math.round(h * dpr)
    ctx.scale(dpr, dpr)
  }

  viewport.canvasW = w
  viewport.canvasH = h

  if (!props.trace) {
    ctx.clearRect(0, 0, w, h)
    ctx.fillStyle = props.options.darkMode ? '#1E1E1E' : '#FFFFFF'
    ctx.fillRect(0, 0, w, h)
    ctx.font = '14px sans-serif'
    ctx.fillStyle = props.options.darkMode ? '#555' : '#AAA'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText('Open a .btf file to begin', w / 2, h / 2)
    return
  }

  if (orientation.value === 'v') {
    renderVertical(ctx, props.trace, viewport, {
      viewMode:     props.options.viewMode,
      expanded,
      highlightKey: props.options.highlightKey,
      showGrid:     props.options.showGrid,
      showSti:      props.options.showSti !== false,
      darkMode:     props.options.darkMode,
    })
  } else {
    renderTimeline(ctx, props.trace, viewport, {
      viewMode:     props.options.viewMode,
      expanded,
      highlightKey: props.options.highlightKey,
      showGrid:     props.options.showGrid,
      showSti:      props.options.showSti !== false,
      darkMode:     props.options.darkMode,
    })
  }

  // Repaint the overlay to keep hover line in sync after a full canvas repaint
  paintHoverOverlay()
}

// ---- Overlay canvas: hover line only -------------------------------------
// Redraws only the hover indicator — never triggers a full segment repaint.
function paintHoverOverlay() {
  const canvas = overlayEl.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  const dpr = window.devicePixelRatio || 1
  const w   = canvas.clientWidth
  const h   = canvas.clientHeight
  const targetW = Math.round(w * dpr)
  const targetH = Math.round(h * dpr)
  if (canvas.width !== targetW || canvas.height !== targetH) {
    canvas.width  = targetW
    canvas.height = targetH
  }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.clearRect(0, 0, w, h)

  if (!props.trace) return

  const { timeStart, timeEnd, canvasW, canvasH } = viewport
  const marks   = props.options.marks || []
  const darkMode = props.options.darkMode

  if (orientation.value === 'v') {
    const bodyH   = canvasH - HEADER_H
    const pxPerNs = bodyH / (timeEnd - timeStart)
    drawMarksVertical(ctx, marks, props.trace, timeStart, pxPerNs, canvasW, canvasH, HEADER_H, darkMode)
    drawCursorsVertical(ctx, props.cursors, props.trace, timeStart, pxPerNs, canvasW, canvasH, HEADER_H, darkMode)
    if (hoverTime.value !== null)
      drawHoverLineVertical(ctx, hoverTime.value, props.trace, timeStart, pxPerNs, canvasW, canvasH, HEADER_H, darkMode)
  } else {
    const pxPerNs = canvasW / (timeEnd - timeStart)
    drawMarksHorizontal(ctx, marks, props.trace, timeStart, pxPerNs, canvasW, canvasH, darkMode)
    drawCursors(ctx, props.cursors, props.trace, timeStart, pxPerNs, canvasW, canvasH, darkMode)
    if (hoverTime.value !== null)
      drawHoverLine(ctx, hoverTime.value, props.trace, timeStart, pxPerNs, canvasW, canvasH, darkMode)
  }
}

// ---- ResizeObserver -------------------------------------------------------
let _resizeObs = null

function setupResize() {
  if (_resizeObs) _resizeObs.disconnect()
  _resizeObs = new ResizeObserver(() => {
    scheduleRender()
  })
  if (canvasWrapEl.value) _resizeObs.observe(canvasWrapEl.value)
}

// ---- InteractionHandler ---------------------------------------------------
let _handler = null

function setupHandler() {
  if (_handler) { _handler.destroy(); _handler = null }
  if (!canvasEl.value) return
  _handler = new InteractionHandler(canvasEl.value, {
    getTrace:    () => props.trace,
    getViewport: () => ({ ...viewport }),
    getOptions:  () => ({
      viewMode: props.options.viewMode,
      expanded,
      orientation: orientation.value,
      showSti: props.options.showSti !== false,
    }),
    getMarks:    () => props.options.marks || [],
    onViewportChange(vp) {
      viewport.timeStart = vp.timeStart
      viewport.timeEnd   = vp.timeEnd
      viewport.scrollY   = vp.scrollY ?? viewport.scrollY
      viewport.scrollX   = vp.scrollX ?? viewport.scrollX
      emit('viewportChange', { ...viewport })
      scheduleRender()
    },
    onCursorsChange(cursors) {
      emit('cursorsChange', cursors)
    },
    onMarkMove({ id, ns }) {
      emit('markMove', { id, ns })
    },
    onStiHover(ev) {
      stiHover.value = ev
    },
    onHoverTimeChange(t) {
      hoverTime.value = t
      paintHoverOverlay()  // cheap: only redraws the hover line on the overlay canvas
    },
    onRowHover(_row) {
      // Handled via LabelColumn hover for now
    },
    onFitToWindow() {
      fitToTrace()
    },
    onExpandToggle(key) {
      onExpandToggle(key)
    },
    onContextMenu({ ns, x, y }) {
      // x, y are client coordinates; convert to element-relative
      const rect = canvasWrapEl.value?.getBoundingClientRect()
      if (!rect) return
      contextMenu.ns      = ns
      contextMenu.x       = x - rect.left
      contextMenu.y       = y - rect.top
      contextMenu.visible = true
    },
  })
  _handler.setCursors(props.cursors)
}

// ---- Context menu actions -------------------------------------------------

function onAddBookmark() {
  contextMenu.visible = false
  emit('addBookmark', contextMenu.ns)
}

function onAddAnnotation() {
  contextMenu.visible = false
  emit('addAnnotation', contextMenu.ns)
}

function onCopyCursorTime() {
  contextMenu.visible = false
  if (!props.trace) return
  const label = formatTime(contextMenu.ns, props.trace.timeScale)
  navigator.clipboard?.writeText(label).catch(() => {})
}

function onCopyScreenshot() {
  contextMenu.visible = false
  emit('copyScreenshot')
}

async function captureScreenshotBlob() {
  const root = panelEl.value
  const { captureW, captureH } = getCaptureSize()
  if (!captureW || !captureH) return null

  if (root) {
    try {
      const blob = await domToBlob(root, {
        cacheBust: true,
        pixelRatio: window.devicePixelRatio || 1,
        width: captureW,
        height: captureH,
        filter: (node) => {
          if (!(node instanceof HTMLElement)) return true
          // Exclude transient overlays from capture output.
          return !node.classList.contains('context-menu') && !node.classList.contains('sti-tooltip')
        },
      })
      if (blob) return blob
    } catch {
      // Fall through to canvas-only fallback.
    }
  }

  return await captureCanvasViewportBlob(captureW, captureH)
}

function getCaptureSize() {
  const root = panelEl.value
  if (!root) return { captureW: 0, captureH: 0 }

  const panelW = root.clientWidth
  const panelH = root.clientHeight
  if (!props.trace) return { captureW: panelW, captureH: panelH }

  if (orientation.value === 'v') {
    const { totalWidth } = buildColumnLayout(
      props.trace,
      props.options.viewMode,
      expanded,
      viewport.scrollX || 0,
      props.options.showSti !== false,
    )
    const captureW = Math.max(220, Math.min(panelW, Math.ceil(totalWidth)))
    return { captureW, captureH: panelH }
  }

  const { totalHeight } = buildRowLayout(props.trace, props.options.viewMode, expanded, 0, props.options.showSti !== false)
  const neededH = RULER_H + Math.max(ROW_H, totalHeight)
  const captureH = Math.max(RULER_H + ROW_H, Math.min(panelH, Math.ceil(neededH)))
  return { captureW: panelW, captureH }
}

async function captureCanvasViewportBlob(captureW, captureH) {
  const base = canvasEl.value
  const overlay = overlayEl.value
  const wrap = canvasWrapEl.value
  if (!base || !overlay || !wrap) return null

  const dpr = window.devicePixelRatio || 1
  const w = Math.min(captureW, wrap.clientWidth)
  const h = Math.min(captureH, wrap.clientHeight)
  if (w <= 0 || h <= 0) return null

  const out = document.createElement('canvas')
  out.width = Math.round(w * dpr)
  out.height = Math.round(h * dpr)
  const outCtx = out.getContext('2d')
  if (!outCtx) return null
  outCtx.setTransform(dpr, 0, 0, dpr, 0, 0)

  const panelStyle = getComputedStyle(panelEl.value || wrap)
  const bg = panelStyle.getPropertyValue('--bg').trim() || (props.options.darkMode ? '#1E1E1E' : '#FFFFFF')
  outCtx.fillStyle = bg
  outCtx.fillRect(0, 0, w, h)

  const srcW = Math.round(w * dpr)
  const srcH = Math.round(h * dpr)
  outCtx.drawImage(base, 0, 0, srcW, srcH, 0, 0, w, h)
  outCtx.drawImage(overlay, 0, 0, srcW, srcH, 0, 0, w, h)

  return await new Promise((resolve) => out.toBlob(resolve, 'image/png'))
}

// ---- Close context menu on outside click ----------------------------------
function onGlobalClick() {
  if (contextMenu.visible) {
    contextMenu.visible = false
  }
}

// ---- Fit to trace ----------------------------------------------------------

function fitToTrace() {
  if (!props.trace) return
  const lo = props.trace.timeMin >= 0 ? Math.max(0, props.trace.timeMin) : props.trace.timeMin
  const hi = props.trace.timeMax
  viewport.timeStart = lo
  viewport.timeEnd   = hi
  viewport.scrollY   = 0
  viewport.scrollX   = 0
  scheduleRender()
}

// ---- Zoom around center (called from parent via ref) ---------------------
function zoomCenter(factor) {
  const span   = (viewport.timeEnd - viewport.timeStart) * factor
  const center = (viewport.timeStart + viewport.timeEnd) / 2
  viewport.timeStart = center - span / 2
  viewport.timeEnd   = center + span / 2
  scheduleRender()
}

// ---- Public fit method (called from parent via ref) -----------------------
function jumpToNs(ns) {
  // Center the viewport around the given timestamp, preserving current zoom span
  const span = viewport.timeEnd - viewport.timeStart
  viewport.timeStart = ns - span / 2
  viewport.timeEnd   = ns + span / 2
  scheduleRender()
}

function getViewportCenter() {
  return (viewport.timeStart + viewport.timeEnd) / 2
}

function scrollToTask(mergeKey) {
  if (!props.trace) return
  // Build layout at yStart=0 to get raw row offsets independent of current scrollY
  const { rows } = buildRowLayout(props.trace, props.options.viewMode, expanded, 0, props.options.showSti !== false)
  // In task view: row.key === mergeKey; in core view: match on taskKey's mergeKey
  let targetRow = rows.find(r => r.type === 'task' && r.key === mergeKey)
  if (!targetRow) {
    targetRow = rows.find(r => r.type === 'core-task' && taskMergeKey(r.taskKey) === mergeKey)
  }
  if (!targetRow) return
  // In rendering: canvas Y of row = (RULER_H - scrollY) + row.y
  // To center row mid in canvas body: RULER_H - scrollY + row.y + ROW_H/2 = canvasH/2
  // => scrollY = RULER_H + row.y + ROW_H/2 - canvasH/2
  viewport.scrollY = Math.max(0, RULER_H + targetRow.y + ROW_H / 2 - viewport.canvasH / 2)
  scheduleRender()
}

defineExpose({ fitToTrace, scheduleRender, zoomCenter, expandAll, collapseAll, jumpToNs, getViewportCenter, scrollToTask, captureScreenshotBlob })

// ---- Expand / collapse core rows -----------------------------------------
function onExpandToggle(coreName) {
  if (expanded.has(coreName)) expanded.delete(coreName)
  else expanded.add(coreName)
  scheduleRender()
}

function expandAll() {
  if (!props.trace) return
  for (const coreName of props.trace.coreNames) expanded.add(coreName)
  scheduleRender()
}

function collapseAll() {
  expanded.clear()
  scheduleRender()
}

// ---- Watchers ------------------------------------------------------------
watch(() => props.trace, (trace) => {
  if (!trace) return
  // Default: expand all cores so task rows are visible on startup
  expanded.clear()
  for (const coreName of trace.coreNames) expanded.add(coreName)
  nextTick(() => {
    fitToTrace()
    setupHandler()
    scheduleRender()
  })
})

// Handler re-creation only needed when orientation or viewMode changes
watch([() => props.options.orientation, () => props.options.viewMode], () => {
  setupHandler()
  scheduleRender()
})
// Other visual options that affect segment rendering → full repaint
watch([() => props.options.highlightKey, () => props.options.showGrid, () => props.options.showSti, () => props.options.darkMode], () => {
  scheduleRender()
})
// Marks are on the overlay — no full repaint needed
watch(() => props.options.marks, () => {
  paintHoverOverlay()
}, { deep: true })

watch(() => props.cursors, (c) => {
  _handler?.setCursors(c)
  paintHoverOverlay()  // cursors are on the overlay canvas — no full repaint needed
}, { deep: true })

// Sync STI tooltip position
watch(stiHover, (ev) => {
  if (!ev || !canvasEl.value || !props.trace) return
  if (orientation.value === 'v') {
    // In vertical mode, X is column position, Y is time
    const hh = 160
    const pxPerNs = (viewport.canvasH - hh) / (viewport.timeEnd - viewport.timeStart)
    stiHoverPos.y = hh + (ev.time - viewport.timeStart) * pxPerNs
    stiHoverPos.x = canvasEl.value.clientWidth / 2
  } else {
    const w = canvasEl.value.clientWidth
    const pxPerNs = w / (viewport.timeEnd - viewport.timeStart)
    stiHoverPos.x = (ev.time - viewport.timeStart) * pxPerNs
    const { rows } = buildRowLayout(
      props.trace,
      props.options.viewMode,
      expanded,
      RULER_H - viewport.scrollY,
      props.options.showSti !== false,
    )
    const row = rows.find(r => r.type === 'sti' && r.key === ev.target)
    stiHoverPos.y = row ? (row.y + STI_ROW_H / 2) : (canvasEl.value.clientHeight / 2)
  }
})

// ---- Lifecycle -----------------------------------------------------------
onMounted(() => {
  setupResize()
  setupHandler()
  document.addEventListener('click', onGlobalClick)
  nextTick(() => {
    if (props.trace) fitToTrace()
    else scheduleRender()
  })
})

onBeforeUnmount(() => {
  if (_resizeObs) _resizeObs.disconnect()
  if (_handler) _handler.destroy()
  if (_rafId) cancelAnimationFrame(_rafId)
  document.removeEventListener('click', onGlobalClick)
})
</script>

<style scoped>
.timeline-panel {
  display: flex;
  flex: 1;
  overflow: hidden;
  position: relative;
}

.canvas-wrap {
  flex: 1;
  overflow: hidden;
  position: relative;
}

canvas {
  display: block;
  width: 100%;
  height: 100%;
  cursor: crosshair;
}

.overlay-canvas {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
}

.context-menu {
  position: absolute;
  z-index: 100;
  background: var(--panel-bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.4);
  padding: 4px 0;
  min-width: 160px;
  font-size: 12px;
}

.ctx-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  cursor: pointer;
  color: var(--fg);
  transition: background 0.08s;
}
.ctx-item:hover {
  background: var(--tb-btn-hover);
}
</style>
