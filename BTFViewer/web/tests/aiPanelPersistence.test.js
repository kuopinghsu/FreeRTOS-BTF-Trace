import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { describe, it } from 'node:test'

// There is no DOM test stack here, so guard the template invariant directly:
// the AI page must be hidden rather than unmounted, or the conversation is
// thrown away every time the user visits another right-panel tab.
const app = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')
  .replace(/\s+/g, ' ')
const aiPanel = readFileSync(new URL('../src/components/AiAssistantPanel.vue', import.meta.url), 'utf8')
  .replace(/\s+/g, ' ')
const corridorDlg = readFileSync(new URL('../src/components/CorridorInspectorDialog.vue', import.meta.url), 'utf8')
  .replace(/\s+/g, ' ')
const compareDlg = readFileSync(new URL('../src/components/TraceCompareDialog.vue', import.meta.url), 'utf8')
  .replace(/\s+/g, ' ')

describe('AI panel survives right-panel tab switches', () => {
  it('hides the AI page instead of destroying it', () => {
    assert.match(app, /v-show="rightPanelTab === 'ai'"/)
    assert.doesNotMatch(app, /v-else-if="rightPanelTab === 'ai'"/)
  })

  it('shows Statistics for every tab but AI, including when AI is turned off', () => {
    assert.match(
      app,
      /v-else-if="rightPanelTab !== 'ai' \|\| !aiTabVisible" class="panel-page panel-page-stats"/,
    )
  })

  it('keeps the panel mounted only while the AI tab exists', () => {
    assert.match(app, /v-if="aiTabVisible" v-show="rightPanelTab === 'ai'"/)
  })
})

describe('AI conversation turn layout', () => {
  it('offers Apply GUI actions as a fallback under the log (desktop parity)', () => {
    assert.match(aiPanel, /Apply GUI actions/)
    assert.match(aiPanel, /Undo last actions/)
    assert.match(aiPanel, /toolBarFallback/)
  })

  it('is chat-first: log stretches; modes and templates wrap like desktop', () => {
    const logAt = aiPanel.indexOf('class="ai-log"')
    const modesAt = aiPanel.indexOf('class="ai-modes"')
    const tplAt = aiPanel.indexOf('class="ai-templates"')
    const planAt = aiPanel.indexOf('planStatusText')
    assert.ok(logAt >= 0 && tplAt > logAt)
    assert.ok(planAt > logAt && planAt < modesAt && modesAt < tplAt)
    assert.match(aiPanel, /\.ai-log \{ flex: 1; min-height: 0;/)
    assert.match(aiPanel, /class="ai-modes"/)
    assert.match(aiPanel, /class="ai-templates"/)
    assert.match(aiPanel, /\.ai-templates, \.ai-modes \{/)
    assert.match(aiPanel, /flex-wrap: wrap/)
    assert.match(aiPanel, /primaryTemplates/)
    assert.match(aiPanel, /More templates/)
    assert.match(aiPanel, /templateMenuGroups/)
    assert.match(aiPanel, /ai-more-col/)
    assert.match(aiPanel, /<Teleport to="body">/)
    assert.match(aiPanel, /class="ai-plan-status"/)
    assert.match(aiPanel, /Language…/)
    assert.match(aiPanel, /Settings…/)
    assert.doesNotMatch(aiPanel, /overflowOpen/)
    assert.match(aiPanel, /formatEvidencePanelMarkdown/)
    assert.doesNotMatch(aiPanel, /evidencePanel/)
    assert.match(aiPanel, /statusWithCost\(base, costMeter.value\)/)
    assert.match(aiPanel, /\.ai-more-item:disabled/)
    assert.match(aiPanel, /color: var\(--muted, #8a96a8\)/)
    assert.equal((aiPanel.match(/costMeter.value = emptyCostMeter\(\)/g) || []).length, 1)
  })

  it('opens a mermaid zoom overlay from the figure', () => {
    assert.match(aiPanel, /ai-mermaid-overlay/)
    assert.match(aiPanel, /openMermaidZoom/)
    assert.match(aiPanel, /closeMermaidZoom/)
    assert.match(aiPanel, /onMermaidZoomWheel/)
    assert.match(aiPanel, /Scroll to zoom/)
  })

  it('styles prompt and reply as separate bubbles', () => {
    assert.match(aiPanel, /class="ai-msg"/)
    assert.match(aiPanel, /:class="m\.role"/)
    assert.match(aiPanel, /\.ai-msg\.user \.ai-msg-body/)
    assert.match(aiPanel, /\.ai-msg\.assistant \.ai-msg-body/)
    assert.match(aiPanel, /#1e3348/)
    assert.match(aiPanel, /#1a2620/)
    assert.match(aiPanel, /#6ea8e0/)
    assert.match(aiPanel, /#6fbf9a/)
    assert.match(aiPanel, /\.ai-msg \+ \.ai-msg/)
  })
})

describe('Migration inspector Query with AI', () => {
  it('footer emits query-ai and App wires the migrations template', () => {
    assert.match(corridorDlg, /Query with AI/)
    assert.match(corridorDlg, /emit\('query-ai'\)/)
    assert.match(app, /@query-ai="queryCorridorWithAi"/)
    assert.match(app, /focusAiAndAsk\('migrations'\)/)
  })
})

describe('Trace Compare Query with AI', () => {
  it('footer emits query-ai and App runs the compare template', () => {
    assert.match(compareDlg, /Query with AI/)
    assert.match(compareDlg, /emit\('query-ai'/)
    assert.match(app, /@query-ai="queryCompareWithAi"/)
    assert.match(app, /askCompare\?\.\(idA, idB\)/)
    assert.match(aiPanel, /async function askCompare/)
  })
})

describe('right-panel tab visibility (desktop parity)', () => {
  it('gates Marks and Find tabs on settings flags and labels Marks Marks', () => {
    assert.match(app, /v-if="appSettings.showMarks"/)
    assert.match(app, /v-if="appSettings.showFind"/)
    assert.match(app, /> Marks </)
    assert.doesNotMatch(app, /Cursor \/ Bookmark/)
  })

  it('keeps Legend independent of the Marks tab', () => {
    assert.match(app, /v-if="appSettings.showLegend"/)
    assert.match(app, /rightPanelTab === 'legend'/)
    assert.match(app, /tab === 'legend' && s\.showLegend/)
    const legendTab = app.indexOf("rightPanelTab === 'legend'")
    const legendPanel = app.indexOf('<LegendPanel')
    const marksTab = app.indexOf("rightPanelTab === 'marks'")
    assert.ok(legendTab >= 0 && legendPanel >= 0)
    assert.ok(legendPanel > legendTab, 'LegendPanel must live on the Legend page')
    assert.ok(marksTab >= 0 && marksTab < legendTab)
  })
})
