/**
 * Guided first review checklist.
 * Keep in sync with btf_viewer_pkg/guided_investigation.py.
 */

export const GUIDED_REVIEW_STEPS = [
  { id: 'quality', label: 'Quality', detail: 'Review trace-quality warnings and limitations.' },
  { id: 'overview', label: 'Overview', detail: 'Check trace span, tasks, cores, and Full Trace overview.' },
  { id: 'symptom', label: 'Symptom', detail: 'Pick a symptom or open Analysis Findings.' },
  { id: 'scope', label: 'Scope', detail: 'Place cursors and enable Limit to C1–Cn when needed.' },
  { id: 'statistics', label: 'Statistics', detail: 'Read Count, Avg, p95, p99, and Max for the scoped window.' },
  { id: 'timeline', label: 'Timeline evidence', detail: 'Use Show on timeline to verify supporting events.' },
  { id: 'ai', label: 'AI', detail: 'Investigate or verify using the same Scope.' },
  { id: 'result', label: 'Result', detail: 'Export HTML or save your case notes.' },
]

export function defaultGuidedProgress() {
  return {
    active: false,
    dismissed: false,
    step_index: 0,
    completed: [],
    trace_key: '',
  }
}

export function guidedStep(index) {
  const i = Number(index)
  if (i >= 0 && i < GUIDED_REVIEW_STEPS.length) return { ...GUIDED_REVIEW_STEPS[i] }
  return null
}

export function advanceGuidedProgress(progress, stepId) {
  const out = { ...(progress || defaultGuidedProgress()) }
  const sid = String(stepId || '').trim()
  const done = [...(out.completed || [])]
  if (sid && !done.includes(sid)) done.push(sid)
  out.completed = done
  const idx = GUIDED_REVIEW_STEPS.findIndex(s => s.id === sid)
  if (idx >= 0) out.step_index = Math.min(GUIDED_REVIEW_STEPS.length - 1, idx + 1)
  return out
}

export function formatGuidedChecklist(progress = null) {
  const done = new Set((progress || {}).completed || [])
  const lines = ['Start first review']
  for (const step of GUIDED_REVIEW_STEPS) {
    const mark = done.has(step.id) ? '✓' : '○'
    lines.push(`${mark} ${step.label} — ${step.detail}`)
  }
  return lines.join('\n')
}
