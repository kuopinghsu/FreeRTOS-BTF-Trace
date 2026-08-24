/**
 * Numeric presentation helpers (Step 3).
 * Lockstep with btf_viewer_pkg/numeric_format.py.
 *
 * Consistent percentile / duration formatting for Statistics tables and reports.
 */
import { formatTimeTrim } from './timeFormat.js'

/** Default decimal places for percentile columns. */
export const PERCENTILE_DECIMALS = 3

/**
 * Format p50/p95/p99/Max style duration values.
 * @param {number|null|undefined} value  Native trace units.
 * @param {string} scale  Trace timeScale.
 * @param {string} [kind] p50 | p95 | p99 | max | avg
 */
export function formatPercentile(value, scale, kind = '') {
  const v = Number(value)
  if (!Number.isFinite(v)) return '—'
  const k = String(kind || '').toLowerCase()
  if (k === 'max') return formatTimeTrim(v, scale)
  return formatTimeTrim(v, scale)
}

/** Right-align CSS class token for numeric table cells. */
export const NUMERIC_CELL_CLASS = 'num-cell'

/** Format a plain ratio as percentage with one decimal. */
export function formatRatioPct(ratio) {
  const v = Number(ratio)
  if (!Number.isFinite(v)) return '—'
  return `${(v * 100).toFixed(1)}%`
}

/** Format CPU utilisation 0–100 with consistent precision. */
export function formatCpuPct(pct) {
  const v = Number(pct)
  if (!Number.isFinite(v)) return '—'
  if (v >= 99.95) return '100%'
  if (v < 0.05 && v > 0) return '<0.1%'
  return `${v.toFixed(1)}%`
}

/**
 * Build an HTML table cell with numeric alignment.
 * @param {string} text
 * @param {string} [title]
 */
export function numericCellHtml(text, title = '') {
  const t = title ? ` title="${String(title).replace(/"/g, '&quot;')}"` : ''
  return `<td class="${NUMERIC_CELL_CLASS}"${t}>${text}</td>`
}

/**
 * Compare-friendly signed delta (Compare regression/improvement columns).
 * @param {number} delta  Native units; positive = regressed (worse).
 * @param {string} scale
 */
export function formatSignedDelta(delta, scale) {
  const v = Number(delta)
  if (!Number.isFinite(v) || v === 0) return '—'
  const sign = v > 0 ? '+' : '−'
  return `${sign}${formatTimeTrim(Math.abs(v), scale)}`
}
