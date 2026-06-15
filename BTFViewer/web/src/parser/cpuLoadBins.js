/**
 * CPU load graph bins — built once at parse time (parity with CpuLoadPanel).
 */
import { parseTaskName, isIdleTaskName, taskMergeKey } from '../utils/colors.js'

export const CPU_LOAD_NUM_BINS = 1024

export function buildCpuLoadBins(store, trace) {
  const n = CPU_LOAD_NUM_BINS
  const tMin = trace.timeMin
  const tMax = trace.timeMax
  const span = Math.max(1, tMax - tMin)
  const binW = span / n
  const cores = trace.coreNames || []

  const coreBusy = Object.fromEntries(cores.map(core => [core, new Float64Array(n)]))
  const coreDiff = Object.fromEntries(cores.map(core => [core, new Float64Array(n + 2)]))
  const taskBusy = new Map()
  const taskDiff = new Map()
  const taskCoreBusy = new Map()
  const taskCoreDiff = new Map()

  const count = store.count
  const { starts, ends, taskIds, coreIds, taskStrings, coreStrings } = store

  for (let si = 0; si < count; si++) {
    const start = starts[si]
    const end = ends[si]
    const task = taskStrings[taskIds[si]]
    const core = coreStrings[coreIds[si]]
    const mk = taskMergeKey(task)
    const { name } = parseTaskName(task)
    const skipCoreLoad = isIdleTaskName(name) || name.toUpperCase() === 'TICK'

    const rawB0 = Math.floor((start - tMin) / binW)
    const rawB1 = Math.floor((end - tMin) / binW)
    const b0 = Math.max(0, Math.min(n - 1, rawB0))
    const b1 = Math.max(0, Math.min(n - 1, rawB1))

    const firstEnd = tMin + (b0 + 1) * binW
    const firstChunk = Math.max(0, Math.min(end, firstEnd) - start)
    const lastChunk = Math.max(0, end - (tMin + b1 * binW))

    if (!skipCoreLoad && coreBusy[core]) {
      const busy = coreBusy[core]
      const diff = coreDiff[core]
      busy[b0] += firstChunk
      if (b1 > b0) {
        busy[b1] += lastChunk
        if (b1 > b0 + 1) {
          diff[b0 + 1] += binW
          diff[b1] -= binW
        }
      }
    }

    if (!taskBusy.has(mk)) {
      taskBusy.set(mk, new Float64Array(n))
      taskDiff.set(mk, new Float64Array(n + 2))
    }
    const totalBusy = taskBusy.get(mk)
    const totalDiff = taskDiff.get(mk)
    totalBusy[b0] += firstChunk
    if (b1 > b0) {
      totalBusy[b1] += lastChunk
      if (b1 > b0 + 1) {
        totalDiff[b0 + 1] += binW
        totalDiff[b1] -= binW
      }
    }

    if (!taskCoreBusy.has(mk)) {
      taskCoreBusy.set(mk, new Map())
      taskCoreDiff.set(mk, new Map())
    }
    const perCoreBusy = taskCoreBusy.get(mk)
    const perCoreDiff = taskCoreDiff.get(mk)
    if (!perCoreBusy.has(core)) {
      perCoreBusy.set(core, new Float64Array(n))
      perCoreDiff.set(core, new Float64Array(n + 2))
    }
    const taskCoreBusyBins = perCoreBusy.get(core)
    const taskCoreDiffBins = perCoreDiff.get(core)
    taskCoreBusyBins[b0] += firstChunk
    if (b1 > b0) {
      taskCoreBusyBins[b1] += lastChunk
      if (b1 > b0 + 1) {
        taskCoreDiffBins[b0 + 1] += binW
        taskCoreDiffBins[b1] -= binW
      }
    }
  }

  const inv = 1 / binW
  const materialize = (busy, diff) => {
    const out = new Float64Array(n)
    let run = 0
    for (let i = 0; i < n; i++) {
      run += diff[i]
      out[i] = Math.min(1, Math.max(0, (busy[i] + run) * inv))
    }
    return out
  }

  const coreBins = {}
  for (const core of cores) {
    coreBins[core] = materialize(coreBusy[core], coreDiff[core])
  }

  const taskBins = {}
  for (const [mk, busy] of taskBusy) {
    taskBins[mk] = materialize(busy, taskDiff.get(mk))
  }

  const taskCoreBins = {}
  for (const [mk, coreMap] of taskCoreBusy) {
    const perCore = {}
    const diffs = taskCoreDiff.get(mk)
    for (const [core, busy] of coreMap) {
      perCore[core] = materialize(busy, diffs.get(core))
    }
    taskCoreBins[mk] = perCore
  }

  const totalBins = new Float64Array(n)
  const nCores = cores.length
  if (nCores > 0) {
    for (let i = 0; i < n; i++) {
      let sum = 0
      for (const core of cores) sum += coreBins[core][i]
      totalBins[i] = Math.min(1, Math.max(0, sum / nCores))
    }
  }
  const avgLoad = {}
  for (const core of cores) {
    const bins = coreBins[core]
    let sum = 0
    for (let i = 0; i < n; i++) sum += bins[i]
    avgLoad[core] = sum / n
  }
  for (const [mk, bins] of Object.entries(taskBins)) {
    let sum = 0
    for (let i = 0; i < n; i++) sum += bins[i]
    avgLoad[mk] = sum / n
  }
  avgLoad.total = n > 0 ? [...totalBins].reduce((a, b) => a + b, 0) / n : 0

  return {
    binWNs: binW,
    numBins: n,
    coreBins,
    taskBins,
    taskCoreBins,
    totalBins,
    avgLoad,
  }
}
