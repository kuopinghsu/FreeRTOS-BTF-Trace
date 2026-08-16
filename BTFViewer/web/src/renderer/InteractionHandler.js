/**
 * InteractionHandler.js – Attaches mouse/wheel/touch events to the timeline canvas.
 *
 * Emits high-level events via callbacks rather than mutating state directly,
 * keeping the handler framework-agnostic (works with Vue, plain JS, etc.).
 *
 * Events emitted (all via options callbacks):
 *   onViewportChange({ timeStart, timeEnd, scrollY })
 *   onCursorsChange([...timestamps])        – null entries = cursor not placed
 *   onStiHover(stiEvent | null)             – nearest STI marker or null
 *   onRowHover(rowDescriptor | null)        – row under cursor (for highlight)
 *   onFitToWindow()                         – user double-clicked ruler
 *   onContextMenu({ ns, x, y })            – right-click on timeline body
 *
 * Orientation modes:
 *   'h' (horizontal, default): time on X axis, rows on Y axis
 *   'v' (vertical):            time on Y axis, columns on X axis
 */

import { hitTestSti, hitTestRow, hitTestStiVertical, hitTestColumn,
         hitTestSegment, hitTestSegmentVertical,
         findNearestCursorIndex, findNearestMark,
         RULER_H, RULER_W, HEADER_H, COL_W } from './TimelineRenderer.js'
import { wheelGesturePlan, applyWheelPlanToViewport } from '../utils/viewportWheel.js'
import { taskMergeKey } from '../utils/colors.js'
import { snapToBoundary } from '../utils/snapBoundary.js'

function maxCursorsFrom(opts) {
  const n = opts.getMaxCursors?.() ?? 8
  return Math.max(4, Math.min(8, n))
}

export class InteractionHandler {
  /**
   * @param {HTMLCanvasElement} canvas
   * @param {object} options
   * @param {Function} options.getTrace        () => BtfTrace | null
   * @param {Function} options.getViewport     () => viewport object
   * @param {Function} options.getOptions      () => render options (viewMode, expanded, orientation, …)
   * @param {Function} options.onViewportChange
   * @param {Function} options.onCursorsChange
   * @param {Function} options.onStiHover
   * @param {Function} options.onRowHover
   * @param {Function} options.onFitToWindow
   * @param {Function} options.onContextMenu   ({ ns, x, y }) – optional right-click callback
   * @param {Function} options.onClearSelection
   * @param {HTMLElement} [options.wheelTarget]  wheel listener target (defaults to canvas)
   */
  constructor(canvas, options = {}) {
    this._canvas  = canvas
    this._wheelEl = options.wheelTarget ?? canvas
    this._opts    = options
    const mc = maxCursorsFrom(options)
    this._cursors = Array.from({ length: mc }, () => null)

    // Drag state
    this._dragging        = false
    this._dragStartX      = 0
    this._dragStartY      = 0
    this._dragStartTime   = 0   // timeStart at drag begin
    this._dragStartScrollX = 0
    this._draggingCursorIdx = -1
    this._draggingMarkId = null
    this._lastActiveCursorIdx = -1  // index of most recently placed/moved cursor
    this._dragCursorPx = 8
    this._dragMarkPx = 6

    // Middle-button drag: select time range → zoom on release
    this._midRangePressPos = null  // { x, y } canvas coords at press
    this._midRangePressT   = null  // timestamp at press
    this._midRangeDragging = false

    // Ctrl+drag: transient measure-ruler tool
    this._measureDragging = false
    this._measurePressT   = null   // timestamp at press
    this._measureAnchorPx = null   // fixed canvas Y (horiz) / X (vert) for the ruler line

    // Min zoom: entire trace visible
    this._minTimeSpan = 1

    // Zoom history for double-click toggle.
    // Each entry: { timeStart, timeEnd, scrollY, scrollX, segKey }
    this._zoomHistory = []

    this._boundWheel       = this._onWheel.bind(this)
    this._boundMouseDown   = this._onMouseDown.bind(this)
    this._boundMouseMove   = this._onMouseMove.bind(this)
    this._boundMouseUp     = this._onMouseUp.bind(this)
    this._boundMouseLeave  = this._onMouseLeave.bind(this)
    this._boundDblClick    = this._onDblClick.bind(this)
    this._boundContextMenu = this._onContextMenu.bind(this)
    this._boundKeyUp       = this._onKeyUp.bind(this)

    // Coalesce wheel-driven viewport updates to one emit per animation frame.
    this._vpQueue    = null
    this._vpFlushRaf = null

    // Coalesce hover hit-tests to one pass per animation frame.
    this._hoverRaf = null
    this._hoverCx  = 0
    this._hoverCy  = 0

    this._wheelEl.addEventListener('wheel',       this._boundWheel,     { capture: true, passive: false })
    canvas.addEventListener('mousedown',   this._boundMouseDown)
    canvas.addEventListener('mousemove',   this._boundMouseMove)
    canvas.addEventListener('mouseup',     this._boundMouseUp)
    canvas.addEventListener('mouseleave',  this._boundMouseLeave)
    canvas.addEventListener('dblclick',    this._boundDblClick)
    canvas.addEventListener('contextmenu', this._boundContextMenu, { capture: true })
    // Ctrl release must cancel the measure-ruler even if it happens off-canvas.
    if (typeof document !== 'undefined') {
      document.addEventListener('keyup', this._boundKeyUp)
    }
  }

  cancelPendingViewport() {
    /** Drop coalesced wheel/pinch viewport updates so Fit cannot be undone. */
    if (this._vpFlushRaf != null) {
      if (typeof cancelAnimationFrame === 'function') {
        cancelAnimationFrame(this._vpFlushRaf)
      }
      this._vpFlushRaf = null
    }
    this._vpQueue = null
  }

  destroy() {
    const c = this._canvas
    this.cancelPendingViewport()
    if (this._hoverRaf) {
      cancelAnimationFrame(this._hoverRaf)
      this._hoverRaf = null
    }
    this._wheelEl.removeEventListener('wheel',       this._boundWheel, { capture: true })
    c.removeEventListener('mousedown',   this._boundMouseDown)
    c.removeEventListener('mousemove',   this._boundMouseMove)
    c.removeEventListener('mouseup',     this._boundMouseUp)
    c.removeEventListener('mouseleave',  this._boundMouseLeave)
    c.removeEventListener('dblclick',    this._boundDblClick)
    c.removeEventListener('contextmenu', this._boundContextMenu, { capture: true })
    if (typeof document !== 'undefined') {
      document.removeEventListener('keyup', this._boundKeyUp)
    }
  }

  // ---- Public API --------------------------------------------------------

  setCursors(cursors) {
    const mc = maxCursorsFrom(this._opts)
    this._cursors = cursors.slice(0, mc)
    while (this._cursors.length < mc) this._cursors.push(null)
  }

  /** Return the timestamp of the most recently placed or dragged cursor, or null. */
  getLastActiveCursorTime() {
    if (this._lastActiveCursorIdx < 0) return null
    return this._cursors[this._lastActiveCursorIdx] ?? null
  }

  setMinTimeSpan(span) {
    this._minTimeSpan = Math.max(1, span)
  }

  placeCursorAt(ns, shiftSnap = false) {
    this._placeCursor(ns, shiftSnap)
  }

  /** Place a cursor at *ns* (stats / plot navigation; does not toggle-remove). */
  placeCursorAtTime(ns) {
    this._opts.onBeforeCursorChange?.()
    this._assignCursorSlot(ns)
  }

  zoomToSegment(seg) {
    this._zoomToSegment(seg)
  }

  removeNearestCursor(ns) {
    this._opts.onBeforeCursorChange?.()
    const vp = this._opts.getViewport()
    if (!vp) return
    const snapNs = 5 * this._nsPerPx()
    const cursors = [...this._cursors]
    let bestIdx = -1
    let bestDist = snapNs
    for (let i = 0; i < cursors.length; i++) {
      if (cursors[i] == null) continue
      const d = Math.abs(cursors[i] - ns)
      if (d < bestDist) {
        bestDist = d
        bestIdx = i
      }
    }
    if (bestIdx >= 0) {
      cursors[bestIdx] = null
      this._cursors = cursors
      this._opts.onCursorsChange?.(cursors)
    }
  }

  clearAllCursors() {
    this._opts.onBeforeCursorChange?.()
    const mc = maxCursorsFrom(this._opts)
    this._cursors = Array.from({ length: mc }, () => null)
    this._lastActiveCursorIdx = -1
    this._opts.onCursorsChange?.(this._cursors)
  }

  // ---- Helpers -----------------------------------------------------------

  _isVertical() {
    return (this._opts.getOptions?.()?.orientation ?? 'h') === 'v'
  }

  /** Top header band height inside the canvas (0 when DOM ColumnHeaderRow is shown). */
  _vertHeaderH() {
    if (!this._isVertical()) return 0
    return this._opts.getOptions?.()?.vertHeaderH ?? HEADER_H
  }

  _zoomToRange(t0, t1) {
    const vp = this._opts.getViewport()
    if (!vp) return
    const lo = Math.min(t0, t1)
    const hi = Math.max(t0, t1)
    if (hi - lo < this._minTimeSpan) return
    const { s, e } = this._clampPan(lo, hi)
    this._opts.onViewportChange?.({ ...vp, timeStart: s, timeEnd: e })
  }

  /** Map canvas coordinates to time (includes ruler/header bands). */
  _canvasToTimeForRange(cx, cy) {
    const vp = this._opts.getViewport()
    if (!vp) return null
    const { timeStart, timeEnd } = vp
    if (this._isVertical()) {
      const bodyH = vp.canvasH - this._vertHeaderH()
      const pxPerNs = bodyH / (timeEnd - timeStart)
      if (pxPerNs <= 0) return null
      const y = Math.max(0, cy - this._vertHeaderH())
      return timeStart + y / pxPerNs
    }
    const nsPerPx = (timeEnd - timeStart) / vp.canvasW
    if (nsPerPx <= 0) return null
    return timeStart + cx * nsPerPx
  }

  /** Convert canvas coordinates to a timestamp (timeline body only). */
  _canvasToTime(cx, cy) {
    const vp = this._opts.getViewport()
    if (!vp) return null
    if (this._isVertical()) {
      // In vertical mode, Y maps to time
      const { timeStart, timeEnd, canvasH } = vp
      const pxPerNs = (canvasH - this._vertHeaderH()) / (timeEnd - timeStart)
      if (pxPerNs <= 0 || cy < this._vertHeaderH()) return null
      return timeStart + (cy - this._vertHeaderH()) / pxPerNs
    } else {
      // In horizontal mode, X maps to time
      const { timeStart, timeEnd, canvasW } = vp
      const nsPerPx = (timeEnd - timeStart) / canvasW
      return timeStart + cx * nsPerPx
    }
  }

  // ---- Zoom helpers -------------------------------------------------------

  /** Queue viewport mutations from wheel — chained and flushed once per frame. */
  _queueViewport(updateFn) {
    if (!this._vpQueue) this._vpQueue = []
    this._vpQueue.push(updateFn)
    if (!this._vpFlushRaf) {
      this._vpFlushRaf = requestAnimationFrame(() => {
        this._vpFlushRaf = null
        const queue = this._vpQueue
        this._vpQueue = null
        let vp = this._opts.getViewport()
        if (!vp) return
        for (const fn of queue) {
          vp = fn(vp) ?? vp
        }
        this._opts.onViewportChange?.(vp)
      })
    }
  }

  /** Zoom around a canvas pivot (horizontal mode – pivot on X axis). */
  _applyZoomAroundH(vp, pivotX, factor) {
    const { timeStart, timeEnd, canvasW } = vp
    const timeSpan = timeEnd - timeStart
    const pivotT = timeStart + (pivotX / canvasW) * timeSpan

    let newSpan = timeSpan * factor
    const trace = this._opts.getTrace()
    if (trace) {
      const minT = trace.timeMin >= 0 ? Math.max(0, trace.timeMin) : trace.timeMin
      const maxSpan = Math.max(1, trace.timeMax - minT)
      newSpan = Math.min(newSpan, maxSpan)
    }
    newSpan = Math.max(this._minTimeSpan, newSpan)

    const newStart = pivotT - (pivotX / canvasW) * newSpan
    const { s, e } = this._clampPan(newStart, newStart + newSpan)
    return { ...vp, timeStart: s, timeEnd: e }
  }

  _zoomAroundH(pivotX, factor) {
    const vp = this._opts.getViewport()
    if (!vp) return
    this._opts.onViewportChange?.(this._applyZoomAroundH(vp, pivotX, factor))
  }

  /** Zoom around a canvas pivot (vertical mode – pivot on Y axis). */
  _applyZoomAroundV(vp, pivotY, factor) {
    const { timeStart, timeEnd, canvasH } = vp
    const bodyH   = canvasH - this._vertHeaderH()
    const timeSpan = timeEnd - timeStart
    const pivotT = timeStart + Math.max(0, pivotY - this._vertHeaderH()) / bodyH * timeSpan

    let newSpan = timeSpan * factor
    const trace = this._opts.getTrace()
    if (trace) {
      const minT = trace.timeMin >= 0 ? Math.max(0, trace.timeMin) : trace.timeMin
      const maxSpan = Math.max(1, trace.timeMax - minT)
      newSpan = Math.min(newSpan, maxSpan)
    }
    newSpan = Math.max(this._minTimeSpan, newSpan)

    const relPos = Math.max(0, pivotY - this._vertHeaderH()) / bodyH
    const newStart = pivotT - relPos * newSpan
    const { s, e } = this._clampPan(newStart, newStart + newSpan)
    return { ...vp, timeStart: s, timeEnd: e }
  }

  _zoomAroundV(pivotY, factor) {
    const vp = this._opts.getViewport()
    if (!vp) return
    this._opts.onViewportChange?.(this._applyZoomAroundV(vp, pivotY, factor))
  }

  _applyPanH(vp, deltaX) {
    const { timeStart, timeEnd, canvasW } = vp
    const nsPerPx = (timeEnd - timeStart) / canvasW
    const deltaNs = deltaX * nsPerPx
    const { s, e } = this._clampPan(timeStart - deltaNs, timeEnd - deltaNs)
    return { ...vp, timeStart: s, timeEnd: e }
  }

  _panH(deltaX) {
    const vp = this._opts.getViewport()
    if (!vp) return
    this._opts.onViewportChange?.(this._applyPanH(vp, deltaX))
  }

  _applyPanV(vp, deltaY) {
    const { timeStart, timeEnd, canvasH } = vp
    const bodyH   = canvasH - this._vertHeaderH()
    const nsPerPx = (timeEnd - timeStart) / bodyH
    const deltaNs = deltaY * nsPerPx
    const { s, e } = this._clampPan(timeStart + deltaNs, timeEnd + deltaNs)
    return { ...vp, timeStart: s, timeEnd: e }
  }

  _panV(deltaY) {
    const vp = this._opts.getViewport()
    if (!vp) return
    this._opts.onViewportChange?.(this._applyPanV(vp, deltaY))
  }

  /**
   * Clamp a proposed [newStart, newEnd] pan so the viewport always overlaps
   * the trace by at least 20% of the current span on each side.
   * Returns { s, e } — the clamped start/end.
   */
  _clampPan(newStart, newEnd) {
    const trace = this._opts.getTrace()
    if (!trace) return { s: newStart, e: newEnd }
    const span   = newEnd - newStart
    const lo = trace.timeMin >= 0 ? Math.max(0, trace.timeMin) : trace.timeMin
    const hi = trace.timeMax
    const range = hi - lo
    if (range <= 0) return { s: lo, e: hi }
    if (span >= range) return { s: lo, e: hi }
    if (newStart < lo) return { s: lo, e: lo + span }
    if (newEnd   > hi) return { s: hi - span, e: hi }
    return { s: newStart, e: newEnd }
  }

  _applyScrollY(vp, delta) {
    return { ...vp, scrollY: Math.max(0, (vp.scrollY || 0) + delta) }
  }

  _scrollY(delta) {
    const vp = this._opts.getViewport()
    if (!vp) return
    this._opts.onViewportChange?.(this._applyScrollY(vp, delta))
  }

  _applyScrollX(vp, delta) {
    return { ...vp, scrollX: Math.max(0, (vp.scrollX || 0) + delta) }
  }

  _scrollX(delta) {
    const vp = this._opts.getViewport()
    if (!vp) return
    this._opts.onViewportChange?.(this._applyScrollX(vp, delta))
  }

  /** True when the time viewport is pinned at trace start/end (wheel orth preference). */
  _traceScrollExtents() {
    const trace = this._opts.getTrace()
    const vp = this._opts.getViewport()
    if (!trace || !vp) return { atStart: false, atEnd: false }
    const lo = trace.timeMin >= 0 ? Math.max(0, trace.timeMin) : trace.timeMin
    const hi = trace.timeMax
    const span = vp.timeEnd - vp.timeStart
    const eps = Math.max(1, span * 0.001)
    return {
      atStart: vp.timeStart <= lo + eps,
      atEnd: vp.timeEnd >= hi - eps,
    }
  }

  _applyWheelGesture(e) {
    const horiz = !this._isVertical()
    const { atStart, atEnd } = this._traceScrollExtents()
    const plan = wheelGesturePlan(e, horiz, { atTraceStart: atStart, atTraceEnd: atEnd })
    if (!plan.doTime && !plan.doOrth) return

    const headerH = horiz ? RULER_H : this._vertHeaderH()
    this._queueViewport(vp => {
      let next = applyWheelPlanToViewport(plan, vp, horiz, headerH)
      if (plan.doTime && plan.timeDelta !== 0) {
        const { s, e } = this._clampPan(next.timeStart, next.timeEnd)
        next = { ...next, timeStart: s, timeEnd: e }
      }
      return next
    })
  }

  // ---- Event handlers -----------------------------------------------------

  _onWheel(e) {
    e.preventDefault()
    const box = this._canvas
    if (!box || typeof box.getBoundingClientRect !== 'function') return
    const rect = box.getBoundingClientRect()
    const cx   = e.clientX - rect.left
    const cy   = e.clientY - rect.top
    const vert = this._isVertical()

    if (e.ctrlKey || e.metaKey) {
      // Pinch-to-zoom (Ctrl-wheel)
      const factor = e.deltaY > 0 ? 1.15 : 0.87
      if (vert) this._queueViewport(vp => this._applyZoomAroundV(vp, cy, factor))
      else       this._queueViewport(vp => this._applyZoomAroundH(vp, cx, factor))
    } else {
      this._applyWheelGesture(e)
    }
  }

  _onMouseDown(e) {
    // Context menu / overlay UI live inside the interaction root (canvas-wrap);
    // do not treat their presses as timeline clicks (would place a cursor).
    if (e.target?.closest?.('.context-menu, .scrollbar-track, .overview-popup')) {
      return
    }
    if (e.button === 1) {
      const trace = this._opts.getTrace()
      if (!trace) return
      const rect = this._canvas.getBoundingClientRect()
      const cx   = e.clientX - rect.left
      const cy   = e.clientY - rect.top
      const t = this._canvasToTimeForRange(cx, cy)
      if (t !== null) {
        this._midRangePressPos = { x: cx, y: cy }
        this._midRangePressT   = t
        this._midRangeDragging = false
        e.preventDefault()
      }
      return
    }
    if (e.button === 0) {
      const vp = this._opts.getViewport()
      if (!vp) return
      const rect = this._canvas.getBoundingClientRect()
      const cx   = e.clientX - rect.left
      const cy   = e.clientY - rect.top
      const vert = this._isVertical()

      // Some platforms/browsers are inconsistent about emitting a `dblclick`
      // after an initial ruler press enters pan mode. Treat the 2nd primary
      // press on the ruler as fit-to-window directly for robust behavior.
      const isRulerClick = vert ? (cx < RULER_W || cy < this._vertHeaderH()) : (cy < RULER_H)

      // Ctrl+drag: measure-ruler tool — takes priority over the ruler
      // dblclick / cursor / mark drags below so it works anywhere in the body.
      if (e.ctrlKey && !isRulerClick) {
        const tMeasure = this._canvasToTime(cx, cy)
        if (tMeasure !== null) {
          this._measureDragging = true
          this._measurePressT   = tMeasure
          this._measureAnchorPx = vert ? cx : cy
          this._canvas.style.cursor = 'crosshair'
          this._opts.onMeasureChange?.({ t0: tMeasure, t1: tMeasure, anchorPx: this._measureAnchorPx })
          e.preventDefault()
          return
        }
      }

      if (isRulerClick && e.detail >= 2) {
        this._dragging = false
        this._draggingCursorIdx = -1
        this._draggingMarkId = null
        this._opts.onFitToWindow?.()
        e.preventDefault()
        return
      }

      const t = this._canvasToTime(cx, cy)
      if (t !== null) {
        const span = vp.timeEnd - vp.timeStart
        const pxBase = vert ? Math.max(1, vp.canvasH - this._vertHeaderH()) : Math.max(1, vp.canvasW)
        const nsPerPx = span / pxBase
        const cursorHit = findNearestCursorIndex(this._cursors, t, this._dragCursorPx * nsPerPx)
        if (cursorHit !== -1) {
          this._opts.onBeforeCursorChange?.()
          this._draggingCursorIdx = cursorHit
          this._canvas.style.cursor = vert ? 'ns-resize' : 'ew-resize'
          e.preventDefault()
          return
        }
        const marks = this._opts.getMarks?.() || []
        const markHit = findNearestMark(marks, t, this._dragMarkPx * nsPerPx)
        if (markHit) {
          this._opts.onBeforeMarkChange?.()
          this._draggingMarkId = markHit.id
          this._canvas.style.cursor = vert ? 'ns-resize' : 'ew-resize'
          e.preventDefault()
          return
        }
      }

      if (vert) {
        if (cy >= this._vertHeaderH() && cx >= RULER_W) {
          // First check if a segment bar was clicked; if so highlight it instead
          const traceObj = this._opts.getTrace()
          const ropts    = this._opts.getOptions?.()
          if (traceObj && ropts) {
            const seg = hitTestSegmentVertical(traceObj, vp, ropts, cx, cy)
            if (seg) { this._opts.onSegmentClick?.(seg); return }
          }
          // Click in timeline body → place cursor
          if (t !== null) {
            this._opts.onClearSelection?.()
            this._placeCursor(t, e.shiftKey)
            return
          }
        }
        // Click in column header area → core expand/collapse or task highlight
        if (cy < this._vertHeaderH() && cx >= RULER_W) {
          const trace = this._opts.getTrace()
          const ropts = this._opts.getOptions?.()
          if (trace && ropts) {
            const col = hitTestColumn(trace, vp, ropts, cx, cy)
            if (col?.type === 'core') {
              this._opts.onExpandToggle?.(col.key)
              e.preventDefault()
              return
            }
            if (col?.type === 'task') {
              this._opts.onHighlightClick?.(col.key)
              e.preventDefault()
              return
            }
            if (col?.type === 'core-task') {
              this._opts.onHighlightClick?.(taskMergeKey(col.taskKey))
              e.preventDefault()
              return
            }
            if (col?.type === 'sti' && col.isExpandable) {
              this._opts.onStiExpandToggle?.(col.key)
              e.preventDefault()
              return
            }
          }
          this._opts.onClearSelection?.()
        }
        // Click on ruler or header (non-core) → start pan
        this._dragging       = true
        this._dragStartX     = e.clientX
        this._dragStartY     = e.clientY
        this._dragStartTime  = vp.timeStart
        this._dragStartScrollX = vp.scrollX ?? 0
      } else {
        if (cy >= RULER_H) {
          // First check if a segment bar was clicked; if so highlight it instead
          const traceObj = this._opts.getTrace()
          const ropts    = this._opts.getOptions?.()
          if (traceObj && ropts) {
            const seg = hitTestSegment(traceObj, vp, ropts, cx, cy)
            if (seg) { this._opts.onSegmentClick?.(seg); return }
          }
          const tClick = this._canvasToTime(cx, cy)
          this._opts.onClearSelection?.()
          this._placeCursor(tClick, e.shiftKey)
          return
        }
        // Click on ruler → start panning
        this._dragging      = true
        this._dragStartX    = e.clientX
        this._dragStartTime = vp.timeStart
      }
    }
  }

  _onMouseMove(e) {
    const rect = this._canvas.getBoundingClientRect()
    const cx   = e.clientX - rect.left
    const cy   = e.clientY - rect.top
    const vert = this._isVertical()

    // Ctrl+drag measure ruler: redraw the double-arrow line + Δtime label,
    // and keep the ghost hover line tracking the mouse during the drag too.
    if (this._measureDragging) {
      const t = this._canvasToTime(cx, cy)
      if (t !== null) {
        this._opts.onMeasureChange?.({ t0: this._measurePressT, t1: t, anchorPx: this._measureAnchorPx })
        this._opts.onHoverTimeChange?.(t)
      }
      return
    }

    // Track hover time (skip during pan / middle range select)
    if (!this._dragging && this._midRangePressT === null) {
      const t = this._canvasToTime(cx, cy)
      if (t !== null) this._opts.onHoverTimeChange?.(t)
      else             this._opts.onHoverTimeChange?.(null)
    }

    if (this._draggingCursorIdx !== -1) {
      const tDrag = this._canvasToTime(cx, cy)
      if (tDrag !== null) {
        const next = [...this._cursors]
        next[this._draggingCursorIdx] = tDrag
        this._cursors = next
        this._lastActiveCursorIdx = this._draggingCursorIdx
        this._opts.onCursorsChange?.(next)
      }
      return
    }

    if (this._draggingMarkId !== null) {
      const tDrag = this._canvasToTime(cx, cy)
      if (tDrag !== null) {
        this._opts.onMarkMove?.({ id: this._draggingMarkId, ns: tDrag })
      }
      return
    }

    if (this._dragging) {
      const dx = e.clientX - this._dragStartX
      const dy = e.clientY - this._dragStartY
      if (vert) {
        this._queueViewport(vp => {
          const bodyH   = vp.canvasH - this._vertHeaderH()
          const nsPerPx = (vp.timeEnd - vp.timeStart) / bodyH
          const rawStart = this._dragStartTime - dy * nsPerPx
          const { s, e: eT } = this._clampPan(rawStart, rawStart + (vp.timeEnd - vp.timeStart))
          const newScrollX = Math.max(0, this._dragStartScrollX - dx)
          return { ...vp, timeStart: s, timeEnd: eT, scrollX: newScrollX }
        })
      } else {
        this._queueViewport(vp => {
          const ns = (vp.timeEnd - vp.timeStart) / vp.canvasW
          const rawStart = this._dragStartTime - dx * ns
          const { s, e: eT } = this._clampPan(rawStart, rawStart + (vp.timeEnd - vp.timeStart))
          return { ...vp, timeStart: s, timeEnd: eT }
        })
      }
      return
    }

    if (this._midRangePressT !== null) {
      const dx = cx - this._midRangePressPos.x
      const dy = cy - this._midRangePressPos.y
      if (!this._midRangeDragging && (Math.abs(dx) > 6 || Math.abs(dy) > 6)) {
        this._midRangeDragging = true
      }
      if (this._midRangeDragging) {
        const t = this._canvasToTimeForRange(cx, cy)
        if (t !== null) {
          e.preventDefault()
          this._opts.onRangeSelectChange?.({
            t0: this._midRangePressT,
            t1: t,
          })
        }
      }
      return
    }

    this._updateHoverCursor(cx, cy)

    this._hoverCx = cx
    this._hoverCy = cy
    if (!this._hoverRaf) {
      this._hoverRaf = requestAnimationFrame(() => {
        this._hoverRaf = null
        this._runHoverHitTests(this._hoverCx, this._hoverCy)
      })
    }
  }

  _runHoverHitTests(cx, cy) {
    const vert = this._isVertical()
    const trace = this._opts.getTrace()
    const ropts = this._opts.getOptions?.()
    if (trace && this._opts.getViewport()) {
      const vp = this._opts.getViewport()
      if (vert) {
        const stiEv = hitTestStiVertical(trace, vp, ropts, cx, cy)
        this._opts.onStiHover?.(stiEv || null)
        const col = hitTestColumn(trace, vp, ropts, cx, cy)
        this._opts.onRowHover?.(col || null)
        const segV = hitTestSegmentVertical(trace, vp, ropts, cx, cy)
        this._opts.onSegmentHover?.(segV || null)
      } else {
        const stiEv = hitTestSti(trace, vp, ropts, cx, cy)
        this._opts.onStiHover?.(stiEv || null)
        const row = hitTestRow(trace, vp, ropts, cx, cy)
        this._opts.onRowHover?.(row || null)
        const seg = hitTestSegment(trace, vp, ropts, cx, cy)
        this._opts.onSegmentHover?.(seg || null)
      }
    }
  }

  _onMouseUp(e) {
    if (this._measureDragging) {
      this._measureDragging = false
      this._measurePressT   = null
      this._measureAnchorPx = null
      this._canvas.style.cursor = 'crosshair'
      this._opts.onMeasureEnd?.()
      return
    }
    if (e.button === 1 && this._midRangePressT !== null) {
      const rect = this._canvas.getBoundingClientRect()
      const cx   = e.clientX - rect.left
      const cy   = e.clientY - rect.top
      if (this._midRangeDragging) {
        const t = this._canvasToTimeForRange(cx, cy)
        if (t !== null) {
          this._zoomToRange(this._midRangePressT, t)
        }
        this._opts.onRangeSelectEnd?.()
      }
      this._midRangePressPos = null
      this._midRangePressT   = null
      this._midRangeDragging = false
      return
    }
    this._draggingCursorIdx = -1
    this._draggingMarkId = null
    this._dragging = false
    this._canvas.style.cursor = 'crosshair'
  }

  /** Releasing Ctrl mid-drag hides the measure-ruler even if the mouse button is still held. */
  _onKeyUp(e) {
    if (e.key === 'Control' && this._measureDragging) {
      this._measureDragging = false
      this._measurePressT   = null
      this._measureAnchorPx = null
      this._canvas.style.cursor = 'crosshair'
      this._opts.onMeasureEnd?.()
    }
  }

  _onMouseLeave() {
    if (this._measureDragging) {
      this._measureDragging = false
      this._measurePressT   = null
      this._measureAnchorPx = null
      this._opts.onMeasureEnd?.()
    }
    if (this._midRangePressT !== null) {
      this._midRangePressPos = null
      this._midRangePressT   = null
      this._midRangeDragging = false
      this._opts.onRangeSelectEnd?.()
    }
    this._draggingCursorIdx = -1
    this._draggingMarkId = null
    this._dragging = false
    this._canvas.style.cursor = 'crosshair'
    this._opts.onHoverTimeChange?.(null)
    this._opts.onStiHover?.(null)
    this._opts.onRowHover?.(null)
    this._opts.onSegmentHover?.(null)
  }

  _onDblClick(e) {
    const rect = this._canvas.getBoundingClientRect()
    const cx   = e.clientX - rect.left
    const cy   = e.clientY - rect.top
    const vert = this._isVertical()
    // Double-click on ruler → fit to window (clears zoom history)
    if (vert ? cx < RULER_W || cy < this._vertHeaderH() : cy < RULER_H) {
      this._zoomHistory = []
      this._opts.onFitToWindow?.()
      return
    }
    // Double-click on segment → zoom to fit segment, or restore on second dblclick
    const trace = this._opts.getTrace()
    const vp    = this._opts.getViewport()
    const ropts = this._opts.getOptions?.()
    if (trace && vp && ropts) {
      const seg = vert
        ? hitTestSegmentVertical(trace, vp, ropts, cx, cy)
        : hitTestSegment(trace, vp, ropts, cx, cy)
      if (seg) {
        const segKey = `${seg.start}:${seg.end}:${seg.task}:${seg.core}`
        if (this._zoomHistory.length &&
            this._zoomHistory[this._zoomHistory.length - 1].segKey === segKey) {
          this._restoreZoom()
        } else {
          this._zoomToSegment(seg)
        }
      }
    }
  }

  _zoomToSegment(seg) {
    const vp = this._opts.getViewport()
    if (!vp) return
    // Save current viewport so a second dblclick can restore it.
    const segKey = `${seg.start}:${seg.end}:${seg.task}:${seg.core}`
    this._zoomHistory.push({
      timeStart: vp.timeStart,
      timeEnd:   vp.timeEnd,
      scrollY:   vp.scrollY ?? 0,
      scrollX:   vp.scrollX ?? 0,
      segKey,
    })
    const dur    = seg.end - seg.start
    const margin = Math.max(1, Math.floor(dur / 10))
    const { s, e } = this._clampPan(seg.start - margin, seg.end + margin)
    this._opts.onViewportChange?.({ ...vp, timeStart: s, timeEnd: e })
  }

  _restoreZoom() {
    if (!this._zoomHistory.length) return
    const prev = this._zoomHistory.pop()
    const vp   = this._opts.getViewport()
    if (!vp) return
    this._opts.onViewportChange?.({
      ...vp,
      timeStart: prev.timeStart,
      timeEnd:   prev.timeEnd,
      scrollY:   prev.scrollY,
      scrollX:   prev.scrollX,
    })
  }

  _onContextMenu(e) {
    e.preventDefault()
    // macOS (and some Linux setups) maps Ctrl+left-click to contextmenu.
    // Ctrl+drag is the measure-ruler tool — do not open the timeline menu.
    if (e.ctrlKey || this._measureDragging) return
    const rect = this._canvas.getBoundingClientRect()
    const cx   = e.clientX - rect.left
    const cy   = e.clientY - rect.top
    const t    = this._canvasToTime(cx, cy)
    let segment = null
    const traceObj = this._opts.getTrace?.()
    const ropts = this._opts.getOptions?.()
    const vp = this._opts.getViewport()
    if (traceObj && ropts && vp && t !== null) {
      segment = this._isVertical()
        ? hitTestSegmentVertical(traceObj, vp, ropts, cx, cy)
        : hitTestSegment(traceObj, vp, ropts, cx, cy)
    }
    if (t !== null) {
      this._opts.onContextMenu?.({ ns: t, x: e.clientX, y: e.clientY, shiftKey: e.shiftKey, segment })
    }
  }

  _nsPerPx() {
    const vp = this._opts.getViewport()
    if (!vp) return 1
    const vert = this._isVertical()
    const span = vp.timeEnd - vp.timeStart
    const pxBase = vert ? Math.max(1, vp.canvasH - this._vertHeaderH()) : Math.max(1, vp.canvasW)
    return span / pxBase
  }

  _placeCursor(t, shiftSnap = false) {
    this._opts.onBeforeCursorChange?.()
    const trace = this._opts.getTrace?.()
    let placeT = t
    if (shiftSnap && trace) {
      placeT = snapToBoundary(trace, t, this._nsPerPx())
    }
    const cursors = [...this._cursors]
    let placed = false
    // Clicking near an existing cursor removes it
    const vp = this._opts.getViewport()
    if (vp) {
      const vert = this._isVertical()
      let snapNs
      if (vert) {
        const bodyH = vp.canvasH - this._vertHeaderH()
        const nsPerPx = (vp.timeEnd - vp.timeStart) / bodyH
        snapNs = 5 * nsPerPx
      } else {
        const nsPerPx = (vp.timeEnd - vp.timeStart) / vp.canvasW
        snapNs = 5 * nsPerPx
      }
      for (let i = 0; i < cursors.length; i++) {
        if (cursors[i] !== null && Math.abs(cursors[i] - t) < snapNs) {
          cursors[i] = null
          placed = true
          break
        }
      }
    }
    if (placed) {
      this._cursors = cursors
      this._opts.onCursorsChange?.(cursors)
    } else {
      this._assignCursorSlot(placeT)
    }
  }

  _assignCursorSlot(placeT) {
    const cursors = [...this._cursors]
    const mc = maxCursorsFrom(this._opts)
    while (cursors.length < mc) cursors.push(null)
    const emptyIdx = cursors.findIndex(c => c === null)
    if (emptyIdx !== -1) {
      cursors[emptyIdx] = placeT
      this._lastActiveCursorIdx = emptyIdx
    } else {
      cursors.shift()
      cursors.push(placeT)
      this._lastActiveCursorIdx = cursors.length - 1
    }
    this._cursors = cursors
    this._opts.onCursorsChange?.(cursors)
  }

  _updateHoverCursor(cx, cy) {
    const vp = this._opts.getViewport()
    if (!vp) {
      this._canvas.style.cursor = 'crosshair'
      return
    }
    const t = this._canvasToTime(cx, cy)
    if (t === null) {
      this._canvas.style.cursor = 'crosshair'
      return
    }
    const vert = this._isVertical()
    const span = vp.timeEnd - vp.timeStart
    const pxBase = vert ? Math.max(1, vp.canvasH - this._vertHeaderH()) : Math.max(1, vp.canvasW)
    const nsPerPx = span / pxBase
    const cursorHit = findNearestCursorIndex(this._cursors, t, this._dragCursorPx * nsPerPx)
    const markHit = findNearestMark(this._opts.getMarks?.() || [], t, this._dragMarkPx * nsPerPx)
    if (cursorHit !== -1 || markHit) {
      this._canvas.style.cursor = vert ? 'ns-resize' : 'ew-resize'
      return
    }
    this._canvas.style.cursor = 'crosshair'
  }
}

