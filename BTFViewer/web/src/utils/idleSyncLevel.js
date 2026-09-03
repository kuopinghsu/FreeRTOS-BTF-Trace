/**
 * Idle + fill-level statistics (parity with parser.py):
 *   Idle Analysis                    — review item A5
 *   Queue Backlog / Semaphore Level  — review item A8
 */
import { isIdleTaskName, parseTaskName } from './colors.js'
import { parseSyncObjectNote, syncObjectKey } from './syncObjectAnalysis.js'

function nearestRank(sorted, p) {
  if (!sorted.length) return 0
  return sorted[Math.min(sorted.length - 1, Math.max(0, Math.ceil(p * sorted.length) - 1))]
}

/** Per-core idle analysis + longest all-cores-idle window — parity with
 * `_idle_analysis_rows` (A5).
 * @returns {{rows: Array<{core,totalNs,longestNs,longestStartNs,fragments,p95Ns}>,
 *            allIdleSpanNs: number, allIdleStartNs: number}}
 */
export function idleAnalysisRows(trace, lo = null, hi = null) {
  const effLo = lo != null ? lo : (trace?.timeMin ?? 0)
  const effHi = hi != null ? hi : (trace?.timeMax ?? 0)
  const cores = [...(trace?.coreNames || [])]
  const idleByCore = new Map()
  const rows = []
  for (const core of cores) {
    const spans = []
    for (const seg of (trace?.coreSegs?.get?.(core) || [])) {
      const slo = Math.max(Math.trunc(seg.start), effLo)
      const shi = Math.min(Math.trunc(seg.end), effHi)
      if (slo >= shi) continue
      if (isIdleTaskName(parseTaskName(seg.task).name)) spans.push([slo, shi])
    }
    idleByCore.set(core, spans)
    if (!spans.length) continue
    const durs = spans.map(([a, b]) => b - a).sort((x, y) => x - y)
    let longest = spans[0]
    for (const s of spans) if (s[1] - s[0] > longest[1] - longest[0]) longest = s
    rows.push({
      core,
      totalNs: durs.reduce((s, d) => s + d, 0),
      longestNs: longest[1] - longest[0],
      longestStartNs: longest[0],
      fragments: spans.length,
      p95Ns: nearestRank(durs, 0.95),
    })
  }
  rows.sort((a, b) => b.totalNs - a.totalNs || a.core.localeCompare(b.core))

  let allIdleSpanNs = 0
  let allIdleStartNs = effLo
  if (cores.length && cores.every(c => (idleByCore.get(c) || []).length)) {
    const evts = []
    for (const c of cores) {
      for (const [a, b] of idleByCore.get(c)) {
        evts.push([a, 1])
        evts.push([b, -1])
      }
    }
    evts.sort((x, y) => x[0] - y[0] || x[1] - y[1])
    let active = 0
    let segStart = null
    const n = cores.length
    for (const [t, delta] of evts) {
      if (segStart != null && active === n && t > segStart && t - segStart > allIdleSpanNs) {
        allIdleSpanNs = t - segStart
        allIdleStartNs = segStart
      }
      active += delta
      segStart = active === n ? t : null
    }
  }
  return { rows, allIdleSpanNs, allIdleStartNs }
}

/** Running fill level of every queue / semaphore — parity with
 * `_sync_level_rows` (A8).
 * @returns {Array<{key,kind,ptr,label,maxLevel,timeAtMaxNs,endLevel,starved}>}
 */
export function syncLevelRows(trace, lo = null, hi = null) {
  const byTgt = trace?.stiEventsByTarget
  const seq = new Map()
  const meta = new Map()
  for (const tgt of ['queue', 'sem']) {
    for (const ev of (byTgt?.get?.(tgt) || [])) {
      if (lo != null && hi != null && !(ev.time >= lo && ev.time <= hi)) continue
      const parsed = parseSyncObjectNote(ev.note)
      if (!parsed || parsed.action === 'delete') continue
      const key = syncObjectKey(tgt, parsed.ptr)
      if (!meta.has(key)) meta.set(key, [tgt, parsed.ptr])
      const delta = (parsed.action === 'give' || parsed.action === 'send') ? 1
        : (parsed.action === 'take' || parsed.action === 'recv') ? -1 : 0
      if (!seq.has(key)) seq.set(key, [])
      seq.get(key).push([ev.time, delta])
    }
  }
  const effHi = hi != null ? hi : (trace?.timeMax ?? 0)
  const rows = []
  for (const [key, evts] of seq) {
    evts.sort((a, b) => a[0] - b[0])
    let lvl = 0
    let maxLevel = 0
    let starved = 0
    for (const [, d] of evts) {
      if (d === 0) lvl = 0
      else if (d < 0 && lvl === 0) starved += 1
      else { lvl = Math.max(0, lvl + d); maxLevel = Math.max(maxLevel, lvl) }
    }
    lvl = 0
    let timeAtMaxNs = 0
    let lastT = evts[0][0]
    for (const [t, d] of evts) {
      if (t > lastT && lvl === maxLevel && maxLevel > 0) timeAtMaxNs += t - lastT
      lastT = t
      if (d === 0) lvl = 0
      else if (d < 0 && lvl === 0) { /* starved: level unchanged */ }
      else lvl = Math.max(0, lvl + d)
    }
    if (effHi > lastT && lvl === maxLevel && maxLevel > 0) timeAtMaxNs += effHi - lastT
    const [kind, ptr] = meta.get(key)
    rows.push({ key, kind, ptr, label: `${kind} ${ptr}`, maxLevel, timeAtMaxNs, endLevel: lvl, starved })
  }
  rows.sort((a, b) => b.maxLevel - a.maxLevel || b.starved - a.starved || a.label.localeCompare(b.label))
  return rows
}
