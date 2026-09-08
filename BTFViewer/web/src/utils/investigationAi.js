/**
 * Collaborate-with-AI entry point + AI proposal review for the Investigation
 * Notebook (BTFVIEWER_DESIGN_CONSISTENCY_TODO §9, §10).
 *
 * Pure functions. investigationNotebook stays AI-independent; this module is the
 * only place that turns AI output into *proposed* Notebook operations and
 * validates them against protected provenance before the user accepts. Nothing
 * here mutates durable state on its own — applyProposal is the explicit-
 * acceptance entry point and is never wired to run automatically.
 *
 * Keep in sync with btf_viewer_pkg/investigation_ai.py.
 */
import {
  BM_CONCLUSION,
  BM_HYPOTHESIS,
  EVIDENCE_BOOKMARK_TYPES,
  EV_AUTHOR_AI,
  EV_KIND_MEASURED,
  LINK_RELATIONS,
  NB_STATUS_CLOSED,
  NOTEBOOK_STATUSES,
  addEvidence,
  guardEvidenceChanges,
  investigationHeader,
  investigationSections,
  linkBookmarks,
  loadInvestigation,
  normalizeEvidenceCard,
  removeBookmark,
  setConclusion,
  setStatus,
  updateEvidenceExplanation,
} from './investigationNotebook.js'

// --- §9 — one "Collaborate with AI" entry point ---------------------
export const NB_AI_DISABLED_REASON = 'Enable AI Assistant in Settings → AI'

export const NB_AI_ACTIONS = [
  ['review_investigation', 'Review investigation',
    'Review this investigation. List unsupported claims, contradictions and '
    + 'missing evidence. Do not change anything — return findings only.'],
  ['suggest_next_check', 'Suggest next check',
    'Recommend exactly one evidence-producing action available in BTFViewer '
    + '(a tool call or a Statistics/Timeline step) that would most advance this '
    + 'investigation. One action, with the reason.'],
  ['draft_hypotheses', 'Draft hypotheses',
    "Propose up to three hypotheses for the open question. Mark each 'open' — "
    + "never 'supported'. Cite the evidence id(s) each rests on."],
  ['draft_conclusion', 'Draft conclusion',
    'Draft a conclusion using only the accepted Notebook evidence. State '
    + 'limitations and the verification state. Cite the evidence ids used.'],
  ['update_from_findings', 'Update from Findings',
    'Propose evidence cards from the current deterministic Analysis Findings. '
    + "Each card must reference the finding's rule_id; never label a card "
    + 'Measured unless it references measured BTFViewer output.'],
  ['compare_trace', 'Compare with another trace',
    'Compare with the other open trace. Baseline A is Trace A, Candidate B is '
    + 'Trace B; verdicts describe Candidate B versus Baseline A. Use the current '
    + 'Compare Scope.'],
]
const NB_AI_ACTION_IDS = new Set(NB_AI_ACTIONS.map(a => a[0]))
export const NB_AI_ACTION_LABELS = Object.fromEntries(NB_AI_ACTIONS.map(a => [a[0], a[1]]))
export const NB_AI_ACTION_PROMPTS = Object.fromEntries(NB_AI_ACTIONS.map(a => [a[0], a[2]]))

export function nbAiActionReason(actionId, inv, { aiEnabled, hasSecondTrace = false } = {}) {
  if (!aiEnabled) return NB_AI_DISABLED_REASON
  const aid = String(actionId || '').trim()
  if (aid === 'compare_trace' && !hasSecondTrace) return 'Open a second trace to compare'
  if (aid === 'draft_conclusion') {
    const secs = Object.fromEntries(investigationSections(inv).map(s => [s.id, s]))
    if (!secs.evidence.items.length) return 'Add evidence before drafting a conclusion'
  }
  return ''
}

export function collaborateHeader(inv, { broken = null, selectedCount = 0 } = {}) {
  inv = loadInvestigation(inv)
  const hdr = investigationHeader(inv, { broken })
  const stale = Number(hdr.stale_ref_count || 0)
  return {
    investigation_title: String(inv.title || 'Untitled investigation'),
    status_label: hdr.status_label,
    trace: hdr.trace,
    scope: hdr.scope,
    evidence_count: hdr.evidence_count,
    selected_count: Number(selectedCount || 0),
    stale_warning: stale ? `${stale} reference(s) no longer resolve` : '',
  }
}

export function collaborateContext(inv, {
  action = '', findings = null, selectedEvidenceIds = null, broken = null,
} = {}) {
  inv = loadInvestigation(inv)
  let aid = String(action || '').trim()
  if (aid && !NB_AI_ACTION_IDS.has(aid)) aid = ''
  const sections = investigationSections(inv, { broken })
  const evItems = (sections.find(s => s.id === 'evidence') || {}).items || []
  const want = new Set((selectedEvidenceIds || []).map(String))
  const selected = evItems.filter(it => !want.size || want.has(String(it.bookmark_id)))
  const ctx = {
    action: aid,
    prompt: NB_AI_ACTION_PROMPTS[aid] || '',
    header: collaborateHeader(inv, { broken, selectedCount: selected.length }),
    investigation: {
      title: String(inv.title || ''),
      status: String(inv.status || ''),
      trace_identity: { ...(inv.trace_identity || {}) },
      sections,
    },
    selected_evidence: selected,
  }
  if (aid === 'update_from_findings') {
    ctx.findings = (findings || [])
      .filter(f => f && typeof f === 'object')
      .slice(0, 20)
      .map(f => ({
        rule_id: String(f.rule_id || f.id || ''),
        title: String(f.title || ''),
        severity: String(f.severity || ''),
        task: String(f.task || ''),
      }))
  }
  return ctx
}

// --- §10 — proposal review ------------------------------------------
export const PROPOSAL_SCHEMA = 'btf-viewer-nb-proposal/1'
export const PROPOSAL_OPS = ['add', 'update', 'link', 'change_status', 'remove']
export const OP_OK = 'ok'
export const OP_CONFIRM = 'needs_confirmation'
export const OP_REJECTED = 'rejected'

export function stripModelSecrets(meta) {
  const m = meta && typeof meta === 'object' ? meta : {}
  const out = {}
  for (const k of ['model', 'provider', 'context_mode']) {
    if (m[k]) out[k] = String(m[k])
  }
  return out
}

function bookmarkIndex(inv) {
  const m = {}
  for (const b of inv.bookmarks || []) m[String(b.id)] = b
  return m
}

function annotateOp(inv, op, { traceHash, allowOtherTrace }) {
  const kind = String(op.op || '').trim().toLowerCase()
  const out = { ...op, op: kind }
  if (!PROPOSAL_OPS.includes(kind)) {
    out.status = OP_REJECTED
    out.reason = `unknown op ${JSON.stringify(kind)}`
    return out
  }
  const bidx = bookmarkIndex(inv)
  const opTrace = String(op.trace_id || '')
  if (opTrace && opTrace !== traceHash && !allowOtherTrace) {
    out.status = OP_REJECTED
    out.reason = 'references another trace without an explicit Compare action'
    return out
  }

  if (kind === 'add') {
    const role = String(op.role || op.type || '').trim().toLowerCase()
    if (!EVIDENCE_BOOKMARK_TYPES.includes(role)) {
      out.status = OP_REJECTED
      out.reason = 'add needs an evidence role'
      return out
    }
    const card = normalizeEvidenceCard({
      source: op.source, kind: op.kind, author: op.author || EV_AUTHOR_AI,
      task: op.task, unit: op.unit, value: op.value, scope: op.scope,
    }, { refs: op.refs })
    out.card = card
    if (String(op.kind || '').toLowerCase() === EV_KIND_MEASURED
      && (!card || card.kind !== EV_KIND_MEASURED)) {
      out.reason = 'downgraded from Measured — AI prose is not measured'
    }
    if ((role === 'supporting' || role === 'contradicting')
      && !(op.evidence_ids || op.rationale) && !out.reason) {
      out.reason = 'no supporting evidence id cited'
    }
    out.status = OP_OK
    return out
  }

  if (kind === 'update') {
    const target = bidx[String(op.bookmark_id || '')]
    if (!target) {
      out.status = OP_REJECTED
      out.reason = 'unknown bookmark_id'
      return out
    }
    const card = (target.evidence && typeof target.evidence === 'object') ? target.evidence : {}
    const { rejected } = guardEvidenceChanges(card, op.changes || {})
    if (rejected.length) {
      out.status = OP_REJECTED
      out.reason = `measured data not changed: ${rejected.slice().sort().join(', ')}`
      return out
    }
    if (target.type === BM_CONCLUSION || 'conclusion' in (op.changes || {})) {
      out.status = OP_CONFIRM
      out.reason = 'replaces a conclusion'
      return out
    }
    out.status = OP_OK
    return out
  }

  if (kind === 'link') {
    const a = String(op.from || '')
    const b = String(op.to || '')
    if (!bidx[a] || !bidx[b] || a === b) {
      out.status = OP_REJECTED
      out.reason = 'link needs two existing bookmarks'
      return out
    }
    const rel = String(op.relation || 'relates').trim().toLowerCase()
    if (!LINK_RELATIONS.includes(rel)) {
      out.status = OP_REJECTED
      out.reason = `unknown relation ${JSON.stringify(rel)}`
      return out
    }
    out.relation = rel
    out.status = OP_OK
    return out
  }

  if (kind === 'change_status') {
    const s = String(op.status || '').trim().toLowerCase()
    if (!NOTEBOOK_STATUSES.includes(s)) {
      out.status = OP_REJECTED
      out.reason = `unknown status ${JSON.stringify(s)}`
      return out
    }
    out.status_value = s
    if (s === NB_STATUS_CLOSED) {
      out.status = OP_CONFIRM
      out.reason = 'closes the investigation'
      return out
    }
    out.status = OP_OK
    return out
  }

  // remove
  const target = bidx[String(op.bookmark_id || '')]
  if (!target) {
    out.status = OP_REJECTED
    out.reason = 'unknown bookmark_id'
    return out
  }
  out.status = OP_CONFIRM
  out.reason = EVIDENCE_BOOKMARK_TYPES.includes(target.type) ? 'removes evidence' : 'removes a bookmark'
  return out
}

export function validateProposal(inv, proposal, { findings = null, allowOtherTrace = false } = {}) {
  inv = loadInvestigation(inv)
  const traceHash = String((inv.trace_identity || {}).hash || '')
  const raw = proposal && typeof proposal === 'object' ? proposal : {}
  const ops = Array.isArray(raw.operations) ? raw.operations : []
  const annotated = ops.map((op, i) => ({
    ...annotateOp(inv, (op && typeof op === 'object') ? op : {}, { traceHash, allowOtherTrace }),
    index: i,
  }))
  const applicable = annotated.some(o => o.status === OP_OK || o.status === OP_CONFIRM)
  return {
    schema: PROPOSAL_SCHEMA,
    ok: !!applicable,
    operations: annotated,
    model: stripModelSecrets(raw.model),
  }
}

export function proposalDiff(inv, validated) {
  const v = validated && typeof validated === 'object' ? validated : {}
  const bySection = { hypotheses: [], evidence: [], conclusion: [], status: [], links: [] }
  const needsConfirmation = []
  const rejected = []
  for (const op of v.operations || []) {
    if (op.status === OP_REJECTED) { rejected.push(op); continue }
    if (op.status === OP_CONFIRM) needsConfirmation.push(op)
    const kind = op.op
    if (kind === 'add') {
      const role = String(op.role || op.type || '')
      bySection[role === BM_HYPOTHESIS ? 'hypotheses' : 'evidence'].push(op)
    } else if (kind === 'update') {
      bySection['conclusion' in (op.changes || {}) ? 'conclusion' : 'evidence'].push(op)
    } else if (kind === 'change_status') {
      bySection.status.push(op)
    } else if (kind === 'link') {
      bySection.links.push(op)
    } else if (kind === 'remove') {
      bySection.evidence.push(op)
    }
  }
  return { by_section: bySection, needs_confirmation: needsConfirmation, rejected }
}

export function applyProposal(inv, validated, {
  acceptIndices = null, acceptAll = false, confirmedIndices = null, now = '',
} = {}) {
  const v = validated && typeof validated === 'object' ? validated : {}
  const ops = v.operations || []
  const model = stripModelSecrets(v.model)
  const want = acceptAll ? null : new Set((acceptIndices || []).map(Number))
  const confirmed = new Set((confirmedIndices || []).map(Number))
  let cur = loadInvestigation(inv)
  const applied = []
  const skipped = []
  for (const op of ops) {
    const i = Number(op.index ?? -1)
    let take = op.status === OP_OK || (op.status === OP_CONFIRM && confirmed.has(i))
    if (want) take = take && want.has(i)
    if (!take) { skipped.push(i); continue }
    cur = applyOne(cur, op, { model, now })
    applied.push(i)
  }
  if (applied.length) {
    const events = [...(cur.proposal_events || [])]
    events.push({
      schema: PROPOSAL_SCHEMA,
      at: String(now || ''),
      accepted: applied,
      rejected: ops.filter(o => o.status === OP_REJECTED).map(o => Number(o.index ?? -1)),
      model,
    })
    cur.proposal_events = events
  }
  return { inv: cur, applied, skipped }
}

function tagAiProv(inv, prov, now) {
  const bms = inv.bookmarks || []
  const last = bms[bms.length - 1]
  if (last && last.evidence && typeof last.evidence === 'object') {
    last.evidence.ai_provenance = {
      model: String(prov.model || ''),
      provider: String(prov.provider || ''),
      source_evidence_ids: [...(prov.source_evidence_ids || [])],
    }
    last.evidence.updated_at = String(now || '')
  }
  return inv
}

function applyOne(inv, op, { model, now }) {
  const kind = op.op
  if (kind === 'add') {
    const card = op.card || {}
    const out = addEvidence(inv, {
      title: String(op.title || 'AI evidence'),
      note: String(op.note || op.rationale || ''),
      role: String(op.role || op.type || 'supporting'),
      source: String(card.source || 'AI suggestion'),
      kind: String(card.kind || ''),
      author: EV_AUTHOR_AI,
      refs: op.refs,
      task: String(card.task || ''),
      value: card.value,
      unit: String(card.unit || ''),
      scope: card.scope,
      hypothesisId: String(op.hypothesis_id || ''),
      createdAt: String(now || ''),
    })
    return tagAiProv(out, {
      model: model.model || '',
      provider: model.provider || '',
      source_evidence_ids: (op.evidence_ids || []).map(String),
    }, now)
  }
  if (kind === 'update') {
    if ('conclusion' in (op.changes || {})) {
      return setConclusion(inv, String(op.changes.conclusion || ''))
    }
    const note = (op.changes || {}).note
    if (note != null) {
      return updateEvidenceExplanation(inv, String(op.bookmark_id || ''), String(note), { updatedAt: now })
    }
    return inv
  }
  if (kind === 'link') {
    return linkBookmarks(inv, String(op.from || ''), String(op.to || ''), String(op.relation || 'relates'))
  }
  if (kind === 'change_status') {
    return setStatus(inv, String(op.status_value || op.status || ''), { updatedAt: now })
  }
  if (kind === 'remove') {
    return removeBookmark(inv, String(op.bookmark_id || ''))
  }
  return inv
}
