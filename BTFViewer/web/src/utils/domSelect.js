/**
 * Position a fixed listbox under (or above) a trigger rect.
 * Used by DomSelect so option lists stay in the page DOM for tab capture.
 *
 * @param {DOMRectReadOnly | { left: number, top: number, width: number, bottom: number }} rect
 * @param {{ maxHeight?: number, gap?: number, zIndex?: number }} [opts]
 * @returns {Record<string, string>}
 */
export function placeDomSelectList(rect, opts = {}) {
  const maxH = Number(opts.maxHeight) || 280
  const gap = Number(opts.gap) || 2
  const zIndex = Number(opts.zIndex) || 2600
  const vw = typeof window !== 'undefined' ? window.innerWidth : 1024
  const vh = typeof window !== 'undefined' ? window.innerHeight : 768
  const left = Math.max(8, Math.min(Math.round(rect.left), vw - 8))
  const width = Math.round(rect.width)
  const spaceBelow = vh - rect.bottom - 8
  const spaceAbove = rect.top - 8
  const openUp = spaceBelow < 140 && spaceAbove > spaceBelow
  const height = Math.min(maxH, Math.max(openUp ? spaceAbove : spaceBelow, 80))
  if (openUp) {
    return {
      position: 'fixed',
      left: `${left}px`,
      width: `${width}px`,
      bottom: `${Math.round(vh - rect.top + gap)}px`,
      maxHeight: `${Math.round(height)}px`,
      zIndex: String(zIndex),
    }
  }
  return {
    position: 'fixed',
    left: `${left}px`,
    width: `${width}px`,
    top: `${Math.round(rect.bottom + gap)}px`,
    maxHeight: `${Math.round(height)}px`,
    zIndex: String(zIndex),
  }
}

/** @param {unknown} option */
export function normalizeDomSelectOption(option) {
  if (option == null) return null
  if (typeof option === 'string' || typeof option === 'number' || typeof option === 'boolean') {
    const label = String(option)
    return { value: option, label, disabled: false, title: '' }
  }
  if (typeof option === 'object') {
    const value = option.value
    const label = option.label != null ? String(option.label) : String(value ?? '')
    return {
      value,
      label,
      disabled: !!option.disabled,
      title: option.title != null ? String(option.title) : '',
    }
  }
  return null
}

/** @param {unknown[]} options */
export function normalizeDomSelectOptions(options) {
  if (!Array.isArray(options)) return []
  return options.map(normalizeDomSelectOption).filter(Boolean)
}

/** @param {unknown} a @param {unknown} b */
export function domSelectValueEqual(a, b) {
  return a === b
}
