/**
 * Export a parsed BTF trace as Chrome Trace Event Format JSON for
 * https://ui.perfetto.dev (same layout as the desktop File → Export Perfetto…).
 */

import { taskDisplayName, taskLabelForMergeKey, taskMergeKey, taskReprGet } from './colors.js'
import { isIntervalMarkerChannel } from './intervalAnalysis.js'
import { isTagChannel, tagChannelLabel } from './tagAnalysis.js'
import { SYNC_OBJECT_TARGETS } from './syncObjectAnalysis.js'

const PID_CORES = 1
const PID_TASKS = 2
const PID_STI = 3
const PID_INTERVALS = 4
const PID_TAGS = 5
const PID_SYNC = 6

const NS_MULT = { ns: 1, us: 1e3, ms: 1e6, s: 1e9 }

/** Convert a native-scale timestamp to Chrome Trace microseconds. */
export function toTraceUs(value, timeScale) {
  const mult = NS_MULT[timeScale] ?? 1
  return (Number(value) * mult) / 1000
}

function metaProcess(pid, name) {
  return { name: 'process_name', ph: 'M', pid, args: { name } }
}

function metaThread(pid, tid, name) {
  return { name: 'thread_name', ph: 'M', pid, tid, args: { name } }
}

function iterSegments(trace) {
  const segs = trace?.segments
  if (!segs) return []
  if (typeof segs[Symbol.iterator] === 'function') return segs
  return Array.isArray(segs) ? segs : []
}

/** Normalize optional [lo, hi) export window (native trace units). */
export function normalizeExportRange(lo, hi) {
  if (lo == null && hi == null) return { lo: null, hi: null }
  if ((lo == null) !== (hi == null)) {
    throw new Error('lo and hi must both be set or both omitted')
  }
  const a = Number(lo)
  const b = Number(hi)
  if (!(b > a)) throw new Error('hi must be greater than lo')
  return { lo: a, hi: b }
}

function inRange(t, lo, hi) {
  if (lo == null) return true
  return t >= lo && t < hi
}

/** Clip [start, end) to [lo, hi); return null if no overlap. */
function clipSpan(start, end, lo, hi) {
  if (lo == null) {
    if (end <= start) return null
    return { start, end }
  }
  if (end <= lo || start >= hi) return null
  const cs = Math.max(start, lo)
  const ce = Math.min(end, hi)
  if (ce <= cs) return null
  return { start: cs, end: ce }
}

function skipStiChannel(channel, skipSync) {
  if (isIntervalMarkerChannel(channel)) return true
  if (isTagChannel(channel)) return true
  if (skipSync && SYNC_OBJECT_TARGETS.has(channel)) return true
  return false
}

function iterSyncObjects(trace) {
  const objs = trace?.syncObjects
  if (!objs) return []
  if (typeof objs.values === 'function') return [...objs.values()]
  if (Array.isArray(objs)) return objs
  return Object.values(objs)
}

function tagSamplesFor(trace, ch) {
  const byCh = trace?.tagSamplesByChannel
  if (!byCh) return []
  if (typeof byCh.get === 'function') return byCh.get(ch) || []
  return byCh[ch] || []
}

/**
 * Build Chrome Trace Event list from a parsed web *trace*.
 * @param {object} trace
 * @param {{ lo?: number|null, hi?: number|null }} [range]
 * @returns {object[]}
 */
export function buildPerfettoChromeEvents(trace, range = {}) {
  const { lo, hi } = normalizeExportRange(range.lo ?? null, range.hi ?? null)
  const scale = trace.timeScale || 'ns'
  const events = []
  const skipSyncSti = !!trace.hasSyncObjectInstrumentation

  // --- Cores / Tasks metadata -----------------------------------------
  events.push(metaProcess(PID_CORES, 'Cores'))
  const coreTid = new Map()
  for (const [i, core] of (trace.coreNames || []).entries()) {
    const tid = i + 1
    coreTid.set(core, tid)
    events.push(metaThread(PID_CORES, tid, core))
  }

  events.push(metaProcess(PID_TASKS, 'Tasks'))
  const taskTid = new Map()
  for (const [i, mk] of (trace.tasks || []).entries()) {
    const tid = i + 1
    const label = taskLabelForMergeKey(trace, mk)
    taskTid.set(mk, tid)
    events.push(metaThread(PID_TASKS, tid, label))
  }

  // --- Segments: discover missing tracks + emit run slices (one pass) -
  for (const seg of iterSegments(trace)) {
    const clipped = clipSpan(seg.start, seg.end, lo, hi)
    if (!clipped) continue

    if (seg.core && !coreTid.has(seg.core)) {
      const tid = coreTid.size + 1
      coreTid.set(seg.core, tid)
      events.push(metaThread(PID_CORES, tid, seg.core))
    }

    const mk = taskMergeKey(seg.task)
    const raw = taskReprGet(trace, mk) || seg.task
    const label = taskDisplayName(raw)
    if (!taskTid.has(mk)) {
      const tid = taskTid.size + 1
      taskTid.set(mk, tid)
      events.push(metaThread(PID_TASKS, tid, label))
    }

    const ts = toTraceUs(clipped.start, scale)
    let dur = toTraceUs(clipped.end - clipped.start, scale)
    if (dur < 0) dur = 0
    const args = { core: seg.core, task: label }

    const ctid = coreTid.get(seg.core)
    if (ctid != null) {
      events.push({
        name: label, cat: 'sched', ph: 'X',
        ts, dur, pid: PID_CORES, tid: ctid, args,
      })
    }
    events.push({
      name: 'run', cat: 'sched', ph: 'X',
      ts, dur, pid: PID_TASKS, tid: taskTid.get(mk), args,
    })
  }

  // --- Migrations -------------------------------------------------------
  for (const mig of trace.migrations || []) {
    if (!inRange(mig.ns, lo, hi)) continue
    const tid = taskTid.get(mig.mergeKey)
    if (tid == null) continue
    events.push({
      name: 'migrate', cat: 'sched', ph: 'i', s: 't',
      ts: toTraceUs(mig.ns, scale),
      pid: PID_TASKS, tid,
      args: {
        from_core: mig.fromCore,
        to_core: mig.toCore,
        gap_ns: mig.gapNs,
      },
    })
  }

  // --- STI channels (skip interval / tag / sync-when-paired) ------------
  const stiChannels = [...(trace.stiChannels || [])].filter(
    ch => !skipStiChannel(ch, skipSyncSti),
  )
  const tickTimes = (trace.tickStiTimes || []).filter(t => inRange(t, lo, hi))
  const stiEvents = [...(trace.stiEvents || [])].filter(
    ev => !skipStiChannel(ev.target, skipSyncSti) && inRange(ev.time, lo, hi),
  )
  if (stiChannels.length || tickTimes.length || stiEvents.length) {
    events.push(metaProcess(PID_STI, 'STI'))
  }
  const stiTid = new Map()
  for (const [i, ch] of stiChannels.entries()) {
    const tid = i + 1
    stiTid.set(ch, tid)
    events.push(metaThread(PID_STI, tid, ch))
  }

  for (const ev of stiEvents) {
    let tid = stiTid.get(ev.target)
    if (tid == null) {
      tid = stiTid.size + 1
      stiTid.set(ev.target, tid)
      events.push(metaThread(PID_STI, tid, ev.target))
    }
    const name = ev.note || ev.event || ev.target
    events.push({
      name, cat: 'sti', ph: 'i', s: 't',
      ts: toTraceUs(ev.time, scale),
      pid: PID_STI, tid,
      args: {
        channel: ev.target,
        event: ev.event,
        note: ev.note,
        core: ev.core,
      },
    })
  }

  if (tickTimes.length) {
    const tickTid = stiTid.size + 1
    events.push(metaThread(PID_STI, tickTid, 'TICK'))
    for (const t of tickTimes) {
      events.push({
        name: 'TICK', cat: 'sti', ph: 'i', s: 't',
        ts: toTraceUs(t, scale),
        pid: PID_STI, tid: tickTid,
      })
    }
  }

  // --- Intervals --------------------------------------------------------
  const intervals = trace.intervalInstances || []
  const idTid = new Map()
  for (const [i, iid] of (trace.intervalIds || []).entries()) {
    idTid.set(iid, i + 1)
  }
  const intervalEvents = []
  for (const inst of intervals) {
    const clipped = clipSpan(inst.startNs, inst.stopNs, lo, hi)
    if (!clipped) continue
    let tid = idTid.get(inst.id)
    if (tid == null) {
      tid = idTid.size + 1
      idTid.set(inst.id, tid)
    }
    const ts = toTraceUs(clipped.start, scale)
    let dur = toTraceUs(clipped.end - clipped.start, scale)
    if (dur < 0) dur = 0
    intervalEvents.push({
      name: inst.id, cat: 'interval', ph: 'X',
      ts, dur, pid: PID_INTERVALS, tid,
      args: {
        start_core: inst.startCore || '',
        stop_core: inst.stopCore || '',
        task_id: inst.taskId || '',
      },
    })
  }
  if (intervalEvents.length) {
    events.push(metaProcess(PID_INTERVALS, 'Intervals'))
    for (const [iid, tid] of [...idTid.entries()].sort((a, b) => a[1] - b[1])) {
      events.push(metaThread(PID_INTERVALS, tid, iid))
    }
    events.push(...intervalEvents)
  }

  // --- Tag counters -----------------------------------------------------
  const tagChannels = [...(trace.tagChannels || [])]
  const tagTid = new Map()
  for (const [i, ch] of tagChannels.entries()) tagTid.set(ch, i + 1)
  const tagEvents = []
  for (const ch of tagChannels) {
    const tid = tagTid.get(ch)
    const label = tagChannelLabel(ch)
    for (const sample of tagSamplesFor(trace, ch)) {
      const t = sample.timeNs
      if (!inRange(t, lo, hi)) continue
      tagEvents.push({
        name: label, cat: 'tag', ph: 'C',
        ts: toTraceUs(t, scale),
        pid: PID_TAGS, tid,
        args: {
          value: Number(sample.value),
          channel: ch,
          core: sample.core || '',
        },
      })
    }
  }
  if (tagEvents.length) {
    events.push(metaProcess(PID_TAGS, 'Tags'))
    for (const [ch, tid] of [...tagTid.entries()].sort((a, b) => a[1] - b[1])) {
      events.push(metaThread(PID_TAGS, tid, tagChannelLabel(ch)))
    }
    events.push(...tagEvents)
  }

  // --- Sync hold slices -------------------------------------------------
  if (skipSyncSti) {
    const syncTid = new Map()
    const nameByTid = new Map()
    let nextTid = 1
    const syncEvents = []
    for (const obj of iterSyncObjects(trace)) {
      const kind = obj.kind || 'sync'
      const ptr = obj.ptr || ''
      const key = obj.key || `${kind}:${ptr}`
      const threadName = `${kind} ${ptr}`.trim()
      let tid = syncTid.get(key)
      if (tid == null) {
        tid = nextTid++
        syncTid.set(key, tid)
        nameByTid.set(tid, threadName)
      }

      if (obj.createNs != null && inRange(obj.createNs, lo, hi)) {
        syncEvents.push({
          name: 'create', cat: 'sync', ph: 'i', s: 't',
          ts: toTraceUs(obj.createNs, scale),
          pid: PID_SYNC, tid,
          args: { kind, ptr, object: threadName },
        })
      }
      if (obj.deleteNs != null && inRange(obj.deleteNs, lo, hi)) {
        syncEvents.push({
          name: 'delete', cat: 'sync', ph: 'i', s: 't',
          ts: toTraceUs(obj.deleteNs, scale),
          pid: PID_SYNC, tid,
          args: { kind, ptr, object: threadName },
        })
      }

      for (const hold of obj.holds || []) {
        const clipped = clipSpan(hold.startNs, hold.stopNs, lo, hi)
        if (!clipped) continue
        const holder = hold.holderLabel || 'hold'
        let dur = toTraceUs(clipped.end - clipped.start, scale)
        if (dur < 0) dur = 0
        syncEvents.push({
          name: holder, cat: 'sync', ph: 'X',
          ts: toTraceUs(clipped.start, scale), dur,
          pid: PID_SYNC, tid,
          args: {
            kind,
            ptr,
            object: threadName,
            take_core: hold.takeCore || '',
            give_core: hold.giveCore || '',
            signal: !!hold.signal,
          },
        })
      }
    }
    if (syncEvents.length) {
      events.push(metaProcess(PID_SYNC, 'Sync'))
      for (const tid of [...nameByTid.keys()].sort((a, b) => a - b)) {
        events.push(metaThread(PID_SYNC, tid, nameByTid.get(tid)))
      }
      events.push(...syncEvents)
    }
  }

  return events
}

/**
 * @param {object} trace
 * @param {{ lo?: number|null, hi?: number|null }} [range]
 * @returns {{ traceEvents: object[], displayTimeUnit: string, otherData: object }}
 */
export function buildPerfettoChromeTrace(trace, range = {}) {
  const { lo, hi } = normalizeExportRange(range.lo ?? null, range.hi ?? null)
  const meta = trace.meta && typeof trace.meta === 'object' ? { ...trace.meta } : {}
  const otherData = {
    source: 'RTOS BTF Viewer',
    timeScale: trace.timeScale,
    time_min: trace.timeMin,
    time_max: trace.timeMax,
    btf_meta: meta,
  }
  if (lo != null && hi != null) {
    otherData.export_lo = lo
    otherData.export_hi = hi
  }
  return {
    traceEvents: buildPerfettoChromeEvents(trace, { lo, hi }),
    displayTimeUnit: 'ns',
    otherData,
  }
}

/**
 * Trigger a browser download of the Perfetto Chrome Trace JSON.
 * @param {object} trace
 * @param {string} [filename]
 * @param {{ lo?: number|null, hi?: number|null }} [range]
 */
export function downloadPerfetto(trace, filename = 'trace.json', range = {}) {
  const payload = buildPerfettoChromeTrace(trace, range)
  const blob = new Blob([JSON.stringify(payload)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}
