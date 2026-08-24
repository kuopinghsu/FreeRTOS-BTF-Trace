/**
 * Loading-state UX (Step 3).
 * Lockstep with btf_viewer_pkg/loading_state.py.
 *
 * Maps implementation-oriented parser progress to user-facing stages and
 * avoids fake percentage precision in the load overlay.
 */

export const LOADING_STAGES = Object.freeze({
  reading: 'Reading trace…',
  parsing: 'Parsing events…',
  building: 'Building Timeline…',
  computing: 'Computing Statistics…',
  opening: 'Opening trace…',
  restoring: 'Restoring session…',
  demo: 'Loading demo trace…',
})

/** Internal parser / worker message patterns → stage key. Order matters. */
const INTERNAL_STAGE_RULES = [
  [/reading file/i, 'reading'],
  [/restoring session/i, 'restoring'],
  [/demo trace/i, 'demo'],
  [/packing trace|opening trace/i, 'opening'],
  [/preparing statistics|computing statistics/i, 'computing'],
  [/building scene|building legend|building task lod|building core lod|per-task core lod|finalising segment|building sti/i, 'building'],
  [/reconstruct|lookup|index|sort|pair|tag channel|finalis|cul|analys|sti channel|tick health/i, 'parsing'],
]

/**
 * Resolve a canonical loading stage key from an internal progress message.
 * @param {string} [internalMsg]
 * @returns {keyof typeof LOADING_STAGES}
 */
export function resolveLoadingStage(internalMsg) {
  const msg = String(internalMsg || '').trim()
  if (!msg) return 'reading'
  for (const [re, stage] of INTERNAL_STAGE_RULES) {
    if (re.test(msg)) return stage
  }
  return 'parsing'
}

/**
 * User-facing stage label for the load overlay / toolbar badge.
 * @param {string} [internalMsg]
 * @returns {string}
 */
export function formatLoadingMessage(internalMsg) {
  const stage = resolveLoadingStage(internalMsg)
  return LOADING_STAGES[stage] || LOADING_STAGES.parsing
}

/**
 * Display percentage — rounded to 5% steps; empty when unknown/zero.
 * @param {number} pct
 * @returns {string}
 */
export function formatLoadingPct(pct) {
  const n = Number(pct)
  if (!Number.isFinite(n) || n <= 0) return ''
  if (n >= 100) return '100'
  const rounded = Math.round(n / 5) * 5
  return String(Math.max(5, Math.min(99, rounded)))
}

/** Whether the current load phase supports user cancellation. */
export function isLoadingCancellable(phase) {
  return phase === 'parse' || phase === 'read'
}

/**
 * Normalize a progress callback payload for UI binding.
 * @param {number} pct
 * @param {string} [internalMsg]
 * @returns {{ pct: number, msg: string, pctLabel: string, cancellable: boolean }}
 */
export function normalizeLoadingProgress(pct, internalMsg, phase = 'parse') {
  return {
    pct: Number(pct) || 0,
    msg: formatLoadingMessage(internalMsg),
    pctLabel: formatLoadingPct(pct),
    cancellable: isLoadingCancellable(phase),
  }
}
