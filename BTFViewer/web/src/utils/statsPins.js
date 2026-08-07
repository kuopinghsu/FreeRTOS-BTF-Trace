/**
 * Statistics section pin helpers.
 * Keep section IDs in sync with btf_viewer_pkg/config.py STATS_PINNABLE_SECTIONS.
 */

export const STATS_PINNABLE_SECTIONS = Object.freeze([
  'cores',
  'core_breakdown',
  'tasks',
  'health',
  'migrations',
  'core_pairs',
  'exec',
  'block',
  'inter',
  'preemption',
  'priority',
  'sync',
  'queue',
  'lifecycle',
  'affinity',
  'deadline',
  'intervals',
  'tags',
])

/** @param {unknown} raw @returns {string[]} */
export function normalizeStatsPins(raw) {
  const allowed = new Set(STATS_PINNABLE_SECTIONS)
  const out = []
  const seen = new Set()
  let items = []
  if (raw == null) return out
  if (typeof raw === 'string') {
    items = raw.replace(/;/g, ',').split(',')
  } else if (Array.isArray(raw)) {
    items = raw
  } else {
    return out
  }
  for (const item of items) {
    const sid = String(item ?? '').trim()
    if (!sid || seen.has(sid) || !allowed.has(sid)) continue
    seen.add(sid)
    out.push(sid)
  }
  return out
}

/** @param {string[]} pins @param {string} sectionId @returns {string[]} */
export function toggleStatsPin(pins, sectionId) {
  const sid = String(sectionId || '').trim()
  if (!STATS_PINNABLE_SECTIONS.includes(sid)) {
    return normalizeStatsPins(pins)
  }
  const cur = normalizeStatsPins(pins)
  if (cur.includes(sid)) {
    return cur.filter((x) => x !== sid)
  }
  return [...cur, sid]
}
