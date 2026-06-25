/**
 * lod.js – Level-of-Detail helpers for timeline rendering.
 *
 * These mirror the Python _make_lod_summary() and _lod_reduce() functions
 * in btf_viewer.py.
 */
import { wasmLodSummaryIndices, wasmParseReady } from '../renderer/wasmAccel.js'

/** LOD bin counts (match Python / btfParser constants). */
export const LOD_SUMMARY_BINS = 4096
export const LOD_SUMMARY_BINS_ULTRA = 1024

/** Cache sorted segment start times as Float64Array (parse / LOD hot path). */
export function segmentStartsF64(segs) {
  if (!segs?.length) return new Float64Array(0)
  if (segs._startsF64?.length === segs.length) return segs._startsF64
  const arr = new Float64Array(segs.length)
  for (let i = 0; i < segs.length; i++) arr[i] = segs[i].start
  segs._startsF64 = arr
  return arr
}

/**
 * Down-sample a sorted segment array to at most `bins` representative entries.
 * When the trace has more segments than bins, consecutive segments that fall
 * in the same time bin are de-duplicated (keeping only the first of each bin).
 *
 * @param {Array}  segs     Sorted array of TaskSegment objects.
 * @param {number} bins     Target max output length.
 * @param {number} binSpan  Nanoseconds per bin (== timeSpan / bins).
 * @param {number} timeMin  Trace start timestamp (used to normalise bin index).
 * @returns {Array} Down-sampled segment array (may be same reference if already small).
 */
export function makeLodSummary(segs, bins, binSpan, timeMin) {
  if (segs.length <= bins) {
    const r = segs.slice()  // copy to prevent aliasing
    return [r, r.map(s => s.start)]
  }
  const safeBinSpan = binSpan > 0 ? binSpan : 1e-9

  if (wasmParseReady()) {
    const starts = segmentStartsF64(segs)
    const idx = wasmLodSummaryIndices(starts, safeBinSpan, timeMin, segs.length)
    if (idx?.length) {
      const result = new Array(idx.length)
      const outStarts = new Array(idx.length)
      for (let j = 0; j < idx.length; j++) {
        const i = idx[j]
        result[j] = segs[i]
        outStarts[j] = starts[i]
      }
      return [result, outStarts]
    }
  }

  const result = []
  const starts = []
  let prevBin = -2
  for (const s of segs) {
    const b = Math.floor((s.start - timeMin) / safeBinSpan)
    if (b !== prevBin) {
      result.push(s)
      starts.push(s.start)
      prevBin = b
    }
  }
  return [result, starts]
}

/**
 * WASM/JS LOD bin de-duplication on flat store indices (no segment object copies).
 * @param {import('../parser/segStore.js').SegStore} store
 * @param {Uint32Array} indices sorted segment indices into store
 * @returns {Uint32Array} reduced index list
 */
export function lodIndicesFromStore(store, indices, bins, binSpan, timeMin) {
  const n = indices.length
  if (n <= bins) {
    const copy = new Uint32Array(n)
    copy.set(indices)
    return copy
  }
  const starts = store.startsForIndices(indices)
  const safeBinSpan = binSpan > 0 ? binSpan : 1e-9

  if (wasmParseReady()) {
    const pick = wasmLodSummaryIndices(starts, safeBinSpan, timeMin, n)
    if (pick?.length) {
      const out = new Uint32Array(pick.length)
      for (let j = 0; j < pick.length; j++) out[j] = indices[pick[j]]
      return out
    }
  }

  const out = []
  let prevBin = -2
  for (let i = 0; i < n; i++) {
    const b = Math.floor((starts[i] - timeMin) / safeBinSpan)
    if (b !== prevBin) {
      out.push(indices[i])
      prevBin = b
    }
  }
  return Uint32Array.from(out)
}

/**
 * Merge sub-pixel-wide segments during paint to avoid overdraw.
 * Segments whose pixel-column start equals the previous segment's start
 * (i.e., would overwrite the same pixel column) are dropped, UNLESS the new
 * segment extends further to the right than the one already kept – in that
 * case the new segment replaces the previous entry.  This prevents a trivial
 * sub-pixel segment (e.g. 1 ns) from hiding a longer execution segment that
 * starts just after it in the same pixel column.
 *
 * @param {Array}  segs            Segments to draw (may be LOD or raw).
 * @param {number} timescalePerPx  Current nanoseconds per canvas pixel.
 * @param {number} timeMin         Trace start time (for origin offset).
 * @returns {Array} Reduced segment array (suitable for a single paint pass).
 */
export function lodReduce(segs, timescalePerPx, timeMin) {
  if (segs.length === 0) return segs
  const result = []
  let prevPx = -2
  let cur = null
  for (const s of segs) {
    const px = Math.floor((s.start - timeMin) / timescalePerPx)
    if (px !== prevPx) {
      if (cur) result.push(cur)
      cur = { ...s }
      prevPx = px
    } else {
      cur.start = Math.min(cur.start, s.start)
      cur.end = Math.max(cur.end, s.end)
    }
  }
  if (cur) result.push(cur)
  return result
}
