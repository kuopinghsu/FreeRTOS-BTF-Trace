/**
 * Trace timestamp formatting (shared by renderer, stats, and analysis helpers).
 */

/**
 * @param {number} t       Timestamp in trace time-scale units.
 * @param {string} scale   Trace timeScale string (e.g. 'ns', 'us', 'ms').
 * @param {number} [decimals=3]
 * @returns {string}
 */
export function formatTime(t, scale, decimals = 3) {
  if (scale === 'ns') {
    if (t >= 1e9) return `${(t / 1e9).toFixed(decimals)} s`
    if (t >= 1e6) return `${(t / 1e6).toFixed(decimals)} ms`
    if (t >= 1e3) return `${(t / 1e3).toFixed(decimals)} µs`
    return `${t} ns`
  }
  if (scale === 'us') {
    if (t >= 1e6) return `${(t / 1e6).toFixed(decimals)} s`
    if (t >= 1e3) return `${(t / 1e3).toFixed(decimals)} ms`
    return `${t} µs`
  }
  if (scale === 'ms') {
    if (t >= 1e3) return `${(t / 1e3).toFixed(decimals)} s`
    return `${t} ms`
  }
  return `${t} ${scale}`
}

/** Format migration gap columns in native trace units (Core Migrations table). */
export function formatMigrationGapTime(t, scale) {
  const v = Number(t)
  if (!Number.isFinite(v)) return '-'
  if (scale === 'ms') return `${v.toFixed(3)} ms`
  if (scale === 'us') return `${Math.round(v)} us`
  return formatTime(v, scale)
}
