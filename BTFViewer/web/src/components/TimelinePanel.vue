<template>
  <div class="timeline-panel" ref="panelEl">
    <!-- Left: sticky label column -->
    <LabelColumn
      :trace="trace"
      :viewMode="options.viewMode"
      :expanded="expanded"
      :scrollY="viewport.scrollY"
      :highlightKey="options.highlightKey"
      @expandToggle="onExpandToggle"
      @highlightChange="(k) => emit('highlightChange', k)"
      @highlightClick="(k) => emit('highlightClick', k)"
    />

    <!-- Right: canvas -->
    <div class="canvas-wrap" ref="canvasWrapEl">
      <canvas ref="canvasEl" />
      <StiTooltip
        :stiEvent="stiHover"
        :x="stiHoverPos.x"
        :y="stiHoverPos.y"
        :timeScale="trace?.timeScale || 'ns'"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import LabelColumn from './LabelColumn.vue'
import StiTooltip  from './StiTooltip.vue'
import { render as renderTimeline, buildRowLayout, LABEL_W, RULER_H, STI_ROW_H } from '../renderer/TimelineRenderer.js'
import { InteractionHandler } from '../renderer/InteractionHandler.js'

// ---- Props & emits -------------------------------------------------------
const props = defineProps({
  trace:   { type: Object, default: null },
  options: { type: Object, required: true },  // { viewMode, highlightKey, showGrid, darkMode }
  cursors: { type: Array, default: () => [] },
})
const emit = defineEmits(['viewportChange', 'cursorsChange', 'highlightChange', 'highlightClick'])

// ---- Template refs -------------------------------------------------------
const panelEl     = ref(null)
const canvasWrapEl = ref(null)
const canvasEl    = ref(null)

// ---- Local state ----------------------------------------------------------
const expanded = reactive(new Set())

const viewport = reactive({
  timeStart: 0,
  timeEnd:   1,
  scrollY:   0,
  canvasW:   1,
  canvasH:   1,
})

const stiHover    = ref(null)
const stiHoverPos = reactive({ x: 0, y: 0 })
const hoverTime   = ref(null)

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
    // Draw a helpful prompt in the center
    ctx.font = '14px sans-serif'
    ctx.fillStyle = props.options.darkMode ? '#555' : '#AAA'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText('Open a .btf file to begin', w / 2, h / 2)
    return
  }

  renderTimeline(ctx, props.trace, viewport, {
    viewMode:     props.options.viewMode,
    expanded,
    cursors:      props.cursors,
    highlightKey: props.options.highlightKey,
    showGrid:     props.options.showGrid,
    darkMode:     props.options.darkMode,
    hoverTime:    hoverTime.value,
  })
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
    getOptions:  () => ({ viewMode: props.options.viewMode, expanded }),
    onViewportChange(vp) {
      viewport.timeStart = vp.timeStart
      viewport.timeEnd   = vp.timeEnd
      viewport.scrollY   = vp.scrollY ?? viewport.scrollY
      emit('viewportChange', { ...viewport })
      scheduleRender()
    },
    onCursorsChange(cursors) {
      emit('cursorsChange', cursors)
    },
    onStiHover(ev) {
      stiHover.value = ev
    },
    onHoverTimeChange(t) {
      hoverTime.value = t
      scheduleRender()
    },
    onRowHover(row) {
      // Handled via LabelColumn hover for now
    },
    onFitToWindow() {
      fitToTrace()
    },
  })
  _handler.setCursors(props.cursors)
}

// ---- Fit to trace ----------------------------------------------------------

function fitToTrace() {
  if (!props.trace) return
  const padding = (props.trace.timeMax - props.trace.timeMin) * 0.02
  viewport.timeStart = props.trace.timeMin - padding
  viewport.timeEnd   = props.trace.timeMax + padding
  viewport.scrollY   = 0
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
defineExpose({ fitToTrace, scheduleRender, zoomCenter, expandAll, collapseAll })

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
  // Fit viewport to new trace and reset scroll
  nextTick(() => {
    fitToTrace()
    setupHandler()
    scheduleRender()
  })
})

watch(() => props.options, () => scheduleRender(), { deep: true })
watch(() => props.cursors, (c) => {
  _handler?.setCursors(c)
  scheduleRender()
}, { deep: true })

// Sync canvas mouse position for STI tooltip
watch(stiHover, (ev) => {
  if (!ev || !canvasEl.value || !props.trace) return
  const w = canvasEl.value.clientWidth
  const pxPerNs = w / (viewport.timeEnd - viewport.timeStart)
  stiHoverPos.x = (ev.time - viewport.timeStart) * pxPerNs
  // Find the STI row Y from the layout so the tooltip tracks the correct row.
  const { rows } = buildRowLayout(props.trace, props.options.viewMode, expanded, RULER_H - viewport.scrollY)
  const row = rows.find(r => r.type === 'sti' && r.key === ev.target)
  stiHoverPos.y = row ? (row.y + STI_ROW_H / 2) : (canvasEl.value.clientHeight / 2)
})

// ---- Lifecycle -----------------------------------------------------------
onMounted(() => {
  setupResize()
  setupHandler()
  nextTick(() => {
    if (props.trace) fitToTrace()
    else scheduleRender()
  })
})

onBeforeUnmount(() => {
  if (_resizeObs) _resizeObs.disconnect()
  if (_handler) _handler.destroy()
  if (_rafId) cancelAnimationFrame(_rafId)
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
</style>
