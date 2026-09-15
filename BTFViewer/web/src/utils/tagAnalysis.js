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
  { value: 'uint32', label: 'UInt32', title: 'Unsigned integer' },
  { value: 'int32', label: 'Int32', title: 'Signed integer' },
  { value: 'float32', label: 'Float32', title: 'IEEE 754 bit interpretation' },
])

export function normalizeTagAlias(value) {
  return typeof value === 'string' ? Array.from(value.replace(/[\r\n\t]/g, ' ').trim()).slice(0, 80).join('') : ''
}
export function tagAlias(channel, representations) {
  return normalizeTagAlias(representations?.[channel]?.alias)
}

export function tagPreferences(value) {
  if (typeof value === 'string') return { format: value === 'log2-uint32' ? 'uint32' : normalizeTagRepresentation(value), scale: value === 'log2-uint32' ? 'log2' : 'linear', includeZero: false }
  const alias = normalizeTagAlias(value?.alias)
  return { format: normalizeTagRepresentation(value?.format), scale: value?.scale === 'log2' ? 'log2' : 'linear', includeZero: value?.includeZero === true, ...(alias ? { alias } : {}) }
}
export function normalizeTagRepresentation(value) {
  return ['uint32', 'int32', 'float32'].includes(value) ? value : 'uint32'
}
// Smallest positive subnormal float32 magnitude (2**-149) — float32's own
// resolution floor. Used as the linear-threshold constant for the float32
// log2 scale below: since |value| >> FLOAT32_LOG_FLOOR for essentially any
// representable float32 (subnormal or normal), log2(1 + |value| / floor)
// reduces to log2(|value|) shifted by a constant, without the degeneracy a
// threshold of 1 would cause (see tagTransform).
const FLOAT32_LOG_FLOOR = 2 ** -149

/**
 * `log2(1 + |value|)` reads as a genuine log SCALE for large-magnitude
 * integers (uint32/int32 bit patterns): it behaves ~linearly near zero and
 * compresses the long tail, and stays invertible because its argument never
 * drops below 1. A float32 payload is usually far below 1 in magnitude (raw
 * bits reinterpreted as float32 land in the subnormal range, ~1e-40), where
 * `log1p(x) ≈ x` — the "+1" swamps the value entirely and the transform
 * degenerates into a constant multiple of the input (1/ln2), i.e. visually
 * identical to linear. Float32 instead divides by its own resolution floor
 * before adding 1, which keeps the same always-invertible shape while
 * actually compressing that range.
 */
export function tagTransform(value, preferences) {
  const prefs = tagPreferences(preferences)
  if (prefs.scale !== 'log2') return value
  if (prefs.format === 'float32') {
    return value === 0 ? 0 : Math.sign(value) * Math.log2(1 + Math.abs(value) / FLOAT32_LOG_FLOOR)
  }
  return Math.sign(value) * Math.log1p(Math.abs(value)) / Math.LN2
}
export function tagInverse(value, preferences) {
  const prefs = tagPreferences(preferences)
  if (prefs.scale !== 'log2') return value
  if (prefs.format === 'float32') {
    return value === 0 ? 0 : Math.sign(value) * (FLOAT32_LOG_FLOOR * (2 ** Math.abs(value) - 1))
  }
  return Math.sign(value) * Math.expm1(Math.abs(value) * Math.LN2)
}
export function tagAxisBounds(values, preferences) {
  const finite = values.filter(Number.isFinite)
  let lo = Infinity, hi = -Infinity
  for (const value of finite) { lo = Math.min(lo, value); hi = Math.max(hi, value) }
  if (!finite.length) return [0, 1]
  if (tagPreferences(preferences).includeZero) { lo = Math.min(0, lo); hi = Math.max(0, hi) }
  if (lo === hi) { const pad = Math.abs(lo) * 0.05 || 0.5; lo -= pad; hi += pad }
  return [lo, hi]
}
export function updateTagPreferences(value, command) {
  const p = tagPreferences(value)
  if (command === 'reset') return p.alias ? { ...tagPreferences(null), alias: p.alias } : null
  if (command.startsWith('alias:')) {
    const alias = normalizeTagAlias(command.slice(6))
    if (alias) p.alias = alias
    else delete p.alias
    return p
  }
  if (command === 'zero') p.includeZero = !p.includeZero
  else if (command === 'linear' || command === 'log2') p.scale = command
  else if (['uint32', 'int32', 'float32'].includes(command)) p.format = command
  return p
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
  switch (tagPreferences(representation).format) {
    case 'int32': return bits | 0
    case 'float32': {
      FLOAT32_VIEW.setUint32(0, bits, false)
      const value = FLOAT32_VIEW.getFloat32(0, false)
      return Number.isFinite(value) ? value : null
    }
    default: return bits
  }
}

export function tagRepresentationFor(channel, representations, _trace = null, _lo = null, _hi = null) {
  if (representations?.[channel]) return tagPreferences(representations[channel]).format
  return 'uint32'
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

export function tagChannelLabel(channel, representations = null) {
  const alias = tagAlias(channel, representations)
  if (alias) return alias
  const m = TAG_CHANNEL_RE.exec(channel || '')
  if (!m) return channel
  const digit = m[1]
  return digit != null ? `Tag ${digit}` : 'Tag'
}

/** Resolve display aliases while retaining all matching canonical channels. */
export function matchingTagChannels(trace, query, mode = 'contains', representations = trace?.tagRepresentations) {
  const q = String(query || '').trim()
  if (!q) return []
  let regex = null
  if (mode === 'regex') {
    if (q.length > 1024) return []
    try { regex = new RegExp(q, 'i') } catch { return [] }
  }
  return (trace?.tagChannels || []).filter(channel => {
    const names = [channel, tagChannelLabel(channel), tagAlias(channel, representations)].filter(Boolean)
    return names.some(name => regex ? regex.test(name) : mode === 'exact' ? name.toLowerCase() === q.toLowerCase() : name.toLowerCase().includes(q.toLowerCase()))
  })
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
      label: tagChannelLabel(channel, representations),
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
        label: tagChannelLabel(channel, representations),
        timeNs: sample.timeNs,
        time: formatTime(sample.timeNs, scale),
        value: formatTagValue(value),
        valueNum: value,
        preferences: tagPreferences(representations?.[channel]),
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
