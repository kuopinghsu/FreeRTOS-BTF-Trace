/**
 * Per-task core affinity data for the affinity strip view.
 */

import { coreShortName } from './migrationAnalysis.js'
import { coreColor } from './colors.js'

/** Segments for mergeKey grouped by core, clipped to [tLo, tHi]. */
export function coreAffinityData(trace, mergeKey, tLo, tHi) {
  if (!trace || !mergeKey) return { cores: [], tLo, tHi, span: 0 }
  const segs = trace.segByMergeKey?.get(mergeKey) || []
  const byCore = new Map()
  for (const s of segs) {
    if (s.end <= tLo || s.start >= tHi) continue
    if (!byCore.has(s.core)) byCore.set(s.core, [])
    byCore.get(s.core).push({
      start: Math.max(s.start, tLo),
      end: Math.min(s.end, tHi),
      core: s.core,
    })
  }
  const cores = [...byCore.entries()]
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([core, segments]) => ({
      core,
      label: coreShortName(core),
      color: coreColor(core),
      segments: segments.sort((a, b) => a.start - b.start),
    }))
  const span = Math.max(tHi - tLo, 1)
  return { cores, tLo, tHi, span }
}
