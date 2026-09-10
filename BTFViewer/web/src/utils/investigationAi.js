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
  EVIDENCE_KIND_LABELS,
  EV_AUTHOR_AI,
  EV_KIND_MEASURED,
  LINK_RELATIONS,
  NB_STATUS_CLOSED,
  NOTEBOOK_STATUSES,
  addBookmark,
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

/**
 * The one reply contract every collaborate action (except refine_question) must
 * follow, so the Notebook can render the answer as a select-and-add proposal
 * card instead of a wall of prose. Appended to each task prompt below and kept
 * in lockstep with investigation_ai.py's NB_PROPOSAL_REPLY_FORMAT.
 */
export const NB_PROPOSAL_REPLY_FORMAT = [
  'Reply with ONE ```json fenced block and NOTHING before or after it — no',
  'commentary, no "next steps", no links, and do NOT put it inside a markdown',
  'list or numbered step. The block is exactly:',
  '{"schema":"btf-viewer-nb-proposal/1","summary":"<1-2 plain sentences>",',
  ' "notes":["<short point>", ...],"operations":[<op>, ...]}',
  'Each op is exactly one of:',
  ' {"op":"add","role":"observation|supporting|contradicting|hypothesis","title":"...","note":"<your words>","evidence_ids":["E1"]}',
  ' {"op":"update","bookmark_id":"E1","changes":{"note":"..."}}  or  {"op":"update","changes":{"conclusion":"..."}}',
  ' {"op":"link","from":"E1","to":"H1","relation":"supports|contradicts|verifies|relates"}',
  ' {"op":"change_status","status":"open|closed"}',
  'Use "operations":[] when you are only reviewing. Cite only evidence ids shown in the',
  'context; never use kind "measured" or a "supported" status; every hypothesis stays "open".',
].join('\n')

const NB_AI_TASKS = [
  ['review_investigation', 'Review investigation',
    'Review this investigation for unsupported claims, contradictions and weak or '
    + 'missing evidence; put each finding in "notes". Where the evidence is too thin '
    + 'to support a conclusion, ALSO return "add" operations naming the specific next '
    + 'evidence to collect — which BTFViewer Statistics section or tool would produce '
    + 'it and what it would show — so the investigation can reach at least '
    + 'Derived-strength evidence. Otherwise "operations":[].'],
  ['gather_evidence', 'Gather evidence',
    'Collect evidence for the open question by CALLING BTFViewer tools. Call tools '
    + 'as many times as needed — one round per gap — until every claim you would make '
    + 'is backed by measured tool output. Then return "add" operations (role '
    + '"supporting" or "observation") whose "note" cites the exact tool and the '
    + 'numbers it returned; list anything you still could not substantiate in "notes".'],
  ['suggest_next_check', 'Suggest next check',
    'Recommend exactly one evidence-producing next action (a BTFViewer tool call or a '
    + 'Statistics/Timeline step). Put it and the reason in "summary"; "operations":[].'],
  ['draft_hypotheses', 'Draft hypotheses',
    'Propose up to three hypotheses for the open question as "add" operations with '
    + 'role "hypothesis", each citing in evidence_ids the id(s) it rests on.'],
  ['draft_conclusion', 'Draft conclusion',
    'Draft a conclusion from the accepted Notebook evidence as one "update" operation '
    + 'with changes.conclusion. State the limitations and verification state in it.'],
  ['update_from_findings', 'Update from Findings',
    'Propose evidence cards from the listed Analysis Findings as "add" operations '
    + '(role "supporting" or "observation"); each "note" must reference the finding.'],
  ['compare_trace', 'Compare with another trace',
    'Compare with the other open trace (Baseline A vs Candidate B, current Compare '
    + 'Scope) and propose "add" operations for the notable differences.'],
]

export const NB_AI_ACTIONS = [
  ...NB_AI_TASKS.map(([id, label, task]) => [id, label, `${task}\n\n${NB_PROPOSAL_REPLY_FORMAT}`]),
  ['refine_question', 'Help refine question',
    'Suggest one clearer, more specific rewording of this investigation '
    + 'question. Return only the improved question text on its own line, '
    + 'prefixed with "Suggested question: ". No JSON, no other operations.'],
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

/**
 * Extract the "Suggested question: …" line from a refine_question reply, if
 * present. Deliberately narrow — this is a single scalar-field suggestion
 * (the question text), not a structured proposal, so it bypasses the whole
 * PROPOSAL_OPS/validateProposal/applyProposal machinery entirely: "Use this
 * question" just sets inv.title directly. Returns '' when the reply doesn't
 * match (never invent a suggestion from unstructured prose).
 */
export function parseQuestionSuggestion(replyText) {
  const m = /Suggested question:\s*(.+)/i.exec(String(replyText || ''))
  if (!m) return ''
  return m[1].trim().replace(/^["']|["']$/g, '')
}

/**
 * Turn a prose AI reply into `[{ title, items: [] }]` for the Notebook's
 * right panel — markdown headings (`#`..`######`, or a lone `**Bold:**` line)
 * start a section; `-`/`*`/`•`/`1.`/`1)` lines and any other non-empty line
 * become items. Inline `**` / `` ` `` and leading `#` are stripped. Falls back
 * to one untitled section. Used only for a reply that is NOT a structured
 * proposal; kept in lockstep with investigation_ai.py's parse_reply_blocks.
 */
export function parseReplyBlocks(replyText) {
  const raw = String(replyText || '')
  if (!raw) return []
  const clean = (s) => String(s)
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/^#{1,6}\s*/, '')
    .trim()
  const blocks = []
  let cur = null
  for (const rawLine of raw.split('\n')) {
    const line = rawLine.trim()
    if (!line) continue
    const isHeading = /^#{1,6}\s+/.test(line) || /^\*\*[^*]+\*\*:?\s*$/.test(line)
    if (isHeading) {
      cur = { title: clean(line).replace(/:$/, ''), items: [] }
      blocks.push(cur)
      continue
    }
    if (!cur) { cur = { title: '', items: [] }; blocks.push(cur) }
    cur.items.push(clean(line.replace(/^([-*•]|\d+[.)])\s+/, '')))
  }
  return blocks.filter((b) => b.title || b.items.length)
}

/**
 * Pull a `btf-viewer-nb-proposal/…` object out of a model reply even when the
 * model wrapped it in a ```json fence, a markdown list (`* `/`- `/`1. ` on each
 * line), or surrounded it with prose and "next step" links. Returns the object
 * (with `operations` defaulted to `[]`) or null. Lockstep with
 * investigation_ai.py's extract_notebook_proposal.
 */
export function extractNotebookProposal(text) {
  const raw = String(text || '')
  const stripListMarkers = (s) => String(s)
    .split('\n')
    .map((ln) => ln.replace(/^\s*(?:[*+-]|\d+[.)])\s+/, ''))
    .join('\n')
    .trim()

  const candidates = []
  const fence = /```(?:json)?\s*([\s\S]*?)```/gi
  let m
  while ((m = fence.exec(raw))) candidates.push(m[1])
  candidates.push(raw)
  // brace-balanced object around the schema marker (handles a bare, unfenced
  // object buried in prose)
  const sIdx = raw.indexOf('btf-viewer-nb-proposal/')
  if (sIdx >= 0) {
    const open = raw.lastIndexOf('{', sIdx)
    if (open >= 0) {
      let depth = 0
      for (let i = open; i < raw.length; i += 1) {
        if (raw[i] === '{') depth += 1
        else if (raw[i] === '}') {
          depth -= 1
          if (depth === 0) { candidates.push(raw.slice(open, i + 1)); break }
        }
      }
    }
  }

  for (const c of candidates) {
    let obj
    try { obj = JSON.parse(stripListMarkers(c)) } catch { continue }
    if (obj && typeof obj === 'object'
      && String(obj.schema || '').startsWith('btf-viewer-nb-proposal/')
      && (Array.isArray(obj.operations) || obj.summary || Array.isArray(obj.notes))) {
      if (!Array.isArray(obj.operations)) obj.operations = []
      return obj
    }
  }
  return null
}

// Explicit reply budget for a Notebook collaboration turn. The proposal JSON
// (summary + notes + operations, often CJK) does not fit the Compact 500-token
// cap, and leaving it unset lets a local server apply its own small default —
// both truncate the JSON mid-string. Sent as max_tokens for every NB collab
// request regardless of context mode. Lockstep with investigation_ai.py.
export const NB_PROPOSAL_REPLY_TOKENS = 4096

export const NB_PROPOSAL_TRUNCATED_HINT =
  'The AI’s reply was cut off before the Notebook proposal finished. The '
  + 'model likely hit its output limit or stopped early — try a larger / '
  + 'stronger model, shrink the request (narrower Scope, fewer findings, '
  + 'clear a long chat), and for a local server make sure its context window '
  + 'is large (Ollama: `OLLAMA_CONTEXT_LENGTH` / `num_ctx` ≥ 8192, and '
  + 'restart it). Then run this action again.'

/**
 * Heuristic: the reply was emitting a `btf-viewer-nb-proposal` but was cut off
 * before the JSON closed (a local model running out of context mid-answer).
 * True only when a proposal marker is present, extraction failed, and the
 * braces from the marker onward stay unbalanced. Lockstep with
 * investigation_ai.py's looks_like_truncated_proposal.
 */
export function looksLikeTruncatedProposal(text) {
  const raw = String(text || '')
  if (!raw.trim() || !raw.includes('btf-viewer-nb-proposal')) return false
  if (extractNotebookProposal(raw)) return false
  const sIdx = raw.indexOf('btf-viewer-nb-proposal')
  const open = raw.lastIndexOf('{', sIdx)
  if (open < 0) return false
  let depth = 0
  for (let i = open; i < raw.length; i += 1) {
    if (raw[i] === '{') depth += 1
    else if (raw[i] === '}') {
      depth -= 1
      if (depth === 0) return false
    }
  }
  return depth > 0
}

/**
 * Rewrite an assistant reply that carries a `btf-viewer-nb-proposal/…` object
 * so the AI panel (and the Notebook) show a readable summary instead of a raw
 * JSON code block + "next step" link soup. No-op when the text has no proposal.
 * Lockstep with investigation_ai.py's summarize_notebook_proposal_for_chat.
 */
export function summarizeNotebookProposalForChat(text) {
  const raw = String(text || '')
  const obj = extractNotebookProposal(raw)
  if (!obj) return raw

  const rest = raw
    .replace(/```(?:json)?\s*[\s\S]*?```/gi, '')
    .split('\n')
    .filter((ln) => {
      const s = ln.trim().replace(/^(?:[*+-]|\d+[.)])\s+/, '')
      if (!s || s === '`' || s === '```') return false
      if (/"schema"\s*:\s*"btf-viewer-nb-proposal/.test(s)) return false
      if (/\]\((?:btfnext|btfstats):/i.test(s)) return false
      return true
    })
    .join('\n')
    .trim()

  const nOps = Array.isArray(obj.operations) ? obj.operations.length : 0
  const out = ['**AI proposal for the Investigation Notebook**']
  const summary = String(obj.summary || '').trim()
  if (summary) { out.push('', summary) }
  const notes = Array.isArray(obj.notes) ? obj.notes.map(n => String(n || '').trim()).filter(Boolean) : []
  if (notes.length) { out.push(''); for (const n of notes) out.push(`- ${n}`) }
  // P0.3 — the proposal review opens the Notebook itself; no "open the
  // Notebook" instruction, and no Review action for zero operations.
  out.push('', nOps
    ? `_${nOps} change${nOps === 1 ? '' : 's'} proposed._`
    : '_No Notebook changes proposed._')
  if (rest) out.push('', rest)
  return out.join('\n')
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

/** Human-readable Markdown digest of a collaborateContext() payload — what the
 *  AI actually receives, formatted for a person to skim (no JSON). Used both as
 *  the message context sent to the model and in the AI panel's "what's sent"
 *  disclosure. */
export function collaborateDigest(ctx) {
  const c = ctx && typeof ctx === 'object' ? ctx : {}
  const inv = c.investigation || {}
  const byId = {}
  for (const s of inv.sections || []) byId[s.id] = s.items || []
  const out = []
  const first = (byId.question || [])[0]
  out.push(`**Question** — ${first && first.text ? first.text : '_(untitled)_'}`)
  const scope = (byId.scope || []).map(i => i.text).filter(Boolean)
  if (scope.length) out.push(`**Scope** — ${scope.join(' · ')}`)

  const hyp = byId.hypotheses || []
  if (hyp.length) {
    out.push('', `**Hypotheses (${hyp.length})**`)
    for (const h of hyp) out.push(`- ${h.text}${h.status ? `  _(${h.status})_` : ''}`)
  }

  const ev = (Array.isArray(c.selected_evidence) && c.selected_evidence.length)
    ? c.selected_evidence
    : (byId.evidence || [])
  if (ev.length) {
    out.push('', `**Evidence (${ev.length})**`)
    for (const e of ev) {
      const label = (e.kind && e.kind !== 'note' && EVIDENCE_KIND_LABELS[e.kind])
        || EVIDENCE_KIND_LABELS['']
      const note = String(e.note || '').split('\n')[0].trim()
      out.push(`- _[${label}]_ ${e.text}${note ? ` — ${note}` : ''}`
        + `${e.stale ? '  ⚠ stale reference' : ''}`)
    }
  }

  const checks = (byId.open_checks || []).map(i => i.text).filter(Boolean)
  if (checks.length) {
    out.push('', `**Open checks (${checks.length})**`)
    for (const t of checks) out.push(`- ${t}`)
  }

  const verdict = (byId.conclusion || [])
    .filter(i => i.kind === 'verdict').map(i => i.text).filter(Boolean)
  out.push('', `**Conclusion** — ${verdict.length ? verdict.join(' ') : '_none yet_'}`)
  return out.join('\n')
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
    if (![...EVIDENCE_BOOKMARK_TYPES, BM_HYPOTHESIS].includes(role)) {
      out.status = OP_REJECTED
      out.reason = 'add needs an evidence or hypothesis role'
      return out
    }
    // Normalise the role so proposalDiff routing and apply() agree regardless
    // of how the model cased it ("Hypothesis" / "SUPPORTING" / …).
    out.role = role
    // A hypothesis has no evidence card — it is an interpretation the user
    // still has to verify. Accept it, but flag one missing its evidence
    // citation; it can never be applied as anything but 'open'.
    if (role === BM_HYPOTHESIS) {
      out.status = OP_OK
      if (!(Array.isArray(op.evidence_ids) && op.evidence_ids.length)
        && !String(op.rationale || '').trim()) {
        out.reason = 'hypothesis cites no evidence id'
      }
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
  const notes = Array.isArray(raw.notes)
    ? raw.notes.map(n => String(n == null ? '' : n).trim()).filter(Boolean)
    : []
  return {
    schema: PROPOSAL_SCHEMA,
    ok: !!applicable,
    summary: String(raw.summary || '').trim(),
    notes,
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
    const role = String(op.role || op.type || 'supporting').trim().toLowerCase()
    if (role === BM_HYPOTHESIS) {
      // Add the hypothesis bookmark, then wire each cited evidence id that
      // resolves to a real bookmark as a 'supports' link (the demo's
      // "Add hypothesis" outcome). Missing/self ids are skipped, not errors.
      let out = addBookmark(inv, {
        type: BM_HYPOTHESIS,
        title: String(op.title || 'AI hypothesis'),
        note: String(op.note || op.rationale || ''),
        refs: op.refs,
      })
      const bms = out.bookmarks || []
      const newId = String(bms[bms.length - 1]?.id || '')
      const known = new Set(bms.map((b) => String(b.id)))
      for (const evId of (op.evidence_ids || []).map(String)) {
        if (evId && evId !== newId && known.has(evId)) {
          out = linkBookmarks(out, evId, newId, 'supports')
        }
      }
      return out
    }
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
