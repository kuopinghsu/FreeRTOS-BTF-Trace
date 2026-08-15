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
  for (const m of migrationsInRange(trace, lo, hi)) {
    if (bounceOnly && !bounceNs.has(m.ns)) continue
    if (m.fromCore === m.toCore) continue
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
    return {
      fromCore: row.fromCore,
      toCore: row.toCore,
      label: row.label,
      count: row.count,
      bounces: row.bounces,
      bouncePct: row.count > 0 ? 100 * row.bounces / row.count : 0,
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
          ? `Hotspot: ${offender.label} on ${c.label} (${c.count} mig, ${c.bouncePct.toFixed(0)}% bounce)`
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
  return {
    ...c,
    count,
    bounces,
    bouncePct: count ? 100 * bounces / count : 0,
    ratePerS: oldCount ? (c.ratePerS || 0) * count / oldCount : 0,
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
