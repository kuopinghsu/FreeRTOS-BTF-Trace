/**
 * Parse BTFViewer demo XML (same schema as scripts/demo_runner.py).
 * Stack parser — no DOMParser — so Node tests can import this module.
 */

import { NS_PER_UNIT, nsToTraceUnits } from './timeFormat.js'
import { normalizeVoiceLang } from './demoVoice.js'

const VAR_RE = /\$\{([A-Za-z0-9_./-]+)\}/g
const ATTR_RE = /([A-Za-z_][\w:.-]*)\s*=\s*(?:"([^"]*)"|'([^']*)')/g

export function stripXmlComments(text) {
  return String(text || '').replace(/<!--[\s\S]*?-->/g, '')
}

export function expandVars(text, vars = {}) {
  let out = String(text ?? '')
  for (let i = 0; i < 8; i++) {
    const nxt = out.replace(VAR_RE, (m, key) => (
      Object.prototype.hasOwnProperty.call(vars, key) ? String(vars[key]) : m
    ))
    if (nxt === out) break
    out = nxt
  }
  return out
}

export function truthy(value, defaultValue = false) {
  if (value == null || value === '') return defaultValue
  if (typeof value === 'boolean') return value
  if (typeof value === 'number') return Boolean(value)
  return !['0', 'false', 'no', 'off'].includes(String(value).trim().toLowerCase())
}

function parseAttrs(raw) {
  const out = {}
  ATTR_RE.lastIndex = 0
  let m
  while ((m = ATTR_RE.exec(raw || ''))) out[m[1]] = m[2] ?? m[3] ?? ''
  return out
}

function textOf(el) {
  if (!el) return ''
  const parts = [el.text || '']
  for (const child of el.children || []) {
    parts.push(textOf(child))
    parts.push(child.tail || '')
  }
  return parts.join('').trim()
}

/**
 * @param {string} xml
 * @returns {{ tag: string, attrib: Record<string,string>, children: object[], text: string, tail: string }}
 */
export function parseXmlRoot(xml) {
  const src = stripXmlComments(xml).replace(/<\?xml[\s\S]*?\?>/i, '').trim()
  const root = { tag: '#doc', attrib: {}, children: [], text: '', tail: '' }
  const stack = [root]
  const re = /<(\/)?([A-Za-z_][\w:.-]*)([^>]*?)(\/)?>|([^<]+)/g
  let m
  while ((m = re.exec(src))) {
    const parent = stack[stack.length - 1]
    if (m[5] != null) {
      const chunk = m[5]
      if (parent.children.length) {
        const last = parent.children[parent.children.length - 1]
        last.tail = (last.tail || '') + chunk
      } else {
        parent.text += chunk
      }
      continue
    }
    const closing = !!m[1]
    const tag = m[2]
    const selfClose = !!m[4] || /\/\s*$/.test(m[3] || '')
    if (closing) {
      if (stack.length > 1 && stack[stack.length - 1].tag === tag) stack.pop()
      continue
    }
    const el = { tag, attrib: parseAttrs(m[3]), children: [], text: '', tail: '' }
    parent.children.push(el)
    if (!selfClose) stack.push(el)
  }
  const demo = root.children.find(c => c.tag === 'demo')
  if (!demo) throw new Error('root element must be <demo>')
  return demo
}

function child(el, tag) {
  return (el?.children || []).find(c => c.tag === tag) || null
}

function children(el, tag) {
  return (el?.children || []).filter(c => c.tag === tag)
}

export function parseDefaults(root) {
  const el = child(root, 'defaults')
  const a = el?.attrib || {}
  return {
    after_voice: Number(a.after_voice ?? 1.5),
    pause: Number(a.pause ?? 0.8),
    ai_wait: Number(a.ai_wait ?? 35),
    move_duration: Number(a.move_duration ?? 0.35),
    audio_block: truthy(a.audio_block, false),
  }
}

export function parseMacros(root) {
  const out = {}
  const wrap = child(root, 'macros')
  if (!wrap) return out
  for (const el of children(wrap, 'macro')) {
    const name = (el.attrib.name || '').trim()
    if (name) out[name] = el.children || []
  }
  return out
}

export function parseSteps(root) {
  const wrap = child(root, 'steps')
  if (!wrap) return []
  return children(wrap, 'step').map(el => ({
    id: el.attrib.id || '?',
    title: el.attrib.title || '',
    optional: truthy(el.attrib.optional, false),
    tags: new Set(
      String(el.attrib.tags || '').split(',').map(t => t.trim()).filter(Boolean),
    ),
    children: el.children || [],
  }))
}

export function buildVariables(root, { xmlDir = '.', extras = {} } = {}) {
  const vars = {
    XML_DIR: xmlDir,
    XML: xmlDir,
    CWD: xmlDir,
    REPO: xmlDir,
    BTF: xmlDir,
    HOME: xmlDir,
    PYTHON: 'python3',
    MOD: 'mod',
    ...extras,
  }
  const meta = child(root, 'meta')
  if (meta) {
    for (const el of meta.children || []) {
      if (['title', 'description', 'author', 'languages'].includes(el.tag)) continue
      if (el.tag === 'var') {
        const name = (el.attrib.name || '').trim()
        if (name) vars[name] = expandVars(textOf(el) || el.attrib.value || '', vars)
        continue
      }
      vars[el.tag] = expandVars(textOf(el) || el.attrib.value || '', vars)
    }
  }
  Object.assign(vars, extras)
  for (let i = 0; i < 3; i++) {
    for (const [k, v] of Object.entries(vars)) vars[k] = expandVars(v, vars)
  }
  return vars
}

export function parseLanguages(root) {
  const wrap = child(root, 'languages') || child(child(root, 'meta'), 'languages')
  const list = []
  let defaultId = 'en'
  if (wrap) {
    defaultId = normalizeVoiceLang(wrap.attrib.default || wrap.attrib.lang || 'en') || 'en'
    for (const el of children(wrap, 'language')) {
      const id = normalizeVoiceLang(el.attrib.id || el.attrib.lang || '')
      if (!id) continue
      const label = String(el.attrib.label || el.attrib.name || id).trim() || id
      if (!list.some(x => x.id === id)) list.push({ id, label })
    }
  }
  if (!list.length) list.push({ id: 'en', label: 'English' })
  if (!list.some(x => x.id === defaultId)) defaultId = list[0].id
  return { defaultId, list }
}

export function parseTargets(root) {
  const wrap = child(root, 'targets')
  const out = {}
  if (!wrap) return out
  for (const pt of children(wrap, 'point')) {
    const name = (pt.attrib.name || '').trim()
    if (!name) continue
    out[name] = { x: Number(pt.attrib.x), y: Number(pt.attrib.y) }
  }
  return out
}

function queryDemoTargetRect(name, lookup) {
  if (!name) return null
  if (typeof lookup === 'function') {
    const node = lookup(name)
    if (node?.getBoundingClientRect) {
      const r = node.getBoundingClientRect()
      if (r && r.width > 0 && r.height > 0) return r
    }
    if (node && Number.isFinite(Number(node.left)) && Number.isFinite(Number(node.width))) {
      return node
    }
  }
  if (typeof document === 'undefined') return null
  try {
    const esc = (typeof CSS !== 'undefined' && CSS.escape)
      ? CSS.escape(name)
      : String(name).replace(/["\\]/g, '')
    const nodes = document.querySelectorAll(`[data-demo-target="${esc}"]`)
    let fallback = null
    for (const node of nodes) {
      const r = node.getBoundingClientRect?.()
      if (!r || !(r.width > 0) || !(r.height > 0)) continue
      // Prefer toolbar icons that are not parked in the closed overflow menu.
      if (node.closest?.('.tb-overflow-panel')) {
        if (!fallback) fallback = r
        continue
      }
      return r
    }
    return fallback
  } catch {
    /* ignore invalid selectors */
  }
  return null
}

/**
 * Resolve a move/click element to client pixels (same rules as desktop resolve_xy).
 * Live `data-demo-target` geometry wins over XML window fractions.
 * Fractions are relative to *box*; values with abs > 1 are treated as pixels.
 */
export function resolveDemoXy(el, targets, box, lookup) {
  const name = (el?.attrib?.target || '').trim()
  if (name) {
    const r = queryDemoTargetRect(name, lookup)
    const w = Number(r?.width)
    const h = Number(r?.height)
    if (r && w > 0 && h > 0) {
      return {
        x: Math.round(Number(r.left) + w / 2),
        y: Math.round(Number(r.top) + h / 2),
      }
    }
  }
  const left = Number(box?.left) || 0
  const top = Number(box?.top) || 0
  const width = Number(box?.width) || 0
  const height = Number(box?.height) || 0
  let fx
  let fy
  if (name) {
    const pt = targets?.[name]
    if (!pt) return null
    fx = Number(pt.x)
    fy = Number(pt.y)
  } else {
    fx = Number(el?.attrib?.x ?? 0.5)
    fy = Number(el?.attrib?.y ?? 0.5)
  }
  if (!Number.isFinite(fx) || !Number.isFinite(fy) || width <= 0 || height <= 0) return null
  const x = Math.abs(fx) > 1 ? left + fx : left + fx * width
  const y = Math.abs(fy) > 1 ? top + fy : top + fy * height
  return { x: Math.round(x), y: Math.round(y) }
}

/**
 * @param {string} xml
 * @param {{ xmlDir?: string, extras?: Record<string,string> }} [opts]
 */
export function parseDemoXml(xml, opts = {}) {
  const root = parseXmlRoot(xml)
  const meta = child(root, 'meta')
  const vars = buildVariables(root, opts)
  return {
    name: root.attrib.name || '',
    version: root.attrib.version || '1',
    title: textOf(child(meta, 'title')),
    description: textOf(child(meta, 'description')),
    trace: vars.trace || '',
    vars,
    defaults: parseDefaults(root),
    languages: parseLanguages(root),
    macros: parseMacros(root),
    targets: parseTargets(root),
    steps: parseSteps(root),
  }
}

const UNIT_NS = {
  s: NS_PER_UNIT.s,
  sec: NS_PER_UNIT.s,
  secs: NS_PER_UNIT.s,
  second: NS_PER_UNIT.s,
  seconds: NS_PER_UNIT.s,
  ms: NS_PER_UNIT.ms,
  msec: NS_PER_UNIT.ms,
  millisecond: NS_PER_UNIT.ms,
  milliseconds: NS_PER_UNIT.ms,
  us: NS_PER_UNIT.us,
  µs: NS_PER_UNIT.us,
  μs: NS_PER_UNIT.us,
  usec: NS_PER_UNIT.us,
  microsecond: NS_PER_UNIT.us,
  microseconds: NS_PER_UNIT.us,
  ns: NS_PER_UNIT.ns,
  nsec: NS_PER_UNIT.ns,
  nanosecond: NS_PER_UNIT.ns,
  nanoseconds: NS_PER_UNIT.ns,
}

/**
 * Convert a demo timestamp into trace-native units (same as timeline cursors).
 * @param {string|number} raw
 * @param {string} unit
 * @param {string} timeScale
 */
export function demoTimeToTraceUnits(raw, unit = '', timeScale = 'ns') {
  const scale = timeScale || 'ns'
  const unitL = String(unit || '').trim().toLowerCase()
  const text = String(raw ?? '').trim()
  if (!text) throw new Error('empty time')
  const native = !unitL || ['trace', 'tu', 'native'].includes(unitL)
  const hasUnitToken = /[a-zA-Zµμ]/.test(text)
  if (native && !hasUnitToken) return Math.round(Number(text))
  let ns
  if (hasUnitToken) {
    const m = text.match(/^([+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?)\s*([a-zA-Zµμ]+)$/i)
    if (!m) throw new Error(`bad time ${raw}`)
    const per = UNIT_NS[m[2].toLowerCase()]
    if (per == null) throw new Error(`unknown time unit ${m[2]}`)
    ns = Number(m[1]) * per
  } else {
    const per = UNIT_NS[unitL]
    if (per == null) throw new Error(`unknown time unit ${unit}`)
    ns = Number(text) * per
  }
  if (!Number.isFinite(ns)) throw new Error(`bad time ${raw}`)
  return Math.round(nsToTraceUnits(ns, scale))
}

export function splitCsv(raw) {
  return String(raw || '')
    .replace(/;/g, ',')
    .split(',')
    .map(s => s.trim())
    .filter(Boolean)
}

export function elementText(el) {
  return textOf(el)
}
