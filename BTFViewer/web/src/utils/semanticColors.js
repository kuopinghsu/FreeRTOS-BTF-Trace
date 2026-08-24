/**
 * Semantic vs data color roles (Step 3).
 * Lockstep with btf_viewer_pkg/semantic_colors.py.
 *
 * Data colors: task/core identity, heatmaps, series distinction.
 * Semantic colors: regression, warning, improvement, selection/focus.
 */

export const SEMANTIC_ROLES = Object.freeze({
  error: 'error',
  warning: 'warning',
  improvement: 'improvement',
  focus: 'focus',
  selection: 'selection',
})

/** CSS variable names (defined on .app in App.vue). */
export const SEMANTIC_CSS_VARS = Object.freeze({
  error: '--semantic-error',
  warning: '--semantic-warning',
  improvement: '--semantic-improvement',
  focus: '--semantic-focus',
  selection: '--semantic-selection',
})

/** Compare / regression chart colors — distinct from task palette. */
export const COMPARE_SEMANTIC = Object.freeze({
  regressed: '#e74c3c',
  improved: '#27ae60',
  neutral: '#95a5a6',
  focus: '#4F8BFF',
})

/** Icon/text reinforcement for colorblind-safe mode.
 *  Regressed (worse / higher latency) uses ↑; Improved uses ↓. */
export const SEMANTIC_GLYPHS = Object.freeze({
  error: '✕',
  warning: '⚠',
  improvement: '↓',
  improved: '↓',
  regressed: '↑',
})

/**
 * @param {'error'|'warning'|'improvement'|'focus'|'selection'|'improved'|'regressed'} role
 * @returns {string}
 */
export function semanticCssVar(role) {
  if (role === 'improved') return SEMANTIC_CSS_VARS.improvement
  if (role === 'regressed') return SEMANTIC_CSS_VARS.error
  return SEMANTIC_CSS_VARS[role] || SEMANTIC_CSS_VARS.focus
}

/** Label with optional glyph when colorblind mode is active. */
export function semanticLabel(text, role, colorblind = false) {
  const glyph = SEMANTIC_GLYPHS[role]
  if (colorblind && glyph) return `${glyph} ${text}`
  return text
}

/** Prefix a signed delta / status cell for colorblind-safe Compare tables. */
export function formatSemanticDelta(text, status, colorblind = false) {
  const s = String(status || '').toLowerCase()
  if (s === 'improved' || s === 'improvement') {
    return semanticLabel(text, 'improved', colorblind)
  }
  if (s === 'regressed' || s === 'error') {
    return semanticLabel(text, 'regressed', colorblind)
  }
  if (s === 'warning' || s === 'warn') {
    return semanticLabel(text, 'warning', colorblind)
  }
  return text
}
