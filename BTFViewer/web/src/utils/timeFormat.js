/**
 * Trace timestamp formatting (shared by renderer, stats, and analysis helpers).
 */

/** Nanoseconds per one unit of the given trace timeScale. */
export const NS_PER_UNIT = Object.freeze({ ns: 1, us: 1e3, ms: 1e6, s: 1e9 })

/** Desktop `_TIME_TIERS`: (threshold_ns, divisor, unit label). */
const TIME_TIERS = [
  [1e9, 1e9, 's'],
  [1e6, 1e6, 'ms'],
  [1e3, 1e3, 'µs'],
  [0, 1, 'ns'],
]

/** Convert a value in trace-native units to nanoseconds. */
export function traceUnitsToNs(value, scale = 'ns') {
  const per = NS_PER_UNIT[scale] ?? 1
  return Number(value) * per
}

/** Convert nanoseconds to the trace's native timeScale unit. */
export function nsToTraceUnits(ns, scale = 'ns') {
  const per = NS_PER_UNIT[scale] ?? 1
  return Number(ns) / per
}

/**
 * @param {number} t       Timestamp in trace time-scale units.
 * @param {string} scale   Trace timeScale string (e.g. 'ns', 'us', 'ms').
 * @param {number} [decimals=3]
 * @returns {string}
 */
export function formatTime(t, scale, decimals = 3) {
  // Base unit (no auto-scaling needed): print whole values as-is, but round
  // fractional ones to `decimals` places — otherwise raw floats (e.g. hover-time
  // pixel-to-time conversions) leak binary-fp noise like "0.30000000000000004".
  const base = (v, unit) => `${Number.isInteger(v) ? v : v.toFixed(decimals)} ${unit}`
  if (scale === 'ns') {
    if (t >= 1e9) return `${(t / 1e9).toFixed(decimals)} s`
    if (t >= 1e6) return `${(t / 1e6).toFixed(decimals)} ms`
    if (t >= 1e3) return `${(t / 1e3).toFixed(decimals)} µs`
    return base(t, 'ns')
  }
  if (scale === 'us') {
    if (t >= 1e6) return `${(t / 1e6).toFixed(decimals)} s`
    if (t >= 1e3) return `${(t / 1e3).toFixed(decimals)} ms`
    return base(t, 'µs')
  }
  if (scale === 'ms') {
    if (t >= 1e3) return `${(t / 1e3).toFixed(decimals)} s`
    return base(t, 'ms')
  }
  return `${t} ${scale}`
}

/**
 * Desktop `_format_time` parity: always use fixed decimals (e.g. "2.000 µs").
 * Prefer this for deadline / budget displays that must match the desktop tables.
 */
export function formatTimeFixed(t, scale, decimals = 3) {
  const ns = traceUnitsToNs(t, scale)
  const fmt = (v) => Number(v).toFixed(decimals)
  if (ns >= 1e9) return `${fmt(ns / 1e9)} s`
  if (ns >= 1e6) return `${fmt(ns / 1e6)} ms`
  if (ns >= 1e3) return `${fmt(ns / 1e3)} µs`
  return `${fmt(ns)} ns`
}

/** Like formatTimeFixed but drops trailing zeros (``19 µs``, not ``19.000 µs``). */
export function formatTimeTrim(t, scale) {
  const text = formatTimeFixed(t, scale, 3)
  const parts = text.split(' ')
  if (parts.length < 2) return text
  const unit = parts[parts.length - 1]
  const num = parts.slice(0, -1).join(' ')
  if (!num.includes('.')) return text
  const [whole, fracRaw = ''] = num.split('.')
  const frac = fracRaw.replace(/0+$/, '')
  if (!frac) return `${whole} ${unit}`
  return `${whole}.${frac} ${unit}`
}

/** Format migration gap columns in native trace units (Core Migrations table).
 * Truncates to an integer native-unit value before formatting, matching the
 * desktop app's `_format_time(int(avg), scale)` (parity for Core Migrations /
 * Core-Pair Migration Summary average gap columns). */
export function formatMigrationGapTime(t, scale) {
  const v = Number(t)
  if (!Number.isFinite(v)) return '-'
  return formatTime(Math.trunc(v), scale)
}

/**
 * Desktop `_format_timescale_per_px`: auto-scaled `xx.x unit/px`.
 * @param {number} timescalePerPx  Trace-native time units per screen pixel.
 * @param {string} [timeScale='ns']
 */
export function formatTimescalePerPx(timescalePerPx, timeScale = 'ns') {
  const ns = traceUnitsToNs(timescalePerPx, timeScale)
  if (!Number.isFinite(ns) || ns < 0) return '—'
  for (const [threshold, divisor, label] of TIME_TIERS) {
    if (ns >= threshold) return `${(ns / divisor).toFixed(1)} ${label}/px`
  }
  return `${ns.toFixed(1)} ns/px`
}

/**
 * Status-bar zoom read-out (desktop `_zoom_scale_label` + `_zoom_visible_label`).
 * @param {{ timeStart?: number, timeEnd?: number, canvasW?: number, canvasH?: number }|null} vp
 * @param {string} [timeScale='ns']
 * @param {string} [orientation='h']
 */
export function zoomStatusFromViewport(vp, timeScale = 'ns', orientation = 'h') {
  const span = Number(vp?.timeEnd) - Number(vp?.timeStart)
  const axisPx = orientation === 'v' ? Number(vp?.canvasH) : Number(vp?.canvasW)
  if (!Number.isFinite(span) || span <= 0 || !Number.isFinite(axisPx) || axisPx <= 1) {
    return { scale: '—', visible: '', title: 'Current zoom level (time per pixel)' }
  }
  const scale = formatTimescalePerPx(span / axisPx, timeScale)
  const vis = formatTime(span, timeScale, 1)
  return {
    scale,
    visible: `·  ${vis} visible`,
    title: `Zoom: ${scale}\nVisible: ${vis}`,
  }
}
