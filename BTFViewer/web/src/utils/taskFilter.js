/** Task row filtering (parity with desktop TimelineScene filter helpers). */

import { taskDisplayName, taskMergeKey, parseTaskName } from './colors.js'
import { isMigratedTask } from './migrationAnalysis.js'

export function normalizeTaskFilterText(text) {
  return (text || '').trim().toLowerCase()
}

export function mergeKeyMatchesTextFilter(trace, mk, q) {
  if (!q) return true
  const raw = trace?.taskRepr?.get(mk) || mk
  const disp = taskDisplayName(raw)
  return mk.toLowerCase().includes(q)
    || String(raw).toLowerCase().includes(q)
    || disp.toLowerCase().includes(q)
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

/** Row visibility: heatmap task filter overrides migrated-only filter; text filter is ANDed. */
export function taskPassesRowFilter(
  trace, mk, migratedOnlyFilter, taskFilterKeys, taskFilterText = '',
) {
  if (taskFilterKeys?.length) {
    const set = taskFilterKeys instanceof Set ? taskFilterKeys : new Set(taskFilterKeys)
    if (!set.has(mk)) return false
  } else if (migratedOnlyFilter) {
    if (!isMigratedTask(trace, mk)) return false
  }
  const q = normalizeTaskFilterText(taskFilterText)
  if (!q) return true
  return mergeKeyMatchesTextFilter(trace, mk, q)
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
 * @returns {{ coreName: string, tasks: string[] }[]}
 */
export function filteredCoreViewTasks(
  trace, migratedOnlyFilter, taskFilterKeys, taskFilterText = '',
) {
  const filterActive = coreViewTaskFilterActive(migratedOnlyFilter, taskFilterKeys, taskFilterText)
  const out = []
  for (const coreName of trace.coreNames) {
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

/** Merge keys visible in task view after active filters. */
export function filteredTaskViewTasks(
  trace, migratedOnlyFilter, taskFilterKeys, taskFilterText = '',
) {
  return (trace?.tasks || []).filter(mk =>
    taskPassesRowFilter(trace, mk, migratedOnlyFilter, taskFilterKeys, taskFilterText))
}
