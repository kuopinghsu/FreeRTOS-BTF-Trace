/**
 * Toolbar zoom presets (parity with desktop _ZOOM_PRESET_PERCENTAGES).
 * Each percentage is the fraction of the full trace that is visible:
 * Fit = 100%, 50% = half the trace (2× zoom).
 */

export const ZOOM_PRESET_PERCENTAGES = Object.freeze([1, 2, 5, 10, 25, 50, 75])

/**
 * @param {number} fitTpp  Time-per-pixel at Fit (full span / axis pixels)
 * @param {number} minTpp  Zoom-in floor (1:1 density)
 */
export function buildZoomPresetOptions(fitTpp, minTpp) {
  const fit = Number(fitTpp)
  const min = Number(minTpp)
  const options = []
  const skipTiny = Number.isFinite(fit) && fit > 0 && Number.isFinite(min) && min > 0
  for (const pct of ZOOM_PRESET_PERCENTAGES) {
    if (skipTiny && (fit * pct / 100) < min) continue
    options.push({ value: String(pct), label: `${pct}%`, pct })
  }
  options.push({ value: 'fit', label: 'Fit', pct: null })
  return options
}

/** Visible fraction of the trace (1 = Fit). Empty string = no matching slot. */
export function matchZoomPresetValue(visibleFrac, options) {
  if (!Number.isFinite(visibleFrac) || visibleFrac >= 0.99) return 'fit'
  for (const opt of options || []) {
    if (opt.pct == null) continue
    const target = opt.pct / 100
    if (Math.abs(visibleFrac - target) / Math.max(target, 1e-12) < 0.01) return opt.value
  }
  return ''
}
