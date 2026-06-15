/**
 * Statistics table computation on flat segment storage (worker + main-thread fallback).
 */
import { parseTaskName, isIdleTaskName, taskDisplayName } from '../utils/colors.js'
import { segFullyInRange } from '../utils/statsRange.js'

function summarizeNumeric(samples) {
  if (!samples?.length) return null
  const values = samples.slice().sort((a, b) => a - b)
  const n = values.length
  const sum = values.reduce((a, b) => a + b, 0)
  const p50Idx = Math.min(n - 1, Math.floor(n * 0.5))
  const p95Idx = Math.min(n - 1, Math.floor(n * 0.95))
  return {
    min: values[0],
    avg: Math.round(sum / n),
    max: values[n - 1],
    p50: values[p50Idx],
    p95: values[p95Idx],
  }
}

function blockingSamples(store, indices, lo, hi) {
  if (indices.length < 2) return []
  const { starts } = store
  const order = indices.slice().sort((a, b) => starts[a] - starts[b])
  const samples = []
  for (let i = 1; i < order.length; i++) {
    const prev = store.getSeg(order[i - 1])
    const nxt = store.getSeg(order[i])
    if (lo != null && hi != null) {
      if (!segFullyInRange(prev, lo, hi) || !segFullyInRange(nxt, lo, hi)) continue
    }
    const gap = nxt.start - prev.end
    if (gap > 0) samples.push(gap)
  }
  return samples
}

function interArrivalSamples(store, indices, lo, hi) {
  if (indices.length < 2) return []
  const { starts } = store
  const order = indices.slice().sort((a, b) => starts[a] - starts[b])
  const samples = []
  for (let i = 1; i < order.length; i++) {
    const t = starts[order[i]]
    if (lo != null && hi != null && (t < lo || t > hi)) continue
    const d = t - starts[order[i - 1]]
    if (d > 0) samples.push(d)
  }
  return samples
}

function execSamples(store, indices, lo, hi) {
  const samples = []
  const { starts, ends } = store
  for (let i = 0; i < indices.length; i++) {
    const si = indices[i]
    const d = ends[si] - starts[si]
    if (d <= 0) continue
    if (lo != null && hi != null) {
      const s = store.getSeg(si)
      if (!segFullyInRange(s, lo, hi)) continue
    }
    samples.push(d)
  }
  return samples
}

function countRuns(store, indices, lo, hi) {
  if (lo == null || hi == null) return indices.length
  const { starts } = store
  let n = 0
  for (let i = 0; i < indices.length; i++) {
    const t = starts[indices[i]]
    if (t >= lo && t <= hi) n++
  }
  return n
}

/**
 * @param {import('./segStore.js').SegStore} store
 * @param {object} opts
 * @returns {{ exec: object[], block: object[], inter: object[], taskCpuNs: [string, number][] }}
 */
export function computeStatsTables(store, {
  tasks,
  taskRepr,
  segIndicesByMk,
  lo,
  hi,
  totalNs,
}) {
  const exec = []
  const block = []
  const inter = []
  const taskCpuNs = []

  for (const mk of tasks) {
    const indices = segIndicesByMk.get(mk)
    if (!indices?.length) continue
    const repr = taskRepr.get(mk) || mk
    const { name } = parseTaskName(repr)
    if (isIdleTaskName(name) || name === 'TICK') continue

    let cpuNs = 0
    const { starts, ends } = store
    for (let i = 0; i < indices.length; i++) {
      const si = indices[i]
      if (lo != null && hi != null) {
        if (ends[si] <= lo || starts[si] >= hi) continue
        cpuNs += Math.min(ends[si], hi) - Math.max(starts[si], lo)
      } else {
        cpuNs += ends[si] - starts[si]
      }
    }
    if (cpuNs > 0) taskCpuNs.push([mk, cpuNs])

    const disp = taskDisplayName(repr)

    const execS = execSamples(store, indices, lo, hi)
    const execSum = summarizeNumeric(execS)
    if (execSum) {
      exec.push({
        mk,
        name: disp,
        runs: execS.length,
        cpuPct: totalNs > 0 ? (100 * execS.reduce((a, b) => a + b, 0) / totalNs) : 0,
        ...execSum,
      })
    }

    const blockS = blockingSamples(store, indices, lo, hi)
    const blockSum = summarizeNumeric(blockS)
    if (blockSum) {
      block.push({
        mk,
        name: disp,
        gaps: blockS.length,
        ...blockSum,
      })
    }

    const interS = interArrivalSamples(store, indices, lo, hi)
    const interSum = summarizeNumeric(interS)
    if (interSum) {
      inter.push({
        mk,
        name: disp,
        runs: countRuns(store, indices, lo, hi),
        ...interSum,
      })
    }
  }

  const byName = (a, b) => a.name.localeCompare(b.name)
  exec.sort((a, b) => b.runs - a.runs || byName(a, b))
  block.sort((a, b) => b.gaps - a.gaps || byName(a, b))
  inter.sort((a, b) => b.runs - a.runs || byName(a, b))
  taskCpuNs.sort((a, b) => b[1] - a[1])

  return { exec, block, inter, taskCpuNs }
}

/** Full-trace per-task CPU ns (for top-tasks without scanning on panel open). */
export function computeTaskCpuNs(store, tasks, taskRepr, segIndicesByMk) {
  const out = []
  const { starts, ends } = store
  for (const mk of tasks) {
    const indices = segIndicesByMk.get(mk)
    if (!indices?.length) continue
    const repr = taskRepr.get(mk) || mk
    const { name } = parseTaskName(repr)
    if (isIdleTaskName(name) || name === 'TICK') continue
    let t = 0
    for (let i = 0; i < indices.length; i++) {
      const si = indices[i]
      t += ends[si] - starts[si]
    }
    if (t > 0) out.push([mk, t])
  }
  out.sort((a, b) => b[1] - a[1])
  return out
}

export function segIndicesMapFromTrace(trace) {
  const out = new Map()
  for (const mk of trace.tasks || []) {
    const list = trace.segByMergeKey?.get(mk)
    if (list?._indices) out.set(mk, list._indices)
  }
  return out
}
