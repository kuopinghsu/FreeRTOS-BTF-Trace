/**
 * lod.js – Level-of-Detail helpers for timeline rendering.
 *
 * These mirror the Python _make_lod_summary() and _lod_reduce() functions
 * in btf_viewer.py.
 */

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
  if (segs.length <= bins) return segs  // already small – skip work
  const result = []
  let prevBin = -2
  for (const s of segs) {
    const b = Math.floor((s.start - timeMin) / binSpan)
    if (b !== prevBin) {
      result.push(s)
      prevBin = b
    }
  }
  return result
}

/**
 * Merge sub-pixel-wide segments during paint to avoid overdraw.
 * Segments whose pixel-column start equals the previous segment's start
 * (i.e., would overwrite the same pixel column) are dropped.
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
  for (const s of segs) {
    const px = Math.floor((s.start - timeMin) / timescalePerPx)
    if (px !== prevPx) {
      result.push(s)
      prevPx = px
    }
  }
  return result
}
