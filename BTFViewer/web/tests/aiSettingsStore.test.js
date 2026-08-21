import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { describe, it } from 'node:test'
import {
  loadAiBaselineProfile,
  loadAiSplitBottom,
  loadAiUserInvestigationTemplates,
  normalizeSettings,
  saveAiBaselineProfile,
  saveAiSplitBottom,
  saveAiUserInvestigationTemplates,
} from '../src/utils/settingsStore.js'

function withMemoryLocalStorage(fn) {
  const store = new Map()
  const prev = globalThis.localStorage
  globalThis.localStorage = {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => { store.set(k, String(v)) },
    removeItem: (k) => { store.delete(k) },
  }
  try {
    return fn()
  } finally {
    if (prev === undefined) delete globalThis.localStorage
    else globalThis.localStorage = prev
  }
}

describe('AI settings storage', () => {
  it('defaults to the Ollama preset with empty per-preset fields', () => {
    const s = normalizeSettings(null)
    assert.equal(s.aiPreset, 'ollama')
    assert.equal(s.aiAutoApply, false)
    assert.equal(s.aiContextMode, 'balanced')
    assert.deepEqual(Object.keys(s.aiPresets).sort(), ['custom', 'gemini', 'ollama', 'openai'])
    assert.deepEqual(s.aiExtraPresets, [])
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

  it('keeps extra presets imported from JSON', () => {
    const s = normalizeSettings({
      aiPreset: 'deepseek',
      aiExtraPresets: [{ id: 'deepseek', label: 'DeepSeek' }],
      aiPresets: {
        deepseek: { baseUrl: 'https://api.deepseek.com/v1', model: 'deepseek-v4-flash', apiKey: '', authMode: 'api_key', tlsVerify: true },
      },
    })
    assert.equal(s.aiPreset, 'deepseek')
    assert.equal(s.aiPresets.deepseek.baseUrl, 'https://api.deepseek.com/v1')
    assert.equal(s.aiExtraPresets[0].id, 'deepseek')
    assert.equal(s.aiExtraPresets[0].label, 'DeepSeek')
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

  it('persists the AI baseline profile under its own localStorage key', () => {
    withMemoryLocalStorage(() => {
      assert.deepEqual(loadAiBaselineProfile(), {})
      const profile = { version: 1, samples: 1, tasks: { 'CS[28]': { wcet_us: { n: 1, mean: 100, m2: 0 } } } }
      saveAiBaselineProfile(profile)
      assert.deepEqual(loadAiBaselineProfile(), profile)
      assert.equal(globalThis.localStorage.getItem('btf-viewer-settings-v1'), null)
    })
  })

  it('persists user investigation templates under their own localStorage key', () => {
    withMemoryLocalStorage(() => {
      assert.deepEqual(loadAiUserInvestigationTemplates(), [])
      saveAiUserInvestigationTemplates([
        { id: 'cpu_latency', label: 'CPU Latency', steps: ['investigate', 'correlate_events'] },
      ])
      const loaded = loadAiUserInvestigationTemplates()
      assert.equal(loaded.length, 1)
      assert.equal(loaded[0].label, 'CPU Latency')
      assert.deepEqual(loaded[0].steps, ['investigate', 'correlate_events'])
      assert.equal(globalThis.localStorage.getItem('btf-viewer-settings-v1'), null)
      assert.ok(globalThis.localStorage.getItem('btf-viewer-ai-user-templates-v1'))
    })
  })

  it('persists the AI composer split height under its own localStorage key', () => {
    withMemoryLocalStorage(() => {
      assert.equal(loadAiSplitBottom(), 80)
      saveAiSplitBottom(40)
      assert.equal(loadAiSplitBottom(), 64)
      saveAiSplitBottom(160)
      assert.equal(loadAiSplitBottom(), 160)
      assert.equal(globalThis.localStorage.getItem('btf-viewer-settings-v1'), null)
      assert.equal(globalThis.localStorage.getItem('btf-viewer-ai-split-bottom-v1'), '160')
    })
  })

  it('Reset to Defaults restores statistics layout into saved settings', () => {
    const src = readFileSync(new URL('../src/components/SettingsDialog.vue', import.meta.url), 'utf8')
    assert.match(src, /resetLayout = true/)
    assert.match(src, /normalizeSettings\(null\)/)
    assert.match(src, /statsSectionCollapsed = defaultSectionCollapsed\(\)/)
    const app = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')
    assert.match(app, /meta\.resetLayout \|\| next\?\.resetLayout/)
    assert.match(app, /statsSectionHeights\.value = \{\}/)
    assert.match(app, /appSettings\.statsSectionCollapsed = defaultSectionCollapsed\(\)/)
    const panel = readFileSync(new URL('../src/components/StatisticsPanel.vue', import.meta.url), 'utf8')
    assert.match(panel, /mergeSectionCollapsed\(state\)/)
    assert.match(panel, /deep: true, immediate: true/)
  })

  it('AI settings expose authentication method and sign-in', () => {
    const src = readFileSync(new URL('../src/components/SettingsDialog.vue', import.meta.url), 'utf8')
    assert.match(src, /Authentication/)
    assert.match(src, /onAiSignIn/)
    assert.match(src, /aiAuthMode/)
    // AI_AUTH_MODE_LABELS is [[id, label], …] — map pairs, not Object.entries.
    assert.match(src, /aiAuthModes\.map\(\(\[id, label\]\)/)
    assert.doesNotMatch(src, /Object\.entries\(aiAuthModes\)/)
    const panel = readFileSync(new URL('../src/components/AiAssistantPanel.vue', import.meta.url), 'utf8')
    assert.match(panel, /ai-auth-chip/)
    assert.match(panel, /authChipLabel/)
    assert.match(panel, /authForced/)
    assert.match(panel, /showSignInCta/)
    assert.match(panel, /Opened \$\{url\}\. Paste the key or token in Settings/)
  })
})
