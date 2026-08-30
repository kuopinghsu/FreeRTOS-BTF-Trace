/** Task row filtering (parity with desktop TimelineScene filter helpers). */

import { taskDisplayName, taskMergeKey, parseTaskName } from './colors.js'
import { isMigratedTask } from './migrationAnalysis.js'

export function normalizeTaskFilterText(text) {
  return (text || '').trim().toLowerCase()
}

export function mergeKeyMatchesTextFilter(trace, mk, q) {
  if (!q) return true
  const raw = (typeof trace?.taskRepr?.get === 'function' ? trace.taskRepr.get(mk) : null) || mk
  const disp = taskDisplayName(raw)
  if (/^\d+$/.test(q)) {
    const qId = String(Number.parseInt(q, 10))
    const hitId = (rawName) => {
      const parsed = parseTaskName(String(rawName || ''))
      return parsed.taskId != null && Number.isFinite(parsed.taskId)
        && String(parsed.taskId) === qId
    }
    if (hitId(raw) || hitId(disp)) return true
    const s = String(mk || '').replace(/\uFFFD/g, '\0')
    if (s.charCodeAt(0) === 0) {
      const sep = s.indexOf('\0', 1)
      if (sep > 0 && String(Number.parseInt(s.slice(1, sep), 10)) === qId) return true
    }
    const m = /^(\d+)(\D.*)$/.exec(s.replace(/\0/g, ''))
    return !!(m && String(Number.parseInt(m[1], 10)) === qId)
  }
  return String(mk).toLowerCase().includes(q)
    || String(raw).toLowerCase().includes(q)
    || String(disp).toLowerCase().includes(q)
}

export function rawTaskNameMatchesTextFilter(trace, rawName, q) {
  if (!q) return true
  const mk = taskMergeKey(rawName)
  const disp = taskDisplayName(rawName)
  return mk.toLowerCase().includes(q)
    || String(rawName).toLowerCase().includes(q)
    || disp.toLowerCase().includes(q)
}

export function stiChannelMatchesTextFilter(trace, channel, q) {
  if (!q) return true
  if (channel.toLowerCase().includes(q)) return true
  for (const ev of trace?.stiEventsByTarget?.get(channel) || []) {
    if ((ev.note || '').toLowerCase().includes(q)) return true
  }
  return false
}

/**
 * Merge key → Set of core names its segments ever run on. Memoised on the trace.
 * Built by inverting `trace.coreTaskOrder` (coreName → rawTask[]).
 */
export function taskCoreSets(trace) {
  if (!trace) return new Map()
  if (trace._taskCoreSets) return trace._taskCoreSets
  const map = new Map()
  const coreTaskOrder = trace.coreTaskOrder instanceof Map ? trace.coreTaskOrder : new Map()
  for (const [coreName, order] of coreTaskOrder) {
    for (const raw of order || []) {
      const mk = taskMergeKey(raw)
      let s = map.get(mk)
      if (!s) { s = new Set(); map.set(mk, s) }
      s.add(coreName)
    }
  }
  try { Object.defineProperty(trace, '_taskCoreSets', { value: map, enumerable: false }) }
  catch { trace._taskCoreSets = map }
  return map
}

/** True when `mk` has at least one segment on a core in `coreFilterKeys`. */
export function taskRunsOnSelectedCore(trace, mk, coreFilterKeys) {
  if (!coreFilterKeys?.length) return true
  const total = trace?.coreNames?.length ?? 0
  if (coreFilterKeys.length >= total) return true
  const cset = coreFilterKeys instanceof Set ? coreFilterKeys : new Set(coreFilterKeys)
  const taskCores = taskCoreSets(trace).get(mk)
  if (!taskCores) return true // unknown → don't hide
  for (const c of taskCores) if (cset.has(c)) return true
  return false
}

/**
 * Row visibility: heatmap task filter overrides migrated-only filter; text filter
 * and the Core Filter are ANDed on top.
 */
export function taskPassesRowFilter(
  trace, mk, migratedOnlyFilter, taskFilterKeys, taskFilterText = '', coreFilterKeys = null,
) {
  if (taskFilterKeys?.length) {
    const set = taskFilterKeys instanceof Set ? taskFilterKeys : new Set(taskFilterKeys)
    if (!set.has(mk)) return false
  } else if (migratedOnlyFilter) {
    if (!isMigratedTask(trace, mk)) return false
  }
  if (!taskRunsOnSelectedCore(trace, mk, coreFilterKeys)) return false
  const q = normalizeTaskFilterText(taskFilterText)
  if (!q) return true
  return mergeKeyMatchesTextFilter(trace, mk, q)
}

/** True when a Core Filter narrows Scope to a subset of the trace's cores. */
export function coreFilterActive(coreFilterKeys, trace) {
  if (!coreFilterKeys?.length) return false
  const total = trace?.coreNames?.length ?? 0
  return coreFilterKeys.length < total
}

/** True when core view should hide non-matching tasks (heatmap, migrated, search). */
export function coreViewTaskFilterActive(
  migratedOnlyFilter, taskFilterKeys, taskFilterText = '',
) {
  return !!(
    taskFilterKeys?.length
    || migratedOnlyFilter
    || normalizeTaskFilterText(taskFilterText)
  )
}

/**
 * Per-core task lists (no TICK). Cores with no matching tasks are omitted when a filter is active.
 * Cores excluded by *coreFilterKeys* (Core Filter — Scope narrowed to specific cores) are omitted
 * entirely, regardless of task filter results.
 * @returns {{ coreName: string, tasks: string[] }[]}
 */
export function filteredCoreViewTasks(
  trace, migratedOnlyFilter, taskFilterKeys, taskFilterText = '', coreFilterKeys = null,
) {
  const filterActive = coreViewTaskFilterActive(migratedOnlyFilter, taskFilterKeys, taskFilterText)
  const coreSet = coreFilterKeys?.length
    ? (coreFilterKeys instanceof Set ? coreFilterKeys : new Set(coreFilterKeys))
    : null
  const out = []
  for (const coreName of trace.coreNames) {
    if (coreSet && !coreSet.has(coreName)) continue
    const taskOrder = (trace.coreTaskOrder.get(coreName) || [])
      .filter(t => parseTaskName(t).name !== 'TICK')
    const tasks = filterActive
      ? taskOrder.filter(t => taskPassesRowFilter(
        trace, taskMergeKey(t), migratedOnlyFilter, taskFilterKeys, taskFilterText,
      ))
      : taskOrder
    if (!filterActive || tasks.length > 0) {
      out.push({ coreName, tasks })
    }
  }
  return out
}

/** Merge keys visible in task view after active filters (incl. the Core Filter). */
export function filteredTaskViewTasks(
  trace, migratedOnlyFilter, taskFilterKeys, taskFilterText = '', coreFilterKeys = null,
) {
  return (trace?.tasks || []).filter(mk =>
    taskPassesRowFilter(trace, mk, migratedOnlyFilter, taskFilterKeys, taskFilterText, coreFilterKeys))
}
