/**
 * Task / object lifecycle from STI task-channel and sync create/delete events.
 */

import { taskLabelForMergeKey, taskMergeKey, taskReprGet } from './colors.js'
import { formatTime } from './timeFormat.js'

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
 * Build per-task lifecycle rows from STI events.
 * @param {object[]} stiEvents
 * @param {Map<string, string>} taskRepr
 */
export function buildTaskLifecycleRows(stiEvents, taskRepr, lo = null, hi = null) {
  const byMk = new Map()

  function inScope(t) {
    if (lo == null || hi == null) return true
    return t >= lo && t <= hi
  }

  for (const ev of stiEvents || []) {
    if (ev.target !== 'task') continue
    const parsed = parseTaskLifecycleNote(ev.note)
    if (!parsed) continue
    if (!inScope(ev.time)) continue

    const label = parsed.label
    const mk = taskMergeKey(label)
    const disp = taskLabelForMergeKey({ taskRepr }, mk)
    if (!byMk.has(mk)) {
      byMk.set(mk, {
        mk,
        label: disp,
        createNs: null,
        deleteNs: null,
        suspendCount: 0,
        resumeCount: 0,
        events: [],
      })
    }
    const row = byMk.get(mk)
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
  }
  rows.sort((a, b) => (a.label || '').localeCompare(b.label || ''))
  return rows
}

export function formatLifecycleSpan(ns, scale) {
  if (ns == null || ns <= 0) return '—'
  return formatTime(ns, scale)
}
