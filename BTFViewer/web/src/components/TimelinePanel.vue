<template>
  <div
    ref="panelEl"
    class="timeline-panel"
    :class="{ 'vert-orient': orientation === 'v' }"
  >
    <!-- Left: sticky label column (horizontal mode only) -->
    <LabelColumn
      ref="labelColRef"
      v-if="orientation === 'h'"
      :key="options.layoutRev"
      :trace="trace"
      :label-width="labelWidth"
      :view-mode="options.viewMode"
      :expanded="expanded"
      :sti-expanded="stiExpanded"
      :scroll-y="viewport.scrollY"
      :body-h="labelBodyH"
      :row-layout="cachedRowLayout"
      :highlight-key="options.highlightKey"
      :show-sti="options.showSti !== false"
      :migrated-only-filter="!!options.migratedOnlyFilter"
      @expand-toggle="onExpandToggle"
      @highlight-change="(k) => emit('highlightChange', k)"
      @highlight-click="(k) => emit('highlightClick', k)"
      @sti-expand-toggle="onStiExpandToggle"
    />

    <div
      v-if="orientation === 'h'"
      class="label-resizer"
      title="Drag to resize label column; double-click to auto-fit"
      @mousedown.prevent.stop="onLabelResizeStart"
      @dblclick.prevent.stop="autoFitLabelWidth"
    />

    <!-- Top: column headers (vertical mode — sibling above canvas, not an overlay) -->
    <ColumnHeaderRow
      ref="headerRowRef"
      v-if="orientation === 'v' && trace"
      :key="options.layoutRev"
      :column-layout="cachedColumnLayout"
      :scroll-x="viewport.scrollX"
      :canvas-w="viewport.canvasW"
      :header-h="vertLabelHeaderH"
      :highlight-key="options.highlightKey"
      :expanded="expanded"
      @expand-toggle="onExpandToggle"
      @highlight-change="(k) => emit('highlightChange', k)"
      @highlight-click="(k) => emit('highlightClick', k)"
      @sti-expand-toggle="onStiExpandToggle"
    />

    <div
      v-if="orientation === 'v'"
      class="header-resizer"
      title="Drag to resize label row; double-click to auto-fit"
      @mousedown.prevent.stop="onHeaderResizeStart"
      @dblclick.prevent.stop="autoFitLabelWidth"
    />

    <!-- Timeline canvas -->
    <div
      ref="canvasWrapEl"
      class="canvas-wrap"
    >
      <div ref="pixiHostEl" class="pixi-host" />
      <canvas ref="canvasEl" class="chrome-canvas" />
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
      <SegmentTooltip
        :lines="segmentTooltipLines"
        :x="segmentHoverPos.x"
        :y="segmentHoverPos.y"
      />
      <!-- Right-click context menu (body: above CPU-load pane) -->
      <Teleport to="body">
        <div
          v-if="contextMenu.visible"
          class="context-menu"
          :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }"
          @mousedown.stop
          @mouseup.stop
          @click.stop
          @contextmenu.prevent.stop
          @mouseleave="contextMenu.visible = false"
        >
        <div
          class="ctx-item"
          :class="{ disabled: !hasMarks }"
          :title="hasMarks
            ? 'Clear all cursors, bookmarks, and annotations'
            : 'No cursors, bookmarks, or annotations to clear'"
          @click="onCtxClearAllMarks"
        >
          Clear all marks
        </div>
        <div
          class="ctx-sep"
          role="separator"
        />
        <template v-if="contextMenu.segment">
          <div
            class="ctx-item"
            @click="onCtxCopyTaskName"
          >
            Copy task name{{ ctxSegmentTaskName ? `  "${ctxSegmentTaskName}"` : '' }}
          </div>
          <div
            class="ctx-item"
            @click="onCtxZoomToSegment"
          >
            Zoom to this segment
          </div>
          <div
            class="ctx-item"
            @click="onCtxSelectInLegend"
          >
            Select in Legend
          </div>
          <div
            class="ctx-item"
            :class="{ disabled: !aiFeatureEnabled }"
            :title="aiFeatureEnabled
              ? ''
              : 'Enable AI Assistant in Settings → AI'"
            @click="onCtxAskAiEvent"
          >
            Ask AI about this event
          </div>
          <div
            class="ctx-sep"
            role="separator"
          />
        </template>
        <div
          class="ctx-item"
          @click="onCtxPlaceCursor"
        >
          Place cursor here{{ ctxTimeLabel ? `  (${ctxTimeLabel})` : '' }}
        </div>
        <div
          v-if="hasPlacedCursors"
          class="ctx-item"
          @click="onCtxRemoveNearestCursor"
        >
          Remove nearest cursor
        </div>
        <div
          v-if="hasPlacedCursors"
          class="ctx-item"
          @click="onCtxClearCursors"
        >
          Clear all cursors
        </div>
        <div
          v-if="hasTwoCursors"
          class="ctx-item"
          :class="{ disabled: !aiFeatureEnabled }"
          :title="aiFeatureEnabled
            ? ''
            : 'Enable AI Assistant in Settings → AI'"
          @click="onCtxExplainRegion"
        >
          Explain this region with AI
        </div>
        <div
          class="ctx-sep"
          role="separator"
        />
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
          Add Bookmark here{{ ctxTimeLabel ? `  (${ctxTimeLabel})` : '' }}
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
          Add Annotation here{{ ctxTimeLabel ? `  (${ctxTimeLabel})` : '' }}
        </div>
        <template v-if="hasBookmarks || hasAnnotations">
          <div
            class="ctx-sep"
            role="separator"
          />
          <div
            v-if="hasBookmarks"
            class="ctx-item"
            @click="onCtxClearBookmarks"
          >
            Clear all bookmarks
          </div>
          <div
            v-if="hasAnnotations"
            class="ctx-item"
            @click="onCtxClearAnnotations"
          >
            Clear all annotations
          </div>
        </template>
        <div
          class="ctx-sep"
          role="separator"
        />
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
      </Teleport>

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
            :class="{ dragging: overviewDragging }"
            width="260"
            height="130"
            @mousedown.prevent.stop="onOverviewMouseDown"
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
import ColumnHeaderRow from './ColumnHeaderRow.vue'
import StiTooltip  from './StiTooltip.vue'
import SegmentTooltip from './SegmentTooltip.vue'
import { render as renderTimeline, renderVertical, buildRowLayout, buildColumnLayout, drawHoverLine, drawHoverLineVertical, drawRangeSelect, drawRangeSelectVertical, drawMeasureRuler, drawMeasureRulerVertical, drawCursors, drawCursorsVertical, drawMarksHorizontal, drawMarksVertical, drawFindHits, drawFindHitsVertical, drawFindingHits, drawFindingHitsVertical, RULER_H, isStiTagChannel, RULER_W, COL_W, HEADER_H, formatTime, rowBandHeight, visibleRowIndexRange, taskPassesRowFilter, filteredCoreViewTasks, coreViewTaskFilterActive } from '../renderer/TimelineRenderer.js'
import { getTimelineLayout, setTimelineLayout } from '../utils/timelineLayout.js'
import { buildZoomPresetOptions, matchZoomPresetValue } from '../utils/zoomPresets.js'
import { renderToSvg } from '../renderer/SvgExporter.js'
import { captureLabelColumnBlob, captureColumnHeaderBlob } from '../renderer/labelColumnCapture.js'
import { InteractionHandler } from '../renderer/InteractionHandler.js'
import { taskMergeKey, taskColor, coreTint, stiNoteColor, stiChannelColor, taskDisplayName, taskReprGet } from '../utils/colors.js'
import { segmentTooltipLines as buildSegmentTooltipLines } from '../utils/statsAnalysis.js'
import { isRestorableViewport } from '../utils/sessionStore.js'
import { lodReduce } from '../utils/lod.js'
import { collectSegmentStarts } from '../utils/snapBoundary.js'
import { bisectLeft, bisectRight } from '../utils/bisect.js'
import { pixiTimelineHost } from '../renderer/pixi/PixiTimelineHost.js'
import {
  initWasmAccel,
  registerTraceWasmAccel,
  unregisterTraceWasmAccel,
  packRowLayoutWasm,
  wasmAccelReady,
} from '../renderer/wasmAccel.js'

function layout() {
  return getTimelineLayout()
}

// ---- Props & emits -------------------------------------------------------
const props = defineProps({
  trace:   { type: Object, default: null },
  options: { type: Object, required: true },  // { viewMode, highlightKey, showGrid, darkMode, orientation, marks }
  cursors: { type: Array, default: () => [] },
  maxCursors: { type: Number, default: 8 },
  labelWidth: { type: Number, default: 160 },
  findHits: { type: Array, default: () => [] },
  findingHits: { type: Array, default: () => [] },
  findMarkerNs: { type: Number, default: null },
  /** Per-tab viewport from session store; applied on trace load instead of fit-to-trace when valid. */
  persistedViewport: { type: Object, default: null },
  /** Force WebGL segment renderer on/off; auto when unset (traces with 5k+ segments). */
  useWebGL: { type: Boolean, default: null },
  /** Decimal-digit precision for times shown in the segment-hover tooltip. */
  timeDecimals: { type: Number, default: 3 },
  aiEnabled: { type: Boolean, default: true },
})
const emit = defineEmits([
  'viewportChange', 'cursorsChange', 'hoverTimeChange', 'highlightChange', 'highlightClick',
  'segmentClick', 'clearSelection', 'addBookmark', 'addAnnotation', 'markMove', 'copyScreenshot',
  'beforeCursorChange', 'beforeMarkChange', 'labelWidthChange', 'explainRegion', 'askAiEvent',
  'clearBookmarks', 'clearAnnotations', 'clearAllMarks',
])

const aiFeatureEnabled = computed(() => props.aiEnabled !== false)

// ---- Template refs -------------------------------------------------------
const panelEl     = ref(null)
const labelColRef = ref(null)
const headerRowRef = ref(null)
const canvasWrapEl = ref(null)
const pixiHostEl  = ref(null)
const canvasEl    = ref(null)
const overlayEl   = ref(null)

// ---- Local state ----------------------------------------------------------
const expanded    = reactive(new Set())
const stiExpanded = reactive(new Set())

/** Auto-expand all cores only on small traces; large SMP traces stay collapsed. */
const AUTO_EXPAND_CORES_MAX = 8

const orientation = computed(() => props.options.orientation || 'h')

/** Vertical-mode top label band height (DOM header row above the canvas). */
const vertLabelHeaderH = computed(() => props.labelWidth || HEADER_H)
/** Vertical canvas has no internal header band — the DOM row sits above canvas-wrap. */
const vertCanvasHeaderH = 0

function layoutFilterArgs() {
  return [
    !!props.options.migratedOnlyFilter,
    props.options.taskFilterKeys || null,
    props.options.taskFilterText || '',
  ]
}

// Cached row/column structure (scroll-independent — offset applied at paint time).
const cachedRowLayout = computed(() => {
  void props.options.layoutRev
  if (!props.trace) return null
  return buildRowLayout(
    props.trace, props.options.viewMode, expanded, 0,
    props.options.showSti !== false, stiExpanded,
    ...layoutFilterArgs(),
  )
})

const cachedColumnLayout = computed(() => {
  void props.options.layoutRev
  if (!props.trace) return null
  return buildColumnLayout(
    props.trace, props.options.viewMode, expanded, 0,
    props.options.showSti !== false, stiExpanded,
    ...layoutFilterArgs(),
  )
})

// ---- Scrollbar geometry --------------------------------------------------
const traceBounds = computed(() => {
  if (!props.trace) return null
  const lo = props.trace.timeMin >= 0 ? Math.max(0, props.trace.timeMin) : props.trace.timeMin
  return { lo, hi: props.trace.timeMax, span: props.trace.timeMax - lo }
})

const totalRowHeight = computed(() => {
  if (!props.trace || orientation.value !== 'h') return 0
  return cachedRowLayout.value?.totalHeight ?? 0
})

const labelBodyH = computed(() => Math.max(0, viewport.canvasH - RULER_H))

const totalColumnWidth = computed(() => {
  if (!props.trace || orientation.value !== 'v') return 0
  return cachedColumnLayout.value?.totalWidth ?? 0
})

const showHScrollbar = computed(() => {
  if (!props.trace || !traceBounds.value) return false
  if (orientation.value === 'h') {
    return (viewport.timeEnd - viewport.timeStart) < traceBounds.value.span - 1
  }
  // Vertical mode: H scrollbar = column scroll
  return totalColumnWidth.value > viewport.canvasW + 1
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
  const totalWidth = totalColumnWidth.value
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
  // Vertical mode – time scroll (canvas-wrap is body-only; no header band inside)
  const visSpan = viewport.timeEnd - viewport.timeStart
  const bodyH   = trackH
  const thumbH  = Math.max(20, (visSpan / traceBounds.value.span) * bodyH)
  const maxTop  = bodyH - thumbH
  const thumbT  = maxTop > 0
    ? Math.min(maxTop, ((viewport.timeStart - traceBounds.value.lo) / (traceBounds.value.span - visSpan)) * maxTop)
    : 0
  return { height: `${thumbH}px`, top: `${thumbT}px` }
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
const segmentHover = ref(null)
const segmentHoverPos = reactive({ x: 0, y: 0 })
const segmentTooltipLines = computed(() => {
  if (!segmentHover.value || !props.trace) return []
  return buildSegmentTooltipLines(props.trace, segmentHover.value, formatTime, taskDisplayName, props.timeDecimals)
})
const hoverTime   = ref(null)
const rangeSelect = ref(null)  // { t0, t1 } while middle-dragging a zoom region
const measureRuler = ref(null) // { t0, t1, anchorPx } while Ctrl-dragging the measure tool

// Right-click context menu
const contextMenu = reactive({ visible: false, x: 0, y: 0, ns: 0, shiftKey: false, segment: null })

const ctxSegmentTaskName = computed(() => {
  const seg = contextMenu.segment
  if (!seg || !props.trace) return ''
  const raw = taskReprGet(props.trace, taskMergeKey(seg.task)) || seg.task
  return taskDisplayName(raw)
})

const hasPlacedCursors = computed(() => props.cursors.some(c => c != null))
const hasTwoCursors = computed(() => props.cursors.filter(c => c != null).length >= 2)
const hasBookmarks = computed(() =>
  (props.options.marks || []).some(m => m && m.type !== 'annotation'))
const hasAnnotations = computed(() =>
  (props.options.marks || []).some(m => m && m.type === 'annotation'))
const hasMarks = computed(() =>
  hasPlacedCursors.value || hasBookmarks.value || hasAnnotations.value)
const ctxTimeLabel = computed(() => {
  if (!props.trace || contextMenu.ns == null) return ''
  return formatTime(contextMenu.ns, props.trace.timeScale, props.timeDecimals)
})

// ---- Scrollbars & navigator popup ----------------------------------------
const SCROLLBAR_SIZE   = 10          // px – scrollbar track thickness
const overviewCanvasEl = ref(null)
const overviewVisible  = ref(false)
const overviewDragging = ref(false)
let   _overviewHideTimer = null
let   _sbDrag            = null      // active scrollbar drag state: { type, … }
let   _ovDrag            = null      // active overview indicator drag: { grabX, grabY, ind }
// OffscreenCanvas cache for the overview background (rows + STI + border).
// Rebuilt only when trace/mode/STI state changes; scroll only repaints the overlay rect.
let _ovBgCanvas      = null   // OffscreenCanvas | null
let _ovBgTrace       = null   // trace identity (object ref)
let _ovBgMode        = null   // viewMode string
let _ovBgShowSti     = null   // showSti option value
let _ovBgExpandedKey = null   // sorted join of expanded STI channels
let _ovBgOrientation = null  // 'h' | 'v' when background was built

// WASM row cull cache (rebuilt when layout or trace changes).
let _packedRows = null
let _mainCtx = null

// ---- Interaction fast-paint (coarse LOD while panning/zooming) ------------
let _interacting = false
let _interactEndTimer = null
const INTERACT_SETTLE_MS = 250

// After trace load, paint coarse LOD once then upgrade — avoids multi-hundred-ms rAF stalls.
let _loadSettling = false
let _loadSettleTimer = null
const LOAD_SETTLE_MS = 350
/** Snapshot export: full-quality paint at CSS pixel ratio (see prepareCanvasForCapture). */
let _captureForceFull = false
/** Above this segment count, fit-to-window stays on coarse LOD; full quality only when zoomed in. */
const LARGE_TRACE_SEGS = 25_000

function isLargeTrace() {
  return (props.trace?.segments?.length ?? 0) >= LARGE_TRACE_SEGS
}

function useWebGLRenderer() {
  if (pixiTimelineHost.failed) return false
  if (props.useWebGL === false) return false
  return pixiTimelineHost.ready
}

function traceTimeBounds() {
  if (!props.trace) return null
  const lo = props.trace.timeMin >= 0 ? Math.max(0, props.trace.timeMin) : props.trace.timeMin
  return { lo, hi: props.trace.timeMax }
}

/** Fraction of trace span visible; 1 = fit-to-window. */
function visibleTimeSpanRatio() {
  const b = traceTimeBounds()
  if (!b) return 1
  const traceSpan = b.hi - b.lo
  if (traceSpan <= 0) return 1
  return (viewport.timeEnd - viewport.timeStart) / traceSpan
}

/** True when the visible window shows essentially the whole trace (post-Fit zoom). */
function isFitToWindowZoom() {
  const ratio = visibleTimeSpanRatio()
  // Core summary rows multiplex every task on a core — stay on coarse LOD longer.
  if (props.options.viewMode === 'core' && isLargeTrace()) return ratio >= 0.65
  return ratio >= 0.92
}

/**
 * Coarse LOD / reduced segment budget.
 * Large traces: coarse while panning/zooming and at idle fit-to-window.
 */
function paintCoarse() {
  if (_captureForceFull) return false
  if (_loadSettling) return true
  if (isLargeTrace() && _interacting) return true
  if (isLargeTrace() && isFitToWindowZoom()) return true
  return false
}

/** Skip grid/TICK/hover while interacting or load-settling — not at idle fit. */
function paintFast() {
  if (_captureForceFull) return false
  if (_loadSettling) return true
  if (isLargeTrace() && _interacting) return true
  return false
}

function paintDpr() {
  if (_captureForceFull) return 1
  if (_loadSettling || (isLargeTrace() && _interacting)) return 1
  if (isLargeTrace()) {
    // Allow retina once zoomed in past overview level.
    if (visibleTimeSpanRatio() < 0.5) return window.devicePixelRatio || 1
    return 1
  }
  return window.devicePixelRatio || 1
}

/** Full-quality synchronous paint before screenshot (colored segments + crisp labels). */
async function prepareCanvasForCapture() {
  _captureForceFull = true
  paint()
  if (useWebGLRenderer()) pixiTimelineHost.endFrame()
  await new Promise((resolve) => requestAnimationFrame(resolve))
  _captureForceFull = false
}

function scheduleFullQualityRender() {
  const run = () => {
    if (!props.trace) return
    scheduleRender()
  }
  if (typeof requestIdleCallback === 'function') {
    requestIdleCallback(run, { timeout: 1000 })
  } else {
    setTimeout(run, 32)
  }
}

function endLoadSettlePaint() {
  _loadSettling = false
  _loadSettleTimer = null
  scheduleRender()
}

function beginLoadSettle() {
  _loadSettling = true
  clearTimeout(_loadSettleTimer)
  _loadSettleTimer = setTimeout(() => {
    endLoadSettlePaint()
    if (overviewVisible.value) scheduleOverviewPaint()
  }, LOAD_SETTLE_MS)
}

function endLoadSettle() {
  _loadSettling = false
  clearTimeout(_loadSettleTimer)
  _loadSettleTimer = null
}

function markInteracting(_timeAxisChanged = false) {
  _interacting = true
  clearTimeout(_interactEndTimer)
  _interactEndTimer = setTimeout(() => {
    _interacting = false
    scheduleRender()
    if (overviewVisible.value) scheduleOverviewPaint()
  }, INTERACT_SETTLE_MS)
}

// ---- Renderer loop --------------------------------------------------------
let _rafId = null
let _dirty = false
let _ovPaintRaf = null

function scheduleRender(immediate = false) {
  _dirty = true
  if (immediate) {
    if (_rafId) {
      cancelAnimationFrame(_rafId)
      _rafId = null
    }
    _dirty = false
    paint()
    if (overviewVisible.value && !paintFast()) scheduleOverviewPaint()
    return
  }
  if (!_rafId) {
    _rafId = requestAnimationFrame(() => {
      _rafId = null
      if (_dirty) {
        _dirty = false
        paint()
        if (overviewVisible.value && !paintFast()) scheduleOverviewPaint()
      }
    })
  }
}

function scheduleOverviewPaint() {
  nextTick(() => {
    if (_ovPaintRaf) return
    _ovPaintRaf = requestAnimationFrame(() => {
      _ovPaintRaf = null
      if (overviewVisible.value) paintOverview()
    })
  })
}

function paint() {
  const canvas = canvasEl.value
  if (!canvas) return
  if (!_mainCtx) {
    _mainCtx = canvas.getContext('2d', { alpha: true, desynchronized: true })
  }
  const ctx = _mainCtx
  const dpr = paintDpr()
  const w   = canvas.clientWidth
  const h   = canvas.clientHeight

  if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
    canvas.width  = Math.round(w * dpr)
    canvas.height = Math.round(h * dpr)
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  }

  viewport.canvasW = w
  viewport.canvasH = h

  if (props.trace && (w <= 0 || h <= 0)) {
    requestAnimationFrame(() => scheduleRender())
    return
  }

  if (ensureTraceViewport()) return

  const webgl = useWebGLRenderer()
  if (webgl) {
    pixiTimelineHost.setBackground(props.options.darkMode ? 0x1E1E1E : 0xFFFFFF)
    pixiTimelineHost.resize(w, h)
    pixiTimelineHost.beginFrame()
  }

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
    highlightInterval: props.options.highlightInterval ?? null,
    showGrid:         props.options.showGrid,
    showSti:          props.options.showSti !== false,
    stiLogScale:      !!props.options.stiLogScale,
    darkMode:         props.options.darkMode,
    migratedOnlyFilter: !!props.options.migratedOnlyFilter,
    taskFilterKeys:     props.options.taskFilterKeys || null,
    taskFilterText:     props.options.taskFilterText || '',
    lockedTaskKey:    props.options.lockedTaskKey ?? null,
    showHoverHighlight: !!props.options.showHoverHighlight,
    fastPaint:        paintFast(),
    coarseLod:        paintCoarse(),
    rowLayout:        cachedRowLayout.value,
    columnLayout:     cachedColumnLayout.value,
    packedRows:       _packedRows,
    gpuBatch:         webgl ? pixiTimelineHost.batcher : null,
    gpuStripes:       webgl ? pixiTimelineHost.stripeBatcher : null,
    skipColumnHeaders: orientation.value === 'v',
    labelHeaderH: orientation.value === 'v' ? vertCanvasHeaderH : vertLabelHeaderH.value,
  }
  if (orientation.value === 'v') {
    renderVertical(ctx, props.trace, viewport, renderOpts)
  } else {
    renderTimeline(ctx, props.trace, viewport, renderOpts)
  }

  if (webgl) pixiTimelineHost.endFrame()

  // Overlay is updated on hover; skip during pan/zoom and initial trace load.
  if (!paintFast()) paintHoverOverlay()
}

// ---- Overlay canvas: hover line only -------------------------------------
// Redraws only the hover indicator — never triggers a full segment repaint.
function paintHoverOverlay() {
  const canvas = overlayEl.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  const dpr = paintDpr()
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
    const hh = vertCanvasHeaderH
    const bodyH   = canvasH
    const pxPerNs = bodyH / (timeEnd - timeStart)
    drawMarksVertical(ctx, marks, props.trace, timeStart, pxPerNs, canvasW, canvasH, hh, darkMode, props.options.selectedMarkId ?? null)
    drawCursorsVertical(ctx, props.cursors, props.trace, timeStart, pxPerNs, canvasW, canvasH, hh, darkMode, props.timeDecimals)
    drawFindHitsVertical(ctx, props.findHits, props.findMarkerNs, props.trace, timeStart, pxPerNs, canvasW, canvasH, hh, darkMode)
    drawFindingHitsVertical(ctx, props.findingHits, props.trace, timeStart, pxPerNs, canvasW, canvasH, hh, darkMode)
    if (rangeSelect.value)
      drawRangeSelectVertical(ctx, rangeSelect.value.t0, rangeSelect.value.t1, timeStart, pxPerNs, canvasW, canvasH, hh, darkMode)
    if (measureRuler.value)
      drawMeasureRulerVertical(ctx, measureRuler.value.t0, measureRuler.value.t1, measureRuler.value.anchorPx, props.trace, timeStart, pxPerNs, canvasW, canvasH, hh, darkMode, props.timeDecimals)
    if (hoverTime.value !== null)
      drawHoverLineVertical(ctx, hoverTime.value, props.trace, timeStart, pxPerNs, canvasW, canvasH, hh, darkMode, props.timeDecimals)
  } else {
    const pxPerNs = canvasW / (timeEnd - timeStart)
    drawMarksHorizontal(ctx, marks, props.trace, timeStart, pxPerNs, canvasW, canvasH, darkMode, props.options.selectedMarkId ?? null)
    drawCursors(ctx, props.cursors, props.trace, timeStart, pxPerNs, canvasW, canvasH, darkMode, props.timeDecimals)
    drawFindHits(ctx, props.findHits, props.findMarkerNs, props.trace, timeStart, pxPerNs, canvasW, canvasH, darkMode)
    drawFindingHits(ctx, props.findingHits, props.trace, timeStart, pxPerNs, canvasW, canvasH, darkMode)
    if (rangeSelect.value)
      drawRangeSelect(ctx, rangeSelect.value.t0, rangeSelect.value.t1, timeStart, pxPerNs, canvasW, canvasH, darkMode)
    if (measureRuler.value)
      drawMeasureRuler(ctx, measureRuler.value.t0, measureRuler.value.t1, measureRuler.value.anchorPx, props.trace, timeStart, pxPerNs, canvasW, canvasH, darkMode, props.timeDecimals)
    if (hoverTime.value !== null)
      drawHoverLine(ctx, hoverTime.value, props.trace, timeStart, pxPerNs, canvasW, canvasH, darkMode, props.timeDecimals)
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
  const target = canvasWrapEl.value || canvasEl.value
  const wheelTarget = panelEl.value || target
  if (!target) return
  _handler = new InteractionHandler(target, {
    wheelTarget,
    getTrace:    () => props.trace,
    getViewport: () => ({ ...viewport }),
    getMaxCursors: () => props.maxCursors,
    getOptions:  () => ({
      viewMode: props.options.viewMode,
      expanded,
      stiExpanded,
      orientation: orientation.value,
      showSti: props.options.showSti !== false,
      migratedOnlyFilter: !!props.options.migratedOnlyFilter,
      rowLayout: cachedRowLayout.value,
      columnLayout: cachedColumnLayout.value,
      vertHeaderH: orientation.value === 'v' ? vertCanvasHeaderH : vertLabelHeaderH.value,
    }),
    getMarks:    () => props.options.marks || [],
    onViewportChange(vp) {
      const vert = orientation.value === 'v'
      const prevScrollY = viewport.scrollY
      const prevScrollX = viewport.scrollX || 0
      const timeAxisChanged = vp.timeStart !== viewport.timeStart
        || vp.timeEnd !== viewport.timeEnd
        || (vert && vp.scrollX != null && vp.scrollX !== prevScrollX)

      viewport.timeStart = vp.timeStart
      viewport.timeEnd   = vp.timeEnd
      if (vp.scrollY != null) {
        if (props.trace) {
          const totalHeight = cachedRowLayout.value?.totalHeight ?? 0
          const maxScrollY = Math.max(0, totalHeight - (viewport.canvasH - RULER_H))
          viewport.scrollY = Math.max(0, Math.min(vp.scrollY, maxScrollY))
        } else {
          viewport.scrollY = Math.max(0, vp.scrollY)
        }
      }
      if (vp.scrollX != null) {
        if (props.trace && orientation.value === 'v') {
          const totalWidth = cachedColumnLayout.value?.totalWidth ?? 0
          const maxScrollX = Math.max(0, totalWidth - viewport.canvasW)
          viewport.scrollX = Math.max(0, Math.min(vp.scrollX, maxScrollX))
        } else {
          viewport.scrollX = Math.max(0, vp.scrollX)
        }
      }
      const orthChanged = viewport.scrollY !== prevScrollY
        || viewport.scrollX !== prevScrollX
      emit('viewportChange', { ...viewport })
      markInteracting(timeAxisChanged || orthChanged)
      // Orthogonal scroll: paint immediately — deferring to the next rAF leaves
      // one frame of empty canvas when the wheel queue flushes in this frame.
      scheduleRender(orthChanged && !timeAxisChanged)
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
    onSegmentHover(seg) {
      segmentHover.value = seg
    },
    onHoverTimeChange(t) {
      hoverTime.value = t
      emit('hoverTimeChange', t)
      if (!_interacting) paintHoverOverlay()
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
    onClearSelection() {
      emit('clearSelection')
    },
    onFitToWindow() {
      fitToTrace()
    },
    onExpandToggle(key) {
      onExpandToggle(key)
    },
    onStiExpandToggle(key) {
      onStiExpandToggle(key)
    },
    onBeforeCursorChange() {
      emit('beforeCursorChange')
    },
    onBeforeMarkChange() {
      emit('beforeMarkChange')
    },
    onContextMenu({ ns, x, y, shiftKey, segment }) {
      if (shiftKey) {
        _handler?.clearAllCursors()
        return
      }
      contextMenu.ns      = ns
      contextMenu.x       = x
      contextMenu.y       = y
      contextMenu.shiftKey = !!shiftKey
      contextMenu.segment = segment ?? null
      contextMenu.visible = true
      nextTick(() => {
        const el = document.querySelector('.context-menu')
        if (!el) return
        const r = el.getBoundingClientRect()
        const pad = 8
        let nx = x
        let ny = y
        if (nx + r.width > window.innerWidth - pad) {
          nx = Math.max(pad, window.innerWidth - pad - r.width)
        }
        if (ny + r.height > window.innerHeight - pad) {
          ny = Math.max(pad, window.innerHeight - pad - r.height)
        }
        contextMenu.x = nx
        contextMenu.y = ny
      })
    },
    onRangeSelectChange({ t0, t1 }) {
      rangeSelect.value = { t0, t1 }
      markInteracting(true)
      paintHoverOverlay()
    },
    onRangeSelectEnd() {
      rangeSelect.value = null
      paintHoverOverlay()
    },
    onMeasureChange({ t0, t1, anchorPx }) {
      contextMenu.visible = false
      measureRuler.value = { t0, t1, anchorPx }
      markInteracting(true)
      paintHoverOverlay()
    },
    onMeasureEnd() {
      measureRuler.value = null
      paintHoverOverlay()
    },
  })
  _handler.setCursors(props.cursors)
}

// ---- Context menu actions -------------------------------------------------

function onCtxPlaceCursor() {
  contextMenu.visible = false
  _handler?.placeCursorAt(contextMenu.ns, contextMenu.shiftKey)
}

function onCtxRemoveNearestCursor() {
  contextMenu.visible = false
  _handler?.removeNearestCursor(contextMenu.ns)
}

function onCtxClearCursors() {
  contextMenu.visible = false
  _handler?.clearAllCursors()
}

function onCtxExplainRegion() {
  if (!aiFeatureEnabled.value) return
  contextMenu.visible = false
  emit('explainRegion')
}

function onAddBookmark() {
  contextMenu.visible = false
  emit('addBookmark', contextMenu.ns)
}

function onAddAnnotation() {
  contextMenu.visible = false
  emit('addAnnotation', contextMenu.ns)
}

function onCtxClearBookmarks() {
  contextMenu.visible = false
  emit('clearBookmarks')
}

function onCtxClearAnnotations() {
  contextMenu.visible = false
  emit('clearAnnotations')
}

function onCtxClearAllMarks() {
  if (!hasMarks.value) return
  contextMenu.visible = false
  emit('clearAllMarks')
}

function onCopyCursorTime() {
  contextMenu.visible = false
  if (!props.trace) return
  const label = formatTime(contextMenu.ns, props.trace.timeScale, props.timeDecimals)
  navigator.clipboard?.writeText(label).catch(() => {})
}

function onCtxCopyTaskName() {
  contextMenu.visible = false
  if (!ctxSegmentTaskName.value) return
  navigator.clipboard?.writeText(ctxSegmentTaskName.value).catch(() => {})
}

function onCtxZoomToSegment() {
  contextMenu.visible = false
  const seg = contextMenu.segment
  if (seg) _handler?.zoomToSegment(seg)
}

function onCtxSelectInLegend() {
  contextMenu.visible = false
  const seg = contextMenu.segment
  if (!seg) return
  emit('highlightClick', taskMergeKey(seg.task))
}

function onCtxAskAiEvent() {
  if (!aiFeatureEnabled.value) return
  contextMenu.visible = false
  const seg = contextMenu.segment
  if (!seg) return
  emit('askAiEvent', {
    task: ctxSegmentTaskName.value || seg.task,
    core: seg.core,
    start: seg.start,
    stop: seg.end,
    ns: contextMenu.ns,
  })
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
    highlightInterval: props.options.highlightInterval ?? null,
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

function captureDomFilter(node) {
  if (!(node instanceof HTMLElement)) return true
  return !node.classList.contains('context-menu') && !node.classList.contains('sti-tooltip')
}

function loadImageFromBlob(blob) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(blob)
    const img = new Image()
    img.onload = () => {
      URL.revokeObjectURL(url)
      resolve(img)
    }
    img.onerror = () => {
      URL.revokeObjectURL(url)
      reject(new Error('image load failed'))
    }
    img.src = url
  })
}

async function stitchImagesHorizontal(leftImg, rightImg) {
  const out = document.createElement('canvas')
  out.width = leftImg.naturalWidth + rightImg.naturalWidth
  out.height = Math.max(leftImg.naturalHeight, rightImg.naturalHeight)
  const ctx = out.getContext('2d')
  if (!ctx) return null
  ctx.drawImage(leftImg, 0, 0)
  ctx.drawImage(rightImg, leftImg.naturalWidth, 0)
  return await new Promise((resolve) => out.toBlob(resolve, 'image/png'))
}

async function stitchImagesVertical(topImg, bottomImg) {
  const out = document.createElement('canvas')
  out.width = Math.max(topImg.naturalWidth, bottomImg.naturalWidth)
  out.height = topImg.naturalHeight + bottomImg.naturalHeight
  const ctx = out.getContext('2d')
  if (!ctx) return null
  ctx.drawImage(topImg, 0, 0)
  ctx.drawImage(bottomImg, 0, topImg.naturalHeight)
  return await new Promise((resolve) => out.toBlob(resolve, 'image/png'))
}

/** Label/header canvas + timeline canvas — html-to-image cannot rasterise WebGL/canvas reliably. */
async function captureCompositeScreenshotBlob(captureW, _captureH) {
  const wrap = canvasWrapEl.value
  if (!wrap) return null

  const timelineW = wrap.clientWidth
  const stampH = viewport.canvasH || wrap.clientHeight
  const timelineH = Math.min(stampH, wrap.clientHeight)
  if (timelineW <= 0 || timelineH <= 0) return null

  const timelineBlob = await captureCanvasViewportBlob(timelineW, timelineH)
  if (!timelineBlob) return null

  if (orientation.value === 'h') {
    const labelW = labelColRef.value?.colEl?.clientWidth ?? props.labelWidth
    const labelBlob = await captureLabelColumnBlob({
      rowLayout: cachedRowLayout.value,
      scrollY: viewport.scrollY,
      width: labelW,
      height: timelineH,
      viewMode: props.options.viewMode,
      darkMode: props.options.darkMode,
      expanded,
      stiExpanded,
      pixelRatio: 1,
    })
    if (!labelBlob) return timelineBlob
    try {
      const [labelImg, timelineImg] = await Promise.all([
        loadImageFromBlob(labelBlob),
        loadImageFromBlob(timelineBlob),
      ])
      return await stitchImagesHorizontal(labelImg, timelineImg)
    } catch {
      return timelineBlob
    }
  }

  const headerH = headerRowRef.value?.rowEl?.clientHeight ?? vertLabelHeaderH.value
  const headerBlob = await captureColumnHeaderBlob({
    columnLayout: cachedColumnLayout.value,
    scrollX: viewport.scrollX,
    canvasW: captureW,
    headerH,
    darkMode: props.options.darkMode,
    expanded,
    pixelRatio: 1,
  })
  if (!headerBlob) return timelineBlob
  try {
    const [headerImg, timelineImg] = await Promise.all([
      loadImageFromBlob(headerBlob),
      loadImageFromBlob(timelineBlob),
    ])
    return await stitchImagesVertical(headerImg, timelineImg)
  } catch {
    return timelineBlob
  }
}

async function captureScreenshotBlob() {
  const root = panelEl.value
  const { captureW, captureH } = getCaptureSize()
  if (!captureW || !captureH) return null

  await prepareCanvasForCapture()

  const composite = await captureCompositeScreenshotBlob(captureW, captureH)
  if (composite) return composite

  if (root) {
    try {
      const blob = await domToBlob(root, {
        cacheBust: true,
        pixelRatio: window.devicePixelRatio || 1,
        width: captureW,
        height: captureH,
        filter: captureDomFilter,
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

  const { totalHeight } = buildRowLayout(
    props.trace, props.options.viewMode, expanded, 0,
    props.options.showSti !== false, stiExpanded,
    !!props.options.migratedOnlyFilter,
    props.options.taskFilterKeys || null,
    props.options.taskFilterText || '',
  )
  const neededH = RULER_H + Math.max(layout().rowH, totalHeight)
  const captureH = Math.max(RULER_H + layout().rowH, Math.min(panelH, Math.ceil(neededH)))
  return { captureW: panelW, captureH }
}

async function captureCanvasViewportBlob(captureW, captureH) {
  const base = canvasEl.value
  const overlay = overlayEl.value
  const wrap = canvasWrapEl.value
  if (!base || !overlay || !wrap) return null

  const w = Math.min(captureW, wrap.clientWidth)
  const h = Math.min(captureH, wrap.clientHeight)
  if (w <= 0 || h <= 0) return null

  const out = document.createElement('canvas')
  out.width = w
  out.height = h
  const outCtx = out.getContext('2d')
  if (!outCtx) return null

  const panelStyle = getComputedStyle(panelEl.value || wrap)
  const bg = panelStyle.getPropertyValue('--bg').trim() || (props.options.darkMode ? '#1E1E1E' : '#FFFFFF')
  outCtx.fillStyle = bg
  outCtx.fillRect(0, 0, w, h)

  const pixiCanvas = pixiTimelineHost.app?.canvas
  if (pixiCanvas && useWebGLRenderer()) {
    outCtx.drawImage(pixiCanvas, 0, 0, pixiCanvas.width, pixiCanvas.height, 0, 0, w, h)
  }
  outCtx.drawImage(base, 0, 0, base.width, base.height, 0, 0, w, h)
  outCtx.drawImage(overlay, 0, 0, overlay.width, overlay.height, 0, 0, w, h)

  return await new Promise((resolve) => out.toBlob(resolve, 'image/png'))
}

// ---- Close context menu on outside click ----------------------------------
function onGlobalClick() {
  if (contextMenu.visible) {
    contextMenu.visible = false
  }
}

function emitViewportChange(extra = {}) {
  emit('viewportChange', { ...viewport, ...extra })
}

/** Keep scroll within content after row/column layout shrinks (e.g. collapse all). */
function clampScrollToContent() {
  if (!props.trace) return
  if (orientation.value === 'h') {
    const visH = viewport.canvasH - RULER_H
    const maxScrollY = Math.max(0, totalRowHeight.value - visH)
    viewport.scrollY = Math.max(0, Math.min(viewport.scrollY || 0, maxScrollY))
  } else {
    const maxScrollX = Math.max(0, totalColumnWidth.value - viewport.canvasW)
    viewport.scrollX = Math.max(0, Math.min(viewport.scrollX || 0, maxScrollX))
  }
}

// ---- Fit to trace ----------------------------------------------------------

function fitToTrace() {
  if (!props.trace) return
  _handler?.cancelPendingViewport?.()
  const lo = props.trace.timeMin >= 0 ? Math.max(0, props.trace.timeMin) : props.trace.timeMin
  const hi = props.trace.timeMax
  viewport.timeStart = lo
  viewport.timeEnd   = hi
  viewport.scrollY   = 0
  viewport.scrollX   = 0
  emitViewportChange()
  scheduleRender()
}

function applyViewport(vp) {
  if (!props.trace || !vp) return false
  if (!isRestorableViewport(vp, props.trace)) {
    fitToTrace()
    return true
  }
  const lo = props.trace.timeMin >= 0 ? Math.max(0, props.trace.timeMin) : props.trace.timeMin
  const hi = props.trace.timeMax
  let timeStart = vp.timeStart
  let timeEnd = vp.timeEnd
  if (timeEnd <= timeStart) {
    fitToTrace()
    return true
  }
  const minSpan = Math.max(1, (hi - lo) * 1e-6)
  if (timeEnd - timeStart < minSpan) {
    const center = (timeStart + timeEnd) / 2
    timeStart = center - minSpan / 2
    timeEnd = center + minSpan / 2
  }
  timeStart = Math.max(lo, timeStart)
  timeEnd = Math.min(hi, timeEnd)
  if (timeEnd - timeStart < minSpan) {
    if (timeStart <= lo) timeEnd = Math.min(hi, lo + minSpan)
    else timeStart = Math.max(lo, hi - minSpan)
  }
  viewport.timeStart = timeStart
  viewport.timeEnd = timeEnd
  viewport.scrollX = vp.scrollX ?? 0
  viewport.scrollY = vp.scrollY ?? 0
  emitViewportChange()
  scheduleRender()
  return true
}

// ---- Zoom around center (called from parent via ref) ---------------------
function zoomCenter(factor) {
  const span   = (viewport.timeEnd - viewport.timeStart) * factor
  const center = (viewport.timeStart + viewport.timeEnd) / 2
  viewport.timeStart = center - span / 2
  viewport.timeEnd   = center + span / 2
  markInteracting(true)
  emitViewportChange()
  scheduleRender()
}

// ---- Public fit method (called from parent via ref) -----------------------
function jumpToNs(ns) {
  // Center the viewport around the given timestamp, preserving current zoom span
  const span = viewport.timeEnd - viewport.timeStart
  viewport.timeStart = ns - span / 2
  viewport.timeEnd   = ns + span / 2
  emitViewportChange()
  scheduleRender()
}

function zoomToTimeRange(lo, hi, paddingFrac = 0.05, opts = {}) {
  if (!props.trace || hi <= lo) return
  const tLo = props.trace.timeMin >= 0 ? Math.max(0, props.trace.timeMin) : props.trace.timeMin
  const tHi = props.trace.timeMax
  const span = hi - lo
  const pad = paddingFrac > 0 ? Math.max(1, span * paddingFrac) : 0
  let timeStart = Math.max(tLo, lo - pad)
  let timeEnd = Math.min(tHi, hi + pad)
  const minSpan = Math.max(1, (tHi - tLo) * 1e-6)
  if (timeEnd - timeStart < minSpan) {
    const c = (lo + hi) / 2
    timeStart = Math.max(tLo, c - minSpan / 2)
    timeEnd = Math.min(tHi, c + minSpan / 2)
  }
  if (opts.animate) {
    const fromStart = viewport.timeStart
    const fromEnd = viewport.timeEnd
    const t0 = performance.now()
    const dur = 280
    const tick = (now) => {
      const t = Math.min(1, (now - t0) / dur)
      const te = 1 - (1 - t) ** 2
      viewport.timeStart = fromStart + (timeStart - fromStart) * te
      viewport.timeEnd = fromEnd + (timeEnd - fromEnd) * te
      emitViewportChange({ programmatic: !!opts.programmatic })
      scheduleRender()
      if (t < 1) requestAnimationFrame(tick)
    }
    requestAnimationFrame(tick)
    return
  }
  viewport.timeStart = timeStart
  viewport.timeEnd = timeEnd
  emitViewportChange({ programmatic: !!opts.programmatic })
  scheduleRender()
}

function zoomToCursorRange() {
  const placed = props.cursors.filter(c => c != null).sort((a, b) => a - b)
  if (placed.length < 2) return false
  zoomToTimeRange(placed[0], placed[placed.length - 1], 0)
  return true
}

function zoom1to1(wasFit = false) {
  if (!props.trace) return
  const tspx = layout().timescalePerPxDefault
  const lo = props.trace.timeMin >= 0 ? Math.max(0, props.trace.timeMin) : props.trace.timeMin
  const hi = props.trace.timeMax
  const centerNs = wasFit ? lo : getViewportCenter()
  applyCenteredSpan(lo, hi, centerNs, Math.max(1, timeAxisPx()) * tspx)
}

function timeAxisPx() {
  return orientation.value === 'v'
    ? Math.max(1, viewport.canvasH)
    : Math.max(1, viewport.canvasW)
}

function applyCenteredSpan(lo, hi, centerNs, span) {
  let timeStart = centerNs - span / 2
  let timeEnd = centerNs + span / 2
  if (timeStart < lo) {
    timeEnd += lo - timeStart
    timeStart = lo
  }
  if (timeEnd > hi) {
    timeStart -= timeEnd - hi
    timeEnd = hi
  }
  timeStart = Math.max(lo, timeStart)
  timeEnd = Math.min(hi, Math.max(timeStart + 1, timeEnd))
  viewport.timeStart = timeStart
  viewport.timeEnd = timeEnd
  emitViewportChange()
  scheduleRender()
}

/** Percentage of the full trace that should be visible (desktop zoom-preset combo). */
function zoomToPercent(pct) {
  if (!props.trace) return
  if (pct == null || pct >= 100) {
    fitToTrace()
    return
  }
  const lo = props.trace.timeMin >= 0 ? Math.max(0, props.trace.timeMin) : props.trace.timeMin
  const hi = props.trace.timeMax
  const full = Math.max(1, hi - lo)
  const axis = timeAxisPx()
  const minTpp = layout().timescalePerPxDefault
  const fitTpp = full / axis
  let tpp = fitTpp * Number(pct) / 100
  tpp = Math.max(minTpp, Math.min(tpp, fitTpp))
  applyCenteredSpan(lo, hi, getViewportCenter(), axis * tpp)
}

function getZoomPresetSnapshot() {
  const options = buildZoomPresetOptions(0, 0)
  if (!props.trace) return { options, value: 'fit' }
  const lo = props.trace.timeMin >= 0 ? Math.max(0, props.trace.timeMin) : props.trace.timeMin
  const hi = props.trace.timeMax
  const full = Math.max(1, hi - lo)
  const axis = timeAxisPx()
  const minTpp = layout().timescalePerPxDefault
  const fitTpp = full / axis
  const opts = buildZoomPresetOptions(fitTpp, minTpp)
  const span = Math.max(0, viewport.timeEnd - viewport.timeStart)
  return { options: opts, value: matchZoomPresetValue(span / full, opts) }
}

function jumpToTraceStart() {
  if (!props.trace) return
  jumpToNs(props.trace.timeMin >= 0 ? Math.max(0, props.trace.timeMin) : props.trace.timeMin)
}

function jumpToTraceEnd() {
  if (!props.trace) return
  jumpToNs(props.trace.timeMax)
}

let _segStartsCache = null
let _segStartsTrace = null

function jumpSegmentBoundary(forward) {
  if (!props.trace) return
  if (_segStartsTrace !== props.trace) {
    _segStartsCache = collectSegmentStarts(props.trace)
    _segStartsTrace = props.trace
  }
  const allStarts = _segStartsCache
  if (!allStarts?.length) return
  const edgeLo = viewport.timeStart
  const edgeHi = viewport.timeEnd
  let target
  if (forward) {
    const idx = bisectRight(allStarts, edgeHi)
    target = allStarts[Math.min(idx, allStarts.length - 1)]
  } else {
    const idx = bisectLeft(allStarts, edgeLo) - 1
    target = allStarts[Math.max(idx, 0)]
  }
  jumpToNs(target)
}

function scrollTimeAxis(fraction) {
  const span = viewport.timeEnd - viewport.timeStart
  const delta = span * fraction
  if (orientation.value === 'v') {
    viewport.timeStart += delta
    viewport.timeEnd += delta
  } else {
    viewport.timeStart += delta
    viewport.timeEnd += delta
  }
  emitViewportChange()
  scheduleRender()
}

function scrollRowAxis(fraction) {
  const vert = orientation.value === 'v'
  if (vert) {
    const totalW = cachedColumnLayout.value?.totalWidth ?? 0
    const maxScroll = Math.max(0, totalW - viewport.canvasW)
    viewport.scrollX = Math.max(0, Math.min(maxScroll, (viewport.scrollX || 0) + maxScroll * fraction))
  } else {
    const totalH = cachedRowLayout.value?.totalHeight ?? 0
    const visH = Math.max(0, viewport.canvasH - RULER_H)
    const maxScroll = Math.max(0, totalH - visH)
    viewport.scrollY = Math.max(0, Math.min(maxScroll, (viewport.scrollY || 0) + maxScroll * fraction))
  }
  emitViewportChange()
  scheduleRender(true)
}

function placeCursorAtCenter(shiftSnap = false) {
  const ns = getHoverTime() ?? getLastActiveCursorTime() ?? getViewportCenter()
  _handler?.placeCursorAt(ns, shiftSnap)
}

function placeCursorAtTime(ns) {
  if (ns == null || !Number.isFinite(ns)) return
  _handler?.placeCursorAtTime(ns)
}

function removeNearestCursorAt(ns) {
  _handler?.removeNearestCursor(ns ?? getViewportCenter())
}

function clearAllCursorsViaHandler() {
  _handler?.clearAllCursors()
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
      stiExpanded,
      ...layoutFilterArgs(),
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
  const scrollY = viewport.scrollY
  const { rows } = buildRowLayout(
    props.trace,
    props.options.viewMode,
    expanded,
    0,
    props.options.showSti !== false,
    stiExpanded,
    ...layoutFilterArgs(),
  )
  const coreRows = rows.filter(r => r.type === 'core' || r.type === 'core-task')
  if (coreRows.length === 0) return null

  const canvasTop = (r) => RULER_H - scrollY + r.y
  const hit = coreRows.find(r => {
    const h = rowBandHeight(r)
    const top = canvasTop(r)
    return centerY >= top && centerY < top + h
  })
  if (hit) return hit.type === 'core' ? hit.key : hit.coreKey

  let best = coreRows[0]
  let bestDist = Math.abs(centerY - (canvasTop(best) + rowBandHeight(best) / 2))
  for (let i = 1; i < coreRows.length; i++) {
    const r = coreRows[i]
    const d = Math.abs(centerY - (canvasTop(r) + rowBandHeight(r) / 2))
    if (d < bestDist) {
      best = r
      bestDist = d
    }
  }
  return best.type === 'core' ? best.key : best.coreKey
}

function findRowForTask(rows, mergeKey) {
  let targetRow = rows.find(r => r.type === 'task' && r.key === mergeKey)
  if (targetRow) return targetRow
  if (props.options.viewMode !== 'core') return null
  targetRow = rows.find(r => r.type === 'core' && r.key === mergeKey)
  if (targetRow) return targetRow
  targetRow = rows.find(r => r.type === 'core-task' && taskMergeKey(r.taskKey) === mergeKey)
  if (targetRow) return targetRow
  // Collapsed core view: task has no sub-row — use the parent core summary row.
  for (const coreName of props.trace.coreNames || []) {
    const taskOrder = props.trace.coreTaskOrder.get(coreName) || []
    if (taskOrder.some(t => taskMergeKey(t) === mergeKey)) {
      return rows.find(r => r.type === 'core' && r.key === coreName) || null
    }
  }
  return null
}

function findColForTask(cols, mergeKey) {
  let targetCol = cols.find(c => c.type === 'task' && c.key === mergeKey)
  if (targetCol) return targetCol
  if (props.options.viewMode !== 'core') return null
  targetCol = cols.find(c => c.type === 'core' && c.key === mergeKey)
  if (targetCol) return targetCol
  targetCol = cols.find(c => c.type === 'core-task' && taskMergeKey(c.taskKey) === mergeKey)
  if (targetCol) return targetCol
  for (const coreName of props.trace.coreNames || []) {
    const taskOrder = props.trace.coreTaskOrder.get(coreName) || []
    if (taskOrder.some(t => taskMergeKey(t) === mergeKey)) {
      return cols.find(c => c.type === 'core' && c.key === coreName) || null
    }
  }
  return null
}

function scrollToTask(mergeKey) {
  if (!props.trace) return
  if (orientation.value === 'v') {
    const { cols } = buildColumnLayout(
      props.trace, props.options.viewMode, expanded, 0,
      props.options.showSti !== false, stiExpanded,
      ...layoutFilterArgs(),
    )
    const targetCol = findColForTask(cols, mergeKey)
    if (!targetCol) return
    const cw = targetCol.colWidth ?? COL_W
    viewport.scrollX = Math.max(0, targetCol.x + cw / 2 - viewport.canvasW / 2)
    clampScrollToContent()
    scheduleRender()
    return
  }
  // Build layout at yStart=0 to get raw row offsets independent of current scrollY
  const { rows } = buildRowLayout(
    props.trace, props.options.viewMode, expanded, 0,
    props.options.showSti !== false, stiExpanded,
    !!props.options.migratedOnlyFilter,
    props.options.taskFilterKeys || null,
    props.options.taskFilterText || '',
  )
  const targetRow = findRowForTask(rows, mergeKey)
  if (!targetRow) return
  // In rendering: canvas Y of row = (RULER_H - scrollY) + row.y
  // To center row mid in canvas body: RULER_H - scrollY + row.y + layout().rowH/2 = canvasH/2
  // => scrollY = RULER_H + row.y + layout().rowH/2 - canvasH/2
  viewport.scrollY = Math.max(0, RULER_H + targetRow.y + layout().rowH / 2 - viewport.canvasH / 2)
  clampScrollToContent()
  scheduleRender()
}

/** Scroll the viewport so an interval row/column is centered (statistics plot drill-down). */
function scrollToIntervalRow(intervalId) {
  if (!props.trace || intervalId == null) return
  const showSti = props.options.showSti !== false
  const migrated = !!props.options.migratedOnlyFilter
  const taskFilterKeys = props.options.taskFilterKeys || null
  const taskFilterText = props.options.taskFilterText || ''

  if (orientation.value === 'v') {
    const { cols } = buildColumnLayout(
      props.trace, props.options.viewMode, expanded, 0,
      showSti, stiExpanded, migrated, taskFilterKeys, taskFilterText,
    )
    const targetCol = cols.find(c => c.type === 'interval' && String(c.key) === String(intervalId))
    if (!targetCol) return
    const cw = targetCol.colWidth ?? COL_W
    viewport.scrollX = Math.max(0, targetCol.x + cw / 2 - viewport.canvasW / 2)
  } else {
    const { rows } = buildRowLayout(
      props.trace, props.options.viewMode, expanded, 0,
      showSti, stiExpanded, migrated, taskFilterKeys, taskFilterText,
    )
    const targetRow = rows.find(r => r.type === 'interval' && String(r.key) === String(intervalId))
    if (!targetRow) return
    viewport.scrollY = Math.max(0, RULER_H + targetRow.y + layout().rowH / 2 - viewport.canvasH / 2)
  }
  clampScrollToContent()
  scheduleRender()
}

/** Scroll the viewport so an STI tag/marker channel row/column is centered. */
function scrollToStiChannel(channel) {
  if (!props.trace || !channel) return
  const showSti = props.options.showSti !== false
  const migrated = !!props.options.migratedOnlyFilter
  const taskFilterKeys = props.options.taskFilterKeys || null
  const taskFilterText = props.options.taskFilterText || ''

  if (orientation.value === 'v') {
    const { cols } = buildColumnLayout(
      props.trace, props.options.viewMode, expanded, 0,
      showSti, stiExpanded, migrated, taskFilterKeys, taskFilterText,
    )
    const targetCol = cols.find(c => c.type === 'sti' && c.key === channel)
    if (!targetCol) return
    const cw = targetCol.colWidth ?? COL_W
    viewport.scrollX = Math.max(0, targetCol.x + cw / 2 - viewport.canvasW / 2)
  } else {
    const { rows } = buildRowLayout(
      props.trace, props.options.viewMode, expanded, 0,
      showSti, stiExpanded, migrated, taskFilterKeys, taskFilterText,
    )
    const targetRow = rows.find(r => r.type === 'sti' && r.key === channel)
    if (!targetRow) return
    viewport.scrollY = Math.max(0, RULER_H + targetRow.y + layout().rowH / 2 - viewport.canvasH / 2)
  }
  clampScrollToContent()
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
    const { rows } = buildRowLayout(
      props.trace, props.options.viewMode, expanded, 0,
      props.options.showSti !== false, stiExpanded,
      ...layoutFilterArgs(),
    )
    if (props.options.viewMode === 'core') {
      targetRow = rows.find(
        r => r.type === 'core-task' && r.coreKey === seg.core && taskMergeKey(r.taskKey) === mk,
      )
      if (!targetRow) {
        targetRow = rows.find(r => r.type === 'core-task' && taskMergeKey(r.taskKey) === mk)
      }
      if (!targetRow && seg.core) {
        targetRow = rows.find(r => r.type === 'core' && r.key === seg.core)
      }
    } else {
      targetRow = rows.find(r => r.type === 'task' && r.key === mk)
    }

    if (targetRow) {
      const actualRowY = RULER_H - scrollY + targetRow.y
      rowOutOfView = (actualRowY + layout().rowH <= RULER_H) || (actualRowY >= canvasH)
    }
  } else {
    const { cols } = buildColumnLayout(
      props.trace, props.options.viewMode, expanded, scrollX,
      props.options.showSti !== false, stiExpanded,
      ...layoutFilterArgs(),
    )
    if (props.options.viewMode === 'core') {
      targetCol = cols.find(
        c => c.type === 'core-task' && c.coreKey === seg.core && taskMergeKey(c.taskKey) === mk,
      )
      if (!targetCol) {
        targetCol = cols.find(c => c.type === 'core-task' && taskMergeKey(c.taskKey) === mk)
      }
      if (!targetCol && seg.core) {
        targetCol = cols.find(c => c.type === 'core' && c.key === seg.core)
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
    viewport.scrollY = Math.max(0, RULER_H + targetRow.y + layout().rowH / 2 - canvasH / 2)
  }
  if (!isHorizontal && colOutOfView && targetCol) {
    const rawX = targetCol.x + scrollX
    const cw = targetCol.colWidth ?? COL_W
    viewport.scrollX = Math.max(0, rawX + cw / 2 - canvasW / 2)
  }
  if (!timeVisible || (isHorizontal && rowOutOfView && targetRow) || (!isHorizontal && colOutOfView && targetCol)) {
    emitViewportChange()
    scheduleRender()
  }
}

function getHoverTime() { return hoverTime.value }
function getLastActiveCursorTime() { return _handler?.getLastActiveCursorTime() ?? null }
function getViewport() { return { ...viewport } }

defineExpose({
  fitToTrace, applyViewport, applyTraceViewport, ensureTraceViewport, beginLoadSettle, scheduleRender,
  zoomCenter, expandAll, collapseAll, expandCoresForMergeKeys, jumpToNs, zoomToTimeRange, zoomToCursorRange, zoom1to1,
  zoomToPercent, getZoomPresetSnapshot,
  jumpToTraceStart, jumpToTraceEnd, jumpSegmentBoundary, scrollTimeAxis, scrollRowAxis,
  placeCursorAtCenter, placeCursorAtTime, removeNearestCursorAt, clearAllCursorsViaHandler,
  getViewport, getViewportCenter, getCoreAtViewportCenter, scrollToTask, expandCore, scrollToIntervalRow, scrollToStiChannel, scrollToSegmentIfNeeded,
  captureScreenshotBlob, captureAsSvg, getHoverTime, getLastActiveCursorTime,
})

// ---- Expand / collapse core rows -----------------------------------------
function onExpandToggle(coreName) {
  if (expanded.has(coreName)) expanded.delete(coreName)
  else expanded.add(coreName)
  clampScrollToContent()
  _ovBgCanvas = null
  scheduleRender()
}

// ---- Expand / collapse tag-event STI waveform rows -----------------------
function onStiExpandToggle(channelName) {
  if (stiExpanded.has(channelName)) stiExpanded.delete(channelName)
  else stiExpanded.add(channelName)
  scheduleRender()
}

function expandCore(coreName) {
  if (!props.trace || !coreName) return
  expanded.add(coreName)
  clampScrollToContent()
  _ovBgCanvas = null
  scheduleRender()
}

function expandAll() {
  if (!props.trace) return
  for (const coreName of props.trace.coreNames) expanded.add(coreName)
  clampScrollToContent()
  _ovBgCanvas = null
  scheduleRender()
}

function collapseAll() {
  expanded.clear()
  clampScrollToContent()
  _ovBgCanvas = null
  scheduleRender()
}

/** Expand only cores that contain one of *mergeKeys* (heatmap drill-down). */
function expandCoresForMergeKeys(mergeKeys) {
  if (!props.trace || !mergeKeys?.length) return
  const mks = new Set(mergeKeys)
  expanded.clear()
  for (const coreName of props.trace.coreNames) {
    const tasks = props.trace.coreTaskOrder.get(coreName) || []
    if (tasks.some(t => mks.has(taskMergeKey(t)))) expanded.add(coreName)
  }
  clampScrollToContent()
  _ovBgCanvas = null
  scheduleRender()
}

let _labelResizeCleanup = null

const _labelMeasureCanvas = document.createElement('canvas')
const _labelMeasureCtx = _labelMeasureCanvas.getContext('2d')

function _clampLabelWidth(w) {
  return Math.max(60, Math.min(600, Math.round(w)))
}

function _measureLabelTextWidth(text) {
  if (!text) return 0
  _labelMeasureCtx.font = `${getTimelineLayout().labelFontSize}px monospace`
  return _labelMeasureCtx.measureText(text).width
}

function autoFitLabelWidth() {
  if (!props.trace) return
  let maxW = 60
  if (orientation.value === 'h') {
    const rows = cachedRowLayout.value?.rows
    if (!rows?.length) return
    const y0 = viewport.scrollY - RULER_H
    const y1 = y0 + labelBodyH.value
    for (const row of rows) {
      const h = rowBandHeight(row)
      if (row.y + h <= y0) continue
      if (row.y >= y1) break
      const w = _measureLabelTextWidth(row.label) + 24
      if (w > maxW) maxW = w
    }
  } else {
    const cols = cachedColumnLayout.value?.cols
    if (!cols?.length) return
    const x0 = viewport.scrollX
    const x1 = x0 + viewport.canvasW
    for (const col of cols) {
      const w = col.width ?? COL_W
      if (col.x + w <= x0) continue
      if (col.x >= x1) break
      const lw = _measureLabelTextWidth(col.label) + 24
      if (lw > maxW) maxW = lw
    }
  }
  const newW = _clampLabelWidth(maxW)
  setTimelineLayout({ labelW: newW })
  emit('labelWidthChange', newW, true)
}

function onLabelResizeStart(e) {
  const startX = e.clientX
  const startW = props.labelWidth
  const onMove = (ev) => {
    const newW = _clampLabelWidth(startW + (ev.clientX - startX))
    setTimelineLayout({ labelW: newW })
    emit('labelWidthChange', newW, false)
  }
  const onUp = () => {
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
    document.body.classList.remove('col-resizing')
    _labelResizeCleanup = null
    emit('labelWidthChange', getTimelineLayout().labelW, true)
  }
  _labelResizeCleanup = onUp
  document.body.classList.add('col-resizing')
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}

function onHeaderResizeStart(e) {
  const startY = e.clientY
  const startW = props.labelWidth
  const onMove = (ev) => {
    const newW = _clampLabelWidth(startW + (ev.clientY - startY))
    setTimelineLayout({ labelW: newW })
    emit('labelWidthChange', newW, false)
  }
  const onUp = () => {
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
    document.body.classList.remove('row-resizing')
    _labelResizeCleanup = null
    emit('labelWidthChange', getTimelineLayout().labelW, true)
  }
  _labelResizeCleanup = onUp
  document.body.classList.add('row-resizing')
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}

// ---- Watchers ------------------------------------------------------------
function rebuildPackedRows() {
  const layout = cachedRowLayout.value
  _packedRows = (layout?.rows && wasmAccelReady())
    ? packRowLayoutWasm(layout.rows, rowBandHeight)
    : null
}

function applyTraceViewport() {
  if (!props.trace) return
  const saved = props.persistedViewport
  if (isRestorableViewport(saved, props.trace)) {
    applyViewport(saved)
  } else {
    fitToTrace()
  }
}

/** True when the local viewport time window overlaps the loaded trace. */
function viewportOverlapsTrace() {
  if (!props.trace) return true
  const lo = props.trace.timeMin >= 0 ? Math.max(0, props.trace.timeMin) : props.trace.timeMin
  const hi = props.trace.timeMax
  if (hi <= lo) return false
  const span = viewport.timeEnd - viewport.timeStart
  if (span <= 0) return false
  // Sentinel from _emptyViewport() before fit — segments are outside [0,1].
  if (viewport.timeStart === 0 && viewport.timeEnd === 1 && span <= 1) return false
  const overlapLo = Math.max(viewport.timeStart, lo)
  const overlapHi = Math.min(viewport.timeEnd, hi)
  // Deep zoom can legitimately show far fewer than 1000 time units; any overlap counts.
  return overlapHi > overlapLo
}

function ensureTraceViewport() {
  if (!props.trace || _interacting || viewportOverlapsTrace()) return false
  fitToTrace()
  return true
}

function deferWasmSetup(trace) {
  const run = () => {
    if (props.trace !== trace) return
    registerTraceWasmAccel(trace)
    rebuildPackedRows()
    setupHandler()
    if (_loadSettling) return
    if (isLargeTrace() && isFitToWindowZoom()) scheduleRender()
    else scheduleFullQualityRender()
  }
  if (typeof requestIdleCallback === 'function') {
    requestIdleCallback(run, { timeout: 500 })
  } else {
    setTimeout(run, 0)
  }
}

watch(() => props.labelWidth, (w) => {
  setTimelineLayout({ labelW: w })
})

watch(() => props.trace, async (trace, prev) => {
  _ovBgCanvas = null
  _mainCtx = null
  if (prev) unregisterTraceWasmAccel(prev)
  if (!trace) {
    _packedRows = null
    expanded.clear()
    endLoadSettle()
    viewport.timeStart = 0
    viewport.timeEnd = 1
    viewport.scrollY = 0
    viewport.scrollX = 0
    return
  }

  beginLoadSettle()
  expanded.clear()
  if (trace.coreNames.length <= AUTO_EXPAND_CORES_MAX) {
    for (const coreName of trace.coreNames) expanded.add(coreName)
  }

  applyTraceViewport()

  await initWasmAccel()
  deferWasmSetup(trace)
})

watch(cachedRowLayout, () => {
  rebuildPackedRows()
  clampScrollToContent()
})

watch(cachedColumnLayout, () => {
  clampScrollToContent()
})

// Handler re-creation only needed when orientation or viewMode changes
watch([() => props.options.orientation, () => props.options.viewMode], () => {
  if (orientation.value === 'v') {
    viewport.scrollX = 0
    viewport.scrollY = 0
  } else {
    viewport.scrollX = 0
  }
  clampScrollToContent()
  _ovBgCanvas = null
  if (props.trace && isLargeTrace()) beginLoadSettle()
  setupHandler()
  scheduleRender(true)
})
// Other visual options that affect segment rendering → full repaint
watch([() => props.options.highlightKey, () => props.options.highlightSegment, () => props.options.highlightInterval, () => props.options.showGrid, () => props.options.showSti, () => props.options.stiLogScale, () => props.options.migratedOnlyFilter, () => props.options.taskFilterKeys, () => props.options.taskFilterText, () => props.options.lockedTaskKey], () => {
  _ovBgCanvas = null
  scheduleRender()
  if (overviewVisible.value) scheduleOverviewPaint()
})
watch(() => props.options.darkMode, () => {
  _ovBgCanvas = null
  scheduleRender(true)
  paintHoverOverlay()
  if (overviewVisible.value) scheduleOverviewPaint()
})
// Marks are on the overlay — no full repaint needed
watch(() => props.options.marks, () => {
  paintHoverOverlay()
}, { deep: true })

watch(() => props.options.selectedMarkId, () => {
  paintHoverOverlay()
})

let _overviewRaf = null

// Show navigator popup on scroll / pan when content overflows the viewport (rAF-coalesced).
watch(
  [() => viewport.timeStart, () => viewport.timeEnd, () => viewport.scrollY, () => viewport.scrollX],
  () => {
    if (!props.trace) return
    if (!_overviewRaf) {
      _overviewRaf = requestAnimationFrame(() => {
        _overviewRaf = null
        if (!props.trace) return
        if (showHScrollbar.value || showVScrollbar.value) {
          showOverviewPopup()
        } else {
          clearTimeout(_overviewHideTimer)
          overviewVisible.value = false
          _ovBgCanvas = null
        }
      })
    }
  },
)

watch(overviewVisible, (vis) => {
  if (vis) scheduleOverviewPaint()
})

watch(() => props.cursors, (c) => {
  _handler?.setCursors(c)
  paintHoverOverlay()  // cursors are on the overlay canvas — no full repaint needed
}, { deep: true })

watch(() => [props.findHits, props.findMarkerNs, props.findingHits], () => {
  paintHoverOverlay()
}, { deep: true })

// Sync STI tooltip position
watch(stiHover, (ev) => {
  if (!ev || !canvasEl.value || !props.trace) return
  if (orientation.value === 'v') {
    // In vertical mode, X is column position, Y is time
    const hh = vertCanvasHeaderH
    const pxPerNs = viewport.canvasH / (viewport.timeEnd - viewport.timeStart)
    stiHoverPos.y = hh + (ev.time - viewport.timeStart) * pxPerNs
    stiHoverPos.x = canvasEl.value.clientWidth / 2
  } else {
    const w = canvasEl.value.clientWidth
    const pxPerNs = w / (viewport.timeEnd - viewport.timeStart)
    stiHoverPos.x = (ev.time - viewport.timeStart) * pxPerNs
    const rows = cachedRowLayout.value?.rows
    const row = rows?.find(r => r.type === 'sti' && r.key === ev.target)
    stiHoverPos.y = row
      ? (RULER_H + row.y - viewport.scrollY + rowBandHeight(row) / 2)
      : (canvasEl.value.clientHeight / 2)
  }
})

watch(segmentHover, (seg) => {
  if (!seg || !canvasEl.value || !props.trace) return
  if (orientation.value === 'v') {
    const hh = vertCanvasHeaderH
    const pxPerNs = viewport.canvasH / (viewport.timeEnd - viewport.timeStart)
    segmentHoverPos.y = hh + (seg.start - viewport.timeStart) * pxPerNs
    const cols = cachedColumnLayout.value?.cols
    let col = null
    if (cols) {
      const scrollX = viewport.scrollX || 0
      const mk = taskMergeKey(seg.task)
      for (const c of cols) {
        if (c.type !== 'task' && c.type !== 'core-task') continue
        const match = c.type === 'task'
          ? mk === c.key
          : (c.coreKey === seg.core && c.taskKey === seg.task)
        if (match) { col = c; break }
      }
      segmentHoverPos.x = col ? (col.x - scrollX + COL_W / 2) : (canvasEl.value.clientWidth / 2)
    } else {
      segmentHoverPos.x = canvasEl.value.clientWidth / 2
    }
  } else {
    const pxPerNs = viewport.canvasW / (viewport.timeEnd - viewport.timeStart)
    segmentHoverPos.x = (seg.start - viewport.timeStart) * pxPerNs
    const rows = cachedRowLayout.value?.rows
    let row = null
    if (rows) {
      const mk = taskMergeKey(seg.task)
      const { i0, i1 } = visibleRowIndexRange(rows, viewport.scrollY, viewport.canvasH - RULER_H, 4)
      for (let i = i0; i < i1; i++) {
        const r = rows[i]
        if (r.type !== 'task' && r.type !== 'core-task') continue
        const match = r.type === 'task'
          ? r.key === mk
          : (r.coreKey === seg.core && r.taskKey === seg.task)
        if (match) { row = r; break }
      }
    }
    segmentHoverPos.y = row
      ? (RULER_H + row.y - viewport.scrollY + layout().rowH / 2)
      : (canvasEl.value.clientHeight / 2)
  }
})

// ---- Navigator popup & scrollbar interaction -----------------------------

function showOverviewPopup() {
  overviewVisible.value = true
  clearTimeout(_overviewHideTimer)
  // Only schedule auto-hide when not actively dragging
  if (!_sbDrag && !_ovDrag) {
    _overviewHideTimer = setTimeout(() => { overviewVisible.value = false }, 1800)
  }
  scheduleOverviewPaint()
}

function _overviewIndicatorRect() {
  const canvas = overviewCanvasEl.value
  if (!canvas || !props.trace || !traceBounds.value) return null
  const W = canvas.width
  const { lo } = traceBounds.value
  const span = traceBounds.value.hi - lo
  if (span <= 0) return null
  const pxPerNs = W / span
  // Full thumbnail height (tasks + STI); indicator scrolls over entire minimap.
  const stripH = canvas.height

  if (orientation.value === 'h') {
    const vx = Math.max(0, (viewport.timeStart - lo) * pxPerNs)
    const vw = Math.min(W - vx, (viewport.timeEnd - viewport.timeStart) * pxPerNs)
    const totH = totalRowHeight.value
    const visH = viewport.canvasH - RULER_H
    const { pos: vy, size: vh } = overviewStripRect(totH, visH, viewport.scrollY, stripH)
    return { x: vx, y: vy, w: Math.max(2, vw), h: vh, W, stripH, lo, span }
  }
  const vx = Math.max(0, (viewport.timeStart - lo) * pxPerNs)
  const vw = Math.min(W - vx, (viewport.timeEnd - viewport.timeStart) * pxPerNs)
  const totW = totalColumnWidth.value
  const visW = viewport.canvasW
  const { pos: vy, size: vh } = overviewStripRect(totW, visW, viewport.scrollX || 0, stripH)
  return { x: vx, y: vy, w: Math.max(2, vw), h: vh, W, stripH, lo, span }
}

function _overviewApplyIndicatorPos(vx, vy, ind) {
  const { W, stripH, lo, span } = ind
  const scrollableW = Math.max(W - ind.w, 1)
  const ratioX = vx / scrollableW
  const visSpan = viewport.timeEnd - viewport.timeStart
  const newStart = lo + ratioX * (span - visSpan)
  viewport.timeStart = newStart
  viewport.timeEnd = newStart + visSpan

  const scrollableH = Math.max(stripH - ind.h, 1)
  const ratioY = vy / scrollableH
  if (orientation.value === 'h') {
    const visH = viewport.canvasH - RULER_H
    viewport.scrollY = ratioY * Math.max(0, totalRowHeight.value - visH)
  } else {
    const totW = totalColumnWidth.value
    viewport.scrollX = ratioY * Math.max(0, totW - viewport.canvasW)
  }
  markInteracting(true)
  scheduleRender()
  emitViewportChange()
}

function _overviewJumpTo(cx, cy) {
  const canvas = overviewCanvasEl.value
  if (!canvas || !traceBounds.value) return
  const W = canvas.width
  const { lo, span } = traceBounds.value
  const ratioX = Math.max(0, Math.min(1, cx / W))
  const ratioY = Math.max(0, Math.min(1, cy / canvas.height))

  if (orientation.value === 'h') {
    const visSpan = viewport.timeEnd - viewport.timeStart
    const newStart = lo + ratioX * (span - visSpan)
    viewport.timeStart = newStart
    viewport.timeEnd = newStart + visSpan
    const visH = viewport.canvasH - RULER_H
    viewport.scrollY = ratioY * Math.max(0, totalRowHeight.value - visH)
    markInteracting(true)
    scheduleRender()
    emitViewportChange()
  } else {
    const visSpan = viewport.timeEnd - viewport.timeStart
    const newStart = lo + ratioX * (span - visSpan)
    viewport.timeStart = newStart
    viewport.timeEnd = newStart + visSpan
    const totW = totalColumnWidth.value
    viewport.scrollX = ratioY * Math.max(0, totW - viewport.canvasW)
    markInteracting(true)
    scheduleRender()
    emitViewportChange()
  }
}

/** Click outside the indicator jumps; drag the indicator to pan. */
function onOverviewMouseDown(e) {
  if (!props.trace || !traceBounds.value) return
  const canvas = overviewCanvasEl.value
  if (!canvas) return
  const rect = canvas.getBoundingClientRect()
  const cx = e.clientX - rect.left
  const cy = e.clientY - rect.top
  const ind = _overviewIndicatorRect()
  if (ind
      && cx >= ind.x && cx <= ind.x + ind.w
      && cy >= ind.y && cy <= ind.y + ind.h) {
    _ovDrag = { grabX: cx - ind.x, grabY: cy - ind.y, ind }
    overviewDragging.value = true
    document.addEventListener('mousemove', _ovMouseMove)
    document.addEventListener('mouseup', _ovMouseUp)
    clearTimeout(_overviewHideTimer)
    showOverviewPopup()
    return
  }
  _overviewJumpTo(cx, cy)
  showOverviewPopup()
}

function _ovMouseMove(e) {
  if (!_ovDrag) return
  const canvas = overviewCanvasEl.value
  if (!canvas) return
  const rect = canvas.getBoundingClientRect()
  const cx = e.clientX - rect.left
  const cy = e.clientY - rect.top
  const { ind, grabX, grabY } = _ovDrag
  const vx = Math.max(0, Math.min(ind.W - ind.w, cx - grabX))
  const vy = Math.max(0, Math.min(ind.stripH - ind.h, cy - grabY))
  _overviewApplyIndicatorPos(vx, vy, ind)
  scheduleOverviewPaint()
}

function _ovMouseUp() {
  _ovDrag = null
  overviewDragging.value = false
  document.removeEventListener('mousemove', _ovMouseMove)
  document.removeEventListener('mouseup', _ovMouseUp)
  _overviewHideTimer = setTimeout(() => { overviewVisible.value = false }, 1500)
}

/** Map main-view scroll position to the overview thumbnail strip area. */
function overviewStripRect(totalMain, visibleMain, scrollPos, stripAreaH) {
  const areaH = Math.max(1, stripAreaH)
  if (totalMain <= visibleMain || totalMain <= 0) {
    return { pos: 0, size: areaH }
  }
  const size = Math.max(2, (visibleMain / totalMain) * areaH)
  const maxPos = Math.max(0, areaH - size)
  const pos = (scrollPos / (totalMain - visibleMain)) * maxPos
  return { pos, size }
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

  // ---- Background cache --------------------------------------------------
  // The static part (rows + STI bars + border) never changes on scroll/pan.
  // Rebuild it only when the trace, view mode or STI state changes.
  const expandedKey = [
    [...stiExpanded].sort().join(','),
    [...expanded].sort().join(','),
    props.options.migratedOnlyFilter ? '1' : '0',
    (props.options.taskFilterKeys || []).join(','),
    props.options.taskFilterText || '',
    props.options.darkMode ? '1' : '0',
    orientation.value,
  ].join('|')
  const needsBgRebuild = _ovBgCanvas === null
    || _ovBgTrace       !== tr
    || _ovBgMode        !== props.options.viewMode
    || _ovBgShowSti     !== props.options.showSti
    || _ovBgExpandedKey !== expandedKey
    || _ovBgOrientation !== orientation.value

  const bgTotSize = orientation.value === 'h'
    ? totalRowHeight.value
    : totalColumnWidth.value

  if (needsBgRebuild) {
    const bg = document.createElement('canvas')
    bg.width  = W
    bg.height = H
    _paintOverviewBg(bg, tr, lo, hi, span, W, H, bgTotSize)
    _ovBgCanvas       = bg
    _ovBgTrace        = tr
    _ovBgMode         = props.options.viewMode
    _ovBgShowSti      = props.options.showSti
    _ovBgExpandedKey  = expandedKey
    _ovBgOrientation  = orientation.value
  }

  ctx.setTransform(1, 0, 0, 1, 0, 0)
  ctx.clearRect(0, 0, W, H)
  if (_ovBgCanvas) {
    ctx.drawImage(_ovBgCanvas, 0, 0, W, H)
  } else {
    _paintOverviewBg(canvas, tr, lo, hi, span, W, H, bgTotSize)
  }

  // ---- Overlay: viewport indicator (only this changes on scroll/zoom) ----
  const dark     = props.options.darkMode
  const pxPerNs  = W / span
  ctx.strokeStyle = dark ? 'rgba(255,160,60,0.9)'  : 'rgba(200,70,10,0.85)'
  ctx.fillStyle   = dark ? 'rgba(255,160,60,0.18)' : 'rgba(200,70,10,0.12)'
  ctx.lineWidth   = 1.5

  const stripH = H

  if (orientation.value === 'h') {
    const vx = Math.max(0, (viewport.timeStart - lo) * pxPerNs)
    const vw = Math.min(W - vx, (viewport.timeEnd - viewport.timeStart) * pxPerNs)
    const totH = totalRowHeight.value
    const visH = viewport.canvasH - RULER_H
    const { pos: vy, size: vh } = overviewStripRect(totH, visH, viewport.scrollY, stripH)
    ctx.beginPath()
    ctx.rect(vx, vy, Math.max(2, vw), vh)
    ctx.fill()
    ctx.stroke()
  } else {
    const vx = Math.max(0, (viewport.timeStart - lo) * pxPerNs)
    const vw = Math.min(W - vx, (viewport.timeEnd - viewport.timeStart) * pxPerNs)
    const totW = totalColumnWidth.value
    const visW = viewport.canvasW
    const { pos: vy, size: vh } = overviewStripRect(totW, visW, viewport.scrollX || 0, stripH)
    ctx.beginPath()
    ctx.rect(vx, vy, Math.max(2, vw), vh)
    ctx.fill()
    ctx.stroke()
  }
}

function _paintOverviewBg(bgCanvas, tr, lo, hi, span, W, H, totMainSize) {
  const ctx     = bgCanvas.getContext('2d')
  const dark    = props.options.darkMode
  const pxPerNs = W / span
  const isCore  = props.options.viewMode === 'core'
  const isVert  = orientation.value === 'v'
  const migratedOnly = !!props.options.migratedOnlyFilter
  const taskFilterKeys = props.options.taskFilterKeys || null
  const taskFilterText = props.options.taskFilterText || ''
  const skipCoreHdr = coreViewTaskFilterActive(migratedOnly, taskFilterKeys, taskFilterText)

  ctx.fillStyle = dark ? '#1a1a1a' : '#e8e8e8'
  ctx.fillRect(0, 0, W, H)

  const stripDefs = []
  const stiDefs = []

  if (!isVert) {
    if (!isCore) {
      for (const mk of tr.tasks) {
        if (!taskPassesRowFilter(tr, mk, migratedOnly, taskFilterKeys, taskFilterText)) continue
        const repr = tr.taskRepr.get(mk)
        const segs = tr.segLodUltraByMergeKey.get(mk) || tr.segByMergeKey.get(mk) || []
        if (!segs.length) continue
        stripDefs.push({ segs, color: taskColor(mk, repr), blend: true })
      }
    } else {
      const cores = filteredCoreViewTasks(tr, migratedOnly, taskFilterKeys, taskFilterText)
      for (const { coreName, tasks } of cores) {
        if (!skipCoreHdr) {
          const hdrSegs = tr.coreSegLodUltra.get(coreName) || tr.coreSegs.get(coreName) || []
          if (hdrSegs.length) stripDefs.push({ segs: hdrSegs, perSegColor: true })
        }
        if (expanded.has(coreName)) {
          for (const taskRaw of tasks) {
            const mk = taskMergeKey(taskRaw)
            const tSegs = tr.coreTaskSegLodUltra.get(coreName)?.get(taskRaw)
                       || tr.coreTaskSegs.get(coreName)?.get(taskRaw) || []
            if (!tSegs.length) continue
            stripDefs.push({ segs: tSegs, color: taskColor(mk, taskRaw) })
          }
        }
      }
    }
    if (props.options.showSti !== false && tr.stiChannels?.length) {
      for (const ch of tr.stiChannels) {
        const evs = tr.stiEventsByTarget?.get(ch) || []
        if (!evs.length) continue
        stiDefs.push({ evs, color: stiChannelColor(ch), isExpanded: stiExpanded.has(ch), ch })
      }
    }
  } else {
    const layout = buildColumnLayout(
      tr, props.options.viewMode, expanded, 0,
      props.options.showSti !== false, stiExpanded, migratedOnly,
      taskFilterKeys, taskFilterText,
    )
    for (const col of layout.cols) {
      if (col.type === 'sti') {
        const evs = tr.stiEventsByTarget?.get(col.key) || []
        if (!evs.length) continue
        stripDefs.push({ sti: true, evs, isExpanded: stiExpanded.has(col.key), ch: col.key })
        continue
      }
      let segs = []
      let color = col.color
      let blend = false
      let perSegColor = false
      if (col.type === 'task') {
        segs = tr.segLodUltraByMergeKey.get(col.key) || tr.segByMergeKey.get(col.key) || []
        blend = true
      } else if (col.type === 'core') {
        if (skipCoreHdr) continue
        segs = tr.coreSegLodUltra.get(col.key) || tr.coreSegs.get(col.key) || []
        perSegColor = true
      } else if (col.type === 'core-task') {
        segs = tr.coreTaskSegLodUltra.get(col.coreKey)?.get(col.taskKey)
            || tr.coreTaskSegs.get(col.coreKey)?.get(col.taskKey) || []
      }
      if (!segs.length) continue
      stripDefs.push({ segs, color, blend, perSegColor })
    }
  }

  let stiMainSize = 0
  if (props.options.showSti !== false && tr.stiChannels?.length) {
    if (isVert) {
      for (const ch of tr.stiChannels) {
        const isExp = isStiTagChannel(ch) && stiExpanded.has(ch)
        stiMainSize += (isExp ? layout().stiWaveformH : COL_W)
      }
    } else {
      for (const ch of tr.stiChannels) {
        const isExp = isStiTagChannel(ch) && stiExpanded.has(ch)
        stiMainSize += (isExp ? layout().stiWaveformH : layout().stiRowH) + layout().rowGap
      }
    }
  }
  const totSafe = Math.max(1, totMainSize)
  const stiAreaH = isVert
    ? 0  // vertical: STI strips share the same Y stack as task columns
    : (stiMainSize / totSafe) * H
  const mainAreaH = isVert ? H : (H - stiAreaH)
  const nsPerPxThumb = span / W

  if (stripDefs.length) {
    const stripH = mainAreaH / stripDefs.length
    const segColorCache = new Map()
    for (let i = 0; i < stripDefs.length; i++) {
      const rd = stripDefs[i]
      const y  = i * stripH
      const rh = Math.max(1, stripH - 0.3)
      if (rd.sti) {
        const reducedEvs = lodReduce(
          rd.evs.map(ev => ({ start: ev.time, end: ev.time + 1, _ev: ev })),
          nsPerPxThumb,
          lo,
        )
        ctx.save()
        for (const seg of reducedEvs) {
          const ev = seg._ev
          ctx.fillStyle = stiNoteColor(ev.note || ev.event || '')
          ctx.beginPath()
          ctx.arc((ev.time - lo) * pxPerNs, y + rh / 2, Math.max(0.5, rh * 0.35), 0, Math.PI * 2)
          ctx.fill()
        }
        ctx.restore()
        continue
      }
      const reduced = lodReduce(rd.segs, nsPerPxThumb, lo)
      for (const seg of reduced) {
        const x  = (seg.start - lo) * pxPerNs
        const sw = Math.max(0.5, (seg.end - seg.start) * pxPerNs)
        if (x + sw < 0 || x > W) continue
        if (rd.perSegColor) {
          if (seg.task?.startsWith('Core_')) continue
          let c = segColorCache.get(seg.task)
          if (c === undefined) {
            c = taskColor(taskMergeKey(seg.task), seg.task)
            segColorCache.set(seg.task, c)
          }
          ctx.fillStyle = c
          ctx.fillRect(x, y, sw, rh)
        } else {
          ctx.fillStyle = rd.color
          ctx.fillRect(x, y, sw, rh)
          if (rd.blend) {
            const tint = coreTint(seg.core)
            if (tint) {
              ctx.fillStyle = tint
              ctx.fillRect(x, y, sw, rh)
            }
          }
        }
      }
    }
  }

  if (stiDefs.length && !isVert) {
    const stiRowH = stiAreaH / stiDefs.length
    for (let i = 0; i < stiDefs.length; i++) {
      const { evs, isExpanded, ch } = stiDefs[i]
      const y  = mainAreaH + i * stiRowH
      const rh = Math.max(2, stiRowH - 0.5)
      if (isExpanded) {
        // Use precomputed value range from parser (O(1)) instead of scanning
        const range = tr.stiValRange?.get(ch)
        const vMin = range?.min ?? Infinity
        const vMax = range?.max ?? -Infinity
        // Use the same waveform colours as drawStiWaveformRow in TimelineRenderer.js.
        const wfLineColor = dark ? '#5BC8FF' : '#0070CC'
        const wfDotColor  = dark ? '#80DFFF' : '#0050AA'
        if (isFinite(vMin) && vMin !== vMax) {
          // Draw as a line chart to match the main timeline view
          const vRng = vMax - vMin
          ctx.save()
          ctx.strokeStyle = wfLineColor
          ctx.lineWidth   = 1.0
          ctx.lineJoin    = 'round'
          ctx.beginPath()
          let firstPt = true
          for (let j = 0; j < evs.length; j++) {
            const ev = evs[j]
            const v  = parseFloat(ev.note !== '' ? ev.note : ev.event)
            if (isNaN(v)) continue
            const cx = (ev.time - lo) * pxPerNs
            const cy = y + rh - (v - vMin) / vRng * rh
            if (firstPt) { ctx.moveTo(cx, cy); firstPt = false }
            else ctx.lineTo(cx, cy)
          }
          if (!firstPt) ctx.stroke()
          ctx.restore()
        } else {
          ctx.save()
          ctx.fillStyle = wfDotColor
          for (const ev of evs) {
            ctx.beginPath()
            ctx.arc((ev.time - lo) * pxPerNs, y + rh / 2, 2, 0, Math.PI * 2)
            ctx.fill()
          }
          ctx.restore()
        }
      } else {
        // Collapsed: per-event note colour matching drawStiRow in TimelineRenderer.js.
        ctx.save()
        for (const ev of evs) {
          ctx.fillStyle = stiNoteColor(ev.note || ev.event || '')
          ctx.beginPath()
          ctx.arc((ev.time - lo) * pxPerNs, y + rh / 2, 2, 0, Math.PI * 2)
          ctx.fill()
        }
        ctx.restore()
      }
    }
  }

  // Static border
  ctx.strokeStyle = dark ? 'rgba(120,120,120,0.6)' : 'rgba(80,80,80,0.5)'
  ctx.lineWidth   = 1
  ctx.strokeRect(0.5, 0.5, W - 1, H - 1)
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
      markInteracting(true)
      scheduleRender()
    } else {
      const maxScroll = _sbDrag.maxScrollX ?? Math.max(0, totalColumnWidth.value - viewport.canvasW)
      viewport.scrollX = Math.max(0, ratio * maxScroll)
      markInteracting(false)
    }
    scheduleRender(orientation.value === 'v')
    emitViewportChange()
  } else {
    const dy   = e.clientY - _sbDrag.startY
    const newT = Math.max(0, Math.min(_sbDrag.usableH, _sbDrag.startT + dy))
    const ratio = _sbDrag.usableH > 0 ? newT / _sbDrag.usableH : 0
    if (orientation.value === 'h') {
      viewport.scrollY = ratio * _sbDrag.maxScrollY
      markInteracting(false)
      scheduleRender(true)
    } else {
      const newStart = _sbDrag.lo + ratio * (_sbDrag.span - _sbDrag.visSpan)
      viewport.timeStart = newStart
      viewport.timeEnd   = newStart + _sbDrag.visSpan
      markInteracting(true)
      scheduleRender()
    }
    emitViewportChange()
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
  const vSbW   = showVScrollbar.value ? SCROLLBAR_SIZE : 0
  const trackW = viewport.canvasW - vSbW
  if (orientation.value === 'v') {
    const totalWidth = totalColumnWidth.value
    const thumbW  = Math.max(20, (viewport.canvasW / Math.max(1, totalWidth)) * trackW)
    const usableW = trackW - thumbW
    const maxScrollX = Math.max(0, totalWidth - viewport.canvasW)
    const startL  = usableW > 0
      ? Math.min(usableW, ((viewport.scrollX || 0) / Math.max(1, maxScrollX)) * usableW)
      : 0
    _sbDrag = { type: 'h', startX: e.clientX, startL, usableW, maxScrollX, totalWidth }
    document.addEventListener('mousemove', _sbMouseMove)
    document.addEventListener('mouseup', _sbMouseUp)
    showOverviewPopup()
    return
  }
  const { lo, span } = traceBounds.value
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
    const bodyH   = trackH
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
      props.trace, props.options.viewMode, expanded, 0, props.options.showSti !== false, stiExpanded,
    )
    viewport.scrollX = Math.max(0, ratio * Math.max(0, totalWidth - viewport.canvasW))
  }
  scheduleRender()
  emitViewportChange()
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
    const bodyH  = trackH
    const ratio  = Math.max(0, Math.min(1, clickY / bodyH))
    const visSpan  = viewport.timeEnd - viewport.timeStart
    const newStart = lo + ratio * (span - visSpan)
    viewport.timeStart = newStart
    viewport.timeEnd   = newStart + visSpan
  }
  scheduleRender()
  emitViewportChange()
  showOverviewPopup()
}

// ---- Lifecycle -----------------------------------------------------------
onMounted(async () => {
  await initWasmAccel()
  if (pixiHostEl.value) {
    await pixiTimelineHost.init(pixiHostEl.value)
  }
  setupResize()
  setupHandler()
  document.addEventListener('click', onGlobalClick)
  nextTick(() => {
    if (props.trace) fitToTrace()
    else scheduleRender()
  })
})

onBeforeUnmount(() => {
  _labelResizeCleanup?.()
  document.body.classList.remove('col-resizing', 'row-resizing')
  pixiTimelineHost.destroy()
  if (_resizeObs) _resizeObs.disconnect()
  if (_handler) _handler.destroy()
  if (_rafId) cancelAnimationFrame(_rafId)
  if (_ovPaintRaf) cancelAnimationFrame(_ovPaintRaf)
  if (_overviewRaf) cancelAnimationFrame(_overviewRaf)
  clearTimeout(_interactEndTimer)
  clearTimeout(_loadSettleTimer)
  document.removeEventListener('click', onGlobalClick)
  clearTimeout(_overviewHideTimer)
  document.removeEventListener('mousemove', _sbMouseMove)
  document.removeEventListener('mouseup', _sbMouseUp)
  document.removeEventListener('mousemove', _ovMouseMove)
  document.removeEventListener('mouseup', _ovMouseUp)
})
</script>

<style scoped>
.timeline-panel {
  display: flex;
  flex: 1;
  overflow: hidden;
  position: relative;
  overscroll-behavior: none;
}

.timeline-panel.vert-orient {
  flex-direction: column;
}

.timeline-panel.vert-orient > .column-header-row {
  flex-shrink: 0;
  width: 100%;
}

.timeline-panel.vert-orient > .canvas-wrap {
  flex: 1;
  min-height: 0;
  width: 100%;
}

.label-resizer {
  flex-shrink: 0;
  width: 10px;
  margin: 0 -4px;
  cursor: col-resize;
  position: relative;
  z-index: 5;
  touch-action: none;
}
.label-resizer::after {
  content: '';
  position: absolute;
  top: 0;
  bottom: 0;
  left: 50%;
  width: 2px;
  transform: translateX(-50%);
  background: var(--border);
  opacity: 0.6;
  transition: opacity 0.1s, background 0.1s;
}
.label-resizer:hover::after {
  opacity: 1;
  background: var(--accent, #4a9eff);
}

.header-resizer {
  flex-shrink: 0;
  width: 100%;
  height: 10px;
  margin: -4px 0;
  cursor: row-resize;
  position: relative;
  z-index: 5;
  touch-action: none;
}
.header-resizer::after {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  top: 50%;
  height: 2px;
  transform: translateY(-50%);
  background: var(--border);
  opacity: 0.6;
  transition: opacity 0.1s, background 0.1s;
}
.header-resizer:hover::after {
  opacity: 1;
  background: var(--accent, #4a9eff);
}

.canvas-wrap {
  flex: 1;
  overflow: hidden;
  position: relative;
  cursor: crosshair;
}

.pixi-host {
  position: absolute;
  inset: 0;
  z-index: 0;
  overflow: hidden;
}

canvas {
  display: block;
  width: 100%;
  height: 100%;
  cursor: crosshair;
}

.chrome-canvas {
  position: absolute;
  inset: 0;
  z-index: 1;
  pointer-events: none;
}

.overlay-canvas {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  z-index: 2;
  pointer-events: none;
}

.context-menu {
  position: fixed;
  z-index: 10100;
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
  pointer-events: auto;
  cursor: pointer;
}

.overview-canvas.dragging {
  cursor: grabbing;
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
.ctx-sep {
  height: 1px;
  margin: 4px 0;
  background: var(--border);
  flex-shrink: 0;
}
.ctx-item:hover {
  background: var(--tb-btn-hover);
}

.ctx-item.disabled {
  opacity: 0.45;
  cursor: not-allowed;
  color: var(--fg-dim);
}

.ctx-item.disabled:hover {
  background: transparent;
}
</style>
