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
 */

import { hitTestSti, hitTestRow, RULER_H, ROW_H, ROW_GAP } from './TimelineRenderer.js'

const MAX_CURSORS = 4

export class InteractionHandler {
  /**
   * @param {HTMLCanvasElement} canvas
   * @param {object} options
   * @param {Function} options.getTrace        () => BtfTrace | null
   * @param {Function} options.getViewport     () => viewport object
   * @param {Function} options.getOptions      () => render options (viewMode, expanded, …)
   * @param {Function} options.onViewportChange
   * @param {Function} options.onCursorsChange
   * @param {Function} options.onStiHover
   * @param {Function} options.onRowHover
   * @param {Function} options.onFitToWindow
   */
  constructor(canvas, options = {}) {
    this._canvas  = canvas
    this._opts    = options
    this._cursors = [null, null, null, null]  // up to MAX_CURSORS timestamps

    // Drag state
    this._dragging        = false
    this._dragStartX      = 0
    this._dragStartTime   = 0   // timeStart at drag begin

    // Min zoom: entire trace visible
    this._minTimeSpan = 1

    this._boundWheel      = this._onWheel.bind(this)
    this._boundMouseDown  = this._onMouseDown.bind(this)
    this._boundMouseMove  = this._onMouseMove.bind(this)
    this._boundMouseUp    = this._onMouseUp.bind(this)
    this._boundMouseLeave = this._onMouseLeave.bind(this)
    this._boundDblClick   = this._onDblClick.bind(this)
    this._boundContextMenu = (e) => e.preventDefault()

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

  // ---- Zoom helpers -------------------------------------------------------

  _zoomAround(pivotX, factor) {
    const vp = this._opts.getViewport()
    if (!vp) return
    const { timeStart, timeEnd, canvasW } = vp
    const timeSpan = timeEnd - timeStart
    const pivotT = timeStart + (pivotX / canvasW) * timeSpan

    let newSpan = timeSpan * factor
    const trace = this._opts.getTrace()
    if (trace) {
      const maxSpan = (trace.timeMax - trace.timeMin) * 1.05
      newSpan = Math.min(newSpan, maxSpan)
    }
    newSpan = Math.max(this._minTimeSpan, newSpan)

    // Keep pivotT at the same screen position
    const newStart = pivotT - (pivotX / canvasW) * newSpan
    const newEnd   = newStart + newSpan

    this._opts.onViewportChange?.({
      ...vp,
      timeStart: newStart,
      timeEnd:   newEnd,
    })
  }

  _pan(deltaX) {
    const vp = this._opts.getViewport()
    if (!vp) return
    const { timeStart, timeEnd, canvasW } = vp
    const nsPerPx = (timeEnd - timeStart) / canvasW
    const deltaNs = deltaX * nsPerPx

    this._opts.onViewportChange?.({
      ...vp,
      timeStart: timeStart - deltaNs,
      timeEnd:   timeEnd   - deltaNs,
    })
  }

  _scrollY(delta) {
    const vp = this._opts.getViewport()
    if (!vp) return
    const newScrollY = Math.max(0, (vp.scrollY || 0) + delta)
    this._opts.onViewportChange?.({ ...vp, scrollY: newScrollY })
  }

  // ---- Event handlers -----------------------------------------------------

  _onWheel(e) {
    e.preventDefault()
    const rect = this._canvas.getBoundingClientRect()
    const cx   = e.clientX - rect.left

    if (e.ctrlKey || e.metaKey) {
      // Pinch-to-zoom on trackpad (Ctrl-wheel on desktop)
      const factor = e.deltaY > 0 ? 1.15 : 0.87
      this._zoomAround(cx, factor)
    } else if (e.shiftKey) {
      // Horizontal scroll
      this._pan(e.deltaY)
    } else {
      // Vertical scroll (for rows that extend beyond canvas)
      const deltaY = e.deltaMode === 1 ? e.deltaY * (ROW_H + ROW_GAP) : e.deltaY
      this._scrollY(deltaY)
    }
  }

  _onMouseDown(e) {
    if (e.button === 1) {
      // Middle button: start range-zoom drag (treated as pan here for simplicity)
      this._dragging      = true
      this._dragStartX    = e.clientX
      const vp = this._opts.getViewport()
      this._dragStartTime = vp?.timeStart ?? 0
      e.preventDefault()
      return
    }
    if (e.button === 0) {
      const vp = this._opts.getViewport()
      if (!vp) return
      const rect = this._canvas.getBoundingClientRect()
      const cx   = e.clientX - rect.left
      const cy   = e.clientY - rect.top

      // A click below the ruler places / removes a cursor
      if (cy >= RULER_H) {
        const nsPerPx = (vp.timeEnd - vp.timeStart) / vp.canvasW
        const t = vp.timeStart + cx * nsPerPx
        this._placeCursor(t)
        return
      }

      // Click on ruler → start panning
      this._dragging      = true
      this._dragStartX    = e.clientX
      this._dragStartTime = vp.timeStart
    }
  }

  _onMouseMove(e) {
    const rect = this._canvas.getBoundingClientRect()
    const cx   = e.clientX - rect.left
    const cy   = e.clientY - rect.top

    // Always track hover time (drives the dash line + time label)
    const vp = this._opts.getViewport()
    if (vp && vp.canvasW > 0) {
      const nsPerPx = (vp.timeEnd - vp.timeStart) / vp.canvasW
      this._opts.onHoverTimeChange?.(vp.timeStart + cx * nsPerPx)
    }

    if (this._dragging) {
      if (!vp) return
      const dx   = e.clientX - this._dragStartX
      const nsPerPx = (vp.timeEnd - vp.timeStart) / vp.canvasW
      const newStart = this._dragStartTime - dx * nsPerPx
      this._opts.onViewportChange?.({
        ...vp,
        timeStart: newStart,
        timeEnd:   newStart + (vp.timeEnd - vp.timeStart),
      })
      return
    }

    // Hover: detect STI marker and row
    const trace = this._opts.getTrace()
    const ropts = this._opts.getOptions?.()
    if (trace && vp && ropts) {
      const stiEv = hitTestSti(trace, vp, ropts, cx, cy)
      this._opts.onStiHover?.(stiEv || null)

      const row = hitTestRow(trace, vp, ropts, cx, cy)
      this._opts.onRowHover?.(row || null)
    }
  }

  _onMouseUp(e) {
    this._dragging = false
  }

  _onMouseLeave(e) {
    this._dragging = false
    this._opts.onHoverTimeChange?.(null)
  }

  _onDblClick(e) {
    const rect = this._canvas.getBoundingClientRect()
    const cy   = e.clientY - rect.top
    if (cy < RULER_H) {
      this._opts.onFitToWindow?.()
    }
  }

  _placeCursor(t) {
    // Find next empty slot; if all full, replace the oldest (index 0).
    const cursors = [...this._cursors]
    let placed = false
    // Check if clicking near an existing cursor (within some px) → remove it
    const vp = this._opts.getViewport()
    if (vp) {
      const nsPerPx = (vp.timeEnd - vp.timeStart) / vp.canvasW
      const snapNs  = 5 * nsPerPx
      for (let i = 0; i < cursors.length; i++) {
        if (cursors[i] !== null && Math.abs(cursors[i] - t) < snapNs) {
          cursors[i] = null
          placed = true
          break
        }
      }
    }
    if (!placed) {
      // Find first empty slot
      const emptyIdx = cursors.findIndex(c => c === null)
      if (emptyIdx !== -1) {
        cursors[emptyIdx] = t
      } else {
        // Shift left, add at end
        cursors.shift()
        cursors.push(t)
      }
    }
    this._cursors = cursors
    this._opts.onCursorsChange?.(cursors)
  }
}
