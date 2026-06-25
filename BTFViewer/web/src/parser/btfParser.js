/**
 * btfParser.js – 4-phase BTF trace file parser.
 *
 * Mirrors the Python parse_btf() function from btf_viewer.py.
 * Returns a BtfTrace object containing all pre-computed lookup tables
 * needed for efficient timeline rendering.
 *
 * Usage:
 *   import { parseBtf } from './parser/btfParser.js'
 *   const trace = await parseBtf(fileText, progressCallback)
 *
 * progressCallback(pct, message) is optional; called with 0-100 + status string.
 */

import { bisectLeft, bisectRight } from '../utils/bisect.js'
import { applyBtfVersionWarning } from '../utils/btfMeta.js'
import { makeLodSummary, segmentStartsF64, LOD_SUMMARY_BINS, LOD_SUMMARY_BINS_ULTRA } from '../utils/lod.js'
import { parseTaskName, taskMergeKey, taskSortKey, resetStiColors } from '../utils/colors.js'
import { buildMigrationIndex } from '../utils/migrationAnalysis.js'
import { analyzeTickHealth } from '../utils/tickHealth.js'
import { buildIntervalData, isIntervalMarkerChannel, buildIntervalMarkerIndex } from '../utils/intervalAnalysis.js'
import { buildPriorityData, parseCreatePriority } from '../utils/priorityAnalysis.js'
import { buildSyncObjectData } from '../utils/syncObjectAnalysis.js'

// LOD bin counts imported from lod.js (LOD_SUMMARY_BINS, LOD_SUMMARY_BINS_ULTRA).

// Yield to the host event loop so progress callbacks can repaint (main thread only).
const IN_WORKER = typeof globalThis.importScripts === 'function'
const LINE_YIELD_EVERY = IN_WORKER ? 65536 : 8192
const TS_YIELD_EVERY   = IN_WORKER ? 32768 : 4096
const LOD_YIELD_EVERY  = IN_WORKER ? 64 : 8
const STI_YIELD_EVERY  = IN_WORKER ? 32 : 4

function yieldToHost() {
  if (IN_WORKER) return Promise.resolve()
  return new Promise(resolve => setTimeout(resolve, 0))
}

// ---- Task-name helpers ----------------------------------------------------

function isCoreName(name) {
  return name.startsWith('Core_')
}

function coreFromTaskEntity(name) {
  const { coreId } = parseTaskName(name)
  return coreId === null ? null : `Core_${coreId}`
}

/**
 * Sorting comparator for task merge keys using taskSortKey tuple logic.
 */
function compareMergeKeys(mkA, mkB, reprMap) {
  const ka = taskSortKey((Object.hasOwn(reprMap, mkA) ? reprMap[mkA] : null) || mkA)
  const kb = taskSortKey((Object.hasOwn(reprMap, mkB) ? reprMap[mkB] : null) || mkB)
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
  return [1, Number.MAX_SAFE_INTEGER, coreName]
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
 * @returns {Promise<object>} BtfTrace
 */
export async function parseBtf(text, progressCallback) {
  const progress = progressCallback || (() => {})

  // Reset STI colour state so colours are consistent across multiple file loads.
  resetStiColors()

  const meta = Object.create(null)
  let timeScale = 'ns'

  // T-events grouped by timestamp.
  // Map<number, Array<{time, source, event, target, note}>>
  const tEventsByTime = new Map()
  const stiEvents = []
  const tickStiTimes = []  // timestamps from STI TICK events → drawn on ruler

  let timeMin = 0
  let timeMax = 0
  let firstEvent = true

  // raw task name → first task_create / create pri timestamp
  const taskCreateRaw = new Map()
  // raw task name → { time, priority } from create pri:N
  const taskCreatePriRaw = new Map()

  // -----------------------------------------------------------------------
  // Phase 1 – File reading (line-at-a-time so progress can update during scan)
  // -----------------------------------------------------------------------
  progress(1, 'Reading file…')
  await yieldToHost()

  let skippedLines = 0
  const textLen = text.length
  let pos = 0
  let lineIndex = 0

  while (pos <= textLen) {
    let lineEnd = text.indexOf('\n', pos)
    if (lineEnd === -1) lineEnd = textLen
    const line = text.slice(pos, lineEnd).trim()
    pos = lineEnd < textLen ? lineEnd + 1 : textLen + 1

    if (line) {
      if (line.startsWith('#')) {
        const stripped = line.slice(1).trim()
        const spaceIdx = stripped.indexOf(' ')
        if (spaceIdx !== -1) {
          const key = stripped.slice(0, spaceIdx)
          const value = stripped.slice(spaceIdx + 1).trim()
          if (/^[\w.-]+$/.test(key)) meta[key] = value
          if (key === 'timeScale') timeScale = value
        }
      } else {
        const parts = line.split(',')
        // Re-join excess fields into the note slot so commas within notes are preserved.
        if (parts.length > 8) parts[7] = parts.splice(7).join(',')
        if (parts.length < 7) {
          skippedLines++
        } else {
          const t = parseInt(parts[0], 10)
          if (isNaN(t) || !Number.isSafeInteger(t)) {
            skippedLines++
          } else {
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
              const createPri = parseCreatePriority(note)
              if (createPri != null) {
                if (!taskCreateRaw.has(tgt)) taskCreateRaw.set(tgt, t)
                if (!taskCreatePriRaw.has(tgt)) {
                  taskCreatePriRaw.set(tgt, { time: t, priority: createPri })
                }
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
              const stiTarget = parts[4].trim()
              if (stiTarget === 'TICK') {
                // STI TICK events are rendered as ruler marks, not as STI channel rows.
                tickStiTimes.push(t)
              } else {
                stiEvents.push({
                  time:   t,
                  core:   parts[1].trim(),
                  target: stiTarget,
                  event:  parts[6].trim(),
                  note:   parts.length > 7 ? parts[7].trim() : '',
                })
              }
            }
          }
        }
      }
    }

    lineIndex++
    if (lineIndex % LINE_YIELD_EVERY === 0) {
      const filePct = textLen > 0 ? Math.min(100, Math.floor((lineEnd / textLen) * 100)) : 100
      progress(1 + Math.floor((lineEnd / Math.max(textLen, 1)) * 22), `Reading file… ${filePct}%`)
      await yieldToHost()
    }
  }

  // -----------------------------------------------------------------------
  // Phase 2 – State-machine segment reconstruction
  // -----------------------------------------------------------------------
  progress(25, 'Reconstructing segments…')
  await yieldToHost()

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
  const tsCount = sortedTimestamps.length
  for (let ti = 0; ti < tsCount; ti++) {
    const ts = sortedTimestamps[ti]
    const events = tEventsByTime.get(ts)

    // Build core-preempt map: preempted-task → core (for Core_N src events)
    const corePreempts = new Map()
    for (const ev of events) {
      if (ev.event === 'preempt') {
        if (isCoreName(ev.source)) {
          corePreempts.set(ev.target, ev.source)
        } else {
          const srcCore = coreFromTaskEntity(ev.source)
          if (srcCore !== null) corePreempts.set(ev.target, srcCore)
        }
      }
    }

    // Build set of sources that issued a resume (detects naked preempts)
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
        core = coreFromTaskEntity(ev.source) || coreFromTaskEntity(ev.target) || 'Core_0'
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
        } else {
          const srcCore = coreFromTaskEntity(ev.source)
          if (srcCore !== null) lastCore.set(ev.target, srcCore)
        }
      }
    }

    if (ti > 0 && ti % TS_YIELD_EVERY === 0) {
      progress(25 + Math.floor((ti / tsCount) * 28), 'Reconstructing segments…')
      await yieldToHost()
    }
  }

  // Close any still-open segments at trace end
  for (const [task] of openSeg) {
    closeSeg(task, timeMax)
  }
  tEventsByTime.clear()  // release per-timestamp event arrays; no longer needed

  // -----------------------------------------------------------------------
  // Phase 3 – Post-processing: build lookup tables
  // -----------------------------------------------------------------------
  progress(55, 'Building lookup tables…')
  await yieldToHost()

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

    // Exclude ALL TICK segments from coreSegs: TICK is rendered as ruler
    // band marks (from segByMergeKey), not as per-core timeline bars.  If TICK
    // is kept in coreSegs it can become the first entry in a LOD bin (because
    // TICK resume events appear before task resume events in the BTF file),
    // causing the LOD de-duplication to drop real task segments and leaving the
    // core summary row empty after TICK is filtered from rendering.
    const { name } = parseTaskName(seg.task)
    if (name !== 'TICK') {
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
  const { migrations, migrationsByMk } = buildMigrationIndex(segsByMk)

  // STI channels
  const stiChannels = [...new Set(stiEvents.map(e => e.target))]
    .filter(ch => !isIntervalMarkerChannel(ch))
    .sort()
  const stiByTarget = new Map()
  for (const ev of stiEvents) {
    if (!stiByTarget.has(ev.target)) stiByTarget.set(ev.target, [])
    stiByTarget.get(ev.target).push(ev)
  }

  progress(58, 'Pairing interval events…')
  await yieldToHost()
  const {
    intervalInstances,
    intervalIds,
    intervalInstancesById,
    unmatchedStarts: intervalUnmatchedStarts,
  } = buildIntervalData(stiEvents)
  const intervalMarkerById = buildIntervalMarkerIndex(stiEvents)

  // Core names sorted
  const coreNames = [...cnSet].sort(compareCores)
  const coreSegs = new Map()
  for (const c of coreNames) {
    const segs = (coreSegsBuild.get(c) || []).sort((a, b) => a.start - b.start)
    coreSegs.set(c, segs)
  }

  // Per-core, per-task ordering for core view
  progress(62, 'Sorting core segments…')
  await yieldToHost()
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

  const taskCreatePriByRaw = new Map()
  for (const [raw, rec] of taskCreatePriRaw) {
    taskCreatePriByRaw.set(raw, rec)
  }
  const {
    taskBasePriority,
    priorityEpisodes,
    priorityEpisodesByMk,
    prioritySummaryByMk,
    hasPriorityInstrumentation,
  } = buildPriorityData(stiEvents, taskCreatePriByRaw, timeMax, mkCache, mkRepr)

  progress(60, 'Analysing mutex/semaphore STI…')
  await yieldToHost()
  const {
    syncObjects,
    syncIssues,
    hasSyncObjectInstrumentation,
  } = buildSyncObjectData(stiEvents, coreSegs, mkRepr, timeMax)

  // -----------------------------------------------------------------------
  // Phase 4 – 1M-event performance pre-processing (LOD + bisect arrays)
  // -----------------------------------------------------------------------
  progress(70, 'Building task LOD summaries…')
  await yieldToHost()

  const timeSpan = Math.max(timeMax - timeMin, 1)
  const lodTimescalePerPx      = timeSpan / LOD_SUMMARY_BINS
  const lodUltraTimescalePerPx = timeSpan / LOD_SUMMARY_BINS_ULTRA

  // Task-view: start arrays + LOD summaries keyed by merge key
  const segStartByMk          = new Map()
  const segLodByMk            = new Map()
  const segLodStartsByMk      = new Map()
  const segLodUltraByMk       = new Map()
  const segLodUltraStartsByMk = new Map()

  const mkEntries = [...segsByMk.entries()]
  for (let mi = 0; mi < mkEntries.length; mi++) {
    const [mk, segs] = mkEntries[mi]
    segStartByMk.set(mk, segmentStartsF64(segs))
    const [lod, lodStarts] = makeLodSummary(segs, LOD_SUMMARY_BINS, lodTimescalePerPx, timeMin)
    segLodByMk.set(mk, lod)
    segLodStartsByMk.set(mk, lodStarts)
    const [ultra, ultraStarts] = makeLodSummary(lod, LOD_SUMMARY_BINS_ULTRA, lodUltraTimescalePerPx, timeMin)
    segLodUltraByMk.set(mk, ultra)
    segLodUltraStartsByMk.set(mk, ultraStarts)

    if (mi > 0 && mi % LOD_YIELD_EVERY === 0) {
      progress(70 + Math.floor((mi / mkEntries.length) * 9), 'Building task LOD summaries…')
      await yieldToHost()
    }
  }

  progress(80, 'Building core LOD summaries…')
  await yieldToHost()

  // Core-view: start arrays + LODs for core summary rows
  const coreSegStarts            = new Map()
  const coreSegLod               = new Map()
  const coreSegLodStarts         = new Map()
  const coreSegLodUltra          = new Map()
  const coreSegLodUltraStarts    = new Map()

  for (let ci = 0; ci < coreNames.length; ci++) {
    const c = coreNames[ci]
    const segs = coreSegs.get(c)
    coreSegStarts.set(c, segmentStartsF64(segs))
    const [lod, lodStarts] = makeLodSummary(segs, LOD_SUMMARY_BINS, lodTimescalePerPx, timeMin)
    coreSegLod.set(c, lod)
    coreSegLodStarts.set(c, lodStarts)
    const [ultra, ultraStarts] = makeLodSummary(lod, LOD_SUMMARY_BINS_ULTRA, lodUltraTimescalePerPx, timeMin)
    coreSegLodUltra.set(c, ultra)
    coreSegLodUltraStarts.set(c, ultraStarts)

    if (ci > 0 && ci % LOD_YIELD_EVERY === 0) {
      progress(80 + Math.floor((ci / coreNames.length) * 7), 'Building core LOD summaries…')
      await yieldToHost()
    }
  }

  progress(88, 'Finalising segment tables…')
  await yieldToHost()

  // Per-task core LOD is built in finalizeTraceStorage (index-based + WASM).
  const coreTaskSegLod            = new Map()
  const coreTaskSegLodUltra       = new Map()
  const coreTaskSegStarts         = new Map()
  const coreTaskSegLodStarts      = new Map()
  const coreTaskSegLodUltraStarts = new Map()

  // STI start-time arrays for bisect clipping
  progress(92, 'Building STI indexes…')
  await yieldToHost()

  const stiStartsByTarget = new Map()
  const stiChannelCount = stiByTarget.size
  let stiIdx = 0
  for (const [ch, evs] of stiByTarget) {
    stiStartsByTarget.set(ch, evs.map(e => e.time))
    stiIdx++
    if (stiIdx % STI_YIELD_EVERY === 0) {
      progress(92 + Math.floor((stiIdx / Math.max(stiChannelCount, 1)) * 3), 'Building STI indexes…')
      await yieldToHost()
    }
  }

  // STI numeric value ranges (valMin/valMax per channel) for waveform rows.
  // Mirrors the evVal() logic in TimelineRenderer.js so the renderer can skip
  // the O(N) scan on every animation frame.
  progress(95, 'Analysing STI channels…')
  await yieldToHost()

  const stiValRange = new Map()
  stiIdx = 0
  for (const [ch, evs] of stiByTarget) {
    let vMin = Infinity, vMax = -Infinity
    for (const ev of evs) {
      const v = parseFloat(ev.note !== '' ? ev.note : ev.event)
      if (isNaN(v)) continue
      if (v < vMin) vMin = v
      if (v > vMax) vMax = v
    }
    if (isFinite(vMin)) stiValRange.set(ch, { min: vMin, max: vMax })
    stiIdx++
    if (stiIdx % STI_YIELD_EVERY === 0) {
      progress(95 + Math.floor((stiIdx / Math.max(stiChannelCount, 1)) * 2), 'Analysing STI channels…')
      await yieldToHost()
    }
  }

  progress(97, 'Finalising…')
  await yieldToHost()
  const sortedTickStiTimes = tickStiTimes.sort((a, b) => a - b)
  progress(98, 'Analysing tick health…')
  await yieldToHost()
  const tickHealth = analyzeTickHealth(sortedTickStiTimes)

  applyBtfVersionWarning(meta)

  return {
    // ---- Metadata ----
    timeScale,
    meta,
    timeMin,
    timeMax,
    skippedLines,

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
    stiValRange,
    tickStiTimes: sortedTickStiTimes,
    tickHealth,

    // ---- Interval instrumentation (paired start/stop) ----
    intervalInstances,
    intervalIds,
    intervalInstancesById,
    intervalUnmatchedStarts,
    intervalMarkerById,

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

    // ---- Priority inheritance (create pri + set_priority) ----
    taskBasePriority,
    priorityEpisodes,
    priorityEpisodesByMk,
    prioritySummaryByMk,
    hasPriorityInstrumentation,

    syncObjects,
    syncIssues,
    hasSyncObjectInstrumentation,

    // ---- Core migrations ----
    migrations,
    migrationsByMk,
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
