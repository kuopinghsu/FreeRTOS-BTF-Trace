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
      :sti-expanded="stiExpanded"
      :scroll-y="viewport.scrollY"
      :highlight-key="options.highlightKey"
      :show-sti="options.showSti !== false"
      @expand-toggle="onExpandToggle"
      @highlight-change="(k) => emit('highlightChange', k)"
      @highlight-click="(k) => emit('highlightClick', k)"
      @sti-expand-toggle="onStiExpandToggle"
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

      <!-- Horizontal scrollbar (time axis in H-mode / column scroll in V-mode) -->
      <div
        v-if="showHScrollbar"
        class="scrollbar-track scrollbar-track-h"
        :class="{ 'has-v-sb': showVScrollbar }"
        @mousedown.prevent.stop="onHTrackClick"
      >
        <div
          class="scrollbar-thumb"
          :style="hThumbStyle"
          @mousedown.prevent.stop="onHThumbMouseDown"
        />
      </div>

      <!-- Vertical scrollbar (row scroll in H-mode / time axis in V-mode) -->
      <div
        v-if="showVScrollbar"
        class="scrollbar-track scrollbar-track-v"
        :class="{ 'has-h-sb': showHScrollbar }"
        @mousedown.prevent.stop="onVTrackClick"
      >
        <div
          class="scrollbar-thumb"
          :style="vThumbStyle"
          @mousedown.prevent.stop="onVThumbMouseDown"
        />
      </div>

      <!-- Navigator popup: shows full-view thumbnail with current viewport highlighted -->
      <Transition name="overview-fade">
        <div
          v-if="overviewVisible"
          class="overview-popup"
        >
          <canvas
            ref="overviewCanvasEl"
            class="overview-canvas"
            width="260"
            height="130"
          />
        </div>
      </Transition>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { toBlob as domToBlob } from 'html-to-image'
import LabelColumn from './LabelColumn.vue'
import StiTooltip  from './StiTooltip.vue'
import { render as renderTimeline, renderVertical, buildRowLayout, buildColumnLayout, drawHoverLine, drawHoverLineVertical, drawCursors, drawCursorsVertical, drawMarksHorizontal, drawMarksVertical, RULER_H, ROW_H, STI_ROW_H, RULER_W, COL_W, HEADER_H, formatTime } from '../renderer/TimelineRenderer.js'
import { renderToSvg } from '../renderer/SvgExporter.js'
import { InteractionHandler } from '../renderer/InteractionHandler.js'
import { taskMergeKey, taskColor, coreColor, parseTaskName, stiChannelColor } from '../utils/colors.js'

// ---- Props & emits -------------------------------------------------------
const props = defineProps({
  trace:   { type: Object, default: null },
  options: { type: Object, required: true },  // { viewMode, highlightKey, showGrid, darkMode, orientation, marks }
  cursors: { type: Array, default: () => [] },
})
const emit = defineEmits(['viewportChange', 'cursorsChange', 'highlightChange', 'highlightClick', 'segmentClick', 'addBookmark', 'addAnnotation', 'markMove', 'copyScreenshot'])

// ---- Template refs -------------------------------------------------------
const panelEl     = ref(null)
const canvasWrapEl = ref(null)
const canvasEl    = ref(null)
const overlayEl   = ref(null)

// ---- Local state ----------------------------------------------------------
const expanded    = reactive(new Set())
const stiExpanded = reactive(new Set())

const orientation = computed(() => props.options.orientation || 'h')

// ---- Scrollbar geometry --------------------------------------------------
const traceBounds = computed(() => {
  if (!props.trace) return null
  const lo = props.trace.timeMin >= 0 ? Math.max(0, props.trace.timeMin) : props.trace.timeMin
  return { lo, hi: props.trace.timeMax, span: props.trace.timeMax - lo }
})

const totalRowHeight = computed(() => {
  if (!props.trace || orientation.value !== 'h') return 0
  const { totalHeight } = buildRowLayout(
    props.trace, props.options.viewMode, expanded, 0,
    props.options.showSti !== false, stiExpanded,
  )
  return totalHeight
})

const showHScrollbar = computed(() => {
  if (!props.trace || !traceBounds.value) return false
  if (orientation.value === 'h') {
    return (viewport.timeEnd - viewport.timeStart) < traceBounds.value.span - 1
  }
  // Vertical mode: H scrollbar = column scroll
  const { totalWidth } = buildColumnLayout(
    props.trace, props.options.viewMode, expanded, 0, props.options.showSti !== false,
  )
  return totalWidth > viewport.canvasW + 1
})

const showVScrollbar = computed(() => {
  if (!props.trace || !traceBounds.value) return false
  if (orientation.value === 'h') {
    return totalRowHeight.value > (viewport.canvasH - RULER_H) + 1
  }
  // Vertical mode: V scrollbar = time scroll
  return (viewport.timeEnd - viewport.timeStart) < traceBounds.value.span - 1
})

const hThumbStyle = computed(() => {
  if (!showHScrollbar.value || !traceBounds.value || !props.trace) return {}
  const vSbW  = showVScrollbar.value ? SCROLLBAR_SIZE : 0
  const trackW = viewport.canvasW - vSbW
  if (orientation.value === 'h') {
    const visSpan = viewport.timeEnd - viewport.timeStart
    const thumbW  = Math.max(20, (visSpan / traceBounds.value.span) * trackW)
    const maxLeft = trackW - thumbW
    const thumbL  = maxLeft > 0
      ? Math.min(maxLeft, ((viewport.timeStart - traceBounds.value.lo) / (traceBounds.value.span - visSpan)) * maxLeft)
      : 0
    return { width: `${thumbW}px`, left: `${Math.max(0, thumbL)}px` }
  }
  // Vertical mode – column scroll
  const { totalWidth } = buildColumnLayout(
    props.trace, props.options.viewMode, expanded, 0, props.options.showSti !== false,
  )
  const thumbW  = Math.max(20, (viewport.canvasW / Math.max(1, totalWidth)) * trackW)
  const maxLeft = trackW - thumbW
  const thumbL  = maxLeft > 0
    ? Math.min(maxLeft, ((viewport.scrollX || 0) / Math.max(1, totalWidth - viewport.canvasW)) * maxLeft)
    : 0
  return { width: `${thumbW}px`, left: `${Math.max(0, thumbL)}px` }
})

const vThumbStyle = computed(() => {
  if (!showVScrollbar.value || !traceBounds.value || !props.trace) return {}
  const hSbH   = showHScrollbar.value ? SCROLLBAR_SIZE : 0
  const trackH = viewport.canvasH - hSbH
  if (orientation.value === 'h') {
    const visH    = viewport.canvasH - RULER_H
    const bodyH   = trackH - RULER_H
    const thumbH  = Math.max(20, (visH / Math.max(1, totalRowHeight.value)) * bodyH)
    const maxTop  = bodyH - thumbH
    const thumbT  = maxTop > 0
      ? Math.min(maxTop, (viewport.scrollY / Math.max(1, totalRowHeight.value - visH)) * maxTop)
      : 0
    return { height: `${thumbH}px`, top: `${RULER_H + thumbT}px` }
  }
  // Vertical mode – time scroll
  const visSpan = viewport.timeEnd - viewport.timeStart
  const bodyH   = trackH - HEADER_H
  const thumbH  = Math.max(20, (visSpan / traceBounds.value.span) * bodyH)
  const maxTop  = bodyH - thumbH
  const thumbT  = maxTop > 0
    ? Math.min(maxTop, ((viewport.timeStart - traceBounds.value.lo) / (traceBounds.value.span - visSpan)) * maxTop)
    : 0
  return { height: `${thumbH}px`, top: `${HEADER_H + thumbT}px` }
})

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

// ---- Scrollbars & navigator popup ----------------------------------------
const SCROLLBAR_SIZE   = 10          // px – scrollbar track thickness
const overviewCanvasEl = ref(null)
const overviewVisible  = ref(false)
let   _overviewHideTimer = null
let   _sbDrag            = null      // active scrollbar drag state: { type, … }

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

  const renderOpts = {
    viewMode:         props.options.viewMode,
    expanded,
    stiExpanded,
    highlightKey:     props.options.highlightKey,
    highlightSegment: props.options.highlightSegment ?? null,
    showGrid:         props.options.showGrid,
    showSti:          props.options.showSti !== false,
    stiLogScale:      !!props.options.stiLogScale,
    darkMode:         props.options.darkMode,
  }
  if (orientation.value === 'v') {
    renderVertical(ctx, props.trace, viewport, renderOpts)
  } else {
    renderTimeline(ctx, props.trace, viewport, renderOpts)
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
    drawMarksVertical(ctx, marks, props.trace, timeStart, pxPerNs, canvasW, canvasH, HEADER_H, darkMode, props.options.selectedMarkId ?? null)
    drawCursorsVertical(ctx, props.cursors, props.trace, timeStart, pxPerNs, canvasW, canvasH, HEADER_H, darkMode)
    if (hoverTime.value !== null)
      drawHoverLineVertical(ctx, hoverTime.value, props.trace, timeStart, pxPerNs, canvasW, canvasH, HEADER_H, darkMode)
  } else {
    const pxPerNs = canvasW / (timeEnd - timeStart)
    drawMarksHorizontal(ctx, marks, props.trace, timeStart, pxPerNs, canvasW, canvasH, darkMode, props.options.selectedMarkId ?? null)
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
      stiExpanded,
      orientation: orientation.value,
      showSti: props.options.showSti !== false,
    }),
    getMarks:    () => props.options.marks || [],
    onViewportChange(vp) {
      viewport.timeStart = vp.timeStart
      viewport.timeEnd   = vp.timeEnd
      if (vp.scrollY != null) {
        if (props.trace) {
          const { totalHeight } = buildRowLayout(props.trace, props.options.viewMode, expanded, 0, props.options.showSti !== false, stiExpanded)
          const maxScrollY = Math.max(0, totalHeight - (viewport.canvasH - RULER_H))
          viewport.scrollY = Math.max(0, Math.min(vp.scrollY, maxScrollY))
        } else {
          viewport.scrollY = Math.max(0, vp.scrollY)
        }
      }
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
      if (orientation.value !== 'v') return
      if (!_row) {
        emit('highlightChange', null)
        return
      }
      if (_row.type === 'task') {
        emit('highlightChange', _row.key)
      } else if (_row.type === 'core-task') {
        emit('highlightChange', taskMergeKey(_row.taskKey))
      } else {
        emit('highlightChange', null)
      }
    },
    onHighlightClick(key) {
      emit('highlightClick', key)
    },
    onSegmentClick(seg) {
      emit('segmentClick', seg)
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

function captureAsSvg() {
  if (!props.trace) return null
  const { canvasW, canvasH } = viewport
  const svgStr = renderToSvg(props.trace, {
    timeStart: viewport.timeStart,
    timeEnd:   viewport.timeEnd,
    scrollY:   viewport.scrollY,
    canvasW,
    canvasH,
  }, {
    viewMode: props.options.viewMode,
    expanded,
    darkMode: props.options.darkMode,
    showGrid: props.options.showGrid,
    showSti:     props.options.showSti !== false,
    stiExpanded,
    stiLogScale: !!props.options.stiLogScale,
    cursors:     props.cursors || [],
    marks:    (props.options.marks || []).map(m => [
      m.ns,
      m.label || '',
      m.type === 'annotation' ? '#FF8C00' : '#FFD700',
      m.type === 'annotation' ? 'annotation' : 'bookmark',
    ]),
  })
  if (!svgStr) return null
  return new Blob([svgStr], { type: 'image/svg+xml' })
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

  const { totalHeight } = buildRowLayout(props.trace, props.options.viewMode, expanded, 0, props.options.showSti !== false, stiExpanded)
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

function getCoreAtViewportCenter() {
  if (!props.trace || props.options.viewMode !== 'core') return null

  if (orientation.value === 'v') {
    const centerX = RULER_W + (viewport.canvasW - RULER_W) / 2
    const { cols } = buildColumnLayout(
      props.trace,
      props.options.viewMode,
      expanded,
      viewport.scrollX,
      props.options.showSti !== false,
    )
    const coreCols = cols.filter(c => c.type === 'core' || c.type === 'core-task')
    if (coreCols.length === 0) return null

    const hit = coreCols.find(c => centerX >= c.x && centerX < c.x + COL_W)
    if (hit) return hit.type === 'core' ? hit.key : hit.coreKey

    let best = coreCols[0]
    let bestDist = Math.abs(centerX - (best.x + COL_W / 2))
    for (let i = 1; i < coreCols.length; i++) {
      const c = coreCols[i]
      const d = Math.abs(centerX - (c.x + COL_W / 2))
      if (d < bestDist) {
        best = c
        bestDist = d
      }
    }
    return best.type === 'core' ? best.key : best.coreKey
  }

  const centerY = RULER_H + (viewport.canvasH - RULER_H) / 2
  const { rows } = buildRowLayout(
    props.trace,
    props.options.viewMode,
    expanded,
    RULER_H - viewport.scrollY,
    props.options.showSti !== false,
    stiExpanded,
  )
  const coreRows = rows.filter(r => r.type === 'core' || r.type === 'core-task')
  if (coreRows.length === 0) return null

  const rowHeight = (r) => (r.type === 'sti' ? STI_ROW_H : ROW_H)
  const hit = coreRows.find(r => centerY >= r.y && centerY < r.y + rowHeight(r))
  if (hit) return hit.type === 'core' ? hit.key : hit.coreKey

  let best = coreRows[0]
  let bestDist = Math.abs(centerY - (best.y + rowHeight(best) / 2))
  for (let i = 1; i < coreRows.length; i++) {
    const r = coreRows[i]
    const d = Math.abs(centerY - (r.y + rowHeight(r) / 2))
    if (d < bestDist) {
      best = r
      bestDist = d
    }
  }
  return best.type === 'core' ? best.key : best.coreKey
}

function scrollToTask(mergeKey) {
  if (!props.trace) return
  // Build layout at yStart=0 to get raw row offsets independent of current scrollY
  const { rows } = buildRowLayout(props.trace, props.options.viewMode, expanded, 0, props.options.showSti !== false, stiExpanded)
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

/**
 * Scroll the viewport so that seg is fully visible.
 * No-op if the segment is already within the visible time range and row.
 */
function scrollToSegmentIfNeeded(seg) {
  if (!props.trace || !seg) return
  const { timeStart, timeEnd, scrollY, scrollX, canvasH, canvasW } = viewport
  const mk = taskMergeKey(seg.task)
  const isHorizontal = orientation.value === 'h'

  // Time-axis visibility
  const timeVisible = seg.start >= timeStart && seg.end <= timeEnd

  let rowOutOfView = false
  let colOutOfView = false
  let targetRow = null
  let targetCol = null
  if (isHorizontal) {
    const { rows } = buildRowLayout(props.trace, props.options.viewMode, expanded, 0, props.options.showSti !== false)
    if (props.options.viewMode === 'core') {
      targetRow = rows.find(
        r => r.type === 'core-task' && r.coreKey === seg.core && taskMergeKey(r.taskKey) === mk,
      )
      if (!targetRow) {
        targetRow = rows.find(r => r.type === 'core-task' && taskMergeKey(r.taskKey) === mk)
      }
    } else {
      targetRow = rows.find(r => r.type === 'task' && r.key === mk)
    }

    if (targetRow) {
      const actualRowY = RULER_H - scrollY + targetRow.y
      rowOutOfView = (actualRowY + ROW_H <= RULER_H) || (actualRowY >= canvasH)
    }
  } else {
    const { cols } = buildColumnLayout(props.trace, props.options.viewMode, expanded, scrollX, props.options.showSti !== false)
    if (props.options.viewMode === 'core') {
      targetCol = cols.find(
        c => c.type === 'core-task' && c.coreKey === seg.core && taskMergeKey(c.taskKey) === mk,
      )
      if (!targetCol) {
        targetCol = cols.find(c => c.type === 'core-task' && taskMergeKey(c.taskKey) === mk)
      }
    } else {
      targetCol = cols.find(c => c.type === 'task' && c.key === mk)
    }

    if (targetCol) {
      colOutOfView = (targetCol.x + COL_W <= RULER_W) || (targetCol.x >= canvasW)
    }
  }

  if (!timeVisible) {
    const span = timeEnd - timeStart
    viewport.timeStart = seg.start - span / 2
    viewport.timeEnd   = seg.start + span / 2
  }
  if (isHorizontal && rowOutOfView && targetRow) {
    viewport.scrollY = Math.max(0, RULER_H + targetRow.y + ROW_H / 2 - canvasH / 2)
  }
  if (!isHorizontal && colOutOfView && targetCol) {
    const rawX = targetCol.x + scrollX
    viewport.scrollX = Math.max(0, RULER_W + rawX + COL_W / 2 - canvasW / 2)
  }
  if (!timeVisible || (isHorizontal && rowOutOfView && targetRow) || (!isHorizontal && colOutOfView && targetCol)) {
    scheduleRender()
  }
}

function getHoverTime() { return hoverTime.value }
function getLastActiveCursorTime() { return _handler?.getLastActiveCursorTime() ?? null }

defineExpose({ fitToTrace, scheduleRender, zoomCenter, expandAll, collapseAll, jumpToNs, getViewportCenter, getCoreAtViewportCenter, scrollToTask, scrollToSegmentIfNeeded, captureScreenshotBlob, captureAsSvg, getHoverTime, getLastActiveCursorTime })

// ---- Expand / collapse core rows -----------------------------------------
function onExpandToggle(coreName) {
  if (expanded.has(coreName)) expanded.delete(coreName)
  else expanded.add(coreName)
  scheduleRender()
}

// ---- Expand / collapse tag-event STI waveform rows -----------------------
function onStiExpandToggle(channelName) {
  if (stiExpanded.has(channelName)) stiExpanded.delete(channelName)
  else stiExpanded.add(channelName)
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
watch([() => props.options.highlightKey, () => props.options.highlightSegment, () => props.options.showGrid, () => props.options.showSti, () => props.options.darkMode, () => props.options.stiLogScale], () => {
  scheduleRender()
})
// Marks are on the overlay — no full repaint needed
watch(() => props.options.marks, () => {
  paintHoverOverlay()
}, { deep: true })

watch(() => props.options.selectedMarkId, () => {
  paintHoverOverlay()
})

// Show navigator popup on scroll / pan when content overflows the viewport
watch(
  [() => viewport.timeStart, () => viewport.timeEnd, () => viewport.scrollY, () => viewport.scrollX],
  () => {
    if (!props.trace) return
    if (showHScrollbar.value || showVScrollbar.value) {
      showOverviewPopup()
    } else {
      clearTimeout(_overviewHideTimer)
      overviewVisible.value = false
    }
  },
)

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

// ---- Navigator popup & scrollbar interaction -----------------------------

function showOverviewPopup() {
  overviewVisible.value = true
  clearTimeout(_overviewHideTimer)
  // Only schedule auto-hide when not actively dragging
  if (!_sbDrag) {
    _overviewHideTimer = setTimeout(() => { overviewVisible.value = false }, 1800)
  }
  nextTick(paintOverview)
}

function paintOverview() {
  const canvas = overviewCanvasEl.value
  if (!canvas || !props.trace || !traceBounds.value) return
  const W   = canvas.width
  const H   = canvas.height
  const ctx = canvas.getContext('2d')
  const tr  = props.trace
  const { lo, hi } = traceBounds.value
  const span = hi - lo
  if (span <= 0) return

  ctx.setTransform(1, 0, 0, 1, 0, 0)

  // ---- Background --------------------------------------------------------
  ctx.fillStyle = props.options.darkMode ? '#1a1a1a' : '#e8e8e8'
  ctx.fillRect(0, 0, W, H)

  const pxPerNs  = W / span
  const isCore   = props.options.viewMode === 'core'

  // ---- Build flat row descriptors ----------------------------------------
  // Each: { segs, color }  – no ruler, no labels, pure colored bars.
  const rowDefs = []

  if (!isCore) {
    for (const mk of tr.tasks) {
      const repr = tr.taskRepr.get(mk)
      const segs = tr.segLodUltraByMergeKey.get(mk) || tr.segByMergeKey.get(mk) || []
      if (!segs.length) continue
      rowDefs.push({ segs, color: taskColor(mk, repr) })
    }
  } else {
    for (const coreName of tr.coreNames) {
      // Core header row (solid core colour)
      const hdrSegs = tr.coreSegLodUltra.get(coreName) || tr.coreSegs.get(coreName) || []
      if (hdrSegs.length) {
        rowDefs.push({ segs: hdrSegs, color: coreColor(coreName) })
      }
      // Task sub-rows (task colour, TICK excluded)
      const taskOrder = (tr.coreTaskOrder.get(coreName) || [])
        .filter(t => parseTaskName(t).name !== 'TICK')
      for (const taskRaw of taskOrder) {
        const mk     = taskMergeKey(taskRaw)
        const tSegs  = tr.coreTaskSegLodUltra.get(coreName)?.get(taskRaw)
                    || tr.coreTaskSegs.get(coreName)?.get(taskRaw) || []
        if (!tSegs.length) continue
        rowDefs.push({ segs: tSegs, color: taskColor(mk, taskRaw) })
      }
    }
  }

  // ---- STI channel rows (separate array, painted at bottom of minimap) ---
  const stiDefs = []
  if (props.options.showSti !== false && tr.stiChannels?.length) {
    for (const ch of tr.stiChannels) {
      const evs = tr.stiEventsByTarget?.get(ch) || []
      if (!evs.length) continue
      stiDefs.push({ evs, color: stiChannelColor(ch), isExpanded: stiExpanded.has(ch) })
    }
  }

  // ---- Paint rows --------------------------------------------------------
  const STI_MINI_H  = 12  // minimum px per STI row in minimap
  const stiTotalH   = Math.min(H * 0.4, stiDefs.length * STI_MINI_H)
  const taskAreaH   = H - stiTotalH

  if (rowDefs.length) {
    const rowH = taskAreaH / rowDefs.length
    for (let i = 0; i < rowDefs.length; i++) {
      const { segs, color } = rowDefs[i]
      const y  = i * rowH
      const rh = Math.max(1, rowH - 0.3)
      ctx.fillStyle = color
      for (const seg of segs) {
        const x  = (seg.start - lo) * pxPerNs
        const sw = Math.max(0.5, (seg.end - seg.start) * pxPerNs)
        ctx.fillRect(x, y, sw, rh)
      }
    }
  }

  if (stiDefs.length) {
    const stiRowH = stiTotalH / stiDefs.length
    for (let i = 0; i < stiDefs.length; i++) {
      const { evs, color, isExpanded } = stiDefs[i]
      const y  = taskAreaH + i * stiRowH
      const rh = Math.max(2, stiRowH - 0.5)
      ctx.fillStyle = color
      if (isExpanded) {
        // Step-hold mini chart using numeric note values
        let vMin = Infinity, vMax = -Infinity
        for (const ev of evs) {
          const v = parseFloat(ev.note !== '' ? ev.note : ev.event)
          if (!isNaN(v)) { if (v < vMin) vMin = v; if (v > vMax) vMax = v }
        }
        if (isFinite(vMin) && vMin !== vMax) {
          for (let j = 0; j < evs.length; j++) {
            const ev  = evs[j]
            const v   = parseFloat(ev.note !== '' ? ev.note : ev.event)
            if (isNaN(v)) continue
            const x1    = (ev.time - lo) * pxPerNs
            const x2    = j + 1 < evs.length ? (evs[j + 1].time - lo) * pxPerNs : W
            const normV = (v - vMin) / (vMax - vMin)
            const barH  = Math.max(1, normV * rh)
            ctx.fillRect(x1, y + rh - barH, Math.max(1, x2 - x1), barH)
          }
        } else {
          // All same value or non-numeric — fall back to 2 px marks
          for (const ev of evs) {
            ctx.fillRect((ev.time - lo) * pxPerNs - 1, y, 2, rh)
          }
        }
      } else {
        // Collapsed: 2 px vertical marks at each event time
        for (const ev of evs) {
          ctx.fillRect((ev.time - lo) * pxPerNs - 1, y, 2, rh)
        }
      }
    }
  }

  // ---- Viewport indicator ------------------------------------------------
  const dark = props.options.darkMode
  ctx.strokeStyle = dark ? 'rgba(255,160,60,0.9)'  : 'rgba(200,70,10,0.85)'
  ctx.fillStyle   = dark ? 'rgba(255,160,60,0.18)' : 'rgba(200,70,10,0.12)'
  ctx.lineWidth   = 1.5

  if (orientation.value === 'h') {
    const vx = Math.max(0, (viewport.timeStart - lo) * pxPerNs)
    const vw = Math.min(W - vx, (viewport.timeEnd - viewport.timeStart) * pxPerNs)
    const totH = totalRowHeight.value
    const visH = viewport.canvasH - RULER_H
    let vy = 0
    let vh = H
    if (totH > visH && totH > 0) {
      vy = (viewport.scrollY / (totH - visH)) * (H - (visH / totH) * H)
      vh = Math.max(2, (visH / totH) * H)
    }
    ctx.beginPath()
    ctx.rect(vx, vy, Math.max(2, vw), vh)
    ctx.fill()
    ctx.stroke()
  } else {
    const pxPerNsV = H / span
    const vy = Math.max(0, (viewport.timeStart - lo) * pxPerNsV)
    const vh = Math.min(H - vy, (viewport.timeEnd - viewport.timeStart) * pxPerNsV)
    ctx.beginPath()
    ctx.rect(0, vy, W, Math.max(2, vh))
    ctx.fill()
    ctx.stroke()
  }
}

// Scrollbar mouse-move / mouse-up (attached to document during drag)
function _sbMouseMove(e) {
  if (!_sbDrag || !props.trace) return
  if (_sbDrag.type === 'h') {
    const dx   = e.clientX - _sbDrag.startX
    const newL = Math.max(0, Math.min(_sbDrag.usableW, _sbDrag.startL + dx))
    const ratio = _sbDrag.usableW > 0 ? newL / _sbDrag.usableW : 0
    if (orientation.value === 'h') {
      const newStart = _sbDrag.lo + ratio * (_sbDrag.span - _sbDrag.visSpan)
      viewport.timeStart = newStart
      viewport.timeEnd   = newStart + _sbDrag.visSpan
    } else {
      const { totalWidth } = buildColumnLayout(
        props.trace, props.options.viewMode, expanded, 0, props.options.showSti !== false,
      )
      viewport.scrollX = Math.max(0, ratio * Math.max(0, totalWidth - viewport.canvasW))
    }
    scheduleRender()
  } else {
    const dy   = e.clientY - _sbDrag.startY
    const newT = Math.max(0, Math.min(_sbDrag.usableH, _sbDrag.startT + dy))
    const ratio = _sbDrag.usableH > 0 ? newT / _sbDrag.usableH : 0
    if (orientation.value === 'h') {
      viewport.scrollY = ratio * _sbDrag.maxScrollY
    } else {
      const newStart = _sbDrag.lo + ratio * (_sbDrag.span - _sbDrag.visSpan)
      viewport.timeStart = newStart
      viewport.timeEnd   = newStart + _sbDrag.visSpan
    }
    scheduleRender()
  }
}

function _sbMouseUp() {
  _sbDrag = null
  document.removeEventListener('mousemove', _sbMouseMove)
  document.removeEventListener('mouseup', _sbMouseUp)
  // Keep overview visible for 1.5 s after releasing
  _overviewHideTimer = setTimeout(() => { overviewVisible.value = false }, 1500)
}

function onHThumbMouseDown(e) {
  if (!props.trace || !traceBounds.value) return
  const { lo, span } = traceBounds.value
  const vSbW   = showVScrollbar.value ? SCROLLBAR_SIZE : 0
  const trackW = viewport.canvasW - vSbW
  const visSpan = viewport.timeEnd - viewport.timeStart
  const thumbW  = Math.max(20, (visSpan / span) * trackW)
  const usableW = trackW - thumbW
  const startL  = usableW > 0
    ? Math.min(usableW, ((viewport.timeStart - lo) / (span - visSpan)) * usableW)
    : 0
  _sbDrag = { type: 'h', startX: e.clientX, startL, usableW, lo, span, visSpan }
  document.addEventListener('mousemove', _sbMouseMove)
  document.addEventListener('mouseup', _sbMouseUp)
  showOverviewPopup()
}

function onVThumbMouseDown(e) {
  if (!props.trace || !traceBounds.value) return
  const { lo, span } = traceBounds.value
  const hSbH   = showHScrollbar.value ? SCROLLBAR_SIZE : 0
  const trackH = viewport.canvasH - hSbH
  if (orientation.value === 'h') {
    const visH    = viewport.canvasH - RULER_H
    const bodyH   = trackH - RULER_H
    const thumbH  = Math.max(20, (visH / Math.max(1, totalRowHeight.value)) * bodyH)
    const usableH = bodyH - thumbH
    const maxScrollY = Math.max(0, totalRowHeight.value - visH)
    const startT  = usableH > 0 ? Math.min(usableH, (viewport.scrollY / Math.max(1, maxScrollY)) * usableH) : 0
    _sbDrag = { type: 'v', startY: e.clientY, startT, usableH, maxScrollY }
  } else {
    const visSpan = viewport.timeEnd - viewport.timeStart
    const bodyH   = trackH - HEADER_H
    const thumbH  = Math.max(20, (visSpan / span) * bodyH)
    const usableH = bodyH - thumbH
    const startT  = usableH > 0
      ? Math.min(usableH, ((viewport.timeStart - lo) / (span - visSpan)) * usableH)
      : 0
    _sbDrag = { type: 'v', startY: e.clientY, startT, usableH, lo, span, visSpan }
  }
  document.addEventListener('mousemove', _sbMouseMove)
  document.addEventListener('mouseup', _sbMouseUp)
  showOverviewPopup()
}

function onHTrackClick(e) {
  if (!props.trace || !traceBounds.value) return
  const { lo, span } = traceBounds.value
  const rect   = e.currentTarget.getBoundingClientRect()
  const clickX = e.clientX - rect.left
  const vSbW   = showVScrollbar.value ? SCROLLBAR_SIZE : 0
  const trackW = viewport.canvasW - vSbW
  const ratio  = Math.max(0, Math.min(1, clickX / trackW))
  if (orientation.value === 'h') {
    const visSpan  = viewport.timeEnd - viewport.timeStart
    const newStart = lo + ratio * (span - visSpan)
    viewport.timeStart = newStart
    viewport.timeEnd   = newStart + visSpan
  } else {
    const { totalWidth } = buildColumnLayout(
      props.trace, props.options.viewMode, expanded, 0, props.options.showSti !== false,
    )
    viewport.scrollX = Math.max(0, ratio * Math.max(0, totalWidth - viewport.canvasW))
  }
  scheduleRender()
  showOverviewPopup()
}

function onVTrackClick(e) {
  if (!props.trace || !traceBounds.value) return
  const { lo, span } = traceBounds.value
  const rect   = e.currentTarget.getBoundingClientRect()
  const clickY = e.clientY - rect.top
  const hSbH   = showHScrollbar.value ? SCROLLBAR_SIZE : 0
  const trackH = viewport.canvasH - hSbH
  if (orientation.value === 'h') {
    const bodyH  = trackH - RULER_H
    const ratio  = Math.max(0, Math.min(1, (clickY - RULER_H) / bodyH))
    const visH   = viewport.canvasH - RULER_H
    viewport.scrollY = ratio * Math.max(0, totalRowHeight.value - visH)
  } else {
    const bodyH  = trackH - HEADER_H
    const ratio  = Math.max(0, Math.min(1, (clickY - HEADER_H) / bodyH))
    const visSpan  = viewport.timeEnd - viewport.timeStart
    const newStart = lo + ratio * (span - visSpan)
    viewport.timeStart = newStart
    viewport.timeEnd   = newStart + visSpan
  }
  scheduleRender()
  showOverviewPopup()
}

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
  clearTimeout(_overviewHideTimer)
  document.removeEventListener('mousemove', _sbMouseMove)
  document.removeEventListener('mouseup', _sbMouseUp)
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

/* ---- Custom scrollbars ------------------------------------------------- */
.scrollbar-track {
  position: absolute;
  z-index: 15;
  border-radius: 4px;
  background: transparent;
  transition: background 0.15s;
}
.scrollbar-track:hover {
  background: rgba(128, 128, 128, 0.10);
}

.scrollbar-track-h {
  bottom: 0;
  left: 0;
  right: 0;
  height: 10px;
  cursor: pointer;
}
.scrollbar-track-h.has-v-sb {
  right: 10px;
}

.scrollbar-track-v {
  top: 0;
  right: 0;
  bottom: 0;
  width: 10px;
  cursor: pointer;
}
.scrollbar-track-v.has-h-sb {
  bottom: 10px;
}

.scrollbar-thumb {
  position: absolute;
  background: var(--sb-thumb, rgba(128, 128, 128, 0.45));
  border-radius: 3px;
  transition: background 0.1s;
}
.scrollbar-thumb:hover,
.scrollbar-track:hover .scrollbar-thumb {
  background: var(--sb-thumb-hover, rgba(128, 128, 128, 0.70));
}

/* H thumb: fill the track height, position set by :style (left/width) */
.scrollbar-track-h .scrollbar-thumb {
  top: 1px;
  bottom: 1px;
  cursor: grab;
}
.scrollbar-track-h .scrollbar-thumb:active { cursor: grabbing; }

/* V thumb: fill the track width, position set by :style (top/height) */
.scrollbar-track-v .scrollbar-thumb {
  left: 1px;
  right: 1px;
  cursor: grab;
}
.scrollbar-track-v .scrollbar-thumb:active { cursor: grabbing; }

/* ---- Navigator / overview popup ---------------------------------------- */
.overview-popup {
  position: absolute;
  bottom: 18px;
  right: 18px;
  z-index: 50;
  border-radius: 6px;
  border: 1px solid var(--border, rgba(128, 128, 128, 0.35));
  background: var(--panel-bg, #1e1e1e);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.45);
  padding: 3px;
  pointer-events: none;
}

.overview-canvas {
  display: block;
  border-radius: 3px;
}

.overview-fade-enter-active {
  transition: opacity 0.08s ease-out;
}
.overview-fade-leave-active {
  transition: opacity 0.40s ease-in;
}
.overview-fade-enter-from,
.overview-fade-leave-to {
  opacity: 0;
}
.ctx-item:hover {
  background: var(--tb-btn-hover);
}
</style>
