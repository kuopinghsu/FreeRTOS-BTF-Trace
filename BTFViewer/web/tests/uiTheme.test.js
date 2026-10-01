import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import {
  BUTTON_ROLES,
  REPORT_EXPAND_FRACTION,
  REPORT_EXPAND_TABS,
  TEXT_CONTRAST_MIN,
  UI_CONTRAST_MIN,
  UI_THEME,
  contrastRatio,
  expandedReportWidth,
  reportExpandAllowed,
  reportExpandButton,
  statusCueText,
  uiThemeTokens,
} from '../src/utils/uiTheme.js'

const here = dirname(fileURLToPath(import.meta.url))
const appVue = readFileSync(join(here, '../src/App.vue'), 'utf8')
const aiVue = readFileSync(join(here, '../src/components/AiAssistantPanel.vue'), 'utf8')

describe('uiTheme', () => {
  it('exposes the Modern UX semantic palette', () => {
    assert.equal(UI_THEME.dark.workspace, '#151A22')
    assert.equal(UI_THEME.light.workspace, '#F5F7FA')
    assert.equal(UI_THEME.dark.accent_ui, '#78A9FF')
    assert.equal(UI_THEME.light.accent_ui, '#2563EB')
    assert.deepEqual([...BUTTON_ROLES], ['primary', 'secondary', 'quiet', 'destructive'])
  })

  it('meets text 4.5:1 and control / focus 3:1 contrast', () => {
    for (const [mode, t] of Object.entries(UI_THEME)) {
      for (const bg of ['workspace', 'surface']) {
        for (const fg of ['fg', 'fg_dim', 'warning', 'success', 'destructive']) {
          assert.ok(contrastRatio(t[fg], t[bg]) >= TEXT_CONTRAST_MIN, `${mode} ${fg}/${bg}`)
        }
        for (const fg of ['focus', 'control_border', 'accent_ui']) {
          assert.ok(contrastRatio(t[fg], t[bg]) >= UI_CONTRAST_MIN, `${mode} ${fg}/${bg}`)
        }
      }
      assert.ok(contrastRatio(t.on_accent, t.accent_ui) >= TEXT_CONTRAST_MIN, `${mode} on_accent`)
    }
  })

  it('pairs status colors with a glyph', () => {
    assert.equal(statusCueText('Request failed', 'error'), '✖ Request failed')
    assert.equal(statusCueText('✖ Request failed', 'error'), '✖ Request failed')
    assert.equal(statusCueText('Partial trace', 'warning'), '⚠ Partial trace')
    assert.equal(statusCueText('Done.', 'info'), 'Done.')
    assert.equal(statusCueText('', 'error'), '')
  })

  it('computes expanded report width and allowed tabs', () => {
    assert.equal(REPORT_EXPAND_FRACTION, 0.82)
    assert.deepEqual([...REPORT_EXPAND_TABS], ['stats', 'ai'])
    assert.equal(reportExpandAllowed('stats'), true)
    assert.equal(reportExpandAllowed('ai'), true)
    assert.equal(reportExpandAllowed('marks'), false)
    assert.equal(expandedReportWidth(1000), 760)
    assert.equal(expandedReportWidth(1600), 1312)
    assert.equal(expandedReportWidth(400), 180)
    assert.equal(expandedReportWidth(0), 180)
    assert.equal(expandedReportWidth(618, undefined, undefined, 450), 450)
    assert.equal(expandedReportWidth(1600, undefined, undefined, 450), 1312)
    for (let w = 420; w < 3000; w += 37) {
      const got = expandedReportWidth(w)
      assert.ok(w - got >= 240, `timeline keeps 240px at ${w}`)
      assert.ok(got >= 180, `report keeps 180px at ${w}`)
    }
    assert.equal(uiThemeTokens(true).surface, '#1D2430')
    assert.equal(uiThemeTokens(false).surface, '#FFFFFF')
  })

  it('App.vue wires Expand report, welcome CTAs, and shared buttons', () => {
    assert.match(appVue, /data-testid="rp-expand-btn"/)
    assert.match(appVue, /reportExpandBtn\.label/)
    assert.match(appVue, /suspendReportExpansionForEvidence\(\)/)
    assert.equal(reportExpandButton(false).label, 'Expand report')
    assert.equal(reportExpandButton(true).label, 'Restore layout')
    assert.equal(reportExpandButton(false, true).label, 'Back to report')
    assert.equal(reportExpandButton(true, true).label, 'Restore layout')
    assert.match(appVue, /data-testid="welcome-page"/)
    assert.match(appVue, /Load bundled demo/)
    assert.match(appVue, /class="btn-primary"/)
    assert.match(appVue, /class="btn-secondary"/)
  })

  it('AI panel moves Language\/Settings\/Clear into the ⋯ menu on the header line', () => {
    assert.match(aiVue, /data-testid="ai-overflow-btn"/)
    assert.match(aiVue, /Panel actions/)
    assert.doesNotMatch(aiVue, /Actions…/)
    const header = aiVue.slice(aiVue.indexOf('<div class="ai-header">'))
    const headerEnd = header.indexOf('<div\n      v-if="notebookCollab')
    assert.match(header.slice(0, headerEnd), /data-testid="ai-overflow-btn"[\s\S]*?>\s*⋯\s*</)
    assert.match(aiVue, /Language…/)
    assert.match(aiVue, />\s*Clear\s*</)
    assert.match(aiVue, /Settings…\s*<\/button>\s*<div\s+class="ai-overflow-sep"\s+role="separator"\s*\/>\s*<button[\s\S]*?>\s*Clear\s*</)
  })
})
