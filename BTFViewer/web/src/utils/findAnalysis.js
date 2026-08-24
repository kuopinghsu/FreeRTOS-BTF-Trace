/**
 * Find panel logic (parity with desktop find_logic.py).
 */

import { bisectLeft, bisectRight } from './bisect.js'
import { taskLabelForMergeKey, taskReprGet } from './colors.js'
import { parseTaskLifecycleNote } from './lifecycleAnalysis.js'
import { parseSyncObjectNote } from './syncObjectAnalysis.js'

export const FIND_MODES = [
  'contains', 'exact', 'regex', 'migrations',
  'sti', 'intervals', 'lifecycle', 'pointers',
]

/** Keep order/help in sync with desktop find_logic.FIND_MODE_CHOICES. */
export const FIND_MODE_CHOICES = [
  {
    label: 'Contains',
    key: 'contains',
    help: 'Substring match on task names (merge key / display name) and annotation notes.',
  },
  {
    label: 'Exact',
    key: 'exact',
    help: 'Whole-string match on a task merge key, raw name, or display name.',
  },
  {
    label: 'Regex',
    key: 'regex',
    help: 'Case-insensitive regular expression on task names and annotation notes.',
  },
  {
    label: 'Migrations',
    key: 'migrations',
    help: 'Core-migration boundaries. Match a task name or a core (from / to), e.g. Core_0 or CS[22].',
  },
  {
    label: 'STI',
    key: 'sti',
    help: 'Software-trace items: channel, event verb, note, and core (tags, TICK, mutex notes, …).',
  },
  {
    label: 'Intervals',
    key: 'intervals',
    help: 'Paired interval_start / interval_stop spans and interval STI notes (id, task, times).',
  },
  {
    label: 'Lifecycle',
    key: 'lifecycle',
    help: 'Task create / delete / suspend / resume STI notes on the task channel.',
  },
  {
    label: 'Pointers',
    key: 'pointers',
    help: 'Mutex, semaphore, and queue object pointers (0x…) and sync-object notes.',
  },
]

const FIND_MODE_ALIASES = {
  'sti events': 'sti',
  'sti event': 'sti',
  tags: 'sti',
  tag: 'sti',
}

export function normalizeFindMode(mode) {
  let key = String(mode || '').trim().toLowerCase()
  key = FIND_MODE_ALIASES[key] || key
  return FIND_MODES.includes(key) ? key : 'contains'
}

export function findModeHelp(mode) {
  const want = normalizeFindMode(mode)
  return FIND_MODE_CHOICES.find(o => o.key === want)?.help || FIND_MODE_CHOICES[0].help
}

/**
 * Status line for the Find panel (desktop find_logic / step wording).
 * @param {{ hitCount?: number, hitIndex?: number, mode?: string, query?: string, error?: string }} opts
 */
export function formatFindStatus({
  hitCount = 0,
  hitIndex = -1,
  mode = 'contains',
  query = '',
  error = '',
} = {}) {
  if (error) return String(error)
  const q = String(query || '').trim()
  if (!q) return '0 matches'
  const n = Number(hitCount) || 0
  // "k of N matches" — matches the Step-1 canonical Find status wording.
  if (hitIndex >= 0 && n > 0) return `${hitIndex + 1} of ${n} matches`
  const modeKey = normalizeFindMode(mode)
  if (n === 0) {
    const label = modeKey === 'migrations' ? '0 migration matches' : '0 matches'
    return `${label} for "${q}"`
  }
  if (modeKey === 'migrations') {
    return `${n} migration matches`
  }
  return `${n} matches`
}

const MAX_REGEX_LEN = 200

function haystackMatches(query, mode, haystack, regexObj) {
  const qLower = query.toLowerCase()
  if (mode === 'exact') return qLower === haystack.toLowerCase()
  if (mode === 'contains') return haystack.toLowerCase().includes(qLower)
  if (regexObj) return regexObj.test(haystack)
  return false
}

function findStiHits(trace, query, mode, regexObj) {
  const hits = []
  const qLower = query.toLowerCase()
  for (const ev of trace.stiEvents || []) {
    const hay = `${ev.target} ${ev.event || ''} ${ev.note || ''} ${ev.core || ''}`
    let matched = false
    if (mode === 'exact') matched = hay.toLowerCase() === qLower
    else if (mode === 'contains') matched = hay.toLowerCase().includes(qLower)
    else if (regexObj) matched = regexObj.test(hay)
    if (matched) hits.push(ev.time)
  }
  return hits
}

function findIntervalHits(trace, query, mode, regexObj) {
  const hits = []
  for (const inst of trace.intervalInstances || []) {
    const hay = `${inst.id || ''} ${inst.taskId || ''} ${inst.startNs} ${inst.stopNs}`
    if (haystackMatches(query, mode, hay, regexObj)) {
      hits.push(inst.startNs, inst.stopNs)
    }
  }
  for (const ev of trace.stiEvents || []) {
    if (!ev.target?.startsWith?.('interval_')) continue
    const hay = `${ev.target} ${ev.note || ''}`
    if (haystackMatches(query, mode, hay, regexObj)) hits.push(ev.time)
  }
  return hits
}

function findLifecycleHits(trace, query, mode, regexObj) {
  const hits = []
  for (const ev of trace.stiEvents || []) {
    if (ev.target !== 'task') continue
    const parsed = parseTaskLifecycleNote(ev.note)
    if (!parsed) continue
    const hay = `${parsed.action} ${parsed.label} ${ev.note || ''}`
    if (haystackMatches(query, mode, hay, regexObj)) hits.push(ev.time)
  }
  return hits
}

function findPointerHits(trace, query, mode, regexObj) {
  const hits = []
  const q = query.trim()
  for (const ev of trace.stiEvents || []) {
    const parsed = parseSyncObjectNote(ev.note)
    const ptr = parsed?.ptr || ''
    const hay = `${ev.target} ${ev.note || ''} ${ptr}`
    let matched = false
    if (mode === 'exact') {
      matched = ptr.toLowerCase() === q.toLowerCase() || (ev.note || '').toLowerCase() === q.toLowerCase()
    } else if (mode === 'contains') {
      matched = hay.toLowerCase().includes(q.toLowerCase())
    } else if (regexObj) {
      matched = regexObj.test(hay)
    }
    if (matched) hits.push(ev.time)
  }
  return hits
}

/**
 * @param {object} trace
 * @param {string} query
 * @param {string} mode
 * @param {object[]} [annotations]
 * @returns {{ hits: number[], error: string|null }}
 */
export function computeFindHits(trace, query, mode, annotations = []) {
  if (!trace || !query?.trim()) return { hits: [], error: null }
  const q = query.trim()
  const modeKey = normalizeFindMode(mode)

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
    if (q.length > MAX_REGEX_LEN) return { hits: [], error: 'Regex too long' }
    try {
      regexObj = new RegExp(q, 'i')
    } catch {
      return { hits: [], error: 'Regex error' }
    }
  }

  if (modeKey === 'sti') {
    return { hits: [...new Set(findStiHits(trace, q, 'contains', regexObj))].sort((a, b) => a - b), error: null }
  }
  if (modeKey === 'intervals') {
    return { hits: [...new Set(findIntervalHits(trace, q, 'contains', regexObj))].sort((a, b) => a - b), error: null }
  }
  if (modeKey === 'lifecycle') {
    return { hits: [...new Set(findLifecycleHits(trace, q, 'contains', regexObj))].sort((a, b) => a - b), error: null }
  }
  if (modeKey === 'pointers') {
    return { hits: [...new Set(findPointerHits(trace, q, 'contains', regexObj))].sort((a, b) => a - b), error: null }
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
