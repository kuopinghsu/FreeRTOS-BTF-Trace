/**
 * Shared semantic UI tokens and control roles.
 * Lockstep with btf_viewer_pkg/ui_theme.py. Trace-data colors stay elsewhere.
 *
 * `divider` is decorative (no contrast target); `control_border` outlines
 * interactive controls and must reach 3:1 against workspace and surface.
 */

export const UI_THEME = Object.freeze({
  dark: Object.freeze({
    workspace: '#151A22',
    surface: '#1D2430',
    fg: '#E6EDF5',
    fg_dim: '#A6B3C4',
    divider: '#344052',
    control_border: '#6B7C93',
    accent_ui: '#78A9FF',
    on_accent: '#0B1220',
    warning: '#E67E22',
    success: '#7DCEA0',
    focus: '#78A9FF',
    destructive: '#FF8585',
    ctrl_h: 28,
    radius_ctrl: 6,
    radius_card: 8,
    sp_1: 4,
    sp_2: 8,
    sp_3: 12,
    sp_4: 16,
  }),
  light: Object.freeze({
    workspace: '#F5F7FA',
    surface: '#FFFFFF',
    fg: '#182230',
    fg_dim: '#526173',
    divider: '#DCE3EC',
    control_border: '#7A8799',
    accent_ui: '#2563EB',
    on_accent: '#FFFFFF',
    warning: '#9A4D00',
    success: '#166534',
    focus: '#2563EB',
    destructive: '#B3261E',
    ctrl_h: 28,
    radius_ctrl: 6,
    radius_card: 8,
    sp_1: 4,
    sp_2: 8,
    sp_3: 12,
    sp_4: 16,
  }),
})

export const BUTTON_ROLES = Object.freeze(['primary', 'secondary', 'quiet', 'destructive'])

export const REPORT_EXPAND_TABS = Object.freeze(['stats', 'ai'])
export const REPORT_EXPAND_FRACTION = 0.82
export const REPORT_EXPAND_MIN_TIMELINE = 240
export const REPORT_EXPAND_MIN_REPORT = 180

export const TEXT_CONTRAST_MIN = 4.5
export const UI_CONTRAST_MIN = 3.0

export function uiThemeTokens(isDark) {
  return { ...(isDark ? UI_THEME.dark : UI_THEME.light) }
}

function relativeLuminance(hex) {
  const h = String(hex).replace('#', '')
  const lin = [0, 2, 4].map((i) => {
    const c = parseInt(h.slice(i, i + 2), 16) / 255
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  })
  return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]
}

/** WCAG 2.x contrast ratio between two `#RRGGBB` colors. */
export function contrastRatio(a, b) {
  const [hi, lo] = [relativeLuminance(a), relativeLuminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

export function reportExpandAllowed(tab) {
  return REPORT_EXPAND_TABS.includes(tab)
}

/**
 * Report width in expanded mode: ~82% of the workspace, but always leaving the
 * timeline REPORT_EXPAND_MIN_TIMELINE px, never below the panel minimum, and
 * never narrower than the report already is (`current`).
 */
export function expandedReportWidth(
  availablePx,
  fraction = REPORT_EXPAND_FRACTION,
  minReport = REPORT_EXPAND_MIN_REPORT,
  current = 0,
) {
  const avail = Math.max(0, Math.floor(Number(availablePx) || 0))
  const wanted = Math.min(Math.floor(avail * fraction), avail - REPORT_EXPAND_MIN_TIMELINE)
  return Math.max(minReport, wanted, Math.floor(Number(current) || 0))
}

export const STATUS_CUES = Object.freeze({ error: '✖', warning: '⚠', success: '✓', info: '' })

/**
 * Prefix a status line with a severity glyph so meaning never depends on
 * color alone. Idempotent; info lines stay quiet.
 */
export function statusCueText(msg, severity = 'info') {
  const text = String(msg || '')
  const cue = STATUS_CUES[severity] || ''
  if (!text || !cue || text.startsWith(cue)) return text
  return `${cue} ${text}`
}

/** Header button state for the report expand / restore / return cycle. */
export function reportExpandButton(expanded, returnPending = false) {
  if (expanded) {
    return { label: 'Restore layout', tooltip: 'Restore the previous panel width' }
  }
  if (returnPending) {
    return { label: 'Back to report', tooltip: 'Re-expand the report you were reading' }
  }
  return { label: 'Expand report', tooltip: 'Give the report most of the workspace' }
}
