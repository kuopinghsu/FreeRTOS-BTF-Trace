/**
 * Evidence round-trip navigation (UX-107).
 * Keep in sync with btf_viewer_pkg/evidence_history.py.
 */

export const SHOW_ON_TIMELINE_LABEL = 'Show on timeline'

export function emptyEvidenceHistory() {
  return { entries: [], index: -1 }
}

export function pushEvidenceEntry(history, entry) {
  const out = { ...(history || emptyEvidenceHistory()) }
  let entries = [...(out.entries || [])]
  let idx = Number(out.index ?? -1)
  if (idx >= 0 && idx < entries.length - 1) entries = entries.slice(0, idx + 1)
  entries.push({ ...entry })
  out.entries = entries
  out.index = entries.length - 1
  return out
}

export function evidenceNavState(history) {
  const out = { ...(history || emptyEvidenceHistory()) }
  const entries = out.entries || []
  const idx = Number(out.index ?? -1)
  return {
    can_back: idx > 0,
    can_forward: idx >= 0 && idx < entries.length - 1,
    current: idx >= 0 && idx < entries.length ? entries[idx] : null,
    count: entries.length,
  }
}

export function stepEvidenceHistory(history, direction) {
  const out = { ...(history || emptyEvidenceHistory()) }
  const entries = out.entries || []
  let idx = Number(out.index ?? -1)
  const step = Number(direction) < 0 ? -1 : 1
  idx = Math.max(-1, Math.min(entries.length - 1, idx + step))
  out.index = idx
  out.entries = entries
  return out
}

export function formatEvidenceInspector(entry) {
  if (!entry || typeof entry !== 'object') return ''
  const parts = []
  for (const [key, label] of [
    ['task', 'Task'],
    ['core', 'Core'],
    ['event_type', 'Event'],
    ['start', 'Start'],
    ['end', 'End'],
    ['duration', 'Duration'],
    ['source_metric', 'Source'],
    ['time', 'Time'],
  ]) {
    const val = entry[key]
    if (val != null && String(val).trim()) parts.push(`${label}: ${val}`)
  }
  return parts.join(' · ')
}
