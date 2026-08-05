/**
 * Metric tabs for the statistics distribution-chart dialog.
 *
 * Kept in sync with the desktop `_MIG_PLOT_TABS` / `_PAIR_PLOT_TABS` /
 * `_TAG_PLOT_TABS` in btf_viewer_pkg/stats.py.
 */

export const MIG_PLOT_TABS = [
  { kind: 'mig_dwell', label: 'Dwell' },
  { kind: 'mig_rate', label: 'Rate' },
  { kind: 'mig_gap', label: 'Gap' },
]

export const PAIR_PLOT_TABS = [
  { kind: 'pair_gap', label: 'Gap' },
  { kind: 'pair_rate', label: 'Rate' },
]

export const TAG_PLOT_TABS = [
  { kind: 'tag', label: 'Value' },
  { kind: 'tag_interval', label: 'Interval' },
]

/** Tabs offered for a plot kind, or null when the metric has no variants. */
export function plotTabsForKind(kind) {
  if (!kind) return null
  if (kind.startsWith('mig_')) return MIG_PLOT_TABS
  if (kind.startsWith('pair_')) return PAIR_PLOT_TABS
  if (kind === 'tag' || kind === 'tag_interval') return TAG_PLOT_TABS
  return null
}

/**
 * Resolve a tab click into the next open-plot descriptor.
 *
 * Returns null when the switch must be ignored — already active, or not a tab
 * of the open metric — so the caller keeps the current tab highlighted. Tabs
 * with no samples in scope still switch: the dialog shows its empty state, so
 * the highlight always matches what is on screen.
 */
export function resolvePlotTabSwitch(open, kind) {
  if (!open || !kind || open.kind === kind) return null
  const tabs = plotTabsForKind(open.kind)
  if (!tabs || !tabs.some((t) => t.kind === kind)) return null
  return { ...open, kind }
}
