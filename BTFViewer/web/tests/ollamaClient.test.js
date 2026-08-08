import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { describe, it } from 'node:test'
import {
  AI_PRESET_CUSTOM,
  AI_PRESET_GEMINI,
  AI_PRESET_OLLAMA,
  AI_PRESET_OPENAI,
  DEFAULT_AI_BASE_URL,
  DEFAULT_AI_PRESET,
  aiReachabilityTip,
  aiSameOriginProxyBase,
  applyAiPreset,
  buildAiSystemPrompt,
  isLocalAiHost,
  matchModelName,
  migrateAiSettings,
  normalizeAiBaseUrl,
  normalizeAiPreset,
  parseAiSettingsJson,
  resolveAiSettings,
} from '../src/utils/ollamaClient.js'

describe('AI endpoint helpers', () => {
  it('normalizeAiBaseUrl targets the OpenAI-compatible root', () => {
    assert.equal(normalizeAiBaseUrl('http://localhost:11434'), 'http://localhost:11434/v1')
    assert.equal(normalizeAiBaseUrl('http://localhost:11434/api'), 'http://localhost:11434/v1')
    assert.equal(
      normalizeAiBaseUrl('https://api.openai.com/v1/chat/completions'),
      'https://api.openai.com/v1',
    )
    assert.equal(normalizeAiBaseUrl(''), DEFAULT_AI_BASE_URL)
  })

  it('detects local hosts (no API key required)', () => {
    assert.equal(isLocalAiHost('http://localhost:11434/v1'), true)
    assert.equal(isLocalAiHost('http://127.0.0.1:11434/v1'), true)
    assert.equal(isLocalAiHost('http://0.0.0.0:11434/v1'), true)
    assert.equal(isLocalAiHost('http://[::1]:11434/v1'), true)
    assert.equal(isLocalAiHost('http://host.docker.internal:11434/v1'), true)
    assert.equal(isLocalAiHost('https://generativelanguage.googleapis.com/v1beta/openai'), false)
    assert.equal(isLocalAiHost('http://localhost.example.com/v1'), false)
  })

  it('same-origin proxy is null without a browser window', () => {
    assert.equal(aiSameOriginProxyBase(AI_PRESET_OLLAMA, 'http://localhost:11434/v1'), null)
  })

  it('buildAiSystemPrompt includes reply language', () => {
    assert.match(buildAiSystemPrompt('English'), /Always write your entire reply in English/)
    assert.match(
      buildAiSystemPrompt('Japanese (日本語)'),
      /Always write your entire reply in Japanese \(日本語\)/,
    )
  })

  it('normalizeAiPreset keeps the known presets', () => {
    assert.equal(normalizeAiPreset(undefined), DEFAULT_AI_PRESET)
    assert.equal(normalizeAiPreset('ollama'), AI_PRESET_OLLAMA)
    assert.equal(normalizeAiPreset('gemini'), AI_PRESET_GEMINI)
    assert.equal(normalizeAiPreset('openai'), AI_PRESET_OPENAI)
    assert.equal(normalizeAiPreset('chatgpt'), AI_PRESET_OPENAI)
    // Retired presets (xAI, DeepSeek) land on Custom.
    assert.equal(normalizeAiPreset('deepseek'), AI_PRESET_CUSTOM)
  })

  it('applyAiPreset fills URL and model', () => {
    const ollama = applyAiPreset(AI_PRESET_OLLAMA)
    assert.equal(ollama.baseUrl, 'http://localhost:11434/v1')
    const gemini = applyAiPreset(AI_PRESET_GEMINI)
    assert.match(gemini.baseUrl, /generativelanguage/)
    assert.equal(gemini.model, 'gemini-flash-lite-latest')
    const openai = applyAiPreset(AI_PRESET_OPENAI)
    assert.equal(openai.baseUrl, 'https://api.openai.com/v1')
    assert.ok(openai.model)
  })

  it('resolveAiSettings reads per-preset values with defaults', () => {
    const cfg = {
      aiPreset: AI_PRESET_GEMINI,
      aiPresets: {
        ollama: { model: 'llama3.2:3b' },
        gemini: { apiKey: 'k' },
      },
    }
    const active = resolveAiSettings(cfg)
    assert.equal(active.preset, AI_PRESET_GEMINI)
    assert.equal(active.apiKey, 'k')
    assert.equal(active.model, 'gemini-flash-lite-latest')
    const other = resolveAiSettings(cfg, AI_PRESET_OLLAMA)
    assert.equal(other.model, 'llama3.2:3b')
    assert.equal(other.apiKey, '')
  })

  it('migrateAiSettings moves pre-preset settings onto presets', () => {
    const patch = migrateAiSettings({
      aiProvider: 'openai_compatible',
      openaiPreset: 'gemini',
      openaiModel: 'gemini-3.6-flash',
      openaiApiKey: 'cloud-key',
      ollamaUrl: 'http://localhost:11434',
    })
    assert.equal(patch.aiPreset, AI_PRESET_GEMINI)
    assert.equal(patch.aiPresets.gemini.model, 'gemini-3.6-flash')
    assert.equal(patch.aiPresets.gemini.apiKey, 'cloud-key')
    assert.equal(patch.aiPresets.ollama.baseUrl, 'http://localhost:11434/v1')
    assert.equal(migrateAiSettings({ aiPreset: AI_PRESET_OLLAMA }), null)
    // A legacy OpenAI setup keeps its fields under the OpenAI preset.
    const legacyOpenai = migrateAiSettings({
      aiProvider: 'openai_compatible',
      openaiPreset: 'openai',
      openaiBaseUrl: 'https://api.openai.com/v1',
      openaiApiKey: 'sk-keep',
    })
    assert.equal(legacyOpenai.aiPreset, AI_PRESET_OPENAI)
    assert.equal(legacyOpenai.aiPresets.openai.apiKey, 'sk-keep')
    // A legacy xAI setup becomes Custom.
    const legacyXai = migrateAiSettings({
      aiProvider: 'openai_compatible',
      openaiPreset: 'xai',
      openaiBaseUrl: 'https://api.x.ai/v1',
    })
    assert.equal(legacyXai.aiPreset, AI_PRESET_CUSTOM)
    assert.equal(legacyXai.aiPresets.custom.baseUrl, 'https://api.x.ai/v1')
  })

  it('parseAiSettingsJson reads a flat endpoint file', () => {
    const patch = parseAiSettingsJson(JSON.stringify({
      preset: 'gemini',
      base_url: 'https://generativelanguage.googleapis.com/v1beta/openai',
      model: 'gemini-flash-lite-latest',
      api_key: '',
      response_language: 'English',
    }))
    assert.equal(patch.preset, AI_PRESET_GEMINI)
    assert.equal(patch.presets.gemini.model, 'gemini-flash-lite-latest')
    assert.equal(patch.responseLanguage, 'English')
    // An empty key means "fall back to the environment", so nothing is written.
    assert.equal(patch.presets.gemini.apiKey, undefined)
  })

  it('parseAiSettingsJson accepts camelCase, vendor names, and presets maps', () => {
    const openai = parseAiSettingsJson({
      preset: 'openai',
      baseUrl: 'https://api.openai.com',
      model: 'gpt-4o-mini',
      apiKey: 'Bearer sk-test',
    })
    assert.equal(openai.preset, AI_PRESET_OPENAI)
    assert.equal(openai.presets.openai.baseUrl, 'https://api.openai.com/v1')
    assert.equal(openai.presets.openai.apiKey, 'sk-test')

    const xai = parseAiSettingsJson({ preset: 'xai', base_url: 'https://api.x.ai/v1', model: 'grok-2' })
    assert.equal(xai.preset, AI_PRESET_CUSTOM)
    assert.equal(xai.presets.custom.model, 'grok-2')

    const local = parseAiSettingsJson({ base_url: 'http://localhost:11434' })
    assert.equal(local.preset, AI_PRESET_OLLAMA)
    assert.equal(local.presets.ollama.baseUrl, 'http://localhost:11434/v1')

    const multi = parseAiSettingsJson({
      preset: 'ollama',
      presets: { gemini: { api_key: 'k' }, ollama: { model: 'm' } },
    })
    assert.equal(multi.preset, AI_PRESET_OLLAMA)
    assert.equal(multi.presets.gemini.apiKey, 'k')
    assert.equal(multi.presets.ollama.model, 'm')
  })

  it('parseAiSettingsJson reports unusable files', () => {
    for (const bad of [
      'not json',
      '[]',
      '{"preset": "claude"}',
      '{"model": ""}',
      '{"preset": "custom", "model": "m"}',
      '{"base_url": "ftp://example.com"}',
    ]) {
      assert.throws(() => parseAiSettingsJson(bad), Error, `expected throw for ${bad}`)
    }
  })

  it('ships importable example files', () => {
    for (const [name, preset] of [
      ['gemini', AI_PRESET_GEMINI],
      ['openai', AI_PRESET_OPENAI],
      ['deepseek', AI_PRESET_CUSTOM],
      ['grok', AI_PRESET_CUSTOM],
    ]) {
      const text = readFileSync(new URL(`../../examples/ai/${name}.json`, import.meta.url), 'utf8')
      const patch = parseAiSettingsJson(text)
      assert.equal(patch.preset, preset)
      assert.ok(patch.presets[preset].baseUrl)
      assert.ok(patch.presets[preset].model)
    }
  })

  it('matchModelName tolerates missing :tag', () => {
    const served = ['qwen2.5:14b', 'deepseek-r1:14b', 'llama3.2:latest']
    assert.equal(matchModelName('qwen2.5:14b', served), 'qwen2.5:14b')
    assert.equal(matchModelName('qwen2.5', served), 'qwen2.5:14b')
    assert.equal(matchModelName('missing', served), null)
  })

  it('aiReachabilityTip explains blocked local calls', () => {
    const localTip = aiReachabilityTip('http://localhost:11434/v1')
    assert.match(localTip, /ollama serve/)
    assert.match(localTip, /OLLAMA_ORIGINS/)
    assert.match(localTip, /proxy/)
    assert.match(aiReachabilityTip('https://api.openai.com/v1'), /CORS/)
  })

  it('matchModelName ignores the Gemini models/ namespace', () => {
    const served = ['models/gemini-flash-lite-latest', 'models/gemini-2.5-pro']
    assert.equal(
      matchModelName('gemini-flash-lite-latest', served),
      'models/gemini-flash-lite-latest',
    )
    assert.equal(matchModelName('models/gemini-2.5-pro', served), 'models/gemini-2.5-pro')
    assert.equal(matchModelName('gemini-9.9-pro', served), null)
  })

  it('normalizeApiKey strips Bearer and quotes', async () => {
    const { normalizeApiKey, aiRequestHeaders } = await import('../src/utils/ollamaClient.js')
    assert.equal(normalizeApiKey('  Bearer AIzaSyAbc  '), 'AIzaSyAbc')
    assert.equal(normalizeApiKey('"AIzaSyAbc"'), 'AIzaSyAbc')
    assert.equal(normalizeApiKey('\u201cAIzaSyAbc\u201d'), 'AIzaSyAbc')
    assert.equal(normalizeApiKey('AIza\u5bc6\u94a5SyAbc'), 'AIzaSyAbc')
    const h = aiRequestHeaders(
      'AIzaSyAbc',
      'https://generativelanguage.googleapis.com/v1beta/openai',
    )
    assert.equal(h.Authorization, 'Bearer AIzaSyAbc')
    assert.equal(h['x-goog-api-key'], undefined)
  })

  it('normalizeAiContext accepts snake_case and camelCase', async () => {
    const { normalizeAiContext } = await import('../src/utils/ollamaClient.js')
    assert.equal(normalizeAiContext({ findings_text: 'a' }).findingsText, 'a')
    assert.equal(normalizeAiContext({ findingsText: 'b' }).findingsText, 'b')
  })

  it('resolveAiApiKey falls back to runtime env bag', async () => {
    const { resolveAiApiKey } = await import('../src/utils/ollamaClient.js')
    globalThis.window = globalThis.window || {}
    window.__BTF_AI_ENV__ = { OPENAI_API_KEY: 'sk-from-env' }
    try {
      assert.equal(resolveAiApiKey(''), 'sk-from-env')
      assert.equal(resolveAiApiKey('sk-settings'), 'sk-settings')
      window.__BTF_AI_ENV__ = { OLLAMA_API_KEY: 'ollama-env' }
      assert.equal(resolveAiApiKey(''), 'ollama-env')
    } finally {
      delete window.__BTF_AI_ENV__
    }
  })
})
