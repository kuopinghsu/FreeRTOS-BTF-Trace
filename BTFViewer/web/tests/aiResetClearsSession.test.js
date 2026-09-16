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
})
