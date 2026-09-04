/**
 * Timeline incident markers (anomalies + findings). Lockstep idea with
 * Desktop finding overlay; Web merges UX anomaly starts when enabled.
 */

/** @param {object[]} uxEvents harvestUxEvents() rows
 *  @param {number[]} findingTimes findingOverlayTimes()
 *  @param {{ includeAnomalies?: boolean, limit?: number }} [opts]
 *  @returns {number[]} */
export function mergeIncidentOverlayTimes(uxEvents, findingTimes, opts = {}) {
  const limit = Math.max(1, Number(opts.limit) || 120)
  const out = []
  const seen = new Set()
  for (const t of findingTimes || []) {
    const n = Number(t)
    if (!Number.isFinite(n) || seen.has(n)) continue
    seen.add(n)
    out.push(n)
    if (out.length >= limit) return out
  }
  if (opts.includeAnomalies === false) return out
  for (const ev of uxEvents || []) {
    if (!ev || typeof ev !== 'object') continue
    const t = Number(ev.jump_ns ?? ev.start ?? ev.time)
    if (!Number.isFinite(t) || seen.has(t)) continue
    seen.add(t)
    out.push(t)
    if (out.length >= limit) break
  }
  return out
}
