/**
 * Ollama client + diagnostic prompt templates for the web AI Assistant.
 * Keep template prompts in sync with btf_viewer_pkg/ai_assistant.py
 * (documented in README.md § AI Assistant).
 */

export const AI_SYSTEM_PROMPT =
  'You are an expert Real-Time Operating System (RTOS) and SMP trace analysis ' +
  'assistant for FreeRTOS BTF traces. Analyse the provided structured metrics ' +
  'and answer the user\'s diagnostic question clearly. Focus on root causes ' +
  '(preemption, priority inversion, lock contention, core thrashing, switch ' +
  'overhead, tick health). Prefer concrete task names, cores, and durations. ' +
  'When mentioning a time, write it as jump:TIME where TIME is the numeric ' +
  'value in the trace time unit (e.g. jump:1805120). Keep answers concise.'

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

export const DEFAULT_OLLAMA_URL = 'http://localhost:11434'
export const DEFAULT_OLLAMA_MODEL = 'phi4-mini:3.8b'

export const AI_PROVIDER_OLLAMA = 'ollama'
export const AI_PROVIDER_OPENAI = 'openai_compatible'
export const DEFAULT_AI_PROVIDER = AI_PROVIDER_OLLAMA

export const AI_PROVIDER_CHOICES = [
  { id: AI_PROVIDER_OLLAMA, label: 'Ollama' },
  { id: AI_PROVIDER_OPENAI, label: 'OpenAI-compatible' },
]

export const AI_OPENAI_PRESET_CUSTOM = 'custom'
/** @type {{ id: string, label: string, baseUrl: string, model: string }[]} */
export const AI_OPENAI_PRESETS = [
  { id: AI_OPENAI_PRESET_CUSTOM, label: 'Custom', baseUrl: '', model: '' },
  {
    id: 'openai',
    label: 'OpenAI (ChatGPT)',
    baseUrl: 'https://api.openai.com/v1',
    model: 'gpt-4o-mini',
  },
  {
    id: 'xai',
    label: 'xAI (Grok)',
    baseUrl: 'https://api.x.ai/v1',
    model: 'grok-3-mini',
  },
  {
    id: 'gemini',
    label: 'Google Gemini',
    baseUrl: 'https://generativelanguage.googleapis.com/v1beta/openai',
    model: 'gemini-3.1-flash-lite',
  },
  {
    id: 'deepseek',
    label: 'DeepSeek',
    baseUrl: 'https://api.deepseek.com/v1',
    model: 'deepseek-chat',
  },
]

export const DEFAULT_OPENAI_PRESET = 'openai'
export const DEFAULT_OPENAI_BASE_URL = 'https://api.openai.com/v1'
export const DEFAULT_OPENAI_MODEL = 'gpt-4o-mini'

/** Vite same-origin proxy path per OpenAI-compatible preset. */
export const AI_OPENAI_PROXY_PATHS = {
  openai: '/proxy/openai',
  xai: '/proxy/xai',
  gemini: '/proxy/gemini',
  deepseek: '/proxy/deepseek',
}

export function normalizeAiProvider(provider) {
  const p = String(provider || DEFAULT_AI_PROVIDER).trim().toLowerCase().replace(/-/g, '_')
  if (p === 'openai' || p === 'openai_compat' || p === 'openai_compatible' || p === 'chatgpt') {
    return AI_PROVIDER_OPENAI
  }
  return AI_PROVIDER_OLLAMA
}

export function openaiPresetInfo(presetId) {
  const want = String(presetId || AI_OPENAI_PRESET_CUSTOM).trim().toLowerCase()
  return AI_OPENAI_PRESETS.find((p) => p.id === want) || AI_OPENAI_PRESETS[0]
}

export function applyOpenaiPreset(presetId) {
  const p = openaiPresetInfo(presetId)
  const out = { openaiPreset: p.id }
  if (p.baseUrl) out.openaiBaseUrl = p.baseUrl
  if (p.model) out.openaiModel = p.model
  return out
}

/** Vite server/preview proxies this path to local Ollama (avoids browser CORS). */
export const OLLAMA_SAME_ORIGIN_PROXY = '/ollama'

export function normalizeOllamaUrl(url) {
  let u = String(url || DEFAULT_OLLAMA_URL).trim().replace(/\/+$/, '')
  if (u.toLowerCase().endsWith('/api')) u = u.slice(0, -4).replace(/\/+$/, '')
  return u || DEFAULT_OLLAMA_URL
}

export function normalizeOpenaiBaseUrl(url) {
  let u = String(url || DEFAULT_OPENAI_BASE_URL).trim().replace(/\/+$/, '')
  if (!u) return DEFAULT_OPENAI_BASE_URL
  let low = u.toLowerCase()
  for (const suffix of ['/chat/completions', '/completions']) {
    if (low.endsWith(suffix)) {
      u = u.slice(0, -suffix.length).replace(/\/+$/, '')
      low = u.toLowerCase()
      break
    }
  }
  if (low === 'https://api.openai.com' || low === 'http://api.openai.com') u += '/v1'
  else if (low === 'https://api.x.ai' || low === 'http://api.x.ai') u += '/v1'
  else if (low === 'https://api.deepseek.com' || low === 'http://api.deepseek.com') u += '/v1'
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
export function resolveOpenaiApiKey(apiKey = '') {
  const key = normalizeApiKey(apiKey)
  if (key) return key
  return readAiEnvKey(['OPENAI_API_KEY', 'GEMINI_API_KEY', 'OLLAMA_API_KEY'])
}

/** Settings key, else OLLAMA_API_KEY (VITE_*). */
export function resolveOllamaApiKey(apiKey = '') {
  const key = normalizeApiKey(apiKey)
  if (key) return key
  return readAiEnvKey(['OLLAMA_API_KEY'])
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

export function openaiRequestHeaders(apiKey = '', baseUrl = '') {
  // baseUrl kept for call-site parity; Gemini OpenAI-compat must use Bearer only
  // (also sending x-goog-api-key causes HTTP 400).
  void baseUrl
  const headers = { 'Content-Type': 'application/json' }
  const key = resolveOpenaiApiKey(apiKey)
  if (key) {
    headers.Authorization = `Bearer ${key}`
  }
  return headers
}

/**
 * Same-origin proxy base for known OpenAI-compatible presets under Vite.
 * Returns null for Custom / file:// / non-localhost hosts.
 */
export function openaiSameOriginProxyBase(presetId, configuredUrl) {
  if (typeof window === 'undefined') return null
  const preset = String(presetId || '').trim().toLowerCase()
  const proxyPath = AI_OPENAI_PROXY_PATHS[preset]
  if (!proxyPath) return null
  const { protocol, hostname, origin } = window.location
  if (protocol !== 'http:' && protocol !== 'https:') return null
  if (hostname !== 'localhost' && hostname !== '127.0.0.1') return null
  // Map configured upstream root onto the proxy: strip scheme+host, keep /v1…
  const configured = normalizeOpenaiBaseUrl(configuredUrl)
  let pathSuffix = ''
  try {
    const u = new URL(configured)
    pathSuffix = u.pathname.replace(/\/+$/, '') || ''
  } catch {
    pathSuffix = ''
  }
  return `${origin}${proxyPath}${pathSuffix}`
}

export function isLocalOllamaUrl(url) {
  try {
    const u = new URL(normalizeOllamaUrl(url))
    return u.hostname === 'localhost'
      || u.hostname === '127.0.0.1'
      || u.hostname === '0.0.0.0'
      || u.hostname === '[::1]'
  } catch {
    return false
  }
}

/**
 * Same-origin base for local Ollama when the page is served over http(s) on
 * localhost (Vite `dev` / `preview` provide `/ollama` → :11434).
 * Returns null when the proxy cannot apply (file://, remote host, cloud URL).
 */
export function ollamaSameOriginProxyBase(configuredUrl) {
  if (typeof window === 'undefined') return null
  if (!isLocalOllamaUrl(configuredUrl)) return null
  const { protocol, hostname, origin } = window.location
  if (protocol !== 'http:' && protocol !== 'https:') return null
  if (hostname !== 'localhost' && hostname !== '127.0.0.1') return null
  return `${origin}${OLLAMA_SAME_ORIGIN_PROXY}`
}

function ollamaReachError(configuredBase, err) {
  const msg = err?.message || String(err)
  const tips = []
  if (typeof window !== 'undefined' && window.location.protocol === 'file:') {
    tips.push(
      'Open the web app via `npm run dev` or `npm run preview` (recommended), '
      + 'or allow CORS: OLLAMA_ORIGINS="*" ollama serve',
    )
  } else if (isLocalOllamaUrl(configuredBase)) {
    tips.push(
      'Is Ollama running? Try `ollama serve`. '
      + 'For a static/file open, set OLLAMA_ORIGINS="*" ollama serve. '
      + 'With Vite, use npm run dev / preview (proxies /ollama).',
    )
  }
  const tip = tips.length ? ` ${tips.join(' ')}` : ''
  return new Error(`Cannot reach Ollama at ${configuredBase}.${tip} (${msg})`)
}

/**
 * fetch() against Ollama, preferring the Vite same-origin proxy for local URLs.
 * @returns {Promise<{ resp: Response, fetchBase: string }>}
 */
export async function ollamaFetch(configuredUrl, apiPath, init = {}) {
  const configuredBase = normalizeOllamaUrl(configuredUrl)
  const path = apiPath.startsWith('/') ? apiPath : `/${apiPath}`
  const proxyBase = ollamaSameOriginProxyBase(configuredBase)
  const bases = proxyBase ? [proxyBase, configuredBase] : [configuredBase]
  let lastErr = null
  for (const base of bases) {
    try {
      const resp = await fetch(`${base}${path}`, init)
      // Static servers without the Vite proxy return an HTML 404 for /ollama/*.
      if (
        proxyBase
        && base === proxyBase
        && resp.status === 404
        && (resp.headers.get('content-type') || '').includes('text/html')
      ) {
        continue
      }
      return { resp, fetchBase: base }
    } catch (err) {
      if (err?.name === 'AbortError') throw err
      lastErr = err
    }
  }
  throw ollamaReachError(configuredBase, lastErr || new Error('Failed to fetch'))
}

export function isOllamaCloudModel(name) {
  const n = String(name || '').trim().toLowerCase()
  if (!n) return false
  return n.endsWith(':cloud') || n.endsWith('-cloud') || n.includes(':cloud')
}

export function isOllamaCloudHost(url) {
  let host = normalizeOllamaUrl(url).toLowerCase()
  if (host.includes('://')) host = host.split('://', 2)[1]
  host = host.split('/', 1)[0]
  return host === 'ollama.com' || host.endsWith('.ollama.com')
}

/** Local proxy keeps :cloud; https://ollama.com drops the suffix. */
export function resolveOllamaChatModel(baseUrl, model) {
  let name = String(model || DEFAULT_OLLAMA_MODEL).trim() || DEFAULT_OLLAMA_MODEL
  if (isOllamaCloudHost(baseUrl)) {
    const low = name.toLowerCase()
    if (low.endsWith(':cloud')) name = name.slice(0, -':cloud'.length)
    else if (low.endsWith('-cloud')) name = name.slice(0, -'-cloud'.length)
  }
  return name
}

export function ollamaRequestHeaders(apiKey = '') {
  const headers = { 'Content-Type': 'application/json' }
  const key = resolveOllamaApiKey(apiKey)
  if (key) headers.Authorization = `Bearer ${key}`
  return headers
}

function ollamaHttpErrorMessage(status, detail, { url, model, baseUrl }) {
  let tip = ''
  if (status === 401 || status === 403) {
    if (isOllamaCloudHost(baseUrl) || isOllamaCloudModel(model)) {
      tip = ' Cloud models need auth: run `ollama signin` (local proxy), or set an API key for https://ollama.com (Settings → AI).'
    } else {
      tip = ' Check credentials / API key.'
    }
  } else if (status === 404 && isOllamaCloudModel(model)) {
    tip = ` Try \`ollama pull ${model}\` after \`ollama signin\`, or use https://ollama.com with an API key (model without :cloud).`
  }
  return `Ollama HTTP ${status} at ${url}: ${detail || status}.${tip}`
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

/**
 * Non-streaming chat. Local Ollama uses the Vite `/ollama` proxy when available;
 * otherwise needs CORS (`OLLAMA_ORIGINS`).
 *
 * @param {object} opts
 * @returns {Promise<string>}
 */
export async function ollamaChat({
  query,
  findingsText = '',
  metrics = null,
  span = '',
  cores = '',
  scope = '',
  baseUrl = DEFAULT_OLLAMA_URL,
  model = DEFAULT_OLLAMA_MODEL,
  apiKey = '',
  responseLanguage = DEFAULT_AI_RESPONSE_LANGUAGE,
  signal,
} = {}) {
  const urlBase = normalizeOllamaUrl(baseUrl)
  const chatModel = resolveOllamaChatModel(urlBase, model)
  const body = {
    model: chatModel,
    stream: false,
    messages: [
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
    ],
  }

  const { resp, fetchBase } = await ollamaFetch(urlBase, '/api/chat', {
    method: 'POST',
    headers: ollamaRequestHeaders(apiKey),
    body: JSON.stringify(body),
    signal,
  })

  if (!resp.ok) {
    const detail = (await resp.text().catch(() => '')).slice(0, 400)
    throw new Error(ollamaHttpErrorMessage(resp.status, detail || resp.statusText, {
      url: `${fetchBase}/api/chat`, model: chatModel, baseUrl: urlBase,
    }))
  }

  const data = await resp.json()
  const content = data?.message?.content ?? data?.response
  if (!content) throw new Error('Unexpected Ollama response')
  return String(content).trim()
}

function openaiHttpErrorTip(status, detail = '', baseUrl = '') {
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
      + 'Settings → AI → API key (OpenAI-compatible), without a Bearer prefix. '
      + 'Save settings, then Test again.'
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
        ' Try model gemini-3.1-flash-lite (or gemini-3.6-flash). '
        + 'Older gemini-2.0-* / gemini-2.5-* free quota is often 0 or '
        + 'closed to new users — enable billing or switch model/project.'
      )
    }
    return tip
  }
  if (status === 404) {
    let tip = ' Check Base URL and model name for this provider.'
    if (low.includes('no longer available') || low.includes('not found')) {
      tip += (
        ' For Gemini, try gemini-3.1-flash-lite or gemini-3.6-flash '
        + '(gemini-2.5-* is closed to many new accounts).'
      )
    }
    return tip
  }
  return ''
}

function openaiFetchReachError(urlBase, lastErr) {
  const msg = String(lastErr?.message || lastErr || 'Failed to fetch')
  if (/ISO-8859-1|non ISO-8859-1|code point/i.test(msg)) {
    return new Error(
      'API key contains non-ASCII characters that browsers reject in HTTP headers. '
      + 'Re-paste the raw key from AI Studio (AIza… / ASCII only), Save, then Test again. '
      + `(${msg})`,
    )
  }
  const tip = typeof window !== 'undefined' && window.location.protocol === 'file:'
    ? ' Use Desktop, or `npm run preview` with a provider preset (Vite proxies).'
    : ' Prefer a known preset under `npm run dev` / `preview` (CORS).'
  return new Error(`Cannot reach OpenAI-compatible API at ${urlBase}.${tip} (${msg})`)
}

/**
 * OpenAI-compatible chat. Known presets use Vite `/proxy/*` when available.
 * @param {object} opts
 * @returns {Promise<string>}
 */
export async function openaiCompatibleChat({
  query,
  findingsText = '',
  metrics = null,
  span = '',
  cores = '',
  scope = '',
  baseUrl = DEFAULT_OPENAI_BASE_URL,
  model = DEFAULT_OPENAI_MODEL,
  apiKey = '',
  responseLanguage = DEFAULT_AI_RESPONSE_LANGUAGE,
  preset = DEFAULT_OPENAI_PRESET,
  signal,
} = {}) {
  const urlBase = normalizeOpenaiBaseUrl(baseUrl)
  const chatModel = String(model || DEFAULT_OPENAI_MODEL).trim() || DEFAULT_OPENAI_MODEL
  const key = resolveOpenaiApiKey(apiKey)
  if (!key) {
    throw new Error(
      'API key required for OpenAI-compatible providers '
      + '(Settings → AI, or VITE_OPENAI_API_KEY / VITE_GEMINI_API_KEY). '
      + 'Paste the raw key only — no Bearer prefix.',
    )
  }
  const body = {
    model: chatModel,
    stream: false,
    messages: [
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
    ],
  }

  const proxyBase = openaiSameOriginProxyBase(preset, urlBase)
  const bases = proxyBase ? [proxyBase, urlBase] : [urlBase]
  const headers = openaiRequestHeaders(key, urlBase)
  let lastErr = null
  let resp = null
  let fetchBase = urlBase
  for (const base of bases) {
    try {
      const r = await fetch(`${base}/chat/completions`, {
        method: 'POST',
        headers,
        body: JSON.stringify(body),
        signal,
      })
      if (
        proxyBase
        && base === proxyBase
        && r.status === 404
        && (r.headers.get('content-type') || '').includes('text/html')
      ) {
        continue
      }
      resp = r
      fetchBase = base
      break
    } catch (err) {
      if (err?.name === 'AbortError') throw err
      lastErr = err
    }
  }
  if (!resp) {
    throw openaiFetchReachError(urlBase, lastErr)
  }
  if (!resp.ok) {
    const detail = (await resp.text().catch(() => '')).slice(0, 400)
    const tip = openaiHttpErrorTip(resp.status, detail, urlBase)
    throw new Error(
      `OpenAI-compatible HTTP ${resp.status} at ${fetchBase}/chat/completions: `
      + `${detail || resp.statusText}.${tip}`,
    )
  }
  const data = await resp.json()
  const content = data?.choices?.[0]?.message?.content
  if (!content) throw new Error('Unexpected OpenAI-compatible response')
  return String(content).trim()
}

/**
 * Dispatch to Ollama or OpenAI-compatible chat.
 * @param {object} opts
 * @returns {Promise<string>}
 */
export async function aiChat(opts = {}) {
  const provider = normalizeAiProvider(opts.provider)
  if (provider === AI_PROVIDER_OPENAI) {
    return openaiCompatibleChat(opts)
  }
  return ollamaChat(opts)
}

export async function openaiCompatibleTestConnection({
  baseUrl = DEFAULT_OPENAI_BASE_URL,
  model = DEFAULT_OPENAI_MODEL,
  apiKey = '',
  preset = DEFAULT_OPENAI_PRESET,
  signal,
  timeoutMs = 60000,
  onProgress,
} = {}) {
  const progress = (msg) => {
    try {
      onProgress?.(msg)
    } catch {
      /* ignore */
    }
  }
  const urlBase = normalizeOpenaiBaseUrl(baseUrl)
  const modelName = String(model || DEFAULT_OPENAI_MODEL).trim() || DEFAULT_OPENAI_MODEL
  const key = resolveOpenaiApiKey(apiKey)
  if (!key) {
    throw new Error(
      'API key required for OpenAI-compatible providers '
      + '(Settings → AI, or VITE_OPENAI_API_KEY / VITE_GEMINI_API_KEY). '
      + 'Paste the raw key only — no Bearer prefix.',
    )
  }
  progress(`1/2 Contacting ${urlBase}…`)
  progress(`2/2 Chat probe with ${modelName} (API key length ${key.length})…`)

  const proxyBase = openaiSameOriginProxyBase(preset, urlBase)
  const bases = proxyBase ? [proxyBase, urlBase] : [urlBase]
  const headers = openaiRequestHeaders(key, urlBase)
  const chatCtrl = new AbortController()
  const onAbort = () => chatCtrl.abort()
  if (signal) {
    if (signal.aborted) chatCtrl.abort()
    else signal.addEventListener('abort', onAbort, { once: true })
  }
  const timer = setTimeout(() => chatCtrl.abort(), timeoutMs)
  let resp = null
  let fetchBase = urlBase
  let lastErr = null
  try {
    for (const base of bases) {
      try {
        const r = await fetch(`${base}/chat/completions`, {
          method: 'POST',
          headers,
          signal: chatCtrl.signal,
          body: JSON.stringify({
            model: modelName,
            stream: false,
            messages: [{ role: 'user', content: 'Reply with exactly: OK' }],
            max_tokens: 8,
          }),
        })
        if (
          proxyBase
          && base === proxyBase
          && r.status === 404
          && (r.headers.get('content-type') || '').includes('text/html')
        ) {
          continue
        }
        resp = r
        fetchBase = base
        break
      } catch (err) {
        if (err?.name === 'AbortError') throw err
        lastErr = err
      }
    }
  } finally {
    clearTimeout(timer)
    if (signal) signal.removeEventListener('abort', onAbort)
  }
  if (!resp) {
    if (lastErr?.name === 'AbortError') {
      throw new Error(
        `OpenAI-compatible chat probe timed out after ${Math.round(timeoutMs / 1000)}s.`,
      )
    }
    throw openaiFetchReachError(urlBase, lastErr)
  }
  if (!resp.ok) {
    const detail = (await resp.text().catch(() => '')).slice(0, 300)
    const tip = openaiHttpErrorTip(resp.status, detail, urlBase)
    throw new Error(
      `OpenAI-compatible HTTP ${resp.status} at ${fetchBase}/chat/completions: `
      + `${detail || resp.statusText}.${tip}`,
    )
  }
  const data = await resp.json()
  const reply = String(data?.choices?.[0]?.message?.content ?? '').trim()
  const note = reply ? ` Probe reply: ${JSON.stringify(reply.slice(0, 40))}.` : ''
  return `Connected to ${urlBase}. Model ${modelName} ready.${note}`
}

/**
 * Verify the active AI provider.
 * @param {object} opts
 * @returns {Promise<string>}
 */
export async function aiTestConnection(opts = {}) {
  if (normalizeAiProvider(opts.provider) === AI_PROVIDER_OPENAI) {
    return openaiCompatibleTestConnection(opts)
  }
  return ollamaTestConnection(opts)
}

export async function ollamaListModels(baseUrl = DEFAULT_OLLAMA_URL, {
  signal, timeoutMs = 12000, apiKey = '',
} = {}) {
  const urlBase = normalizeOllamaUrl(baseUrl)
  const ctrl = signal ? null : new AbortController()
  const timer = ctrl
    ? setTimeout(() => ctrl.abort(), timeoutMs)
    : null
  try {
    const { resp } = await ollamaFetch(urlBase, '/api/tags', {
      method: 'GET',
      headers: ollamaRequestHeaders(apiKey),
      signal: signal || ctrl.signal,
    })
    if (!resp.ok) {
      const detail = (await resp.text().catch(() => '')).slice(0, 300)
      throw new Error(`Ollama HTTP ${resp.status}: ${detail || resp.statusText}`)
    }
    const data = await resp.json()
    const models = []
    for (const m of data?.models || []) {
      if (m?.name) models.push(String(m.name))
    }
    return models
  } catch (err) {
    if (err?.name === 'AbortError') {
      throw new Error(`Cannot list Ollama models at ${urlBase}/api/tags: timed out`)
    }
    // ollamaFetch already formats reachability errors.
    if (String(err?.message || '').startsWith('Cannot reach Ollama')) throw err
    const msg = err?.message || String(err)
    throw new Error(`Cannot list Ollama models at ${urlBase}/api/tags: ${msg}`)
  } finally {
    if (timer) clearTimeout(timer)
  }
}

/** @param {string} requested @param {string[]} installed */
export function matchOllamaModel(requested, installed) {
  const want = String(requested || '').trim()
  if (!want) return null
  const names = (installed || []).map(String).filter(Boolean)
  if (names.includes(want)) return want

  const cloudBase = (n) => {
    const low = n.toLowerCase()
    if (low.endsWith(':cloud')) return n.slice(0, -':cloud'.length)
    if (low.endsWith('-cloud')) return n.slice(0, -'-cloud'.length)
    return n
  }

  const wantBase = want.split(':', 1)[0]
  const wantCloudBase = cloudBase(want).toLowerCase()
  for (const n of names) {
    if (n === want || n.startsWith(`${want}:`) || n.split(':', 1)[0] === want) return n
    if (n.split(':', 1)[0] === wantBase && !want.includes(':')) return n
    if (isOllamaCloudModel(want) || isOllamaCloudModel(n)) {
      if (cloudBase(n).toLowerCase() === wantCloudBase) {
        if (isOllamaCloudModel(want)) {
          if (isOllamaCloudModel(n)) return n
          continue
        }
        return n
      }
    }
  }
  if (isOllamaCloudModel(want)) {
    for (const n of names) {
      if (isOllamaCloudModel(n) && cloudBase(n).toLowerCase() === wantCloudBase) return n
      if (n.split(':', 1)[0].toLowerCase() === wantBase.toLowerCase() && isOllamaCloudModel(n)) return n
    }
  }
  return null
}

/**
 * Reach Ollama, confirm *model* is usable, optionally run a tiny chat probe.
 * Cloud models (`*:cloud`) may be absent from `/api/tags` — those still probe chat.
 * @param {object} opts
 * @param {(msg: string) => void} [opts.onProgress]
 * @returns {Promise<string>} success message
 */
export async function ollamaTestConnection({
  baseUrl = DEFAULT_OLLAMA_URL,
  model = DEFAULT_OLLAMA_MODEL,
  apiKey = '',
  probeChat = true,
  signal,
  timeoutMs = 60000,
  onProgress,
} = {}) {
  const progress = (msg) => {
    try {
      onProgress?.(msg)
    } catch {
      /* ignore UI callback errors */
    }
  }

  const urlBase = normalizeOllamaUrl(baseUrl)
  const modelName = String(model || DEFAULT_OLLAMA_MODEL).trim() || DEFAULT_OLLAMA_MODEL
  const cloudish = isOllamaCloudModel(modelName) || isOllamaCloudHost(urlBase)

  progress(`1/3 Contacting Ollama at ${urlBase}…`)
  const installed = await ollamaListModels(urlBase, {
    signal,
    timeoutMs: Math.min(12000, timeoutMs),
    apiKey,
  })

  progress(`2/3 Checking model "${modelName}"…`)
  let matched = matchOllamaModel(modelName, installed)
  if (!matched) {
    if (cloudish) {
      matched = resolveOllamaChatModel(urlBase, modelName)
      progress(
        `2/3 Cloud model "${matched}" not in local tags — will probe chat (need ollama signin / API key)…`,
      )
    } else {
      const listing = installed.slice(0, 12).join(', ') || '(none)'
      const more = installed.length > 12 ? ` … +${installed.length - 12} more` : ''
      throw new Error(
        `Model "${modelName}" is not installed at ${urlBase}. ` +
        `Installed: ${listing}${more}. Try: ollama pull ${modelName}`,
      )
    }
  }

  let chatModel = resolveOllamaChatModel(urlBase, matched || modelName)
  if (!isOllamaCloudHost(urlBase) && matched) chatModel = matched

  if (!probeChat) {
    return `Connected to ${urlBase}. Model ${chatModel} is available (${installed.length} models listed).`
  }

  progress(
    `3/3 Running chat probe with ${chatModel} (cloud / first load can take a while)…`,
  )
  const chatCtrl = new AbortController()
  const onAbort = () => chatCtrl.abort()
  if (signal) {
    if (signal.aborted) chatCtrl.abort()
    else signal.addEventListener('abort', onAbort, { once: true })
  }
  const timer = setTimeout(() => chatCtrl.abort(), timeoutMs)
  let resp
  let fetchBase = urlBase
  try {
    ;({ resp, fetchBase } = await ollamaFetch(urlBase, '/api/chat', {
      method: 'POST',
      headers: ollamaRequestHeaders(apiKey),
      signal: chatCtrl.signal,
      body: JSON.stringify({
        model: chatModel,
        stream: false,
        messages: [{ role: 'user', content: 'Reply with exactly: OK' }],
        options: { num_predict: 8 },
      }),
    }))
  } catch (err) {
    if (err?.name === 'AbortError') {
      throw new Error(
        `Ollama reached, model "${chatModel}" allowed, but chat probe timed out ` +
        `after ${Math.round(timeoutMs / 1000)}s (model may still be loading).`,
      )
    }
    if (String(err?.message || '').startsWith('Cannot reach Ollama')) throw err
    const msg = err?.message || String(err)
    throw new Error(
      `Ollama reached, model "${chatModel}" allowed, but chat probe failed: ${msg}`,
    )
  } finally {
    clearTimeout(timer)
    if (signal) signal.removeEventListener('abort', onAbort)
  }
  if (!resp.ok) {
    const detail = (await resp.text().catch(() => '')).slice(0, 300)
    throw new Error(ollamaHttpErrorMessage(resp.status, detail || resp.statusText, {
      url: `${fetchBase}/api/chat`, model: chatModel, baseUrl: urlBase,
    }))
  }
  const data = await resp.json()
  const reply = String(data?.message?.content ?? data?.response ?? '').trim()
  const note = reply ? ` Probe reply: ${JSON.stringify(reply.slice(0, 40))}.` : ''
  const cloudNote = cloudish ? ' (cloud)' : ''
  return `Connected to ${urlBase}. Model ${chatModel}${cloudNote} ready (${installed.length} listed).${note}`
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
