/**
 * Export a parsed BTF trace as Chrome Trace Event Format JSON for
 * https://ui.perfetto.dev (same layout as the desktop File → Export Perfetto…).
 */

import { taskDisplayName, taskLabelForMergeKey, taskMergeKey, taskReprGet } from './colors.js'
import { isIntervalMarkerChannel } from './intervalAnalysis.js'

const PID_CORES = 1
const PID_TASKS = 2
const PID_STI = 3
const PID_INTERVALS = 4

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

/**
 * Build Chrome Trace Event list from a parsed web *trace*.
 * @param {object} trace
 * @returns {object[]}
 */
export function buildPerfettoChromeEvents(trace) {
  const scale = trace.timeScale || 'ns'
  const events = []

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

    const ts = toTraceUs(seg.start, scale)
    let dur = toTraceUs(seg.end - seg.start, scale)
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

  // --- STI channels (skip interval_start/stop — those become Intervals) -
  const stiChannels = [...(trace.stiChannels || [])].filter(
    ch => !isIntervalMarkerChannel(ch),
  )
  const tickTimes = trace.tickStiTimes || []
  const stiEvents = [...(trace.stiEvents || [])].filter(
    ev => !isIntervalMarkerChannel(ev.target),
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
  if (intervals.length) {
    events.push(metaProcess(PID_INTERVALS, 'Intervals'))
    const idTid = new Map()
    for (const [i, iid] of (trace.intervalIds || []).entries()) {
      const tid = i + 1
      idTid.set(iid, tid)
      events.push(metaThread(PID_INTERVALS, tid, iid))
    }
    for (const inst of intervals) {
      let tid = idTid.get(inst.id)
      if (tid == null) {
        tid = idTid.size + 1
        idTid.set(inst.id, tid)
        events.push(metaThread(PID_INTERVALS, tid, inst.id))
      }
      const ts = toTraceUs(inst.startNs, scale)
      let dur = toTraceUs(inst.stopNs - inst.startNs, scale)
      if (dur < 0) dur = 0
      events.push({
        name: inst.id, cat: 'interval', ph: 'X',
        ts, dur, pid: PID_INTERVALS, tid,
        args: {
          start_core: inst.startCore || '',
          stop_core: inst.stopCore || '',
          task_id: inst.taskId || '',
        },
      })
    }
  }

  return events
}

/**
 * @param {object} trace
 * @returns {{ traceEvents: object[], displayTimeUnit: string, otherData: object }}
 */
export function buildPerfettoChromeTrace(trace) {
  const meta = trace.meta && typeof trace.meta === 'object' ? { ...trace.meta } : {}
  return {
    traceEvents: buildPerfettoChromeEvents(trace),
    displayTimeUnit: 'ns',
    otherData: {
      source: 'RTOS BTF Viewer',
      timeScale: trace.timeScale,
      time_min: trace.timeMin,
      time_max: trace.timeMax,
      btf_meta: meta,
    },
  }
}

/**
 * Trigger a browser download of the Perfetto Chrome Trace JSON.
 * @param {object} trace
 * @param {string} [filename]
 */
export function downloadPerfetto(trace, filename = 'trace.json') {
  const payload = buildPerfettoChromeTrace(trace)
  const blob = new Blob([JSON.stringify(payload)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}
