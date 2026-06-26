/**
 * Core migration analysis (parity with desktop btf_viewer.py).
 */

import { bisectLeft, bisectRight } from './bisect.js'
import { parseTaskName, taskLabelForMergeKey, taskReprGet } from './colors.js'
import { computeFindHits } from './findAnalysis.js'
import { blockingTimeSamples } from './statsAnalysis.js'
import { segFullyInRange, segOverlapsRange } from './statsRange.js'
import { formatMigrationGapTime, formatTime } from './timeFormat.js'

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
  return taskCoresUsed(trace, mergeKey).size >= 2
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
  return { migrations, migrationsByMk }
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
  if (!migs?.length || !trace.stiEvents?.length) return 0
  const stiTimes = trace.stiEvents.map(e => e.time).sort((a, b) => a - b)
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

export function traceIsMultiCore(trace) {
  return (trace?.coreNames?.length ?? 0) >= 2
}

/** Above this core count, heatmap level-0 uses a core×core matrix instead of pair×time rows. */
export const MIGRATION_HEATMAP_MATRIX_CORE_THRESHOLD = 16

export function migrationHeatmapUsesMatrix(trace) {
  return (trace?.coreNames?.length ?? 0) > MIGRATION_HEATMAP_MATRIX_CORE_THRESHOLD
}

/** Source × destination core counts for large traces (one overview row per source core). */
export function migrationHeatmapMatrix(trace, lo = null, hi = null) {
  if (!trace) return { cores: [], grid: [] }
  const cores = trace.coreNames || []
  const n = cores.length
  const coreIndex = new Map(cores.map((c, i) => [c, i]))
  const grid = Array.from({ length: n }, () => Array(n).fill(0))
  for (const m of trace.migrations || []) {
    if (lo != null && m.ns < lo) continue
    if (hi != null && m.ns > hi) continue
    const fi = coreIndex.get(m.fromCore)
    const ti = coreIndex.get(m.toCore)
    if (fi == null || ti == null || fi === ti) continue
    grid[fi][ti]++
  }
  return { cores, grid }
}

/** Time bins for all outgoing pairs from one source core (matrix row drill-down). */
export function migrationCoreOutgoingHeatmap(trace, fromCore, lo = null, hi = null, timeBins = 32) {
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
  for (const m of trace.migrations || []) {
    if (m.fromCore !== fromCore) continue
    if (lo != null && m.ns < lo) continue
    if (hi != null && m.ns > hi) continue
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
  for (const m of trace.migrations || []) {
    if (m.fromCore !== fromCore || m.toCore !== toCore) continue
    if (lo != null && m.ns < lo) continue
    if (hi != null && m.ns > hi) continue
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
export function migrationHeatmapGrid(trace, lo = null, hi = null, timeBins = 32) {
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
  for (const m of trace.migrations || []) {
    if (lo != null && m.ns < lo) continue
    if (hi != null && m.ns > hi) continue
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
  for (const m of trace.migrations || []) {
    if (m.fromCore !== fromCore || m.toCore !== toCore) continue
    if (!migrationNsInBin(m.ns, binLo, binHi, binIndex, timeBins)) continue
    keys.add(m.mergeKey)
  }
  return [...keys]
}

/** Task rows × sub-bins for one core-pair / time-bin drill-down. */
export function migrationTaskHeatmapGrid(trace, fromCore, toCore, binLo, binHi,
                                         timeBins = 32, parentBinIndex = 0,
                                         parentTimeBins = 32) {
  if (!trace) return { rows: [], timeBins, tMin: binLo, tMax: binHi, binW: 0 }
  const tMin = binLo
  const tHi = binHi
  const span = Math.max(tHi - tMin, 1)
  const binW = span / timeBins
  const taskBins = new Map()
  for (const m of trace.migrations || []) {
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
  const rows = items.map(([mk, grid]) => ({
    mk,
    label: taskLabelForMergeKey(trace, mk),
    grid,
  }))
  return { rows, timeBins, binW, tMin, tMax: tHi }
}
