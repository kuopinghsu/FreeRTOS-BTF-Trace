/**
 * Statistics section pin helpers and default display order.
 * Keep section IDs in sync with btf_viewer_pkg/config.py STATS_PINNABLE_SECTIONS.
 */

import { STATS_DEFAULT_EXPANDED_SECTIONS } from '../config.js'

// Triage sections (Step-1 item 6): visually distinguished in the section
// header from Overview/Timing/SMP/Sync "detailed analysis" sections. Keep in
// sync with btf_viewer_pkg/config.py STATS_TRIAGE_SECTIONS.
export const STATS_TRIAGE_SECTIONS = Object.freeze([
  'anomalies',
  'worst',
  'patterns',
  'response',
  'task_health',
])

// Triage-first default order (Step-1 item 6): surface "what deserves
// attention" before detailed/overview metrics, then Timing, then
// SMP/Scheduling, then Synchronization/Detail.
export const STATS_PINNABLE_SECTIONS = Object.freeze([
  // Triage
  'anomalies',
  'worst',
  'patterns',
  'response',
  'task_health',
  // Overview
  'cores',
  'core_breakdown',
  'concurrency',
  'switch_overhead',
  'tasks',
  'health',
  // Timing Investigation
  'exec',
  'block',
  'dispatch',
  'crit_path',
  'inter',
  'period',
  'jitter',
  'distrib',
  // SMP / Scheduling
  'task_core',
  'core_time',
  'migrations',
  'core_pairs',
  'affinity',
  'preempt_matrix',
  'preemption',
  'priority',
  // Synchronization / Detail
  'sync',
  'wait_owner',
  'mutex_block',
  'queue',
  'intervals',
  'tags',
  'lifecycle',
  'deadline',
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

/**
 * Full statistics section order: preferred IDs first, then catalogue defaults.
 * @param {unknown} raw
 * @returns {string[]}
 */
export function normalizeStatsSectionOrder(raw) {
  const preferred = normalizeStatsPins(raw)
  const seen = new Set(preferred)
  const out = [...preferred]
  for (const sid of STATS_PINNABLE_SECTIONS) {
    if (!seen.has(sid)) out.push(sid)
  }
  return out
}

/**
 * Move src to the position of dst (insert before dst).
 * @param {unknown} order
 * @param {string} src
 * @param {string} dst
 * @returns {string[]}
 */
export function moveStatsSection(order, src, dst) {
  const cur = normalizeStatsSectionOrder(order)
  const srcS = String(src || '').trim()
  const dstS = String(dst || '').trim()
  if (!srcS || !dstS || srcS === dstS || !cur.includes(srcS) || !cur.includes(dstS)) {
    return cur
  }
  const next = cur.filter((x) => x !== srcS)
  next.splice(next.indexOf(dstS), 0, srcS)
  return next
}

/** @returns {string[]} */
export function defaultStatsSectionOrder() {
  return [...STATS_PINNABLE_SECTIONS]
}

/** @param {unknown} order @returns {boolean} */
export function isDefaultStatsSectionOrder(order) {
  const cur = normalizeStatsSectionOrder(order)
  const def = defaultStatsSectionOrder()
  if (cur.length !== def.length) return false
  return cur.every((sid, i) => sid === def[i])
}

/** @returns {Record<string, boolean>} */
export function defaultSectionCollapsed() {
  const out = {}
  for (const id of STATS_PINNABLE_SECTIONS) {
    out[id] = !STATS_DEFAULT_EXPANDED_SECTIONS.includes(id)
  }
  return out
}

/** @param {unknown} src @returns {Record<string, boolean>} */
export function mergeSectionCollapsed(src) {
  const out = defaultSectionCollapsed()
  if (!src || typeof src !== 'object' || Array.isArray(src)) return out
  for (const [key, val] of Object.entries(src)) {
    if (Object.prototype.hasOwnProperty.call(out, key) && typeof val === 'boolean') {
      out[key] = val
    }
  }
  return out
}
