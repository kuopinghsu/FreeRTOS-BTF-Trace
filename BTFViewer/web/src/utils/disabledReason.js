/**
 * Disabled-state prerequisite checks (Step 3).
 * Lockstep with btf_viewer_pkg/disabled_reason.py.
 *
 * Aligns toolbar, menus, and command-palette unavailable messaging.
 */

export const DISABLED_REASONS = Object.freeze({
  noTrace: 'Open a trace first',
  twoTraces: 'Open at least two traces',
  cursors2: 'Place at least two cursors (C1–Cn)',
  aiConfig: 'Configure an AI provider in Settings',
  smpOnly: 'Requires a multi-core trace',
  noEvidence: 'No Timeline Evidence for this finding',
  unavailable: 'Unavailable',
})

/**
 * @typedef {Object} PrerequisiteContext
 * @property {boolean} [hasTrace]
 * @property {number} [traceCount]
 * @property {number} [cursorCount]
 * @property {boolean} [isMultiCore]
 * @property {boolean} [aiConfigured]
 */

/**
 * Evaluate a prerequisite token (matches COMMAND_PALETTE_META.requires).
 * @param {string} requires
 * @param {PrerequisiteContext} ctx
 * @param {string} [fallback]
 * @returns {[boolean, string]}
 */
export function checkPrerequisite(requires, ctx, fallback = '') {
  const req = String(requires || 'none')
  if (!req || req === 'none') return [true, '']
  if (req === 'trace') {
    return ctx.hasTrace
      ? [true, '']
      : [false, fallback || DISABLED_REASONS.noTrace]
  }
  if (req === 'two_traces') {
    return (ctx.traceCount ?? 0) >= 2
      ? [true, '']
      : [false, fallback || DISABLED_REASONS.twoTraces]
  }
  if (req === 'cursors2') {
    return (ctx.cursorCount ?? 0) >= 2
      ? [true, '']
      : [false, fallback || DISABLED_REASONS.cursors2]
  }
  if (req === 'ai_config') {
    return ctx.aiConfigured
      ? [true, '']
      : [false, fallback || DISABLED_REASONS.aiConfig]
  }
  if (req === 'smp') {
    return ctx.isMultiCore
      ? [true, '']
      : [false, fallback || DISABLED_REASONS.smpOnly]
  }
  return [true, '']
}

/** Build a prerequisite context from common app refs. */
export function buildPrerequisiteContext({
  trace = null,
  compareTabCount = 0,
  cursorCount = 0,
  aiConfigured = true,
} = {}) {
  const cores = trace?.meta?.cores?.length ?? trace?.cores?.length ?? 0
  return {
    hasTrace: !!trace,
    traceCount: compareTabCount,
    cursorCount,
    isMultiCore: cores > 1,
    aiConfigured,
  }
}
