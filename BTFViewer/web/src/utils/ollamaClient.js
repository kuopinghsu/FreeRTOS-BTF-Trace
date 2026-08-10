/**
 * Ollama client + diagnostic prompt templates for the web AI Assistant.
 * Keep template prompts in sync with btf_viewer_pkg/ai_assistant.py
 * (documented in README.md § AI Assistant).
 */

import {
  AI_TOOL_SYSTEM_ADDENDUM,
  aiViewerTools,
  extractToolCalls,
  mergeToolCalls,
  messageContentText,
  parseToolCallsFromText,
  stripParsedToolMarkup,
  summariseToolCall,
} from './aiTools.js'

export const AI_SYSTEM_PROMPT =
  'You are an expert Real-Time Operating System (RTOS) and SMP trace analysis ' +
  'assistant for FreeRTOS BTF traces. Analyse the provided structured metrics ' +
  'and answer the user\'s diagnostic question clearly. Focus on root causes ' +
  '(preemption, priority inversion, lock contention, core thrashing, switch ' +
  'overhead, tick health). Prefer concrete task names, cores, and durations. ' +
  'When mentioning a time, write it as jump:TIME where TIME is the numeric ' +
  'value in the trace time unit (e.g. jump:1805120). Keep answers concise. '
  + AI_TOOL_SYSTEM_ADDENDUM

/** Preferred reply languages — keep in sync with btf_viewer_pkg/ai_assistant.py */
export const DEFAULT_AI_RESPONSE_LANGUAGE = 'English'
export const AI_RESPONSE_LANGUAGES = [
  'English',
  'Traditional Chinese (繁體中文)',
  'Simplified Chinese (简体中文)',
  'Japanese (日本語)',
  'Korean (한국어)',
  'German',
  'French',
  'Spanish',
  'Klingon (tlhIngan Hol)',
]

/** Keep in sync with btf_viewer_pkg/ai_assistant.py (seconds). */
export const AI_CHAT_TIMEOUT_MS = 120000
export const AI_LIST_MODELS_TIMEOUT_MS = 12000
export const AI_TEST_TIMEOUT_MS = 60000

export function buildAiSystemPrompt(responseLanguage = DEFAULT_AI_RESPONSE_LANGUAGE) {
  const lang = String(responseLanguage || DEFAULT_AI_RESPONSE_LANGUAGE).trim()
    || DEFAULT_AI_RESPONSE_LANGUAGE
  return `${AI_SYSTEM_PROMPT} Always write your entire reply in ${lang}.`
}

export const AI_COMPARE_TEMPLATE_ID = 'compare'

/** @type {{ id: string, label: string, prompt: string }[]} */
export const AI_TEMPLATE_QUESTIONS = [
  {
    id: 'findings',
    label: 'Analysis Findings',
    prompt:
      'Walk through the Analysis Findings in the context. For each finding, ' +
      'state its severity, what it means for this RTOS/SMP system, and which ' +
      'Statistics section or timeline check to open next. If there are no ' +
      'findings, say so and suggest a default top-down inspection order.',
  },
  {
    id: AI_COMPARE_TEMPLATE_ID,
    label: 'Trace Compare',
    prompt:
      'Compare Trace A vs Trace B using the Trace Compare tables in the ' +
      'context. Highlight the largest deltas (CPU, migrations, latency, ' +
      'tick health, sync). Say which side is worse for each concern and ' +
      'which Statistics section or Trace Compare page to open next.',
  },
  {
    id: 'triage',
    label: 'Triage findings',
    prompt:
      'Summarise the Analysis Findings and list the top three issues to ' +
      'investigate first, with the Statistics section to open for each.',
  },
  {
    id: 'latency',
    label: 'Highest latency',
    prompt:
      'Which tasks show the highest latency or blocking? Explain likely ' +
      'causes using preemption, dispatch latency, and mutex evidence in ' +
      'the context.',
  },
  {
    id: 'wcet',
    label: 'WCET / hot CPU',
    prompt:
      'Which tasks dominate CPU and which have the worst execution-slice ' +
      'Max? Recommend whether to affinity-pin, reduce fan-out, or inspect ' +
      'preemption.',
  },
  {
    id: 'migrations',
    label: 'Migration thrash',
    prompt:
      'Is there core thrashing or lock-bounce? Cite migration rate, ping, ' +
      'dwell, and any hot mutex/queue bounces. Suggest affinity or ' +
      'ownership fixes.',
  },
  {
    id: 'balance',
    label: 'Core balance',
    prompt:
      'Is SMP load balance healthy? Interpret Load Balance Score / σ and ' +
      'whether Concurrent Core Active or Switch Overhead needs attention.',
  },
  {
    id: 'tick',
    label: 'Tick health',
    prompt:
      'Interpret Trace Health (TICK). Are large gaps expected under ' +
      'tickless idle, or should we re-check inside a busy cursor window?',
  },
  {
    id: 'priority',
    label: 'Priority inversion',
    prompt:
      'Is there priority inversion or L/M/H geometry? Explain any inherit ' +
      'episodes and what to verify next.',
  },
  {
    id: 'deadlines',
    label: 'Deadline / budget',
    prompt:
      'Are there deadline or CPU-budget concerns in the findings? What ' +
      'should the engineer measure next?',
  },
]

// Every provider is reached over its OpenAI-compatible /chat/completions API,
// including Ollama (http://localhost:11434/v1).
export const AI_PRESET_CUSTOM = 'custom'
export const AI_PRESET_OLLAMA = 'ollama'
export const AI_PRESET_OPENAI = 'openai'
export const AI_PRESET_GEMINI = 'gemini'

/** @type {{ id: string, label: string, baseUrl: string, model: string }[]} */
export const AI_PRESETS = [
  { id: AI_PRESET_CUSTOM, label: 'Custom', baseUrl: '', model: '' },
  {
    id: AI_PRESET_OLLAMA,
    label: 'Ollama',
    baseUrl: 'http://localhost:11434/v1',
    model: 'phi4-mini:3.8b',
  },
  {
    id: AI_PRESET_OPENAI,
    label: 'OpenAI',
    baseUrl: 'https://api.openai.com/v1',
    model: 'gpt-4o-mini',
  },
  {
    id: AI_PRESET_GEMINI,
    label: 'Google Gemini',
    baseUrl: 'https://generativelanguage.googleapis.com/v1beta/openai',
    // Rolling alias: concrete versions come and go per account/tier.
    model: 'gemini-flash-lite-latest',
  },
]

export const DEFAULT_AI_PRESET = AI_PRESET_OLLAMA
export const DEFAULT_AI_BASE_URL = 'http://localhost:11434/v1'
export const DEFAULT_AI_MODEL = 'phi4-mini:3.8b'

/** Per-preset settings stored in browser storage (parity with btf_viewer.rc). */
export const AI_PRESET_FIELDS = ['baseUrl', 'model', 'apiKey']

/** Vite same-origin proxy prefix per preset (avoids browser CORS). */
export const AI_PRESET_PROXY_PATHS = {
  [AI_PRESET_OLLAMA]: '/ollama',
  [AI_PRESET_OPENAI]: '/proxy/openai',
  [AI_PRESET_GEMINI]: '/proxy/gemini',
}

/**
 * Hosts that serve a local model and therefore need no API key.
 * Keep in sync with LOCAL_AI_HOSTS in btf_viewer_pkg/ai_assistant.py.
 */
export const LOCAL_AI_HOSTS = [
  'localhost',
  '127.0.0.1',
  '0.0.0.0',
  '::1',
  'host.docker.internal',
]

/** Where each vendor issues API keys (shown as a Settings hint). */
export const AI_PRESET_KEY_URLS = {
  [AI_PRESET_OPENAI]: 'https://platform.openai.com/api-keys',
  [AI_PRESET_GEMINI]: 'https://aistudio.google.com/apikey',
}

/** Map a stored/legacy preset id onto one of the known presets. */
export function normalizeAiPreset(presetId) {
  const want = String(presetId || DEFAULT_AI_PRESET).trim().toLowerCase().replace(/-/g, '_')
  if (AI_PRESETS.some((p) => p.id === want)) return want
  if (want === 'google' || want === 'google_gemini' || want === 'gemini_openai') {
    return AI_PRESET_GEMINI
  }
  if (want === 'ollama_cloud' || want === 'local') return AI_PRESET_OLLAMA
  if (want === 'chatgpt' || want === 'open_ai') return AI_PRESET_OPENAI
  return AI_PRESET_CUSTOM
}

export function aiPresetInfo(presetId) {
  const want = normalizeAiPreset(presetId)
  return AI_PRESETS.find((p) => p.id === want) || AI_PRESETS[0]
}

/** Base URL / model to fill in when the user picks a preset. */
export function applyAiPreset(presetId) {
  const p = aiPresetInfo(presetId)
  return { preset: p.id, baseUrl: p.baseUrl, model: p.model }
}

/**
 * Active preset plus its stored base URL / model / API key, falling back to
 * the preset defaults. Pass *presetId* to read a preset other than the active.
 */
export function resolveAiSettings(cfg = {}, presetId = null) {
  const c = cfg && typeof cfg === 'object' ? cfg : {}
  const preset = normalizeAiPreset(presetId == null ? c.aiPreset : presetId)
  const info = aiPresetInfo(preset)
  const stored = (c.aiPresets || {})[preset] || {}
  return {
    preset,
    baseUrl: String(stored.baseUrl || '') || info.baseUrl,
    model: String(stored.model || '') || info.model,
    apiKey: String(stored.apiKey || ''),
  }
}

/** Preset that owns the retired `openai*` fields. */
function legacyOpenaiTarget(legacyPreset, legacyBaseUrl) {
  const want = String(legacyPreset || '').trim().toLowerCase().replace(/-/g, '_')
  if (want === 'gemini' || want === 'google' || want === 'google_gemini') return AI_PRESET_GEMINI
  if (want === 'openai' || want === 'chatgpt') return AI_PRESET_OPENAI
  if (want) return AI_PRESET_CUSTOM
  const host = normalizeAiBaseUrl(legacyBaseUrl).toLowerCase()
  if (host.includes('api.openai.com')) return AI_PRESET_OPENAI
  if (host.includes('generativelanguage')) return AI_PRESET_GEMINI
  return AI_PRESET_CUSTOM
}

/**
 * Move pre-preset settings (one provider with separate Ollama and OpenAI
 * fields) onto the per-preset shape. Returns null when nothing to migrate.
 */
export function migrateAiSettings(saved = {}) {
  const s = saved && typeof saved === 'object' ? saved : {}
  const legacyPreset = String(s.openaiPreset || '').trim().toLowerCase()
  const openaiTarget = legacyOpenaiTarget(legacyPreset, String(s.openaiBaseUrl || ''))
  const presets = {}
  const keep = (preset, field, value) => {
    const has = ((s.aiPresets || {})[preset] || {})[field]
    if (value && !String(has || '').trim()) {
      presets[preset] = { ...(presets[preset] || {}), [field]: value }
    }
  }

  const oldOllamaUrl = String(s.ollamaUrl || '').trim()
  if (oldOllamaUrl) keep(AI_PRESET_OLLAMA, 'baseUrl', normalizeAiBaseUrl(oldOllamaUrl))
  keep(AI_PRESET_OLLAMA, 'model', String(s.ollamaModel || '').trim())
  keep(AI_PRESET_OLLAMA, 'apiKey', String(s.ollamaApiKey || '').trim())

  const oldOpenaiUrl = String(s.openaiBaseUrl || '').trim()
  if (oldOpenaiUrl) keep(openaiTarget, 'baseUrl', normalizeAiBaseUrl(oldOpenaiUrl))
  keep(openaiTarget, 'model', String(s.openaiModel || '').trim())
  keep(openaiTarget, 'apiKey', String(s.openaiApiKey || '').trim())

  const out = {}
  if (Object.keys(presets).length) out.aiPresets = presets
  if (!String(s.aiPreset || '').trim()) {
    const provider = String(s.aiProvider || '').trim().toLowerCase().replace(/-/g, '_')
    if (provider && provider !== 'ollama') out.aiPreset = openaiTarget
    else if (provider || oldOllamaUrl) out.aiPreset = AI_PRESET_OLLAMA
  }
  return Object.keys(out).length ? out : null
}

// Preset ids accepted by an import file beyond the current ones; older exports
// and vendor names map onto an existing preset.
export const AI_IMPORT_PRESET_ALIASES = {
  chatgpt: AI_PRESET_OPENAI,
  open_ai: AI_PRESET_OPENAI,
  openai_compatible: AI_PRESET_CUSTOM,
  xai: AI_PRESET_CUSTOM,
  grok: AI_PRESET_CUSTOM,
  deepseek: AI_PRESET_CUSTOM,
  google: AI_PRESET_GEMINI,
  google_gemini: AI_PRESET_GEMINI,
}

function jsonStr(obj, ...names) {
  for (const name of names) {
    const value = obj?.[name]
    if (value != null && typeof value !== 'object') {
      const text = String(value).trim()
      if (text) return text
    }
  }
  return ''
}

/** Preset id for an import file, rejecting names we cannot place. */
function importPresetId(raw) {
  const want = String(raw).trim().toLowerCase().replace(/[-\s]/g, '_')
  const hit = AI_PRESETS.find(
    (p) => want === p.id || want === p.label.toLowerCase().replace(/\s/g, '_'),
  )
  if (hit) return hit.id
  if (AI_IMPORT_PRESET_ALIASES[want]) return AI_IMPORT_PRESET_ALIASES[want]
  const valid = AI_PRESETS.map((p) => p.id).join(', ')
  throw new Error(`Unknown preset "${raw}". Use one of: ${valid}.`)
}

/** Guess the preset when the file only carries a base URL. */
function importPresetFromUrl(baseUrl) {
  const host = normalizeAiBaseUrl(baseUrl).toLowerCase()
  if (isLocalAiHost(host)) return AI_PRESET_OLLAMA
  if (host.includes('generativelanguage') || host.includes('gemini')) return AI_PRESET_GEMINI
  if (host.includes('api.openai.com')) return AI_PRESET_OPENAI
  return AI_PRESET_CUSTOM
}

/**
 * Settings patch from an AI settings JSON file (see `examples/ai`).
 *
 * Accepts a flat file describing one endpoint
 * (`{ preset, base_url, model, api_key }`) or a `presets` object carrying
 * several. snake_case and camelCase key names both work, so files exported
 * from either app import into both. Throws `Error` with a user-facing message
 * when the file cannot be applied.
 *
 * @param {string|object} data
 * @returns {{ preset?: string, presets: object, responseLanguage?: string }}
 */
export function parseAiSettingsJson(data) {
  let parsed = data
  if (typeof parsed === 'string') {
    try {
      parsed = JSON.parse(parsed)
    } catch (err) {
      throw new Error(`Not valid JSON: ${err?.message || err}`, { cause: err })
    }
  }
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('AI settings file must contain a JSON object.')
  }

  const rawPreset = jsonStr(parsed, 'preset', 'aiPreset', 'ai_preset', 'provider')
  let preset = rawPreset ? importPresetId(rawPreset) : ''
  const presets = {}

  const collect = (target, fields) => {
    let baseUrl = jsonStr(fields, 'base_url', 'baseUrl', 'url')
    if (baseUrl) {
      if (!/^https?:\/\//i.test(baseUrl)) {
        throw new Error(`Base URL must start with http:// or https:// (got "${baseUrl}").`)
      }
      baseUrl = normalizeAiBaseUrl(baseUrl)
    }
    const entry = {}
    if (baseUrl) entry.baseUrl = baseUrl
    const model = jsonStr(fields, 'model', 'model_id', 'modelId')
    if (model) entry.model = model
    const apiKey = normalizeApiKey(jsonStr(fields, 'api_key', 'apiKey', 'key'))
    if (apiKey) entry.apiKey = apiKey
    if (Object.keys(entry).length) {
      presets[target] = { ...(presets[target] || {}), ...entry }
    }
  }

  const presetsObj = parsed.presets ?? parsed.aiPresets
  if (presetsObj != null) {
    if (typeof presetsObj !== 'object' || Array.isArray(presetsObj)) {
      throw new Error('"presets" must be an object keyed by preset id.')
    }
    for (const [key, fields] of Object.entries(presetsObj)) {
      if (!fields || typeof fields !== 'object' || Array.isArray(fields)) {
        throw new Error(`Preset "${key}" must be an object.`)
      }
      collect(importPresetId(key), fields)
    }
  }

  const flatUrl = jsonStr(parsed, 'base_url', 'baseUrl', 'url')
  const flatTarget = preset || importPresetFromUrl(flatUrl)
  collect(flatTarget, parsed)
  if (!preset && flatUrl) preset = flatTarget
  const names = Object.keys(presets)
  if (!preset && names.length === 1) [preset] = names
  if (!names.length) {
    throw new Error(
      'No AI settings found. Expected base_url / model / api_key '
      + '(optionally inside a presets object).',
    )
  }
  if (preset && !aiPresetInfo(preset).baseUrl && !presets[preset]?.baseUrl) {
    throw new Error(`Preset "${preset}" needs a base_url.`)
  }

  const out = { presets }
  if (preset) out.preset = preset
  const language = jsonStr(
    parsed, 'response_language', 'responseLanguage', 'aiResponseLanguage')
  if (language) out.responseLanguage = language
  return out
}

/** Normalize an OpenAI-compatible API root (…/v1 or vendor equivalent). */
export function normalizeAiBaseUrl(url) {
  let u = String(url || DEFAULT_AI_BASE_URL).trim().replace(/\/+$/, '')
  if (!u) return DEFAULT_AI_BASE_URL
  let low = u.toLowerCase()
  for (const suffix of ['/chat/completions', '/completions']) {
    if (low.endsWith(suffix)) {
      u = u.slice(0, -suffix.length).replace(/\/+$/, '')
      low = u.toLowerCase()
      break
    }
  }
  // Ollama's native root (…/api) is not the OpenAI-compatible one.
  if (low.endsWith('/api')) {
    u = u.slice(0, -4).replace(/\/+$/, '')
    low = u.toLowerCase()
  }
  // A bare host (no path) means the vendor's /v1 root.
  const hostOnly = low.split('://').pop()
  if (!hostOnly.includes('/')) u += '/v1'
  return u
}

export function normalizeApiKey(apiKey = '') {
  let key = String(apiKey || '').trim()
  if (!key) return ''
  for (const ch of ['\ufeff', '\u200b', '\u200c', '\u200d', '\u00a0']) {
    key = key.split(ch).join('')
  }
  key = key.trim().replace(/^["']|["']$/g, '').trim()
  // fetch() headers must be ISO-8859-1; API keys are ASCII. Drop CJK / smart quotes.
  key = Array.from(key).filter((ch) => {
    const c = ch.codePointAt(0)
    return c >= 0x20 && c <= 0x7e
  }).join('')
  key = key.trim().replace(/^["']|["']$/g, '').trim()
  if (key.toLowerCase().startsWith('bearer ')) {
    key = key.slice(7).trim().replace(/^["']|["']$/g, '').trim()
  }
  const placeholders = new Set([
    'gemini_api_key', 'your-api-key', 'your_api_key', 'api_key',
    'openai_api_key', '<api-key>', 'xxx',
  ])
  if (placeholders.has(key.toLowerCase())) return ''
  return key
}

/** Read optional Vite / runtime env keys (parity with Desktop os.environ). */
export function readAiEnvKey(names = []) {
  let env = {}
  try {
    if (typeof import.meta !== 'undefined' && import.meta.env) {
      env = { ...import.meta.env }
    }
  } catch {
    /* ignore */
  }
  try {
    if (typeof window !== 'undefined' && window.__BTF_AI_ENV__) {
      env = { ...env, ...window.__BTF_AI_ENV__ }
    }
  } catch {
    /* ignore */
  }
  for (const name of names) {
    const raw = env[name] ?? env[`VITE_${name}`] ?? ''
    const key = normalizeApiKey(raw)
    if (key) return key
  }
  return ''
}

/** Settings key, else OPENAI_API_KEY / GEMINI_API_KEY / OLLAMA_API_KEY (VITE_*). */
export function resolveAiApiKey(apiKey = '') {
  const key = normalizeApiKey(apiKey)
  if (key) return key
  return readAiEnvKey(['OPENAI_API_KEY', 'GEMINI_API_KEY', 'OLLAMA_API_KEY'])
}

/**
 * Accept Desktop snake_case or Web camelCase context objects.
 * @param {object} ctx
 */
export function normalizeAiContext(ctx = {}) {
  const c = ctx && typeof ctx === 'object' ? ctx : {}
  return {
    findingsText: String(c.findingsText ?? c.findings_text ?? ''),
    span: String(c.span ?? ''),
    cores: c.cores ?? '',
    scope: String(c.scope ?? ''),
    metrics: c.metrics ?? null,
  }
}

export function aiRequestHeaders(apiKey = '', baseUrl = '') {
  // baseUrl kept for call-site parity; Gemini OpenAI-compat must use Bearer only
  // (also sending x-goog-api-key causes HTTP 400). Local Ollama needs no key.
  void baseUrl
  const headers = { 'Content-Type': 'application/json' }
  const key = resolveAiApiKey(apiKey)
  if (key) {
    headers.Authorization = `Bearer ${key}`
  }
  return headers
}

/** True for loopback endpoints (Ollama and other local servers need no key). */
export function isLocalAiHost(url) {
  try {
    const u = new URL(normalizeAiBaseUrl(url))
    // URL keeps IPv6 literals bracketed; LOCAL_AI_HOSTS stores them bare.
    const host = u.hostname.replace(/^\[|\]$/g, '').toLowerCase()
    return LOCAL_AI_HOSTS.includes(host)
  } catch {
    return false
  }
}

/**
 * Same-origin proxy base for the Ollama / OpenAI / Gemini presets under Vite
 * (`npm run dev` / `preview`). Returns null for Custom, file://, remote hosts.
 */
export function aiSameOriginProxyBase(presetId, configuredUrl) {
  if (typeof window === 'undefined') return null
  const proxyPath = AI_PRESET_PROXY_PATHS[normalizeAiPreset(presetId)]
  if (!proxyPath) return null
  const { protocol, hostname, origin } = window.location
  if (protocol !== 'http:' && protocol !== 'https:') return null
  if (hostname !== 'localhost' && hostname !== '127.0.0.1') return null
  // Map the configured upstream root onto the proxy: drop scheme+host, keep /v1…
  const configured = normalizeAiBaseUrl(configuredUrl)
  let pathSuffix
  try {
    pathSuffix = new URL(configured).pathname.replace(/\/+$/, '')
  } catch {
    pathSuffix = ''
  }
  return `${origin}${proxyPath}${pathSuffix}`
}

/**
 * @param {string} query
 * @param {{ findingsText?: string, metrics?: object, span?: string, cores?: any, scope?: string }} ctx
 */
export function buildAiUserMessage(query, ctx = {}) {
  const parts = ['### System Trace Context']
  if (ctx.span) parts.push(`- Trace Span: ${ctx.span}`)
  if (ctx.cores != null && ctx.cores !== '') parts.push(`- Cores: ${ctx.cores}`)
  if (ctx.scope) parts.push(`- Statistics scope: ${ctx.scope}`)
  parts.push('')
  parts.push('### Analysis Findings')
  parts.push((ctx.findingsText || 'No findings for the current scope.').trimEnd())
  parts.push('')
  if (ctx.metrics) {
    parts.push('### Extracted Relevant Metrics')
    parts.push(JSON.stringify(ctx.metrics, null, 2))
    parts.push('')
  }
  parts.push('### User Question')
  parts.push(String(query || '').trim())
  return parts.join('\n')
}

function aiHttpErrorTip(status, detail = '', baseUrl = '') {
  const low = String(detail || '').toLowerCase()
  const host = String(baseUrl || '').toLowerCase()
  if (status === 401 || status === 403) {
    return ' Check API key (Settings → AI, or OPENAI_API_KEY / GEMINI_API_KEY / VITE_*).'
  }
  if (
    status === 400
    && (
      low.includes('valid api key')
      || (low.includes('api key') && low.includes('invalid'))
      || low.includes('multiple authentication')
    )
  ) {
    let tip = (
      ' Paste a Gemini key from https://aistudio.google.com/apikey into '
      + 'Settings → AI → API key, without a Bearer prefix. Save settings, then Test again.'
    )
    if (host.includes('generativelanguage') || host.includes('gemini')) {
      tip += (
        ' Use Bearer-only auth (AI Studio key). If the key starts with AQ., '
        + 'create a new key in AI Studio (non-AQ format) — Google\'s '
        + 'OpenAI-compat endpoint still rejects some AQ. keys. '
        + 'Do not use an OpenAI sk- key.'
      )
    }
    return tip
  }
  if (status === 429) {
    let tip = (
      ' Rate/quota limit (RESOURCE_EXHAUSTED). Wait and retry, check '
      + 'https://aistudio.google.com/rate-limit (Gemini) or your provider dashboard.'
    )
    if (host.includes('gemini') || host.includes('generativelanguage') || low.includes('gemini')) {
      tip += (
        ' Try model gemini-flash-lite-latest (or gemini-flash-latest). '
        + 'Free quota for a pinned version is often 0 or closed to new '
        + 'users — enable billing or switch model/project.'
      )
    }
    return tip
  }
  if (status === 404) {
    let tip = ' Check Base URL and model name for this endpoint.'
    if (low.includes('no longer available') || low.includes('not found')) {
      tip += (
        ' For Gemini, prefer the rolling aliases gemini-flash-lite-latest '
        + 'or gemini-flash-latest; pinned versions are retired over time.'
      )
    }
    return tip
  }
  return ''
}

/**
 * Why a same-origin-blocked fetch failed, and what to do about it. A browser
 * reports every blocked request as "Failed to fetch" with no detail, so the
 * page's own protocol is the only clue we have.
 */
export function aiReachabilityTip(urlBase) {
  const local = isLocalAiHost(urlBase)
  if (typeof window !== 'undefined' && window.location.protocol === 'file:') {
    return (
      ' A page opened from the filesystem sends Origin: null, which Ollama '
      + 'rejects (403) — the server itself is fine. Serve the app over http '
      + '(`npm run dev` / `npm run preview` proxy it for you), start Ollama '
      + 'with OLLAMA_ORIGINS="*", or use the Desktop app.'
    )
  }
  if (local) {
    return (
      ' Is `ollama serve` running? If this page is not served by Vite there is '
      + 'no /ollama proxy, so the browser blocks the cross-origin call — use '
      + '`npm run dev` / `preview`, or start Ollama with OLLAMA_ORIGINS="*".'
    )
  }
  return ' Prefer `npm run dev` / `preview` (CORS).'
}

function aiFetchReachError(urlBase, lastErr) {
  const msg = String(lastErr?.message || lastErr || 'Failed to fetch')
  if (/ISO-8859-1|non ISO-8859-1|code point/i.test(msg)) {
    return new Error(
      'API key contains non-ASCII characters that browsers reject in HTTP headers. '
      + 'Re-paste the raw key (ASCII only), Save, then Test again. '
      + `(${msg})`,
    )
  }
  return new Error(
    `Cannot reach the AI endpoint at ${urlBase}.${aiReachabilityTip(urlBase)} (${msg})`,
  )
}

/**
 * POST to `/chat/completions`, preferring the Vite same-origin proxy.
 * @returns {Promise<{ resp: Response, fetchBase: string }>}
 */
async function aiFetchChat(preset, urlBase, { headers, body, signal }) {
  const proxyBase = aiSameOriginProxyBase(preset, urlBase)
  const bases = proxyBase ? [proxyBase, urlBase] : [urlBase]
  let lastErr = null
  for (const base of bases) {
    try {
      const r = await fetch(`${base}/chat/completions`, {
        method: 'POST',
        headers,
        body,
        signal,
      })
      // Static servers without the Vite proxy answer with an HTML 404.
      if (
        proxyBase
        && base === proxyBase
        && r.status === 404
        && (r.headers.get('content-type') || '').includes('text/html')
      ) {
        continue
      }
      return { resp: r, fetchBase: base }
    } catch (err) {
      if (err?.name === 'AbortError') throw err
      lastErr = err
    }
  }
  throw aiFetchReachError(urlBase, lastErr)
}

/**
 * One non-streaming `/chat/completions` round (optional tools).
 * @returns {Promise<{ content: string, tool_calls: object[], message: object }>}
 */
export async function aiChatCompletion({
  query = '',
  findingsText = '',
  metrics = null,
  span = '',
  cores = '',
  scope = '',
  baseUrl = DEFAULT_AI_BASE_URL,
  model = DEFAULT_AI_MODEL,
  apiKey = '',
  responseLanguage = DEFAULT_AI_RESPONSE_LANGUAGE,
  preset = DEFAULT_AI_PRESET,
  messages = null,
  tools = null,
  signal,
  timeoutMs = AI_CHAT_TIMEOUT_MS,
} = {}) {
  const urlBase = normalizeAiBaseUrl(baseUrl)
  const chatModel = String(model || DEFAULT_AI_MODEL).trim() || DEFAULT_AI_MODEL
  const key = resolveAiApiKey(apiKey)
  if (!key && !isLocalAiHost(urlBase)) {
    throw new Error(
      'API key required for remote endpoints '
      + '(Settings → AI, or VITE_OPENAI_API_KEY / VITE_GEMINI_API_KEY). '
      + 'Paste the raw key only — no Bearer prefix.',
    )
  }
  const chatMessages = messages || [
    { role: 'system', content: buildAiSystemPrompt(responseLanguage) },
    {
      role: 'user',
      content: buildAiUserMessage(query, {
        findingsText,
        metrics,
        span,
        cores,
        scope,
      }),
    },
  ]
  const payload = {
    model: chatModel,
    stream: false,
    messages: chatMessages,
  }
  const useTools = Array.isArray(tools) && tools.length ? tools : null
  if (useTools) {
    // Omit tool_choice — Ollama/some proxies 400 on it and used to drop tools.
    payload.tools = useTools
  }

  const chatCtrl = new AbortController()
  let timedOut = false
  const onAbort = () => chatCtrl.abort()
  if (signal) {
    if (signal.aborted) chatCtrl.abort()
    else signal.addEventListener('abort', onAbort, { once: true })
  }
  const timer = setTimeout(() => {
    timedOut = true
    chatCtrl.abort()
  }, timeoutMs)

  async function post(bodyObj) {
    const { resp, fetchBase } = await aiFetchChat(preset, urlBase, {
      headers: aiRequestHeaders(key, urlBase),
      body: JSON.stringify(bodyObj),
      signal: chatCtrl.signal,
    })
    if (!resp.ok) {
      const detail = (await resp.text().catch(() => '')).slice(0, 400)
      const tip = aiHttpErrorTip(resp.status, detail, urlBase)
      const err = new Error(
        `HTTP ${resp.status} at ${fetchBase}/chat/completions: `
        + `${detail || resp.statusText}.${tip}`,
      )
      err.httpStatus = resp.status
      err.httpDetail = detail
      throw err
    }
    return resp.json()
  }

  let data
  try {
    try {
      data = await post(payload)
    } catch (err) {
      if (err?.name === 'AbortError') {
        if (signal?.aborted && !timedOut) throw err
        throw new Error(
          `OpenAI-compatible request timed out after ${Math.round(timeoutMs / 1000)}s (${urlBase})`,
          { cause: err },
        )
      }
      const detail = String(err?.httpDetail || err?.message || '').toLowerCase()
      const code = Number(err?.httpStatus || 0)
      const unsupported = [
        'does not support tools',
        'does not support function',
        'tool calling is not supported',
        'unsupported tool',
        'unknown field: tools',
        'unknown field "tools"',
        "unknown field 'tools'",
      ].some(s => detail.includes(s))
      if (useTools && [400, 404, 422].includes(code) && unsupported) {
        delete payload.tools
        delete payload.tool_choice
        data = await post(payload)
      } else {
        throw err
      }
    }
  } finally {
    clearTimeout(timer)
    if (signal) signal.removeEventListener('abort', onAbort)
  }
  const choice0 = data?.choices?.[0] || {}
  const msg = choice0.message || data?.message || {}
  let content = messageContentText(msg.content)
  let calls = extractToolCalls(msg)
  if (!calls.length && choice0.tool_calls) {
    calls = extractToolCalls({ tool_calls: choice0.tool_calls })
  }
  const textCalls = parseToolCallsFromText(content)
  calls = mergeToolCalls(calls, textCalls)
  if (textCalls.length) content = stripParsedToolMarkup(content)
  if (!content && !calls.length) throw new Error('Unexpected chat response')
  return { content, tool_calls: calls, message: msg }
}

/**
 * Non-streaming chat against any OpenAI-compatible endpoint (Ollama included).
 * @param {object} opts
 * @returns {Promise<string>}
 */
export async function aiChat(opts = {}) {
  const turn = await aiChatCompletion(opts)
  if (turn.content) return turn.content
  if (turn.tool_calls?.length) {
    return turn.tool_calls
      .map(c => summariseToolCall(c.name, c.arguments || {}))
      .join('\n')
  }
  throw new Error('Unexpected chat response')
}

/** Model ids from `GET /models` on an OpenAI-compatible API. */
export async function aiListModels(baseUrl = DEFAULT_AI_BASE_URL, {
  signal, timeoutMs = AI_LIST_MODELS_TIMEOUT_MS, apiKey = '', preset = DEFAULT_AI_PRESET,
} = {}) {
  const urlBase = normalizeAiBaseUrl(baseUrl)
  const proxyBase = aiSameOriginProxyBase(preset, urlBase)
  const bases = proxyBase ? [proxyBase, urlBase] : [urlBase]
  const ctrl = signal ? null : new AbortController()
  const timer = ctrl ? setTimeout(() => ctrl.abort(), timeoutMs) : null
  let lastErr = null
  try {
    for (const base of bases) {
      try {
        const resp = await fetch(`${base}/models`, {
          method: 'GET',
          headers: aiRequestHeaders(apiKey, urlBase),
          signal: signal || ctrl.signal,
        })
        if (
          proxyBase
          && base === proxyBase
          && resp.status === 404
          && (resp.headers.get('content-type') || '').includes('text/html')
        ) {
          continue
        }
        if (!resp.ok) {
          const detail = (await resp.text().catch(() => '')).slice(0, 300)
          throw new Error(`HTTP ${resp.status}: ${detail || resp.statusText}`)
        }
        const data = await resp.json()
        return (data?.data || []).map((m) => String(m?.id || '')).filter(Boolean)
      } catch (err) {
        if (err?.name === 'AbortError') {
          throw new Error(`Cannot list models at ${urlBase}/models: timed out`, { cause: err })
        }
        lastErr = err
      }
    }
    const msg = lastErr?.message || 'Failed to fetch'
    const via = proxyBase ? ` (also tried ${proxyBase}/models)` : ''
    throw new Error(
      `Cannot list models at ${urlBase}/models${via}: ${msg}.`
      + aiReachabilityTip(urlBase),
      { cause: lastErr },
    )
  } finally {
    if (timer) clearTimeout(timer)
  }
}

/** Model id without Gemini's `models/` namespace prefix. */
function modelId(name) {
  const n = String(name || '').trim()
  return n.slice(0, 7).toLowerCase() === 'models/' ? n.slice(7) : n
}

/**
 * Served model name matching *requested*, or null. Ollama reports `name:tag`
 * while users often type just `name`, and Gemini lists ids as `models/<id>`
 * while the chat API takes either form.
 * @param {string} requested @param {string[]} available
 */
export function matchModelName(requested, available) {
  const want = modelId(requested)
  if (!want) return null
  const names = (available || []).map(String).filter(Boolean)
  if (names.includes(want)) return want
  const wantBase = want.split(':', 1)[0]
  for (const n of names) {
    const served = modelId(n)
    if (served === want || served.startsWith(`${want}:`)) return n
    const servedBase = served.split(':', 1)[0]
    if (servedBase === want || (!want.includes(':') && servedBase === wantBase)) return n
  }
  return null
}

/**
 * List models, then run a tiny chat probe against the configured endpoint.
 * @param {object} opts
 * @param {(msg: string) => void} [opts.onProgress]
 * @returns {Promise<string>} success message
 */
export async function aiTestConnection({
  baseUrl = DEFAULT_AI_BASE_URL,
  model = DEFAULT_AI_MODEL,
  apiKey = '',
  preset = DEFAULT_AI_PRESET,
  signal,
  timeoutMs = AI_TEST_TIMEOUT_MS,
  onProgress,
} = {}) {
  const progress = (msg) => {
    try {
      onProgress?.(msg)
    } catch {
      /* ignore UI callback errors */
    }
  }
  const urlBase = normalizeAiBaseUrl(baseUrl)
  const modelName = String(model || DEFAULT_AI_MODEL).trim() || DEFAULT_AI_MODEL
  const key = resolveAiApiKey(apiKey)
  const local = isLocalAiHost(urlBase)
  if (!key && !local) {
    throw new Error(
      'API key required for remote endpoints '
      + '(Settings → AI, or VITE_OPENAI_API_KEY / VITE_GEMINI_API_KEY). '
      + 'Paste the raw key only — no Bearer prefix.',
    )
  }

  progress(`1/2 Listing models at ${urlBase}…`)
  let served = []
  let listingNote = ''
  try {
    served = await aiListModels(urlBase, {
      signal,
      timeoutMs: Math.min(AI_LIST_MODELS_TIMEOUT_MS, timeoutMs),
      apiKey: key,
      preset,
    })
  } catch (err) {
    if (local) {
      // aiListModels already explains the failure and how to fix it; only add
      // the canonical root when the user pointed somewhere else.
      const wrongRoot = urlBase !== DEFAULT_AI_BASE_URL
        ? ` For a default Ollama install use ${DEFAULT_AI_BASE_URL}.`
        : ''
      throw new Error(`${err?.message || err}${wrongRoot}`, { cause: err })
    }
    listingNote = ' (model list unavailable)'
  }
  if (served.length && !matchModelName(modelName, served)) {
    const listing = served.slice(0, 12).join(', ')
    const more = served.length > 12 ? ` … +${served.length - 12} more` : ''
    throw new Error(
      `Model "${modelName}" is not served at ${urlBase}. Available: ${listing}${more}.`,
    )
  }

  progress(`2/2 Chat probe with ${modelName} (first load can take a while)…`)
  const chatCtrl = new AbortController()
  const onAbort = () => chatCtrl.abort()
  if (signal) {
    if (signal.aborted) chatCtrl.abort()
    else signal.addEventListener('abort', onAbort, { once: true })
  }
  const timer = setTimeout(() => chatCtrl.abort(), timeoutMs)
  let resp
  let fetchBase
  try {
    ;({ resp, fetchBase } = await aiFetchChat(preset, urlBase, {
      headers: aiRequestHeaders(key, urlBase),
      signal: chatCtrl.signal,
      body: JSON.stringify({
        model: modelName,
        stream: false,
        messages: [{ role: 'user', content: 'Reply with exactly: OK' }],
        max_tokens: 8,
      }),
    }))
  } catch (err) {
    if (err?.name === 'AbortError') {
      throw new Error(
        `Chat probe timed out after ${Math.round(timeoutMs / 1000)}s `
        + '(model may still be loading).',
        { cause: err },
      )
    }
    throw err
  } finally {
    clearTimeout(timer)
    if (signal) signal.removeEventListener('abort', onAbort)
  }
  if (!resp.ok) {
    const detail = (await resp.text().catch(() => '')).slice(0, 300)
    const tip = aiHttpErrorTip(resp.status, detail, urlBase)
    throw new Error(
      `HTTP ${resp.status} at ${fetchBase}/chat/completions: `
      + `${detail || resp.statusText}.${tip}`,
    )
  }
  const data = await resp.json()
  const reply = String(data?.choices?.[0]?.message?.content ?? '').trim()
  const note = reply ? ` Probe reply: ${JSON.stringify(reply.slice(0, 40))}.` : ''
  return `Connected to ${urlBase}. Model ${modelName} ready${listingNote}.${note}`
}

/** Parse jump:NNNN tokens from assistant text. */
export function extractJumpTimes(text) {
  const out = []
  const re = /jump:([0-9]+(?:\.[0-9]+)?)/g
  let m
  while ((m = re.exec(String(text || ''))) !== null) {
    out.push(Number(m[1]))
  }
  return out
}

/** Annotation label for a clicked jump:TIME link (desktop parity). */
export function aiJumpAnnotationNote(value) {
  const n = Number(value)
  if (!Number.isFinite(n)) return 'AI jump'
  if (Number.isInteger(n) || n === Math.trunc(n)) return `AI jump:${Math.trunc(n)}`
  return `AI jump:${n}`
}
