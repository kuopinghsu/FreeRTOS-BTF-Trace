/**
 * Universal Evidence Navigation (Step 2).
 * Lockstep with btf_viewer_pkg/evidence_nav.py.
 *
 * Show Evidence centers the Timeline, places/reuses one Evidence cursor, and
 * highlights the related Task — without silently changing Scope or Filters.
 */
import { bestFindingScope } from './uxExplore.js'

export const EVIDENCE_GLYPH = '\u2197' // ↗

/** Tooltip for Evidence-affordance cells (Statistics / Findings / Compare). */
export const EVIDENCE_TOOLTIP = 'Jump to Evidence (does not change Scope)'

const TIME_TOKEN_RE = /(?:jump:)?(\d+(?:\.\d+)?)\s*(ns|us|µs|μs|ms|s)?/gi

const UNIT_NS = {
  '': 1,
  ns: 1,
  us: 1e3,
  'µs': 1e3,
  'μs': 1e3,
  ms: 1e6,
  s: 1e9,
}

export function parseEvidenceTimestamps(...texts) {
  const out = []
  const seen = new Set()
  for (const text of texts) {
    const blob = String(text || '')
    TIME_TOKEN_RE.lastIndex = 0
    let m
    while ((m = TIME_TOKEN_RE.exec(blob)) !== null) {
      const value = Number(m[1])
      if (!Number.isFinite(value)) continue
      const unit = String(m[2] || '').toLowerCase()
      const raw = m[0]
      let scale = UNIT_NS[unit] ?? 1
      if (!unit && !/jump:/i.test(raw)) {
        if (value < 1e6) continue
        scale = 1
      }
      const ns = Math.trunc(value * scale)
      if (ns < 0 || seen.has(ns)) continue
      seen.add(ns)
      out.push(ns)
    }
  }
  return out
}

export function resolveFindingEvidence(finding, events, timeMin, timeMax) {
  if (!finding || typeof finding !== 'object') {
    return {
      ok: false,
      ns: null,
      task: '',
      mk: '',
      note: '',
      multi: false,
      reason: 'No finding selected',
    }
  }

  const times = []
  for (const ev of finding.evidence || []) {
    if (!ev || typeof ev !== 'object') continue
    for (const key of ['time', 'start', 'stop', 'ns']) {
      if (ev[key] == null) continue
      const v = Number(ev[key])
      if (Number.isFinite(v)) times.push(v)
    }
  }
  times.push(
    ...parseEvidenceTimestamps(
      finding.evidence_text || '',
      finding.title || '',
      finding.text || '',
    ),
  )

  const scope = bestFindingScope(finding, events, timeMin, timeMax)
  let task = String(scope?.task || finding.task || '').trim()
  let mk = String(scope?.mk || '').trim()
  const multi = new Set(times.map(t => Math.trunc(t))).size > 1

  let ns = null
  let note = ''
  if (times.length) {
    ns = Math.trunc(Math.max(...times))
    note = multi
      ? 'Representative (latest) Evidence among multiple samples'
      : 'Evidence timestamp from finding'
  } else if (scope) {
    const lo = Math.trunc(scope.lo || 0)
    const hi = Math.trunc(scope.hi || lo)
    ns = Math.trunc((lo + hi) / 2)
    note = scope.reason || 'Representative moment in finding episode'
    task = task || String(scope.task || '')
    mk = mk || String(scope.mk || '')
  }

  if (ns == null) {
    return {
      ok: false,
      ns: null,
      task,
      mk,
      note: '',
      multi: false,
      reason: 'No locatable Timeline Evidence for this finding',
    }
  }

  const tmin = Math.trunc(timeMin || 0)
  const tmax = Math.trunc(timeMax || 0)
  if (tmax > tmin) ns = Math.max(tmin, Math.min(tmax, ns))

  return {
    ok: true,
    ns,
    task,
    mk,
    note,
    multi,
    reason: '',
  }
}

export function resolveTimestampEvidence(
  ns,
  { task = '', mk = '', note = '', timeMin = 0, timeMax = 0 } = {},
) {
  if (ns == null || ns === '') {
    return {
      ok: false,
      ns: null,
      task: task || '',
      mk: mk || '',
      note: '',
      multi: false,
      reason: 'Evidence timestamp is missing or invalid',
    }
  }
  const value = Number(ns)
  if (!Number.isFinite(value)) {
    return {
      ok: false,
      ns: null,
      task: task || '',
      mk: mk || '',
      note: '',
      multi: false,
      reason: 'Evidence timestamp is missing or invalid',
    }
  }
  let out = Math.trunc(value)
  const tmin = Math.trunc(timeMin || 0)
  const tmax = Math.trunc(timeMax || 0)
  if (tmax > tmin) out = Math.max(tmin, Math.min(tmax, out))
  return {
    ok: true,
    ns: out,
    task: String(task || ''),
    mk: String(mk || ''),
    note: note || 'Evidence timestamp',
    multi: false,
    reason: '',
  }
}
