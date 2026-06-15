/**
 * wasmAccel.js – WASM-backed hot paths for timeline pan/zoom.
 * Falls back to pure JS when WebAssembly is unavailable.
 */
import wasmB64 from './wasmBytes.js'
import { bisectLeft, bisectRight } from '../utils/bisect.js'

let _wasm = null
let _mem = null
let _i32 = null
let _f64 = null
let _scratch = 0          // i32 pair / index output
let _uploadBase = 4096    // uploaded trace arrays start here
let _uploadEnd = 4096

const SCRATCH_I32 = 0
const SCRATCH_INDICES = 256  // byte offset; room for 4k u32 indices (16 KiB)

function jsVisibleRowRange(rows, scrollY, bodyH, buffer, rowBandHeightFn) {
  if (!rows?.length) return { i0: 0, i1: 0 }
  const visTop = scrollY
  const visBot = scrollY + bodyH
  let i0 = 0
  while (i0 < rows.length && rows[i0].y + rowBandHeightFn(rows[i0]) <= visTop) i0++
  i0 = Math.max(0, i0 - buffer)
  let i1 = i0
  while (i1 < rows.length && rows[i1].y <= visBot) i1++
  i1 = Math.min(rows.length, i1 + buffer)
  return { i0, i1 }
}

function jsVisibleSegRange(starts, nsLo, nsHi) {
  if (!starts?.length) return { from: 0, to: -1 }
  const lo = bisectLeft(starts, nsLo)
  const hi = bisectRight(starts, nsHi)
  const from = Math.max(0, lo - 1)
  return { from, to: hi }
}

/**
 * Merge visible segments to one index per pixel column, then cap to maxOut.
 * Scans the full viewport (no left-to-right truncation) so zoomed-out rows
 * still show activity across the entire trace width.
 */
function jsLodReduceIndices(starts, ends, from, to, timeStart, timeEnd, nsPerPx, maxOut) {
  const count = to - from + 1
  if (count <= maxOut) {
    const out = new Array(count)
    for (let i = from, j = 0; i <= to; i++, j++) out[j] = i
    return out
  }

  const span = Math.max(timeEnd - timeStart, 1)
  const collect = (tpp) => {
    const cols = []
    let prevPx = -2
    let last = 0
    for (let i = from; i <= to; i++) {
      const px = starts[i] < timeStart ? 0 : Math.floor((starts[i] - timeStart) / tpp)
      if (px !== prevPx) {
        cols.push(i)
        prevPx = px
        last = cols.length - 1
      } else if (ends[i] > ends[cols[last]]) {
        cols[last] = i
      }
    }
    return cols
  }

  const subsample = (cols) => {
    const out = []
    const step = cols.length / maxOut
    for (let j = 0; j < maxOut; j++) {
      out.push(cols[Math.min(cols.length - 1, Math.floor(j * step))])
    }
    return out
  }

  // Very large rows: one coarse pass across the full viewport (fast).
  if (count > maxOut * 8) {
    const cols = collect(Math.max(nsPerPx, span / maxOut))
    return cols.length <= maxOut ? cols : subsample(cols)
  }

  // Moderate rows: fine pixel columns + even subsample (preserves coverage).
  const fine = collect(nsPerPx)
  if (fine.length <= maxOut) return fine
  return subsample(fine)
}

function ensureMem(bytes) {
  if (!_mem) return
  const need = _uploadEnd + bytes
  if (need <= _mem.buffer.byteLength) return
  const pages = Math.ceil(need / 65536)
  _mem.grow(pages - Math.floor(_mem.buffer.byteLength / 65536))
  _i32 = new Int32Array(_mem.buffer)
  _f64 = new Float64Array(_mem.buffer)
}

function startsArray(segs) {
  if (!segs?.length) return new Float64Array(0)
  if (segs._startsF64?.length === segs.length) return segs._startsF64
  if (segs._indices && segs._store) {
    const arr = segs._store.startsForIndices(segs._indices)
    segs._startsF64 = arr
    return arr
  }
  const starts = new Float64Array(segs.length)
  for (let i = 0; i < segs.length; i++) starts[i] = segs[i].start
  segs._startsF64 = starts
  return starts
}

function endsArray(segs) {
  if (!segs?.length) return new Float64Array(0)
  if (segs._endsF64?.length === segs.length) return segs._endsF64
  if (segs._indices && segs._store) {
    const n = segs._indices.length
    const arr = new Float64Array(n)
    const ends = segs._store.ends
    const indices = segs._indices
    for (let i = 0; i < n; i++) arr[i] = ends[indices[i]]
    segs._endsF64 = arr
    return arr
  }
  const ends = new Float64Array(segs.length)
  for (let i = 0; i < segs.length; i++) ends[i] = segs[i].end
  segs._endsF64 = ends
  return ends
}

function uploadF64(arr) {
  if (!_mem || !arr?.length) return { ptr: 0, len: 0 }
  const len = arr.length
  const bytes = len * 8
  ensureMem(bytes + 8)
  const ptr = _uploadEnd
  new Float64Array(_mem.buffer, ptr, len).set(arr)
  _uploadEnd = ptr + bytes
  return { ptr, len }
}

function uploadLodTier(segs) {
  if (!segs?.length) return { starts: { ptr: 0, len: 0 }, ends: { ptr: 0, len: 0 } }
  return {
    starts: uploadF64(startsArray(segs)),
    ends: uploadF64(endsArray(segs)),
  }
}

/** Upload LOD arrays once per trace for zero-copy WASM bisect/reduce. */
export function registerTraceWasmAccel(trace) {
  if (!_wasm || !trace) return
  _uploadEnd = _uploadBase
  const task = new Map()
  for (const mk of trace.tasks || []) {
    task.set(mk, {
      raw: uploadLodTier(trace.segByMergeKey?.get(mk) || []),
      lod: uploadLodTier(trace.segLodByMergeKey?.get(mk) || []),
      ultra: uploadLodTier(trace.segLodUltraByMergeKey?.get(mk) || []),
    })
  }
  const core = new Map()
  for (const c of trace.coreNames || []) {
    core.set(c, {
      raw: uploadLodTier(trace.coreSegs?.get(c) || []),
      lod: uploadLodTier(trace.coreSegLod?.get(c) || []),
      ultra: uploadLodTier(trace.coreSegLodUltra?.get(c) || []),
    })
  }
  const coreTask = new Map()
  for (const c of trace.coreNames || []) {
    const order = trace.coreTaskOrder?.get(c) || []
    for (const raw of order) {
      const lod = trace.coreTaskSegLod?.get(c)?.get(raw) || []
      const ultra = trace.coreTaskSegLodUltra?.get(c)?.get(raw) || []
      if (!lod.length && !ultra.length) continue
      coreTask.set(`${c}__${raw}`, {
        // Raw tier omitted — zoomed-in per-core rows are small; JS bisect is fast.
        raw: uploadLodTier(lod),
        lod: uploadLodTier(lod),
        ultra: uploadLodTier(ultra.length ? ultra : lod),
      })
    }
  }
  trace._wasmAccel = { task, core, coreTask }
}

export function unregisterTraceWasmAccel(trace) {
  if (trace) delete trace._wasmAccel
}

export function wasmAccelReady() {
  return !!_wasm
}

export async function initWasmAccel() {
  if (_wasm !== null) return !!_wasm
  if (typeof WebAssembly === 'undefined') {
    _wasm = false
    return false
  }
  try {
    const bytes = Uint8Array.from(atob(wasmB64), c => c.charCodeAt(0))
    const { instance } = await WebAssembly.instantiate(bytes, {})
    _wasm = instance.exports
    _mem = _wasm.memory
    _i32 = new Int32Array(_mem.buffer)
    _f64 = new Float64Array(_mem.buffer)
    _scratch = SCRATCH_I32
    return true
  } catch (err) {
    console.warn('WASM timeline accel unavailable, using JS fallback:', err)
    _wasm = false
    return false
  }
}

/** Pack row y/heights for WASM row cull (small; copied per layout change). */
export function packRowLayoutWasm(rows, rowBandHeightFn) {
  const n = rows?.length || 0
  const ys = new Float64Array(n)
  const hs = new Float64Array(n)
  for (let i = 0; i < n; i++) {
    ys[i] = rows[i].y
    hs[i] = rowBandHeightFn(rows[i])
  }
  let ptr = 0
  if (_wasm && _mem && n > 0) {
    const bytes = n * 8 * 2
    ensureMem(bytes)
    ptr = _uploadEnd
    new Float64Array(_mem.buffer, ptr, n).set(ys)
    new Float64Array(_mem.buffer, ptr + n * 8, n).set(hs)
  }
  return { ys, hs, ptr, len: n }
}

export function accelVisibleRowRange(rows, scrollY, bodyH, buffer, rowBandHeightFn, packed) {
  if (!_wasm || !packed?.ptr || !packed.len) {
    return jsVisibleRowRange(rows, scrollY, bodyH, buffer, rowBandHeightFn)
  }
  _wasm.visible_row_range(
    packed.ptr,
    packed.ptr + packed.len * 8,
    packed.len,
    scrollY,
    bodyH,
    buffer,
    _scratch,
  )
  return { i0: _i32[_scratch >> 2], i1: _i32[(_scratch >> 2) + 1] }
}

function pickWasmTier(handles, nsPerPx, lodTpp, ultraTpp) {
  if (!handles) return null
  if (nsPerPx >= ultraTpp) return handles.ultra
  if (nsPerPx >= lodTpp) return handles.lod
  return handles.raw
}

function pickLodSegs(lodData, nsPerPx, lodTpp, ultraTpp) {
  if (nsPerPx >= ultraTpp) return lodData.ultraSegs || lodData.segs
  if (nsPerPx >= lodTpp) return lodData.lodSegs || lodData.segs
  return lodData.segs
}

function pickLodStarts(lodData, nsPerPx, lodTpp, ultraTpp) {
  if (nsPerPx >= ultraTpp) return lodData.ultraStarts || lodData.starts
  if (nsPerPx >= lodTpp) return lodData.lodStarts || lodData.starts
  return lodData.starts
}

export function accelVisibleSegIndices(wasmHandles, lodData, timeStart, timeEnd, nsPerPx, lodTpp, ultraTpp) {
  const tier = pickWasmTier(wasmHandles, nsPerPx, lodTpp, ultraTpp)
  const segs = pickLodSegs(lodData, nsPerPx, lodTpp, ultraTpp)
  if (!segs?.length) return { segs, indices: [] }

  // WASM arrays must match the LOD tier being painted (core-task rows ≠ global task LOD).
  if (_wasm && tier?.starts?.len && tier.starts.len === segs.length) {
    _wasm.visible_seg_range(tier.starts.ptr, tier.starts.len, timeStart, timeEnd, _scratch)
    let from = _i32[_scratch >> 2]
    let to = _i32[(_scratch >> 2) + 1]
    if (from >= segs.length) from = segs.length - 1
    if (to >= segs.length) to = segs.length - 1
    return { segs, from, to, tier }
  }

  const starts = pickLodStarts(lodData, nsPerPx, lodTpp, ultraTpp)
  let { from, to } = jsVisibleSegRange(starts, timeStart, timeEnd)
  if (from >= segs.length) from = segs.length - 1
  if (to >= segs.length) to = segs.length - 1
  return { segs, from, to, tier: null }
}

export function accelLodReduceIndices(segQuery, timeStart, timeEnd, nsPerPx, maxOut, forceCoarse) {
  const { segs, from, to } = segQuery
  if (!segs?.length || from > to) return []

  if (!forceCoarse && to - from + 1 <= maxOut) {
    const indices = new Array(to - from + 1)
    for (let i = from, j = 0; i <= to; i++, j++) indices[j] = i
    return indices
  }

  const starts = segs._startsF64 || startsArray(segs)
  const ends = segs._endsF64 || endsArray(segs)
  return jsLodReduceIndices(starts, ends, from, to, timeStart, timeEnd, nsPerPx, maxOut)
}

export function getWasmHandles(trace, kind, key) {
  if (!trace?._wasmAccel) return null
  if (kind === 'task') return trace._wasmAccel.task.get(key) || null
  if (kind === 'core') return trace._wasmAccel.core.get(key) || null
  if (kind === 'core-task') return trace._wasmAccel.coreTask?.get(key) || null
  return null
}
