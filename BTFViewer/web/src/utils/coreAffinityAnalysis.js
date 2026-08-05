/**
 * Core-affinity statistics from affinity_set STI events vs. execution slices.
 *
 * Mask changes are time-aware: each slice is checked against the mask in effect
 * at its start. Before the first affinity_set the task is unrestricted
 * (tskNO_AFFINITY) and does not contribute violations.
 */

import { taskDisplayName, taskMergeKey, taskReprGet } from './colors.js'

const AFFINITY_NOTE_RE = /^affinity_set\s+(.+?)\s+(0x[0-9a-fA-F]+|\d+)\s*$/i

/**
 * @param {Array<[number, number]>} history time-sorted [timestamp, mask]
 * @param {number} t
 * @returns {number|null}
 */
export function affinityMaskAtTime(history, t) {
  let active = null
  for (const [ts, mask] of history) {
    if (ts > t) break
    active = mask
  }
  return active
}

/**
 * @param {number} mask
 * @param {string[]} coreNames
 * @returns {Set<string>}
 */
export function coresAllowedByMask(mask, coreNames) {
  const allowed = new Set()
  for (const core of coreNames || []) {
    const idx = parseInt(String(core).split('_').at(-1), 10)
    if (!Number.isNaN(idx) && idx >= 0 && idx < 4096 && (mask & (1 << idx))) {
      allowed.add(core)
    }
  }
  return allowed
}

/**
 * @param {Array<[number, number]>} history
 * @returns {string}
 */
export function formatAffinityMaskHistory(history) {
  const parts = []
  for (const [, mask] of history) {
    const hx = `0x${mask.toString(16).toUpperCase()}`
    if (!parts.length || parts[parts.length - 1] !== hx) parts.push(hx)
  }
  return parts.join(' → ')
}

/**
 * @param {object} trace
 * @param {number|null} [lo]
 * @param {number|null} [hi]
 * @returns {{ mk: string, label: string, maskHex: string, observedCores: string, violations: string }[]}
 */
export function buildCoreAffinityRows(trace, lo = null, hi = null) {
  if (!trace?.stiEvents?.length) return []

  /** @type {Map<string, Array<[number, number]>>} */
  const histories = new Map()
  for (const ev of trace.stiEvents) {
    if (ev.target !== 'task') continue
    const m = AFFINITY_NOTE_RE.exec((ev.note ?? '').trim())
    if (!m) continue
    const taskLabel = m[1].trim()
    const raw = m[2]
    const mask = parseInt(raw, raw.startsWith('0x') || raw.startsWith('0X') ? 16 : 10)
    if (Number.isNaN(mask)) continue
    const mk = taskMergeKey(taskLabel)
    if (!histories.has(mk)) histories.set(mk, [])
    histories.get(mk).push([ev.time, mask])
  }
  if (!histories.size) return []

  for (const hist of histories.values()) {
    hist.sort((a, b) => a[0] - b[0])
  }

  const rows = []
  // Ordinal (codepoint) compare on the merge key, matching Python's default
  // `sorted(masks.items())` string ordering (not locale-aware).
  for (const [mk, history] of [...histories.entries()].sort((a, b) =>
    (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0))) {
    const label = taskDisplayName(taskReprGet(trace, mk) || mk)
    const obs = new Set()
    const violations = new Set()
    for (const seg of (trace.segByMergeKey?.get(mk) ?? [])) {
      if (lo != null && seg.end < lo) continue
      if (hi != null && seg.start > hi) continue
      obs.add(seg.core)
      const mask = affinityMaskAtTime(history, seg.start)
      if (mask == null) continue
      const allowed = coresAllowedByMask(mask, trace.coreNames)
      if (allowed.size > 0 && !allowed.has(seg.core)) violations.add(seg.core)
    }
    if (!obs.size) continue
    rows.push({
      mk,
      label,
      maskHex: formatAffinityMaskHistory(history),
      observedCores: [...obs].sort().join(', '),
      violations: violations.size > 0 ? [...violations].sort().join(', ') : '—',
    })
  }
  return rows
}
