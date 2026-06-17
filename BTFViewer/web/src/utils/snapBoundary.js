/**
 * Snap a timestamp to the nearest segment boundary within a pixel window.
 */

import { bisectLeft, bisectRight } from './bisect.js'

export function snapToBoundary(trace, ns, nsPerPx, windowPx = 8) {
  if (!trace || !nsPerPx || nsPerPx <= 0) return ns
  const window = Math.max(1, Math.floor(windowPx * nsPerPx))
  const nsLo = ns - window
  const nsHi = ns + window
  let bestNs = ns
  let bestDist = window + 1

  for (const [mk, segs] of trace.segByMergeKey || []) {
    const starts = []
    for (const s of segs) starts.push(s.start)
    if (!starts.length) continue
    starts.sort((a, b) => a - b)

    let i = bisectLeft(starts, nsLo)
    while (i < starts.length && starts[i] <= nsHi) {
      const dist = Math.abs(starts[i] - ns)
      if (dist < bestDist) {
        bestDist = dist
        bestNs = starts[i]
      }
      i++
    }

    const jHi = bisectRight(starts, nsHi)
    const jLo = Math.max(0, bisectLeft(starts, nsLo) - 32)
    for (let k = jLo; k < jHi && k < segs.length; k++) {
      const end = segs[k].end
      if (end >= nsLo && end <= nsHi) {
        const dist = Math.abs(end - ns)
        if (dist < bestDist) {
          bestDist = dist
          bestNs = end
        }
      }
    }
  }
  return bestNs
}

/** Collect sorted unique segment start times for boundary navigation. */
export function collectSegmentStarts(trace) {
  const set = new Set()
  for (const segs of trace.segByMergeKey?.values() || []) {
    for (const s of segs) set.add(s.start)
  }
  return [...set].sort((a, b) => a - b)
}
