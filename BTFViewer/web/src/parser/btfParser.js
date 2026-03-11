/**
 * btfParser.js – 4-phase BTF trace file parser.
 *
 * Mirrors the Python parse_btf() function from btf_viewer.py.
 * Returns a BtfTrace object containing all pre-computed lookup tables
 * needed for efficient timeline rendering.
 *
 * Usage:
 *   import { parseBtf } from './parser/btfParser.js'
 *   const trace = parseBtf(fileText, progressCallback)
 *
 * progressCallback(pct, message) is optional; called with 0-100 + status string.
 */

import { bisectLeft, bisectRight } from '../utils/bisect.js'
import { makeLodSummary } from '../utils/lod.js'
import { parseTaskName, taskMergeKey, taskSortKey, resetStiColors } from '../utils/colors.js'

// LOD bin counts (match Python constants).
const LOD_SUMMARY_BINS       = 4096
const LOD_SUMMARY_BINS_ULTRA = 1024

// ---- Task-name helpers ----------------------------------------------------

function isCoreName(name) {
  return name.startsWith('Core_')
}

/**
 * Sorting comparator for task merge keys using taskSortKey tuple logic.
 */
function compareMergeKeys(mkA, mkB, reprMap) {
  const ka = taskSortKey(reprMap[mkA] || mkA)
  const kb = taskSortKey(reprMap[mkB] || mkB)
  for (let i = 0; i < ka.length; i++) {
    if (ka[i] < kb[i]) return -1
    if (ka[i] > kb[i]) return  1
  }
  return 0
}

function coreOrder(coreName) {
  if (coreName.startsWith('Core_')) {
    const tail = coreName.slice(5)
    if (/^\d+$/.test(tail)) return [0, parseInt(tail), coreName]
  }
  return [1, Infinity, coreName]
}

function compareCores(a, b) {
  const ka = coreOrder(a), kb = coreOrder(b)
  for (let i = 0; i < ka.length; i++) {
    if (ka[i] < kb[i]) return -1
    if (ka[i] > kb[i]) return  1
  }
  return 0
}

// ---- Main parser ----------------------------------------------------------

/**
 * Parse a BTF file text string and return a BtfTrace object.
 *
 * @param {string}   text              Full file content as a string.
 * @param {Function} [progressCallback] Called as (pct:number, msg:string).
 * @returns {object} BtfTrace
 */
export function parseBtf(text, progressCallback) {
  const progress = progressCallback || (() => {})

  // Reset STI colour state so colours are consistent across multiple file loads.
  resetStiColors()

  const meta = {}
  let timeScale = 'ns'

  // T-events grouped by timestamp.
  // Map<number, Array<{time, source, event, target, note}>>
  const tEventsByTime = new Map()
  const stiEvents = []

  let timeMin = 0
  let timeMax = 0
  let firstEvent = true

  // raw task name → first task_create timestamp
  const taskCreateRaw = new Map()

  // -----------------------------------------------------------------------
  // Phase 1 – File reading
  // -----------------------------------------------------------------------
  progress(2, 'Reading file…')

  const lines = text.split('\n')
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim()
    if (!line) continue

    if (line.startsWith('#')) {
      const stripped = line.slice(1).trim()
      const spaceIdx = stripped.indexOf(' ')
      if (spaceIdx !== -1) {
        const key = stripped.slice(0, spaceIdx)
        const value = stripped.slice(spaceIdx + 1).trim()
        meta[key] = value
        if (key === 'timeScale') timeScale = value
      }
      continue
    }

    const parts = line.split(',')
    // Re-join excess fields into the note slot so commas within notes are preserved.
    if (parts.length > 8) parts[7] = parts.splice(7).join(',')
    if (parts.length < 7) continue

    const t = parseInt(parts[0], 10)
    if (isNaN(t)) continue

    const evType = parts[3].trim()

    if (evType !== 'C') {
      if (firstEvent) {
        timeMin = timeMax = t
        firstEvent = false
      } else {
        if (t < timeMin) timeMin = t
        if (t > timeMax) timeMax = t
      }
    }

    if (evType === 'T') {
      const note = parts.length > 7 ? parts[7].trim() : ''
      const tgt = parts[4].trim()
      if (note === 'task_create' && !taskCreateRaw.has(tgt)) {
        taskCreateRaw.set(tgt, t)
      }
      if (!tEventsByTime.has(t)) tEventsByTime.set(t, [])
      tEventsByTime.get(t).push({
        time:   t,
        source: parts[1].trim(),
        event:  parts[6].trim(),
        target: tgt,
        note,
      })
    } else if (evType === 'STI') {
      stiEvents.push({
        time:   t,
        core:   parts[1].trim(),
        target: parts[4].trim(),
        event:  parts[6].trim(),
        note:   parts.length > 7 ? parts[7].trim() : '',
      })
    }
  }

  // -----------------------------------------------------------------------
  // Phase 2 – State-machine segment reconstruction
  // -----------------------------------------------------------------------
  progress(25, 'Reconstructing segments…')

  const openSeg  = new Map()  // taskName → {start, core}
  const lastCore = new Map()  // taskName → coreName
  const segments = []

  function closeSeg(task, endTime) {
    const open = openSeg.get(task)
    if (open) {
      openSeg.delete(task)
      if (endTime > open.start) {
        segments.push({ task, start: open.start, end: endTime, core: open.core })
      }
    }
  }

  function openSegFn(task, startTime, core) {
    closeSeg(task, startTime)
    openSeg.set(task, { start: startTime, core })
    lastCore.set(task, core)
  }

  // Process events in chronological order
  const sortedTimestamps = Array.from(tEventsByTime.keys()).sort((a, b) => a - b)
  for (const ts of sortedTimestamps) {
    const events = tEventsByTime.get(ts)

    // Build core-preempt map: preempted-task → core (for Core_N src events)
    const corePreempts = new Map()
    for (const ev of events) {
      if (ev.event === 'preempt' && isCoreName(ev.source)) {
        corePreempts.set(ev.target, ev.source)
      }
    }

    // Build set of tasks that have a resume at this tick
    const resumeSources = new Set()
    for (const ev of events) {
      if (ev.event === 'resume') resumeSources.add(ev.source)
    }

    // Pass A – resume events
    for (const ev of events) {
      if (ev.event !== 'resume') continue
      let core
      if (corePreempts.has(ev.source)) {
        core = corePreempts.get(ev.source)
      } else if (isCoreName(ev.source)) {
        core = ev.source
      } else if (lastCore.has(ev.source)) {
        core = lastCore.get(ev.source)
      } else {
        core = 'Core_?'
      }
      closeSeg(ev.source, ts)
      openSegFn(ev.target, ts, core)
    }

    // Pass B – preempt events without matching resume
    for (const ev of events) {
      if (ev.event !== 'preempt') continue
      if (!resumeSources.has(ev.target)) {
        closeSeg(ev.target, ts)
        if (isCoreName(ev.source)) {
          lastCore.set(ev.target, ev.source)
        }
      }
    }
  }

  // Close any still-open segments at trace end
  for (const [task] of openSeg) {
    closeSeg(task, timeMax)
  }

  // -----------------------------------------------------------------------
  // Phase 3 – Post-processing: build lookup tables
  // -----------------------------------------------------------------------
  progress(55, 'Building lookup tables…')

  const mkCache = new Map()        // rawTaskName → mergeKey
  const segsByMkBuild = new Map()  // mergeKey   → TaskSegment[]
  const coreSegsBuild = new Map()  // coreName   → TaskSegment[]
  const cnSet = new Set()

  for (const seg of segments) {
    if (isCoreName(seg.task) || !seg.task) continue
    let mk = mkCache.get(seg.task)
    if (mk === undefined) {
      mk = taskMergeKey(seg.task)
      mkCache.set(seg.task, mk)
    }
    if (!segsByMkBuild.has(mk)) segsByMkBuild.set(mk, [])
    segsByMkBuild.get(mk).push(seg)

    // TICK on Core_? – suppress from unknown-core row in core view
    const { name } = parseTaskName(seg.task)
    if (!(name === 'TICK' && seg.core === 'Core_?')) {
      if (!coreSegsBuild.has(seg.core)) coreSegsBuild.set(seg.core, [])
      coreSegsBuild.get(seg.core).push(seg)
      cnSet.add(seg.core)
    }
  }

  // Build representative-raw-name map per merge key
  const mkRepr = new Map()  // mergeKey → raw task name
  for (const [raw, mk] of mkCache) {
    if (!mkRepr.has(mk)) mkRepr.set(mk, raw)
  }

  // Build tasks list (sorted, excluding TICK)
  const tickMk = taskMergeKey('TICK')
  const reprObj = Object.fromEntries(mkRepr)
  const tasks = Array.from(segsByMkBuild.keys())
    .filter(mk => mk !== tickMk)
    .sort((a, b) => compareMergeKeys(a, b, reprObj))

  // Sort segments within each merge key
  const segsByMk = new Map()
  for (const [mk, segs] of segsByMkBuild) {
    segsByMk.set(mk, segs.sort((a, b) => a.start - b.start))
  }

  // STI channels
  const stiChannels = [...new Set(stiEvents.map(e => e.target))].sort()
  const stiByTarget = new Map()
  for (const ev of stiEvents) {
    if (!stiByTarget.has(ev.target)) stiByTarget.set(ev.target, [])
    stiByTarget.get(ev.target).push(ev)
  }

  // Core names sorted
  const coreNames = [...cnSet].sort(compareCores)
  const coreSegs = new Map()
  for (const c of coreNames) {
    const segs = (coreSegsBuild.get(c) || []).sort((a, b) => a.start - b.start)
    coreSegs.set(c, segs)
  }

  // Per-core, per-task ordering for core view
  progress(62, 'Sorting core segments…')
  const coreTaskOrder = new Map()  // coreName → taskRawName[]
  const coreTaskSegs  = new Map()  // coreName → Map<taskRawName, TaskSegment[]>

  for (const c of coreNames) {
    const taskMap = new Map()
    for (const seg of coreSegs.get(c)) {
      if (!taskMap.has(seg.task)) taskMap.set(seg.task, [])
      taskMap.get(seg.task).push(seg)
    }
    for (const segs of taskMap.values()) segs.sort((a, b) => a.start - b.start)
    coreTaskSegs.set(c, taskMap)
    coreTaskOrder.set(c, [...taskMap.keys()].sort((a, b) => {
      const ka = taskSortKey(a), kb = taskSortKey(b)
      for (let i = 0; i < ka.length; i++) {
        if (ka[i] < kb[i]) return -1
        if (ka[i] > kb[i]) return  1
      }
      return 0
    }))
  }

  // task_create times mapped to merge keys
  const taskCreateTimes = new Map()
  for (const [rawCt, ctTime] of taskCreateRaw) {
    const mkCt = mkCache.get(rawCt) || taskMergeKey(rawCt)
    if (!taskCreateTimes.has(mkCt) || ctTime < taskCreateTimes.get(mkCt)) {
      taskCreateTimes.set(mkCt, ctTime)
    }
  }

  // -----------------------------------------------------------------------
  // Phase 4 – 1M-event performance pre-processing (LOD + bisect arrays)
  // -----------------------------------------------------------------------
  progress(70, 'Building task LOD summaries…')

  const timeSpan = Math.max(timeMax - timeMin, 1)
  const lodTimescalePerPx      = timeSpan / LOD_SUMMARY_BINS
  const lodUltraTimescalePerPx = timeSpan / LOD_SUMMARY_BINS_ULTRA

  // Task-view: start arrays + LOD summaries keyed by merge key
  const segStartByMk          = new Map()
  const segLodByMk            = new Map()
  const segLodStartsByMk      = new Map()
  const segLodUltraByMk       = new Map()
  const segLodUltraStartsByMk = new Map()

  for (const [mk, segs] of segsByMk) {
    segStartByMk.set(mk, segs.map(s => s.start))
    const lod = makeLodSummary(segs, LOD_SUMMARY_BINS, lodTimescalePerPx, timeMin)
    segLodByMk.set(mk, lod)
    segLodStartsByMk.set(mk, lod.map(s => s.start))
    const ultra = makeLodSummary(lod, LOD_SUMMARY_BINS_ULTRA, lodUltraTimescalePerPx, timeMin)
    segLodUltraByMk.set(mk, ultra)
    segLodUltraStartsByMk.set(mk, ultra.map(s => s.start))
  }

  progress(80, 'Building core LOD summaries…')

  // Core-view: start arrays + LODs for core summary rows
  const coreSegStarts            = new Map()
  const coreSegLod               = new Map()
  const coreSegLodStarts         = new Map()
  const coreSegLodUltra          = new Map()
  const coreSegLodUltraStarts    = new Map()

  for (const c of coreNames) {
    const segs = coreSegs.get(c)
    coreSegStarts.set(c, segs.map(s => s.start))
    const lod = makeLodSummary(segs, LOD_SUMMARY_BINS, lodTimescalePerPx, timeMin)
    coreSegLod.set(c, lod)
    coreSegLodStarts.set(c, lod.map(s => s.start))
    const ultra = makeLodSummary(lod, LOD_SUMMARY_BINS_ULTRA, lodUltraTimescalePerPx, timeMin)
    coreSegLodUltra.set(c, ultra)
    coreSegLodUltraStarts.set(c, ultra.map(s => s.start))
  }

  progress(88, 'Building per-task core LOD summaries…')

  const coreTaskSegStarts         = new Map()
  const coreTaskSegLod            = new Map()
  const coreTaskSegLodStarts      = new Map()
  const coreTaskSegLodUltra       = new Map()
  const coreTaskSegLodUltraStarts = new Map()

  for (const c of coreNames) {
    const ts = coreTaskSegs.get(c)
    const tsStarts = new Map(), tsLod = new Map(), tsLodStarts = new Map()
    const tsLodUltra = new Map(), tsLodUltraStarts = new Map()
    for (const [tn, tsegs] of ts) {
      tsStarts.set(tn, tsegs.map(s => s.start))
      const lod = makeLodSummary(tsegs, LOD_SUMMARY_BINS, lodTimescalePerPx, timeMin)
      tsLod.set(tn, lod)
      tsLodStarts.set(tn, lod.map(s => s.start))
      const ultra = makeLodSummary(lod, LOD_SUMMARY_BINS_ULTRA, lodUltraTimescalePerPx, timeMin)
      tsLodUltra.set(tn, ultra)
      tsLodUltraStarts.set(tn, ultra.map(s => s.start))
    }
    coreTaskSegStarts.set(c, tsStarts)
    coreTaskSegLod.set(c, tsLod)
    coreTaskSegLodStarts.set(c, tsLodStarts)
    coreTaskSegLodUltra.set(c, tsLodUltra)
    coreTaskSegLodUltraStarts.set(c, tsLodUltraStarts)
  }

  // STI start-time arrays for bisect clipping
  const stiStartsByTarget = new Map()
  for (const [ch, evs] of stiByTarget) {
    stiStartsByTarget.set(ch, evs.map(e => e.time))
  }

  progress(95, 'Finalising…')

  return {
    // ---- Metadata ----
    timeScale,
    meta,
    timeMin,
    timeMax,

    // ---- Task view ----
    tasks,              // merge keys, sorted
    taskRepr: mkRepr,   // mergeKey → representative raw name

    // ---- All segments (raw) ----
    segments,

    // ---- STI events ----
    stiEvents,
    stiChannels,
    stiEventsByTarget: stiByTarget,
    stiStartsByTarget,

    // ---- Task-view lookup tables ----
    segByMergeKey:              segsByMk,
    segStartByMergeKey:         segStartByMk,
    segLodByMergeKey:           segLodByMk,
    segLodStartsByMergeKey:     segLodStartsByMk,
    segLodUltraByMergeKey:      segLodUltraByMk,
    segLodUltraStartsByMergeKey: segLodUltraStartsByMk,

    // ---- Core-view lookup tables ----
    coreNames,
    coreSegs,
    coreSegStarts,
    coreSegLod,
    coreSegLodStarts,
    coreSegLodUltra,
    coreSegLodUltraStarts,
    coreTaskOrder,
    coreTaskSegs,
    coreTaskSegStarts,
    coreTaskSegLod,
    coreTaskSegLodStarts,
    coreTaskSegLodUltra,
    coreTaskSegLodUltraStarts,

    // ---- LOD thresholds ----
    lodTimescalePerPx,
    lodUltraTimescalePerPx,

    // ---- Other ----
    taskCreateTimes,
  }
}

/**
 * Return the segments visible in the viewport [nsLo, nsHi], using
 * the appropriate LOD level based on the current zoom.
 *
 * @param {object}  lodData  Object with { segs, starts, lodSegs, lodStarts, ultraSegs, ultraStarts }
 * @param {number}  nsLo     Viewport start in trace time units.
 * @param {number}  nsHi     Viewport end in trace time units.
 * @param {number}  tpp      Current timescale per pixel (ns or trace units per px).
 * @param {number}  lodTpp   LOD threshold (use coarse LOD above this value).
 * @param {number}  ultraTpp Ultra-LOD threshold (use ultra-coarse LOD above this value).
 * @returns {Array} Visible segments array.
 */
export function visibleSegs(lodData, nsLo, nsHi, tpp, lodTpp, ultraTpp) {
  let segs, starts
  if (tpp >= ultraTpp) {
    segs = lodData.ultraSegs; starts = lodData.ultraStarts
  } else if (tpp >= lodTpp) {
    segs = lodData.lodSegs; starts = lodData.lodStarts
  } else {
    segs = lodData.segs; starts = lodData.starts
  }
  if (!segs || segs.length === 0) return []
  const lo = bisectLeft(starts, nsLo)
  const hi = bisectRight(starts, nsHi)
  // lo is the first segment starting >= nsLo; but we also want segments
  // that STARTED before nsLo yet END after it (i.e., are currently running).
  // Back up one step to catch that case.
  const from = Math.max(0, lo - 1)
  return segs.slice(from, hi + 1)
}
