import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import {
  AI_PROVIDER_OLLAMA,
  AI_PROVIDER_OPENAI,
  buildAiSystemPrompt,
  isLocalOllamaUrl,
  normalizeAiProvider,
  normalizeOllamaUrl,
  normalizeOpenaiBaseUrl,
  ollamaSameOriginProxyBase,
  applyOpenaiPreset,
} from '../src/utils/ollamaClient.js'

describe('ollama URL helpers', () => {
  it('normalizes trailing slash and /api', () => {
    assert.equal(normalizeOllamaUrl('http://localhost:11434/'), 'http://localhost:11434')
    assert.equal(normalizeOllamaUrl('http://localhost:11434/api'), 'http://localhost:11434')
  })

  it('detects local Ollama hosts', () => {
    assert.equal(isLocalOllamaUrl('http://localhost:11434'), true)
    assert.equal(isLocalOllamaUrl('http://127.0.0.1:11434'), true)
    assert.equal(isLocalOllamaUrl('https://ollama.com'), false)
  })

  it('same-origin proxy is null without a browser window', () => {
    assert.equal(ollamaSameOriginProxyBase('http://localhost:11434'), null)
  })

  it('buildAiSystemPrompt includes reply language', () => {
    assert.match(buildAiSystemPrompt('English'), /Always write your entire reply in English/)
    assert.match(
      buildAiSystemPrompt('Japanese (日本語)'),
      /Always write your entire reply in Japanese \(日本語\)/,
    )
  })

  it('normalizeAiProvider', () => {
    assert.equal(normalizeAiProvider(undefined), AI_PROVIDER_OLLAMA)
    assert.equal(normalizeAiProvider('openai'), AI_PROVIDER_OPENAI)
    assert.equal(normalizeAiProvider('OpenAI-compatible'), AI_PROVIDER_OPENAI)
  })

  it('normalizeOpenaiBaseUrl', () => {
    assert.equal(normalizeOpenaiBaseUrl('https://api.openai.com'), 'https://api.openai.com/v1')
    assert.equal(
      normalizeOpenaiBaseUrl('https://api.openai.com/v1/chat/completions'),
      'https://api.openai.com/v1',
    )
  })

  it('applyOpenaiPreset fills URL and model', () => {
    const applied = applyOpenaiPreset('gemini')
    assert.equal(applied.openaiPreset, 'gemini')
    assert.match(applied.openaiBaseUrl, /generativelanguage/)
    assert.equal(applied.openaiModel, 'gemini-3.1-flash-lite')
  })

  it('normalizeApiKey strips Bearer and quotes', async () => {
    const { normalizeApiKey, openaiRequestHeaders } = await import('../src/utils/ollamaClient.js')
    assert.equal(normalizeApiKey('  Bearer AIzaSyAbc  '), 'AIzaSyAbc')
    assert.equal(normalizeApiKey('"AIzaSyAbc"'), 'AIzaSyAbc')
    assert.equal(normalizeApiKey('\u201cAIzaSyAbc\u201d'), 'AIzaSyAbc')
    assert.equal(normalizeApiKey('AIza\u5bc6\u94a5SyAbc'), 'AIzaSyAbc')
    const h = openaiRequestHeaders(
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

  it('resolveOpenaiApiKey falls back to runtime env bag', async () => {
    const { resolveOpenaiApiKey, resolveOllamaApiKey } = await import('../src/utils/ollamaClient.js')
    globalThis.window = globalThis.window || {}
    window.__BTF_AI_ENV__ = { OPENAI_API_KEY: 'sk-from-env' }
    try {
      assert.equal(resolveOpenaiApiKey(''), 'sk-from-env')
      assert.equal(resolveOpenaiApiKey('sk-settings'), 'sk-settings')
      window.__BTF_AI_ENV__ = { OLLAMA_API_KEY: 'ollama-env' }
      assert.equal(resolveOllamaApiKey(''), 'ollama-env')
    } finally {
      delete window.__BTF_AI_ENV__
    }
  })
})
