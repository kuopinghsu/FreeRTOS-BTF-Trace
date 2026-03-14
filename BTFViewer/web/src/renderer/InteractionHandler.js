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
         RULER_H, ROW_H, ROW_GAP, RULER_W, HEADER_H,
         findNearestCursorIndex, findNearestMark } from './TimelineRenderer.js'

const MAX_CURSORS = 4

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
   */
  constructor(canvas, options = {}) {
    this._canvas  = canvas
    this._opts    = options
    this._cursors = [null, null, null, null]  // up to MAX_CURSORS timestamps

    // Drag state
    this._dragging        = false
    this._dragStartX      = 0
    this._dragStartY      = 0
    this._dragStartTime   = 0   // timeStart at drag begin
    this._dragStartScrollX = 0
    this._draggingCursorIdx = -1
    this._draggingMarkId = null
    this._dragCursorPx = 8
    this._dragMarkPx = 6

    // Min zoom: entire trace visible
    this._minTimeSpan = 1

    this._boundWheel       = this._onWheel.bind(this)
    this._boundMouseDown   = this._onMouseDown.bind(this)
    this._boundMouseMove   = this._onMouseMove.bind(this)
    this._boundMouseUp     = this._onMouseUp.bind(this)
    this._boundMouseLeave  = this._onMouseLeave.bind(this)
    this._boundDblClick    = this._onDblClick.bind(this)
    this._boundContextMenu = this._onContextMenu.bind(this)

    canvas.addEventListener('wheel',       this._boundWheel,     { passive: false })
    canvas.addEventListener('mousedown',   this._boundMouseDown)
    canvas.addEventListener('mousemove',   this._boundMouseMove)
    canvas.addEventListener('mouseup',     this._boundMouseUp)
    canvas.addEventListener('mouseleave',  this._boundMouseLeave)
    canvas.addEventListener('dblclick',    this._boundDblClick)
    canvas.addEventListener('contextmenu', this._boundContextMenu)
  }

  destroy() {
    const c = this._canvas
    c.removeEventListener('wheel',       this._boundWheel)
    c.removeEventListener('mousedown',   this._boundMouseDown)
    c.removeEventListener('mousemove',   this._boundMouseMove)
    c.removeEventListener('mouseup',     this._boundMouseUp)
    c.removeEventListener('mouseleave',  this._boundMouseLeave)
    c.removeEventListener('dblclick',    this._boundDblClick)
    c.removeEventListener('contextmenu', this._boundContextMenu)
  }

  // ---- Public API --------------------------------------------------------

  setCursors(cursors) {
    this._cursors = cursors.slice(0, MAX_CURSORS)
    while (this._cursors.length < MAX_CURSORS) this._cursors.push(null)
  }

  setMinTimeSpan(span) {
    this._minTimeSpan = Math.max(1, span)
  }

  // ---- Helpers -----------------------------------------------------------

  _isVertical() {
    return (this._opts.getOptions?.()?.orientation ?? 'h') === 'v'
  }

  /** Convert canvas coordinates to a timestamp. */
  _canvasToTime(cx, cy) {
    const vp = this._opts.getViewport()
    if (!vp) return null
    if (this._isVertical()) {
      // In vertical mode, Y maps to time
      const { timeStart, timeEnd, canvasH } = vp
      const pxPerNs = (canvasH - HEADER_H) / (timeEnd - timeStart)
      if (pxPerNs <= 0 || cy < HEADER_H) return null
      return timeStart + (cy - HEADER_H) / pxPerNs
    } else {
      // In horizontal mode, X maps to time
      const { timeStart, timeEnd, canvasW } = vp
      const nsPerPx = (timeEnd - timeStart) / canvasW
      return timeStart + cx * nsPerPx
    }
  }

  // ---- Zoom helpers -------------------------------------------------------

  /** Zoom around a canvas pivot (horizontal mode – pivot on X axis). */
  _zoomAroundH(pivotX, factor) {
    const vp = this._opts.getViewport()
    if (!vp) return
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
    this._opts.onViewportChange?.({ ...vp, timeStart: s, timeEnd: e })
  }

  /** Zoom around a canvas pivot (vertical mode – pivot on Y axis). */
  _zoomAroundV(pivotY, factor) {
    const vp = this._opts.getViewport()
    if (!vp) return
    const { timeStart, timeEnd, canvasH } = vp
    const bodyH   = canvasH - HEADER_H
    const timeSpan = timeEnd - timeStart
    const pivotT = timeStart + Math.max(0, pivotY - HEADER_H) / bodyH * timeSpan

    let newSpan = timeSpan * factor
    const trace = this._opts.getTrace()
    if (trace) {
      const minT = trace.timeMin >= 0 ? Math.max(0, trace.timeMin) : trace.timeMin
      const maxSpan = Math.max(1, trace.timeMax - minT)
      newSpan = Math.min(newSpan, maxSpan)
    }
    newSpan = Math.max(this._minTimeSpan, newSpan)

    const relPos = Math.max(0, pivotY - HEADER_H) / bodyH
    const newStart = pivotT - relPos * newSpan
    const { s, e } = this._clampPan(newStart, newStart + newSpan)
    this._opts.onViewportChange?.({ ...vp, timeStart: s, timeEnd: e })
  }

  _panH(deltaX) {
    const vp = this._opts.getViewport()
    if (!vp) return
    const { timeStart, timeEnd, canvasW } = vp
    const nsPerPx = (timeEnd - timeStart) / canvasW
    const deltaNs = deltaX * nsPerPx
    const { s, e } = this._clampPan(timeStart - deltaNs, timeEnd - deltaNs)
    this._opts.onViewportChange?.({ ...vp, timeStart: s, timeEnd: e })
  }

  _panV(deltaY) {
    const vp = this._opts.getViewport()
    if (!vp) return
    const { timeStart, timeEnd, canvasH } = vp
    const bodyH   = canvasH - HEADER_H
    const nsPerPx = (timeEnd - timeStart) / bodyH
    const deltaNs = deltaY * nsPerPx
    const { s, e } = this._clampPan(timeStart + deltaNs, timeEnd + deltaNs)
    this._opts.onViewportChange?.({ ...vp, timeStart: s, timeEnd: e })
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

  _scrollY(delta) {
    const vp = this._opts.getViewport()
    if (!vp) return
    const newScrollY = Math.max(0, (vp.scrollY || 0) + delta)
    this._opts.onViewportChange?.({ ...vp, scrollY: newScrollY })
  }

  _scrollX(delta) {
    const vp = this._opts.getViewport()
    if (!vp) return
    const newScrollX = Math.max(0, (vp.scrollX || 0) + delta)
    this._opts.onViewportChange?.({ ...vp, scrollX: newScrollX })
  }

  // ---- Event handlers -----------------------------------------------------

  _onWheel(e) {
    e.preventDefault()
    const rect = this._canvas.getBoundingClientRect()
    const cx   = e.clientX - rect.left
    const cy   = e.clientY - rect.top
    const vert = this._isVertical()

    if (e.ctrlKey || e.metaKey) {
      // Pinch-to-zoom (Ctrl-wheel)
      const factor = e.deltaY > 0 ? 1.15 : 0.87
      if (vert) this._zoomAroundV(cy, factor)
      else       this._zoomAroundH(cx, factor)
    } else if (vert) {
      // === Vertical mode ===
      const isHorizInput = e.shiftKey || Math.abs(e.deltaX) > Math.abs(e.deltaY)
      if (isHorizInput) {
        // Horizontal input (trackpad swipe or Shift+scroll) → scroll columns
        const dx = e.shiftKey ? e.deltaY : e.deltaX
        this._scrollX(dx)
      } else {
        // Vertical scroll → pan time
        this._panV(e.deltaMode === 1 ? e.deltaY * (ROW_H + ROW_GAP) : e.deltaY)
      }
    } else {
      // === Horizontal mode ===
      const isHorizInput = Math.abs(e.deltaX) > Math.abs(e.deltaY)
      if (isHorizInput) {
        // Trackpad horizontal swipe → pan time left/right
        this._panH(e.deltaX)
      } else if (e.shiftKey) {
        // Shift + vertical scroll → pan time left/right
        this._panH(e.deltaY)
      } else {
        // Plain vertical scroll → scroll rows up/down
        const deltaY = e.deltaMode === 1 ? e.deltaY * (ROW_H + ROW_GAP) : e.deltaY
        this._scrollY(deltaY)
      }
    }
  }

  _onMouseDown(e) {
    if (e.button === 1) {
      // Middle button: start pan-drag
      this._dragging       = true
      this._dragStartX     = e.clientX
      this._dragStartY     = e.clientY
      const vp = this._opts.getViewport()
      this._dragStartTime  = vp?.timeStart ?? 0
      this._dragStartScrollX = vp?.scrollX ?? 0
      e.preventDefault()
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
      const isRulerClick = vert ? (cx < RULER_W || cy < HEADER_H) : (cy < RULER_H)
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
        const pxBase = vert ? Math.max(1, vp.canvasH - HEADER_H) : Math.max(1, vp.canvasW)
        const nsPerPx = span / pxBase
        const cursorHit = findNearestCursorIndex(this._cursors, t, this._dragCursorPx * nsPerPx)
        if (cursorHit !== -1) {
          this._draggingCursorIdx = cursorHit
          this._canvas.style.cursor = vert ? 'ns-resize' : 'ew-resize'
          e.preventDefault()
          return
        }
        const marks = this._opts.getMarks?.() || []
        const markHit = findNearestMark(marks, t, this._dragMarkPx * nsPerPx)
        if (markHit) {
          this._draggingMarkId = markHit.id
          this._canvas.style.cursor = vert ? 'ns-resize' : 'ew-resize'
          e.preventDefault()
          return
        }
      }

      if (vert) {
        if (cy >= HEADER_H && cx >= RULER_W) {
          // Click in timeline body → place cursor
          if (t !== null) { this._placeCursor(t); return }
        }
        // Click in column header area → check for core expand/collapse
        if (cy < HEADER_H && cx >= RULER_W) {
          const trace = this._opts.getTrace()
          const ropts = this._opts.getOptions?.()
          if (trace && ropts) {
            const col = hitTestColumn(trace, vp, ropts, cx, cy)
            if (col?.type === 'core') {
              this._opts.onExpandToggle?.(col.key)
              e.preventDefault()
              return
            }
          }
        }
        // Click on ruler or header (non-core) → start pan
        this._dragging       = true
        this._dragStartX     = e.clientX
        this._dragStartY     = e.clientY
        this._dragStartTime  = vp.timeStart
        this._dragStartScrollX = vp.scrollX ?? 0
      } else {
        if (cy >= RULER_H) {
          const t = this._canvasToTime(cx, cy)
          this._placeCursor(t)
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

    // Track hover time
    const t = this._canvasToTime(cx, cy)
    if (t !== null) this._opts.onHoverTimeChange?.(t)
    else             this._opts.onHoverTimeChange?.(null)

    if (this._draggingCursorIdx !== -1) {
      const tDrag = this._canvasToTime(cx, cy)
      if (tDrag !== null) {
        const next = [...this._cursors]
        next[this._draggingCursorIdx] = tDrag
        this._cursors = next
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
      const vp = this._opts.getViewport()
      if (!vp) return
      if (vert) {
        const dy      = e.clientY - this._dragStartY
        const dx      = e.clientX - this._dragStartX
        const bodyH   = vp.canvasH - HEADER_H
        const nsPerPx = (vp.timeEnd - vp.timeStart) / bodyH
        const rawStart = this._dragStartTime - dy * nsPerPx
        const { s, e: eT } = this._clampPan(rawStart, rawStart + (vp.timeEnd - vp.timeStart))
        const newScrollX = Math.max(0, this._dragStartScrollX - dx)
        this._opts.onViewportChange?.({ ...vp, timeStart: s, timeEnd: eT, scrollX: newScrollX })
      } else {
        const dx      = e.clientX - this._dragStartX
        const nsPerPx = (vp.timeEnd - vp.timeStart) / vp.canvasW
        const rawStart = this._dragStartTime - dx * nsPerPx
        const { s, e: eT } = this._clampPan(rawStart, rawStart + (vp.timeEnd - vp.timeStart))
        this._opts.onViewportChange?.({ ...vp, timeStart: s, timeEnd: eT })
      }
      return
    }

    this._updateHoverCursor(cx, cy)

    // Hover: detect STI marker and row/column
    const trace = this._opts.getTrace()
    const ropts = this._opts.getOptions?.()
    if (trace && this._opts.getViewport()) {
      const vp = this._opts.getViewport()
      if (vert) {
        const stiEv = hitTestStiVertical(trace, vp, ropts, cx, cy)
        this._opts.onStiHover?.(stiEv || null)
        const col = hitTestColumn(trace, vp, ropts, cx, cy)
        this._opts.onRowHover?.(col || null)
      } else {
        const stiEv = hitTestSti(trace, vp, ropts, cx, cy)
        this._opts.onStiHover?.(stiEv || null)
        const row = hitTestRow(trace, vp, ropts, cx, cy)
        this._opts.onRowHover?.(row || null)
      }
    }
  }

  _onMouseUp() {
    this._draggingCursorIdx = -1
    this._draggingMarkId = null
    this._dragging = false
    this._canvas.style.cursor = 'crosshair'
  }

  _onMouseLeave() {
    this._draggingCursorIdx = -1
    this._draggingMarkId = null
    this._dragging = false
    this._canvas.style.cursor = 'crosshair'
    this._opts.onHoverTimeChange?.(null)
  }

  _onDblClick(e) {
    const rect = this._canvas.getBoundingClientRect()
    const cx   = e.clientX - rect.left
    const cy   = e.clientY - rect.top
    const vert = this._isVertical()
    // Double-click on ruler → fit to window
    if (vert ? cx < RULER_W || cy < HEADER_H : cy < RULER_H) {
      this._opts.onFitToWindow?.()
    }
  }

  _onContextMenu(e) {
    e.preventDefault()
    const rect = this._canvas.getBoundingClientRect()
    const cx   = e.clientX - rect.left
    const cy   = e.clientY - rect.top
    const t    = this._canvasToTime(cx, cy)
    if (t !== null) {
      this._opts.onContextMenu?.({ ns: t, x: e.clientX, y: e.clientY })
    }
  }

  _placeCursor(t) {
    const cursors = [...this._cursors]
    let placed = false
    // Clicking near an existing cursor removes it
    const vp = this._opts.getViewport()
    if (vp) {
      const vert = this._isVertical()
      let snapNs
      if (vert) {
        const bodyH = vp.canvasH - HEADER_H
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
    if (!placed) {
      const emptyIdx = cursors.findIndex(c => c === null)
      if (emptyIdx !== -1) {
        cursors[emptyIdx] = t
      } else {
        cursors.shift()
        cursors.push(t)
      }
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
    const pxBase = vert ? Math.max(1, vp.canvasH - HEADER_H) : Math.max(1, vp.canvasW)
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

