/**
 * colors.js – Task and core colour helpers.
 *
 * Mirrors the colour logic in btf_viewer.py:
 *   _PALETTE, _CORE_PALETTE, _CORE_TINTS, _SPECIAL_COLORS, _STI_COLORS
 *   and the CRC32-hash task colour assignment.
 */

// 16-colour cycle for tasks (matches Python _PALETTE).
const PALETTE = [
  '#4E9AF1', '#F1884E', '#4EF188', '#F14E9A',
  '#9A4EF1', '#F1D94E', '#4EF1D9', '#F14E4E',
  '#88C057', '#C057C0', '#57C0C0', '#C09057',
  '#7B68EE', '#EE687B', '#68EE7B', '#EEB468',
]

// Per-core header / dot colours.
const CORE_PALETTE = [
  '#FF9933', '#33BBFF', '#66FF88', '#FF66AA',
  '#FFEE44', '#BB77FF', '#44FFEE', '#FF5555',
  '#AADDFF', '#FFBB55', '#88FF44', '#FF88DD',
  '#55DDBB', '#FFAA77', '#99BBFF', '#DDFF77',
]

// Alpha tints applied on top of task colours to hint which core ran a segment.
// Format: [r, g, b, a] (0-255).
const CORE_TINTS = {
  'Core_0': [255, 255, 255,  0],   // no tint
  'Core_1': [  0,   0,  40, 40],   // subtle blue
  'Core_2': [  0,  40,   0, 40],   // subtle green
  'Core_3': [ 40,   0,   0, 40],   // subtle red
  'Core_?': [ 60,  60,  60, 60],   // grey for unknown
}

// Colour overrides for specific task names.
const SPECIAL_COLORS = {
  'TICK': '#E8C84A',
  'IDLE': '#808080',
}

// Fixed colours for well-known STI notes.
const STI_COLORS = {
  'take_mutex':   '#E05050',
  'give_mutex':   '#50C050',
  'create_mutex': '#5080E0',
  'trigger':      '#C08030',
}

// Auto-assigned colours for unknown STI notes (cycle through this list).
const STI_PALETTE = [
  '#FF6B6B', '#FFD93D', '#6BCB77', '#4D96FF',
  '#C77DFF', '#48CAE4', '#F77F00', '#B5E48C',
]

// ---- CRC32 -----------------------------------------------------------------
// Used to deterministically assign palette indices to task names.
// This is a simple table-driven CRC32 (same algorithm as Python's zlib.crc32).

const CRC32_TABLE = (() => {
  const t = new Uint32Array(256)
  for (let i = 0; i < 256; i++) {
    let c = i
    for (let j = 0; j < 8; j++) {
      c = (c & 1) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1)
    }
    t[i] = c
  }
  return t
})()

function crc32(str) {
  let crc = 0xFFFFFFFF
  for (let i = 0; i < str.length; i++) {
    crc = CRC32_TABLE[(crc ^ str.charCodeAt(i)) & 0xFF] ^ (crc >>> 8)
  }
  return (crc ^ 0xFFFFFFFF) >>> 0
}

// ---- Task display-name helpers --------------------------------------------

const TASK_RE = /^\[(\d+)\/(\d+)\](.+)$/
const IDLE_RE = /^idle(?:\s*(\d+))?$/i

function isIdleTaskName(name) {
  return IDLE_RE.test(name)
}

function idleTaskIndex(name) {
  const m = IDLE_RE.exec(name)
  if (m && m[1]) return parseInt(m[1], 10)
  return 0
}

/**
 * Parse a raw BTF task name into { coreId, taskId, name }.
 * Returns { coreId: null, taskId: null, name: raw } for simple names.
 */
export function parseTaskName(raw) {
  const m = TASK_RE.exec(raw)
  if (m) return { coreId: parseInt(m[1]), taskId: parseInt(m[2]), name: m[3].trim() }
  return { coreId: null, taskId: null, name: raw }
}

/**
 * Short display name: 'Name[id]' for regular tasks; bare name for IDLE/TICK.
 */
export function taskDisplayName(raw) {
  const { taskId, name } = parseTaskName(raw)
  if (taskId !== null && !isIdleTaskName(name) && name !== 'TICK') {
    return `${name}[${taskId}]`
  }
  return name
}

/**
 * Stable merge key that ignores core_id.
 * '[0/1]MyTask' and '[1/1]MyTask' return the same key.
 */
export function taskMergeKey(raw) {
  const { taskId, name } = parseTaskName(raw)
  if (taskId !== null) return `\x00${taskId}\x00${name}`
  return raw
}

/**
 * Sorting key: user tasks (1) → IDLE (2) → TICK (3).
 */
export function taskSortKey(raw) {
  const { taskId, name } = parseTaskName(raw)
  let group = 1
  if (isIdleTaskName(name)) group = 2
  else if (name === 'TICK') group = 3
  return [group, taskId ?? 0, name]
}

/**
 * Return an opaque colour string for a task's merge key.
 * Special tasks (IDLE*, TICK) use fixed colours; others use CRC32 → palette.
 */
export function taskColor(mergeKey, repr) {
  const { name } = parseTaskName(repr || mergeKey)
  if (name === 'TICK') return SPECIAL_COLORS['TICK']
  if (isIdleTaskName(name)) {
    // Shade IDLE tasks slightly differently by index.
    const idx = idleTaskIndex(name)
    const v = Math.max(80, 130 - idx * 15)
    return `rgb(${v},${v},${v})`
  }
  const idx = crc32(mergeKey) % PALETTE.length
  return PALETTE[idx]
}

/**
 * Return a CSS rgba() tint string for a core name, or null for Core_0 (no tint).
 */
export function coreTint(coreName) {
  const t = CORE_TINTS[coreName] || CORE_TINTS['Core_?']
  if (t[3] === 0) return null
  return `rgba(${t[0]},${t[1]},${t[2]},${(t[3] / 255).toFixed(3)})`
}

/**
 * Return the dot/header colour for a core name (e.g. 'Core_0').
 */
export function coreColor(coreName) {
  if (coreName.startsWith('Core_')) {
    const tail = coreName.slice(5)
    if (/^\d+$/.test(tail)) return CORE_PALETTE[parseInt(tail) % CORE_PALETTE.length]
  }
  return '#AAAAAA'
}

// Separate caches for STI note and channel colours to avoid name collisions.
const _stiNoteCache    = new Map()
let   _stiNoteIdx      = 0
const _stiChannelCache = new Map()
let   _stiChannelIdx   = 0

/** Reset STI colour assignments between file loads. */
export function resetStiColors() {
  _stiNoteCache.clear()
  _stiNoteIdx    = 0
  _stiChannelCache.clear()
  _stiChannelIdx = 0
}

/** Return a colour for a STI note string. */
export function stiNoteColor(note) {
  if (STI_COLORS[note]) return STI_COLORS[note]
  if (_stiNoteCache.has(note)) return _stiNoteCache.get(note)
  const color = STI_PALETTE[_stiNoteIdx % STI_PALETTE.length]
  _stiNoteIdx++
  _stiNoteCache.set(note, color)
  return color
}

/** Return a colour for a STI channel (target) name. */
export function stiChannelColor(channel) {
  if (_stiChannelCache.has(channel)) return _stiChannelCache.get(channel)
  const color = STI_PALETTE[_stiChannelIdx % STI_PALETTE.length]
  _stiChannelIdx++
  _stiChannelCache.set(channel, color)
  return color
}

export { CORE_PALETTE, PALETTE }

// ---- Segment highlight colour helpers ------------------------------------

function _hexToHsv(cssHex) {
  const m = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(cssHex)
  if (!m) return null
  const r = parseInt(m[1], 16) / 255
  const g = parseInt(m[2], 16) / 255
  const b = parseInt(m[3], 16) / 255
  const max = Math.max(r, g, b), min = Math.min(r, g, b), d = max - min
  let h = 0
  if (d !== 0) {
    if (max === r)      h = (g - b) / d % 6
    else if (max === g) h = (b - r) / d + 2
    else                h = (r - g) / d + 4
    h = h / 6; if (h < 0) h += 1
  }
  return { h, s: max === 0 ? 0 : d / max, v: max, d }
}

function _hsvToHex(h, s, v) {
  const i = Math.floor(h * 6), f = h * 6 - i
  const p = v * (1 - s), q = v * (1 - f * s), t = v * (1 - (1 - f) * s)
  let r, g, b
  switch (i % 6) {
    case 0: r = v; g = t; b = p; break
    case 1: r = q; g = v; b = p; break
    case 2: r = p; g = v; b = t; break
    case 3: r = p; g = q; b = v; break
    case 4: r = t; g = p; b = v; break
    case 5: r = v; g = p; b = q; break
    default: r = 0; g = 0; b = 0
  }
  const x = n => Math.round(n * 255).toString(16).padStart(2, '0')
  return `#${x(r)}${x(g)}${x(b)}`
}

/**
 * Return a CSS hex colour lighter than cssHex by multiplying HSV value by factor.
 */
export function lighterColor(cssHex, factor = 1.6) {
  const hsv = _hexToHsv(cssHex)
  if (!hsv) return cssHex
  return _hsvToHex(hsv.h, hsv.s, Math.min(1, hsv.v * factor))
}

/**
 * Return the complementary (hue-opposite, boosted saturation/value) of cssHex.
 * Falls back to gold for achromatic colours.
 */
export function complementaryColor(cssHex) {
  const hsv = _hexToHsv(cssHex)
  if (!hsv || hsv.d < 0.01) return '#FFD700'
  return _hsvToHex(
    (hsv.h + 0.5) % 1,
    Math.max(hsv.s, 0.85),
    Math.max(hsv.v, 0.90),
  )
}
