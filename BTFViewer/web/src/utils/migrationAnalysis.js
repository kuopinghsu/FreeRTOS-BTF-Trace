/**
 * Core migration analysis (parity with desktop btf_viewer.py).
 */

import { bisectLeft, bisectRight } from './bisect.js'
import { parseTaskName, taskLabelForMergeKey, taskReprGet, isIdleTaskName, taskMergeKey, taskDisplayName } from './colors.js'
import { computeFindHits } from './findAnalysis.js'
import { blockingTimeSamples, schedulingStats } from './statsAnalysis.js'
import { segFullyInRange, segOverlapsRange } from './statsRange.js'
import { formatMigrationGapTime, formatTime } from './timeFormat.js'
import { prepareUxEvents } from './uxExplore.js'
import { classifyLoadBalance, loadBalanceMetrics } from './loadBalanceGauge.js'

const NS_PER_SCALE = { ns: 1e9, us: 1e6, ms: 1e3, s: 1 }

/** Distinct cores with on-CPU slices or migrations in scope. */
export function coresInScope(segs, migs, lo, hi) {
  const cores = new Set()
  for (const s of segs) {
    if (lo != null && hi != null) {
      if (!segOverlapsRange(s, lo, hi)) continue
    }
    cores.add(s.core)
  }
  if (!cores.size && migs?.length) {
    for (const m of migs) {
      cores.add(m.fromCore)
      cores.add(m.toCore)
    }
  }
  return cores
}

/** Visible span ≥ this fraction of the trace counts as Fit / Full view. */
export const INSPECTOR_FULL_VIEW_RATIO = 0.92

export function inspectorViewportIsFull(lo, hi, timeMin, timeMax, fitMode = false) {
  if (fitMode || lo == null || hi == null) return true
  const tlo = Number(timeMin)
  const thi = Number(timeMax)
  const span = Math.max(thi - tlo, 1)
  return (Number(hi) - Number(lo)) / span >= INSPECTOR_FULL_VIEW_RATIO
}

/** Banner for heatmap Full view vs Viewport view (distribution-chart colors). */
export function inspectorViewportBanner(lo, hi, timeMin, timeMax, timeScale, formatTimeFn, fitMode = false) {
  const tlo = Number.isFinite(Number(timeMin)) ? Number(timeMin) : 0
  const thi = Number.isFinite(Number(timeMax)) ? Number(timeMax) : 0
  let full = inspectorViewportIsFull(lo, hi, tlo, thi, fitMode)
  let a = full ? tlo : Number(lo)
  let b = full ? thi : Number(hi)
  if (!Number.isFinite(a) || !Number.isFinite(b) || b <= a) {
    a = tlo
    b = thi
    full = true
  }
  const fmt = formatTimeFn || formatTime
  const detail = `${fmt(a, timeScale)} … ${fmt(b, timeScale)} (${fmt(b - a, timeScale)})`
  return {
    scoped: !full,
    badge: full ? 'Full view' : 'Viewport view',
    detail,
  }
}

function clipSegmentsForScope(segs, lo, hi) {
  const clipped = []
  for (const s of segs) {
    let segLo
    let segHi
    if (lo != null && hi != null) {
      if (!segOverlapsRange(s, lo, hi)) continue
      segLo = Math.max(s.start, lo)
      segHi = Math.min(s.end, hi)
    } else {
      segLo = s.start
      segHi = s.end
    }
    if (segLo <= segHi) clipped.push([segLo, segHi])
  }
  clipped.sort((a, b) => a[0] - b[0])
  return clipped
}

/** TICK events in scope while this task was on-CPU (trace time units). */
export function tickCountForTask(segs, tickTimes, lo, hi) {
  const clipped = clipSegmentsForScope(segs, lo, hi)
  if (!clipped.length || !tickTimes?.length) return 0
  let count = 0
  let i = 0
  const n = clipped.length
  for (const t of tickTimes) {
    if (lo != null && hi != null && (t < lo || t > hi)) continue
    while (i + 1 < n && clipped[i + 1][0] <= t) i++
    const [segLo, segHi] = clipped[i]
    if (segLo <= t && t <= segHi) count++
  }
  return count
}

export function coreDwellSamples(segs, lo, hi) {
  const samples = []
  for (const s of segs) {
    let ovLo
    let ovHi
    if (lo != null && hi != null) {
      if (!segOverlapsRange(s, lo, hi)) continue
      ovLo = Math.max(s.start, lo)
      ovHi = Math.min(s.end, hi)
    } else {
      ovLo = s.start
      ovHi = s.end
    }
    const dur = Math.max(0, ovHi - ovLo)
    if (dur > 0) samples.push(dur)
  }
  return samples
}

export function formatMigrationRate(nMig, taskActive, tickCount, timeScale) {
  if (nMig <= 0) return { label: '-', ratePerS: -1 }
  const div = NS_PER_SCALE[timeScale] || 1e9
  let perS = -1
  let perSLabel = null
  if (taskActive > 0) {
    const activeS = taskActive / div
    if (activeS > 0) {
      perS = nMig / activeS
      perSLabel = `${perS.toFixed(2)}/s`
    }
  }
  if (tickCount > 0) {
    const tickLabel = `${(nMig / tickCount).toFixed(3)}/tick`
    if (perSLabel) return { label: `${perSLabel} · ${tickLabel}`, ratePerS: perS }
    return { label: tickLabel, ratePerS: perS }
  }
  if (perSLabel) return { label: perSLabel, ratePerS: perS }
  return { label: '-', ratePerS: -1 }
}

export const MIGRATION_PING_PONG_WINDOW = 1000
export const MIGRATION_STI_WINDOW = 500
/** Short-dwell threshold: 1 ms in the trace time unit. */
export const CORRIDOR_SHORT_DWELL_MS = 1
export const CORRIDOR_HANDOFF_HATCH_PCT = 15
export const CORRIDOR_TOP_N_OPTIONS = Object.freeze([5, 10, 25, 0])
export const CORRIDOR_SORT_KEYS = Object.freeze([
  'rate', 'pingpong', 'dwell', 'handoff', 'share',
  'count', 'net', 'label',
])
/** Path table: Core path first, then Sort by metrics (compact headers). */
export const CORRIDOR_TREE_COLS = Object.freeze([
  { key: 'label', label: 'Core path', tip: 'Sort by Core path' },
  { key: 'rate', label: 'Rate', tip: 'Sort by Migration rate' },
  { key: 'count', label: 'Count', tip: 'Sort by Migrations' },
  { key: 'pingpong', label: 'Ping', tip: 'Sort by Ping-pong' },
  { key: 'dwell', label: 'Dwell', tip: 'Sort by Short dwell' },
  { key: 'handoff', label: 'Handoff', tip: 'Sort by Handoff' },
  { key: 'net', label: 'Net', tip: 'Sort by Net flow' },
  { key: 'share', label: 'Share', tip: 'Sort by Task share' },
])
/** Inspector workspace panes: Core path | heatmap | Topology (1:2:1). */
export const CI_SPLIT_RATIO = Object.freeze([1, 2, 1])
export const CI_SPLIT_PANE_MIN = 160
export const CI_TREE_COL_MIN = 40
export const CI_TREE_NAME_W = 140
export const CI_TREE_NUM_W = 56

export function corridorTreeColDefaults() {
  return CORRIDOR_TREE_COLS.map((c) => (
    c.key === 'label' ? CI_TREE_NAME_W : CI_TREE_NUM_W
  ))
}

export function parseIntCsv(text, n, fallback, lo = 1, hi = 8000) {
  const fb = Array.from(fallback || [])
  if (text == null || String(text).trim() === '') return fb
  const parts = String(text).split(',').map((p) => p.trim()).filter(Boolean)
  if (parts.length !== Number(n)) return fb
  const vals = parts.map((p) => {
    const v = Number.parseInt(p, 10)
    if (!Number.isFinite(v)) return null
    return Math.max(lo, Math.min(hi, v))
  })
  if (vals.some((v) => v == null)) return fb
  return vals
}

export function formatIntCsv(vals) {
  return (vals || []).map((v) => String(Math.trunc(Number(v) || 0))).join(',')
}

export function scaleSplitSizes(sizes, total, mins) {
  const n = 3
  const floor = (mins && mins.length === n)
    ? mins.map((m) => Math.trunc(Number(m) || CI_SPLIT_PANE_MIN))
    : [CI_SPLIT_PANE_MIN, CI_SPLIT_PANE_MIN, CI_SPLIT_PANE_MIN]
  const src = (sizes && sizes.length === n) ? sizes : CI_SPLIT_RATIO
  const raw = src.map((v) => Math.max(1, Math.trunc(Number(v) || 1)))
  const width = Math.max(Math.trunc(Number(total) || 0), floor.reduce((a, b) => a + b, 0))
  const ssum = raw.reduce((a, b) => a + b, 0) || 1
  const out = raw.map((v, i) => Math.max(floor[i], Math.trunc(width * v / ssum)))
  out[1] = Math.max(floor[1], out[1] + (width - out.reduce((a, b) => a + b, 0)))
  return out
}

export function corridorTreeCell(row, key, kind = 'corridor') {
  if (key === 'label') return String(row?.label || '')
  if (kind === 'group') {
    if (key === 'count') return String(row?.count || 0)
    return '—'
  }
  if (kind === 'task') {
    if (key === 'count') return String(row?.count || 0)
    if (key === 'handoff') {
      return `${Number(row?.handoffPct ?? row?.bouncePct ?? 0).toFixed(0)}%`
    }
    if (key === 'share') return `${Number(row?.sharePct || 0).toFixed(0)}%`
    return '—'
  }
  if (key === 'rate') return `${Number(row?.ratePerS || 0).toFixed(1)}/s`
  if (key === 'count') return String(row?.count || 0)
  if (key === 'pingpong') return `${Number(row?.pingPongPct || 0).toFixed(0)}%`
  if (key === 'dwell') return `${Number(row?.shortDwellShare || 0).toFixed(0)}%`
  if (key === 'handoff') {
    return `${Number(row?.handoffPct ?? row?.bouncePct ?? 0).toFixed(0)}%`
  }
  if (key === 'net') {
    const net = Number(row?.net || 0)
    if (net > 0) return `+${net} ▲`
    if (net < 0) return `${net} ▼`
    return '0'
  }
  if (key === 'share') {
    const task = row?.primaryTask
    if (!task) return '—'
    return `${Number(task.sharePct || 0).toFixed(0)}%`
  }
  return '—'
}

export function corridorShortDwellThreshold(timeScale) {
  const nsPer = NS_PER_SCALE[timeScale] || 1e9
  return Math.max(1, Math.round((nsPer / 1000) * CORRIDOR_SHORT_DWELL_MS))
}

function isIdleOrTick(raw) {
  const { name } = parseTaskName(raw)
  return /^idle/i.test(name) || name === 'TICK'
}

export function taskCoresUsed(trace, mergeKey) {
  const segs = trace.segByMergeKey?.get(mergeKey) || []
  return new Set(segs.map(s => s.core))
}

export function isMigratedTask(trace, mergeKey) {
  const mks = trace?.migratedMks
  if (mks?.size) return mks.has(mergeKey)
  if (trace?.migrationsByMk?.size) return trace.migrationsByMk.has(mergeKey)
  return taskCoresUsed(trace, mergeKey).size >= 2
}

/** Migrations with ns in [lo, hi] (inclusive). Uses migrationTimes bisect. */
export function migrationsInRange(trace, lo = null, hi = null) {
  const migs = trace?.migrations || []
  if (!migs.length || (lo == null && hi == null)) return migs
  const times = trace.migrationTimes
  if (!times || times.length !== migs.length) {
    return migs.filter(m => (lo == null || m.ns >= lo) && (hi == null || m.ns <= hi))
  }
  const i0 = lo == null ? 0 : bisectLeft(times, lo)
  const i1 = hi == null ? migs.length : bisectRight(times, hi)
  return migs.slice(i0, i1)
}

/** @returns {{ migrations: object[], migrationsByMk: Map<string, object[]> }} */
export function buildMigrationIndex(segByMergeKey) {
  const migrations = []
  const migrationsByMk = new Map()
  for (const [mk, segs] of segByMergeKey) {
    if (!segs || segs.length < 2) continue
    const raw = segs[0].task
    if (isIdleOrTick(raw)) continue
    for (let i = 1; i < segs.length; i++) {
      const prev = segs[i - 1]
      const nxt = segs[i]
      if (prev.core === nxt.core) continue
      const ev = {
        ns: prev.end,
        mergeKey: mk,
        fromCore: prev.core,
        toCore: nxt.core,
        gapNs: Math.max(0, nxt.start - prev.end),
      }
      migrations.push(ev)
      if (!migrationsByMk.has(mk)) migrationsByMk.set(mk, [])
      migrationsByMk.get(mk).push(ev)
    }
  }
  migrations.sort((a, b) => a.ns - b.ns)
  return {
    migrations,
    migrationsByMk,
    migrationTimes: migrations.map(m => m.ns),
  }
}

/** Full-trace snapshots for Statistics / heatmap (call once at parse/finalize). */
export function prepareFullTraceStats(trace) {
  if (!trace) return trace
  const migs = trace.migrations || []
  if (!trace.migrationTimes || trace.migrationTimes.length !== migs.length) {
    trace.migrationTimes = migs.map(m => m.ns)
  }
  if (!trace.migratedMks) {
    trace.migratedMks = trace.migrationsByMk instanceof Map
      ? new Set(trace.migrationsByMk.keys())
      : new Set()
  }
  if (!trace.coreUtilPct) {
    const total = Math.max((trace.timeMax ?? 0) - (trace.timeMin ?? 0), 1)
    const pct = {}
    for (const core of trace.coreNames || []) {
      const segs = trace.coreSegs?.get?.(core) || []
      let active = 0
      for (const s of segs) {
        const { name } = parseTaskName(s.task)
        if (name === 'TICK' || isIdleTaskName(name)) continue
        active += s.end - s.start
      }
      pct[core] = 100.0 * active / total
    }
    trace.coreUtilPct = pct
  }
  if (!trace.taskCpuNs) {
    const out = []
    const entries = trace.segByMergeKey?.entries?.() || []
    for (const [mk, segs] of entries) {
      const repr = taskReprGet(trace, mk) || mk
      const { name } = parseTaskName(repr)
      if (isIdleTaskName(name) || name === 'TICK') continue
      let t = 0
      for (const s of segs) t += s.end - s.start
      if (t > 0) out.push([mk, t])
    }
    out.sort((a, b) => b[1] - a[1])
    trace.taskCpuNs = out
  }
  if (trace.schedCtxSwitches == null || !Array.isArray(trace.schedCoreGaps)) {
    const sched = schedulingStats(trace)
    trace.schedCtxSwitches = sched.contextSwitches
    trace.schedCoreGaps = sched.coreGaps
    trace.schedGapMax = sched.gapMax
  }
  if (!Array.isArray(trace.migrationRowsFull)) {
    trace.migrationRowsFull = migrationRows(trace)
  }
  if (!Array.isArray(trace.uxEventsFull)) {
    prepareUxEvents(trace)
  }
  return trace
}

export function countPingPong(migs, window = MIGRATION_PING_PONG_WINDOW) {
  if (!migs || migs.length < 3) return 0
  let count = 0
  for (let i = 2; i < migs.length; i++) {
    const a = migs[i - 2]
    const b = migs[i - 1]
    const c = migs[i]
    if (b.ns - a.ns > window || c.ns - b.ns > window) continue
    if (a.toCore === b.fromCore && b.toCore === c.fromCore && a.fromCore === c.toCore) count++
  }
  return count
}

export function migrationStiNearCount(trace, migs, window = MIGRATION_STI_WINDOW) {
  if (!migs?.length) return 0
  const stiTimes = trace.stiEventTimes
    ?? (trace.stiEvents?.length ? trace.stiEvents.map(e => e.time).sort((a, b) => a - b) : [])
  if (!stiTimes.length) return 0
  let count = 0
  for (const m of migs) {
    const lo = m.ns - window
    const hi = m.ns + window
    const i0 = bisectLeft(stiTimes, lo)
    const i1 = bisectRight(stiTimes, hi)
    if (i1 > i0) count++
  }
  return count
}

export function migrationRows(trace, lo, hi) {
  if (lo == null && hi == null && Array.isArray(trace?.migrationRowsFull)) {
    return trace.migrationRowsFull
  }
  const rows = []
  const tickTimes = trace.tickStiTimes || []
  for (const mk of trace.tasks || []) {
    if (!isMigratedTask(trace, mk)) continue
    const segs = trace.segByMergeKey?.get(mk) || []
    let migs = trace.migrationsByMk?.get(mk) || []
    if (lo != null && hi != null) {
      migs = migs.filter(m => m.ns >= lo && m.ns <= hi)
      if (!migs.length && !segs.some(s => segOverlapsRange(s, lo, hi))) continue
    }
    const coreTime = new Map()
    for (const s of segs) {
      let ovLo, ovHi
      if (lo != null && hi != null) {
        if (!segOverlapsRange(s, lo, hi)) continue
        ovLo = Math.max(s.start, lo)
        ovHi = Math.min(s.end, hi)
      } else {
        ovLo = s.start
        ovHi = s.end
      }
      coreTime.set(s.core, (coreTime.get(s.core) || 0) + Math.max(0, ovHi - ovLo))
    }
    const total = [...coreTime.values()].reduce((a, b) => a + b, 0)
    if (total <= 0 && !migs.length) continue
    const cores = taskCoresUsed(trace, mk)
    const scopedCores = coresInScope(segs, migs, lo, hi)
    const coreCount = scopedCores.size || cores.size
    let primary
    let primaryPct
    if (total > 0) {
      primary = [...coreTime.entries()].sort((a, b) => b[1] - a[1])[0][0]
      primaryPct = 100 * coreTime.get(primary) / total
    } else {
      primary = [...cores].sort()[0] ?? '-'
      primaryPct = 0
    }
    const tickCount = tickCountForTask(segs, tickTimes, lo, hi)
    const gapsAfter = migs.filter(m => m.gapNs > 0).map(m => m.gapNs)
    const allGaps = blockingTimeSamples(segs, lo, hi)
    const avgAfter = gapsAfter.length ? gapsAfter.reduce((a, b) => a + b, 0) / gapsAfter.length : 0
    const avgOther = allGaps.length ? allGaps.reduce((a, b) => a + b, 0) / allGaps.length : 0
    const dwellSamples = coreDwellSamples(segs, lo, hi)
    const avgDwellTu = dwellSamples.length
      ? Math.round(dwellSamples.reduce((a, b) => a + b, 0) / dwellSamples.length)
      : 0
    const { label: migrRate, ratePerS } = formatMigrationRate(migs.length, total, tickCount, trace.timeScale)
    rows.push({
      mk,
      name: taskLabelForMergeKey(trace, mk),
      migrations: migs.length,
      migrRate,
      ratePerS,
      avgDwell: avgDwellTu ? formatTime(avgDwellTu, trace.timeScale) : '-',
      avgDwellTu: avgDwellTu || -1,
      coreCount,
      primary,
      primaryPct,
      pingPong: countPingPong(migs),
      stiNear: migrationStiNearCount(trace, migs),
      gapAfter: avgAfter ? formatMigrationGapTime(avgAfter, trace.timeScale) : '-',
      gapOther: avgOther ? formatMigrationGapTime(avgOther, trace.timeScale) : '-',
      gapAfterNs: avgAfter || -1,
      gapOtherNs: avgOther || -1,
    })
  }
  rows.sort((a, b) => b.migrations - a.migrations || a.name.localeCompare(b.name))
  return rows
}

/** Plot points: one per on-core run (clipped to scope). x = run start, y = duration. */
export function migrationDwellPlotPoints(trace, mk, lo, hi) {
  const segs = trace.segByMergeKey?.get(mk) || []
  const points = []
  for (const s of segs) {
    let ovLo
    let ovHi
    if (lo != null && hi != null) {
      if (!segOverlapsRange(s, lo, hi)) continue
      ovLo = Math.max(s.start, lo)
      ovHi = Math.min(s.end, hi)
    } else {
      ovLo = s.start
      ovHi = s.end
    }
    const dur = Math.max(0, ovHi - ovLo)
    if (dur > 0) points.push({ xNs: ovLo, yValue: dur, payload: s })
  }
  return points
}

/** Plot points: one per consecutive migration-event pair. x = event time, y = gap since the previous migration. */
export function migrationRatePlotPoints(trace, mk, lo, hi) {
  const migs = [...(trace.migrationsByMk?.get(mk) || [])].sort((a, b) => a.ns - b.ns)
  const points = []
  for (let i = 1; i < migs.length; i++) {
    const cur = migs[i]
    if (lo != null && hi != null && (cur.ns < lo || cur.ns > hi)) continue
    const gap = cur.ns - migs[i - 1].ns
    if (gap > 0) points.push({ xNs: cur.ns, yValue: gap, payload: cur })
  }
  return points
}

/** Plot points: one per migration event with a positive post-migration blocking gap. */
export function migrationGapPlotPoints(trace, mk, lo, hi) {
  const migs = trace.migrationsByMk?.get(mk) || []
  const points = []
  for (const m of migs) {
    if (lo != null && hi != null && (m.ns < lo || m.ns > hi)) continue
    if (m.gapNs > 0) points.push({ xNs: m.ns, yValue: m.gapNs, payload: m })
  }
  return points
}

export const PAIR_BOUNCE_POINT_COLOR = '#FF9800'
export const PAIR_PLOT_KEY_SEP = '\x00'

export function pairPlotKey(fromCore, toCore) {
  return `${fromCore}${PAIR_PLOT_KEY_SEP}${toCore}`
}

export function parsePairPlotKey(key) {
  if (!key || !key.includes(PAIR_PLOT_KEY_SEP)) return null
  const [fromCore, toCore] = key.split(PAIR_PLOT_KEY_SEP)
  if (!fromCore || !toCore) return null
  return { fromCore, toCore }
}

/** Directed From→To migrations in scope, time-sorted. */
export function pairMigrations(trace, fromCore, toCore, lo = null, hi = null) {
  const out = []
  for (const m of migrationsInRange(trace, lo, hi)) {
    if (m.fromCore !== fromCore || m.toCore !== toCore) continue
    out.push(m)
  }
  out.sort((a, b) => a.ns - b.ns)
  return out
}

/**
 * Core-pair Gap plot points. Bounce migrations carry fillColor accent.
 * Returns [{ xNs, yValue, payload, fillColor? }]
 */
export function pairGapPlotPoints(trace, fromCore, toCore, lo = null, hi = null) {
  const bounceNs = buildLockBounceNsSet(trace)
  const points = []
  for (const m of pairMigrations(trace, fromCore, toCore, lo, hi)) {
    if ((m.gapNs ?? 0) <= 0) continue
    const pt = { xNs: m.ns, yValue: m.gapNs, payload: m }
    if (bounceNs.has(m.ns)) pt.fillColor = PAIR_BOUNCE_POINT_COLOR
    points.push(pt)
  }
  return points
}

/**
 * Core-pair Rate plot points: y = time since previous migration on this corridor.
 */
export function pairRatePlotPoints(trace, fromCore, toCore, lo = null, hi = null) {
  const migs = pairMigrations(trace, fromCore, toCore)
  const bounceNs = buildLockBounceNsSet(trace)
  const points = []
  for (let i = 1; i < migs.length; i++) {
    const cur = migs[i]
    if (lo != null && hi != null && (cur.ns < lo || cur.ns > hi)) continue
    const gap = cur.ns - migs[i - 1].ns
    if (gap <= 0) continue
    const pt = { xNs: cur.ns, yValue: gap, payload: cur }
    if (bounceNs.has(cur.ns)) pt.fillColor = PAIR_BOUNCE_POINT_COLOR
    points.push(pt)
  }
  return points
}

/** Prefer Bounce Only when Bounce % is elevated (≥25% with ≥5 migrations). */
export function pairBouncePrefer(trace, fromCore, toCore, lo = null, hi = null) {
  const migs = pairMigrations(trace, fromCore, toCore, lo, hi)
  if (migs.length < 5) return false
  const bounceNs = buildLockBounceNsSet(trace)
  const pct = 100 * migs.filter(m => bounceNs.has(m.ns)).length / migs.length
  return pct >= 25
}

export function migrationFindHits(trace, query) {
  return computeFindHits(trace, query, 'migrations').hits
}

export function coreShortName(core) {
  if (core?.startsWith('Core_')) {
    const tail = core.slice(5)
    if (/^\d+$/.test(tail)) return `c${tail}`
  }
  return core
}

/** Round a label stride up to 1/2/5×10^k (c0, c5, c10…). */
export function chordLabelNiceStep(raw) {
  const n = Math.max(1, Math.floor(Number(raw) || 1))
  if (n <= 1) return 1
  const mag = 10 ** Math.floor(Math.log10(n))
  for (const mult of [1, 2, 5, 10]) {
    const nice = mult * mag
    if (nice >= n) return nice
  }
  return n
}

/**
 * Stride between chord circle / matrix tick labels.
 * Small core counts keep every name; larger diagrams skip (0, 5, 10…).
 * Optional minPx/spanPx raise the stride when glyphs would collide.
 */
export function chordLabelStep(nCores, minPx = 0, spanPx = 0) {
  const n = Math.floor(Number(nCores) || 0)
  let step = 1
  if (n <= 16) step = 1
  else if (n <= 32) step = 2
  else if (n <= 64) step = 5
  else if (n <= 128) step = 8
  else step = 10
  if (minPx > 0 && spanPx > 0 && n > 0) {
    const per = spanPx / n
    if (per < minPx) {
      const need = Math.ceil(minPx / Math.max(per, 1e-9))
      step = Math.max(step, chordLabelNiceStep(need))
    }
  }
  return Math.max(1, step)
}

/** True when core index should draw a name (stride tick or hover/focus). */
export function chordLabelVisible(index, step, extra) {
  if (extra && extra.has(index)) return true
  if (step <= 1) return true
  return index % step === 0
}

export function traceIsMultiCore(trace) {
  return (trace?.coreNames?.length ?? 0) >= 2
}

/** Above this core count, heatmap level-0 uses a core×core matrix instead of pair×time rows. */
export const MIGRATION_HEATMAP_MATRIX_CORE_THRESHOLD = 16

export function migrationHeatmapUsesMatrix(trace) {
  return (trace?.coreNames?.length ?? 0) > MIGRATION_HEATMAP_MATRIX_CORE_THRESHOLD
}

/**
 * Build the set of migration ns timestamps that occurred during a mutex hold
 * that crossed cores (cache-line bounce). Result is cached on the trace object.
 */
export function buildLockBounceNsSet(trace) {
  if (!trace) return new Set()
  if (trace._lockBounceNs) return trace._lockBounceNs
  const s = new Set()
  if (trace.hasSyncObjectInstrumentation && trace.syncObjects) {
    const bounceHolds = []
    for (const obj of trace.syncObjects.values()) {
      if (obj.kind !== 'mutex') continue
      for (const h of obj.holds || []) {
        if (h.takeCore && h.giveCore && h.takeCore !== h.giveCore) {
          bounceHolds.push(h)
        }
      }
    }
    if (bounceHolds.length) {
      for (const m of trace.migrations || []) {
        for (const h of bounceHolds) {
          if (h.holderMk && m.mergeKey !== h.holderMk) continue
          if (m.ns >= h.startNs && m.ns <= h.stopNs) {
            s.add(m.ns)
            break
          }
        }
      }
    }
  }
  trace._lockBounceNs = s
  return s
}

/** Source × destination core counts for large traces (one overview row per source core). */
export function migrationHeatmapMatrix(trace, lo = null, hi = null, bounceOnly = false) {
  if (!trace) return { cores: [], grid: [] }
  const cores = trace.coreNames || []
  const n = cores.length
  const coreIndex = new Map(cores.map((c, i) => [c, i]))
  const grid = Array.from({ length: n }, () => Array(n).fill(0))
  const bounceNs = bounceOnly ? buildLockBounceNsSet(trace) : null
  for (const m of migrationsInRange(trace, lo, hi)) {
    if (bounceNs && !bounceNs.has(m.ns)) continue
    const fi = coreIndex.get(m.fromCore)
    const ti = coreIndex.get(m.toCore)
    if (fi == null || ti == null || fi === ti) continue
    grid[fi][ti]++
  }
  return { cores, grid }
}

/** Time bins for all outgoing pairs from one source core (matrix row drill-down). */
export function migrationCoreOutgoingHeatmap(trace, fromCore, lo = null, hi = null, timeBins = 32, bounceOnly = false) {
  if (!trace || !fromCore) {
    return { pairs: [], grid: [], timeBins, tMin: 0, tMax: 0, binW: 0 }
  }
  const cores = trace.coreNames || []
  const pairs = []
  for (const tc of cores) {
    if (tc === fromCore) continue
    pairs.push({
      from: fromCore,
      to: tc,
      label: `${coreShortName(fromCore)}→${coreShortName(tc)}`,
    })
  }
  const tMin = lo ?? trace.timeMin
  const tHi = hi ?? trace.timeMax
  const span = Math.max(tHi - tMin, 1)
  const binW = span / timeBins
  const grid = pairs.map(() => Array(timeBins).fill(0))
  const pairIndex = new Map(pairs.map((p, i) => [`${p.to}`, i]))
  const bounceNs = bounceOnly ? buildLockBounceNsSet(trace) : null
  for (const m of migrationsInRange(trace, lo, hi)) {
    if (m.fromCore !== fromCore) continue
    if (bounceNs && !bounceNs.has(m.ns)) continue
    const pi = pairIndex.get(m.toCore)
    if (pi == null) continue
    const bi = heatmapBinIndexForNs(tMin, binW, timeBins, tHi, m.ns)
    grid[pi][bi]++
  }
  return { pairs, grid, binW, tMin, timeBins, tMax: tHi }
}

/** Time bins for one directed core pair (heatmap drill-down after outgoing pick). */
export function migrationPairTimeBins(trace, fromCore, toCore, lo = null, hi = null, timeBins = 32) {
  if (!trace) {
    return { pairs: [], grid: [], timeBins, tMin: 0, tMax: 0, binW: 0 }
  }
  const tMin = lo ?? trace.timeMin
  const tHi = hi ?? trace.timeMax
  const span = Math.max(tHi - tMin, 1)
  const binW = span / timeBins
  const bins = Array(timeBins).fill(0)
  for (const m of migrationsInRange(trace, lo, hi)) {
    if (m.fromCore !== fromCore || m.toCore !== toCore) continue
    const bi = heatmapBinIndexForNs(tMin, binW, timeBins, tHi, m.ns)
    bins[bi]++
  }
  const label = `${coreShortName(fromCore)}→${coreShortName(toCore)}`
  return {
    pairs: [{ from: fromCore, to: toCore, label }],
    grid: [bins],
    binW,
    tMin,
    timeBins,
    tMax: tHi,
  }
}

/** Core-pair rows × time bins for migration heatmap popup. */
export function migrationHeatmapGrid(trace, lo = null, hi = null, timeBins = 32, bounceOnly = false) {
  if (!trace) return { pairs: [], grid: [], timeBins, tMin: 0, tMax: 0, binW: 0 }
  const cores = trace.coreNames || []
  const pairs = []
  const pairIndex = new Map()
  for (const fc of cores) {
    for (const tc of cores) {
      if (fc !== tc) {
        pairIndex.set(`${fc}\0${tc}`, pairs.length)
        pairs.push({
          from: fc,
          to: tc,
          label: `${coreShortName(fc)}→${coreShortName(tc)}`,
        })
      }
    }
  }
  const tMin = lo ?? trace.timeMin
  const tHi = hi ?? trace.timeMax
  const span = Math.max(tHi - tMin, 1)
  const binW = span / timeBins
  const grid = pairs.map(() => Array(timeBins).fill(0))
  const bounceNs = bounceOnly ? buildLockBounceNsSet(trace) : null
  for (const m of migrationsInRange(trace, lo, hi)) {
    if (bounceNs && !bounceNs.has(m.ns)) continue
    const pi = pairIndex.get(`${m.fromCore}\0${m.toCore}`)
    if (pi == null) continue
    const bi = heatmapBinIndexForNs(tMin, binW, timeBins, tHi, m.ns)
    grid[pi][bi]++
  }
  return { pairs, grid, binW, tMin, timeBins, tMax: tHi }
}

/** Time bounds [lo, hi) for one heatmap column index. */
export function heatmapBinRange(tMin, binW, timeBins, tMax, binIndex) {
  const binLo = Math.floor(tMin + binIndex * binW)
  const binHi = binIndex >= timeBins - 1 ? tMax : Math.floor(tMin + (binIndex + 1) * binW)
  return { binLo, binHi }
}

/** Half-open [binLo, binHi) except the last bin includes binHi. */
export function migrationNsInBin(ns, binLo, binHi, binIndex, timeBins) {
  if (ns < binLo) return false
  if (binIndex >= timeBins - 1) return ns <= binHi
  return ns < binHi
}

/** Bin index for ns; retries bi+1 when floor division lands on an upper boundary. */
export function heatmapBinIndexForNs(tMin, binW, timeBins, tMax, ns) {
  let bi = Math.min(timeBins - 1, Math.max(0, Math.floor((ns - tMin) / binW)))
  for (const b of [bi, bi + 1]) {
    if (b >= timeBins) continue
    const { binLo, binHi } = heatmapBinRange(tMin, binW, timeBins, tMax, b)
    if (migrationNsInBin(ns, binLo, binHi, b, timeBins)) return b
  }
  return bi
}

/** Merge keys of tasks with a migration from→to core in [binLo, binHi). */
export function mergeKeysForHeatmapCell(trace, fromCore, toCore, binLo, binHi,
                                        binIndex, timeBins) {
  const keys = new Set()
  for (const m of migrationsInRange(trace, binLo, binHi)) {
    if (m.fromCore !== fromCore || m.toCore !== toCore) continue
    if (!migrationNsInBin(m.ns, binLo, binHi, binIndex, timeBins)) continue
    keys.add(m.mergeKey)
  }
  return [...keys]
}

/** Task rows × sub-bins for one core-pair / time-bin drill-down.
 *  scopeLo/scopeHi are the cursor range used to count reverse-direction
 *  migrations for the ingress (▼) / egress (▲) / balanced (⇄) annotation. */
export function migrationTaskHeatmapGrid(trace, fromCore, toCore, binLo, binHi,
                                         timeBins = 32, parentBinIndex = 0,
                                         parentTimeBins = 32, scopeLo = null, scopeHi = null) {
  if (!trace) return { rows: [], timeBins, tMin: binLo, tMax: binHi, binW: 0 }
  const tMin = binLo
  const tHi = binHi
  const span = Math.max(tHi - tMin, 1)
  const binW = span / timeBins
  const taskBins = new Map()
  for (const m of migrationsInRange(trace, binLo, binHi)) {
    if (m.fromCore !== fromCore || m.toCore !== toCore) continue
    if (!migrationNsInBin(m.ns, binLo, binHi, parentBinIndex, parentTimeBins)) continue
    const mk = m.mergeKey
    if (!taskBins.has(mk)) taskBins.set(mk, Array(timeBins).fill(0))
    const bi = heatmapBinIndexForNs(tMin, binW, timeBins, tHi, m.ns)
    taskBins.get(mk)[bi]++
  }
  const items = [...taskBins.entries()].sort((a, b) => {
    const sa = a[1].reduce((x, y) => x + y, 0)
    const sb = b[1].reduce((x, y) => x + y, 0)
    return sb - sa || a[0].localeCompare(b[0])
  })
  // Count reverse-direction migrations per task for ingress/egress annotation.
  const revTotals = new Map()
  if (fromCore && toCore) {
    for (const m of migrationsInRange(trace, scopeLo, scopeHi)) {
      if (m.fromCore !== toCore || m.toCore !== fromCore) continue
      revTotals.set(m.mergeKey, (revTotals.get(m.mergeKey) || 0) + 1)
    }
  }
  const rows = items.map(([mk, grid]) => {
    const fwd = grid.reduce((s, v) => s + v, 0)
    const rev = revTotals.get(mk) || 0
    const sym = fwd > rev * 1.5 ? '▲' : rev > fwd * 1.5 ? '▼' : '⇄'
    return { mk, label: `${sym} ${taskLabelForMergeKey(trace, mk)}`, grid }
  })
  return { rows, timeBins, binW, tMin, tMax: tHi }
}

/**
 * Per (fromCore, toCore) pair migration summary rows.
 * Returns [{fromCore, toCore, count, bounceCount, bouncePct, avgGapNs}]
 */
export function buildCorePairRows(trace, lo = null, hi = null) {
  const bounceNs = buildLockBounceNsSet(trace)
  const pairs = new Map()
  for (const m of migrationsInRange(trace, lo, hi)) {
    const key = `${m.fromCore}\x00${m.toCore}`
    const d = pairs.get(key) ?? { fromCore: m.fromCore, toCore: m.toCore, count: 0, bounces: 0, gapSum: 0 }
    d.count++
    if (bounceNs.has(m.ns)) d.bounces++
    d.gapSum += (m.gapNs ?? 0)
    pairs.set(key, d)
  }
  return [...pairs.values()]
    .sort((a, b) => b.count - a.count)
    .map(d => ({
      ...d,
      bouncePct: d.count > 0 ? 100 * d.bounces / d.count : 0,
      avgGapNs: d.count > 0 ? Math.floor(d.gapSum / d.count) : 0,
    }))
}

/**
 * Compact Migration Summary for progressive drill-down (Step 2).
 * Lockstep with btf_viewer_pkg.parser._migration_summary.
 */
export function summarizeMigrations(trace, lo = null, hi = null) {
  const migs = migrationsInRange(trace, lo, hi)
  const total = migs.length
  const rows = migrationRows(trace, lo, hi)
  const pairs = buildCorePairRows(trace, lo, hi)
  const tMin = Number(trace?.timeMin ?? 0)
  const tMax = Number(trace?.timeMax ?? 0)
  const span = (lo != null && hi != null) ? Math.max(0, hi - lo) : Math.max(0, tMax - tMin)
  const scale = trace?.timeScale || 'us'
  const perS = NS_PER_SCALE[scale] || 1e6
  const spanS = span > 0 ? span / perS : 0
  const rate = spanS > 0 ? total / spanS : 0
  const rateLabel = (spanS > 0 && total) ? `${rate.toFixed(2)}/s` : '—'

  let topTask = null
  if (rows.length) {
    const r = rows[0]
    topTask = { mk: r.mk, name: r.name, count: r.migrations }
  }

  let topPair = null
  if (pairs.length) {
    const p = pairs[0]
    topPair = {
      from: p.fromCore,
      to: p.toCore,
      count: p.count,
      bounces: p.bounces,
    }
  }

  const dwell = []
  for (const r of rows) {
    const segs = trace.segByMergeKey?.get(r.mk) || []
    dwell.push(...coreDwellSamples(segs, lo, hi))
  }
  let medianDwellNs = 0
  if (dwell.length) {
    const ordered = dwell.slice().sort((a, b) => a - b)
    medianDwellNs = ordered[Math.floor(ordered.length / 2)]
  }
  const medianDwell = medianDwellNs
    ? formatTime(medianDwellNs, scale)
    : '—'

  const pingTotal = rows.reduce((a, r) => a + (r.pingPong || 0), 0)
  let thrashHint = ''
  if (pingTotal > 0) {
    thrashHint = `${pingTotal} ping-pong migration(s) in scope`
  } else if (topPair && topPair.count > 0) {
    const bouncePct = 100 * topPair.bounces / topPair.count
    if (bouncePct >= 30) {
      thrashHint = `Hot pair ${topPair.from}→${topPair.to} bounce ${bouncePct.toFixed(0)}%`
    }
  }

  return {
    total,
    rate,
    rateLabel,
    topTask,
    topPair,
    medianDwellNs,
    medianDwell,
    thrashHint,
    hasData: total > 0 || rows.length > 0,
  }
}

/** True if any sync-object hold crossed cores (cache-line "lock bounce"). */
export function traceHasCoreBounceHolds(trace) {
  if (!trace?.hasSyncObjectInstrumentation) return false
  for (const obj of trace.syncObjects?.values() || []) {
    for (const h of obj.holds || []) {
      if (h.takeCore && h.giveCore && h.takeCore !== h.giveCore) return true
    }
  }
  return false
}

const CHORD_GAP_RAD = 0.03
const CHORD_MIN_ARC_RAD = 0.05

/** Dest ribbon width as a fraction of source width (directional taper). */
export const CHORD_TAPER_DEST_RATIO = 0.4
/** Gradient holds source color until this stop, then fades to dest. */
export const CHORD_GRAD_SOURCE_STOP = 0.7
/** Max stroke/fill half-width for tapered ribbons (CSS px). */
export const CHORD_RIBBON_MAX_HALF = 7
/** Outer ring stroke (egress / departures). */
export const CHORD_ARC_OUTER = 12
/** Inner ring stroke (ingress / arrivals). */
export const CHORD_ARC_INNER = 8

/** Radii for split core rings + ribbon attach point. */
export function chordRingGeometry(radius) {
  const rEgress = Number(radius)
  const rIngress = rEgress - CHORD_ARC_OUTER - 2
  const rRibbon = rIngress - CHORD_ARC_INNER / 2 - 2
  return { rEgress, rIngress, rRibbon }
}

/** Which split ring a distance-from-centre hits. */
export function chordHitRing(dist, radius) {
  const { rEgress, rIngress } = chordRingGeometry(radius)
  if (Math.abs(dist - rEgress) <= CHORD_ARC_OUTER / 2 + 3) return 'egress'
  if (Math.abs(dist - rIngress) <= CHORD_ARC_INNER / 2 + 3) return 'ingress'
  return null
}

/**
 * Default Top-N corridor threshold from core count (TODO2 §5).
 * @returns {number} percent 10|25|50|100
 */
export function defaultCorridorTopPct(coreCount) {
  const n = coreCount || 0
  if (n > 16) return 25
  if (n > 8) return 25
  return 100
}

/** Keep corridors whose volume is in the top `topPct` percent by count. */
export function filterCorridorsByTopPct(corridors, topPct = 100) {
  const list = Array.isArray(corridors) ? [...corridors] : []
  if (!list.length || topPct >= 100) return list
  const pct = Math.max(1, Math.min(100, topPct))
  const sorted = [...list].sort((a, b) => (b.count || 0) - (a.count || 0))
  const keep = Math.max(1, Math.ceil(sorted.length * (pct / 100)))
  const threshold = sorted[keep - 1]?.count ?? 0
  return list.filter(c => (c.count || 0) >= threshold)
}

/**
 * Default Top-N path count from core count.
 * @returns {number} 5|10|25|0 (0 = all paths)
 */
export function defaultCorridorTopN(coreCount) {
  const n = coreCount || 0
  if (n > 8) return 10
  return 0
}

/** Keep the N busiest corridors by count. `n <= 0` keeps all. */
export function filterCorridorsByTopN(corridors, n = 0) {
  const list = Array.isArray(corridors) ? [...corridors] : []
  const limit = Number(n)
  if (!list.length || !Number.isFinite(limit) || limit <= 0 || limit >= list.length) {
    return list
  }
  return [...list]
    .sort((a, b) => (b.count || 0) - (a.count || 0) || String(a.label || '').localeCompare(String(b.label || '')))
    .slice(0, Math.floor(limit))
}

export function sortCorridors(corridors, sortBy = 'rate', descending = null) {
  const list = Array.isArray(corridors) ? [...corridors] : []
  const key = CORRIDOR_SORT_KEYS.includes(sortBy) ? sortBy : 'rate'
  const desc = descending == null ? key !== 'label' : !!descending
  const metric = (c) => {
    if (key === 'pingpong') return c.pingPongPct || 0
    if (key === 'dwell') return c.shortDwellShare || 0
    if (key === 'handoff') return c.handoffPct ?? c.bouncePct ?? 0
    if (key === 'share') return c.primaryTask?.sharePct || 0
    if (key === 'count') return c.count || 0
    if (key === 'net') return c.net || 0
    return c.ratePerS || 0
  }
  return list.sort((a, b) => {
    let d
    if (key === 'label') {
      d = String(a.label || '').localeCompare(String(b.label || ''))
    } else {
      d = metric(a) - metric(b)
    }
    if (d) return desc ? -d : d
    const dc = (b.count || 0) - (a.count || 0)
    if (dc) return dc
    return String(a.label || '').localeCompare(String(b.label || ''))
  })
}

/**
 * Inspector Analysis Scope: Full Trace, Viewport (visible window), or Cursor C1–Cn.
 * @param {'full'|'viewport'|'cursor'} mode
 * @param {number[]} [cursors]
 * @param {object} [viewport] `{ timeStart, timeEnd }` from the timeline
 */
function viewportWindow(viewport, tlo, thi) {
  let vlo = Number(viewport?.timeStart ?? viewport?.[0])
  let vhi = Number(viewport?.timeEnd ?? viewport?.[1])
  if (!Number.isFinite(vlo) || !Number.isFinite(vhi) || !(vhi > vlo)) {
    vlo = tlo
    vhi = thi
  }
  return [vlo, vhi]
}

export function inspectorAnalysisScope(
  mode,
  cursors,
  timeMin,
  timeMax,
  timeScale,
  formatTimeFn,
  viewport,
) {
  const fmt = formatTimeFn || formatTime
  const tlo = Number.isFinite(Number(timeMin)) ? Number(timeMin) : 0
  const thi = Number.isFinite(Number(timeMax)) ? Number(timeMax) : 0
  const placed = (cursors || []).filter(c => c != null && Number.isFinite(Number(c)))
  const canCursor = placed.length >= 2
  let lo = null
  let hi = null
  let resolved = 'full'
  const want = mode || 'auto'
  if (want === 'cursor' && canCursor) {
    const sorted = placed.map(Number).sort((a, b) => a - b)
    lo = sorted[0]
    hi = sorted[sorted.length - 1]
    if (hi > lo) resolved = 'cursor'
    else {
      lo = null
      hi = null
    }
  } else if (want === 'viewport') {
    const [vlo, vhi] = viewportWindow(viewport, tlo, thi)
    lo = vlo
    hi = vhi
    resolved = 'viewport'
  } else if (want === 'full') {
    resolved = 'full'
  } else {
    const [vlo, vhi] = viewportWindow(viewport, tlo, thi)
    const fit = Boolean(viewport?.fitMode)
    if (inspectorViewportIsFull(vlo, vhi, tlo, thi, fit)) {
      resolved = 'full'
    } else {
      lo = vlo
      hi = vhi
      resolved = 'viewport'
    }
  }
  const scoped = resolved !== 'full'
  const a = scoped ? lo : tlo
  const b = scoped ? hi : thi
  const n = resolved === 'cursor' ? placed.length : 0
  const label = resolved === 'cursor'
    ? `Cursor C1–C${n}`
    : resolved === 'viewport' ? 'Viewport' : 'Full Trace'
  const unit = timeScale || 'ns'
  const detail = `${fmt(a, unit)} … ${fmt(b, unit)} (${fmt(Math.max(0, b - a), unit)}) · trace unit: ${unit}`
  return {
    mode: resolved,
    lo: scoped ? lo : null,
    hi: scoped ? hi : null,
    nCursors: n,
    canCursor,
    cursorDisabledReason: canCursor ? '' : 'Place at least two cursors.',
    label,
    detail,
    unit,
    scoped,
  }
}

/** Net migration balance: positive = net gain (sink), negative = net loss (spillway). */
export function netMigrationBalance(incoming, outgoing) {
  return (incoming || 0) - (outgoing || 0)
}

/**
 * Pure circular layout for a chord diagram from a core×core matrix
 * (as returned by migrationHeatmapMatrix): each core gets an arc sized
 * proportionally to its total in+out migration volume (with a minimum
 * sliver so zero-flow cores still appear as nodes), and each connected
 * core-pair gets a tick position within its two arcs used as chord endpoints.
 *
 * Also exposes egress/ingress tick angles (for split rings) and tapered
 * ribbon half-widths at each end of a directed corridor.
 *
 * Returns {
 *   arcs: [{ core, index, startAngle, endAngle, total, outTotal, inTotal }],
 *   tickAngle(i, j),
 *   egressTickAngle(i, j),
 *   ingressTickAngle(i, j),
 *   ribbonHalfWidths(i, j, maxCount),
 * }
 */
export function buildChordLayout(cores, grid) {
  const n = cores.length
  const totals = Array(n).fill(0)
  const outTotals = Array(n).fill(0)
  const inTotals = Array(n).fill(0)
  for (let i = 0; i < n; i++) {
    for (let j = 0; j < n; j++) {
      if (i === j) continue
      const o = grid[i]?.[j] || 0
      const inn = grid[j]?.[i] || 0
      outTotals[i] += o
      inTotals[i] += inn
      totals[i] += o + inn
    }
  }
  const grandTotal = totals.reduce((a, b) => a + b, 0)
  const gap = n > 0 ? Math.min(CHORD_GAP_RAD, (Math.PI * 1.5) / n) : 0
  const available = Math.max(0, 2 * Math.PI - gap * n)
  const minArc = n > 0 ? Math.min(CHORD_MIN_ARC_RAD, available / n) : 0

  // First pass: minimum-floor sizes; remaining angle split proportionally to volume.
  const floorTotal = minArc * n
  const remaining = Math.max(0, available - floorTotal)
  const arcSizes = totals.map(t => minArc + (grandTotal > 0 ? remaining * (t / grandTotal) : remaining / Math.max(n, 1)))

  const arcs = []
  let angle = -Math.PI / 2
  for (let i = 0; i < n; i++) {
    const startAngle = angle
    const endAngle = startAngle + arcSizes[i]
    arcs.push({
      core: cores[i],
      index: i,
      startAngle,
      endAngle,
      total: totals[i],
      outTotal: outTotals[i],
      inTotal: inTotals[i],
    })
    angle = endAngle + gap
  }

  // Combined (legacy) ticks + separate egress/ingress ticks within each arc.
  const tickAngles = arcs.map(() => new Map())
  const egressTicks = arcs.map(() => new Map())
  const ingressTicks = arcs.map(() => new Map())
  for (let i = 0; i < n; i++) {
    const arc = arcs[i]
    const span = arc.endAngle - arc.startAngle
    const combined = []
    const egress = []
    const ingress = []
    for (let j = 0; j < n; j++) {
      if (j === i) continue
      const out = grid[i]?.[j] || 0
      const inn = grid[j]?.[i] || 0
      if (out + inn > 0) combined.push({ j, mag: out + inn })
      if (out > 0) egress.push({ j, mag: out })
      if (inn > 0) ingress.push({ j, mag: inn })
    }
    const place = (links, map) => {
      const linkTotal = links.reduce((s, l) => s + l.mag, 0)
      let cursor = arc.startAngle
      for (const l of links) {
        const slice = linkTotal > 0 ? span * (l.mag / linkTotal) : (links.length ? span / links.length : 0)
        map.set(l.j, cursor + slice / 2)
        cursor += slice
      }
    }
    place(combined, tickAngles[i])
    place(egress, egressTicks[i])
    place(ingress, ingressTicks[i])
  }

  const arcMid = (i) => (arcs[i] ? (arcs[i].startAngle + arcs[i].endAngle) / 2 : 0)

  return {
    arcs,
    tickAngle(i, j) {
      return tickAngles[i]?.get(j) ?? arcMid(i)
    },
    egressTickAngle(i, j) {
      return egressTicks[i]?.get(j) ?? tickAngles[i]?.get(j) ?? arcMid(i)
    },
    ingressTickAngle(i, j) {
      return ingressTicks[i]?.get(j) ?? tickAngles[i]?.get(j) ?? arcMid(i)
    },
    /**
     * Half-widths (px) at source and dest ends for directed corridor i→j.
     * Source scales with count; dest tapers for directional encoding.
     */
    ribbonHalfWidths(i, j, maxCount = 1) {
      const count = grid[i]?.[j] || 0
      if (!count) return { srcHalf: 0, dstHalf: 0 }
      const m = maxCount || 1
      const srcHalf = Math.max(0.75, Math.min(CHORD_RIBBON_MAX_HALF, CHORD_RIBBON_MAX_HALF * (count / m)))
      const dstHalf = Math.max(0.5, srcHalf * CHORD_TAPER_DEST_RATIO)
      return { srcHalf, dstHalf }
    },
  }
}

/**
 * Point on a circle.
 * @returns {{ x: number, y: number }}
 */
export function chordPointAt(cx, cy, angle, r) {
  return { x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle) }
}

/** Distance from (mx, my) to a quadratic Bézier (p1 → ctrl → p2). */
export function distToQuadraticBezier(mx, my, p1, ctrl, p2, steps = 16) {
  let best = Infinity
  for (let k = 0; k <= steps; k++) {
    const t = k / steps
    const u = 1 - t
    const x = u * u * p1.x + 2 * u * t * ctrl.x + t * t * p2.x
    const y = u * u * p1.y + 2 * u * t * ctrl.y + t * t * p2.y
    const d = Math.hypot(mx - x, my - y)
    if (d < best) best = d
  }
  return best
}

/**
 * Build a tapered ribbon path (quadratic centerline + perpendicular offsets)
 * for canvas `Path2D` / SVG path `d` between two tick angles.
 */
export function buildTaperedRibbonPath(cx, cy, rInner, a0, a1, srcHalf, dstHalf, bidirOffset = 0) {
  const p1 = chordPointAt(cx, cy, a0, rInner)
  const p2 = chordPointAt(cx, cy, a1, rInner)
  const mx = (p1.x + p2.x) / 2
  const my = (p1.y + p2.y) / 2
  let vx = mx - cx
  let vy = my - cy
  const vlen = Math.hypot(vx, vy) || 1
  vx /= vlen
  vy /= vlen
  const perpX = -vy
  const perpY = vx
  const pull = 0.18
  const ctrlX = cx + vx * rInner * pull + perpX * bidirOffset
  const ctrlY = cy + vy * rInner * pull + perpY * bidirOffset

  // Tangents at ends ≈ direction toward control, for width normals.
  const t0x = ctrlX - p1.x
  const t0y = ctrlY - p1.y
  const t0len = Math.hypot(t0x, t0y) || 1
  const n0x = -t0y / t0len
  const n0y = t0x / t0len
  const t1x = p2.x - ctrlX
  const t1y = p2.y - ctrlY
  const t1len = Math.hypot(t1x, t1y) || 1
  const n1x = -t1y / t1len
  const n1y = t1x / t1len

  const sL = { x: p1.x + n0x * srcHalf, y: p1.y + n0y * srcHalf }
  const sR = { x: p1.x - n0x * srcHalf, y: p1.y - n0y * srcHalf }
  const dL = { x: p2.x + n1x * dstHalf, y: p2.y + n1y * dstHalf }
  const dR = { x: p2.x - n1x * dstHalf, y: p2.y - n1y * dstHalf }
  const cL = { x: ctrlX + ((n0x + n1x) / 2) * ((srcHalf + dstHalf) / 2), y: ctrlY + ((n0y + n1y) / 2) * ((srcHalf + dstHalf) / 2) }
  const cR = { x: ctrlX - ((n0x + n1x) / 2) * ((srcHalf + dstHalf) / 2), y: ctrlY - ((n0y + n1y) / 2) * ((srcHalf + dstHalf) / 2) }

  const d = `M ${sL.x} ${sL.y} Q ${cL.x} ${cL.y} ${dL.x} ${dL.y} L ${dR.x} ${dR.y} Q ${cR.x} ${cR.y} ${sR.x} ${sR.y} Z`
  return {
    d,
    p1,
    p2,
    ctrl: { x: ctrlX, y: ctrlY },
    points: { sL, sR, dL, dR, cL, cR },
  }
}

/**
 * Unified corridor inspector model (TODO2 Phase 1).
 * @param {object} trace
 * @param {number|null} lo
 * @param {number|null} hi
 * @param {{ bounceOnly?: boolean, topPct?: number, timeBins?: number }} [opts]
 */
export function buildCorridorInspectorModel(trace, lo = null, hi = null, opts = {}) {
  const bounceOnly = !!opts.bounceOnly
  const timeBins = opts.timeBins ?? 32
  if (!trace) {
    return emptyCorridorModel(timeBins)
  }
  const cores = trace.coreNames || []
  const topPct = opts.topPct ?? defaultCorridorTopPct(cores.length)
  const bounceNs = buildLockBounceNsSet(trace)
  const tMin = lo ?? trace.timeMin
  const tHi = hi ?? trace.timeMax
  const span = Math.max(tHi - tMin, 1)
  const binW = span / timeBins
  const scopeSec = span / (NS_PER_SCALE[trace.timeScale] || 1e9)

  /** @type {Map<string, object>} */
  const byKey = new Map()
  const nCores = cores.length
  const coreIndex = new Map(cores.map((c, i) => [c, i]))
  const fullGrid = Array.from({ length: nCores }, () => Array(nCores).fill(0))
  const scopedMigs = []
  for (const m of migrationsInRange(trace, lo, hi)) {
    if (bounceOnly && !bounceNs.has(m.ns)) continue
    if (m.fromCore === m.toCore) continue
    scopedMigs.push(m)
    const fi = coreIndex.get(m.fromCore)
    const ti = coreIndex.get(m.toCore)
    if (fi != null && ti != null) fullGrid[fi][ti]++
    const key = `${m.fromCore}\0${m.toCore}`
    let row = byKey.get(key)
    if (!row) {
      row = {
        fromCore: m.fromCore,
        toCore: m.toCore,
        label: `${coreShortName(m.fromCore)}→${coreShortName(m.toCore)}`,
        count: 0,
        bounces: 0,
        gapSum: 0,
        bins: Array(timeBins).fill(0),
        bounceBins: Array(timeBins).fill(0),
        tasks: new Map(),
      }
      byKey.set(key, row)
    }
    row.count++
    const isBounce = bounceNs.has(m.ns)
    if (isBounce) row.bounces++
    row.gapSum += (m.gapNs ?? 0)
    const bi = heatmapBinIndexForNs(tMin, binW, timeBins, tHi, m.ns)
    row.bins[bi]++
    if (isBounce) row.bounceBins[bi]++
    const mk = m.mergeKey
    if (mk) {
      let t = row.tasks.get(mk)
      if (!t) {
        t = {
          mk, count: 0, bounces: 0,
          bins: Array(timeBins).fill(0),
          bounceBins: Array(timeBins).fill(0),
        }
        row.tasks.set(mk, t)
      }
      t.count++
      if (isBounce) {
        t.bounces++
        t.bounceBins[bi]++
      }
      t.bins[bi]++
    }
  }
  attachCorridorPathMetrics(byKey, scopedMigs, trace.timeScale)

  const allCorridors = [...byKey.values()].map((row) => {
    const rev = byKey.get(`${row.toCore}\0${row.fromCore}`)
    const revCount = rev?.count || 0
    const net = netMigrationBalance(revCount, row.count)
    const tasks = [...row.tasks.values()]
      .sort((a, b) => b.count - a.count || a.mk.localeCompare(b.mk))
      .map((t) => {
        const label = taskLabelForMergeKey(trace, t.mk)
        const { ids } = corridorTaskIdsAndName({ mk: t.mk, label })
        return {
          mk: t.mk,
          label,
          taskId: ids[0] != null ? Number(ids[0]) : null,
          count: t.count,
          bounces: t.bounces,
          bouncePct: t.count > 0 ? 100 * t.bounces / t.count : 0,
          sharePct: row.count > 0 ? 100 * t.count / row.count : 0,
          bins: t.bins,
          bounceBins: t.bounceBins,
        }
      })
    let peakBin = 0
    let peakVal = -1
    for (let b = 0; b < timeBins; b++) {
      if (row.bins[b] > peakVal) {
        peakVal = row.bins[b]
        peakBin = b
      }
    }
    const bouncePct = row.count > 0 ? 100 * row.bounces / row.count : 0
    const pingPong = row.pingPong || 0
    const pingPongPct = row.pingPongPct || 0
    const medianDwellNs = row.medianDwellNs || 0
    const shortDwellShare = row.shortDwellShare || 0
    return {
      fromCore: row.fromCore,
      toCore: row.toCore,
      label: row.label,
      count: row.count,
      bounces: row.bounces,
      bouncePct,
      handoffCount: row.bounces,
      handoffPct: bouncePct,
      pingPong,
      pingPongPct,
      medianDwellNs,
      shortDwellShare,
      avgGapNs: row.count > 0 ? Math.floor(row.gapSum / row.count) : 0,
      ratePerS: scopeSec > 0 ? row.count / scopeSec : 0,
      net,
      revCount,
      bins: row.bins,
      bounceBins: row.bounceBins,
      tasks,
      primaryTask: tasks[0] || null,
      peakBin,
      peakCount: Math.max(0, peakVal),
    }
  }).sort((a, b) => b.count - a.count || a.label.localeCompare(b.label))

  const matrixCores = cores

  const taskAggByCore = new Map()
  for (const c of allCorridors) {
    for (const core of [c.fromCore, c.toCore]) {
      let agg = taskAggByCore.get(core)
      if (!agg) {
        agg = new Map()
        taskAggByCore.set(core, agg)
      }
      for (const t of c.tasks) agg.set(t.mk, (agg.get(t.mk) || 0) + t.count)
    }
  }
  const coreStats = matrixCores.map((core, i) => {
    let out = 0
    let inn = 0
    for (let j = 0; j < matrixCores.length; j++) {
      if (i === j) continue
      out += fullGrid[i]?.[j] || 0
      inn += fullGrid[j]?.[i] || 0
    }
    const top3 = [...(taskAggByCore.get(core) || new Map()).entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, 3)
      .map(([mk, count]) => ({ mk, label: taskLabelForMergeKey(trace, mk), count }))
    return {
      core,
      out,
      in: inn,
      net: netMigrationBalance(inn, out),
      topTasks: top3,
    }
  })

  let hotspot = null
  for (const c of allCorridors) {
    const score = c.count + c.bounces * 2
    const offender = c.primaryTask
    if (!hotspot || score > hotspot.score) {
      hotspot = {
        score,
        fromCore: c.fromCore,
        toCore: c.toCore,
        label: c.label,
        count: c.count,
        bounces: c.bounces,
        bouncePct: c.bouncePct,
        peakBin: c.peakBin,
        task: offender,
        summary: offender
          ? `Hotspot: ${offender.label} on ${c.label} (${c.count} mig, ${(c.pingPongPct || 0).toFixed(0)}% ping-pong)`
          : `Hotspot: ${c.label} (${c.count} migrations)`,
      }
    }
  }

  const base = {
    cores: matrixCores,
    allCorridors,
    groupBySource: cores.length > 16,
    timeBins,
    tMin,
    tMax: tHi,
    binW,
    matrix: { cores: matrixCores, grid: fullGrid },
    coreStats,
    hotspot,
  }
  return applyCorridorTopFilter(base, topPct)
}

function reindexCorridorView(model, corridors) {
  const cores = model.cores || []
  const groupBySource = !!(model.groupBySource || cores.length > 16)
  const groups = []
  if (groupBySource) {
    const gmap = new Map()
    for (const c of corridors) {
      if (!gmap.has(c.fromCore)) {
        gmap.set(c.fromCore, {
          source: c.fromCore,
          label: `${coreShortName(c.fromCore)} → Destinations`,
          count: 0,
          corridors: [],
        })
      }
      const g = gmap.get(c.fromCore)
      g.count += c.count
      g.corridors.push(c)
    }
    groups.push(...[...gmap.values()].sort((a, b) => b.count - a.count))
  }
  const pairCount = new Map(corridors.map(c => [`${c.fromCore}\0${c.toCore}`, c.count]))
  const filteredGrid = cores.map((fc, i) => cores.map((tc, j) => {
    if (i === j) return 0
    return pairCount.get(`${fc}\0${tc}`) || 0
  }))
  let maxBin = 0
  for (const c of corridors) {
    for (const v of c.bins || []) if (v > maxBin) maxBin = v
  }
  return {
    ...model,
    corridors,
    groups,
    groupBySource,
    maxBin,
    filteredMatrix: { cores, grid: filteredGrid },
    hasData: corridors.some(c => c.count > 0),
  }
}

/**
 * Re-apply Top-N corridor filter without rescanning migrations.
 * @param {object} model
 * @param {number} topPct
 */
export function applyCorridorTopFilter(model, topPct = 100) {
  if (!model) return emptyCorridorModel()
  const corridors = filterCorridorsByTopPct(model.allCorridors || [], topPct)
  return { ...reindexCorridorView(model, corridors), topPct }
}

/** Re-apply Top-N path count. `topN <= 0` keeps all. */
export function applyCorridorTopNFilter(model, topN = 0) {
  if (!model) return emptyCorridorModel()
  const corridors = filterCorridorsByTopN(model.allCorridors || [], topN)
  return { ...reindexCorridorView(model, corridors), topN, topPct: model.topPct }
}

export function applyCorridorSort(model, sortBy = 'rate', descending = null) {
  if (!model) return emptyCorridorModel()
  const corridors = sortCorridors(model.corridors || [], sortBy, descending)
  return { ...reindexCorridorView(model, corridors), sortBy, sortDesc: descending }
}

/**
 * Narrow corridors to the selected pair's source (egress) or dest (ingress).
 * @param {object} model
 * @param {'all'|'egress'|'ingress'} mode
 * @param {{ fromCore?: string, toCore?: string }|null} selected
 */
export function applyCorridorDirectionFilter(model, mode = 'all', selected = null) {
  if (!model || mode === 'all' || !selected) return model
  const src = model.corridors || []
  let corridors = src
  if (mode === 'egress' && selected.fromCore) {
    corridors = src.filter(c => c.fromCore === selected.fromCore)
  } else if (mode === 'ingress' && selected.toCore) {
    corridors = src.filter(c => c.toCore === selected.toCore)
  } else {
    return model
  }
  if (corridors === src || corridors.length === src.length) {
    const same = corridors.length === src.length
      && corridors.every((c, i) => c === src[i])
    if (same) return model
  }
  return reindexCorridorView(model, corridors)
}

function canonNumericId(token) {
  const t = String(token || '').trim().toLowerCase()
  if (!t) return null
  if (t.startsWith('0x')) {
    const n = Number.parseInt(t, 16)
    return Number.isFinite(n) ? String(n) : null
  }
  if (/^\d+$/.test(t)) return String(Number.parseInt(t, 10))
  return null
}

function corridorTaskIdsAndName(task) {
  const ids = []
  let name = ''
  const addId = (token) => {
    const cid = canonNumericId(token)
    if (cid != null && !ids.includes(cid)) ids.push(cid)
  }
  const consider = (raw) => {
    if (raw == null || raw === '') return
    const s = String(raw)
    const norm = s.replace(/\uFFFD/g, '\0')
    if (norm.charCodeAt(0) === 0) {
      const sep = norm.indexOf('\0', 1)
      if (sep > 0) {
        addId(norm.slice(1, sep))
        if (!name) name = norm.slice(sep + 1)
      }
    }
    const parsed = parseTaskName(s)
    if (parsed.taskId != null && Number.isFinite(parsed.taskId)) {
      addId(String(parsed.taskId))
      if (!name) name = parsed.name
    }
    const collapsed = norm.replace(/\0/g, '')
    const m = /^(\d+)(\D.*)$/.exec(collapsed)
    if (m) {
      addId(m[1])
      if (!name) name = m[2]
    }
  }
  if (task?.taskId != null) addId(String(task.taskId))
  consider(task?.mk)
  consider(task?.label)
  if (!name) name = String(task?.label || '')
  return { ids, name }
}

function corridorTaskQueryHit(task, q) {
  const { ids, name } = corridorTaskIdsAndName(task)
  const qId = canonNumericId(q)
  if (qId != null && /^\d+$/.test(q)) return ids.includes(qId)
  const label = String(task?.label || '').toLowerCase()
  if (label.includes(q)) return true
  if (String(name).toLowerCase().includes(q)) return true
  const mk = String(task?.mk || '')
  if (mk.charCodeAt(0) === 0) return false
  return mk.toLowerCase().includes(q)
}

function corridorRestrictedToTasks(c, tasks) {
  const n = (c.bins || []).length
  const bins = Array(n).fill(0)
  let bounceBins = Array(n).fill(0)
  let count = 0
  let bounces = 0
  let hasTaskBounce = false
  for (const t of tasks) {
    count += t.count || 0
    bounces += t.bounces || 0
    const tb = t.bins || []
    const bb = t.bounceBins || []
    if (bb.length) hasTaskBounce = true
    for (let i = 0; i < n; i++) {
      bins[i] += tb[i] || 0
      bounceBins[i] += bb[i] || 0
    }
  }
  if (!hasTaskBounce) {
    if (!bounces) bounceBins = Array(n).fill(0)
    else if (count && bounces === count) bounceBins = bins.slice()
    else {
      const old = c.bounceBins || []
      bounceBins = bins.map((v, i) => Math.min(old[i] || 0, v))
    }
  }
  const newTasks = tasks.map(t => ({
    ...t,
    sharePct: count ? 100 * (t.count || 0) / count : 0,
  }))
  let peakBin = 0
  let peakVal = 0
  for (let b = 0; b < n; b++) {
    if (bins[b] > peakVal) {
      peakVal = bins[b]
      peakBin = b
    }
  }
  const oldCount = c.count || 0
  const bouncePct = count ? 100 * bounces / count : 0
  const scale = oldCount ? count / oldCount : 1
  return {
    ...c,
    count,
    bounces,
    bouncePct,
    handoffCount: bounces,
    handoffPct: bouncePct,
    pingPong: Math.round((c.pingPong || 0) * scale),
    pingPongPct: c.pingPongPct || 0,
    ratePerS: oldCount ? (c.ratePerS || 0) * scale : 0,
    bins,
    bounceBins,
    tasks: newTasks,
    primaryTask: newTasks[0] || null,
    peakBin,
    peakCount: peakVal,
  }
}

function recomputeCorridorNets(corridors) {
  const byPair = new Map(corridors.map(c => [`${c.fromCore}\0${c.toCore}`, c]))
  return corridors.map((c) => {
    const rev = byPair.get(`${c.toCore}\0${c.fromCore}`)
    const revCount = rev ? (rev.count || 0) : 0
    const net = netMigrationBalance(revCount, c.count || 0)
    if (revCount === c.revCount && net === c.net) return c
    return { ...c, revCount, net }
  })
}

/**
 * Keep corridors that have a matching task; drop sibling tasks from hits.
 * Decimal queries are exact ids (`28` ≠ `CS[128]`).
 * @param {object[]} corridors
 * @param {string} query
 */
export function filterCorridorsByTaskQuery(corridors, query) {
  const q = String(query || '').trim().toLowerCase()
  if (!q) return corridors || []
  const out = []
  for (const c of corridors || []) {
    const tasks = c.tasks || []
    const matched = tasks.filter(t => corridorTaskQueryHit(t, q))
    if (!matched.length) continue
    out.push(matched.length === tasks.length ? c : corridorRestrictedToTasks(c, matched))
  }
  return recomputeCorridorNets(out)
}

/**
 * In-inspector custom task filter (TODO2 §3.1).
 * Searches allCorridors so Top-N cannot hide a matching task.
 * @param {object} model
 * @param {string} query
 */
export function applyCorridorTaskFilter(model, query) {
  if (!model) return model
  const q = String(query || '').trim()
  if (!q) return model
  const src = model.allCorridors || model.corridors || []
  const corridors = filterCorridorsByTaskQuery(src, q)
  if (corridors.length === src.length && corridors.every((c, i) => c === src[i])) {
    return model
  }
  return reindexCorridorView(model, corridors)
}

function attachCorridorPathMetrics(byKey, migrations, timeScale) {
  const window = MIGRATION_PING_PONG_WINDOW
  const shortTh = corridorShortDwellThreshold(timeScale)
  const byMk = new Map()
  for (const m of migrations || []) {
    if (!m?.mergeKey) continue
    if (!byMk.has(m.mergeKey)) byMk.set(m.mergeKey, [])
    byMk.get(m.mergeKey).push(m)
  }
  const ping = new Map()
  const dwells = new Map()
  for (const list of byMk.values()) {
    const ordered = [...list].sort((a, b) => a.ns - b.ns)
    for (let i = 0; i < ordered.length; i++) {
      const m = ordered[i]
      const key = `${m.fromCore}\0${m.toCore}`
      const next = ordered[i + 1]
      if (next) {
        const dwell = Math.max(0, next.ns - m.ns)
        if (!dwells.has(key)) dwells.set(key, [])
        dwells.get(key).push(dwell)
      }
    }
    for (let i = 1; i < ordered.length; i++) {
      const a = ordered[i - 1]
      const b = ordered[i]
      if (b.ns - a.ns > window) continue
      if (a.toCore === b.fromCore && a.fromCore === b.toCore) {
        const key = `${a.fromCore}\0${a.toCore}`
        ping.set(key, (ping.get(key) || 0) + 1)
      }
    }
  }
  for (const [key, row] of byKey) {
    const p = ping.get(key) || 0
    const samples = dwells.get(key) || []
    row.pingPong = p
    row.pingPongPct = row.count ? 100 * p / row.count : 0
    const sorted = [...samples].sort((a, b) => a - b)
    row.medianDwellNs = sorted.length ? sorted[Math.floor(sorted.length / 2)] : 0
    row.shortDwellShare = samples.length
      ? 100 * samples.filter(d => d < shortTh).length / samples.length
      : 0
  }
}

function loadBalanceStatus(trace, lo, hi) {
  if (!trace) return { label: 'Not evaluated', zone: null, score: null, sigma: null }
  const rows = buildCoreTimeBreakdown(trace, lo, hi)
  const pcts = rows.map(r => (r.spanNs > 0 ? 100 * r.activeNs / r.spanNs : 0))
  const lb = loadBalanceMetrics(pcts)
  if (!lb) return { label: 'Not evaluated', zone: null, score: null, sigma: null }
  const zone = classifyLoadBalance(lb.score, lb.stddev)
  return {
    label: zone === 'ok' ? 'Balanced' : 'Imbalanced',
    zone,
    score: lb.score,
    sigma: lb.stddev,
  }
}

export function classifyCorridorConcern(corridor) {
  if (!corridor) return { id: 'none', label: 'None', detail: '' }
  const ping = Number(corridor.pingPongPct) || 0
  const short = Number(corridor.shortDwellShare) || 0
  const handoff = Number(corridor.handoffPct ?? corridor.bouncePct) || 0
  const burst = corridor.count > 0
    ? 100 * (corridor.peakCount || 0) / corridor.count
    : 0
  const candidates = [
    { id: 'pingpong', label: 'Ping-pong', score: ping, min: 40, need: corridor.pingPong != null },
    { id: 'dwell', label: 'Short dwell', score: short, min: 50, need: corridor.shortDwellShare != null },
    { id: 'burst', label: 'Burst', score: burst, min: 40, need: corridor.peakCount != null },
    { id: 'handoff', label: 'Handoff suspect', score: handoff, min: CORRIDOR_HANDOFF_HATCH_PCT, need: corridor.bounces != null },
  ].filter(c => c.need)
  candidates.sort((a, b) => b.score - a.score)
  const best = candidates.find(c => c.score >= c.min)
  if (!best) return { id: 'none', label: 'None', detail: '' }
  const task = corridor.primaryTask
  let detail = ''
  if (best.id === 'pingpong' && task) {
    detail = `${task.label} repeatedly moves between ${corridor.fromCore} and ${corridor.toCore}`
  } else if (best.id === 'burst') {
    detail = `${corridor.label} concentrates migrations in a short window`
  } else if (best.id === 'dwell' && task) {
    detail = `${task.label} leaves ${corridor.toCore} after a short dwell`
  } else if (best.id === 'handoff') {
    detail = `Repeated synchronization ownership changes associated with ${corridor.label}`
  } else if (task) {
    detail = `${task.label} on ${corridor.label}`
  } else {
    detail = corridor.label
  }
  return { id: best.id, label: best.label, detail }
}

export function buildCorridorOverview(trace, model, scope = {}) {
  const corridors = model?.allCorridors || model?.corridors || []
  const lo = scope.lo ?? null
  const hi = scope.hi ?? null
  const total = corridors.reduce((s, c) => s + (c.count || 0), 0)
  const rate = corridors.reduce((s, c) => s + (c.ratePerS || 0), 0)
  const lb = loadBalanceStatus(trace, lo, hi)
  const hottest = [...corridors].sort((a, b) => (b.count || 0) - (a.count || 0))[0] || null
  const taskTotals = new Map()
  for (const c of corridors) {
    for (const t of c.tasks || []) {
      const cur = taskTotals.get(t.mk) || { mk: t.mk, label: t.label, count: 0 }
      cur.count += t.count || 0
      taskTotals.set(t.mk, cur)
    }
  }
  const topTask = [...taskTotals.values()].sort((a, b) => b.count - a.count)[0] || null
  const share = topTask && total ? 100 * topTask.count / total : 0
  const concern = classifyCorridorConcern(hottest)
  const hottestLabel = hottest
    ? `${hottest.fromCore} → ${hottest.toCore}`
    : '—'
  const rateLabel = total ? `${rate.toFixed(1)}/s` : '—'
  const scopeLabel = scope.label || 'Full Trace'
  const headline = `Scope: ${scopeLabel} · Load balance: ${lb.label} · ${total.toLocaleString()} migrations`
  return {
    scopeLabel,
    scopeDetail: scope.detail || '',
    loadBalance: lb.label,
    loadBalanceZone: lb.zone,
    loadBalanceScore: lb.score,
    migrations: total,
    migrationRate: rate,
    migrationRateLabel: rateLabel,
    mostAffectedTask: topTask,
    mostAffectedShare: share,
    hottestPath: hottestLabel,
    hottestCorridor: hottest,
    mainConcern: concern.label,
    mainConcernId: concern.id,
    mainConcernDetail: concern.detail,
    headline,
    evaluated: lb.label !== 'Not evaluated',
  }
}

export function buildCorridorEvidence(corridor, opts = {}) {
  if (!corridor) return null
  const scale = opts.timeScale || 'ns'
  const fmt = opts.formatTimeFn || formatTime
  const task = opts.selectedTask || corridor.primaryTask
  const concern = classifyCorridorConcern(corridor)
  const median = corridor.medianDwellNs
    ? fmt(corridor.medianDwellNs, scale)
    : '—'
  const window = opts.binLo != null && opts.binHi != null
    ? `range:${opts.binLo}/${opts.binHi}`
    : (opts.scopeLabel || 'full trace')
  const lines = [
    { key: 'Migration volume', value: String(corridor.count ?? 0) },
    { key: 'Rate', value: `${(corridor.ratePerS || 0).toFixed(1)}/s` },
    { key: 'Ping-pong', value: corridor.pingPongPct != null ? `${corridor.pingPongPct.toFixed(0)}%` : '—' },
    { key: 'Median dwell', value: median },
    { key: 'Short-dwell share', value: corridor.shortDwellShare != null ? `${corridor.shortDwellShare.toFixed(0)}%` : '—' },
    { key: 'Handoff suspects', value: corridor.bounces != null ? `${corridor.bounces} (${(corridor.handoffPct ?? corridor.bouncePct ?? 0).toFixed(0)}%)` : '—' },
    { key: 'Top migrating task', value: task ? `${task.label} · ${(task.sharePct || 0).toFixed(0)}%` : '—' },
    { key: 'Evidence window', value: window },
  ]
  return {
    title: `${corridor.fromCore} → ${corridor.toCore}`,
    label: corridor.label,
    fromCore: corridor.fromCore,
    toCore: corridor.toCore,
    lines,
    assessment: concern.detail || 'No dominant migration condition on this path.',
    concern,
    evidenceQuality: {
      direct: 'migration events',
      correlated: 'synchronization handoffs',
      limitation: 'Handoff association is a heuristic, not a measured cache-line transfer.',
    },
    task,
  }
}

export function buildCorridorAiContext({
  scope,
  corridor,
  task,
  bin,
  overview,
  inspectorFilters,
  timeScale,
} = {}) {
  const scale = timeScale || scope?.unit || 'ns'
  const lines = [
    `Analysis scope: ${scope?.label || 'Full Trace'}`,
    `Trace unit: ${scale}`,
    scope?.detail ? `Scope range: ${scope.detail}` : null,
    corridor ? `Selected core path: ${corridor.fromCore} → ${corridor.toCore}` : 'Selected core path: none',
    task ? `Selected task: ${task.label}` : 'Selected task: none',
    bin?.label ? `Selected time bin: ${bin.label}` : 'Selected time bin: none',
    corridor ? `Migrations: ${corridor.count} (${(corridor.ratePerS || 0).toFixed(1)}/s)` : null,
    corridor && corridor.pingPongPct != null ? `Ping-pong: ${corridor.pingPongPct.toFixed(0)}%` : null,
    corridor && corridor.medianDwellNs != null
      ? `Median dwell: ${formatTime(corridor.medianDwellNs, scale)}`
      : null,
    corridor && corridor.shortDwellShare != null
      ? `Short-dwell share: ${corridor.shortDwellShare.toFixed(0)}%`
      : null,
    corridor
      ? `Handoff suspects: ${corridor.bounces || 0} (${(corridor.handoffPct ?? corridor.bouncePct ?? 0).toFixed(0)}%). Heuristic synchronization association, not a measured cache-line transfer.`
      : null,
    overview ? `Load balance: ${overview.loadBalance}` : null,
    inspectorFilters ? `Inspector filters: ${inspectorFilters}` : 'Inspector filters: none',
    'Do not automatically filter the timeline or change cursors unless the user explicitly selects a viewer action.',
  ]
  return lines.filter(Boolean).join('\n')
}

function emptyCorridorModel(timeBins = 32) {
  return {
    cores: [],
    corridors: [],
    allCorridors: [],
    groups: [],
    groupBySource: false,
    topPct: 100,
    timeBins,
    tMin: 0,
    tMax: 0,
    binW: 0,
    maxBin: 0,
    matrix: { cores: [], grid: [] },
    filteredMatrix: { cores: [], grid: [] },
    coreStats: [],
    hotspot: null,
    hasData: false,
    topN: 0,
    sortBy: 'rate',
  }
}

/**
 * Per-core time breakdown: active / idle / tick / gap.
 * Returns [{core, activeNs, idleNs, tickNs, gapNs, spanNs}]
 */
export function buildCoreTimeBreakdown(trace, lo = null, hi = null) {
  const effLo = lo ?? trace.timeMin
  const effHi = hi ?? trace.timeMax
  const span = Math.max(effHi - effLo, 1)
  return (trace.coreNames ?? []).map(core => {
    const segs = (trace.coreSegs instanceof Map ? trace.coreSegs.get(core) : trace.coreSegs?.[core]) ?? []
    let activeNs = 0, idleNs = 0, tickNs = 0, segTotal = 0
    for (const s of segs) {
      const slo = Math.max(s.start, effLo)
      const shi = Math.min(s.end, effHi)
      if (slo >= shi) continue
      const dur = shi - slo
      const { name } = parseTaskName(s.task)
      if (isIdleTaskName(name)) idleNs += dur
      else if (name === 'TICK') tickNs += dur
      else activeNs += dur
      segTotal += dur
    }
    return { core, activeNs, idleNs, tickNs, gapNs: Math.max(0, span - segTotal), spanNs: span }
  })
}
