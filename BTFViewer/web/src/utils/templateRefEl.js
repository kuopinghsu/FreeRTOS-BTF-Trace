/**
 * Unwrap a Vue template ref. Refs inside ``v-for`` are arrays, so
 * ``el.getBoundingClientRect`` throws if the caller assumes a single node.
 */
export function templateRefEl(value) {
  const el = Array.isArray(value) ? value.find(Boolean) : value
  return el && typeof el.getBoundingClientRect === 'function' ? el : null
}
