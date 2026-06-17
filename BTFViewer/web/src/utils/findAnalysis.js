/**
 * Find panel logic (parity with desktop _recompute_find_hits).
 */

import { bisectLeft, bisectRight } from './bisect.js'
import { taskLabelForMergeKey, taskReprGet } from './colors.js'

export const FIND_MODES = ['contains', 'exact', 'regex', 'migrations']

/**
 * @param {object} trace
 * @param {string} query
 * @param {'contains'|'exact'|'regex'|'migrations'} mode
 * @param {object[]} [annotations]
 * @returns {{ hits: number[], error: string|null }}
 */
export function computeFindHits(trace, query, mode, annotations = []) {
  if (!trace || !query?.trim()) return { hits: [], error: null }
  const q = query.trim()
  const modeKey = (mode || 'contains').toLowerCase()

  if (modeKey === 'migrations') {
    const qLower = q.toLowerCase()
    const hits = []
    for (const m of trace.migrations || []) {
      const raw = taskReprGet(trace, m.mergeKey) || m.mergeKey
      const disp = taskLabelForMergeKey(trace, m.mergeKey)
      const hay = `${m.mergeKey} ${raw} ${disp} ${m.fromCore} ${m.toCore}`.toLowerCase()
      if (!qLower
          || hay.includes(qLower)
          || m.fromCore.toLowerCase().includes(qLower)
          || m.toCore.toLowerCase().includes(qLower)) {
        hits.push(m.ns)
      }
    }
    return { hits: [...new Set(hits)].sort((a, b) => a - b), error: null }
  }

  let regexObj = null
  if (modeKey === 'regex') {
    try {
      regexObj = new RegExp(q, 'i')
    } catch {
      return { hits: [], error: 'Regex error' }
    }
  }

  const hits = []
  const qLower = q.toLowerCase()
  for (const [mk, segs] of trace.segByMergeKey || []) {
    const raw = taskReprGet(trace, mk) || mk
    const disp = taskLabelForMergeKey(trace, mk)
    const hay = `${mk} ${raw} ${disp}`
    let matched = false
    if (modeKey === 'exact') {
      matched = qLower === mk.toLowerCase() || qLower === raw.toLowerCase() || qLower === disp.toLowerCase()
    } else if (modeKey === 'contains') {
      matched = hay.toLowerCase().includes(qLower)
    } else if (regexObj) {
      matched = regexObj.test(hay)
    }
    if (matched) {
      for (const s of segs) hits.push(s.start)
    }
  }
  for (const ann of annotations || []) {
    const hay = ann.label || ann.note || ''
    if (!hay) continue
    let matched = false
    if (modeKey === 'exact') matched = qLower === hay.toLowerCase()
    else if (modeKey === 'contains') matched = hay.toLowerCase().includes(qLower)
    else if (regexObj) matched = regexObj.test(hay)
    if (matched) hits.push(ann.ns)
  }
  return { hits: [...new Set(hits)].sort((a, b) => a - b), error: null }
}

/** Step find index forward/back from viewport centre or current index. */
export function stepFindHitIndex(hits, currentIdx, centerNs, forward) {
  if (!hits?.length) return -1
  const n = hits.length
  if (currentIdx < 0) {
    if (forward) return bisectRight(hits, centerNs) % n
    return (bisectLeft(hits, centerNs) - 1 + n) % n
  }
  return forward ? (currentIdx + 1) % n : (currentIdx - 1 + n) % n
}
