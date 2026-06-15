/**
 * Pack / unpack trace for transferable worker → main transfer.
 */
import { SegStore, createSegList, finalizeTraceStorage } from './segStore.js'
import { buildCpuLoadBins } from './cpuLoadBins.js'
import { computeTaskCpuNs, segIndicesMapFromTrace } from './statsCompute.js'

function packPlainMap(map) {
  return [...map.entries()]
}

function copyBuffer(buf) {
  return buf instanceof ArrayBuffer ? buf.slice(0) : buf
}

function packIndicesMap(map) {
  const out = []
  for (const [k, list] of map) {
    out.push([k, copyBuffer(list._indices.buffer)])
  }
  return out
}

function packNestedIndicesMap(map) {
  const out = []
  for (const [core, inner] of map) {
    const tasks = []
    for (const [task, list] of inner) {
      tasks.push([task, copyBuffer(list._indices.buffer)])
    }
    out.push([core, tasks])
  }
  return out
}

function startsMapFromSegMap(store, segMap) {
  const out = new Map()
  for (const [k, list] of segMap) {
    out.set(k, store.startsForIndices(list._indices))
  }
  return out
}

function nestedStartsMapFromSegMap(store, nestedMap) {
  const out = new Map()
  for (const [core, inner] of nestedMap) {
    const innerOut = new Map()
    for (const [task, list] of inner) {
      innerOut.set(task, store.startsForIndices(list._indices))
    }
    out.set(core, innerOut)
  }
  return out
}

/**
 * Finalize flat storage, precompute bins, pack for postMessage transfer.
 */
export function packTrace(trace) {
  finalizeTraceStorage(trace)
  trace.cpuLoadBins = buildCpuLoadBins(trace.segStore, trace)
  const segIndicesByMk = segIndicesMapFromTrace(trace)
  trace.taskCpuNs = computeTaskCpuNs(
    trace.segStore, trace.tasks, trace.taskRepr, segIndicesByMk,
  )

  const store = trace.segStore
  const allIdx = store.allIndices()

  const segByMk = packIndicesMap(trace.segByMergeKey)
  const segLod = packIndicesMap(trace.segLodByMergeKey)
  const segUltra = packIndicesMap(trace.segLodUltraByMergeKey)

  const coreSegs = packIndicesMap(trace.coreSegs)
  const coreLod = packIndicesMap(trace.coreSegLod)
  const coreUltra = packIndicesMap(trace.coreSegLodUltra)

  const coreTaskSegs = packNestedIndicesMap(trace.coreTaskSegs)
  const coreTaskLod = packNestedIndicesMap(trace.coreTaskSegLod)
  const coreTaskUltra = packNestedIndicesMap(trace.coreTaskSegLodUltra)

  // Structured-clone only (no transfer list). Transferring store buffers while also
  // referencing them in the payload can yield detached/empty arrays in some browsers.
  return {
    transferables: [],
    payload: {
      timeScale: trace.timeScale,
      meta: trace.meta,
      timeMin: trace.timeMin,
      timeMax: trace.timeMax,
      skippedLines: trace.skippedLines,
      tasks: trace.tasks,
      taskRepr: packPlainMap(trace.taskRepr),
      store: {
        starts: copyBuffer(store.starts.buffer),
        ends: copyBuffer(store.ends.buffer),
        taskIds: copyBuffer(store.taskIds.buffer),
        coreIds: copyBuffer(store.coreIds.buffer),
        taskStrings: store.taskStrings,
        coreStrings: store.coreStrings,
      },
      allIndices: copyBuffer(allIdx.buffer),
      segByMergeKey: segByMk,
      segLodByMergeKey: segLod,
      segLodUltraByMergeKey: segUltra,
      coreNames: trace.coreNames,
      coreSegs,
      coreSegLod: coreLod,
      coreSegLodUltra: coreUltra,
      coreTaskOrder: packPlainMap(trace.coreTaskOrder),
      coreTaskSegs,
      coreTaskSegLod: coreTaskLod,
      coreTaskSegLodUltra: coreTaskUltra,
      lodTimescalePerPx: trace.lodTimescalePerPx,
      lodUltraTimescalePerPx: trace.lodUltraTimescalePerPx,
      taskCreateTimes: packPlainMap(trace.taskCreateTimes),
      migrations: trace.migrations,
      migrationsByMk: packPlainMap(trace.migrationsByMk),
      stiEvents: trace.stiEvents,
      stiChannels: trace.stiChannels,
      stiEventsByTarget: packPlainMap(trace.stiEventsByTarget),
      stiStartsByTarget: packPlainMap(trace.stiStartsByTarget),
      stiValRange: packPlainMap(trace.stiValRange),
      tickStiTimes: trace.tickStiTimes,
      tickHealth: trace.tickHealth,
      cpuLoadBins: trace.cpuLoadBins,
      taskCpuNs: trace.taskCpuNs,
    },
  }
}

function unpackIndicesMap(store, entries) {
  const m = new Map()
  for (const [k, buf] of entries) {
    m.set(k, createSegList(store, new Uint32Array(buf)))
  }
  return m
}

function unpackNestedIndicesMap(store, entries) {
  const m = new Map()
  for (const [core, tasks] of entries) {
    const inner = new Map()
    for (const [task, buf] of tasks) {
      inner.set(task, createSegList(store, new Uint32Array(buf)))
    }
    m.set(core, inner)
  }
  return m
}

function unpackPlainMap(entries) {
  return new Map(entries)
}

function enrichStartsMaps(store, trace) {
  trace.segStartByMergeKey = startsMapFromSegMap(store, trace.segByMergeKey)
  trace.segLodStartsByMergeKey = startsMapFromSegMap(store, trace.segLodByMergeKey)
  trace.segLodUltraStartsByMergeKey = startsMapFromSegMap(store, trace.segLodUltraByMergeKey)
  trace.coreSegStarts = startsMapFromSegMap(store, trace.coreSegs)
  trace.coreSegLodStarts = startsMapFromSegMap(store, trace.coreSegLod)
  trace.coreSegLodUltraStarts = startsMapFromSegMap(store, trace.coreSegLodUltra)
  trace.coreTaskSegStarts = nestedStartsMapFromSegMap(store, trace.coreTaskSegLod)
  trace.coreTaskSegLodStarts = nestedStartsMapFromSegMap(store, trace.coreTaskSegLod)
  trace.coreTaskSegLodUltraStarts = nestedStartsMapFromSegMap(store, trace.coreTaskSegLodUltra)
}

export function unpackTrace(packed) {
  const p = packed.payload ?? packed
  const store = SegStore.fromPacked(p.store)
  const segByMergeKey = unpackIndicesMap(store, p.segByMergeKey)
  const segLodByMergeKey = unpackIndicesMap(store, p.segLodByMergeKey)
  const segLodUltraByMergeKey = unpackIndicesMap(store, p.segLodUltraByMergeKey)
  const coreSegs = unpackIndicesMap(store, p.coreSegs)
  const coreSegLod = unpackIndicesMap(store, p.coreSegLod)
  const coreSegLodUltra = unpackIndicesMap(store, p.coreSegLodUltra)
  const coreTaskSegs = unpackNestedIndicesMap(store, p.coreTaskSegs)
  const coreTaskSegLod = unpackNestedIndicesMap(store, p.coreTaskSegLod)
  const coreTaskSegLodUltra = unpackNestedIndicesMap(store, p.coreTaskSegLodUltra)

  const trace = {
    timeScale: p.timeScale,
    meta: p.meta,
    timeMin: p.timeMin,
    timeMax: p.timeMax,
    skippedLines: p.skippedLines,
    tasks: p.tasks,
    taskRepr: unpackPlainMap(p.taskRepr),
    segStore: store,
    segments: createSegList(store, new Uint32Array(p.allIndices)),
    segByMergeKey,
    segLodByMergeKey,
    segLodUltraByMergeKey,
    coreNames: p.coreNames,
    coreSegs,
    coreSegLod,
    coreSegLodUltra,
    coreTaskOrder: unpackPlainMap(p.coreTaskOrder),
    coreTaskSegs,
    coreTaskSegLod,
    coreTaskSegLodUltra,
    lodTimescalePerPx: p.lodTimescalePerPx,
    lodUltraTimescalePerPx: p.lodUltraTimescalePerPx,
    taskCreateTimes: unpackPlainMap(p.taskCreateTimes),
    migrations: p.migrations,
    migrationsByMk: unpackPlainMap(p.migrationsByMk),
    stiEvents: p.stiEvents,
    stiChannels: p.stiChannels,
    stiEventsByTarget: unpackPlainMap(p.stiEventsByTarget),
    stiStartsByTarget: unpackPlainMap(p.stiStartsByTarget),
    stiValRange: unpackPlainMap(p.stiValRange),
    tickStiTimes: p.tickStiTimes,
    tickHealth: p.tickHealth,
    cpuLoadBins: p.cpuLoadBins,
    taskCpuNs: p.taskCpuNs,
  }
  enrichStartsMaps(store, trace)
  return trace
}

/** Main-thread parse path (no worker transfer). */
export function finalizeAndEnrich(trace) {
  finalizeTraceStorage(trace)
  trace.cpuLoadBins = buildCpuLoadBins(trace.segStore, trace)
  const segIndicesByMk = segIndicesMapFromTrace(trace)
  trace.taskCpuNs = computeTaskCpuNs(
    trace.segStore, trace.tasks, trace.taskRepr, segIndicesByMk,
  )
  return trace
}
