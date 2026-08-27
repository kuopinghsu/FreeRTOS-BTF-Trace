/**
 * Evidence-strength labels.
 * Keep in sync with btf_viewer_pkg/evidence_strength.py.
 */

export const EVIDENCE_STRENGTHS = ['direct', 'derived', 'estimated', 'configured']

export const EVIDENCE_STRENGTH_LABELS = {
  direct: 'Direct',
  derived: 'Derived',
  estimated: 'Estimated / heuristic',
  configured: 'Configured comparison',
}

export const EVIDENCE_STRENGTH_TOOLTIPS = {
  direct: 'Recorded in the trace (slice start/end, core ID, STI tag value).',
  derived: 'Deterministic calculation from recorded evidence.',
  estimated: 'Useful screening evidence with stated assumptions.',
  configured: 'Valid only when the configured threshold matches the application requirement.',
}

export const METRIC_EVIDENCE_STRENGTH = {
  response_time: 'estimated',
  critical_path: 'estimated',
  task_health: 'estimated',
  waiter_owner: 'estimated',
  mutex_blocking: 'derived',
  core_util: 'derived',
  migrations: 'derived',
  load_balance: 'derived',
  deadline: 'configured',
  cpu_budget: 'configured',
  anomalies: 'derived',
  worst_events: 'derived',
  execution: 'derived',
  blocking: 'derived',
  dispatch: 'derived',
  period_jitter: 'derived',
  preemption: 'derived',
}

export const ESTIMATED_VERIFY_HINTS = {
  response_time: {
    missing: 'End-to-end response markers or explicit release→complete pairs.',
    verify: 'Correlate Execution, Dispatch, Blocking, and Preemption on the timeline.',
  },
  critical_path: {
    missing: 'Full causal chain with blocking and preemption evidence.',
    verify: 'Walk Critical Path steps and jump to each blocking/preemption event.',
  },
  task_health: {
    missing: 'Configured health thresholds and complete slice coverage.',
    verify: 'Compare Task Health with Execution and Blocking tables.',
  },
  waiter_owner: {
    missing: 'Mutex/semaphore STI pairing for waiter and owner tasks.',
    verify: 'Open Waiter × Owner and Mutex Blocking for the same window.',
  },
  default: {
    missing: 'Direct trace events that confirm this interpretation.',
    verify: 'Inspect Timeline Evidence and supporting Statistics sections.',
  },
}

export function normalizeEvidenceStrength(value) {
  const want = String(value || '').trim().toLowerCase()
  if (EVIDENCE_STRENGTHS.includes(want)) return want
  if (want === 'heuristic' || want === 'estimate') return 'estimated'
  if (want === 'config' || want === 'configured comparison' || want === 'budget' || want === 'deadline') {
    return 'configured'
  }
  return 'derived'
}

export function evidenceStrengthForMetric(metricId) {
  const key = String(metricId || '').trim().toLowerCase().replace(/-/g, '_')
  return METRIC_EVIDENCE_STRENGTH[key] || 'derived'
}

export function evidenceStrengthBadge(strength) {
  const key = normalizeEvidenceStrength(strength)
  return {
    strength: key,
    label: EVIDENCE_STRENGTH_LABELS[key],
    tooltip: EVIDENCE_STRENGTH_TOOLTIPS[key],
  }
}

export function estimatedVerifyHints(metricId = '') {
  const key = String(metricId || '').trim().toLowerCase().replace(/-/g, '_')
  return { ...(ESTIMATED_VERIFY_HINTS[key] || ESTIMATED_VERIFY_HINTS.default) }
}

export function formatEvidenceStrengthNote(strength, { metricId = '', verified = false } = {}) {
  const badge = evidenceStrengthBadge(strength)
  if (normalizeEvidenceStrength(strength) === 'estimated') {
    const hints = estimatedVerifyHints(metricId)
    const headline = verified ? 'Cause' : 'Possible explanation'
    return `${badge.label} — ${headline}. What is missing? ${hints.missing} How to verify: ${hints.verify}`
  }
  if (verified) return `${badge.label} — verified conclusion.`
  return `${badge.label} — ${badge.tooltip}`
}
