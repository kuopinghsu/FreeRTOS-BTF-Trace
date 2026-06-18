/**
 * Pair interval_start / interval_stop STI events into measurable spans.
 */
import { formatTime } from './timeFormat.js'
import { lighterColor } from './colors.js'

export const INTERVAL_START_CHANNELS = new Set(['interval_start', 'start_intval'])
export const INTERVAL_STOP_CHANNELS = new Set(['interval_stop', 'stop_intval'])

const INTERVAL_COLORS = [
  '#E74C3C', '#2ECC71', '#F39C12', '#3498DB', '#9B59B6',
  '#1ABC9C', '#E91E63', '#F1C40F', '#00BCD4', '#FF5722',
]

export function isIntervalMarkerChannel(name) {
  return INTERVAL_START_CHANNELS.has(name) || INTERVAL_STOP_CHANNELS.has(name)
}

export function intervalColor(id) {
  const n = parseInt(id, 10)
  const idx = Number.isFinite(n) ? Math.abs(n) % INTERVAL_COLORS.length : 0
  return INTERVAL_COLORS[idx]
}

/** Alternating dark/light shades of the interval base colour (start = dark stripe). */
export function intervalStripeColors(base, darkMode) {
  return {
    dark: lighterColor(base, darkMode ? 0.58 : 0.70),
    light: lighterColor(base, darkMode ? 1.22 : 1.12),
  }
}

const INTERVAL_MAX_STRIPES = 12
const INTERVAL_MIN_PX = 0.5
const INTERVAL_STRIPE_PERIOD = 8 // trace time units (~4px at 2 units/px)

export function intervalRowStripeWidthPx(visibleSpanPx) {
  let sw = 4
  if (visibleSpanPx > 0 && visibleSpanPx / sw > INTERVAL_MAX_STRIPES) {
    sw = Math.max(2, visibleSpanPx / INTERVAL_MAX_STRIPES)
  }
  return sw
}

export function intervalStripeWidthPx(clipWidthPx) {
  return intervalRowStripeWidthPx(clipWidthPx)
}

/** Drop instances fully covered by a longer one (time-domain containment). */
export function cullNestedIntervalInstances(instances) {
  if (!instances?.length || instances.length <= 1) return instances || []
  const byDuration = [...instances].sort((a, b) => {
    const da = a.stopNs - a.startNs
    const db = b.stopNs - b.startNs
    if (db !== da) return db - da
    if (a.startNs !== b.startNs) return a.startNs - b.startNs
    return b.stopNs - a.stopNs
  })
  const kept = []
  for (const inst of byDuration) {
    if (kept.some(k => k.startNs <= inst.startNs && k.stopNs >= inst.stopNs)) continue
    kept.push(inst)
  }
  kept.sort((a, b) => a.startNs - b.startNs)
  return kept
}

/** Fill an interval bar with vertical dark/light stripes (time-anchored phase). */
export function fillIntervalStripedBar(ctx, x, y, w, h, baseColor, darkMode, startNs, stopNs, timeStart, pxPerNs) {
  if (w < INTERVAL_MIN_PX || h <= 0 || pxPerNs <= 0) return
  const { dark, light } = intervalStripeColors(baseColor, darkMode)
  const basePeriod = INTERVAL_STRIPE_PERIOD
  const spanT = stopNs - startNs
  if (spanT <= 0) return
  if (w < 2) {
    ctx.fillStyle = dark
    ctx.fillRect(x, y, w, h)
    return
  }
  const xEnd = x + w
  const tClipLo = Math.max(startNs, timeStart + x / pxPerNs)
  const tClipHi = Math.min(stopNs, timeStart + xEnd / pxPerNs)
  if (tClipHi <= tClipLo) return
  let paintPeriod = basePeriod
  if (spanT / basePeriod > INTERVAL_MAX_STRIPES) {
    paintPeriod = spanT / INTERVAL_MAX_STRIPES
  }
  let i0 = Math.max(0, Math.floor((tClipLo - startNs) / paintPeriod))
  let t = startNs + i0 * paintPeriod
  while (t < tClipHi - 1e-9) {
    const segEndT = Math.min(t + paintPeriod, tClipHi)
    const loT = Math.max(t, tClipLo)
    const hiT = Math.min(segEndT, tClipHi)
    if (hiT > loT + 1e-9) {
      const idx = Math.floor((t - startNs) / basePeriod) % 2
      const sx = (loT - timeStart) * pxPerNs
      const sx2 = (hiT - timeStart) * pxPerNs
      const clipLo = Math.max(sx, x)
      const clipHi = Math.min(sx2, xEnd)
      if (clipHi > clipLo + 0.01) {
        ctx.fillStyle = (idx % 2) === 0 ? dark : light
        ctx.fillRect(clipLo, y, clipHi - clipLo, h)
      }
    }
    t += paintPeriod
  }
}

function isStart(ev) {
  return INTERVAL_START_CHANNELS.has(ev.target)
}

function isStop(ev) {
  return INTERVAL_STOP_CHANNELS.has(ev.target)
}

function intervalId(ev) {
  return (ev.note != null && ev.note !== '') ? String(ev.note) : '0'
}

/** @returns {{ intervalInstances, intervalIds, intervalInstancesById, unmatchedStarts }} */
export function buildIntervalData(stiEvents) {
  const open = new Map()
  const intervalInstances = []
  let unmatchedStarts = 0

  const sorted = (stiEvents || [])
    .filter(ev => isStart(ev) || isStop(ev))
    .sort((a, b) => a.time - b.time || (isStart(a) ? 0 : 1))

  for (const ev of sorted) {
    const id = intervalId(ev)
    if (isStart(ev)) {
      if (!open.has(id)) open.set(id, [])
      open.get(id).push(ev)
    } else {
      const stack = open.get(id)
      if (!stack?.length) continue
      const startEv = stack.pop()
      if (ev.time > startEv.time) {
        intervalInstances.push({
          id,
          startNs: startEv.time,
          stopNs: ev.time,
          durationNs: ev.time - startEv.time,
          startCore: startEv.core || '',
          stopCore: ev.core || '',
        })
      }
    }
  }

  for (const stack of open.values()) unmatchedStarts += stack.length

  const intervalInstancesById = new Map()
  for (const inst of intervalInstances) {
    if (!intervalInstancesById.has(inst.id)) intervalInstancesById.set(inst.id, [])
    intervalInstancesById.get(inst.id).push(inst)
  }
  for (const list of intervalInstancesById.values()) {
    list.sort((a, b) => a.startNs - b.startNs || a.stopNs - b.stopNs)
  }

  const intervalIds = [...intervalInstancesById.keys()].sort((a, b) => {
    const na = parseInt(a, 10)
    const nb = parseInt(b, 10)
    if (Number.isFinite(na) && Number.isFinite(nb) && na !== nb) return na - nb
    return a.localeCompare(b)
  })

  return { intervalInstances, intervalIds, intervalInstancesById, unmatchedStarts }
}

export function intervalOverlapsRange(inst, lo, hi) {
  if (lo == null || hi == null) return true
  return inst.stopNs > lo && inst.startNs < hi
}

function percentile(sorted, p) {
  if (!sorted.length) return 0
  const idx = Math.min(sorted.length - 1, Math.max(0, Math.ceil(p * sorted.length) - 1))
  return sorted[idx]
}

/**
 * Per-interval-id statistics rows.
 * @returns {Array<{id, label, count, minNs, avgNs, maxNs, p95Ns, min, avg, max, p95}>}
 */
export function intervalStatsRows(trace, lo, hi) {
  const scale = trace?.timeScale || 'ns'
  const byId = trace?.intervalInstancesById
  if (!byId?.size) return []

  const rows = []
  for (const id of trace.intervalIds || []) {
    const samples = (byId.get(id) || [])
      .filter(inst => intervalOverlapsRange(inst, lo, hi))
      .map(inst => inst.durationNs)
    if (!samples.length) continue
    const sorted = [...samples].sort((a, b) => a - b)
    const total = samples.reduce((a, b) => a + b, 0)
    const count = samples.length
    const min = sorted[0]
    const max = sorted[sorted.length - 1]
    const avg = Math.round(total / count)
    const p95 = percentile(sorted, 0.95)
    rows.push({
      id,
      label: `Interval ${id}`,
      count,
      minNs: min,
      avgNs: avg,
      maxNs: max,
      p95Ns: p95,
      min: formatTime(min, scale),
      avg: formatTime(avg, scale),
      max: formatTime(max, scale),
      p95: formatTime(p95, scale),
    })
  }
  rows.sort((a, b) => {
    const na = parseInt(a.id, 10)
    const nb = parseInt(b.id, 10)
    if (Number.isFinite(na) && Number.isFinite(nb) && na !== nb) return na - nb
    return a.id.localeCompare(b.id)
  })
  return rows
}

/** Plot points: x = stop time, y = duration. */
export function intervalPlotPoints(trace, id, lo, hi) {
  const instances = trace?.intervalInstancesById?.get(id) || []
  return instances
    .filter(inst => intervalOverlapsRange(inst, lo, hi))
    .map(inst => ({
      xNs: inst.stopNs,
      yValue: inst.durationNs,
      payload: inst,
    }))
}

/** Visible interval instances for timeline drawing (time overlap with viewport). */
export function visibleIntervalInstances(instances, timeStart, timeEnd) {
  if (!instances?.length) return []
  const visible = instances.filter(inst => inst.stopNs > timeStart && inst.startNs < timeEnd)
  return cullNestedIntervalInstances(visible)
}
