/** BTF header metadata helpers (shared semantics with desktop parser). */

export const META_KEY_RE = /^[\w.-]+$/
export const SUPPORTED_BTF_VERSION_MAJOR = 2

/** @returns {string|null} warning message, or null if ok / absent */
export function checkBtfVersion(meta) {
  const v = meta?.version
  if (!v) return null
  const major = Number.parseInt(String(v).split('.')[0], 10)
  if (!Number.isFinite(major) || major !== SUPPORTED_BTF_VERSION_MAJOR) {
    return `Unsupported BTF format version: ${v} (expected 2.x)`
  }
  return null
}

export function applyBtfVersionWarning(meta) {
  if (!meta || typeof meta !== 'object') return
  const warn = checkBtfVersion(meta)
  if (warn) meta._versionWarning = warn
}
