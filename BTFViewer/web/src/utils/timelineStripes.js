/**
 * Desktop-parity timeline stripe colors (scene._c_row_even / _c_row_odd, …).
 */
export function timelineStripePalette(darkMode) {
  if (darkMode) {
    return {
      even: '#252526',
      odd: '#2D2D2D',
      sti: '#1A1A2E',
      core: '#2A2A3E',
      coreSubEven: '#1E1E2C',
      coreSubOdd: '#232330',
    }
  }
  return {
    even: '#FFFFFF',
    odd: '#F2F2F2',
    sti: '#EEF3F8',
    core: '#E7ECF3',
    coreSubEven: '#F7F9FC',
    coreSubOdd: '#EEF2F7',
  }
}

/**
 * Background fill for a timeline row or vertical column.
 * @param {{ type?: string, stripeIdx?: number }} band
 * @param {boolean} darkMode
 * @param {number} [fallbackIdx]
 */
export function stripeColorForBand(band, darkMode, fallbackIdx = 0) {
  const p = timelineStripePalette(darkMode)
  const i = Number.isFinite(band?.stripeIdx) ? band.stripeIdx : fallbackIdx
  const type = band?.type
  if (type === 'sti' || type === 'interval') return p.sti
  if (type === 'core') return p.core
  if (type === 'core-task') return i % 2 === 0 ? p.coreSubEven : p.coreSubOdd
  return i % 2 === 0 ? p.even : p.odd
}

/** CSS class for label-column / column-header stripe (pairs with App.vue vars). */
export function stripeClassForBand(band, fallbackIdx = 0) {
  const i = Number.isFinite(band?.stripeIdx) ? band.stripeIdx : fallbackIdx
  const type = band?.type
  if (type === 'sti' || type === 'interval') return 'stripe-sti'
  if (type === 'core') return 'stripe-core'
  if (type === 'core-task') return i % 2 === 0 ? 'stripe-core-sub-even' : 'stripe-core-sub-odd'
  return i % 2 === 0 ? 'stripe-even' : 'stripe-odd'
}
