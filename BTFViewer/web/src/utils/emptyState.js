/**
 * Empty-state messages (Step 3).
 * Lockstep with btf_viewer_pkg/empty_state.py.
 *
 * Wording is aligned with disabled-state / command-palette prerequisite text.
 */

export const EMPTY_STATES = Object.freeze({
  noTrace: {
    message: 'Open a BTF trace to begin.',
    action: 'open',
  },
  noStats: {
    message: 'Open a trace file to view statistics.',
    action: 'open',
  },
  noCursors: {
    message: 'Place two cursors to measure a range.',
    action: null,
  },
  noCompare: {
    message: 'Open at least two traces to compare.',
    action: 'open',
  },
  noFindQuery: {
    message: 'Enter a task name, annotation, or migration to search.',
    action: null,
  },
  noFindHits: {
    message: 'No matches in the current Scope.',
    action: null,
  },
  noMarks: {
    message: 'No bookmarks or annotations yet.',
    hint: 'Double-click the Timeline or press B / A to add one.',
    action: null,
  },
  noAi: {
    message: 'Ask about evidence already found in Statistics or the Timeline.',
    action: null,
  },
  noAiConfig: {
    message: 'Configure an AI provider in Settings to enable investigation.',
    action: 'settings',
  },
  noMigration: {
    message: 'No migrations in the current Scope.',
    hint: 'Switch to Core View or widen Scope with cursors.',
    action: null,
  },
  noHeatmap: {
    message: 'No on-CPU slices in the current Scope.',
    action: null,
  },
  noTimeline: {
    message: 'Open a .btf file to begin.',
    action: 'open',
  },
  stats_scoped_empty: {
    message: 'No data in the current cursor range.',
    hint: 'Turn off Limit to C1–Cn or widen the cursors.',
    action: 'clear_scope',
  },
  stats_needs_sti: {
    message: 'No samples — this metric needs STI instrumentation '
      + '(task resume Name[id] / create→first-run).',
    action: null,
  },
  stats_needs_multicore: {
    message: 'No tasks ran on multiple cores.',
    hint: 'Migrations require multi-core activity in the trace.',
    action: null,
  },
  stats_filtered_empty: {
    message: 'No rows match the current Filter.',
    hint: 'Clear the Filter to show all tasks.',
    action: 'clear_filter',
  },
})

/**
 * @param {keyof typeof EMPTY_STATES|string} key
 * @returns {{ message: string, hint: string|null, action: string|null }}
 */
export function emptyStateParts(key) {
  const s = EMPTY_STATES[key]
  if (!s) return { message: '', hint: null, action: null }
  return {
    message: String(s.message || ''),
    hint: s.hint ? String(s.hint) : null,
    action: s.action ?? null,
  }
}

/**
 * @param {keyof typeof EMPTY_STATES} key
 * @returns {string}
 */
export function emptyStateMessage(key) {
  const s = EMPTY_STATES[key]
  if (!s) return ''
  if (s.hint) return `${s.message} ${s.hint}`
  return s.message
}

/** Optional action id for empty-state chips (open, settings, clear_scope, clear_filter). */
export function emptyStateAction(key) {
  return EMPTY_STATES[key]?.action ?? null
}
