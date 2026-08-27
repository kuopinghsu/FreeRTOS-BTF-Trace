/**
 * Findings triage queue helpers.
 * Keep in sync with btf_viewer_pkg/findings_triage.py.
 */

import { evidenceStrengthBadge, normalizeEvidenceStrength } from './evidenceStrength.js'

const SEVERITY_ORDER = { error: 0, warning: 1, info: 2, ask: 3 }

export const FINDING_CATEGORIES = [
  'migration', 'blocking', 'deadline', 'load', 'jitter',
  'execution', 'dispatch', 'general',
]

export const SORT_SEVERITY = 'severity'
export const SORT_EVIDENCE = 'evidence'
export const SORT_TITLE = 'title'
export const SORT_CATEGORY = 'category'
export const SORT_KEYS = [SORT_SEVERITY, SORT_EVIDENCE, SORT_TITLE, SORT_CATEGORY]
export const SORT_LABELS = {
  [SORT_SEVERITY]: 'Severity',
  [SORT_EVIDENCE]: 'Evidence strength',
  [SORT_TITLE]: 'Title',
  [SORT_CATEGORY]: 'Category',
}

export function findingCategory(finding) {
  const blob = `${finding.title || ''} ${finding.text || ''}`.toLowerCase()
  if (/migrat|thrash|bounce/.test(blob)) return 'migration'
  if (/block|mutex|wait/.test(blob)) return 'blocking'
  if (/deadline|budget/.test(blob)) return 'deadline'
  if (/load|balance|gini/.test(blob)) return 'load'
  if (/jitter|period/.test(blob)) return 'jitter'
  if (/wcet|execution|cpu/.test(blob)) return 'execution'
  if (/dispatch|latency/.test(blob)) return 'dispatch'
  return 'general'
}

export function findingEvidenceStrength(finding) {
  const ev = finding.evidence || []
  if (ev.some(e => e && typeof e === 'object' && e.time != null)) return 'direct'
  if (ev.length) return 'derived'
  return 'estimated'
}

function defaultCheckNext(finding) {
  const cat = findingCategory(finding)
  const mapping = {
    migration: 'Open Core Migrations and check load balance first.',
    blocking: 'Inspect Blocking Time and Mutex Blocking around the cited time.',
    deadline: 'Open Deadline / CPU Budget and Response Time.',
    load: 'Open Load Balance and Task × Core.',
    jitter: 'Open Period / Jitter and Recurring Patterns.',
    execution: 'Open Execution and Worst Events for Max/outliers.',
    dispatch: 'Open Dispatch latency and Execution.',
  }
  return mapping[cat] || 'Open Statistics for the related metric and verify on the timeline.'
}

export function enrichFindingCard(finding) {
  const title = String(finding.title || 'Finding')
  const text = String(finding.text || '')
  const strength = findingEvidenceStrength(finding)
  const badge = evidenceStrengthBadge(strength)
  const evLines = []
  for (const ev of finding.evidence || []) {
    if (!ev || typeof ev !== 'object') continue
    const label = String(ev.label || ev.text || 'evidence')
    evLines.push(ev.time != null ? `${label}: jump:${ev.time}` : label)
  }
  return {
    ...finding,
    category: findingCategory(finding),
    evidence_strength: strength,
    evidence_strength_label: badge.label,
    observation: title,
    evidence_text: evLines.length ? evLines.join('; ') : 'No timed evidence yet.',
    why_it_matters: text || 'May indicate a timing or scheduling problem in the current Scope.',
    check_next: finding.check_next || defaultCheckNext(finding),
  }
}

export function sortFindingsTriage(items, { sortBy = SORT_SEVERITY } = {}) {
  let mode = String(sortBy || SORT_SEVERITY).trim().toLowerCase()
  if (!SORT_KEYS.includes(mode)) mode = SORT_SEVERITY
  const strengthRank = { direct: 0, derived: 1, estimated: 2, configured: 1 }
  const enriched = (items || []).filter(f => f && typeof f === 'object').map(f => enrichFindingCard({ ...f }))
  enriched.sort((a, b) => {
    const sa = SEVERITY_ORDER[String(a.severity || 'info').toLowerCase()] ?? 9
    const sb = SEVERITY_ORDER[String(b.severity || 'info').toLowerCase()] ?? 9
    const ea = strengthRank[normalizeEvidenceStrength(a.evidence_strength)] ?? 3
    const eb = strengthRank[normalizeEvidenceStrength(b.evidence_strength)] ?? 3
    const ta = String(a.title || '')
    const tb = String(b.title || '')
    const ca = String(a.category || '')
    const cb = String(b.category || '')
    if (mode === SORT_EVIDENCE) {
      if (ea !== eb) return ea - eb
      if (sa !== sb) return sa - sb
      return ta.localeCompare(tb)
    }
    if (mode === SORT_TITLE) {
      const cmp = ta.localeCompare(tb)
      if (cmp) return cmp
      if (sa !== sb) return sa - sb
      return ea - eb
    }
    if (mode === SORT_CATEGORY) {
      const cmp = ca.localeCompare(cb)
      if (cmp) return cmp
      if (sa !== sb) return sa - sb
      if (ea !== eb) return ea - eb
      return ta.localeCompare(tb)
    }
    if (sa !== sb) return sa - sb
    if (ea !== eb) return ea - eb
    return ta.localeCompare(tb)
  })
  return enriched
}

export function filterFindingsTriage(items, {
  severity = '', category = '', task = '', core = '',
  evidenceStrength = '', sortBy = SORT_SEVERITY,
} = {}) {
  const sevW = String(severity || '').trim().toLowerCase()
  const catW = String(category || '').trim().toLowerCase()
  const taskW = String(task || '').trim().toLowerCase()
  const coreW = String(core || '').trim().toLowerCase()
  const evW = String(evidenceStrength || '').trim().toLowerCase()
  return sortFindingsTriage(items, { sortBy }).filter(f => {
    if (sevW && String(f.severity || '').toLowerCase() !== sevW) return false
    if (catW && String(f.category || '').toLowerCase() !== catW) return false
    const blob = `${f.title || ''} ${f.text || ''} ${f.task || ''} ${f.core || ''}`.toLowerCase()
    if (taskW && !blob.includes(taskW)) return false
    if (coreW && !blob.includes(coreW)) return false
    if (evW && normalizeEvidenceStrength(f.evidence_strength) !== evW) return false
    return true
  })
}

export function findingFilterFacets(items) {
  const cats = new Set()
  const tasks = new Set()
  const cores = new Set()
  for (const f of sortFindingsTriage(items || [])) {
    cats.add(String(f.category || 'general'))
    const task = String(f.task || '').trim()
    if (task) tasks.add(task)
    const core = String(f.core || '').trim()
    if (core) cores.add(core)
    const blob = `${f.title || ''} ${f.text || ''}`
    const re = /\bCore[_ ]?\d+\b/gi
    let m
    while ((m = re.exec(blob))) cores.add(m[0].replace(/ /g, '_'))
  }
  return {
    categories: [...cats].sort(),
    tasks: [...tasks].sort((a, b) => a.localeCompare(b)),
    cores: [...cores].sort((a, b) => a.localeCompare(b)),
  }
}

export function groupFindingsByIncident(items, clusters = [], { group = true } = {}) {
  const findings = (items || []).filter(f => f && typeof f === 'object')
  if (!group || !findings.length) {
    return findings.map(f => ({ kind: 'finding', ...f }))
  }
  const incs = (clusters || []).filter(c => c && typeof c === 'object')
  const idToInc = new Map()
  const titleToInc = new Map()
  for (const inc of incs) {
    for (const fid of inc.finding_ids || []) {
      if (fid) idToInc.set(String(fid), inc)
    }
    for (const title of inc.findings || []) {
      if (title) titleToInc.set(String(title), inc)
    }
  }
  const buckets = new Map()
  const order = []
  const ungrouped = []
  for (const f of findings) {
    const fid = String(f.id || '')
    const title = String(f.title || f.observation || '')
    const inc = idToInc.get(fid) || titleToInc.get(title)
    if (!inc || Number(inc.count || 0) < 2) {
      ungrouped.push(f)
      continue
    }
    const cid = String(inc.id || '')
    if (!buckets.has(cid)) {
      buckets.set(cid, [])
      order.push(cid)
    }
    buckets.get(cid).push(f)
  }
  const rows = []
  for (const cid of order) {
    const members = buckets.get(cid) || []
    if (members.length < 2) {
      for (const m of members) rows.push({ kind: 'finding', ...m })
      continue
    }
    const inc = idToInc.get(String(members[0].id || '')) || {}
    const root = String(inc.root_suspect || 'mixed')
    rows.push({
      kind: 'header',
      incident_id: cid,
      label: `${cid} · ${root}`,
      count: members.length,
      finding_ids: members.map(m => String(m.id || '')),
    })
    for (const m of members) rows.push({ kind: 'finding', incident_id: cid, ...m })
  }
  for (const f of ungrouped) rows.push({ kind: 'finding', ...f })
  return rows
}

export function formatInvestigatePreview(finding, {
  scope = null, sectionId = '', sectionLabel = '',
  currentLimit = false, currentLo = null, currentHi = null,
} = {}) {
  if (!finding || typeof finding !== 'object') {
    return 'Select a finding to preview Investigate.'
  }
  const lines = ['Investigate will:']
  const sid = String(sectionId || '').trim()
  const slabel = String(sectionLabel || sid || 'related Statistics').trim()
  lines.push(`  • Open Statistics → ${slabel}`)
  if (scope && scope.lo != null && scope.hi != null) {
    const lo = Math.trunc(Number(scope.lo))
    const hi = Math.trunc(Number(scope.hi))
    const reason = String(scope.reason || 'recommended evidence window').trim()
    lines.push(`  • Place C1–C2 at ${lo}–${hi} (${reason})`)
    lines.push('  • Enable Limit to C1–Cn for Statistics / Findings')
    if (currentLimit && currentLo != null && currentHi != null) {
      lines.push(`  • Replaces current Scope ${Math.trunc(Number(currentLo))}–${Math.trunc(Number(currentHi))}`)
    } else if (currentLimit) {
      lines.push('  • Replaces the current cursor Scope')
    } else {
      lines.push('  • Scope is currently Full Trace (Limit off)')
    }
  } else {
    lines.push('  • Keep the current cursor Scope (no recommended window)')
  }
  lines.push('You can Undo the Scope change after Confirm.')
  return lines.join('\n')
}

/** Queue labels shown in the Analysis Findings strip (Done = reviewed). */
export const QUEUE_OPEN = 'open'
export const QUEUE_DONE = 'done'
export const QUEUE_CASE = 'case'
export const QUEUE_DISMISSED = 'dismissed'
export const QUEUE_IDS = [QUEUE_OPEN, QUEUE_DONE, QUEUE_CASE, QUEUE_DISMISSED]

export function defaultTriageState() {
  return { reviewed: [], dismissed: {}, case: [] }
}

export function normalizeTriageState(state) {
  const base = defaultTriageState()
  if (!state || typeof state !== 'object') return base
  const reviewed = (state.reviewed || []).map(x => String(x).trim()).filter(Boolean)
  const caseIds = (state.case || []).map(x => String(x).trim()).filter(Boolean)
  const dismissed = {}
  const raw = state.dismissed || {}
  if (raw && typeof raw === 'object') {
    for (const [k, v] of Object.entries(raw)) {
      const kid = String(k).trim()
      if (kid) dismissed[kid] = String(v || 'Dismissed')
    }
  }
  return { reviewed, dismissed, case: caseIds }
}

/** Primary queue for a finding: dismissed > case > done > open. */
export function findingQueueStatus(findingId, state = null) {
  const st = normalizeTriageState(state)
  const fid = String(findingId || '').trim()
  if (!fid) return QUEUE_OPEN
  if (st.dismissed?.[fid]) return QUEUE_DISMISSED
  if ((st.case || []).includes(fid)) return QUEUE_CASE
  if ((st.reviewed || []).includes(fid)) return QUEUE_DONE
  return QUEUE_OPEN
}

export function filterByQueue(items, state = null, { queue = QUEUE_OPEN } = {}) {
  let q = String(queue || QUEUE_OPEN).trim().toLowerCase() || QUEUE_OPEN
  if (!QUEUE_IDS.includes(q)) q = QUEUE_OPEN
  const st = normalizeTriageState(state)
  return (items || []).filter(f => {
    if (!f || typeof f !== 'object') return false
    return findingQueueStatus(f.id || '', st) === q
  })
}

export function queueCounts(items, state = null) {
  const st = normalizeTriageState(state)
  const counts = Object.fromEntries(QUEUE_IDS.map(id => [id, 0]))
  for (const f of items || []) {
    if (!f || typeof f !== 'object') continue
    const fid = String(f.id || '').trim()
    if (!fid) {
      counts[QUEUE_OPEN] += 1
      continue
    }
    counts[findingQueueStatus(fid, st)] += 1
  }
  return counts
}

export function applyTriageAction(state, findingId, action, { reason = '' } = {}) {
  const out = normalizeTriageState(state)
  const fid = String(findingId || '').trim()
  const act = String(action || '').trim().toLowerCase()
  if (!fid) return out
  if (act === 'reviewed' || act === 'done') {
    const reviewed = [...(out.reviewed || [])]
    if (!reviewed.includes(fid)) reviewed.push(fid)
    out.reviewed = reviewed
    const dismissed = { ...(out.dismissed || {}) }
    delete dismissed[fid]
    out.dismissed = dismissed
  } else if (act === 'unreviewed' || act === 'undo_done') {
    out.reviewed = (out.reviewed || []).filter(x => x !== fid)
  } else if (act === 'dismiss') {
    out.dismissed = { ...(out.dismissed || {}), [fid]: String(reason || 'Dismissed') }
    out.reviewed = (out.reviewed || []).filter(x => x !== fid)
    out.case = (out.case || []).filter(x => x !== fid)
  } else if (act === 'undismiss' || act === 'restore') {
    const dismissed = { ...(out.dismissed || {}) }
    delete dismissed[fid]
    out.dismissed = dismissed
  } else if (act === 'case') {
    const caseIds = [...(out.case || [])]
    if (!caseIds.includes(fid)) caseIds.push(fid)
    out.case = caseIds
    const dismissed = { ...(out.dismissed || {}) }
    delete dismissed[fid]
    out.dismissed = dismissed
  } else if (act === 'uncase') {
    out.case = (out.case || []).filter(x => x !== fid)
  }
  return out
}

/** Append Done / Case / Dismissed sections for Save as text. */
export function formatTriageAuditText(findings, state = null) {
  const st = normalizeTriageState(state)
  const byId = {}
  for (const f of findings || []) {
    if (!f || typeof f !== 'object') continue
    const fid = String(f.id || '').trim()
    if (fid) byId[fid] = f
  }
  const titleOf = (fid) => String((byId[fid] || {}).title || fid)
  const lines = []
  const done = st.reviewed || []
  const caseIds = st.case || []
  const dismissed = st.dismissed || {}
  if (done.length) {
    lines.push('Done:')
    for (const fid of done) lines.push(`  - ${titleOf(fid)} (id=${fid})`)
    lines.push('')
  }
  if (caseIds.length) {
    lines.push('In case:')
    for (const fid of caseIds) lines.push(`  - ${titleOf(fid)} (id=${fid})`)
    lines.push('')
  }
  if (Object.keys(dismissed).length) {
    lines.push('Dismissed:')
    for (const [fid, reason] of Object.entries(dismissed)) {
      lines.push(`  - ${titleOf(fid)} (id=${fid}): ${reason}`)
    }
    lines.push('')
  }
  return lines.join('\n').replace(/\n+$/, '')
}
