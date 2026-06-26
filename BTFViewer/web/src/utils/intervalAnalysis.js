/**
 * Pair interval_start / interval_stop STI events into measurable spans.
 */
import { formatTime } from './timeFormat.js'
import { lighterColor } from './colors.js'
import { bisectLeft } from './bisect.js'

export const INTERVAL_START_CHANNELS = new Set(['interval_start'])
export const INTERVAL_STOP_CHANNELS = new Set(['interval_stop'])

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

/** Dark/light shades of the interval base colour for start/stop tick lines. */
export function intervalStripeColors(base, darkMode) {
  return {
    dark: lighterColor(base, darkMode ? 0.58 : 0.70),
    light: lighterColor(base, darkMode ? 1.22 : 1.12),
  }
}

/** Drop instances fully covered by a longer one (time-domain containment). O(n log n). */
export function cullNestedIntervalInstances(instances) {
  if (!instances?.length || instances.length <= 1) return instances || []
  const ordered = [...instances].sort((a, b) => {
    if (a.startNs !== b.startNs) return a.startNs - b.startNs
    return b.stopNs - a.stopNs
  })
  const kept = []
  for (const inst of ordered) {
    while (kept.length
           && kept[kept.length - 1].startNs >= inst.startNs
           && kept[kept.length - 1].stopNs <= inst.stopNs) {
      kept.pop()
    }
    const last = kept[kept.length - 1]
    if (last && inst.startNs >= last.startNs && inst.stopNs <= last.stopNs) continue
    kept.push(inst)
  }
  return kept
}

function isStart(ev) {
  return INTERVAL_START_CHANNELS.has(ev.target)
}

function isStop(ev) {
  return INTERVAL_STOP_CHANNELS.has(ev.target)
}

const INTERVAL_TID_RE = /^(\S+)\s+tid:((?:0[xX][0-9a-fA-F]+|\d+))\s*$/i

function parseIntervalIntToken(s) {
  const t = s.trim()
  if (/^0[xX]/.test(t)) return parseInt(t, 16)
  return parseInt(t, 10)
}

function formatIntervalTidDisplay(token, value) {
  if (/^0[xX]/.test(token)) return `0x${value.toString(16).toUpperCase()}`
  return String(value)
}

/** @typedef {{ intervalId: string, taskId: string|null, pairingKey: string }} ParsedIntervalNote */

/**
 * Parse interval STI note: legacy `{id}` or `{id} tid:{task_id}` (decimal or 0x hex).
 * @returns {ParsedIntervalNote}
 */
export function parseIntervalNote(note) {
  const raw = (note != null && note !== '') ? String(note).trim() : '0'
  const m = INTERVAL_TID_RE.exec(raw)
  if (m) {
    const tidVal = parseIntervalIntToken(m[2])
    return {
      intervalId: m[1],
      taskId: formatIntervalTidDisplay(m[2], tidVal),
      pairingKey: `${m[1]}\0tid:${tidVal}`,
    }
  }
  return { intervalId: raw, taskId: null, pairingKey: raw }
}

/** Stack key for start/stop pairing. */
function intervalPairingKey(ev) {
  return parseIntervalNote(ev.note).pairingKey
}

/** Row / stats bucket id (interval id when tid present, else full legacy note). */
function intervalDisplayId(ev) {
  const parsed = parseIntervalNote(ev.note)
  return parsed.taskId != null ? parsed.intervalId : parsed.pairingKey
}

/** @returns {{ intervalInstances, intervalIds, intervalInstancesById, intervalInstancesCulledById, unmatchedStarts }} */
export function buildIntervalData(stiEvents) {
  const open = new Map()
  const intervalInstances = []
  let unmatchedStarts = 0

  const sorted = (stiEvents || [])
    .filter(ev => isStart(ev) || isStop(ev))
    .sort((a, b) => a.time - b.time || (isStart(a) ? 0 : 1))

  for (const ev of sorted) {
    const pairKey = intervalPairingKey(ev)
    const displayId = intervalDisplayId(ev)
    const parsed = parseIntervalNote(ev.note)
    if (isStart(ev)) {
      if (!open.has(pairKey)) open.set(pairKey, [])
      open.get(pairKey).push(ev)
    } else {
      const stack = open.get(pairKey)
      if (!stack?.length) continue
      const startEv = stack.pop()
      if (ev.time > startEv.time) {
        intervalInstances.push({
          id: displayId,
          taskId: parsed.taskId,
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

  const intervalInstancesCulledById = new Map()
  for (const [id, list] of intervalInstancesById) {
    intervalInstancesCulledById.set(id, cullNestedIntervalInstances(list))
  }

  const intervalIds = [...intervalInstancesById.keys()].sort((a, b) => {
    const na = parseInt(a, 10)
    const nb = parseInt(b, 10)
    if (Number.isFinite(na) && Number.isFinite(nb) && na !== nb) return na - nb
    return a.localeCompare(b)
  })

  return { intervalInstances, intervalIds, intervalInstancesById, intervalInstancesCulledById, unmatchedStarts }
}

/** Per-id sorted marker events for O(log n) viewport clipping. */
export function buildIntervalMarkerIndex(stiEvents) {
  const byId = new Map()
  for (const ev of stiEvents || []) {
    if (!isStart(ev) && !isStop(ev)) continue
    const id = intervalDisplayId(ev)
    if (!byId.has(id)) byId.set(id, [])
    byId.get(id).push({ timeNs: ev.time, isStart: isStart(ev) })
  }
  for (const events of byId.values()) {
    events.sort((a, b) => a.timeNs - b.timeNs || (a.isStart ? 0 : 1))
  }
  return byId
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

/** Per-instance detail rows for HTML/CSV export. */
export function intervalInstanceDetailRows(trace, lo, hi, limit = 200) {
  const scale = trace?.timeScale || 'ns'
  const byId = trace?.intervalInstancesById
  if (!byId?.size) return []
  const rows = []
  for (const id of trace.intervalIds || []) {
    for (const inst of byId.get(id) || []) {
      if (!intervalOverlapsRange(inst, lo, hi)) continue
      rows.push({
        id,
        label: `Interval ${id}`,
        taskId: inst.taskId ?? '',
        startNs: inst.startNs,
        stopNs: inst.stopNs,
        start: formatTime(inst.startNs, scale),
        stop: formatTime(inst.stopNs, scale),
        duration: formatTime(inst.durationNs, scale),
        durationNs: inst.durationNs,
        startCore: inst.startCore || '',
        stopCore: inst.stopCore || '',
      })
    }
  }
  rows.sort((a, b) => b.durationNs - a.durationNs || a.startNs - b.startNs)
  return limit > 0 ? rows.slice(0, limit) : rows
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

/** Instances for timeline drawing (pre-culled list when available). */
export function intervalInstancesForDraw(trace, intervalId) {
  const id = String(intervalId)
  const culledMap = trace?.intervalInstancesCulledById
  if (culledMap?.has(id)) {
    return { instances: culledMap.get(id) || [], preCulled: true }
  }
  return { instances: trace?.intervalInstancesById?.get(id) || [], preCulled: false }
}

/** Visible interval instances for timeline drawing (time overlap with viewport). */
export function visibleIntervalInstances(instances, timeStart, timeEnd, preCulled = false) {
  if (!instances?.length) return []
  const visible = []
  for (const inst of instances) {
    if (inst.startNs >= timeEnd) break
    if (inst.stopNs <= timeStart) continue
    visible.push(inst)
  }
  return preCulled ? visible : cullNestedIntervalInstances(visible)
}

/** Raw interval_start / interval_stop marker events for one id in the viewport. */
export function visibleIntervalMarkerEvents(trace, intervalId, timeStart, timeEnd) {
  const id = String(intervalId)
  let byId = trace.intervalMarkerById
  if (!byId) {
    if (!trace.stiEventsByTarget) return []
    byId = buildIntervalMarkerIndex(
      [...INTERVAL_START_CHANNELS, ...INTERVAL_STOP_CHANNELS]
        .flatMap(ch => trace.stiEventsByTarget.get(ch) || []),
    )
  }
  const events = byId.get(id)
  if (!events?.length) return []
  const times = events.map(e => e.timeNs)
  const lo = Math.max(0, bisectLeft(times, timeStart))
  const hi = bisectLeft(times, timeEnd)
  return events.slice(lo, hi)
}
