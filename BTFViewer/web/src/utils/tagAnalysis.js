/**
 * STI tag channel statistics (tag0_event … tag7_event, tag_event).
 */
import { formatTime } from './timeFormat.js'

const TAG_CHANNEL_RE = /^tag([0-7])?_event$/i

const TAG_COLORS = [
  '#E8C84A', '#3498DB', '#2ECC71', '#E74C3C', '#9B59B6',
  '#1ABC9C', '#F39C12', '#E91E63',
]
const FLOAT32_VIEW = new DataView(new ArrayBuffer(4))

export const TAG_REPRESENTATION_OPTIONS = Object.freeze([
  { value: 'uint32', label: 'uint32' },
  { value: 'int32', label: 'int32' },
  { value: 'float32', label: 'float32' },
  { value: 'log2-uint32', label: 'log₂ uint32' },
])

export function normalizeTagRepresentation(value) {
  return TAG_REPRESENTATION_OPTIONS.some(option => option.value === value) ? value : 'uint32'
}

/** Convert the BTF numeric payload to its original 32-bit word. */
export function tagRawUint32(note) {
  const raw = (note != null && note !== '') ? String(note).trim() : ''
  if (!raw) return null
  const numeric = /^[-+]?0[xX][0-9a-f]+$/i.test(raw) ? Number.parseInt(raw, 0) : Number(raw)
  if (!Number.isFinite(numeric)) return null
  return Math.trunc(numeric) >>> 0
}

/** Interpret one tag payload without changing its underlying 32-bit bits. */
export function interpretTagValue(note, representation = 'uint32') {
  const bits = tagRawUint32(note)
  if (bits == null) return null
  switch (normalizeTagRepresentation(representation)) {
    case 'int32': return bits | 0
    case 'float32': {
      FLOAT32_VIEW.setUint32(0, bits, false)
      const value = FLOAT32_VIEW.getFloat32(0, false)
      return Number.isFinite(value) ? value : null
    }
    case 'log2-uint32': return Math.log2(1 + bits)
    default: return bits
  }
}

export function tagRepresentationFor(channel, representations, trace = null, lo = null, hi = null) {
  if (representations?.[channel]) return normalizeTagRepresentation(representations[channel])
  return trace ? recommendTagRepresentation(trace, channel, lo, hi) : 'uint32'
}

/** Recommend log normalization only when non-zero uint32 samples span >= 256x. */
export function recommendTagRepresentation(trace, channel, lo = null, hi = null) {
  const samples = trace?.tagSamplesByChannel?.get(channel) || []
  const values = samples
    .filter(sample => tagOverlapsRange(sample, lo, hi))
    .map(sample => sample.rawUint32 ?? tagRawUint32(sample.rawValue ?? sample.value))
    .filter(value => Number.isFinite(value) && value > 0)
  if (values.length < 3) return 'uint32'
  let min = Infinity
  let max = -Infinity
  for (const value of values) {
    if (value < min) min = value
    if (value > max) max = value
  }
  return max / min >= 256 ? 'log2-uint32' : 'uint32'
}

export function isTagChannel(name) {
  return TAG_CHANNEL_RE.test(name || '')
}

/** Sort key aligned with timeline STI tag channel order. */
export function tagChannelSortKey(channel) {
  const m = TAG_CHANNEL_RE.exec(channel || '')
  if (!m) return [2, 0, channel]
  const digit = m[1]
  return [0, digit != null ? parseInt(digit, 10) : -1, channel.toLowerCase()]
}

export function tagChannelLabel(channel) {
  const m = TAG_CHANNEL_RE.exec(channel || '')
  if (!m) return channel
  const digit = m[1]
  return digit != null ? `Tag ${digit}` : 'Tag'
}

export function tagColor(channel) {
  const m = TAG_CHANNEL_RE.exec(channel || '')
  const idx = m?.[1] != null ? parseInt(m[1], 10) % TAG_COLORS.length : 0
  return TAG_COLORS[idx]
}

export function parseTagValue(note) {
  return interpretTagValue(note, 'uint32')
}

export function formatTagValue(value) {
  if (!Number.isFinite(value)) return '—'
  if (Number.isInteger(value)) return value.toLocaleString()
  return formatGeneral(value, 6)
}

/** Mimic Python's `f"{value:g}"` (6 significant digits, switches to
 * scientific notation outside the fixed-point exponent range), so
 * non-integer averages/min/max/p95 render the same on desktop and web. */
function formatGeneral(value, precision) {
  if (value === 0) return '0'
  const sign = value < 0 ? '-' : ''
  const abs = Math.abs(value)
  let e = Math.floor(Math.log10(abs))
  if (Math.pow(10, e) > abs) e -= 1
  else if (Math.pow(10, e + 1) <= abs) e += 1
  let str
  if (e < -4 || e >= precision) {
    const [mantissaRaw, expRaw] = abs.toExponential(precision - 1).split('e')
    const mantissa = mantissaRaw.includes('.')
      ? mantissaRaw.replace(/0+$/, '').replace(/\.$/, '')
      : mantissaRaw
    const expNum = parseInt(expRaw, 10)
    const expSign = expNum < 0 ? '-' : '+'
    const expAbs = String(Math.abs(expNum)).padStart(2, '0')
    str = `${mantissa}e${expSign}${expAbs}`
  } else {
    const decimals = Math.max(0, precision - 1 - e)
    str = abs.toFixed(decimals)
    if (str.includes('.')) str = str.replace(/0+$/, '').replace(/\.$/, '')
  }
  return sign + str
}

function percentile(sorted, p) {
  if (!sorted.length) return 0
  const idx = Math.min(sorted.length - 1, Math.max(0, Math.ceil(p * sorted.length) - 1))
  return sorted[idx]
}

/** `{ jitter, sigma, p50, p99 }` for a sorted list — matches parser.py `_sample_variability`. */
function sampleVariability(sorted) {
  const n = sorted.length
  if (!n) return { jitter: 0, sigma: 0, p50: 0, p99: 0 }
  const avg = sorted.reduce((a, b) => a + b, 0) / n
  const sigma = Math.sqrt(sorted.reduce((a, v) => a + (v - avg) * (v - avg), 0) / n)
  return {
    jitter: sorted[n - 1] - sorted[0],
    sigma,
    p50: percentile(sorted, 0.50),
    p99: percentile(sorted, 0.99),
  }
}

/**
 * Index tag STI events by channel.
 * @returns {{ tagChannels: string[], tagSamplesByChannel: Map<string, Array> }}
 */
export function buildTagData(stiEvents) {
  /** @type {Map<string, Array<{channel, timeNs, value, core}>>} */
  const tagSamplesByChannel = new Map()

  for (const ev of stiEvents || []) {
    if (!isTagChannel(ev.target)) continue
    const rawUint32 = tagRawUint32(ev.note)
    const value = rawUint32
    if (value == null) continue
    const ch = ev.target
    if (!tagSamplesByChannel.has(ch)) tagSamplesByChannel.set(ch, [])
    tagSamplesByChannel.get(ch).push({
      channel: ch,
      timeNs: ev.time,
      value,
      rawValue: ev.note,
      rawUint32,
      core: ev.core || '',
    })
  }

  for (const list of tagSamplesByChannel.values()) {
    list.sort((a, b) => a.timeNs - b.timeNs || a.value - b.value)
  }

  const tagChannels = [...tagSamplesByChannel.keys()].sort((a, b) => {
    const ka = tagChannelSortKey(a)
    const kb = tagChannelSortKey(b)
    if (ka[0] !== kb[0]) return ka[0] - kb[0]
    if (ka[1] !== kb[1]) return ka[1] - kb[1]
    return ka[2].localeCompare(kb[2])
  })

  return { tagChannels, tagSamplesByChannel }
}

export function tagOverlapsRange(sample, lo, hi) {
  if (lo == null || hi == null) return true
  return sample.timeNs >= lo && sample.timeNs <= hi
}

/**
 * Per-tag-channel statistics rows (value distribution, not time).
 * @returns {Array<{channel, label, count, minVal, avgVal, maxVal, jitterVal,
 *   sigmaVal, p50Val, p95Val, p99Val, min, avg, max, jitter, sigma, p50, p95, p99}>}
 */
export function tagStatsRows(trace, lo, hi, representations = null) {
  const byCh = trace?.tagSamplesByChannel
  if (!byCh?.size) return []

  const rows = []
  for (const channel of trace.tagChannels || []) {
    const samples = (byCh.get(channel) || [])
      .filter(s => tagOverlapsRange(s, lo, hi))
      .map(s => interpretTagValue(s.rawValue ?? s.rawUint32 ?? s.value, tagRepresentationFor(channel, representations, trace, lo, hi)))
      .filter(Number.isFinite)
    if (!samples.length) continue
    const sorted = [...samples].sort((a, b) => a - b)
    const total = samples.reduce((a, b) => a + b, 0)
    const count = samples.length
    const minVal = sorted[0]
    const maxVal = sorted[sorted.length - 1]
    const avgVal = total / count
    const p95Val = percentile(sorted, 0.95)
    const v = sampleVariability(sorted)
    rows.push({
      channel,
      label: tagChannelLabel(channel),
      count,
      minVal,
      avgVal,
      maxVal,
      jitterVal: v.jitter,
      sigmaVal: v.sigma,
      p50Val: v.p50,
      p95Val,
      p99Val: v.p99,
      min: formatTagValue(minVal),
      avg: formatTagValue(avgVal),
      max: formatTagValue(maxVal),
      jitter: formatTagValue(v.jitter),
      sigma: formatTagValue(v.sigma),
      p50: formatTagValue(v.p50),
      p95: formatTagValue(p95Val),
      p99: formatTagValue(v.p99),
    })
  }
  return rows
}

/** Per-sample detail rows for HTML/CSV export. */
export function tagSampleDetailRows(trace, lo, hi, limit = 200, representations = null) {
  const byCh = trace?.tagSamplesByChannel
  if (!byCh?.size) return []
  const scale = trace?.timeScale || 'ns'
  const rows = []
  for (const channel of trace.tagChannels || []) {
    for (const sample of byCh.get(channel) || []) {
      if (!tagOverlapsRange(sample, lo, hi)) continue
      const value = interpretTagValue(sample.rawValue ?? sample.rawUint32 ?? sample.value, tagRepresentationFor(channel, representations, trace, lo, hi))
      if (!Number.isFinite(value)) continue
      rows.push({
        channel,
        label: tagChannelLabel(channel),
        timeNs: sample.timeNs,
        time: formatTime(sample.timeNs, scale),
        value: formatTagValue(value),
        valueNum: value,
        core: sample.core || '',
      })
    }
  }
  rows.sort((a, b) => b.valueNum - a.valueNum || a.timeNs - b.timeNs)
  return limit > 0 ? rows.slice(0, limit) : rows
}

/** Plot points: x = sample time, y = tag value. */
export function tagPlotPoints(trace, channel, lo, hi, representations = null) {
  const representation = tagRepresentationFor(channel, representations, trace, lo, hi)
  const samples = trace?.tagSamplesByChannel?.get(channel) || []
  return samples
    .filter(s => tagOverlapsRange(s, lo, hi))
    .map(s => ({
      xNs: s.timeNs,
      yValue: interpretTagValue(s.rawValue ?? s.rawUint32 ?? s.value, representation),
      payload: s,
    }))
    .filter(point => Number.isFinite(point.yValue))
}

/**
 * Elapsed time between consecutive samples on one tag channel.
 *
 * Unlike interval_start/stop (paired per task id), tag samples carry no
 * task pairing — consecutive samples on the same channel measure elapsed
 * time regardless of which task/core emitted them, which makes tags the
 * recommended way to measure an interval that spans two different tasks.
 *
 * Plot points: x = later sample time, y = elapsed time since previous sample.
 */
export function tagIntervalPlotPoints(trace, channel, lo, hi) {
  const samples = (trace?.tagSamplesByChannel?.get(channel) || [])
    .filter(s => tagOverlapsRange(s, lo, hi))
  const pts = []
  for (let i = 1; i < samples.length; i++) {
    const gap = samples[i].timeNs - samples[i - 1].timeNs
    if (gap > 0) pts.push({ xNs: samples[i].timeNs, yValue: gap, payload: samples[i] })
  }
  return pts
}
