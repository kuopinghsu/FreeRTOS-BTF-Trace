/**
 * Cursor scoping workflow helpers.
 * Keep in sync with btf_viewer_pkg/cursor_scope.py.
 */

export function shouldOfferUseAsScope(cursorTimes, { limitToCursors = false } = {}) {
  const placed = (cursorTimes || []).filter(t => t != null)
  return placed.length >= 2 && !limitToCursors
}

export function formatUseAsScopePrompt(cursorTimes) {
  const placed = [...(cursorTimes || [])].filter(t => t != null).sort((a, b) => a - b)
  if (placed.length < 2) return ''
  return `Use C1–C${placed.length} as analysis Scope`
}

export function multiCursorSpanWarning(cursorTimes) {
  const placed = [...(cursorTimes || [])].filter(t => t != null).sort((a, b) => a - b)
  if (placed.length <= 2) return null
  return `${placed.length} cursors define C1–C${placed.length} as earliest-to-latest span; verify this includes the intended incident only.`
}

export function cursorRangeActions() {
  return [
    { id: 'fit', label: 'Fit range' },
    { id: 'analyze', label: 'Analyze range' },
    { id: 'save_btf', label: 'Save range as BTF' },
    { id: 'clear', label: 'Clear range' },
  ]
}
