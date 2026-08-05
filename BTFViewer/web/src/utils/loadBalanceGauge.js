/**
 * Load Balance gauges — Score and σ side by side (parity with desktop QPainter widget).
 * Score = 100 × (1 − Gini); σ = population stddev of core utilisation %.
 *
 * Zones (aligned with Analysis Findings):
 *   Score red   — score < 70%
 *   Overall amber — score ≥ 70% but σ > 30%
 *   σ amber/red — σ > 30% (amber), σ > 50% (red)
 */

export const LB_SCORE_WARN = 70
export const LB_SIGMA_WARN = 30
export const LB_SIGMA_RED = 50
/** σ gauge full-scale (needle at right). */
export const LB_SIGMA_SCALE = 60

/** Gini coefficient of non-negative values (0 = equality, 1 = max inequality). */
export function giniCoefficient(values) {
  const n = (values || []).length
  if (n < 2) return 0
  const total = values.reduce((a, b) => a + b, 0)
  if (total === 0) return 0
  const sorted = [...values].sort((a, b) => a - b)
  let cumsum = 0
  let giniNum = 0
  for (let i = 0; i < n; i++) {
    cumsum += sorted[i]
    giniNum += cumsum
  }
  return Math.max(0, Math.min(1, (n + 1) / n - (2 * giniNum) / (n * total)))
}

/** Population standard deviation of core utilisation %. */
export function coreUtilStddev(values) {
  const n = (values || []).length
  if (n < 2) return 0
  const mean = values.reduce((a, b) => a + b, 0) / n
  return Math.sqrt(values.reduce((s, v) => s + (v - mean) ** 2, 0) / n)
}

/**
 * Load Balance {score, gini, stddev} for ≥2 non-negative values with a
 * positive total (e.g. per-core utilisation %), else null.
 */
export function loadBalanceMetrics(values) {
  const n = (values || []).length
  if (n < 2) return null
  const total = values.reduce((a, b) => a + b, 0)
  if (total === 0) return null
  const gini = giniCoefficient(values)
  const stddev = coreUtilStddev(values)
  const score = Math.max(0, 100 * (1 - gini))
  return { score, gini, stddev }
}

/** Per-gauge SVG geometry — mirrors desktop stroke 8 / hollow % placement. */
export const LB_GAUGE = Object.freeze({
  viewW: 140,
  viewH: 100,
  cx: 70,
  cy: 78,
  rTrack: 48,
  rBg: 48,
  needleLen: Math.round(48 * 0.68), // ≈ 33 — desktop: r * 0.68
  hubR: 3.5,
  strokeW: 8,
  startDeg: 180,
  sweepDeg: 180,
  /** Value % in the upper hollow of the arc (above needle mid). */
  scoreY: 78 - Math.round(48 * 0.52),
})

/** Combined dual-gauge SVG canvas (HTML export). */
export const LB_DUAL = Object.freeze({
  viewW: 300,
  viewH: 148,
  leftCx: 70,
  rightCx: 230,
  cy: 88,
  r: 48,
  needleLen: Math.round(48 * 0.68),
  strokeW: 8,
})

export const LB_ZONE_COLORS = Object.freeze({
  ok: { accent: '#1a8a2a', fillEnd: '#22C55E', chipBg: '#E8F6EC', chipFg: '#1a8a2a', chipBd: '#5FCF6F' },
  amber: { accent: '#C47F00', fillEnd: '#E0A020', chipBg: '#FFF6E5', chipFg: '#C47F00', chipBd: '#E0A020' },
  red: { accent: '#C62828', fillEnd: '#E53935', chipBg: '#FDECEA', chipFg: '#C62828', chipBd: '#E57373' },
})

/**
 * @param {number} score
 * @param {number} stddev
 * @returns {'ok'|'amber'|'red'}
 */
export function classifyLoadBalance(score, stddev) {
  const s = Number(score) || 0
  const sigma = Number(stddev) || 0
  if (s < LB_SCORE_WARN) return 'red'
  if (sigma > LB_SIGMA_WARN) return 'amber'
  return 'ok'
}

/** Zone for the σ gauge alone. */
export function classifySigma(stddev) {
  const sigma = Number(stddev) || 0
  if (sigma > LB_SIGMA_RED) return 'red'
  if (sigma > LB_SIGMA_WARN) return 'amber'
  return 'ok'
}

/** Map value 0…max → degrees (180° left → 0° right). */
export function valueToNeedleDeg(value, max = 100) {
  const m = Math.max(1e-9, Number(max) || 100)
  const s = Math.max(0, Math.min(m, Number(value) || 0))
  return 180 - (s / m) * 180
}

export function needleTipPoint(
  value,
  max = 100,
  cx = LB_GAUGE.cx,
  cy = LB_GAUGE.cy,
  needleLen = LB_GAUGE.needleLen,
) {
  const rad = (valueToNeedleDeg(value, max) * Math.PI) / 180
  return {
    x: cx + Math.cos(rad) * needleLen,
    y: cy - Math.sin(rad) * needleLen,
  }
}

function polar(cx, cy, r, deg) {
  const rad = (deg * Math.PI) / 180
  return { x: cx + Math.cos(rad) * r, y: cy - Math.sin(rad) * r }
}

export function semicirclePath(cx, cy, r) {
  const s = polar(cx, cy, r, 180)
  const e = polar(cx, cy, r, 0)
  return `M ${s.x.toFixed(2)} ${s.y.toFixed(2)} A ${r} ${r} 0 0 1 ${e.x.toFixed(2)} ${e.y.toFixed(2)}`
}

export function valueArcPath(value, max = 100, cx = LB_GAUGE.cx, cy = LB_GAUGE.cy, r = LB_GAUGE.rTrack) {
  const s = polar(cx, cy, r, 180)
  const endDeg = valueToNeedleDeg(value, max)
  const e = polar(cx, cy, r, endDeg)
  const sweep = 180 - endDeg
  if (sweep < 0.5) return `M ${s.x.toFixed(2)} ${s.y.toFixed(2)}`
  return `M ${s.x.toFixed(2)} ${s.y.toFixed(2)} A ${r} ${r} 0 0 1 ${e.x.toFixed(2)} ${e.y.toFixed(2)}`
}

/** @deprecated use valueArcPath */
export function scoreArcPath(score, cx = LB_GAUGE.cx, cy = LB_GAUGE.cy, r = LB_GAUGE.rTrack) {
  return valueArcPath(score, 100, cx, cy, r)
}

/** @deprecated use valueToNeedleDeg(score, 100) */
export function scoreToNeedleDeg(score) {
  return valueToNeedleDeg(score, 100)
}

function _gaugeSvgBody({
  uid, cx, cy, value, max, zone, title, valueLabel, legend,
  r = LB_DUAL.r, needleLen = LB_DUAL.needleLen, strokeW = LB_DUAL.strokeW,
}) {
  const colors = LB_ZONE_COLORS[zone] || LB_ZONE_COLORS.ok
  const bg = semicirclePath(cx, cy, r)
  const fill = valueArcPath(value, max, cx, cy, r)
  const tip = needleTipPoint(value, max, cx, cy, needleLen)
  const track = '#D8DCE4'
  const fg = '#1A2030'
  const muted = '#6A7388'
  const redFill = zone === 'red'
  const valueY = cy - Math.round(r * 0.28)
  return `
  <defs>
    <linearGradient id="${uid}" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="${redFill ? '#EF5350' : '#3B82F6'}"/>
      <stop offset="55%" stop-color="${redFill ? '#E53935' : '#14B8A6'}"/>
      <stop offset="100%" stop-color="${colors.fillEnd}"/>
    </linearGradient>
  </defs>
  <text x="${cx}" y="18" text-anchor="middle" fill="${fg}" font-family="system-ui,sans-serif" font-size="10" font-weight="600">${title}</text>
  <path d="${bg}" fill="none" stroke="${track}" stroke-width="${strokeW}" stroke-linecap="round"/>
  <path d="${fill}" fill="none" stroke="url(#${uid})" stroke-width="${strokeW}" stroke-linecap="round"/>
  <line x1="${cx}" y1="${cy}" x2="${tip.x.toFixed(2)}" y2="${tip.y.toFixed(2)}" stroke="${fg}" stroke-width="2" stroke-linecap="round"/>
  <circle cx="${cx}" cy="${cy}" r="3.5" fill="#FFFFFF" stroke="${fg}" stroke-width="1.75"/>
  <text x="${cx}" y="${valueY}" text-anchor="middle" fill="${colors.accent}" font-family="system-ui,sans-serif" font-size="12" font-weight="700">${valueLabel}</text>
  <text x="${cx}" y="${cy + 16}" text-anchor="middle" fill="${muted}" font-family="system-ui,sans-serif" font-size="9">${legend}</text>`
}

/**
 * Dual Score + σ gauges in one SVG (panel export / HTML).
 * @param {{ score: number, gini: number, stddev: number, zone?: string }} metrics
 * @param {{ width?: number }} [opts]
 */
export function loadBalanceGaugeSvg(metrics, opts = {}) {
  const score = Math.max(0, Math.min(100, Number(metrics?.score) || 0))
  const gini = Number(metrics?.gini) || 0
  const stddev = Number(metrics?.stddev) || 0
  const scoreZone = score < LB_SCORE_WARN ? 'red' : 'ok'
  const sigmaZone = classifySigma(stddev)
  const overall = metrics?.zone || classifyLoadBalance(score, stddev)
  const width = Math.max(220, Number(opts.width) || 300)
  const d = LB_DUAL
  const h = Math.round(width * d.viewH / d.viewW)
  const uid = `lb${Math.abs(Math.round(score * 17 + stddev * 13))}`
  const sigmaMax = LB_SIGMA_SCALE
  const border = overall === 'red' ? LB_ZONE_COLORS.red.chipBd
    : (overall === 'amber' ? LB_ZONE_COLORS.amber.chipBd : '#E2E5EC')

  const left = _gaugeSvgBody({
    uid: `${uid}S`,
    cx: d.leftCx,
    cy: d.cy,
    value: score,
    max: 100,
    zone: scoreZone,
    title: 'Load Balance Score',
    valueLabel: `${score.toFixed(0)}%`,
    legend: '100 = balanced · 0 = overload',
  })
  const right = _gaugeSvgBody({
    uid: `${uid}D`,
    cx: d.rightCx,
    cy: d.cy,
    value: Math.min(stddev, sigmaMax),
    max: sigmaMax,
    zone: sigmaZone,
    title: 'Std Deviation (σ)',
    valueLabel: `${stddev.toFixed(1)}%`,
    legend: `0–${sigmaMax}% · warn &gt; ${LB_SIGMA_WARN}%`,
  })

  let chip = ''
  if (overall === 'red') {
    chip = `<rect x="210" y="6" width="80" height="16" rx="8" fill="${LB_ZONE_COLORS.red.chipBg}" stroke="${LB_ZONE_COLORS.red.chipBd}"/>
  <text x="250" y="17" text-anchor="middle" fill="${LB_ZONE_COLORS.red.chipFg}" font-family="system-ui,sans-serif" font-size="9" font-weight="700">Unbalanced</text>`
  } else if (overall === 'amber') {
    chip = `<rect x="228" y="6" width="62" height="16" rx="8" fill="${LB_ZONE_COLORS.amber.chipBg}" stroke="${LB_ZONE_COLORS.amber.chipBd}"/>
  <text x="259" y="17" text-anchor="middle" fill="${LB_ZONE_COLORS.amber.chipFg}" font-family="system-ui,sans-serif" font-size="9" font-weight="700">σ &gt; 30%</text>`
  }

  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${d.viewW} ${d.viewH}" width="${width}" height="${h}" role="img" aria-label="Load Balance Score ${score.toFixed(0)} percent, sigma ${stddev.toFixed(1)} percent">
  <rect width="100%" height="100%" rx="8" fill="#F7F8FA" stroke="${border}"/>
  ${left}
  ${right}
  <text x="${d.viewW / 2}" y="${d.viewH - 8}" text-anchor="middle" fill="#6A7388" font-family="ui-monospace,monospace" font-size="9">G=${gini.toFixed(3)} · Score = 100 × (1 − Gini)</text>
  ${chip}
</svg>`
}

/**
 * HTML snippet with dual gauges as an embedded SVG data-URI &lt;img&gt;.
 * @param {{ score: number, gini: number, stddev: number, zone?: string }} metrics
 * @param {{ width?: number }} [opts]
 */
export function loadBalanceGaugeImgHtml(metrics, opts = {}) {
  const width = Math.max(220, Number(opts.width) || 300)
  const svg = loadBalanceGaugeSvg(metrics, { width })
  const score = Math.max(0, Math.min(100, Number(metrics?.score) || 0))
  const stddev = Number(metrics?.stddev) || 0
  const zone = metrics?.zone || classifyLoadBalance(score, stddev)
  const dataUri = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`
  const h = Math.round(width * LB_DUAL.viewH / LB_DUAL.viewW)
  return (
    `<div class="lb-gauge-embed" style="margin:8px 0 12px;">`
    + `<img src="${dataUri}" width="${width}" height="${h}" `
    + `alt="Load Balance Score ${score.toFixed(0)}%, σ=${stddev.toFixed(1)}% (${zone})" `
    + `style="display:block;max-width:100%;height:auto;border:0;"/>`
    + `</div>`
  )
}
