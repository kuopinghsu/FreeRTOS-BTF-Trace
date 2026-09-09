/**
 * Investigation Bookmarks and Evidence Chain — deterministic model + serialisation.
 * Keep in sync with btf_viewer_pkg/investigation_notebook.py.
 *
 * An Investigation preserves the reasoning behind a trace analysis: typed
 * bookmarks, links between them, a conclusion, and open questions. Bookmarks
 * reference stable identifiers (a finding rule_id, a metric name, an entity, a
 * time range) rather than copied display text, so a report stays navigable
 * after the trace changes — and stale references are detectable. Pure
 * functions; user text is never merged into measured data.
 */

export const INVESTIGATION_SCHEMA = 'btf-viewer-investigation/2'

// --- Durable investigation status (schema/2) ----------------------------
// One durable status only. The AI workflow *stage* is transient and must never
// be shown as a second Notebook status.
export const NB_STATUS_OPEN = 'open'
export const NB_STATUS_NEEDS_EVIDENCE = 'needs_evidence'
export const NB_STATUS_READY = 'ready_to_conclude'
export const NB_STATUS_CLOSED = 'closed'
export const NOTEBOOK_STATUSES = [
  NB_STATUS_OPEN, NB_STATUS_NEEDS_EVIDENCE, NB_STATUS_READY, NB_STATUS_CLOSED,
]
export const NOTEBOOK_STATUS_LABELS = {
  [NB_STATUS_OPEN]: 'Open',
  [NB_STATUS_NEEDS_EVIDENCE]: 'Needs evidence',
  [NB_STATUS_READY]: 'Ready to conclude',
  [NB_STATUS_CLOSED]: 'Closed',
}

// --- Six-section presentation -----------------------------------------
export const NB_SECTION_ORDER = [
  'question', 'scope', 'hypotheses', 'evidence', 'open_checks', 'conclusion',
]
export const NB_SECTION_LABELS = {
  question: 'Question',
  scope: 'Scope',
  hypotheses: 'Hypotheses',
  evidence: 'Evidence',
  open_checks: 'Open checks',
  conclusion: 'Conclusion',
}

// Empty-state entry points (replace the old generic hint).
export const NB_EMPTY_FROM_FINDINGS = 'Start from current Findings'
export const NB_EMPTY_BLANK = 'Start a blank investigation'

export const BM_OBSERVATION = 'observation'
export const BM_HYPOTHESIS = 'hypothesis'
export const BM_SUPPORTING = 'supporting'
export const BM_CONTRADICTING = 'contradicting'
export const BM_VERIFICATION = 'verification'
export const BM_CONCLUSION = 'conclusion'
export const BOOKMARK_TYPES = [
  BM_OBSERVATION, BM_HYPOTHESIS, BM_SUPPORTING,
  BM_CONTRADICTING, BM_VERIFICATION, BM_CONCLUSION,
]
export const BOOKMARK_TYPE_LABELS = {
  [BM_OBSERVATION]: 'Observation',
  [BM_HYPOTHESIS]: 'Hypothesis',
  [BM_SUPPORTING]: 'Supporting evidence',
  [BM_CONTRADICTING]: 'Contradicting evidence',
  [BM_VERIFICATION]: 'Verification step',
  [BM_CONCLUSION]: 'Conclusion',
}
export const FACT_TYPES = [BM_OBSERVATION, BM_SUPPORTING, BM_VERIFICATION]
export const INTERPRETATION_TYPES = [BM_HYPOTHESIS, BM_CONCLUSION]

export const REF_FINDING = 'finding'
export const REF_METRIC = 'metric'
export const REF_ENTITY = 'entity'
export const REF_RANGE = 'range'
export const REF_EVIDENCE = 'evidence'
export const REF_KINDS = [REF_FINDING, REF_METRIC, REF_ENTITY, REF_RANGE, REF_EVIDENCE]

export const LINK_RELATIONS = ['supports', 'contradicts', 'verifies', 'concludes', 'relates']

// --- Structured evidence cards (schema/2, §8) -------------------------
export const EV_SOURCE_TIMELINE = 'Timeline'
export const EV_SOURCE_STATISTICS = 'Statistics'
export const EV_SOURCE_FINDINGS = 'Analysis Findings'
export const EV_SOURCE_COMPARE = 'Trace Compare'
export const EV_SOURCE_USER = 'User note'
export const EV_SOURCE_AI = 'AI suggestion'
export const EVIDENCE_SOURCES = [
  EV_SOURCE_TIMELINE, EV_SOURCE_STATISTICS, EV_SOURCE_FINDINGS,
  EV_SOURCE_COMPARE, EV_SOURCE_USER, EV_SOURCE_AI,
]
export const EV_KIND_MEASURED = 'measured'
export const EV_KIND_DERIVED = 'derived'
export const EV_KIND_HEURISTIC = 'heuristic'
export const EV_KIND_ESTIMATE = 'estimate'
export const EVIDENCE_KINDS = [EV_KIND_MEASURED, EV_KIND_DERIVED, EV_KIND_HEURISTIC, EV_KIND_ESTIMATE]
export const EVIDENCE_KIND_LABELS = {
  [EV_KIND_MEASURED]: 'Measured',
  [EV_KIND_DERIVED]: 'Derived',
  [EV_KIND_HEURISTIC]: 'Heuristic',
  [EV_KIND_ESTIMATE]: 'Simulation / estimate',
  '': 'User note',
}
export const EV_AUTHOR_USER = 'user'
export const EV_AUTHOR_BTFVIEWER = 'btfviewer'
export const EV_AUTHOR_AI = 'ai'
export const EVIDENCE_AUTHORS = [EV_AUTHOR_USER, EV_AUTHOR_BTFVIEWER, EV_AUTHOR_AI]
export const EVIDENCE_PROTECTED_FIELDS = [
  'source', 'kind', 'author', 'trace_id', 'scope', 'task', 'core', 'value', 'unit',
]
export const EVIDENCE_BOOKMARK_TYPES = [BM_OBSERVATION, BM_SUPPORTING, BM_CONTRADICTING]

function measuredRef(refs) {
  const kinds = new Set((refs || []).filter(r => r && typeof r === 'object').map(r => String(r.kind)))
  if (kinds.has(REF_FINDING)) return EV_SOURCE_FINDINGS
  if (kinds.has(REF_METRIC)) return EV_SOURCE_STATISTICS
  if (kinds.has(REF_RANGE) || kinds.has(REF_EVIDENCE)) return EV_SOURCE_TIMELINE
  return ''
}

/** Coerce a raw evidence card to a valid one, enforcing provenance rules.
 *  AI prose and unreferenced claims are never Measured; source data stays
 *  separate from the bookmark's editable `note`. */
export function normalizeEvidenceCard(card, { refs = null } = {}) {
  if (!card || typeof card !== 'object') return null
  let src = String(card.source || '').trim()
  if (!EVIDENCE_SOURCES.includes(src)) src = measuredRef(refs) || EV_SOURCE_USER
  let author = String(card.author || '').trim().toLowerCase()
  if (!EVIDENCE_AUTHORS.includes(author)) author = src === EV_SOURCE_AI ? EV_AUTHOR_AI : EV_AUTHOR_USER
  if (src === EV_SOURCE_AI) author = EV_AUTHOR_AI
  let kind = String(card.kind || '').trim().toLowerCase()
  if (!EVIDENCE_KINDS.includes(kind)) kind = ''
  if (kind === EV_KIND_MEASURED && (author === EV_AUTHOR_AI || !measuredRef(refs))) {
    kind = author !== EV_AUTHOR_AI ? EV_KIND_DERIVED : ''
  }
  let value = null
  if (typeof card.value === 'number' && Number.isFinite(card.value)) value = card.value
  else if (String(card.value ?? '').trim() !== '') {
    const n = Number(card.value)
    value = Number.isFinite(n) ? n : null
  }
  let scope = null
  const sc = card.scope
  if (sc && typeof sc === 'object' && sc.start != null && sc.end != null) {
    scope = { start: Math.trunc(sc.start), end: Math.trunc(sc.end) }
  }
  return {
    source: src,
    kind,
    author,
    trace_id: String(card.trace_id || ''),
    task: String(card.task || ''),
    core: String(card.core || ''),
    unit: String(card.unit || ''),
    hypothesis_id: String(card.hypothesis_id || ''),
    created_at: String(card.created_at || ''),
    updated_at: String(card.updated_at || ''),
    value,
    scope,
  }
}

export function evidenceCardIsMeasured(card) {
  return !!card && typeof card === 'object' && card.kind === EV_KIND_MEASURED
}

/** Split proposed card `changes` into { allowed, rejected } — protected fields
 *  on a measured card (and setting kind → measured) are never mutable. */
export function guardEvidenceChanges(card, changes) {
  const allowed = {}
  const rejected = []
  const measured = evidenceCardIsMeasured(card)
  for (const [key, val] of Object.entries(changes || {})) {
    if (key === 'kind' && String(val).trim().toLowerCase() === EV_KIND_MEASURED && !measured) {
      rejected.push(key)
      continue
    }
    if (measured && EVIDENCE_PROTECTED_FIELDS.includes(key)) {
      rejected.push(key)
      continue
    }
    allowed[key] = val
  }
  return { allowed, rejected }
}

const SLUG_RE = /[^a-z0-9]+/g

function slug(text, used, prefix = 'bm') {
  const base = String(text || '').toLowerCase().replace(SLUG_RE, '-').replace(/^-+|-+$/g, '').slice(0, 40) || prefix
  let cand = base
  let n = 2
  while (used.has(cand)) { cand = `${base}-${n}`; n++ }
  used.add(cand)
  return cand
}

export function traceIdentity(trace, filename = '') {
  if (!trace) return { file: String(filename || ''), hash: '', time_scale: '', event_count: 0, span: null }
  const segs = trace.segments || []
  const sti = trace.stiEvents || []
  const tMin = trace.timeMin
  const tMax = trace.timeMax
  // Deterministic non-cryptographic digest (host may replace with SHA-256).
  const names = [...(trace.tasks || [])].map(String).sort().slice(0, 200)
  const material = `${trace.timeScale || ''}|${tMin}|${tMax}|${segs.length}|${sti.length}|${names.join('|')}`
  let hash = 0
  for (let i = 0; i < material.length; i++) {
    hash = (hash * 31 + material.charCodeAt(i)) | 0
  }
  return {
    file: String(filename || ''),
    hash: (hash >>> 0).toString(16).padStart(8, '0'),
    time_scale: String(trace.timeScale || ''),
    event_count: segs.length + sti.length,
    span: (tMin != null && tMax != null) ? { start: Math.trunc(tMin), end: Math.trunc(tMax) } : null,
  }
}

export function newInvestigation({ title = '', traceIdentity: ident = null, analysisRange = null } = {}) {
  let rng = null
  if (ident && analysisRange && analysisRange.start != null) {
    rng = { start: Math.trunc(analysisRange.start), end: Math.trunc(analysisRange.end) }
  } else if (analysisRange && analysisRange.start != null) {
    rng = { start: Math.trunc(analysisRange.start), end: Math.trunc(analysisRange.end) }
  }
  return {
    schema: INVESTIGATION_SCHEMA,
    title: String(title || '').trim(),
    trace_identity: { ...(ident || {}) },
    analysis_range: rng,
    bookmarks: [],
    links: [],
    conclusion: '',
    unresolved_questions: [],
    status: NB_STATUS_OPEN,
    updated_at: '',
    next_seq: 1,
  }
}

function clone(inv) {
  if (!inv || typeof inv !== 'object') return newInvestigation()
  return {
    ...inv,
    trace_identity: { ...(inv.trace_identity || {}) },
    bookmarks: (inv.bookmarks || []).map(b => {
      const nb = { ...b, refs: (b.refs || []).map(r => ({ ...r })) }
      if (b.evidence && typeof b.evidence === 'object') {
        nb.evidence = { ...b.evidence }
        if (b.evidence.scope && typeof b.evidence.scope === 'object') {
          nb.evidence.scope = { ...b.evidence.scope }
        }
      }
      return nb
    }),
    links: (inv.links || []).map(l => ({ ...l })),
    unresolved_questions: [...(inv.unresolved_questions || [])],
  }
}

export function normalizeRef(ref) {
  if (!ref || typeof ref !== 'object') return null
  const kind = String(ref.kind || '').trim().toLowerCase()
  if (!REF_KINDS.includes(kind)) return null
  const out = { kind, label: String(ref.label || '').trim() }
  if (kind === REF_FINDING) out.rule_id = String(ref.rule_id || ref.id || '').trim()
  else if (kind === REF_METRIC) out.metric = String(ref.metric || ref.label || '').trim()
  else if (kind === REF_ENTITY) out.entity = String(ref.entity || ref.label || '').trim()
  else if (kind === REF_RANGE || kind === REF_EVIDENCE) {
    const rng = ref.range
    if (rng && typeof rng === 'object' && rng.start != null && rng.end != null) {
      out.range = { start: Math.trunc(rng.start), end: Math.trunc(rng.end) }
    }
    if (ref.time != null && Number.isFinite(Number(ref.time))) out.time = Math.trunc(Number(ref.time))
  }
  return out
}

export function addBookmark(inv, { type, title, note = '', refs = null, bookmarkId = '', evidence = null } = {}) {
  const out = clone(inv)
  let btype = String(type || '').trim().toLowerCase()
  if (!BOOKMARK_TYPES.includes(btype)) btype = BM_OBSERVATION
  const used = new Set(out.bookmarks.map(b => String(b.id)))
  let bid = String(bookmarkId || '').trim()
  if (!bid || used.has(bid)) bid = slug(`${btype}-${title}`, used)
  else used.add(bid)
  const seq = Number(out.next_seq || 1)
  out.next_seq = seq + 1
  const cleanRefs = (refs || []).map(normalizeRef).filter(Boolean)
  const row = {
    id: bid,
    type: btype,
    title: String(title || '').trim() || BOOKMARK_TYPE_LABELS[btype],
    note: String(note || ''),
    refs: cleanRefs,
    seq,
  }
  if (evidence != null && EVIDENCE_BOOKMARK_TYPES.includes(btype)) {
    const card = normalizeEvidenceCard(evidence, { refs: cleanRefs })
    if (card) row.evidence = card
  }
  out.bookmarks.push(row)
  return out
}

/** Add a structured evidence card (a bookmark with an `evidence` dict). Source
 *  data stays separate from the editable explanation (`note`). */
export function addEvidence(inv, {
  title, note = '', role = BM_SUPPORTING, source = EV_SOURCE_USER, kind = '',
  author = EV_AUTHOR_USER, refs = null, task = '', core = '', value = null,
  unit = '', scope = null, traceId = '', hypothesisId = '', createdAt = '',
  bookmarkId = '',
} = {}) {
  let r = String(role || '').trim().toLowerCase()
  if (!EVIDENCE_BOOKMARK_TYPES.includes(r)) r = BM_SUPPORTING
  return addBookmark(inv, {
    type: r, title, note, refs, bookmarkId,
    evidence: {
      source, kind, author, task, core, value, unit, scope,
      trace_id: traceId, hypothesis_id: hypothesisId,
      created_at: createdAt, updated_at: createdAt,
    },
  })
}

/** Edit only the explanation text of an evidence card — never source data. */
export function updateEvidenceExplanation(inv, bookmarkId, note, { updatedAt = '' } = {}) {
  const out = clone(inv)
  const bid = String(bookmarkId || '').trim()
  for (const b of out.bookmarks) {
    if (String(b.id) !== bid) continue
    b.note = String(note || '')
    if (b.evidence && typeof b.evidence === 'object' && updatedAt) b.evidence.updated_at = String(updatedAt)
    break
  }
  return out
}

/** Merge proposed card `changes` for one evidence bookmark; returns
 *  { inv, rejected } where `rejected` names protected fields that were dropped. */
export function applyEvidenceEdit(inv, bookmarkId, changes, { updatedAt = '' } = {}) {
  const out = clone(inv)
  const bid = String(bookmarkId || '').trim()
  let rejected = []
  for (const b of out.bookmarks) {
    if (String(b.id) !== bid) continue
    const card = (b.evidence && typeof b.evidence === 'object') ? b.evidence : {}
    const guard = guardEvidenceChanges(card, changes)
    rejected = guard.rejected
    const allowed = { ...guard.allowed }
    if ('note' in allowed) {
      b.note = String(allowed.note || '')
      delete allowed.note
    }
    if (Object.keys(allowed).length) {
      b.evidence = normalizeEvidenceCard({ ...card, ...allowed }, { refs: b.refs })
    }
    if (b.evidence && typeof b.evidence === 'object' && updatedAt) b.evidence.updated_at = String(updatedAt)
    break
  }
  return { inv: out, rejected }
}

export function updateBookmark(inv, bookmarkId, changes = {}) {
  const out = clone(inv)
  const bid = String(bookmarkId || '').trim()
  for (const b of out.bookmarks) {
    if (String(b.id) !== bid) continue
    if ('type' in changes) {
      const t = String(changes.type || '').trim().toLowerCase()
      if (BOOKMARK_TYPES.includes(t)) b.type = t
    }
    if ('title' in changes) b.title = String(changes.title || '').trim() || b.title
    if ('note' in changes) b.note = String(changes.note || '')
    if ('refs' in changes) b.refs = (changes.refs || []).map(normalizeRef).filter(Boolean)
    break
  }
  return out
}

export function removeBookmark(inv, bookmarkId) {
  const out = clone(inv)
  const bid = String(bookmarkId || '').trim()
  out.bookmarks = out.bookmarks.filter(b => String(b.id) !== bid)
  out.links = out.links.filter(l => String(l.from) !== bid && String(l.to) !== bid)
  return out
}

function bookmarkSortKey(a, b) {
  return (Number(a.seq || 0) - Number(b.seq || 0))
    || String(a.id).localeCompare(String(b.id))
}

/** Reorder one bookmark by delta (±1) among its siblings. `within` restricts
 *  the sibling group to those bookmark types (Evidence passes
 *  EVIDENCE_BOOKMARK_TYPES). Ids / refs / evidence cards are preserved — only
 *  `seq` (the canonical order key loadInvestigation sorts by) is swapped and
 *  the list re-sorted, so the change survives a save/reload. */
export function moveBookmark(inv, bookmarkId, delta, { within = null } = {}) {
  const out = clone(inv)
  const bid = String(bookmarkId || '').trim()
  const bms = out.bookmarks
  let sibs
  if (within && within.length) {
    const wset = new Set(within.map(String))
    sibs = bms.filter(b => wset.has(String(b.type)))
  } else {
    sibs = [...bms]
  }
  sibs.sort(bookmarkSortKey)
  const pos = sibs.findIndex(b => String(b.id) === bid)
  if (pos < 0) return out
  const step = delta > 0 ? 1 : delta < 0 ? -1 : 0
  const npos = pos + step
  if (step === 0 || npos < 0 || npos >= sibs.length) return out
  const a = sibs[pos]
  const b = sibs[npos]
  const sa = Number(a.seq || 0)
  let sb = Number(b.seq || 0)
  if (sa === sb) sb = sa + step
  a.seq = sb
  b.seq = sa
  bms.sort(bookmarkSortKey)
  return out
}

export function linkBookmarks(inv, fromId, toId, relation = 'relates') {
  const out = clone(inv)
  const a = String(fromId || '').trim()
  const b = String(toId || '').trim()
  let rel = String(relation || 'relates').trim().toLowerCase()
  if (!LINK_RELATIONS.includes(rel)) rel = 'relates'
  const ids = new Set(out.bookmarks.map(x => String(x.id)))
  if (a === b || !ids.has(a) || !ids.has(b)) return out
  for (const l of out.links) {
    if (String(l.from) === a && String(l.to) === b) { l.relation = rel; return out }
  }
  out.links.push({ from: a, to: b, relation: rel })
  return out
}

export function unlinkBookmarks(inv, fromId, toId) {
  const out = clone(inv)
  const a = String(fromId || '').trim()
  const b = String(toId || '').trim()
  out.links = out.links.filter(l => !(String(l.from) === a && String(l.to) === b))
  return out
}

export function setConclusion(inv, text) {
  const out = clone(inv)
  out.conclusion = String(text || '').trim()
  return out
}

export function addUnresolvedQuestion(inv, text) {
  const out = clone(inv)
  const q = String(text || '').trim()
  if (q && !out.unresolved_questions.includes(q)) out.unresolved_questions.push(q)
  return out
}

export function removeUnresolvedQuestion(inv, text) {
  const out = clone(inv)
  const q = String(text || '').trim()
  out.unresolved_questions = out.unresolved_questions.filter(x => x !== q)
  return out
}

// --- durable status (schema/2) ----------------------------------------
/** Best-effort durable status for a schema/1 investigation being upgraded.
 *  Never returns 'closed' — closing an investigation is an explicit act. */
export function deriveStatus(inv) {
  inv = inv && typeof inv === 'object' ? inv : {}
  const types = (inv.bookmarks || [])
    .filter(b => b && typeof b === 'object')
    .map(b => String(b.type || ''))
  const hasHypothesis = types.includes(BM_HYPOTHESIS)
  const hasEvidence = types.some(t => t === BM_SUPPORTING || t === BM_VERIFICATION)
  const hasConclusion = !!String(inv.conclusion || '').trim()
    || types.includes(BM_CONCLUSION)
  const hasOpen = (inv.unresolved_questions || []).length > 0
  if (hasConclusion) return NB_STATUS_READY
  if (hasHypothesis && !hasEvidence) return NB_STATUS_NEEDS_EVIDENCE
  if (hasOpen) return NB_STATUS_NEEDS_EVIDENCE
  return NB_STATUS_OPEN
}

export function setStatus(inv, status, { updatedAt = '' } = {}) {
  const out = clone(inv)
  const s = String(status || '').trim().toLowerCase()
  out.status = NOTEBOOK_STATUSES.includes(s) ? s : NB_STATUS_OPEN
  if (updatedAt) out.updated_at = String(updatedAt)
  return out
}

export function touchInvestigation(inv, updatedAt) {
  const out = clone(inv)
  out.updated_at = String(updatedAt || '')
  return out
}

/** Bring a normalised investigation dict up to the current schema, keeping
 *  every bookmark / link / question / conclusion. A transient `workflow_stage`
 *  key, if present, is left untouched — never promoted to the status. */
export function migrateInvestigation(inv) {
  const stored = String(inv.status || '').trim().toLowerCase()
  inv.status = NOTEBOOK_STATUSES.includes(stored) ? stored : deriveStatus(inv)
  inv.updated_at = String(inv.updated_at || '')
  // Wrap legacy evidence bookmarks (schema/1) in a provenance card, keeping
  // every id / ref / note. Provenance inferred conservatively; never AI.
  for (const b of inv.bookmarks || []) {
    if (!b || typeof b !== 'object') continue
    if (!EVIDENCE_BOOKMARK_TYPES.includes(b.type) || (b.evidence && typeof b.evidence === 'object')) continue
    const refs = b.refs || []
    const src = measuredRef(refs) || EV_SOURCE_USER
    b.evidence = normalizeEvidenceCard({
      source: src,
      kind: src !== EV_SOURCE_USER ? EV_KIND_MEASURED : '',
      author: EV_AUTHOR_USER,
      trace_id: String((inv.trace_identity || {}).hash || ''),
    }, { refs })
  }
  inv.schema = INVESTIGATION_SCHEMA
  return inv
}

// --- six-section presentation (pure projection) ----------------------
function evidenceKind(bookmark) {
  for (const r of bookmark.refs || []) {
    if ([REF_FINDING, REF_METRIC, REF_RANGE].includes(String(r.kind))) return 'measured'
  }
  return 'note'
}

function staleBookmarkIds(broken) {
  if (!broken || typeof broken !== 'object') return new Set()
  return new Set((broken.issues || [])
    .filter(i => i && typeof i === 'object' && i.bookmark_id)
    .map(i => String(i.bookmark_id)))
}

function evidenceIsStale(bid, nav, staleIds, broken) {
  if (staleIds.has(String(bid))) return true
  if (broken && typeof broken === 'object' && broken.stale_trace) {
    return Object.keys(nav || {}).length > 0
  }
  return false
}

/** Resolvable navigation targets for one evidence bookmark — no scope change. */
export function evidenceNavTargets(bookmark) {
  const out = {}
  for (const r of (bookmark || {}).refs || []) {
    if (!r || typeof r !== 'object') continue
    if (r.time != null && !('jump' in out)) out.jump = Math.trunc(r.time)
    if (r.range && typeof r.range === 'object' && r.range.start != null && !('range' in out)) {
      out.range = [Math.trunc(r.range.start), Math.trunc(r.range.end)]
    }
    if (String(r.kind) === REF_METRIC && r.metric && !('stats_metric' in out)) out.stats_metric = String(r.metric)
    if (String(r.kind) === REF_FINDING && r.rule_id && !('finding' in out)) out.finding = String(r.rule_id)
  }
  return out
}

/** If an evidence card was measured under a scope that differs from the current
 *  one, describe restoring it — a separate, previewable, cancelable, undoable
 *  action (never folded into Jump to evidence / Show Evidence). Returns null
 *  when there is no stored scope or it already matches. */
export function evidenceScopeRestorePlan(card, { currentScope = null, fmt = null } = {}) {
  if (!card || typeof card !== 'object') return null
  const sc = card.scope
  if (!(sc && typeof sc === 'object' && sc.start != null && sc.end != null)) return null
  const lo = Math.trunc(sc.start)
  const hi = Math.trunc(sc.end)
  const cur = currentScope && typeof currentScope === 'object' ? currentScope : null
  if (cur && cur.start != null && cur.end != null
      && Math.trunc(cur.start) === lo && Math.trunc(cur.end) === hi) {
    return null
  }
  const f = typeof fmt === 'function' ? fmt : (v) => String(Math.trunc(v))
  return {
    start: lo,
    end: hi,
    summary: `Evidence was measured over ${f(lo)} – ${f(hi)}.`,
    changes: [
      `Place C1–C2 at ${f(lo)} – ${f(hi)}`,
      'Zoom the timeline to that window',
      'Limit Statistics to the cursor range',
    ],
  }
}

function hypothesisStatus(inv, bid) {
  const rels = new Set()
  for (const l of inv.links || []) {
    if (String(l.to) === bid || String(l.from) === bid) rels.add(String(l.relation))
  }
  if (rels.has('contradicts')) return 'contradicted'
  if (rels.has('supports') || rels.has('verifies')) return 'supported'
  return 'open'
}

function scopeSummary(inv) {
  const rng = inv.analysis_range
  if (rng && typeof rng === 'object' && rng.start != null) {
    return `${Math.trunc(rng.start)}–${Math.trunc(rng.end)}`
  }
  return 'Full trace'
}

/** Project a stored investigation onto the six report sections, in order.
 *  Purely derived — nothing invented or relabelled as measured. Evidence items
 *  carry the full provenance `card`, a `stale` flag (from an optional
 *  detectBrokenReferences result) and resolvable `nav` targets. */
export function investigationSections(inv, { broken = null } = {}) {
  inv = loadInvestigation(inv)
  const bms = inv.bookmarks || []
  const ident = inv.trace_identity || {}
  const stale = staleBookmarkIds(broken)

  const scopeItems = []
  if (ident.file) scopeItems.push({ kind: 'trace', text: String(ident.file) })
  scopeItems.push({ kind: 'range', text: scopeSummary(inv) })
  if (ident.time_scale) scopeItems.push({ kind: 'unit', text: String(ident.time_scale) })

  const hypItems = bms.filter(b => b.type === BM_HYPOTHESIS).map(b => ({
    bookmark_id: b.id, text: b.title, note: b.note, refs: b.refs,
    status: hypothesisStatus(inv, b.id),
  }))
  const evidenceItems = bms
    .filter(b => EVIDENCE_BOOKMARK_TYPES.includes(b.type))
    .map((b) => {
      const card = (b.evidence && typeof b.evidence === 'object') ? b.evidence : null
      const nav = evidenceNavTargets(b)
      return {
        bookmark_id: b.id, text: b.title, note: b.note, refs: b.refs,
        role: b.type === BM_SUPPORTING ? 'supporting'
          : b.type === BM_CONTRADICTING ? 'contradicting' : 'observation',
        kind: card ? (card.kind ?? evidenceKind(b)) : evidenceKind(b),
        card,
        stale: evidenceIsStale(b.id, nav, stale, broken),
        nav,
      }
    })
  const openItems = [
    ...(inv.unresolved_questions || []).map(q => ({ source: 'question', text: q })),
    ...bms.filter(b => b.type === BM_VERIFICATION).map(b => ({
      source: 'verification', bookmark_id: b.id, text: b.title, note: b.note, refs: b.refs,
    })),
  ]
  const conclusionItems = []
  if (String(inv.conclusion || '').trim()) {
    conclusionItems.push({ kind: 'verdict', text: inv.conclusion })
  }
  for (const b of bms) {
    if (b.type === BM_CONCLUSION) {
      conclusionItems.push({
        kind: 'verdict', bookmark_id: b.id, text: b.title, note: b.note, refs: b.refs,
      })
    }
  }
  const verified = bms.filter(b => b.type === BM_VERIFICATION).length
  conclusionItems.push({
    kind: 'verification_state',
    text: verified
      ? `${verified} verification step(s) recorded`
      : 'No verification steps recorded',
  })

  const byId = {
    question: inv.title ? [{ text: inv.title }] : [],
    scope: scopeItems,
    hypotheses: hypItems,
    evidence: evidenceItems,
    open_checks: openItems,
    conclusion: conclusionItems,
  }
  return NB_SECTION_ORDER.map(sid => ({
    id: sid, title: NB_SECTION_LABELS[sid], items: byId[sid],
  }))
}

/** Compact header row for the Notebook — usable with AI disabled. `broken` is
 *  an optional detectBrokenReferences() result so the count stays pure. */
export function investigationHeader(inv, { broken = null } = {}) {
  inv = loadInvestigation(inv)
  const secs = Object.fromEntries(investigationSections(inv).map(s => [s.id, s]))
  const status = String(inv.status || NB_STATUS_OPEN)
  const ident = inv.trace_identity || {}
  return {
    status,
    status_label: NOTEBOOK_STATUS_LABELS[status] || 'Open',
    trace: String(ident.file || ''),
    scope: scopeSummary(inv),
    hypothesis_count: secs.hypotheses.items.length,
    evidence_count: secs.evidence.items.length,
    open_check_count: secs.open_checks.items.length,
    stale_ref_count: ((broken || {}).issues || []).length,
    updated_at: String(inv.updated_at || ''),
  }
}

// --- undo / redo ---------------------------------------------------------
export function emptyNotebookHistory() {
  return { stack: [], index: -1 }
}

export function pushNotebookState(history, inv, { limit = 100 } = {}) {
  const out = { ...(history || emptyNotebookHistory()) }
  let stack = [...(out.stack || [])].map(s => s)
  const idx = Number(out.index ?? -1)
  if (idx >= 0 && idx < stack.length - 1) stack = stack.slice(0, idx + 1)
  const snap = JSON.parse(dumpInvestigation(inv))
  const snapStr = JSON.stringify(snap)
  if (stack.length && JSON.stringify(stack[stack.length - 1]) === snapStr) {
    out.stack = stack
    out.index = stack.length - 1
    return out
  }
  stack.push(snap)
  const lim = Math.max(2, Number(limit))
  if (stack.length > lim) stack = stack.slice(-lim)
  out.stack = stack
  out.index = stack.length - 1
  return out
}

export function notebookUndo(history) {
  const out = { ...(history || emptyNotebookHistory()) }
  out.index = (out.stack || []).length ? Math.max(0, Number(out.index ?? 0) - 1) : -1
  return out
}

export function notebookRedo(history) {
  const out = { ...(history || emptyNotebookHistory()) }
  const stack = out.stack || []
  out.index = Math.min(stack.length - 1, Number(out.index ?? -1) + 1)
  return out
}

/** Jump the undo cursor to an absolute snapshot index (clamped). Powers the
 *  Notebook "restore from history" control. */
export function notebookGoto(history, index) {
  const out = { ...(history || emptyNotebookHistory()) }
  const stack = out.stack || []
  if (!stack.length) { out.index = -1; return out }
  out.index = Math.max(0, Math.min(stack.length - 1, Number(index)))
  return out
}

export function notebookHistoryState(history) {
  const out = { ...(history || emptyNotebookHistory()) }
  const stack = out.stack || []
  const idx = Number(out.index ?? -1)
  return {
    can_undo: idx > 0,
    can_redo: idx >= 0 && idx < stack.length - 1,
    current: (idx >= 0 && idx < stack.length) ? { ...stack[idx] } : null,
    count: stack.length,
    index: idx,
  }
}

// --- broken references -------------------------------------------------
function refInRange(rng, span) {
  if (!rng || typeof rng !== 'object' || !span || typeof span !== 'object') return true
  return Math.trunc(rng.start) >= Math.trunc(span.start) && Math.trunc(rng.end) <= Math.trunc(span.end)
}

const ENTITY_LEAD_BRACKET_RE = /^\[[^\]]*\]/
const ENTITY_TAIL_ID_RE = /[[(][^\])]*[\])]$/

/**
 * Reduce a task label to its bare name for existence checks. `[0/1]Worker`,
 * `Worker[8]`, `Worker(0x9)` and the merge key `\0 1 \0 Worker` all reduce to
 * `Worker`, so an entity reference resolves whichever decorated form it was
 * stored in (Desktop vs. Web, pre/post Anonymize). Keep in sync with
 * btf_viewer_pkg/investigation_notebook.py `_entity_bare`.
 */
export function entityBare(name) {
  let s = String(name ?? '')
  if (s[0] === '\x00') {
    const j = s.lastIndexOf('\x00')
    if (j > 0) s = s.slice(j + 1)
  }
  s = s.replace(ENTITY_LEAD_BRACKET_RE, '').replace(ENTITY_TAIL_ID_RE, '')
  return s.trim()
}

function entityVocabulary(trace, knownEntities) {
  const ents = new Set()
  for (const e of knownEntities || []) {
    ents.add(String(e))
    const b = entityBare(e)
    if (b) ents.add(b)
  }
  if (trace) {
    const repr = trace.taskRepr
    const entries = repr && typeof repr.entries === 'function'
      ? [...repr.entries()]
      : (repr && typeof repr === 'object' ? Object.entries(repr) : null)
    if (entries && entries.length) {
      for (const [mk, raw] of entries) {
        for (const form of [mk, raw]) {
          ents.add(String(form))
          const b = entityBare(form)
          if (b) ents.add(b)
        }
      }
    } else {
      for (const mk of trace.tasks || []) {
        ents.add(String(mk))
        const b = entityBare(mk)
        if (b) ents.add(b)
      }
    }
    for (const c of trace.coreNames || []) ents.add(String(c))
  }
  return ents
}

export function detectBrokenReferences(inv, {
  trace = null, knownRuleIds = null, knownEntities = null, currentIdentity = null,
} = {}) {
  inv = inv || newInvestigation()
  const issues = []
  const ruleIds = new Set((knownRuleIds || []).map(String))
  const entities = entityVocabulary(trace, knownEntities)
  let span = null
  if (currentIdentity && currentIdentity.span && typeof currentIdentity.span === 'object') {
    span = currentIdentity.span
  } else if (trace) {
    if (trace.timeMin != null && trace.timeMax != null) {
      span = { start: Math.trunc(trace.timeMin), end: Math.trunc(trace.timeMax) }
    }
  }
  let staleTrace = false
  const savedId = inv.trace_identity || {}
  if (currentIdentity && savedId.hash && currentIdentity.hash) {
    staleTrace = savedId.hash !== currentIdentity.hash
  }
  for (const b of inv.bookmarks || []) {
    const bid = String(b.id || '')
    const refs = b.refs || []
    for (let i = 0; i < refs.length; i++) {
      const ref = refs[i]
      const kind = String(ref.kind || '')
      let reason = ''
      if (kind === REF_FINDING && ruleIds.size && !ruleIds.has(ref.rule_id)) {
        reason = `rule '${ref.rule_id}' is no longer produced`
      } else if (kind === REF_ENTITY && entities.size) {
        const ent = String(ref.entity ?? '')
        if (!entities.has(ent) && !entities.has(entityBare(ent))) {
          reason = `entity '${ent}' is not in the trace`
        }
      } else if (kind === REF_RANGE || kind === REF_EVIDENCE) {
        if (!refInRange(ref.range, span)) reason = 'time range falls outside the trace span'
        if (ref.time != null && span && !(Math.trunc(span.start) <= Math.trunc(ref.time) && Math.trunc(ref.time) <= Math.trunc(span.end))) {
          reason = 'timestamp falls outside the trace span'
        }
      }
      if (reason) issues.push({ bookmark_id: bid, ref_index: i, kind, reason })
    }
  }
  return { stale_trace: staleTrace, issues }
}

// --- conclusion → evidence chain ------------------------------------
function refKeyset(bm) {
  const out = new Set()
  for (const r of bm.refs || []) {
    if (r.kind === REF_FINDING && r.rule_id) out.add(`finding:${r.rule_id}`)
    else if (r.kind === REF_METRIC && r.metric) out.add(`metric:${r.metric}`)
    else if (r.kind === REF_ENTITY && r.entity) out.add(`entity:${r.entity}`)
  }
  return out
}

function sharedRef(a, b) {
  const ka = refKeyset(a)
  for (const k of refKeyset(b)) if (ka.has(k)) return true
  return false
}

export function conclusionEvidenceChains(inv) {
  inv = inv || newInvestigation()
  const byId = {}
  for (const b of inv.bookmarks || []) byId[String(b.id)] = b
  const adj = {}
  for (const bid of Object.keys(byId)) adj[bid] = new Set()
  for (const l of inv.links || []) {
    const a = String(l.from)
    const b = String(l.to)
    if (a in adj && b in adj) { adj[a].add(b); adj[b].add(a) }
  }
  const ids = Object.keys(byId)
  for (const a of ids) {
    for (const b of ids) {
      if (a !== b && sharedRef(byId[a], byId[b])) adj[a].add(b)
    }
  }
  const chains = []
  for (const bid of ids) {
    const bm = byId[bid]
    if (bm.type !== BM_CONCLUSION) continue
    const seen = new Set([bid])
    const queue = [...(adj[bid] || [])]
    const support = []
    while (queue.length) {
      const nid = queue.shift()
      if (seen.has(nid)) continue
      seen.add(nid)
      const nb = byId[nid]
      if (!nb) continue
      support.push({ id: nid, type: nb.type, title: nb.title })
      queue.push(...(adj[nid] || []))
    }
    support.sort((x, y) => (INTERPRETATION_TYPES.includes(x.type) - INTERPRETATION_TYPES.includes(y.type))
      || String(x.id).localeCompare(String(y.id)))
    chains.push({ conclusion_id: bid, title: bm.title, evidence: support, grounded: support.length > 0 })
  }
  return chains
}

// --- serialisation ---------------------------------------------------
export function dumpInvestigation(inv) {
  return JSON.stringify(sortKeys(loadInvestigation(inv)), null, 2)
}

function sortKeys(v) {
  if (Array.isArray(v)) return v.map(sortKeys)
  if (v && typeof v === 'object') {
    const out = {}
    for (const k of Object.keys(v).sort()) out[k] = sortKeys(v[k])
    return out
  }
  return v
}

export function loadInvestigation(raw) {
  if (typeof raw === 'string') {
    try { raw = JSON.parse(raw) } catch { raw = {} }
  }
  if (!raw || typeof raw !== 'object') raw = {}
  const base = newInvestigation({
    title: String(raw.title || ''),
    traceIdentity: (raw.trace_identity && typeof raw.trace_identity === 'object') ? raw.trace_identity : {},
    analysisRange: (raw.analysis_range && typeof raw.analysis_range === 'object') ? raw.analysis_range : null,
  })
  const used = new Set()
  const bookmarks = []
  let maxSeq = 0
  for (const b of raw.bookmarks || []) {
    if (!b || typeof b !== 'object') continue
    let btype = String(b.type || '').trim().toLowerCase()
    if (!BOOKMARK_TYPES.includes(btype)) btype = BM_OBSERVATION
    let bid = String(b.id || '').trim()
    if (!bid || used.has(bid)) bid = slug(`${btype}-${b.title || ''}`, used)
    else used.add(bid)
    let seq = Number(b.seq || 0)
    if (!Number.isFinite(seq)) seq = 0
    maxSeq = Math.max(maxSeq, seq)
    const cleanRefs = (b.refs || []).map(normalizeRef).filter(Boolean)
    const row = {
      id: bid,
      type: btype,
      title: String(b.title || '').trim() || BOOKMARK_TYPE_LABELS[btype],
      note: String(b.note || ''),
      refs: cleanRefs,
      seq: seq || (bookmarks.length + 1),
    }
    if (b.evidence && typeof b.evidence === 'object' && EVIDENCE_BOOKMARK_TYPES.includes(btype)) {
      const card = normalizeEvidenceCard(b.evidence, { refs: cleanRefs })
      if (card) row.evidence = card
    }
    bookmarks.push(row)
  }
  bookmarks.sort((a, b) => (a.seq - b.seq) || String(a.id).localeCompare(String(b.id)))
  const ids = new Set(bookmarks.map(b => b.id))
  const links = []
  const seenLinks = new Set()
  for (const l of raw.links || []) {
    if (!l || typeof l !== 'object') continue
    const a = String(l.from || '')
    const b = String(l.to || '')
    let rel = String(l.relation || 'relates').trim().toLowerCase()
    if (!LINK_RELATIONS.includes(rel)) rel = 'relates'
    const key = `${a}|${b}`
    if (ids.has(a) && ids.has(b) && a !== b && !seenLinks.has(key)) {
      seenLinks.add(key)
      links.push({ from: a, to: b, relation: rel })
    }
  }
  const out = { ...raw, ...base }
  out.bookmarks = bookmarks
  out.links = links
  out.conclusion = String(raw.conclusion || '').trim()
  out.unresolved_questions = (raw.unresolved_questions || []).map(String).map(s => s.trim()).filter(Boolean)
  // base carries default status/updated_at; keep any stored values so
  // migrateInvestigation can honour an explicit status.
  out.status = raw.status || ''
  out.updated_at = String(raw.updated_at || '')
  out.next_seq = Math.max(Number(base.next_seq), maxSeq + 1)
  out.schema = INVESTIGATION_SCHEMA
  return migrateInvestigation(out)
}

// --- bridge from the findings triage "case" list ----------------------
export function investigationFromCase({
  caseFindingIds = [], findings = [], traceIdentity: ident = null, analysisRange = null, title = '',
} = {}) {
  const want = (caseFindingIds || []).map(String).map(s => s.trim()).filter(Boolean)
  const byId = {}
  for (const f of findings || []) if (f && typeof f === 'object') byId[String(f.id || '')] = f
  let inv = newInvestigation({ title: title || 'Investigation', traceIdentity: ident || {}, analysisRange })
  for (const fid of want) {
    const f = byId[fid]
    if (!f) continue
    const refs = [{ kind: REF_FINDING, rule_id: String(f.rule_id || fid), label: String(f.title || f.observation || fid) }]
    for (const ent of f.entities || []) refs.push({ kind: REF_ENTITY, entity: String(ent), label: String(ent) })
    const rng = f.affected_range
    if (rng && typeof rng === 'object' && rng.start != null) refs.push({ kind: REF_RANGE, range: rng, label: 'evidence window' })
    const metric = String(f.inspect || '').trim()
    if (metric) refs.push({ kind: REF_METRIC, metric, label: metric })
    const isEmpty = String(f.severity) === 'info' && String(f.title || '').toLowerCase().includes('no findings')
    inv = addBookmark(inv, {
      type: isEmpty ? BM_CONTRADICTING : BM_SUPPORTING,
      title: String(f.observation || f.title || fid),
      note: String(f.text || ''),
      refs,
    })
  }
  return inv
}

// --- guided scaffold: seed a structured investigation from findings ----
const _SEV_RANK = { error: 0, warning: 1, info: 2 }

/**
 * Merge a starter structure into `inv` from the current analysis findings:
 * every actionable finding becomes an Observation (with finding/entity/range/
 * metric refs), and — only when the notebook was empty — a Hypothesis and a
 * Verification-step stub are appended so the evidence chain has somewhere to go.
 * Findings already referenced by a bookmark are skipped, so it is safe to re-run.
 *
 * @param {object} inv
 * @param {{ findings?: object[], cursorRange?: {start:number,end:number}|null,
 *           limit?: number, includeInfo?: boolean }} opts
 * @returns {object} the updated investigation
 */
export function scaffoldInvestigationFromFindings(inv, {
  findings = [], cursorRange = null, limit = 8, includeInfo = false,
} = {}) {
  let out = inv || newInvestigation()
  const wasEmpty = (out.bookmarks || []).length === 0

  const already = new Set()
  for (const b of out.bookmarks || []) {
    for (const r of b.refs || []) {
      if (r.kind === REF_FINDING && r.rule_id) already.add(String(r.rule_id))
    }
  }

  const rows = (findings || [])
    .filter((f) => f && typeof f === 'object')
    .filter((f) => includeInfo || String(f.severity || 'info') !== 'info')
    .slice()
    .sort((a, b) =>
      (_SEV_RANK[String(a.severity)] ?? 3) - (_SEV_RANK[String(b.severity)] ?? 3))

  let added = 0
  for (const f of rows) {
    if (added >= limit) break
    const ruleId = String(f.rule_id || f.ruleId || f.id || '').trim()
    if (!ruleId || already.has(ruleId)) continue
    already.add(ruleId)
    const refs = [{ kind: REF_FINDING, rule_id: ruleId, label: String(f.title || ruleId) }]
    for (const ent of f.entities || []) {
      refs.push({ kind: REF_ENTITY, entity: String(ent), label: String(ent) })
    }
    const rng = (f.affected_range && f.affected_range.start != null)
      ? f.affected_range
      : (cursorRange && cursorRange.start != null ? cursorRange : null)
    if (rng) refs.push({ kind: REF_RANGE, range: { start: rng.start, end: rng.end }, label: 'evidence window' })
    const metric = String(f.inspect || f.inspect_href || '').trim()
    if (metric) refs.push({ kind: REF_METRIC, metric, label: metric })
    out = addBookmark(out, {
      type: BM_OBSERVATION,
      title: String(f.title || f.observation || ruleId),
      note: String(f.text || f.impact || ''),
      refs,
    })
    added += 1
  }

  if (wasEmpty) {
    out = addBookmark(out, {
      type: BM_HYPOTHESIS,
      title: 'Likely cause — edit this',
      note: 'What single explanation best fits the observations above? '
        + 'Link the observations that support it.',
    })
    out = addBookmark(out, {
      type: BM_VERIFICATION,
      title: 'How to confirm — edit this',
      note: 'Which measurement, cursor window, or experiment would confirm or '
        + 'rule out the hypothesis?',
    })
  }
  return out
}

/**
 * Up to `limit` actual relevant findings for the Question screen's "Start
 * from a finding" picker — same severity ordering as
 * scaffoldInvestigationFromFindings, deduped by rule_id, excluding the
 * "no findings" info sentinel. Returns the original finding objects
 * unreshaped (callers already know how to read rule_id/title/severity/etc.
 * off a raw finding, same as findingOptions in the Notebook dialog).
 *
 * @param {object[]} findings
 * @param {number} limit
 * @returns {object[]}
 */
export function topFindingsForStart(findings, limit = 3) {
  const seen = new Set()
  const isEmptySentinel = (f) => String(f.severity) === 'info'
    && String(f.title || '').toLowerCase().includes('no findings')
  const rows = (findings || [])
    .filter((f) => f && typeof f === 'object' && !isEmptySentinel(f))
    .filter((f) => {
      const ruleId = String(f.rule_id || f.ruleId || f.id || '').trim()
      if (!ruleId || seen.has(ruleId)) return false
      seen.add(ruleId)
      return true
    })
    .slice()
    .sort((a, b) => (_SEV_RANK[String(a.severity)] ?? 3) - (_SEV_RANK[String(b.severity)] ?? 3))
  return rows.slice(0, Math.max(0, Number(limit) || 0))
}
