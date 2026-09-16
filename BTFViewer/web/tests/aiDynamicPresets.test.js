import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { loadSettings, saveSettings, normalizeSettings } from '../src/utils/settingsStore.js'
import { sanitizeAiPresetId } from '../src/utils/aiClient.js'

// Dynamic AI preset import / persistence / Reset to Defaults --
// TODO.bak/BTFVIEWER_AI_SETTINGS_DYNAMIC_PRESET_TODO.md, web side.

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

describe('AI dynamic preset persistence (web)', () => {
  it('an unknown imported preset survives a reload (localStorage round trip)', () => {
    withMemoryLocalStorage(() => {
      const draft = normalizeSettings({
        aiPreset: 'openrouter',
        aiExtraPresets: [{ id: 'openrouter', label: 'OpenRouter' }],
        aiPresets: {
          openrouter: {
            baseUrl: 'https://openrouter.ai/api/v1', model: 'openai/gpt-5',
            apiKey: 'or-key', authMode: 'api_key', tlsVerify: true,
          },
        },
      })
      saveSettings(draft)

      const reloaded = loadSettings()
      assert.equal(reloaded.aiPreset, 'openrouter')
      assert.deepEqual(reloaded.aiExtraPresets.map((e) => e.id), ['openrouter'])
      assert.equal(reloaded.aiPresets.openrouter.baseUrl, 'https://openrouter.ai/api/v1')
      assert.equal(reloaded.aiPresets.openrouter.model, 'openai/gpt-5')
      assert.equal(reloaded.aiPresets.openrouter.apiKey, 'or-key')
    })
  })

  it('re-importing the same preset (case/spacing variant) updates it instead of duplicating', () => {
    withMemoryLocalStorage(() => {
      saveSettings(normalizeSettings({
        aiPreset: 'openrouter',
        aiExtraPresets: [{ id: 'openrouter', label: 'OpenRouter' }],
        aiPresets: { openrouter: { baseUrl: '', model: 'openai/gpt-5', apiKey: '', authMode: '', tlsVerify: true } },
      }))
      const first = loadSettings()

      // Re-import as "OpenRouter" / "open-router" style spelling with new values.
      const merged = normalizeSettings({
        ...first,
        aiPreset: sanitizeAiPresetId('OpenRouter'),
        aiExtraPresets: [...first.aiExtraPresets, { id: 'OpenRouter', label: 'OpenRouter' }],
        aiPresets: { ...first.aiPresets, openrouter: { ...first.aiPresets.openrouter, model: 'openai/gpt-5.1' } },
      })
      saveSettings(merged)

      const reloaded = loadSettings()
      const matches = reloaded.aiExtraPresets.filter((e) => e.id === 'openrouter')
      assert.equal(matches.length, 1)
      assert.equal(reloaded.aiPresets.openrouter.model, 'openai/gpt-5.1')
    })
  })

  it('multiple imported presets coexist after reload', () => {
    withMemoryLocalStorage(() => {
      saveSettings(normalizeSettings({
        aiPreset: 'openrouter',
        aiExtraPresets: [
          { id: 'openrouter', label: 'OpenRouter' },
          { id: 'deepseek', label: 'DeepSeek' },
        ],
        aiPresets: {
          openrouter: { baseUrl: 'https://openrouter.ai/api/v1', model: 'openai/gpt-5', apiKey: '', authMode: '', tlsVerify: true },
          deepseek: { baseUrl: 'https://api.deepseek.com/v1', model: 'deepseek-chat', apiKey: '', authMode: '', tlsVerify: true },
        },
      }))
      const reloaded = loadSettings()
      const ids = reloaded.aiExtraPresets.map((e) => e.id).sort()
      assert.deepEqual(ids, ['deepseek', 'openrouter'])
      assert.equal(reloaded.aiPresets.deepseek.model, 'deepseek-chat')
    })
  })

  it('importing a new preset merges with, rather than replaces, existing extras', () => {
    withMemoryLocalStorage(() => {
      saveSettings(normalizeSettings({
        aiPreset: 'openrouter',
        aiExtraPresets: [
          { id: 'openrouter', label: 'OpenRouter' },
          { id: 'deepseek', label: 'DeepSeek' },
        ],
        aiPresets: {
          openrouter: { baseUrl: '', model: '', apiKey: '', authMode: '', tlsVerify: true },
          deepseek: { baseUrl: '', model: '', apiKey: '', authMode: '', tlsVerify: true },
        },
      }))
      const before = loadSettings()
      // Simulate the Settings dialog's import handler: append the newly
      // imported preset onto the existing draft (not a fresh object).
      const draft = normalizeSettings({
        ...before,
        aiPreset: 'grok',
        aiExtraPresets: [...before.aiExtraPresets, { id: 'grok', label: 'Grok' }],
        aiPresets: { ...before.aiPresets, grok: { baseUrl: '', model: '', apiKey: '', authMode: '', tlsVerify: true } },
      })
      saveSettings(draft)

      const reloaded = loadSettings()
      const ids = reloaded.aiExtraPresets.map((e) => e.id).sort()
      assert.deepEqual(ids, ['deepseek', 'grok', 'openrouter'])
    })
  })

  it('Reset to Defaults (normalizeSettings(null)) wipes every imported preset and credential', () => {
    withMemoryLocalStorage(() => {
      saveSettings(normalizeSettings({
        aiPreset: 'openrouter',
        aiExtraPresets: [{ id: 'openrouter', label: 'OpenRouter' }],
        aiPresets: {
          openrouter: { baseUrl: 'https://openrouter.ai/api/v1', model: 'openai/gpt-5', apiKey: 'or-key', authMode: 'api_key', tlsVerify: true },
          openai: { baseUrl: '', model: '', apiKey: 'sk-live', authMode: 'api_key', tlsVerify: true },
        },
      }))
      assert.equal(loadSettings().aiPresets.openai.apiKey, 'sk-live')

      // Reset to Defaults: the dialog rebuilds its draft from
      // normalizeSettings(null) and Save persists that draft as-is.
      saveSettings(normalizeSettings(null))

      const reloaded = loadSettings()
      assert.deepEqual(reloaded.aiExtraPresets, [])
      assert.deepEqual(Object.keys(reloaded.aiPresets).sort(), ['custom', 'gemini', 'ollama', 'openai'])
      assert.equal(reloaded.aiPresets.openai.apiKey, '')
      assert.equal(reloaded.aiPreset, 'ollama')
      assert.equal(globalThis.localStorage.getItem('btf-viewer-settings-v1').includes('openrouter'), false)
      assert.equal(globalThis.localStorage.getItem('btf-viewer-settings-v1').includes('or-key'), false)
      assert.equal(globalThis.localStorage.getItem('btf-viewer-settings-v1').includes('sk-live'), false)
    })
  })

  it('load -> save -> load is a fixed point for AI preset data (round-trip invariant)', () => {
    withMemoryLocalStorage(() => {
      saveSettings(normalizeSettings({
        aiPreset: 'openrouter',
        aiExtraPresets: [{ id: 'openrouter', label: 'OpenRouter' }],
        aiPresets: {
          openrouter: { baseUrl: 'https://openrouter.ai/api/v1', model: 'openai/gpt-5', apiKey: 'or-key', authMode: 'api_key', tlsVerify: true },
        },
      }))
      const a = loadSettings()
      saveSettings(a)
      const b = loadSettings()
      assert.deepEqual(a.aiExtraPresets, b.aiExtraPresets)
      assert.deepEqual(a.aiPresets, b.aiPresets)
      assert.equal(a.aiPreset, b.aiPreset)
    })
  })

  it('malformed imported preset ids never produce unsafe ids', () => {
    for (const bad of ['', '   ', 'a'.repeat(40), '\x00\x01', '123abc', '---']) {
      assert.equal(sanitizeAiPresetId(bad), '', JSON.stringify(bad))
    }
    const sanitized = sanitizeAiPresetId('../../etc/passwd')
    assert.match(sanitized, /^[a-z][a-z0-9_]*$/)
    assert.ok(!sanitized.includes('/'))
    assert.ok(!sanitized.includes('.'))
  })
})
