/**
 * Export statistics distribution plots (scatter + histogram) as SVG for README docs.
 * Usage: node scripts/export-stats-plots.mjs [path/to/trace.btf] [output-dir]
 */
import { readFileSync, mkdirSync, writeFileSync } from 'fs'
import { dirname, join, resolve } from 'path'
import { fileURLToPath } from 'url'
import { parseBtf } from '../src/parser/btfParser.js'
import { finalizeAndEnrich } from '../src/parser/tracePack.js'
import {
  blockingTimePlotPoints,
  preemptionChainPlotPoints,
  preemptionChainRows,
} from '../src/utils/statsAnalysis.js'
import { intervalColor, intervalPlotPoints } from '../src/utils/intervalAnalysis.js'
import { taskColor, taskDisplayName, taskReprGet } from '../src/utils/colors.js'
import { formatTime } from '../src/utils/timeFormat.js'

const __dirname = dirname(fileURLToPath(import.meta.url))
const defaultBtf = resolve(__dirname, '../../../tracedata/example-4cores.btf')
const defaultOut = resolve(__dirname, '../../../images/stats')

const btfPath = resolve(process.argv[2] || defaultBtf)
const outDir = resolve(process.argv[3] || defaultOut)

function summarizeNumericSamples(samples) {
  if (!samples?.length) return null
  const values = [...samples].sort((a, b) => a - b)
  const n = values.length
  return {
    avg: values.reduce((sum, v) => sum + v, 0) / n,
    p50: values[Math.min(n - 1, Math.floor(n * 0.5))],
    p95: values[Math.min(n - 1, Math.floor(n * 0.95))],
  }
}

function buildExecPlot(trace, mk) {
  const repr = taskReprGet(trace, mk) || mk
  let segs = trace.segByMergeKey.get(mk) || []
  const points = segs
    .filter(seg => seg.end > seg.start)
    .map((seg, index) => ({
      index,
      xNs: seg.start,
      yValue: seg.end - seg.start,
    }))
  return {
    title: `${taskDisplayName(repr)} — Execution Time`,
    color: taskColor(mk, repr),
    points,
  }
}

function buildBlockPlot(trace, mk) {
  const repr = taskReprGet(trace, mk) || mk
  const segs = trace.segByMergeKey.get(mk) || []
  const points = blockingTimePlotPoints(segs, null, null).map((pt, index) => ({
    index,
    xNs: pt.xNs,
    yValue: pt.yValue,
  }))
  return {
    title: `${taskDisplayName(repr)} — Blocking Time`,
    color: taskColor(mk, repr),
    points,
  }
}

function buildInterPlot(trace, mk) {
  const repr = taskReprGet(trace, mk) || mk
  const segs = [...(trace.segByMergeKey.get(mk) || [])].sort((a, b) => a.start - b.start)
  const points = []
  for (let i = 1; i < segs.length; i++) {
    const delta = segs[i].start - segs[i - 1].start
    if (delta <= 0) continue
    points.push({ index: points.length, xNs: segs[i].start, yValue: delta })
  }
  return {
    title: `${taskDisplayName(repr)} — Inter-Arrival Time`,
    color: taskColor(mk, repr),
    points,
  }
}

function buildPreemptPlot(trace, victimMk, preemptor) {
  const repr = taskReprGet(trace, victimMk) || victimMk
  const points = preemptionChainPlotPoints(trace, victimMk, preemptor, null, null).map((pt, index) => ({
    index,
    xNs: pt.xNs,
    yValue: pt.yValue,
  }))
  return {
    title: `${taskDisplayName(repr)} ← preempted by ${preemptor}`,
    color: taskColor(victimMk, repr),
    points,
  }
}

function buildIntervalPlot(trace, intervalId) {
  const points = intervalPlotPoints(trace, intervalId, null, null).map((pt, index) => ({
    index,
    xNs: pt.xNs,
    yValue: pt.yValue,
  }))
  return {
    title: `Interval ${intervalId} — Duration`,
    color: intervalColor(intervalId),
    points,
  }
}

function buildScatterModel(plot, timeScale) {
  const width = 820
  const height = 320
  const margin = { left: 72, right: 42, top: 16, bottom: 34 }
  const xs = plot.points.map(p => p.xNs)
  const ys = plot.points.map(p => p.yValue)
  const x0 = Math.min(...xs)
  const x1 = Math.max(...xs)
  const yMax = Math.max(1, ...ys)
  const xSpan = Math.max(1, x1 - x0)
  const plotW = width - margin.left - margin.right
  const plotH = height - margin.top - margin.bottom
  const summary = summarizeNumericSamples(ys)
  const scaleX = v => margin.left + ((v - x0) / xSpan) * plotW
  const scaleY = v => margin.top + plotH - (v / yMax) * plotH
  return {
    width,
    height,
    margin,
    color: plot.color,
    xTicks: [0, 0.5, 1].map((ratio, index) => {
      const value = Math.round(x0 + xSpan * ratio)
      return { index, x: scaleX(value), label: formatTime(value, timeScale) }
    }),
    yTicks: Array.from({ length: 5 }, (_, index) => {
      const value = yMax * (1 - index / 4)
      return { index, y: scaleY(value), label: formatTime(Math.round(value), timeScale) }
    }),
    referenceLines: summary
      ? [
          { label: 'avg', y: scaleY(summary.avg), color: '#CE93D8' },
          { label: 'p50', y: scaleY(summary.p50), color: '#4CAF50' },
          { label: 'p95', y: scaleY(summary.p95), color: '#FF9800' },
        ]
      : [],
    points: plot.points.map(p => ({ ...p, x: scaleX(p.xNs), y: scaleY(p.yValue) })),
  }
}

function buildHistogramModel(plot, timeScale) {
  const width = 820
  const height = 220
  const margin = { left: 72, right: 24, top: 16, bottom: 34 }
  const values = plot.points.map(p => p.yValue).sort((a, b) => a - b)
  const v0 = values[0]
  const v1 = values[values.length - 1]
  const vSpan = Math.max(1, v1 - v0)
  const plotW = width - margin.left - margin.right
  const plotH = height - margin.top - margin.bottom
  const binCount = 50
  const counts = Array.from({ length: binCount }, () => 0)
  const step = vSpan / binCount
  for (const value of values) {
    const rawIndex = step > 0 ? Math.floor((value - v0) / step) : 0
    counts[Math.min(binCount - 1, Math.max(0, rawIndex))] += 1
  }
  const maxCount = Math.max(1, ...counts)
  const summary = summarizeNumericSamples(values)
  const scaleX = v => margin.left + ((v - v0) / vSpan) * plotW
  return {
    width,
    height,
    margin,
    color: plot.color,
    bars: counts.map((count, index) => {
      const barWidth = Math.max(1, plotW / binCount - 1)
      const barHeight = count > 0 ? (count / maxCount) * plotH : 0
      return {
        index,
        x: margin.left + (index * plotW) / binCount,
        y: margin.top + plotH - barHeight,
        width: barWidth,
        height: barHeight,
      }
    }),
    xTicks: [0, 0.5, 1].map((ratio, index) => {
      const value = Math.round(v0 + vSpan * ratio)
      return { index, x: scaleX(value), label: formatTime(value, timeScale) }
    }),
    referenceLines: summary
      ? [
          { label: 'avg', x: scaleX(summary.avg), color: '#CE93D8' },
          { label: 'p50', x: scaleX(summary.p50), color: '#4CAF50' },
          { label: 'p95', x: scaleX(summary.p95), color: '#FF9800' },
        ]
      : [],
  }
}

function esc(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function renderScatterSvg(model, yLabel) {
  const lines = []
  lines.push(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${model.width} ${model.height}" width="${model.width}" height="${model.height}">`)
  lines.push(`<rect width="100%" height="100%" fill="#1e1e1e"/>`)
  for (const grid of model.yTicks) {
    lines.push(`<line x1="${model.margin.left}" y1="${grid.y}" x2="${model.width - model.margin.right}" y2="${grid.y}" stroke="#333" stroke-width="1"/>`)
  }
  lines.push(`<line x1="${model.margin.left}" y1="${model.margin.top}" x2="${model.margin.left}" y2="${model.height - model.margin.bottom}" stroke="#666" stroke-width="1"/>`)
  lines.push(`<line x1="${model.margin.left}" y1="${model.height - model.margin.bottom}" x2="${model.width - model.margin.right}" y2="${model.height - model.margin.bottom}" stroke="#666" stroke-width="1"/>`)
  for (const tick of model.yTicks) {
    lines.push(`<text x="${model.margin.left - 8}" y="${tick.y + 4}" text-anchor="end" fill="#aaa" font-size="10" font-family="monospace">${esc(tick.label)}</text>`)
  }
  for (const tick of model.xTicks) {
    lines.push(`<text x="${tick.x}" y="${model.height - 10}" text-anchor="middle" fill="#aaa" font-size="10" font-family="monospace">${esc(tick.label)}</text>`)
  }
  lines.push(`<text x="${model.width / 2}" y="${model.height - 2}" text-anchor="middle" fill="#888" font-size="11" font-family="sans-serif">Time</text>`)
  lines.push(`<text transform="rotate(-90 ${14} ${model.height / 2})" x="14" y="${model.height / 2}" text-anchor="middle" fill="#888" font-size="11" font-family="sans-serif">${esc(yLabel)}</text>`)
  for (const ref of model.referenceLines) {
    lines.push(`<line x1="${model.margin.left}" y1="${ref.y}" x2="${model.width - model.margin.right}" y2="${ref.y}" stroke="${ref.color}" stroke-width="1" stroke-dasharray="4 3" opacity="0.85"/>`)
    lines.push(`<text x="${model.width - model.margin.right + 6}" y="${ref.y + 4}" fill="${ref.color}" font-size="9" font-family="monospace">${esc(ref.label)}</text>`)
  }
  for (const point of model.points) {
    lines.push(`<circle cx="${point.x}" cy="${point.y}" r="3" fill="${model.color}" opacity="0.75"/>`)
  }
  lines.push('</svg>')
  return lines.join('\n')
}

function renderHistogramSvg(model) {
  const lines = []
  lines.push(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${model.width} ${model.height}" width="${model.width}" height="${model.height}">`)
  lines.push(`<rect width="100%" height="100%" fill="#1e1e1e"/>`)
  const plotH = model.height - model.margin.top - model.margin.bottom
  const baseY = model.margin.top + plotH
  lines.push(`<line x1="${model.margin.left}" y1="${model.margin.top}" x2="${model.margin.left}" y2="${baseY}" stroke="#666" stroke-width="1"/>`)
  lines.push(`<line x1="${model.margin.left}" y1="${baseY}" x2="${model.width - model.margin.right}" y2="${baseY}" stroke="#666" stroke-width="1"/>`)
  for (const tick of model.xTicks) {
    lines.push(`<text x="${tick.x}" y="${model.height - 10}" text-anchor="middle" fill="#aaa" font-size="10" font-family="monospace">${esc(tick.label)}</text>`)
  }
  lines.push(`<text x="${model.width / 2}" y="${model.height - 2}" text-anchor="middle" fill="#888" font-size="11" font-family="sans-serif">Duration</text>`)
  lines.push(`<text transform="rotate(-90 ${14} ${model.height / 2})" x="14" y="${model.height / 2}" text-anchor="middle" fill="#888" font-size="11" font-family="sans-serif">Count</text>`)
  for (const ref of model.referenceLines) {
    lines.push(`<line x1="${ref.x}" y1="${model.margin.top}" x2="${ref.x}" y2="${baseY}" stroke="${ref.color}" stroke-width="1" stroke-dasharray="4 3" opacity="0.85"/>`)
    lines.push(`<text x="${ref.x}" y="${model.margin.top - 4}" text-anchor="middle" fill="${ref.color}" font-size="9" font-family="monospace">${esc(ref.label)}</text>`)
  }
  for (const bar of model.bars) {
    if (bar.height <= 0) continue
    lines.push(`<rect x="${bar.x}" y="${bar.y}" width="${bar.width}" height="${bar.height}" fill="${model.color}" opacity="0.8"/>`)
  }
  lines.push('</svg>')
  return lines.join('\n')
}

function renderPlotSvg(plot, timeScale, yLabel) {
  const scatter = buildScatterModel(plot, timeScale)
  const hist = buildHistogramModel(plot, timeScale)
  const totalH = scatter.height + hist.height + 48
  const width = scatter.width
  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${totalH}" width="${width}" height="${totalH}">
  <rect width="100%" height="100%" fill="#1a1a1a"/>
  <text x="16" y="22" fill="#e0e0e0" font-size="14" font-weight="600" font-family="sans-serif">${esc(plot.title)}</text>
  <text x="16" y="38" fill="#888" font-size="10" font-family="sans-serif">Scatter: ${esc(yLabel.scatter)} · Histogram: ${esc(yLabel.histogram)} · ${plot.points.length} points</text>
  <g transform="translate(0,44)">
    ${renderScatterSvg(scatter).replace(/^<svg[^>]*>/, '').replace(/<\/svg>$/, '')}
  </g>
  <g transform="translate(0,${44 + scatter.height + 8})">
    ${renderHistogramSvg(hist).replace(/^<svg[^>]*>/, '').replace(/<\/svg>$/, '')}
  </g>
</svg>
`
}

const Y_LABELS = {
  exec: {
    scatter: 'x = slice start time, y = slice duration',
    histogram: 'distribution of slice durations',
  },
  block: {
    scatter: 'x = resume time, y = off-CPU gap',
    histogram: 'distribution of blocking gaps',
  },
  inter: {
    scatter: 'x = activation time, y = gap since previous activation',
    histogram: 'distribution of inter-arrival gaps',
  },
  preempt: {
    scatter: 'x = preemption overlap start, y = overlap duration',
    histogram: 'overlap duration distribution for this preemptor',
  },
  interval: {
    scatter: 'x = interval stop time, y = interval duration',
    histogram: 'distribution of interval durations',
  },
}

function findMkByDisplay(trace, display) {
  for (const [mk, repr] of trace.taskRepr) {
    if (taskDisplayName(repr) === display) return mk
  }
  return null
}

const text = readFileSync(btfPath, 'utf8')
const trace = finalizeAndEnrich(await parseBtf(text))
mkdirSync(outDir, { recursive: true })

const cs8Mk = findMkByDisplay(trace, 'CS[8]')
const { rows: _preemptExportRows } = preemptionChainRows(trace)
const preemptRow = _preemptExportRows[1] // CS[10] ← CS[11], high count

const exports = [
  { id: 'exec-cs8', plot: buildExecPlot(trace, cs8Mk), kind: 'exec' },
  { id: 'block-cs8', plot: buildBlockPlot(trace, cs8Mk), kind: 'block' },
  { id: 'inter-cs8', plot: buildInterPlot(trace, cs8Mk), kind: 'inter' },
  {
    id: 'preempt-cs10-cs11',
    plot: buildPreemptPlot(trace, preemptRow.mk, preemptRow.preemptor),
    kind: 'preempt',
  },
  {
    id: 'interval-1',
    plot: buildIntervalPlot(trace, '1'),
    kind: 'interval',
  },
]

for (const item of exports) {
  if (!item.plot?.points?.length) {
    console.warn(`skip ${item.id}: no points`)
    continue
  }
  const svg = renderPlotSvg(item.plot, trace.timeScale, Y_LABELS[item.kind])
  const path = join(outDir, `stats-${item.id}.svg`)
  writeFileSync(path, svg)
  console.log(`wrote ${path} (${item.plot.points.length} points)`)
}

console.log(`trace: ${btfPath} (${trace.coreNames.length} cores, ${trace.tasks.length} tasks, scale=${trace.timeScale})`)
