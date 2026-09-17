import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { describe, it } from 'node:test'

// Reset to Defaults must also clear the AI investigation session/response
// history — both the visible chat (AiAssistantPanel's own state) and the
// persisted btf-viewer-session-v2 blob (via scheduleSessionSave(), which
// reads aiPanelRef.value.investigationSnapshot()). Desktop mirrors this by
// calling `_ai_panel.clear_conversation()` from the Settings-Accept
// reset_requested branch in mainwindow.py.
const app = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')

describe('Reset to Defaults clears the AI conversation', () => {
  it('onSettingsSave clears the AI panel before re-saving the session snapshot', () => {
    const m = app.match(/function onSettingsSave\(next, meta = \{\}\) \{[\s\S]*?\n\}/)
    assert.ok(m, 'onSettingsSave not found')
    const body = m[0]
    const resetBlock = body.match(/if \(resetLayout\) \{[\s\S]*?\n {2}\}/)
    assert.ok(resetBlock, 'resetLayout block not found inside onSettingsSave')
    const block = resetBlock[0]
    assert.match(block, /aiPanelRef\.value\?\.clear\?\.\(\)/)
    // Order matters: clear the panel before scheduling the session re-save,
    // so the persisted btf-viewer-session-v2 snapshot picks up empty chat.
    const clearIdx = block.indexOf('aiPanelRef.value?.clear?.()')
    const scheduleIdx = block.indexOf('scheduleSessionSave()')
    assert.ok(clearIdx >= 0 && scheduleIdx >= 0 && clearIdx < scheduleIdx)
  })

  // Regression coverage for TODO.bak/TODO.md P1: Reset must also clear the
  // AI personalization/history/baseline localStorage keys (baseline
  // profile, user templates/knowledge, split position, template MRU/usage)
  // and re-sync the live panel's in-memory copies of them — not just the
  // conversation. Desktop mirrors this with clear_section("ai") +
  // _clear_template_history() / _restore_ai_split() in mainwindow.py.
  it('onSettingsSave clears AI personalization state and re-syncs the panel', () => {
    const m = app.match(/function onSettingsSave\(next, meta = \{\}\) \{[\s\S]*?\n\}/)
    assert.ok(m, 'onSettingsSave not found')
    const body = m[0]
    const resetBlock = body.match(/if \(resetLayout\) \{[\s\S]*?\n {2}\}/)
    assert.ok(resetBlock, 'resetLayout block not found inside onSettingsSave')
    const block = resetBlock[0]
    assert.match(block, /clearAiPersistentState\(\)/)
    assert.match(block, /aiPanelRef\.value\?\.resetPersonalizationState\?\.\(\)/)
    // clearAiPersistentState() must run before the panel re-syncs its
    // in-memory copies of the (now-cleared) template MRU/usage/split keys.
    const clearStateIdx = block.indexOf('clearAiPersistentState()')
    const resetPersonalizationIdx = block.indexOf('aiPanelRef.value?.resetPersonalizationState?.()')
    assert.ok(
      clearStateIdx >= 0 && resetPersonalizationIdx >= 0
      && clearStateIdx < resetPersonalizationIdx,
    )
    assert.match(app, /clearAiPersistentState,?\s*\n?\s*\} from '\.\/utils\/settingsStore\.js'/)
  })

  it('AiAssistantPanel exposes resetPersonalizationState separately from clear', () => {
    const panel = readFileSync(
      new URL('../src/components/AiAssistantPanel.vue', import.meta.url), 'utf8')
    assert.match(panel, /function resetPersonalizationState\(\)/)
    assert.match(panel, /recentTemplateIds\.value = loadAiRecentTemplates\(\)/)
    assert.match(panel, /templateUsage\.value = loadAiTemplateUsage\(\)/)
    assert.match(panel, /splitBottom\.value = loadAiSplitBottom\(\)/)
    assert.match(panel, /resetPersonalizationState,/)
    // clear() is also the in-panel "New chat" button's handler — it must
    // not be folded into the personalization reset.
    const clearFn = panel.match(/function clear\(\) \{[\s\S]*?\n\}/)
    assert.ok(clearFn, 'clear() not found')
    assert.doesNotMatch(clearFn[0], /recentTemplateIds|templateUsage|splitBottom/)
  })
})
