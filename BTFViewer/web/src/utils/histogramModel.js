/** Histogram model for metrics plots (skew-aware binning + optional CDF). */

export const HISTOGRAM_SCALE_MODES = ['auto', 'linear', 'percentile', 'log']

const DEFAULT_BIN_COUNT = 40
const MAX_BIN_COUNT = 80
const MIN_BIN_COUNT = 12

export function percentile(sorted, p) {
  const n = sorted.length
  if (n === 0) return 0
  const idx = Math.min(n - 1, Math.max(0, Math.floor(p * (n - 1))))
  return sorted[idx]
}

export function summarizeNumericSamples(samples) {
  if (!samples || samples.length === 0) return null
  const values = [...samples].sort((a, b) => a - b)
  const n = values.length
  return {
    min: values[0],
    max: values[n - 1],
    avg: values.reduce((sum, value) => sum + value, 0) / n,
    p5: percentile(values, 0.05),
    p50: percentile(values, 0.5),
    p95: percentile(values, 0.95),
    p99: percentile(values, 0.99),
  }
}

/** Pick linear / percentile / log when mode is auto. */
export function detectHistogramScaleMode(values, summary) {
  if (!values.length) return 'linear'
  if (values.length < 4) return 'linear'

  const min = summary.min
  const max = summary.max
  const p5 = summary.p5
  const p95 = summary.p95
  const span = Math.max(1, max - min)
  const coreSpan = Math.max(1, p95 - p5)
  const tailRatio = max / Math.max(p95, 1)
  const crowded = coreSpan / span < 0.55

  if (min > 0) {
    const rangeRatio = max / Math.max(min, 1)
    if (rangeRatio >= 40 || (tailRatio >= 4 && crowded)) return 'log'
  }
  if (tailRatio >= 2 || crowded) return 'percentile'
  return 'linear'
}

function freedmanDiaconisBinCount(values, minVal, maxVal) {
  const n = values.length
  if (n < 2) return DEFAULT_BIN_COUNT
  const p25 = percentile(values, 0.25)
  const p75 = percentile(values, 0.75)
  const iqr = Math.max(1, p75 - p25)
  const binWidth = (2 * iqr) / Math.cbrt(n)
  const span = Math.max(1, maxVal - minVal)
  return Math.min(MAX_BIN_COUNT, Math.max(MIN_BIN_COUNT, Math.round(span / binWidth)))
}

function shouldUseLogY(counts) {
  const positive = counts.filter(c => c > 0)
  if (positive.length < 2) return false
  const maxCount = Math.max(...positive)
  const sorted = [...positive].sort((a, b) => a - b)
  const median = sorted[Math.floor(sorted.length / 2)]
  return maxCount >= 12 && median > 0 && maxCount / median >= 8
}

function logSpacedEdges(minVal, maxVal, binCount) {
  const lo = Math.max(minVal, 1)
  const hi = Math.max(lo + 1, maxVal)
  const logLo = Math.log10(lo)
  const logHi = Math.log10(hi)
  const edges = []
  for (let i = 0; i <= binCount; i++) {
    edges.push(10 ** (logLo + ((logHi - logLo) * i) / binCount))
  }
  return edges
}

function binIndexForValue(value, edges) {
  const last = edges.length - 2
  if (value <= edges[0]) return 0
  if (value >= edges[last + 1]) return last
  for (let i = 0; i <= last; i++) {
    if (value < edges[i + 1]) return i
  }
  return last
}

function buildBins(values, scaleMode, summary) {
  const min = summary.min
  const max = summary.max
  const p5 = summary.p5
  const p95 = summary.p95

  if (scaleMode === 'percentile') {
    const lo = Math.min(p5, p95)
    const hi = Math.max(lo + 1, p95)
    const regularBins = freedmanDiaconisBinCount(values, lo, hi)
    const edges = []
    const step = (hi - lo) / regularBins
    for (let i = 0; i <= regularBins; i++) edges.push(lo + step * i)
    const counts = Array.from({ length: regularBins }, () => 0)
    let overflow = 0
    let underflow = 0
    for (const value of values) {
      if (value < lo) underflow++
      else if (value > hi) overflow++
      else counts[binIndexForValue(value, edges)]++
    }
    return {
      counts,
      edges,
      displayMin: lo,
      displayMax: hi,
      overflow,
      underflow,
      hasOverflowBin: overflow > 0,
      hasUnderflowBin: underflow > 0,
      xScale: 'linear',
    }
  }

  if (scaleMode === 'log' && min > 0) {
    const binCount = DEFAULT_BIN_COUNT
    const edges = logSpacedEdges(min, max, binCount)
    const counts = Array.from({ length: binCount }, () => 0)
    for (const value of values) {
      counts[binIndexForValue(value, edges)]++
    }
    return {
      counts,
      edges,
      displayMin: min,
      displayMax: max,
      overflow: 0,
      underflow: 0,
      hasOverflowBin: false,
      hasUnderflowBin: false,
      xScale: 'log',
    }
  }

  const lo = min
  const hi = max
  const span = Math.max(1, hi - lo)
  const binCount = freedmanDiaconisBinCount(values, lo, hi)
  const step = span / binCount
  const edges = []
  for (let i = 0; i <= binCount; i++) edges.push(lo + step * i)
  const counts = Array.from({ length: binCount }, () => 0)
  for (const value of values) {
    counts[binIndexForValue(value, edges)]++
  }
  return {
    counts,
    edges,
    displayMin: lo,
    displayMax: hi,
    overflow: 0,
    underflow: 0,
    hasOverflowBin: false,
    hasUnderflowBin: false,
    xScale: 'linear',
  }
}

function histSlotLayout(binSpec, plotW) {
  const { counts, hasOverflowBin, hasUnderflowBin } = binSpec
  const leading = hasUnderflowBin ? 1 : 0
  const regularSlots = counts.length
  const slotCount = leading + regularSlots + (hasOverflowBin ? 1 : 0)
  const slotW = plotW / Math.max(1, slotCount)
  return { slotCount, slotW, leading, regularSlots, regularW: regularSlots * slotW }
}

function valueToX(value, binSpec, plotW, marginLeft) {
  const { displayMin, displayMax, xScale, hasOverflowBin, hasUnderflowBin } = binSpec
  const { slotW, leading, regularSlots, regularW } = histSlotLayout(binSpec, plotW)
  const regionLeft = marginLeft + leading * slotW

  if (hasUnderflowBin && value < displayMin) {
    return marginLeft + slotW * 0.5
  }
  if (hasOverflowBin && value > displayMax) {
    const slot = leading + regularSlots
    return marginLeft + slot * slotW + slotW * 0.5
  }

  let t
  if (xScale === 'log') {
    const lo = Math.max(displayMin, 1)
    const hi = Math.max(lo + 1, displayMax)
    const logLo = Math.log10(lo)
    const logHi = Math.log10(hi)
    t = (Math.log10(Math.max(value, lo)) - logLo) / Math.max(1e-9, logHi - logLo)
  } else {
    const span = Math.max(1, displayMax - displayMin)
    t = (value - displayMin) / span
  }
  return regionLeft + t * regularW
}

function buildBarLayout(binSpec, plotW, plotH, margin, logY) {
  const { counts, edges, hasOverflowBin, hasUnderflowBin, overflow, underflow } = binSpec
  const { slotCount, slotW, leading } = histSlotLayout(binSpec, plotW)
  const maxCount = Math.max(1, ...counts, overflow, underflow)
  const countHeight = count => {
    if (count <= 0) return 0
    if (!logY) return (count / maxCount) * plotH
    return (Math.log10(count + 1) / Math.log10(maxCount + 1)) * plotH
  }

  const bars = []
  let slot = leading

  if (hasUnderflowBin) {
    const h = countHeight(underflow)
    bars.push({
      index: -1,
      x: margin.left + slot * slotW,
      y: margin.top + plotH - h,
      width: Math.max(1, slotW - 1),
      height: h,
      kind: 'underflow',
      label: `<p5 (${underflow})`,
    })
    slot++
  }

  for (let i = 0; i < counts.length; i++) {
    const h = countHeight(counts[i])
    bars.push({
      index: i,
      x: margin.left + slot * slotW,
      y: margin.top + plotH - h,
      width: Math.max(1, slotW - 1),
      height: h,
      kind: 'regular',
      edgeLo: edges[i],
      edgeHi: edges[i + 1],
    })
    slot++
  }

  if (hasOverflowBin) {
    const h = countHeight(overflow)
    bars.push({
      index: counts.length,
      x: margin.left + slot * slotW,
      y: margin.top + plotH - h,
      width: Math.max(1, slotW - 1),
      height: h,
      kind: 'overflow',
      label: `>p95 (${overflow})`,
    })
  }

  return { bars, maxCount, slotCount, slotW }
}

function buildXTicks(binSpec, plotW, margin, formatValue) {
  const { displayMin, displayMax, xScale, hasOverflowBin, hasUnderflowBin } = binSpec
  const { slotCount, slotW, leading, regularSlots, regularW } = histSlotLayout(binSpec, plotW)
  const regionLeft = margin.left + leading * slotW

  if (xScale === 'log') {
    const lo = Math.max(displayMin, 1)
    const hi = Math.max(lo + 1, displayMax)
    const logLo = Math.log10(lo)
    const logHi = Math.log10(hi)
    const ticks = []
    const startDecade = Math.floor(logLo)
    const endDecade = Math.ceil(logHi)
    let idx = 0
    for (let d = startDecade; d <= endDecade; d++) {
      for (const m of [1, 2, 5]) {
        const value = m * 10 ** d
        if (value < lo * 0.999 || value > hi * 1.001) continue
        const t = (Math.log10(value) - logLo) / Math.max(1e-9, logHi - logLo)
        ticks.push({
          index: idx++,
          x: regionLeft + t * regularW,
          label: formatValue(Math.round(value)),
        })
      }
    }
    if (ticks.length === 0) {
      return [0, 0.5, 1].map((ratio, index) => {
        const logVal = logLo + (logHi - logLo) * ratio
        const value = Math.round(10 ** logVal)
        return { index, x: regionLeft + ratio * regularW, label: formatValue(value) }
      })
    }
    return ticks.slice(0, 7)
  }

  const ticks = [0, 0.5, 1].map((ratio, index) => {
    const value = Math.round(displayMin + (displayMax - displayMin) * ratio)
    return {
      index,
      x: regionLeft + ratio * regularW,
      label: formatValue(value),
    }
  })

  if (hasOverflowBin) {
    ticks.push({
      index: ticks.length,
      x: margin.left + (leading + regularSlots + 0.5) * slotW,
      label: '>p95',
    })
  }
  return ticks
}

function buildCdfPoints(values, binSpec, plotW, plotH, margin) {
  const n = values.length
  if (n < 2) return { points: [], ticks: [] }

  const sorted = [...values].sort((a, b) => a - b)
  const raw = []
  for (let i = 0; i < n; i++) {
    const pct = ((i + 1) / n) * 100
    raw.push({
      x: valueToX(sorted[i], binSpec, plotW, margin.left),
      y: margin.top + plotH - (pct / 100) * plotH,
      pct,
    })
  }

  // ECDF: keep the highest percentile at each x so the polyline never hooks backward.
  const points = []
  for (const pt of raw) {
    const prev = points[points.length - 1]
    if (prev && Math.abs(prev.x - pt.x) < 0.5) {
      points[points.length - 1] = pt
    } else if (!prev || pt.x >= prev.x - 0.5) {
      points.push(pt)
    }
  }

  if (points.length > 90) {
    const sampled = []
    const step = Math.ceil(points.length / 80)
    for (let i = 0; i < points.length; i += step) sampled.push(points[i])
    const last = points[points.length - 1]
    if (sampled[sampled.length - 1] !== last) sampled.push(last)
    return {
      points: sampled,
      ticks: [0, 50, 100].map((pct, index) => ({
        index,
        y: margin.top + plotH - (pct / 100) * plotH,
        label: `${pct}%`,
      })),
    }
  }

  const ticks = [0, 50, 100].map((pct, index) => ({
    index,
    y: margin.top + plotH - (pct / 100) * plotH,
    label: `${pct}%`,
  }))

  return { points, ticks }
}

function buildCaption(scaleMode, summary, binSpec, logY, formatValue) {
  const parts = []
  if (scaleMode === 'percentile') {
    parts.push('p5–p95 view')
    if (binSpec.overflow > 0) parts.push(`${binSpec.overflow} above p95`)
    if (binSpec.underflow > 0) parts.push(`${binSpec.underflow} below p5`)
  } else if (scaleMode === 'log') {
    parts.push('log-scaled duration axis')
  } else {
    parts.push('linear scale')
  }
  if (logY) parts.push('log-scaled counts')
  parts.push(`full range ${formatValue(summary.min)}–${formatValue(summary.max)}`)
  return parts.join(' · ')
}

/**
 * @param {number[]} values
 * @param {object} options
 * @param {'auto'|'linear'|'percentile'|'log'} [options.scaleMode='auto']
 * @param {(ns:number)=>string} options.formatValue
 * @param {string} [options.color]
 * @param {number} [options.width=820]
 * @param {number} [options.height=240]
 */
export function buildHistogramModel(values, options = {}) {
  const {
    scaleMode = 'auto',
    formatValue = v => String(v),
    color = '#5B9BD5',
    width = 820,
    height = 240,
  } = options

  const sorted = [...values].sort((a, b) => a - b)
  if (sorted.length === 0) return null

  const summary = summarizeNumericSamples(sorted)
  const resolvedMode = scaleMode === 'auto'
    ? detectHistogramScaleMode(sorted, summary)
    : scaleMode

  const effectiveMode = (resolvedMode === 'log' && summary.min <= 0) ? 'percentile' : resolvedMode
  const binSpec = buildBins(sorted, effectiveMode, summary)
  const margin = { left: 72, right: 44, top: 28, bottom: 38 }
  const plotW = width - margin.left - margin.right
  const plotH = height - margin.top - margin.bottom
  const logY = shouldUseLogY([...binSpec.counts, binSpec.overflow, binSpec.underflow])
  const { bars, maxCount } = buildBarLayout(binSpec, plotW, plotH, margin, logY)

  const scaleX = value => valueToX(value, binSpec, plotW, margin.left)
  const xTicks = buildXTicks(binSpec, plotW, margin, formatValue)
  const yTicks = Array.from({ length: 5 }, (_, index) => {
    const ratio = 1 - index / 4
    const count = logY
      ? Math.round((10 ** (Math.log10(maxCount + 1) * ratio)) - 1)
      : Math.round(maxCount * ratio)
    const barH = logY
      ? (Math.log10(count + 1) / Math.log10(maxCount + 1)) * plotH
      : (count / Math.max(1, maxCount)) * plotH
    return {
      index,
      y: margin.top + plotH - barH,
      label: String(count),
    }
  })

  const cdf = buildCdfPoints(sorted, binSpec, plotW, plotH, margin)

  return {
    width,
    height,
    margin,
    color,
    bars,
    xTicks,
    yTicks,
    cdfPoints: cdf.points,
    cdfTicks: cdf.ticks,
    referenceLines: [
      { label: 'avg', x: scaleX(summary.avg), color: '#CE93D8' },
      { label: 'p50', x: scaleX(summary.p50), color: '#4CAF50' },
      { label: 'p95', x: scaleX(summary.p95), color: '#FF9800' },
    ].filter(line => line.x >= margin.left && line.x <= width - margin.right),
    caption: buildCaption(effectiveMode, summary, binSpec, logY, formatValue),
    scaleMode: effectiveMode,
    requestedScaleMode: scaleMode,
    logY,
    summary,
    overflowCount: binSpec.overflow,
  }
}
