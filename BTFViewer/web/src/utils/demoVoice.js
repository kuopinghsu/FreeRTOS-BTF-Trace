/**
 * Demo narration language: path candidates and picker helpers.
 *
 * Clips live at ``voice/<lang>/<file>`` with fallback to flat ``voice/<file>``
 * (the shipped English layout).
 */

export function normalizeVoiceLang(raw) {
  const s = String(raw || '').trim().replace(/_/g, '-').toLowerCase()
  if (!s) return ''
  const [a, b] = s.split('-')
  if (a === 'zh' && (b === 'tw' || b === 'hant' || b === 'hk' || b === 'mo')) return 'zh-tw'
  if (a === 'zh' && (b === 'cn' || b === 'sg' || b === 'hans')) return 'zh'
  return a || ''
}

export function pickVoiceLang(preferred, available, fallback = 'en') {
  const ids = (available || []).map(normalizeVoiceLang).filter(Boolean)
  const want = normalizeVoiceLang(preferred)
  if (want && ids.includes(want)) return want
  if (want) {
    const prefix = want.split('-')[0]
    const hit = ids.find(id => id === prefix || id.startsWith(`${prefix}-`))
    if (hit) return hit
  }
  const fb = normalizeVoiceLang(fallback) || 'en'
  if (ids.includes(fb)) return fb
  if (ids.includes('en')) return 'en'
  return ids[0] || fb
}

function normalizeRel(rel) {
  return String(rel || '')
    .replace(/\\/g, '/')
    .replace(/^\.\//, '')
    .replace(/\/{2,}/g, '/')
}

/**
 * Alternate relative paths for a ``voice/`` clip, preferred language first.
 * @param {string} rel
 * @param {string} lang
 * @param {string} [defaultLang]
 * @returns {string[]}
 */
export function voicePathCandidates(rel, lang, defaultLang = 'en') {
  const n = normalizeRel(rel)
  if (!n) return []
  const parts = n.split('/')
  const voiceIdx = parts.findIndex(p => p.toLowerCase() === 'voice')
  const out = []
  const add = (p) => {
    const s = normalizeRel(p)
    if (s && !out.includes(s)) out.push(s)
  }
  if (voiceIdx < 0) {
    add(n)
    return out
  }
  const prefix = parts.slice(0, voiceIdx + 1).join('/')
  const rest = parts.slice(voiceIdx + 1)
  let basename = rest.join('/')
  if (rest.length >= 2 && /^[a-z]{2}(?:-[a-z0-9]+)?$/i.test(rest[0])) {
    basename = rest.slice(1).join('/')
  }
  const langN = normalizeVoiceLang(lang)
  const defN = normalizeVoiceLang(defaultLang) || 'en'
  if (langN) add(`${prefix}/${langN}/${basename}`)
  add(`${prefix}/${basename}`)
  if (defN && defN !== langN) add(`${prefix}/${defN}/${basename}`)
  add(n)
  return out
}

export function discoverVoiceLangs(files) {
  const found = new Set()
  let flatDefault = false
  for (const key of files instanceof Map ? files.keys() : Object.keys(files || {})) {
    const n = normalizeRel(key)
    const nested = n.match(/(?:^|\/)voice\/([^/]+)\/[^/]+\.(mp3|wav|m4a|ogg|flac|aiff|aif)$/i)
    if (nested) {
      found.add(normalizeVoiceLang(nested[1]))
      continue
    }
    if (/(?:^|\/)voice\/[^/]+\.(mp3|wav|m4a|ogg|flac|aiff|aif)$/i.test(n)) flatDefault = true
  }
  if (flatDefault) found.add('en')
  return [...found].filter(Boolean)
}

export function mergeVoiceLangs(parsedLangs, discovered) {
  const base = parsedLangs?.list?.length
    ? parsedLangs.list.map(x => ({ ...x }))
    : [{ id: 'en', label: 'English' }]
  const labels = {
    en: 'English',
    zh: '简体中文',
    'zh-tw': '中文',
    ja: '日本語',
    ko: '한국어',
    de: 'Deutsch',
    fr: 'Français',
    es: 'Español',
  }
  for (const id of discovered || []) {
    const n = normalizeVoiceLang(id)
    if (n && !base.some(x => x.id === n)) base.push({ id: n, label: labels[n] || n })
  }
  const defaultId = parsedLangs?.defaultId || 'en'
  return { defaultId: base.some(x => x.id === defaultId) ? defaultId : base[0].id, list: base }
}
