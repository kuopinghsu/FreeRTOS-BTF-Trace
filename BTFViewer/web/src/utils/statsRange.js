/**
 * Cursor-scoped statistics helpers (parity with desktop btf_viewer.py).
 */

/** @returns {number[]} Non-null cursor timestamps. */
export function getPlacedCursors(cursors) {
  return (cursors || []).filter(c => c !== null)
}

/** Nanoseconds of segment inside [lo, hi). */
export function segOverlapNs(seg, lo, hi) {
  if (seg.end <= lo || seg.start >= hi) return 0
  return Math.min(seg.end, hi) - Math.max(seg.start, lo)
}

/** Segment starts and ends inside [lo, hi] (inclusive). */
export function segFullyInRange(seg, lo, hi) {
  return seg.start >= lo && seg.end <= hi
}

export function segOverlapsRange(seg, lo, hi) {
  return seg.end > lo && seg.start < hi
}

/**
 * Active cursor range for statistics when scope is enabled.
 * @returns {{ lo: number, hi: number, nCursors: number } | null}
 */
export function getStatsRange(cursors, scopeEnabled) {
  if (!scopeEnabled) return null
  const placed = getPlacedCursors(cursors)
  if (placed.length < 2) return null
  const sorted = [...placed].sort((a, b) => a - b)
  const lo = sorted[0]
  const hi = sorted[sorted.length - 1]
  if (hi <= lo) return null
  return { lo, hi, nCursors: placed.length }
}

/** Section/plot title append — empty when ranged; C1–Cn is shown via badge/chip. */
export function scopeSuffix(_range) {
  return ''
}

/** Map lookup — parser uses Map; some paths may yield plain objects. */
export function traceMapGet(mapLike, key) {
  if (!mapLike) return undefined
  if (typeof mapLike.get === 'function') return mapLike.get(key)
  return mapLike[key]
}

/** Iterate Map or plain-object entries without spread. */
export function* traceMapEntries(mapLike) {
  if (!mapLike) return
  if (typeof mapLike.entries === 'function') {
    yield* mapLike.entries()
    return
  }
  for (const key of Object.keys(mapLike)) {
    yield [key, mapLike[key]]
  }
}

/** Banner text for metrics plot dialogs. */
export function plotScopeBanner(range, timeScale, formatTimeFn) {
  if (range) {
    return {
      scoped: true,
      badge: 'Cursor range',
      detail: `C1–C${range.nCursors}: ${formatTimeFn(range.lo, timeScale)} … ${formatTimeFn(range.hi, timeScale)} (${formatTimeFn(range.hi - range.lo, timeScale)})`,
    }
  }
  return {
    scoped: false,
    badge: 'Full trace',
    detail: 'Not limited to cursors — all slices in the loaded trace',
  }
}
