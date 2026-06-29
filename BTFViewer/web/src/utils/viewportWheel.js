/** Shared timeline viewport mutations for wheel input (CPU load panel, etc.). */

/** Ruler band height in horizontal layout (matches TimelineRenderer.RULER_H). */
export const WHEEL_RULER_H = 28

/**
 * Wheel/trackpad deltas for pan classification (desktop _wheel_pan_deltas parity).
 * @returns {{ dx: number, dy: number, lineMode: boolean }}
 */
export function wheelPanDeltas(e) {
  let dx = e.deltaX
  let dy = e.deltaY
  const lineMode = e.deltaMode === 1

  if (e.deltaMode === 0) {
    const wdy = e.wheelDeltaY
    const wdx = e.wheelDeltaX
    if (dy === 0 && typeof wdy === 'number' && wdy !== 0) {
      dy = -wdy / 3
    }
    if (dx === 0 && typeof wdx === 'number' && wdx !== 0) {
      dx = -wdx / 3
    }
  }

  if (e.deltaMode === 1) {
    dx *= 16
    dy *= 16
  } else if (e.deltaMode === 2) {
    dx *= 100
    dy *= 100
  }
  return { dx, dy, lineMode }
}

/** True when the physical swipe is more vertical than horizontal. */
export function physicalVerticalDominant(e, dx, dy) {
  if (e.deltaMode === 0) {
    const wdy = e.wheelDeltaY
    const wdx = e.wheelDeltaX
    if (typeof wdy === 'number' && typeof wdx === 'number' && (wdy !== 0 || wdx !== 0)) {
      return Math.abs(wdy) >= Math.abs(wdx)
    }
  }
  return Math.abs(dy) >= Math.abs(dx)
}

function pickDelta(primary, alternate) {
  return primary !== 0 ? primary : alternate
}

/** Map pixel deltas onto time-axis and orth-axis magnitudes (desktop parity). */
export function mappedWheelDeltas(horizontal, shift, dx, dy) {
  if (horizontal) {
    return shift ? { time: dy, orth: dx } : { time: dx, orth: dy }
  }
  return shift ? { time: dx, orth: dy } : { time: dy, orth: dx }
}

function orthPlan(orthDelta) {
  return { doTime: false, timeDelta: 0, doOrth: orthDelta !== 0, orthDelta }
}

function timePlan(timeDelta) {
  return { doTime: timeDelta !== 0, timeDelta, doOrth: false, orthDelta: 0 }
}

function planFromPhysical(horizontal, shift, physVert, dx, dy) {
  if (horizontal) {
    if (!shift) {
      return physVert ? orthPlan(pickDelta(dy, dx)) : timePlan(pickDelta(dx, dy))
    }
    return physVert ? timePlan(pickDelta(dy, dx)) : orthPlan(pickDelta(dx, dy))
  }
  if (!shift) {
    return physVert ? timePlan(pickDelta(dy, dx)) : orthPlan(pickDelta(dx, dy))
  }
  return physVert ? orthPlan(pickDelta(dy, dx)) : timePlan(pickDelta(dx, dy))
}

/**
 * Classify wheel input into time-axis vs orthogonal-axis pans.
 *
 * Classify by *physical* swipe direction, then map to time or orth per orientation
 * and Shift. When the browser zeros one pixel delta, fall back to the alternate
 * axis so row/column scroll still works without Shift.
 *
 * @param {WheelEvent} e
 * @param {boolean} horizontal  true = task view (time on X)
 * @param {{ atTraceStart?: boolean, atTraceEnd?: boolean }} opts
 * @returns {{ doTime: boolean, timeDelta: number, doOrth: boolean, orthDelta: number }}
 */
export function wheelGesturePlan(e, horizontal, opts = {}) {
  const { dx, dy } = wheelPanDeltas(e)
  if (dx === 0 && dy === 0) {
    return { doTime: false, timeDelta: 0, doOrth: false, orthDelta: 0 }
  }

  const mapped = mappedWheelDeltas(horizontal, e.shiftKey, dx, dy)
  const { atTraceStart = false, atTraceEnd = false } = opts
  const mt = Math.abs(mapped.time)
  const mo = Math.abs(mapped.orth)
  if ((atTraceStart || atTraceEnd) && mo > 0 && mt > 0 && mo >= mt * 0.7) {
    return orthPlan(mapped.orth)
  }

  return planFromPhysical(horizontal, e.shiftKey, physicalVerticalDominant(e, dx, dy), dx, dy)
}

/**
 * Apply a wheel gesture plan to a timeline viewport (InteractionHandler parity).
 * Time clamping is omitted — callers clamp against trace bounds when needed.
 */
export function applyWheelPlanToViewport(plan, vp, horizontal, rulerH = WHEEL_RULER_H) {
  let next = { ...vp }
  if (plan.doTime && plan.timeDelta !== 0) {
    const span = next.timeEnd - next.timeStart
    if (horizontal) {
      const nsPerPx = span / Math.max(1, next.canvasW)
      const deltaNs = plan.timeDelta * nsPerPx
      next = { ...next, timeStart: next.timeStart - deltaNs, timeEnd: next.timeEnd - deltaNs }
    } else {
      const bodyH = Math.max(1, (next.canvasH || 1) - rulerH)
      const nsPerPx = span / bodyH
      const deltaNs = plan.timeDelta * nsPerPx
      next = { ...next, timeStart: next.timeStart + deltaNs, timeEnd: next.timeEnd + deltaNs }
    }
  }
  if (plan.doOrth && plan.orthDelta !== 0) {
    if (horizontal) {
      next = { ...next, scrollY: Math.max(0, (next.scrollY || 0) + plan.orthDelta) }
    } else {
      next = { ...next, scrollX: Math.max(0, (next.scrollX || 0) + plan.orthDelta) }
    }
  }
  return next
}

/** Clamp row scroll like TimelinePanel.onViewportChange. */
export function clampViewportScrollY(vp, totalRowHeight, rulerH = WHEEL_RULER_H) {
  const maxScrollY = Math.max(0, totalRowHeight - ((vp.canvasH || 0) - rulerH))
  return { ...vp, scrollY: Math.max(0, Math.min(vp.scrollY || 0, maxScrollY)) }
}

/** Clamp column scroll like TimelinePanel.onViewportChange (vertical orientation). */
export function clampViewportScrollX(vp, totalColumnWidth) {
  const maxScrollX = Math.max(0, totalColumnWidth - (vp.canvasW || 0))
  return { ...vp, scrollX: Math.max(0, Math.min(vp.scrollX || 0, maxScrollX)) }
}

export function clampPan(trace, newStart, newEnd) {
  const span = newEnd - newStart
  const lo = trace.timeMin >= 0 ? Math.max(0, trace.timeMin) : trace.timeMin
  const hi = trace.timeMax
  const range = hi - lo
  if (range <= 0) return { timeStart: lo, timeEnd: hi }
  if (span >= range) return { timeStart: lo, timeEnd: hi }
  if (newStart < lo) return { timeStart: lo, timeEnd: lo + span }
  if (newEnd > hi) return { timeStart: hi - span, timeEnd: hi }
  return { timeStart: newStart, timeEnd: newEnd }
}

export function applyZoomAroundPlotX(vp, trace, plotX, plotWidth, factor, minSpan = 1) {
  const { timeStart, timeEnd } = vp
  const span = timeEnd - timeStart
  const w = Math.max(1, plotWidth)
  const pivotT = timeStart + (plotX / w) * span

  let newSpan = span * factor
  const lo = trace.timeMin >= 0 ? Math.max(0, trace.timeMin) : trace.timeMin
  const maxSpan = Math.max(1, trace.timeMax - lo)
  newSpan = Math.min(newSpan, maxSpan)
  newSpan = Math.max(minSpan, newSpan)

  const newStart = pivotT - (plotX / w) * newSpan
  const { timeStart: s, timeEnd: e } = clampPan(trace, newStart, newStart + newSpan)
  return { ...vp, timeStart: s, timeEnd: e }
}

export function applyZoomAroundPlotY(vp, trace, plotY, plotHeight, headerH, factor, minSpan = 1) {
  const { timeStart, timeEnd } = vp
  const bodyH = Math.max(1, plotHeight - headerH)
  const span = timeEnd - timeStart
  const pivotT = timeStart + (Math.max(0, plotY - headerH) / bodyH) * span

  let newSpan = span * factor
  const lo = trace.timeMin >= 0 ? Math.max(0, trace.timeMin) : trace.timeMin
  const maxSpan = Math.max(1, trace.timeMax - lo)
  newSpan = Math.min(newSpan, maxSpan)
  newSpan = Math.max(minSpan, newSpan)

  const relPos = Math.max(0, plotY - headerH) / bodyH
  const newStart = pivotT - relPos * newSpan
  const { timeStart: s, timeEnd: e } = clampPan(trace, newStart, newStart + newSpan)
  return { ...vp, timeStart: s, timeEnd: e }
}

export function applyPanPlotX(vp, trace, deltaPx, plotWidth) {
  const span = vp.timeEnd - vp.timeStart
  const deltaNs = deltaPx * span / Math.max(1, plotWidth)
  const { timeStart: s, timeEnd: e } = clampPan(trace, vp.timeStart - deltaNs, vp.timeEnd - deltaNs)
  return { ...vp, timeStart: s, timeEnd: e }
}

export function applyPanPlotY(vp, trace, deltaPx, plotHeight, headerH) {
  const bodyH = Math.max(1, plotHeight - headerH)
  const span = vp.timeEnd - vp.timeStart
  const deltaNs = deltaPx * span / bodyH
  const { timeStart: s, timeEnd: e } = clampPan(trace, vp.timeStart + deltaNs, vp.timeEnd + deltaNs)
  return { ...vp, timeStart: s, timeEnd: e }
}
