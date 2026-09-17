import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
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

  // -- 32/33: Cancel (after Import or after Reset to Defaults) must not
  // persist the dialog's draft. Web's Settings dialog is fully transactional
  // (parity with desktop): Cancel and Reset both only mutate an in-dialog
  // draft; only Save/OK ever calls saveSettings(). Reset doesn't close the
  // dialog either, so "Cancel after Import" and "Cancel after Reset" both
  // go through the same onSettingsCancel -> closeSettingsDialog wiring.
  it('Cancel reverts to the pre-open snapshot without persisting (App.vue wiring)', () => {
    const app = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')
    assert.match(app, /settingsRevertSnapshot = normalizeSettings\(appSettings\)/)
    const closeFn = app.match(/function closeSettingsDialog\(\) \{[\s\S]*?\n\}/)
    assert.ok(closeFn, 'closeSettingsDialog not found')
    assert.match(closeFn[0], /applyAppSettings\(snap, \{ silent: true, persist: false \}\)/)
    const cancelFn = app.match(/function onSettingsCancel\(\) \{[\s\S]*?\n\}/)
    assert.ok(cancelFn, 'onSettingsCancel not found')
    assert.match(cancelFn[0], /closeSettingsDialog\(\)/)
    // onReset() only mutates the in-dialog draft/emits a live preview — it
    // never emits 'save', so Reset followed by Cancel takes this same path.
    const dlg = readFileSync(new URL('../src/components/SettingsDialog.vue', import.meta.url), 'utf8')
    const resetFn = dlg.match(/function onReset\(\) \{[\s\S]*?\n\}/)
    assert.ok(resetFn, 'onReset not found')
    assert.doesNotMatch(resetFn[0], /emit\('save'/)
  })

  it('discarding an imported draft without saving leaves localStorage untouched', () => {
    withMemoryLocalStorage(() => {
      saveSettings(normalizeSettings({ aiPreset: 'ollama' }))
      const before = globalThis.localStorage.getItem('btf-viewer-settings-v1')

      // "Open Settings" snapshot, then a draft mutated by Import — never saved.
      const snapshot = loadSettings()
      const draft = normalizeSettings({
        ...snapshot,
        aiPreset: 'openrouter',
        aiExtraPresets: [{ id: 'openrouter', label: 'OpenRouter' }],
        aiPresets: { ...snapshot.aiPresets, openrouter: { baseUrl: 'https://openrouter.ai/api/v1', model: '', apiKey: 'or-key', authMode: '', tlsVerify: true } },
      })
      void draft // Cancel: the draft is discarded, saveSettings is never called.

      assert.equal(globalThis.localStorage.getItem('btf-viewer-settings-v1'), before)
      assert.equal(loadSettings().aiPreset, 'ollama')
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
