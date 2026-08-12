/**
 * Ollama client + diagnostic prompt templates for the web AI Assistant.
 * Keep template prompts in sync with btf_viewer_pkg/ai_assistant.py
 * (documented in AI.md; UI usage in README.md § AI Assistant).
 */

import {
  AI_TOOL_SYSTEM_ADDENDUM,
  aiViewerTools,
  assistantMessageText,
  emptyChatCompletionError,
  ensureGeminiThoughtSignatures,
  extractToolCalls,
  mergeToolCalls,
  needsGeminiThoughtSignatures,
  normalizeToolChatMessages,
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
  'value in the trace time unit (e.g. jump:1805120). ' +
  'For every important conclusion, cite evidence (metric names, counts, ' +
  'jump:TIME ranges) and state confidence as High, Medium, or Low — and ' +
  'whether the evidence is Directly observed, Strong correlation, Possible ' +
  'explanation, or Insufficient evidence. Do not invent numbers, task names, ' +
  'or jump:TIME timestamps that are not in the findings, tool results, or ' +
  'Trace Compare tables. If a Cursor region window is listed, only cite ' +
  'jump:TIME values inside that window (or say the window has no matching ' +
  'evidence). Keep answers concise. '
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
]

/** Keep in sync with btf_viewer_pkg/ai_assistant.py (seconds). */
export const AI_CHAT_TIMEOUT_MS = 120000
export const AI_LIST_MODELS_TIMEOUT_MS = 12000
export const AI_TEST_TIMEOUT_MS = 120000

export function buildAiSystemPrompt(responseLanguage = DEFAULT_AI_RESPONSE_LANGUAGE) {
  const lang = String(responseLanguage || DEFAULT_AI_RESPONSE_LANGUAGE).trim()
    || DEFAULT_AI_RESPONSE_LANGUAGE
  return `${AI_SYSTEM_PROMPT} Always write your entire reply in ${lang}.`
}

export const AI_COMPARE_TEMPLATE_ID = 'compare'

// Templates that only make sense for a multi-core (SMP) trace — keep in sync
// with btf_viewer_pkg/ai_assistant.py AI_SMP_ONLY_TEMPLATE_IDS.
export const AI_SMP_ONLY_TEMPLATE_IDS = new Set(['migrations', 'balance'])

/** Always-visible chips (one row). Keep in sync with btf_viewer_pkg/ai_assistant.py. */
export const AI_TEMPLATE_PRIMARY_IDS = [
  'investigate',
  'findings',
  'explain_region',
  'auto_investigate',
]

/** Overflow menu groups for templates not in AI_TEMPLATE_PRIMARY_IDS. */
export const AI_TEMPLATE_MENU_GROUPS = [
  { label: 'Diagnose', ids: ['root_cause', 'verify', 'triage', 'diagnostic_report'] },
  { label: 'Compare', ids: ['compare'] },
  {
    label: 'Metrics',
    ids: [
      'task_profile', 'latency', 'wcet', 'migrations', 'balance',
      'tick', 'priority', 'deadlines',
    ],
  },
  { label: 'What-if / Optimize', ids: ['what_if', 'optimize'] },
]

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
    id: 'investigate',
    label: 'Investigate',
    prompt:
      'Investigate the main performance problem in this scope. First call ' +
      'investigate() to get hypotheses and an evidence chain, then use ' +
      'query_raw_metric and search_timeline as needed. Place cursors and ' +
      'zoom_to_range on the strongest evidence, highlight the key task, ' +
      'and finish with: (1) goal, (2) numbered investigation steps you ' +
      'took, (3) root cause with confidence, (4) clickable jump:TIME ' +
      'evidence, (5) next mitigation to try.',
  },
  {
    id: 'root_cause',
    label: 'Root cause',
    prompt:
      'Perform root-cause analysis for the top finding. Call ' +
      'investigate(finding_id) first, then follow the chain ' +
      'deadline/WCET → execution → preemption → blocking → mutex → ' +
      'priority inheritance → migration only as far as the evidence ' +
      'supports. Call query_raw_metric / search_timeline when numbers are ' +
      'missing. Set cursors around the worst episode, highlight the ' +
      'victim task, and answer with Root cause, Evidence (bullet list with ' +
      'jump:TIME), Confidence, and Suggested fix.',
  },
  {
    id: 'verify',
    label: 'Verify finding',
    prompt:
      'Verify the selected Analysis Finding. Call investigate(finding_id=ID) ' +
      'first (use the finding_id given in the user message). Then collect ' +
      'evidence with query_raw_metric / correlate_events / search_timeline as ' +
      'needed. Place cursors and zoom_to_range on the strongest evidence. ' +
      'Finish with a verdict: Confirmed, Rejected, or Inconclusive; list ' +
      'Evidence as jump:TIME bullets; Confidence (High/Medium/Low); ' +
      'Alternatives considered; and one next check.',
  },
  {
    id: 'explain_region',
    label: 'Explain region',
    prompt:
      'Explain the current timeline cursor region (scope C1–Cn — see the '
      + 'Cursor region window in context). Stay strictly inside that window: '
      + 'every jump:TIME you cite must fall between C1 and Cn. Identify '
      + 'longest blocking, migrations, priority changes, wakeups, mutex '
      + 'contention, deadline issues, idle gaps, and CPU imbalance in this '
      + 'window. Call correlate_events and query_raw_metric as needed. Use '
      + 'only in-window jump:TIME evidence (or state that tools found none). '
      + 'End with: Summary, Top issues, Evidence, Suggested next action.',
  },
  {
    id: AI_COMPARE_TEMPLATE_ID,
    label: 'Trace Compare',
    prompt:
      'Compare Trace A vs Trace B using the Trace Compare tables in the ' +
      'context. Classify each major delta as Regression, Improvement, or ' +
      'Neutral (CPU, migrations, latency, tick health, sync). State which ' +
      'side is worse for each concern, the likely cause with confidence, ' +
      'and which Statistics section or Trace Compare page to open next. ' +
      'Use jump:TIME when a concrete timestamp is available.',
  },
  {
    id: 'triage',
    label: 'Triage findings',
    prompt:
      'Summarise the Analysis Findings and list the top three issues to ' +
      'investigate first, with the Statistics section to open for each.',
  },
  {
    id: 'task_profile',
    label: 'Task profile',
    prompt:
      'Build an AI task behaviour profile for the hottest or most ' +
      'problematic task in the findings (CPU %, typical / p95 / WCET ' +
      'execution, dispatch, blocking, migrations, sync / priority ' +
      'inheritance). Use query_raw_metric if needed. End with a short ' +
      'assessment checklist (normal / warning) and one Ask-next question.',
  },
  {
    id: 'diagnostic_report',
    label: 'Diagnostic report',
    prompt:
      'Write a structured engineering diagnostic report for this scope: ' +
      'Executive summary, Key findings, CPU / scheduling, WCET / ' +
      'deadlines, Blocking / sync, Migrations, Root cause, ' +
      'Recommendations (only when evidence supports them), and Evidence ' +
      'timeline with jump:TIME links. Use export_report when the user ' +
      'asks to save the report.',
  },
  {
    id: 'what_if',
    label: 'What-if',
    prompt:
      'Call what_if with a concrete change (pin TASK to Core_N, raise ' +
      'priority, reduce mutex contention). The tool runs a heuristic ' +
      'slice-replay simulator (not FreeRTOS kernel). Summarise baseline vs ' +
      'simulated migrations/blocking/load-balance and the labelled ' +
      'disclaimer. Cite evidence; do not invent numbers beyond the tool.',
  },
  {
    id: 'optimize',
    label: 'Optimize',
    prompt:
      'Call optimize_experiment for the hottest task (pin / priority / ' +
      'contention / migration candidates), then summarise the ranked ' +
      'experiments and best cost delta. Optionally call optimize for ' +
      'qualitative mitigations. Label results as heuristic estimates — not ' +
      'measured FreeRTOS behavior. Call investigate() if the top finding ' +
      'is unclear.',
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
  {
    id: 'auto_investigate',
    label: 'Auto investigate',
    prompt:
      'Automatically investigate and confirm the top finding end-to-end. ' +
      'Call investigate(finding_id) first, then correlate_events on the ' +
      'same window. Call find_critical_path to build the causal chain, or ' +
      'detect_priority_inversion instead when investigate flags a ' +
      'priority-inversion finding. Place cursors and zoom_to_range on the ' +
      'strongest evidence. Then call what_if or optimize_experiment to ' +
      'test a concrete mitigation. Finish with a verdict — Confirmed, ' +
      'Rejected, or Inconclusive — Evidence as jump:TIME bullets, ' +
      'Confidence (High/Medium/Low), and one recommended experiment to ' +
      'run next.',
  },
]

// "Ask AI about this event" (timeline segment context menu) — intentionally
// kept out of AI_TEMPLATE_QUESTIONS so it does not show in the template grid.
// Keep in sync with btf_viewer_pkg/ai_assistant.py ASK_EVENT_PROMPT.
export const ASK_EVENT_PROMPT =
  'Explain the timeline event for task {task} on {core} around jump:{ns} ' +
  '(segment {start}-{stop}). Call correlate_events and query_raw_metric as ' +
  'needed. Cite jump:TIME evidence.'

/**
 * Build the ASK_EVENT_PROMPT from a timeline segment hit
 * ({ task, core, start, stop, ns }).
 */
export function composeAskEventPrompt(event) {
  const ev = event || {}
  const num = (key) => {
    const n = Number(ev[key])
    if (!Number.isFinite(n)) return '?'
    return Number.isInteger(n) ? String(n) : String(n)
  }
  const task = String(ev.task || '').trim() || 'the selected task'
  const core = String(ev.core || '').trim() || 'its core'
  return ASK_EVENT_PROMPT
    .replace('{task}', task)
    .replace('{core}', core)
    .replace('{ns}', num('ns'))
    .replace('{start}', num('start'))
    .replace('{stop}', num('stop'))
}

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
export const AI_PRESET_FIELDS = ['baseUrl', 'model', 'apiKey', 'authMode', 'tlsVerify']

export const AI_AUTH_NONE = 'none'
export const AI_AUTH_API_KEY = 'api_key'
export const AI_AUTH_BROWSER = 'browser'
export const AI_AUTH_MODES = [AI_AUTH_NONE, AI_AUTH_API_KEY, AI_AUTH_BROWSER]
export const AI_AUTH_MODE_LABELS = [
  [AI_AUTH_NONE, 'None (local)'],
  [AI_AUTH_API_KEY, 'API key'],
  [AI_AUTH_BROWSER, 'Sign in'],
]

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
  [AI_PRESET_OLLAMA]: 'https://ollama.com/settings/keys',
}

export const AI_PRESET_SIGNIN_LABELS = {
  [AI_PRESET_OPENAI]: 'Sign in with OpenAI…',
  [AI_PRESET_GEMINI]: 'Sign in with Google…',
  [AI_PRESET_OLLAMA]: 'Open Ollama sign-in…',
  [AI_PRESET_CUSTOM]: 'Open provider sign-in…',
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
  const baseUrl = String(stored.baseUrl || '') || info.baseUrl
  return {
    preset,
    baseUrl,
    model: String(stored.model || '') || info.model,
    apiKey: String(stored.apiKey || ''),
    authMode: normalizeAiAuthMode(stored.authMode, { presetId: preset, baseUrl }),
    tlsVerify: parseAiTlsVerify(stored.tlsVerify, true),
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

/** Drop whole-line `//` comments (URLs in strings stay intact). */
export function stripAiSettingsJsonc(text) {
  return String(text || '')
    .split(/\r?\n/)
    .filter((line) => !line.trimStart().startsWith('//'))
    .join('\n')
}

/**
 * Settings patch from an AI settings JSON file (see `examples/ai`).
 *
 * Accepts a flat file describing one endpoint
 * (`{ preset, base_url, model, api_key, auth_mode }`) or a `presets` object carrying
 * several. snake_case and camelCase key names both work, so files exported
 * from either app import into both. Whole-line `//` comments are ignored.
 * Throws `Error` with a user-facing message when the file cannot be applied.
 *
 * @param {string|object} data
 * @returns {{ preset?: string, presets: object, responseLanguage?: string }}
 */
export function parseAiSettingsJson(data) {
  let parsed = data
  if (typeof parsed === 'string') {
    try {
      parsed = JSON.parse(stripAiSettingsJsonc(parsed))
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
    const authMode = jsonStr(fields, 'auth_mode', 'authMode', 'authentication')
    if (authMode) {
      entry.authMode = normalizeAiAuthMode(authMode, { presetId: target, baseUrl })
    }
    const tls = jsonTlsVerify(fields)
    if (tls !== undefined) entry.tlsVerify = tls
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
  let cursors = c.cursors
  if (cursors == null) cursors = []
  else if (!Array.isArray(cursors)) cursors = [cursors]
  return {
    findingsText: String(c.findingsText ?? c.findings_text ?? ''),
    span: String(c.span ?? ''),
    cores: c.cores ?? '',
    scope: String(c.scope ?? ''),
    metrics: c.metrics ?? null,
    cursors,
  }
}

export function formatJumpTimeToken(value) {
  const v = Number(value)
  if (!Number.isFinite(v)) return String(value)
  if (Number.isInteger(v)) return String(v)
  return String(v)
}

export function placedCursorTimes(cursors = []) {
  return (cursors || [])
    .filter(c => c != null && c !== '')
    .map(c => Number(c))
    .filter(n => Number.isFinite(n))
    .sort((a, b) => a - b)
}

export function cursorRegionBounds(cursors = []) {
  const placed = placedCursorTimes(cursors)
  if (placed.length < 2) return null
  const lo = placed[0]
  const hi = placed[placed.length - 1]
  if (hi <= lo) return null
  return { lo, hi }
}

export function appendExplainRegionBounds(prompt, cursors = []) {
  const bounds = cursorRegionBounds(cursors)
  if (!bounds) return String(prompt || '')
  const loS = formatJumpTimeToken(bounds.lo)
  const hiS = formatJumpTimeToken(bounds.hi)
  const extra = (
    `Cursor region window: jump:${loS} … jump:${hiS}. `
    + 'ONLY cite jump:TIME evidence inside this window. '
    + 'If tools return no in-window events, say the region has no matching '
    + 'evidence — do not invent timestamps or task names.'
  )
  const base = String(prompt || '').trimEnd()
  return base ? `${base}\n\n${extra}` : extra
}

export function buildAiUserMessage(query, ctx = {}) {
  const parts = ['### System Trace Context']
  if (ctx.span) parts.push(`- Trace Span: ${ctx.span}`)
  if (ctx.cores != null && ctx.cores !== '') parts.push(`- Cores: ${ctx.cores}`)
  if (ctx.scope) parts.push(`- Statistics scope: ${ctx.scope}`)
  const placed = placedCursorTimes(ctx.cursors)
  if (placed.length) {
    const labels = placed
      .map((t, i) => `C${i + 1}=jump:${formatJumpTimeToken(t)}`)
      .join(', ')
    parts.push(`- Timeline cursors: ${labels}`)
    const bounds = cursorRegionBounds(placed)
    if (bounds) {
      parts.push(
        `- Cursor region window: jump:${formatJumpTimeToken(bounds.lo)} … `
        + `jump:${formatJumpTimeToken(bounds.hi)} `
        + '(only cite jump:TIME evidence inside this window when '
        + 'explaining the region)',
      )
    }
  }
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

export function defaultAiAuthMode(presetId = '', baseUrl = '') {
  const pid = presetId ? normalizeAiPreset(presetId) : ''
  if (pid === AI_PRESET_OLLAMA) return AI_AUTH_NONE
  if (baseUrl && isLocalAiHost(baseUrl)) return AI_AUTH_NONE
  return AI_AUTH_API_KEY
}

export function parseAiTlsVerify(value, defaultValue = true) {
  if (value == null || value === '') return !!defaultValue
  if (typeof value === 'boolean') return value
  const s = String(value).trim().toLowerCase()
  if (['0', 'false', 'no', 'off', 'disable', 'disabled', 'insecure'].includes(s)) {
    return false
  }
  if (['1', 'true', 'yes', 'on', 'enable', 'enabled', 'secure'].includes(s)) {
    return true
  }
  return !!defaultValue
}

function jsonTlsVerify(fields) {
  if (!fields || typeof fields !== 'object') return undefined
  for (const name of ['tls_verify', 'tlsVerify', 'verify_tls', 'verifyTls']) {
    if (Object.prototype.hasOwnProperty.call(fields, name)) {
      return parseAiTlsVerify(fields[name], true)
    }
  }
  for (const name of [
    'insecure_tls', 'insecureTls', 'tls_insecure', 'allow_insecure_tls',
    'allowInsecureTls',
  ]) {
    if (Object.prototype.hasOwnProperty.call(fields, name)) {
      return !parseAiTlsVerify(fields[name], false)
    }
  }
  return undefined
}

export function normalizeAiAuthMode(value, { presetId = '', baseUrl = '' } = {}) {
  const want = String(value || '').trim().toLowerCase().replace(/-/g, '_').replace(/\s+/g, '_')
  const aliases = {
    none: AI_AUTH_NONE,
    local: AI_AUTH_NONE,
    no: AI_AUTH_NONE,
    off: AI_AUTH_NONE,
    api_key: AI_AUTH_API_KEY,
    apikey: AI_AUTH_API_KEY,
    api: AI_AUTH_API_KEY,
    key: AI_AUTH_API_KEY,
    token: AI_AUTH_API_KEY,
    browser: AI_AUTH_BROWSER,
    sign_in: AI_AUTH_BROWSER,
    signin: AI_AUTH_BROWSER,
    login: AI_AUTH_BROWSER,
    oauth: AI_AUTH_BROWSER,
  }
  if (Object.prototype.hasOwnProperty.call(aliases, want)) return aliases[want]
  return defaultAiAuthMode(presetId, baseUrl)
}

export function aiPresetSignInUrl(presetId, baseUrl = '') {
  const pid = normalizeAiPreset(presetId)
  if (AI_PRESET_KEY_URLS[pid]) return AI_PRESET_KEY_URLS[pid]
  const raw = String(baseUrl || '').trim()
  if (/^https?:\/\//i.test(raw)) {
    try {
      return new URL(raw).origin
    } catch {
      return raw
    }
  }
  return ''
}

export function aiPresetSignInLabel(presetId) {
  const pid = normalizeAiPreset(presetId)
  return AI_PRESET_SIGNIN_LABELS[pid] || 'Sign in…'
}

export function aiAuthStatus({
  authMode = '', apiKey = '', baseUrl = '', presetId = '',
} = {}) {
  const mode = normalizeAiAuthMode(authMode, { presetId, baseUrl })
  const hasKey = Boolean(resolveAiApiKey(apiKey))
  if (mode === AI_AUTH_NONE) {
    return { mode, label: 'Local', needsAuth: false, signedIn: false }
  }
  if (hasKey) {
    if (mode === AI_AUTH_BROWSER) {
      return { mode, label: 'Signed in', needsAuth: false, signedIn: true }
    }
    return { mode, label: 'Key saved', needsAuth: false, signedIn: false }
  }
  return {
    mode,
    label: mode === AI_AUTH_BROWSER ? 'Needs sign-in' : 'Needs API key',
    needsAuth: true,
    signedIn: false,
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
 * @param {{ findingsText?: string, metrics?: object, span?: string, cores?: any, scope?: string, cursors?: any[] }} ctx
 */
function aiHttpErrorTip(status, detail = '', baseUrl = '') {
  const low = String(detail || '').toLowerCase()
  const host = String(baseUrl || '').toLowerCase()
  if (status === 401 || status === 403) {
    return (
      ' Check authentication (Settings → AI → Sign in or API key, '
      + 'or OPENAI_API_KEY / GEMINI_API_KEY / VITE_*).'
    )
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

/** Tip when HTTPS to a private / self-signed AI gateway fails in the browser. */
export function aiTlsTip(urlBase, tlsVerify = true) {
  const u = String(urlBase || '')
  if (!/^https:/i.test(u)) return ''
  if (parseAiTlsVerify(tlsVerify, true)) {
    return (
      ' If this host uses a self-signed certificate, the browser cannot skip '
      + 'the check — trust the cert in the OS/browser, use http:// on a private '
      + 'LAN, or enable Allow self-signed TLS in the Desktop app.'
    )
  }
  return (
    ' Allow self-signed TLS is on, but browsers still verify certificates. '
    + 'Trust the cert in the OS/browser, use http:// on a private LAN, or '
    + 'use the Desktop app.'
  )
}

function aiFetchReachError(urlBase, lastErr, tlsVerify = true) {
  const msg = String(lastErr?.message || lastErr || 'Failed to fetch')
  if (/ISO-8859-1|non ISO-8859-1|code point/i.test(msg)) {
    return new Error(
      'API key contains non-ASCII characters that browsers reject in HTTP headers. '
      + 'Re-paste the raw key (ASCII only), Save, then Test again. '
      + `(${msg})`,
    )
  }
  return new Error(
    `Cannot reach the AI endpoint at ${urlBase}.${aiReachabilityTip(urlBase)}`
    + `${aiTlsTip(urlBase, tlsVerify)} (${msg})`,
  )
}

/**
 * POST to `/chat/completions`, preferring the Vite same-origin proxy.
 * @returns {Promise<{ resp: Response, fetchBase: string }>}
 */
async function aiFetchChat(preset, urlBase, { headers, body, signal, tlsVerify = true }) {
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
  throw aiFetchReachError(urlBase, lastErr, tlsVerify)
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
  cursors = null,
  baseUrl = DEFAULT_AI_BASE_URL,
  model = DEFAULT_AI_MODEL,
  apiKey = '',
  responseLanguage = DEFAULT_AI_RESPONSE_LANGUAGE,
  preset = DEFAULT_AI_PRESET,
  tlsVerify = true,
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
  let chatMessages = normalizeToolChatMessages(messages || [
    { role: 'system', content: buildAiSystemPrompt(responseLanguage) },
    {
      role: 'user',
      content: buildAiUserMessage(query, {
        findingsText,
        metrics,
        span,
        cores,
        scope,
        cursors,
      }),
    },
  ])
  if (needsGeminiThoughtSignatures({ baseUrl: urlBase, model: chatModel, preset })) {
    chatMessages = ensureGeminiThoughtSignatures(chatMessages)
  }
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
      tlsVerify,
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
  let useToolsActive = useTools
  let turn = { content: '', calls: [], msg: {} }
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
      if (useToolsActive && [400, 404, 422].includes(code) && unsupported) {
        delete payload.tools
        delete payload.tool_choice
        useToolsActive = false
        data = await post(payload)
      } else {
        throw err
      }
    }

    const parseTurn = (respBody) => {
      const choice0 = respBody?.choices?.[0] || {}
      const msg = choice0.message || respBody?.message || {}
      let content = assistantMessageText(msg, choice0)
      let calls = extractToolCalls(msg)
      if (!calls.length && choice0.tool_calls) {
        calls = extractToolCalls({ tool_calls: choice0.tool_calls })
      }
      const textCalls = parseToolCallsFromText(content)
      calls = mergeToolCalls(calls, textCalls)
      if (textCalls.length) content = stripParsedToolMarkup(content)
      return { content, calls, msg }
    }

    turn = parseTurn(data)
    if (!turn.content && !turn.calls.length) {
      // Gemini occasionally returns finish_reason=stop with 0 completion tokens.
      data = await post(payload)
      turn = parseTurn(data)
    }
    if (!turn.content && !turn.calls.length && useToolsActive) {
      const nudge = {
        ...payload,
        messages: [
          ...chatMessages,
          {
            role: 'user',
            content:
              'Your previous reply was empty (no text and no tool call). '
              + 'Answer now with a short analysis, or call a tool.',
          },
        ],
      }
      data = await post(nudge)
      turn = parseTurn(data)
    }
  } catch (err) {
    if (err?.name === 'AbortError') {
      if (signal?.aborted && !timedOut) throw err
      throw new Error(
        `OpenAI-compatible request timed out after ${Math.round(timeoutMs / 1000)}s (${urlBase})`,
        { cause: err },
      )
    }
    throw err
  } finally {
    clearTimeout(timer)
    if (signal) signal.removeEventListener('abort', onAbort)
  }

  if (!turn.content && !turn.calls.length) {
    throw new Error(emptyChatCompletionError(data, { hadTools: Boolean(useToolsActive) }))
  }
  return { content: turn.content, tool_calls: turn.calls, message: turn.msg }
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
  tlsVerify = true,
} = {}) {
  const urlBase = normalizeAiBaseUrl(baseUrl)
  const proxyBase = aiSameOriginProxyBase(preset, urlBase)
  const bases = proxyBase ? [proxyBase, urlBase] : [urlBase]
  const timeoutSignal = AbortSignal.timeout(timeoutMs)
  const combined = signal ? AbortSignal.any([signal, timeoutSignal]) : timeoutSignal
  let lastErr = null
  for (const base of bases) {
    try {
      const resp = await fetch(`${base}/models`, {
        method: 'GET',
        headers: aiRequestHeaders(apiKey, urlBase),
        signal: combined,
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
      if (err?.name === 'AbortError' || err?.name === 'TimeoutError') {
        if (signal?.aborted && !timeoutSignal.aborted) throw err
        throw new Error(`Cannot list models at ${urlBase}/models: timed out`, { cause: err })
      }
      lastErr = err
    }
  }
  const msg = lastErr?.message || 'Failed to fetch'
  const via = proxyBase ? ` (also tried ${proxyBase}/models)` : ''
  throw new Error(
    `Cannot list models at ${urlBase}/models${via}: ${msg}.`
    + aiReachabilityTip(urlBase)
    + aiTlsTip(urlBase, tlsVerify),
    { cause: lastErr },
  )
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
  tlsVerify = true,
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
      tlsVerify,
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
      tlsVerify,
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
        + '(GET /models only lists ids and does not run the model). '
        + 'First load of a large model is often slower — wait until it is warm '
        + 'and retry, or Ask in the AI tab. Confirm with curl to the same URL '
        + 'and body; if curl also hangs, the gateway\'s chat upstream is stuck. '
        + 'Try curl with "stream": true if non-stream never returns.',
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
