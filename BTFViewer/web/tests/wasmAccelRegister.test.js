import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import { finalizeTraceStorage } from '../src/parser/segStore.js'
import {
  initWasmAccel,
  registerTraceWasmAccel,
  getWasmHandles,
  accelVisibleSegIndices,
  wasmPeekF64,
} from '../src/renderer/wasmAccel.js'
import { bisectLeft, bisectRight } from '../src/utils/bisect.js'

function buildTrace() {
  const segments = []
  const tasks = []
  const taskRepr = new Map()
  const segByMergeKey = new Map()
  const timeMin = 1_000_000
  const timeMax = 5_000_000
  const span = timeMax - timeMin

  const addTask = (id, n) => {
    const raw = `[0/${id}]T${id}`
    const mk = `\x00${id}\x00T${id}`
    tasks.push(mk)
    taskRepr.set(mk, raw)
    const segs = []
    for (let i = 0; i < n; i++) {
      const start = timeMin + Math.floor(i * span / n)
      const seg = { task: raw, core: 'Core_0', start, end: start + 40 }
      segs.push(seg)
      segments.push(seg)
    }
    segByMergeKey.set(mk, segs)
  }

  // Enough small tasks that timeline uploads pass PARSE_UPLOAD_BASE (64 KiB)
  // before a ≥4096-seg gather, reproducing the old scratch overlap.
  for (let id = 1; id <= 8; id++) addTask(id, 220)
  addTask(9, 4500)
  addTask(10, 300)

  const empty = new Map()
  const coreSegs = new Map([['Core_0', segments.slice()]])
  return finalizeTraceStorage({
    timeMin,
    timeMax,
    timeScale: 'us',
    tasks,
    taskRepr,
    segments,
    coreNames: ['Core_0'],
    coreSegs,
    coreTaskOrder: new Map([['Core_0', []]]),
    coreTaskSegs: new Map([['Core_0', new Map()]]),
    segByMergeKey,
    segLodByMergeKey: new Map(segByMergeKey),
    segLodUltraByMergeKey: new Map(segByMergeKey),
    coreSegLod: new Map(coreSegs),
    coreSegLodUltra: new Map(coreSegs),
    lodTimescalePerPx: span / 4096,
    lodUltraTimescalePerPx: span / 1024,
    stiChannels: [],
  })
}

describe('registerTraceWasmAccel', () => {
  it('keeps per-task start arrays intact after a large gather upload', async () => {
    assert.equal(await initWasmAccel(), true)
    const trace = buildTrace()
    registerTraceWasmAccel(trace)

    const mk = trace.tasks[0]
    const starts = trace.segStartByMergeKey.get(mk)
    const handles = getWasmHandles(trace, 'task', mk)
    assert.ok(handles?.raw?.starts?.len === starts.length)
    assert.deepEqual(wasmPeekF64(handles.raw.starts.ptr, 4), [...starts.slice(0, 4)])
    assert.deepEqual(
      wasmPeekF64(handles.raw.starts.ptr + (starts.length - 2) * 8, 2),
      [starts[starts.length - 2], starts[starts.length - 1]],
    )

    const lo = 1_800_000
    const hi = 3_200_000
    const ld = {
      segs: trace.segByMergeKey.get(mk),
      starts,
      lodSegs: trace.segLodByMergeKey.get(mk),
      lodStarts: trace.segLodStartsByMergeKey.get(mk),
      ultraSegs: trace.segLodUltraByMergeKey.get(mk),
      ultraStarts: trace.segLodUltraStartsByMergeKey.get(mk),
    }
    const q = accelVisibleSegIndices(handles, ld, lo, hi, 0, Infinity, Infinity)
    const jsFrom = Math.max(0, bisectLeft(starts, lo) - 1)
    const jsTo = bisectRight(starts, hi) - 1
    assert.equal(q.from, jsFrom)
    assert.equal(q.to, jsTo)
    assert.ok(q.to - q.from + 1 > 10)
  })
})
