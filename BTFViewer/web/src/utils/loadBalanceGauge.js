/**
 * Load Balance Score gauge — clean geometry + zone alerts + SVG export.
 * Score = 100 × (1 − Gini).
 *
 * Zones (aligned with Analysis Findings):
 *   red   — score < 70%  (unbalanced / red zone)
 *   amber — score ≥ 70% but σ > 30%
 *   ok    — score ≥ 70% and σ ≤ 30%
 */

export const LB_SCORE_WARN = 70
export const LB_SIGMA_WARN = 30

export const LB_GAUGE = Object.freeze({
  viewW: 280,
  viewH: 168,
  cx: 140,
  cy: 118,
  rTrack: 78,
  rBg: 78,
  needleLen: 52,
  startDeg: 180,
  sweepDeg: 180,
  scoreY: 78,
  labelY: 96,
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

/** Map score 0–100 → degrees (180° left → 0° right). */
export function scoreToNeedleDeg(score) {
  const s = Math.max(0, Math.min(100, Number(score) || 0))
  return LB_GAUGE.startDeg - (s / 100) * LB_GAUGE.sweepDeg
}

export function needleTipPoint(score, g = LB_GAUGE) {
  const rad = (scoreToNeedleDeg(score) * Math.PI) / 180
  return {
    x: g.cx + Math.cos(rad) * g.needleLen,
    y: g.cy - Math.sin(rad) * g.needleLen,
  }
}

function polar(cx, cy, r, deg) {
  const rad = (deg * Math.PI) / 180
  return { x: cx + Math.cos(rad) * r, y: cy - Math.sin(rad) * r }
}

/** Semicircle path left → right through the top. */
export function semicirclePath(cx, cy, r) {
  const s = polar(cx, cy, r, 180)
  const e = polar(cx, cy, r, 0)
  return `M ${s.x.toFixed(2)} ${s.y.toFixed(2)} A ${r} ${r} 0 0 1 ${e.x.toFixed(2)} ${e.y.toFixed(2)}`
}

/** Arc from 180° to the score angle (progress fill). */
export function scoreArcPath(score, cx = LB_GAUGE.cx, cy = LB_GAUGE.cy, r = LB_GAUGE.rTrack) {
  const s = polar(cx, cy, r, 180)
  const endDeg = scoreToNeedleDeg(score)
  const e = polar(cx, cy, r, endDeg)
  const sweep = 180 - endDeg
  if (sweep < 0.5) return `M ${s.x.toFixed(2)} ${s.y.toFixed(2)}`
  const large = sweep > 180 ? 1 : 0
  return `M ${s.x.toFixed(2)} ${s.y.toFixed(2)} A ${r} ${r} 0 ${large} 1 ${e.x.toFixed(2)} ${e.y.toFixed(2)}`
}

/**
 * Compact SVG for HTML export (light, print-friendly).
 * @param {{ score: number, gini: number, stddev: number, amber?: boolean, zone?: string }} metrics
 * @param {{ width?: number }} [opts]
 */
export function loadBalanceGaugeSvg(metrics, opts = {}) {
  const score = Math.max(0, Math.min(100, Number(metrics?.score) || 0))
  const gini = Number(metrics?.gini) || 0
  const stddev = Number(metrics?.stddev) || 0
  const zone = metrics?.zone || classifyLoadBalance(score, stddev)
  const colors = LB_ZONE_COLORS[zone] || LB_ZONE_COLORS.ok
  const width = Math.max(200, Number(opts.width) || 280)
  const g = LB_GAUGE
  const h = Math.round(width * g.viewH / g.viewW)
  const uid = `lb${Math.abs(Math.round(score * 17 + stddev * 13))}`
  const bg = semicirclePath(g.cx, g.cy, g.rBg)
  const fill = scoreArcPath(score)
  const tip = needleTipPoint(score)
  const track = '#D8DCE4'
  const fg = '#1A2030'
  const muted = '#6A7388'

  let chip = ''
  if (zone === 'red') {
    chip = `<rect x="188" y="16" width="80" height="22" rx="6" fill="${colors.chipBg}" stroke="${colors.chipBd}"/>
  <text x="228" y="31" text-anchor="middle" fill="${colors.chipFg}" font-family="system-ui,sans-serif" font-size="11" font-weight="700">Unbalanced</text>`
  } else if (zone === 'amber') {
    chip = `<rect x="210" y="16" width="58" height="22" rx="6" fill="${colors.chipBg}" stroke="${colors.chipBd}"/>
  <text x="239" y="31" text-anchor="middle" fill="${colors.chipFg}" font-family="system-ui,sans-serif" font-size="11" font-weight="700">σ &gt; 30%</text>`
  }

  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${g.viewW} ${g.viewH}" width="${width}" height="${h}" role="img" aria-label="Load Balance Score ${score.toFixed(0)} percent, ${zone}">
  <defs>
    <linearGradient id="${uid}Grad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="${zone === 'red' ? '#EF5350' : '#3B82F6'}"/>
      <stop offset="55%" stop-color="${zone === 'red' ? '#E53935' : '#14B8A6'}"/>
      <stop offset="100%" stop-color="${colors.fillEnd}"/>
    </linearGradient>
  </defs>
  <rect width="100%" height="100%" rx="8" fill="#F7F8FA" stroke="${zone === 'red' ? colors.chipBd : '#E2E5EC'}"/>
  <path d="${bg}" fill="none" stroke="${track}" stroke-width="12" stroke-linecap="round"/>
  <path d="${fill}" fill="none" stroke="url(#${uid}Grad)" stroke-width="12" stroke-linecap="round"/>
  <line x1="${g.cx}" y1="${g.cy}" x2="${tip.x.toFixed(2)}" y2="${tip.y.toFixed(2)}" stroke="${fg}" stroke-width="2.25" stroke-linecap="round"/>
  <circle cx="${g.cx}" cy="${g.cy}" r="5" fill="#FFFFFF" stroke="${fg}" stroke-width="2"/>
  <text x="${g.cx}" y="${g.scoreY}" text-anchor="middle" fill="${colors.accent}" font-family="system-ui,sans-serif" font-size="28" font-weight="700">${score.toFixed(0)}%</text>
  <text x="${g.cx}" y="${g.labelY}" text-anchor="middle" fill="${muted}" font-family="system-ui,sans-serif" font-size="11">Load Balance Score</text>
  <text x="${g.cx}" y="142" text-anchor="middle" fill="${muted}" font-family="ui-monospace,monospace" font-size="10">100 × (1 − Gini) · σ=${stddev.toFixed(1)}% · G=${gini.toFixed(3)}</text>
  <text x="${g.cx}" y="158" text-anchor="middle" fill="${muted}" font-family="system-ui,sans-serif" font-size="10">100 = perfect balance · 0 = single-core overload</text>
  ${chip}
</svg>`
}
