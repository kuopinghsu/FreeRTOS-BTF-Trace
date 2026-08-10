import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { describe, it } from 'node:test'
import { normalizeSettings } from '../src/utils/settingsStore.js'

describe('AI settings storage', () => {
  it('defaults to the Ollama preset with empty per-preset fields', () => {
    const s = normalizeSettings(null)
    assert.equal(s.aiPreset, 'ollama')
    assert.equal(s.aiAutoApply, false)
    assert.deepEqual(Object.keys(s.aiPresets).sort(), ['custom', 'gemini', 'ollama', 'openai'])
    assert.deepEqual(s.aiPresets.gemini, {
      baseUrl: '', model: '', apiKey: '', authMode: 'api_key', tlsVerify: true,
    })
    assert.equal(s.aiPresets.ollama.authMode, 'none')
  })

  it('keeps each preset independent', () => {
    const s = normalizeSettings({
      aiPreset: 'custom',
      aiPresets: {
        custom: { baseUrl: 'http://gateway.internal/v1', model: 'm', apiKey: 'a' },
        ollama: { model: 'llama3.2:3b' },
      },
    })
    assert.equal(s.aiPreset, 'custom')
    assert.equal(s.aiPresets.custom.apiKey, 'a')
    assert.equal(s.aiPresets.ollama.model, 'llama3.2:3b')
    assert.equal(s.aiPresets.ollama.apiKey, '')
  })

  it('migrates pre-preset provider settings', () => {
    const s = normalizeSettings({
      aiProvider: 'openai_compatible',
      openaiPreset: 'gemini',
      openaiBaseUrl: 'https://generativelanguage.googleapis.com/v1beta/openai',
      openaiModel: 'gemini-3.6-flash',
      openaiApiKey: 'cloud-key',
      ollamaUrl: 'http://192.168.1.5:11434',
      ollamaModel: 'llama3.2:3b',
    })
    assert.equal(s.aiPreset, 'gemini')
    assert.equal(s.aiPresets.gemini.apiKey, 'cloud-key')
    assert.equal(s.aiPresets.gemini.model, 'gemini-3.6-flash')
    // Native Ollama roots become the OpenAI-compatible /v1 endpoint.
    assert.equal(s.aiPresets.ollama.baseUrl, 'http://192.168.1.5:11434/v1')
    assert.equal(s.ollamaUrl, undefined)
  })

  it('migrates a legacy OpenAI setup onto the OpenAI preset', () => {
    const s = normalizeSettings({
      aiProvider: 'openai_compatible',
      openaiPreset: 'openai',
      openaiBaseUrl: 'https://api.openai.com/v1',
      openaiModel: 'gpt-4o-mini',
      openaiApiKey: 'sk-keep',
    })
    assert.equal(s.aiPreset, 'openai')
    assert.equal(s.aiPresets.openai.model, 'gpt-4o-mini')
    assert.equal(s.aiPresets.openai.apiKey, 'sk-keep')
    assert.equal(s.aiPresets.custom.baseUrl, '')
  })

  it('migrates a retired vendor preset onto Custom', () => {
    const s = normalizeSettings({
      aiProvider: 'openai_compatible',
      openaiPreset: 'deepseek',
      openaiBaseUrl: 'https://api.deepseek.com/v1',
      openaiApiKey: 'ds-key',
    })
    assert.equal(s.aiPreset, 'custom')
    assert.equal(s.aiPresets.custom.baseUrl, 'https://api.deepseek.com/v1')
    assert.equal(s.aiPresets.custom.apiKey, 'ds-key')
  })

  it('Display tab lists Timeline overlays before Analysis thresholds', () => {
    const src = readFileSync(new URL('../src/components/SettingsDialog.vue', import.meta.url), 'utf8')
    const overlays = src.indexOf('Timeline overlays')
    const analysis = src.indexOf('Analysis thresholds')
    assert.ok(overlays >= 0 && analysis > overlays)
  })

  it('AI model field has a refresh control', () => {
    const src = readFileSync(new URL('../src/components/SettingsDialog.vue', import.meta.url), 'utf8')
    assert.match(src, /onRefreshModels/)
    assert.match(src, /role="combobox"/)
    assert.match(src, /ai-model-listbox/)
    assert.match(src, /Show model list/)
    assert.match(src, /aiListModels/)
    assert.match(src, /Refresh model list/)
    assert.doesNotMatch(src, /<datalist/)
  })

  it('AI settings expose authentication method and sign-in', () => {
    const src = readFileSync(new URL('../src/components/SettingsDialog.vue', import.meta.url), 'utf8')
    assert.match(src, /Authentication/)
    assert.match(src, /onAiSignIn/)
    assert.match(src, /aiAuthMode/)
    const panel = readFileSync(new URL('../src/components/AiAssistantPanel.vue', import.meta.url), 'utf8')
    assert.match(panel, /ai-auth-chip/)
    assert.match(panel, /authChipLabel/)
    assert.match(panel, /authForced/)
    assert.match(panel, /showSignInCta/)
    assert.match(panel, /Opened \$\{url\}\. Paste the key or token in Settings/)
  })
})
