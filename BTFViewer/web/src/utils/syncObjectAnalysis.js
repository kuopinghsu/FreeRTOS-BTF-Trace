/**
 * Pair mutex/sem STI take/give events by object pointer; detect mispairs and deadlock risk.
 */
import { formatTime } from './timeFormat.js'
import { taskMergeKey, taskLabelForMergeKey, normalizeSyncPtr } from './colors.js'
import { bisectLeft } from './bisect.js'
import { segmentStartsF64 } from './lod.js'

export const SYNC_OBJECT_TARGETS = new Set(['mutex', 'sem', 'queue'])

/** Max time after `create` for the kernel post-create `give` (mutex / binary sem available). */
export const POST_CREATE_GIVE_MAX_NS = 1000

const SYNC_NOTE_RE = /^(create|take|give|delete|send|recv)(?:\s+(0[xX][0-9a-fA-F]+|\d+))?$/i

/** @returns {{ action: string, ptr: string }|null} */
export function parseSyncObjectNote(note) {
  const m = SYNC_NOTE_RE.exec((note ?? '').trim())
  if (!m) return null
  const action = m[1].toLowerCase()
  const ptr = normalizeSyncPtr(m[2] || '0')
  return { action, ptr }
}

/** What a paired sync span measures — parity with `_SYNC_SPAN_LABELS`. */
export const SYNC_SPAN_LABELS = {
  mutex_hold: 'hold',
  sem_take_give: 'take→give',
  sem_give_take: 'give→take',
  queue_send_recv: 'send→recv',
}

export function syncSpanKind(objKind, takeFirst) {
  if (objKind === 'queue') return 'queue_send_recv'
  if (objKind === 'sem') return takeFirst ? 'sem_take_give' : 'sem_give_take'
  return 'mutex_hold'
}

export const QUEUE_PAIRING_NOTE = 'Send→recv spans pair each recv with the oldest open send (FIFO). The trace '
  + 'does not record overwrite, send-to-front or reset, so queues using those '
  + 'can pair the wrong send.'

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
    // Distinct tasks that took while an earlier take was still open, and the
    // deepest simultaneously-open take count.
    waiters: new Set(),
    maxNest: 0,
    generation: 1,
    // Gives within POST_CREATE_GIVE_MAX_NS of create (kernel init), not paired.
    postCreateGives: 0,
  }
}

function isPostCreateKernelGive(obj, timeNs) {
  return obj.createNs != null && timeNs - obj.createNs <= POST_CREATE_GIVE_MAX_NS
}

function recordHold(obj, take, give, takeFirst, crossTask = false) {
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
    spanKind: syncSpanKind(obj.kind, takeFirst),
    // Mutex released by a task other than the taker: not a hold-time sample.
    crossTask,
  })
}

/** Infer running task merge key on *core* at *timeNs* from core timeline segments. */
export function runningTaskMk(coreSegs, core, timeNs, coreSegStarts = null) {
  const seg = segmentAtCoreTime(coreSegs, core, timeNs, coreSegStarts)
  return seg ? taskMergeKey(seg.task) : null
}

/** Task segment running on *core* at *timeNs*, if any. */
export function segmentAtCoreTime(coreSegs, core, timeNs, coreSegStarts = null) {
  const segs = coreSegs?.get?.(core) || coreSegs?.[core] || []
  if (!segs.length || timeNs == null) return null
  const starts = coreSegStarts?.get?.(core) ?? segmentStartsF64(segs)
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
export function buildSyncObjectData(stiEvents, coreSegs, taskRepr, timeMax, coreSegStarts = null) {
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
    const taskMk = runningTaskMk(coreSegs, ev.core, ev.time, coreSegStarts)
    const taskLabel = taskMk ? taskLabelForMergeKey({ taskRepr }, taskMk) : '?'
    const { action } = parsed

    if (action === 'create') {
      const obj = emptyObject(ev.target, parsed.ptr)
      obj.createNs = ev.time
      const prev = objects.get(key)
      if (prev && (prev.holds.length || prev.issues.length
          || prev.createNs != null || prev.deleteNs != null)) {
        // Same handle re-created: keep the earlier lifetime as its own row.
        const gen = prev.generation
        prev.key = `${key}#${gen}`
        objects.set(prev.key, prev)
        obj.generation = gen + 1
      }
      objects.set(key, obj)
    } else {
      if (!objects.has(key)) objects.set(key, emptyObject(ev.target, parsed.ptr))
      const obj = objects.get(key)
      if (action === 'take' || action === 'recv') {
        const rec = { timeNs: ev.time, taskMk, taskLabel, core: ev.core || '' }
        if (obj.kind === 'sem' && obj.openGives.length) {
          const give = obj.openGives.shift()
          recordHold(obj, rec, give, false)
        } else if (obj.kind === 'queue' && obj.openGives.length) {
          const send = obj.openGives.shift()
          recordHold(obj, { ...send, timeNs: send.timeNs }, rec, true)
        } else {
          // Take by another task while one is still open: recursion or a missing
          // give. STI takes mark acquisition, not waiting.
          if (obj.openTakes.length && taskMk
              && taskMk !== obj.openTakes[obj.openTakes.length - 1].taskMk) {
            obj.waiters.add(taskMk)
          }
          obj.openTakes.push(rec)
          if (obj.openTakes.length > obj.maxNest) obj.maxNest = obj.openTakes.length
        }
      } else if (action === 'give' || action === 'send') {
        if (action === 'give' && isPostCreateKernelGive(obj, ev.time)) {
          obj.postCreateGives++
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
            const crossTask = !!(take.taskMk && taskMk && take.taskMk !== taskMk)
            if (crossTask) {
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
            recordHold(obj, take, giveRec, true, crossTask)
            if (take.core && giveRec.core && take.core !== giveRec.core) {
              pushIssue(obj, {
                kind: 'CORE_MIGRATION_WHILE_HELD',
                severity: 'warning',
                timeNs: ev.time,
                core: ev.core || '',
                taskMk,
                taskLabel,
                detail: `Lock bounced from ${take.core} to ${ev.core}`,
              })
            }
          }
        } else if (obj.kind === 'queue') {
          obj.openGives.push(giveRec)
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
        kind: obj.kind === 'queue' ? 'unmatched_send' : 'unmatched_give',
        severity: 'warning',
        timeNs: give.timeNs,
        core: give.core,
        taskMk: give.taskMk,
        taskLabel: give.taskLabel,
        detail: obj.kind === 'queue'
          ? 'send without matching recv before trace end'
          : 'give without matching take before trace end',
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

// A cross-core hold ratio this high on a meaningful sample is a warning even
// with no explicit issue record; below the sample floor one stray issue is
// noise. Keep in lockstep with parser.py::_SYNC_MIN_SAMPLE / _SYNC_HIGH_BOUNCE_PCT.
const SYNC_MIN_SAMPLE = 20
const SYNC_HIGH_BOUNCE_PCT = 25.0

function objectStatus(obj, lo, hi) {
  const issues = obj.issues.filter(i => inScope(i.timeNs, lo, hi))
  if (!issues.length) return 'ok'
  if (issues.some(i => i.severity === 'error')) return 'error'
  return 'warning'
}

function nearestRankHold(sorted, p) {
  if (!sorted.length) return 0
  return sorted[Math.min(sorted.length - 1, Math.max(0, Math.ceil(p * sorted.length) - 1))]
}

/**
 * Split window-touching holds into hold-time samples and exclusions — parity
 * with `_sync_stat_holds`. Cross-task mutex gives are not hold samples, and
 * with a cursor window both endpoints must lie inside it.
 */
export function syncStatHolds(holds, lo, hi) {
  const samples = []
  let crossTask = 0
  let boundary = 0
  const scoped = lo != null && hi != null
  for (const h of holds || []) {
    if (h.crossTask) crossTask++
    else if (scoped && (h.startNs < lo || h.stopNs > hi)) boundary++
    else samples.push(h)
  }
  return { samples, crossTask, boundary }
}

function syncObjectLabel(obj) {
  let label = `${obj.kind} ${obj.ptr}`
  const gen = Math.trunc(obj.generation || 1)
  if (gen > 1 || String(obj.key || '').includes('#')) label += ` (gen ${gen})`
  return label
}

/** Span kinds behind an object's hold-time samples — parity with `_sync_span_summary`. */
export function syncSpanSummary(holds, objKind) {
  const kinds = new Set((holds || []).map(h => h.spanKind || syncSpanKind(objKind, !h.signal)))
  if (!kinds.size) return ''
  const order = Object.keys(SYNC_SPAN_LABELS)
  return [...kinds].sort((a, b) => order.indexOf(a) - order.indexOf(b))
    .map(k => SYNC_SPAN_LABELS[k]).join(', ')
}

/** Kind column text: object kind plus what its spans measure. */
export function syncKindDisplay(row) {
  return row?.span ? `${row.kind} · ${row.span}` : String(row?.kind ?? '')
}

/** Caption for spans left out of the Holds / hold-time columns, or ''. */
export function syncExclusionNote(rows) {
  let cross = 0
  let boundary = 0
  let postCreate = 0
  for (const r of rows || []) {
    cross += r.crossTaskExcluded || 0
    boundary += r.boundaryExcluded || 0
    postCreate += r.postCreateGives || 0
  }
  const bits = []
  if (cross) bits.push(`${cross.toLocaleString('en-US')} cross-task mutex give(s)`)
  if (boundary) bits.push(`${boundary.toLocaleString('en-US')} span(s) crossing the cursor window`)
  if (postCreate) bits.push(`${postCreate.toLocaleString('en-US')} kernel give(s) right after create`)
  if (!bits.length) return ''
  return `Not counted as hold-time samples: ${bits.join('; ')}.`
}

/** Stats rows: one per mutex/sem/queue object in scope. */
export function syncObjectStatsRows(trace, lo, hi, { kindFilter = null } = {}) {
  if (!trace?.hasSyncObjectInstrumentation) return []
  const scale = trace.timeScale
  const rows = []
  for (const obj of trace.syncObjects?.values() || []) {
    if (kindFilter && obj.kind !== kindFilter) continue
    const touching = (obj.holds || []).filter(h =>
      (lo == null || hi == null) ? true : (h.stopNs > lo && h.startNs < hi),
    )
    const { samples: holds, crossTask: crossTaskExcluded, boundary: boundaryExcluded } =
      syncStatHolds(touching, lo, hi)
    const issues = (obj.issues || []).filter(i => inScope(i.timeNs, lo, hi))
    if (lo != null && hi != null && !touching.length && !issues.length
        && !(obj.createNs != null && inScope(obj.createNs, lo, hi))) {
      continue
    }
    let status = objectStatus(obj, lo, hi)
    const bounceCount = holds.filter(
      h => h.takeCore && h.giveCore && h.takeCore !== h.giveCore,
    ).length
    const bouncePct = holds.length
      ? Math.round((1000 * bounceCount) / holds.length) / 10
      : 0
    if (status === 'ok' && holds.length >= SYNC_MIN_SAMPLE
        && bouncePct >= SYNC_HIGH_BOUNCE_PCT) {
      status = 'warning'
    }
    rows.push({
      key: obj.key,
      kind: obj.kind,
      ptr: obj.ptr,
      label: syncObjectLabel(obj),
      holdCount: holds.length,
      issueCount: issues.length,
      bounceCount,
      bouncePct,
      status,
      statusLabel: status === 'ok' ? 'OK' : status === 'error' ? 'Error' : 'Warning',
      issues,
      holds,
      avgHoldNs: holds.length
        ? Math.floor(holds.reduce((s, h) => s + h.durationNs, 0) / holds.length)
        : 0,
      avgHold: holds.length
        ? formatTime(Math.floor(holds.reduce((s, h) => s + h.durationNs, 0) / holds.length), scale)
        : '—',
      ...(() => {
        const hd = holds.map(h => h.durationNs).sort((a, b) => a - b)
        const p95 = nearestRankHold(hd, 0.95)
        const p99 = nearestRankHold(hd, 0.99)
        return {
          p95HoldNs: p95,
          p99HoldNs: p99,
          p95Hold: hd.length ? formatTime(p95, scale) : '—',
          p99Hold: hd.length ? formatTime(p99, scale) : '—',
        }
      })(),
      waiters: (obj.waiters && obj.waiters.size) || 0,
      maxNest: Math.trunc(obj.maxNest || 0),
      crossTaskExcluded,
      boundaryExcluded,
      span: syncSpanSummary(holds, obj.kind),
      postCreateGives: obj.postCreateGives || 0,
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
        object: syncObjectLabel(obj),
        span: SYNC_SPAN_LABELS[h.spanKind || syncSpanKind(obj.kind, !h.signal)] || 'hold',
        holder: h.holderLabel || '—',
        startNs: h.startNs,
        stopNs: h.stopNs,
        start: formatTime(h.startNs, scale),
        stop: formatTime(h.stopNs, scale),
        duration: formatTime(h.durationNs, scale),
        durationNs: h.durationNs,
        takeCore: h.takeCore || '',
        giveCore: h.giveCore || '',
        crossTask: !!h.crossTask,
      })
    }
  }
  rows.sort((a, b) => b.durationNs - a.durationNs || a.startNs - b.startNs)
  return limit > 0 ? rows.slice(0, limit) : rows
}

/** Hold-duration scatter for one sync object — parity with `_sync_hold_plot_points`. */
export function syncHoldPlotPoints(trace, objKey, lo = null, hi = null) {
  if (!trace?.hasSyncObjectInstrumentation || !objKey) return []
  const obj = trace.syncObjects?.get?.(objKey)
  if (!obj) return []
  const pts = []
  for (const h of obj.holds || []) {
    const start = Math.trunc(h.startNs || 0)
    const stop = Math.trunc(h.stopNs || 0)
    if (stop < start) continue
    if (lo != null && hi != null && !(stop >= lo && start <= hi)) continue
    pts.push({ xNs: start, yValue: stop - start, payload: h })
  }
  return pts
}

/** Mutex-wait scatter for waiter×object — parity with `_mutex_wait_plot_points`. */
export function mutexWaitPlotPoints(waits, waiterMk, objKey) {
  const wk = String(waiterMk || '')
  const obj = String(objKey || '')
  if (!wk || !obj) return []
  const pts = []
  for (const w of waits || []) {
    if (!w || String(w.waiter_mk || '') !== wk) continue
    if (String(w.object || '') !== obj) continue
    const dur = Math.trunc(w.duration || 0)
    if (dur <= 0) continue
    pts.push({ xNs: Math.trunc(w.start || 0), yValue: dur, payload: w })
  }
  return pts
}
