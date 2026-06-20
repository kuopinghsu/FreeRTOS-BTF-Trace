/**
 * Pair mutex/sem STI take/give events by object pointer; detect mispairs and deadlock risk.
 */
import { formatTime } from './timeFormat.js'
import { taskMergeKey, taskLabelForMergeKey } from './colors.js'
import { bisectLeft } from './bisect.js'

export const SYNC_OBJECT_TARGETS = new Set(['mutex', 'sem'])

/** Max time after `create` for the kernel post-create `give` (mutex / binary sem available). */
export const POST_CREATE_GIVE_MAX_NS = 1000

const SYNC_NOTE_RE = /^(create|take|give|delete)\s+(0x[0-9a-f]+)$/i

/** @returns {{ action: string, ptr: string }|null} */
export function parseSyncObjectNote(note) {
  const m = SYNC_NOTE_RE.exec((note ?? '').trim())
  if (!m) return null
  return { action: m[1].toLowerCase(), ptr: m[2].toLowerCase() }
}

export function syncObjectKey(kind, ptr) {
  return `${kind}:${ptr}`
}

function emptyObject(kind, ptr) {
  return {
    key: syncObjectKey(kind, ptr),
    kind,
    ptr,
    createNs: null,
    deleteNs: null,
    holds: [],
    issues: [],
    openTakes: [],
    openGives: [],
  }
}

function isPostCreateKernelGive(obj, timeNs) {
  return obj.createNs != null && timeNs - obj.createNs <= POST_CREATE_GIVE_MAX_NS
}

function recordHold(obj, take, give, takeFirst) {
  const start = takeFirst ? take : give
  const stop = takeFirst ? give : take
  obj.holds.push({
    startNs: start.timeNs,
    stopNs: stop.timeNs,
    durationNs: stop.timeNs - start.timeNs,
    holderMk: take.taskMk,
    holderLabel: take.taskLabel,
    takeCore: take.core,
    giveCore: give.core,
    giveTaskMk: give.taskMk,
    giveTaskLabel: give.taskLabel,
    signal: !takeFirst,
  })
}

/** Infer running task merge key on *core* at *timeNs* from core timeline segments. */
export function runningTaskMk(coreSegs, core, timeNs) {
  const seg = segmentAtCoreTime(coreSegs, core, timeNs)
  return seg ? taskMergeKey(seg.task) : null
}

/** Task segment running on *core* at *timeNs*, if any. */
export function segmentAtCoreTime(coreSegs, core, timeNs) {
  const segs = coreSegs?.get?.(core) || coreSegs?.[core] || []
  if (!segs.length || timeNs == null) return null
  const starts = segs.map(s => s.start)
  const lo = Math.max(0, bisectLeft(starts, timeNs) - 1)
  for (let i = lo; i < segs.length; i++) {
    const s = segs[i]
    if (s.start > timeNs) break
    if (s.end >= timeNs) return s
  }
  return null
}

export function syncIssueAnnotationNote(issue) {
  if (!issue) return 'sync issue'
  if (issue.objKey) {
    return `${issue.kindLabel || issue.kind || 'sync'} ${issue.ptr || ''}: ${issue.detail || issue.kind}`
  }
  return issue.detail || issue.kind || 'sync issue'
}

function pushIssue(obj, issue) {
  obj.issues.push(issue)
}

function inScope(timeNs, lo, hi) {
  if (lo == null || hi == null) return true
  return timeNs >= lo && timeNs <= hi
}

/**
 * @param {object[]} stiEvents
 * @param {Map<string, object[]>} coreSegs
 * @param {Map<string, string>} taskRepr
 * @param {number} timeMax
 */
export function buildSyncObjectData(stiEvents, coreSegs, taskRepr, timeMax) {
  const objects = new Map()
  const globalIssues = []

  const events = (stiEvents || [])
    .filter(ev => SYNC_OBJECT_TARGETS.has(ev.target))
    .map(ev => ({ ev, parsed: parseSyncObjectNote(ev.note) }))
    .filter(x => x.parsed)
    .sort((a, b) => a.ev.time - b.ev.time || a.parsed.action.localeCompare(b.parsed.action))

  if (!events.length) {
    return {
      syncObjects: objects,
      syncIssues: [],
      hasSyncObjectInstrumentation: false,
    }
  }

  for (const { ev, parsed } of events) {
    const key = syncObjectKey(ev.target, parsed.ptr)
    const taskMk = runningTaskMk(coreSegs, ev.core, ev.time)
    const taskLabel = taskMk ? taskLabelForMergeKey({ taskRepr }, taskMk) : '?'
    const { action } = parsed

    if (action === 'create') {
      const obj = emptyObject(ev.target, parsed.ptr)
      obj.createNs = ev.time
      objects.set(key, obj)
    } else {
      if (!objects.has(key)) objects.set(key, emptyObject(ev.target, parsed.ptr))
      const obj = objects.get(key)
      if (action === 'take') {
        const rec = { timeNs: ev.time, taskMk, taskLabel, core: ev.core || '' }
        if (obj.kind === 'sem' && obj.openGives.length) {
          const give = obj.openGives.shift()
          recordHold(obj, rec, give, false)
        } else {
          obj.openTakes.push(rec)
        }
      } else if (action === 'give') {
        if (isPostCreateKernelGive(obj, ev.time)) {
          continue
        }
        const giveRec = { timeNs: ev.time, taskMk, taskLabel, core: ev.core || '' }
        if (obj.kind === 'mutex') {
          if (!obj.openTakes.length) {
            pushIssue(obj, {
              kind: 'orphan_give',
              severity: 'error',
              timeNs: ev.time,
              core: ev.core || '',
              taskMk,
              taskLabel,
              detail: 'give without matching take',
            })
          } else {
            const take = obj.openTakes.pop()
            if (take.taskMk && taskMk && take.taskMk !== taskMk) {
              pushIssue(obj, {
                kind: 'cross_task_give',
                severity: 'warning',
                timeNs: ev.time,
                core: ev.core || '',
                taskMk,
                taskLabel,
                detail: `give by ${taskLabel}, held by ${take.taskLabel}`,
              })
            }
            recordHold(obj, take, giveRec, true)
          }
        } else if (obj.openTakes.length) {
          const take = obj.openTakes.shift()
          recordHold(obj, take, giveRec, true)
        } else {
          obj.openGives.push(giveRec)
        }
      } else if (action === 'delete') {
        obj.deleteNs = ev.time
        if (obj.openTakes.length) {
          pushIssue(obj, {
            kind: 'delete_while_held',
            severity: 'warning',
            timeNs: ev.time,
            core: ev.core || '',
            taskMk,
            taskLabel,
            detail: `delete while ${obj.openTakes.length} take(s) unmatched`,
          })
        }
        obj.openTakes = []
        obj.openGives = []
      }
    }
  }

  for (const obj of objects.values()) {
    for (const take of obj.openTakes) {
      pushIssue(obj, {
        kind: 'unmatched_take',
        severity: 'warning',
        timeNs: take.timeNs,
        core: take.core,
        taskMk: take.taskMk,
        taskLabel: take.taskLabel,
        detail: 'take without matching give before trace end',
      })
    }
    for (const give of obj.openGives) {
      pushIssue(obj, {
        kind: 'unmatched_give',
        severity: 'warning',
        timeNs: give.timeNs,
        core: give.core,
        taskMk: give.taskMk,
        taskLabel: give.taskLabel,
        detail: 'give without matching take before trace end',
      })
    }
    obj.openTakes = []
    obj.openGives = []
  }

  const endMutexHolds = []
  for (const obj of objects.values()) {
    if (obj.kind !== 'mutex') continue
    const open = obj.issues.filter(i => i.kind === 'unmatched_take')
    for (const iss of open) {
      endMutexHolds.push({ obj, holderMk: iss.taskMk, holderLabel: iss.taskLabel })
    }
  }
  const holders = new Set(endMutexHolds.map(h => h.holderMk).filter(Boolean))
  if (endMutexHolds.length >= 2 && holders.size >= 2) {
    globalIssues.push({
      kind: 'deadlock_risk',
      severity: 'warning',
      timeNs: timeMax,
      objKey: null,
      ptr: '',
      kindLabel: 'mutex',
      detail: `${endMutexHolds.length} mutex(es) still held by ${holders.size} tasks at trace end`,
      objects: endMutexHolds.map(h => h.obj.key),
    })
  }

  const syncIssues = []
  for (const obj of objects.values()) {
    for (const iss of obj.issues) {
      syncIssues.push({
        ...iss,
        objKey: obj.key,
        ptr: obj.ptr,
        kindLabel: obj.kind,
      })
    }
  }
  for (const iss of globalIssues) syncIssues.push(iss)

  syncIssues.sort((a, b) => a.timeNs - b.timeNs || (a.objKey || '').localeCompare(b.objKey || ''))

  return {
    syncObjects: objects,
    syncIssues,
    hasSyncObjectInstrumentation: true,
  }
}

function objectStatus(obj, lo, hi) {
  const issues = obj.issues.filter(i => inScope(i.timeNs, lo, hi))
  if (!issues.length) return 'ok'
  if (issues.some(i => i.severity === 'error')) return 'error'
  return 'warning'
}

/** Stats rows: one per mutex/sem object in scope. */
export function syncObjectStatsRows(trace, lo, hi) {
  if (!trace?.hasSyncObjectInstrumentation) return []
  const scale = trace.timeScale
  const rows = []
  for (const obj of trace.syncObjects?.values() || []) {
    const holds = (obj.holds || []).filter(h =>
      (lo == null || hi == null) ? true : (h.stopNs > lo && h.startNs < hi),
    )
    const issues = (obj.issues || []).filter(i => inScope(i.timeNs, lo, hi))
    if (lo != null && hi != null && !holds.length && !issues.length
        && !(obj.createNs != null && inScope(obj.createNs, lo, hi))) {
      continue
    }
    const status = objectStatus(obj, lo, hi)
    rows.push({
      key: obj.key,
      kind: obj.kind,
      ptr: obj.ptr,
      label: `${obj.kind} ${obj.ptr}`,
      holdCount: holds.length,
      issueCount: issues.length,
      status,
      statusLabel: status === 'ok' ? 'OK' : status === 'error' ? 'Error' : 'Warning',
      issues,
      holds,
      avgHoldNs: holds.length
        ? Math.round(holds.reduce((s, h) => s + h.durationNs, 0) / holds.length)
        : 0,
      avgHold: holds.length
        ? formatTime(Math.round(holds.reduce((s, h) => s + h.durationNs, 0) / holds.length), scale)
        : '—',
    })
  }
  rows.sort((a, b) => {
    const sev = s => (s.status === 'error' ? 0 : s.status === 'warning' ? 1 : 2)
    const d = sev(a) - sev(b)
    if (d !== 0) return d
    return b.issueCount - a.issueCount || a.label.localeCompare(b.label)
  })
  return rows
}

export function syncObjectIssueRows(trace, lo, hi) {
  if (!trace?.hasSyncObjectInstrumentation) return []
  return (trace.syncIssues || []).filter(i => inScope(i.timeNs, lo, hi))
}

/** Flat hold rows for HTML/CSV detail export (longest first). */
export function syncObjectHoldDetailRows(trace, lo, hi, limit = 150) {
  if (!trace?.hasSyncObjectInstrumentation) return []
  const scale = trace.timeScale
  const rows = []
  for (const obj of trace.syncObjects?.values() || []) {
    for (const h of obj.holds || []) {
      if (lo != null && hi != null && !(h.stopNs > lo && h.startNs < hi)) continue
      rows.push({
        object: `${obj.kind} ${obj.ptr}`,
        holder: h.holderLabel || '—',
        startNs: h.startNs,
        stopNs: h.stopNs,
        start: formatTime(h.startNs, scale),
        stop: formatTime(h.stopNs, scale),
        duration: formatTime(h.durationNs, scale),
        durationNs: h.durationNs,
        takeCore: h.takeCore || '',
        giveCore: h.giveCore || '',
      })
    }
  }
  rows.sort((a, b) => b.durationNs - a.durationNs || a.startNs - b.startNs)
  return limit > 0 ? rows.slice(0, limit) : rows
}
