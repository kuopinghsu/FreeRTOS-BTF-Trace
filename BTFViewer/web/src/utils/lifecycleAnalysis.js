/**
 * Task / object lifecycle from STI task-channel and sync create/delete events.
 */

import { taskLabelForMergeKey, taskMergeKey } from './colors.js'
import { formatTime } from './timeFormat.js'
import { segOverlapsRange } from './statsRange.js'

const TASK_LIFE_RE = /^(create|delete|suspend|resume)\b/i

/** @returns {{ action: string, label: string }|null} */
export function parseTaskLifecycleNote(note) {
  const raw = (note ?? '').trim()
  if (!raw) return null
  const m = TASK_LIFE_RE.exec(raw)
  if (!m) return null
  const action = m[1].toLowerCase()
  const label = raw.slice(m[0].length).trim() || raw
  return { action, label: label || raw }
}

/**
 * Build per-task lifecycle rows.
 *
 * Creation timestamps come from `taskCreateTimes` (task creation is recorded
 * as a dedicated 'T' event, never as an STI 'task' channel note — that channel
 * only ever emits delete/suspend/resume/set_priority/…), so relying solely on
 * `stiEvents` would leave `createNs` always null. Delete/suspend/resume still
 * come from STI 'task' channel events.
 *
 * `runCount` is the number of times the task was dispatched onto a core
 * (context-switch-in / segment count) — a scheduler-level metric, distinct
 * from `suspendCount`/`resumeCount` which only reflect explicit
 * vTaskSuspend()/vTaskResume() API calls.
 * @param {object[]} stiEvents
 * @param {Map<string, string>} taskRepr
 * @param {Map<string, number>} [taskCreateTimes]
 * @param {Map<string, object[]>} [segByMergeKey]
 */
export function buildTaskLifecycleRows(stiEvents, taskRepr, lo = null, hi = null, taskCreateTimes = null, segByMergeKey = null) {
  const byMk = new Map()

  function inScope(t) {
    if (lo == null || hi == null) return true
    return t >= lo && t <= hi
  }

  function getRow(mk) {
    if (!byMk.has(mk)) {
      byMk.set(mk, {
        mk,
        label: taskLabelForMergeKey({ taskRepr }, mk),
        createNs: null,
        deleteNs: null,
        suspendCount: 0,
        resumeCount: 0,
        events: [],
      })
    }
    return byMk.get(mk)
  }

  for (const [mk, createNs] of taskCreateTimes || []) {
    if (!inScope(createNs)) continue
    const row = getRow(mk)
    row.createNs = createNs
    row.events.push({ timeNs: createNs, action: 'create', core: '' })
  }

  for (const ev of stiEvents || []) {
    if (ev.target !== 'task') continue
    const parsed = parseTaskLifecycleNote(ev.note)
    if (!parsed) continue
    if (!inScope(ev.time)) continue

    const label = parsed.label
    const mk = taskMergeKey(label)
    const row = getRow(mk)
    row.events.push({ timeNs: ev.time, action: parsed.action, core: ev.core || '' })
    if (parsed.action === 'create' && row.createNs == null) row.createNs = ev.time
    if (parsed.action === 'delete') row.deleteNs = ev.time
    if (parsed.action === 'suspend') row.suspendCount++
    if (parsed.action === 'resume') row.resumeCount++
  }

  const rows = [...byMk.values()]
  for (const row of rows) {
    row.events.sort((a, b) => a.timeNs - b.timeNs)
    row.eventCount = row.events.length
    row.aliveSpanNs = (row.createNs != null && row.deleteNs != null && row.deleteNs > row.createNs)
      ? row.deleteNs - row.createNs
      : null
    const segs = segByMergeKey?.get(row.mk) ?? []
    let runCount = segs.length || 0
    if (lo != null && hi != null) {
      runCount = 0
      for (const s of segs) {
        if (segOverlapsRange(s, lo, hi)) runCount++
      }
    }
    row.runCount = runCount
  }
  rows.sort((a, b) => (a.label || '').localeCompare(b.label || ''))
  return rows
}

export function formatLifecycleSpan(ns, scale) {
  if (ns == null || ns <= 0) return '—'
  return formatTime(ns, scale)
}
