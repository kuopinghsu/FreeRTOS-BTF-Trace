/**
 * Shared logic for the unified Export dialog (workspace · Perfetto · BTF slice).
 * Pure helpers so the dialog + App.vue stay thin and this stays unit-tested.
 */

export const EXPORT_TARGETS = ['workspace', 'perfetto', 'btf-slice']

export const EXPORT_TARGET_LABELS = {
  workspace: 'Portable workspace (.btfw)',
  perfetto: 'Perfetto / Chrome Trace JSON',
  'btf-slice': 'Cursor-range BTF file',
}

// Single-line so the desktop dialog (mainwindow._EXPORT_TARGET_HINTS) can carry
// byte-identical strings — see tests/test_export_dialog_parity.py.
export const EXPORT_TARGET_HINTS = {
  workspace: 'Trace + view state + analysis findings + trace health + investigation notebook + a rendered HTML report, in one ZIP-compatible file.',
  perfetto: 'Open in https://ui.perfetto.dev — full loaded trace or the current viewport.',
  'btf-slice': 'A .btf containing only the events between the earliest and latest cursors.',
}

// Trailing trace / archive suffix — lockstep with mainwindow._EXPORT_BASENAME_RE.
export const EXPORT_BASENAME_RE = /\.(btf\.gz|btf\.bz2|btf\.zip|btf|btfw|json|gz|bz2|zip)$/i

/** `example-8cores.btf.gz` → `example-8cores` so a new extension can be appended. */
export function exportBaseName(name, fallback = 'trace') {
  const s = String(name || '').trim()
  if (!s) return fallback
  return s.replace(EXPORT_BASENAME_RE, '') || fallback
}

export function perfettoFilename(name) {
  return `${exportBaseName(name, 'trace')}.json`
}

export function workspaceFilename(name) {
  return `${exportBaseName(name, 'workspace')}.btfw`
}

export function btfSliceFilename(name, lo, hi) {
  return `${exportBaseName(name, 'selection')}_${lo}-${hi}.btf`
}

/**
 * [lo, hi) for the cursor-range slice from placed cursor timestamps.
 * @returns {{lo:number, hi:number} | null}
 */
export function cursorRange(placedCursors) {
  const nums = (placedCursors || []).map(Number).filter(Number.isFinite)
  if (nums.length < 2) return null
  const lo = Math.min(...nums)
  const hi = Math.max(...nums)
  return hi > lo ? { lo, hi } : null
}

/**
 * Availability of each export target for the current state.
 * @param {{ hasTrace:boolean, placedCursorCount:number }} state
 * @returns {{ id:string, label:string, hint:string, available:boolean, reason:string }[]}
 */
export function exportTargets({ hasTrace = false, placedCursorCount = 0 } = {}) {
  return EXPORT_TARGETS.map((id) => {
    let available = hasTrace
    let reason = hasTrace ? '' : 'Open a trace first.'
    if (available && id === 'btf-slice' && placedCursorCount < 2) {
      available = false
      reason = 'Place at least two cursors (C1–Cn) to mark the range.'
    }
    return {
      id,
      label: EXPORT_TARGET_LABELS[id],
      hint: EXPORT_TARGET_HINTS[id],
      available,
      reason,
    }
  })
}

/** First available target id, preferring `preferred` when it is available. */
export function defaultExportTarget(targets, preferred = 'workspace') {
  const rows = targets || []
  const pick = rows.find((t) => t.id === preferred && t.available)
  if (pick) return pick.id
  const firstOk = rows.find((t) => t.available)
  return firstOk ? firstOk.id : (rows[0]?.id ?? 'workspace')
}
