/**
 * Core migration analysis (parity with desktop btf_viewer.py).
 */

import { bisectLeft, bisectRight } from './bisect.js'
import { parseTaskName, taskLabelForMergeKey, taskReprGet } from './colors.js'
import { blockingTimeSamples } from './statsAnalysis.js'
import { segFullyInRange, segOverlapsRange } from './statsRange.js'
import { formatMigrationGapTime } from '../renderer/TimelineRenderer.js'

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
    if (total <= 0) continue
    let primary = [...coreTime.entries()].sort((a, b) => b[1] - a[1])[0][0]
    const primaryPct = 100 * coreTime.get(primary) / total
    const gapsAfter = migs.filter(m => m.gapNs > 0).map(m => m.gapNs)
    const allGaps = blockingTimeSamples(segs, lo, hi)
    const avgAfter = gapsAfter.length ? gapsAfter.reduce((a, b) => a + b, 0) / gapsAfter.length : 0
    const avgOther = allGaps.length ? allGaps.reduce((a, b) => a + b, 0) / allGaps.length : 0
    rows.push({
      mk,
      name: taskLabelForMergeKey(trace, mk),
      migrations: migs.length,
      coreCount: coreTime.size,
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
  const q = (query || '').trim().toLowerCase()
  const hits = []
  for (const m of trace.migrations || []) {
    const raw = taskReprGet(trace, m.mergeKey) || m.mergeKey
    const disp = taskLabelForMergeKey(trace, m.mergeKey)
    const hay = `${m.mergeKey} ${raw} ${disp} ${m.fromCore} ${m.toCore}`.toLowerCase()
    if (!q || hay.includes(q)) hits.push(m.ns)
  }
  return [...new Set(hits)].sort((a, b) => a - b)
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

/** Core-pair rows × time bins for migration heatmap popup. */
export function migrationHeatmapGrid(trace, lo = null, hi = null, timeBins = 32) {
  if (!trace) return { pairs: [], grid: [], timeBins, tMin: 0, tMax: 0 }
  const cores = trace.coreNames || []
  const pairs = []
  for (const fc of cores) {
    for (const tc of cores) {
      if (fc !== tc) {
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
    const pi = pairs.findIndex(p => p.from === m.fromCore && p.to === m.toCore)
    if (pi < 0) continue
    const bi = Math.min(timeBins - 1, Math.max(0, Math.floor((m.ns - tMin) / binW)))
    grid[pi][bi]++
  }
  return { pairs, grid, binW, tMin, timeBins }
}
