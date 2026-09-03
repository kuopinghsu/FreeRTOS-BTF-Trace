/**
 * Statistics section pin helpers, categories, and default display order.
 * Keep section IDs in sync with btf_viewer_pkg/config.py STATS_PINNABLE_SECTIONS.
 */

import { STATS_DEFAULT_EXPANDED_SECTIONS } from '../config.js'

/** Investigation categories (Step 1.1). Category is a property of the section. */
export const STATS_SECTION_CATEGORIES = Object.freeze([
  'OVERVIEW', 'TRIAGE', 'TIMING', 'SCHED', 'SYNC', 'DETAIL',
])

/**
 * Section id → category label (exactly one primary category each).
 * Keep lockstep with btf_viewer_pkg/config.py STATS_SECTION_CATEGORY.
 */
export const STATS_SECTION_CATEGORY = Object.freeze({
  cores: 'OVERVIEW',
  health: 'OVERVIEW',
  task_health: 'OVERVIEW',
  anomalies: 'TRIAGE',
  worst: 'TRIAGE',
  patterns: 'TRIAGE',
  response: 'TIMING',
  exec: 'TIMING',
  dispatch: 'TIMING',
  block: 'TIMING',
  crit_path: 'TIMING',
  period: 'TIMING',
  jitter: 'TIMING',
  inter: 'TIMING',
  activation: 'TIMING',
  ready_gap: 'TIMING',
  task_core: 'SCHED',
  core_time: 'SCHED',
  migrations: 'SCHED',
  core_pairs: 'SCHED',
  affinity: 'SCHED',
  preempt_matrix: 'SCHED',
  preemption: 'SCHED',
  priority: 'SCHED',
  concurrency: 'SCHED',
  switch_reason: 'SCHED',
  sched_load: 'SCHED',
  mutex_block: 'SYNC',
  wait_owner: 'SYNC',
  sync: 'SYNC',
  queue: 'SYNC',
  sync_level: 'SYNC',
  core_breakdown: 'DETAIL',
  idle: 'DETAIL',
  switch_overhead: 'DETAIL',
  tasks: 'DETAIL',
  distrib: 'DETAIL',
  intervals: 'DETAIL',
  tags: 'DETAIL',
  lifecycle: 'DETAIL',
  deadline: 'DETAIL',
})

/** Backward-compatible alias: TRIAGE category members. */
export const STATS_TRIAGE_SECTIONS = Object.freeze(
  Object.entries(STATS_SECTION_CATEGORY)
    .filter(([, cat]) => cat === 'TRIAGE')
    .map(([sid]) => sid),
)

/**
 * Low-saturation category badge colours (Step 1.1-color).
 * Values are { light|dark: { bg, fg, border } }. Text remains the primary
 * identifier; colour is a secondary cue. Keep lockstep with
 * btf_viewer_pkg/config.py STATS_CATEGORY_BADGE_COLORS and App.vue CSS vars.
 */
export const STATS_CATEGORY_BADGE_COLORS = Object.freeze({
  OVERVIEW: {
    light: { bg: '#E8EDF2', fg: '#536475', border: '#B8C4CF' },
    dark:  { bg: '#26313B', fg: '#C3CED8', border: '#4A5966' },
  },
  TRIAGE: {
    light: { bg: '#F7EDD7', fg: '#8A641F', border: '#DFC68E' },
    dark:  { bg: '#3A3020', fg: '#E2C27C', border: '#675630' },
  },
  TIMING: {
    light: { bg: '#E3EDF9', fg: '#426A9E', border: '#AFC7E5' },
    dark:  { bg: '#243449', fg: '#A9C5E8', border: '#47658A' },
  },
  SCHED: {
    light: { bg: '#ECE8F7', fg: '#665A98', border: '#C5BCE0' },
    dark:  { bg: '#302C44', fg: '#C1B7E3', border: '#5D557B' },
  },
  SYNC: {
    light: { bg: '#E2F1EF', fg: '#39746F', border: '#ADD2CD' },
    dark:  { bg: '#203A38', fg: '#9DD0CA', border: '#426C68' },
  },
  DETAIL: {
    light: { bg: '#ECEDEF', fg: '#656B72', border: '#C8CBD0' },
    dark:  { bg: '#303337', fg: '#C0C4C9', border: '#565B61' },
  },
})

/** @param {string} category @param {boolean} [dark=true]
 *  @returns {{ bg: string, fg: string, border: string }} */
export function statsCategoryBadgeColors(category, dark = true) {
  const key = dark ? 'dark' : 'light'
  const palette = STATS_CATEGORY_BADGE_COLORS[String(category || '').trim().toUpperCase()]
  return palette ? palette[key] : STATS_CATEGORY_BADGE_COLORS.DETAIL[key]
}

/**
 * OVERVIEW → TRIAGE → TIMING → SCHED → SYNC → DETAIL (Step 1.1).
 * Category badges stay with the section after user reordering.
 */
export const STATS_PINNABLE_SECTIONS = Object.freeze([
  // OVERVIEW — is the system generally healthy?
  'cores',
  'health',
  'task_health',
  // TRIAGE — what deserves attention?
  'anomalies',
  'worst',
  'patterns',
  // TIMING — what timing behavior explains it?
  'response',
  'exec',
  'dispatch',
  'block',
  'crit_path',
  'period',
  'jitter',
  'inter',
  'activation',
  'ready_gap',
  // SCHED — scheduling / CPU / SMP
  'task_core',
  'core_time',
  'migrations',
  'core_pairs',
  'affinity',
  'preempt_matrix',
  'preemption',
  'priority',
  'concurrency',
  'switch_reason',
  'sched_load',
  // SYNC — blocking and synchronization
  'mutex_block',
  'wait_owner',
  'sync',
  'queue',
  'sync_level',
  // DETAIL — supporting / lower-level measurements
  'core_breakdown',
  'idle',
  'switch_overhead',
  'tasks',
  'distrib',
  'intervals',
  'tags',
  'lifecycle',
  'deadline',
])

/** Per-core util above this counts as meaningful SMP-active activity. */
export const STATS_SMP_ACTIVE_MIN_UTIL_PCT = 0.01

/**
 * True when meaningful non-IDLE/TICK work is observed on more than one core.
 * Uses cached ``trace.coreUtilPct`` when present. Presentation only.
 * @param {object|null|undefined} trace
 * @param {number} [minUtilPct]
 * @returns {boolean}
 */
export function statsTraceIsSmpActive(trace, minUtilPct = STATS_SMP_ACTIVE_MIN_UTIL_PCT) {
  if (!trace) return false
  const names = Array.isArray(trace.coreNames) ? [...trace.coreNames] : []
  const pctMap = trace.coreUtilPct && typeof trace.coreUtilPct === 'object'
    ? trace.coreUtilPct
    : {}
  if (!names.length) {
    for (const k of Object.keys(pctMap)) names.push(k)
  }
  const threshold = Number(minUtilPct)
  let active = 0
  for (const core of names) {
    const pct = Number(pctMap[core] ?? 0)
    if (Number.isFinite(pct) && pct > threshold) {
      active += 1
      if (active > 1) return true
    }
  }
  return false
}

/**
 * Initial pins + collapsed map for a newly opened trace (or Reset to Defaults).
 * SMP-active → pin+expand ``cores`` only. Otherwise all collapsed, none pinned.
 * @param {object|null|undefined} trace
 * @returns {{ pins: string[], collapsed: Record<string, boolean> }}
 */
export function defaultStatsPresentation(trace = null) {
  const collapsed = defaultSectionCollapsed()
  /** @type {string[]} */
  const pins = []
  if (statsTraceIsSmpActive(trace)) {
    pins.push('cores')
    collapsed.cores = false
  }
  return { pins, collapsed }
}

/** @param {string} sectionId @returns {string|undefined} */
export function statsSectionCategory(sectionId) {
  return STATS_SECTION_CATEGORY[String(sectionId || '').trim()]
}

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
  const catalogue = [...STATS_PINNABLE_SECTIONS]
  if (!preferred.length) return catalogue
  const catIndex = new Map(catalogue.map((sid, i) => [sid, i]))
  // Self-heal an order that is just the catalogue with a few sections tacked on
  // at the end — what older builds wrote whenever the catalogue gained a section
  // (appended after every existing one instead of dropped into its own group).
  // A deliberately drag-reordered list is left untouched.
  const sameSet = preferred.length === catalogue.length
    && preferred.every(sid => catIndex.has(sid))
  if (sameSet) {
    for (let k = 1; k < Math.min(preferred.length, 6); k++) {
      const head = preferred.slice(0, preferred.length - k)
      const headSorted = [...head].sort((a, b) => catIndex.get(a) - catIndex.get(b))
      if (head.some((sid, i) => sid !== headSorted[i])) continue
      const healed = [...head]
      const tail = preferred.slice(preferred.length - k)
        .sort((a, b) => catIndex.get(a) - catIndex.get(b))
      for (const sid of tail) {
        let pos = healed.findIndex(h => catIndex.get(h) > catIndex.get(sid))
        if (pos < 0) pos = healed.length
        healed.splice(pos, 0, sid)
      }
      if (healed.every((sid, i) => sid === catalogue[i])) return catalogue
    }
  }
  const seen = new Set(preferred)
  const out = [...preferred]
  // A catalogue-ordered saved list that simply predates a newer section: drop
  // the new IDs into their own group rather than after every existing one.
  const splice = out.every((sid, i) => i === 0 || catIndex.get(out[i - 1]) < catIndex.get(sid))
  for (const sid of catalogue) {
    if (seen.has(sid)) continue
    if (splice) {
      let pos = out.findIndex(h => catIndex.get(h) > catIndex.get(sid))
      if (pos < 0) pos = out.length
      out.splice(pos, 0, sid)
    } else {
      out.push(sid)
    }
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
