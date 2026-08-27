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
const statsPanel = readFileSync(new URL('../src/components/StatisticsPanel.vue', import.meta.url), 'utf8')
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

  it('is chat-first: log stretches; dynamic templates wrap like desktop', () => {
    const logAt = aiPanel.indexOf('class="ai-log"')
    const tplAt = aiPanel.indexOf('class="ai-templates"')
    const planAt = aiPanel.indexOf('planStatusText')
    assert.ok(logAt >= 0 && tplAt > logAt)
    assert.ok(planAt > logAt && planAt < tplAt)
    assert.doesNotMatch(aiPanel, /class="ai-modes"/)
    assert.doesNotMatch(aiPanel, /\.ai-modes \{/)
    assert.doesNotMatch(aiPanel, /primaryTemplates|primaryTemplateRows|ai-tpl-row/)
    assert.match(aiPanel, /\.ai-log \{ flex: 1; min-height: 0;/)
    assert.match(aiPanel, /class="ai-templates"/)
    assert.match(aiPanel, /\.ai-templates \{/)
    assert.match(aiPanel, /flex-wrap: wrap/)
    assert.match(aiPanel, /min-height: 28px/)
    assert.match(aiPanel, /\.ai-header-actions/)
    assert.match(aiPanel, /visibleTemplates/)
    assert.match(aiPanel, /recordTemplateUse/)
    assert.match(aiPanel, /Start Investigation/)
    assert.match(aiPanel, /class="ai-guide-stepper"/)
    assert.match(aiPanel, /jumpGuideStage/)
    assert.match(aiPanel, /ai-msg-flash/)
    assert.match(aiPanel, /dumpInvestigationSession/)
    assert.match(aiPanel, /investigationSessionHasChat/)
    assert.match(aiPanel, /if \(!investigationSessionHasChat\(msgs\)\)/)
    assert.match(compareDlg, /Save as baseline/)
    assert.match(compareDlg, /Score vs baseline/)
    assert.match(compareDlg, /@click="onSaveBaseline"/)
    assert.match(compareDlg, /@click="onScoreBaseline"/)
    assert.match(app, /onCompareSaveBaseline/)
    assert.match(app, /onCompareScoreBaseline/)
    assert.match(compareDlg, /activePage === 'trends'/)
    assert.match(aiPanel, /VERIFY_HINT/)
    assert.match(app, /COMMAND_PALETTE_ACTIONS/)
    assert.match(app, /Ctrl\+K/)
    assert.match(aiPanel, /templateMenuGroups/)
    assert.match(aiPanel, /ai-more-col/)
    assert.match(aiPanel, /<Teleport to="body">/)
    assert.doesNotMatch(aiPanel, /moreBtnEl\.value =/)
    assert.match(app, /body:has\(\.app:not\(\.dark\)\)/)
    assert.match(aiPanel, /class="ai-plan-status"/)
    assert.match(aiPanel, /Language…/)
    assert.match(aiPanel, /Settings…/)
    assert.doesNotMatch(aiPanel, /overflowOpen/)
    assert.match(aiPanel, /formatEvidencePanelMarkdown/)
    assert.match(aiPanel, /ai-ev-panel/)
    assert.match(aiPanel, /toggleEvidenceSubfolds/)
    assert.match(aiPanel, /evidenceSubfoldsExpanded/)
    assert.match(aiPanel, /ai-ev-panel-toggle/)
    assert.match(aiPanel, /syncEvidenceSubfolds/)
    assert.match(aiPanel, /formatContextUsageStatus\(/)
    assert.match(aiPanel, /class="ai-usage-bar"/)
    assert.match(aiPanel, /class="ai-split"/)
    assert.match(aiPanel, /class="ai-split-top"/)
    assert.match(aiPanel, /class="ai-split-handle"/)
    assert.match(aiPanel, /class="ai-split-bottom"/)
    assert.match(aiPanel, /function setErrorStatus/)
    assert.match(aiPanel, /emit\('statusMessage'/)
    assert.match(app, /@status-message="onAiStatusMessage"/)
    assert.match(app, /statusBarFlash/)
    assert.match(aiPanel, /class="ai-composer"/)
    assert.match(aiPanel, /onComposerAction/)
    assert.match(aiPanel, /busy \? 'Stop' : 'Send'/)
    assert.match(aiPanel, /Enter to send, Shift\+Enter for a new line/)
    assert.match(aiPanel, /keydown\.enter\.exact\.prevent/)
    assert.doesNotMatch(aiPanel, /Ctrl\/Cmd\+Enter to send/)
    assert.doesNotMatch(aiPanel, /busy \? 'Waiting…' : 'Ask'/)
    assert.match(aiPanel, /\.ai-more-item:disabled/)
    assert.match(aiPanel, /color: var\(--muted, #8a96a8\)/)
    assert.ok((aiPanel.match(/costMeter\.value = emptyCostMeter\(\)/g) || []).length >= 1)
    assert.match(aiPanel, /evidencePayload = null/)
    assert.match(aiPanel, /investigationPlan\.value = null/)
    assert.match(aiPanel, /Clear replies, usage cost, and current investigation issues/)
  })

  it('opens a mermaid zoom overlay from the figure', () => {
    assert.match(aiPanel, /ai-mermaid-overlay/)
    assert.match(aiPanel, /openMermaidZoom/)
    assert.match(aiPanel, /closeMermaidZoom/)
    assert.match(aiPanel, /onMermaidZoomWheel/)
    assert.match(aiPanel, /Scroll to zoom/)
    assert.match(aiPanel, /darkMode: \{ type: Boolean, default: true \}/)
    assert.match(aiPanel, /formatAiMessageHtml\(role, text, \{ dark: props\.darkMode !== false \}\)/)
    assert.match(aiPanel, /background: var\(--panel-bg/)
    assert.match(app, /:dark-mode="timelineOptions\.darkMode"/)
  })

    it('styles prompt and reply as separate bubbles', () => {
    assert.match(aiPanel, /class="ai-msg"/)
    assert.match(aiPanel, /:class="m\.role"/)
    assert.match(aiPanel, /\.ai-msg\.user \.ai-msg-body/)
    assert.match(aiPanel, /\.ai-msg\.assistant \.ai-msg-body/)
    assert.match(aiPanel, /--ai-user-bg, #1e3348/)
    assert.match(aiPanel, /--ai-asst-bg, #1a2620/)
    assert.match(aiPanel, /#6ea8e0/)
    assert.match(aiPanel, /#6fbf9a/)
    assert.match(aiPanel, /\.ai-msg \+ \.ai-msg/)
  })
})

describe('Migration inspector Investigate with AI', () => {
  it('footer emits query-ai and App wires the migrations template', () => {
    assert.match(corridorDlg, /Investigate with AI/)
    assert.match(corridorDlg, /queryAi\('path'\)/)
    assert.match(app, /@query-ai="queryCorridorWithAi"/)
    assert.match(app, /template: 'migrations'/)
  })
})

describe('Trace Compare Query with AI', () => {
  it('footer emits query-ai and App runs the compare template', () => {
    assert.match(compareDlg, /Query with AI/)
    assert.match(compareDlg, /emit\('query-ai'/)
    assert.match(app, /@query-ai="queryCompareWithAi"/)
    assert.match(compareDlg, /emit\('compared'/)
    assert.match(compareDlg, /scopeToCursors: !!scopeToCursors\.value/)
    assert.match(app, /@compared="onTraceCompared"/)
    assert.match(app, /function compareAiPerformance\(tabARef, tabBRef, \{ scopeToCursors = true \} = \{\}\)/)
    assert.match(app, /askCompare\?\.\(idA, idB\)/)
    assert.match(aiPanel, /async function askCompare/)
  })

  it('footer emits validate-experiment and App asks validate_experiment', () => {
    assert.match(compareDlg, /Validate experiment/)
    assert.match(compareDlg, /emit\('validate-experiment'/)
    assert.match(app, /@validate-experiment="queryValidateExperimentWithAi"/)
    assert.match(app, /askValidateExperiment\?\.\(idA, idB\)/)
    assert.match(aiPanel, /async function askValidateExperiment/)
    assert.match(aiPanel, /VALIDATE_EXPERIMENT_PROMPT/)
  })
})

describe('Statistics distribution Query with AI', () => {
  it('plot and explorer buttons are grayed when AI is off', () => {
    assert.match(statsPanel, /Query with AI…/)
    assert.match(statsPanel, /queryDistributionWithAi\('plot'\)/)
    assert.match(statsPanel, /queryDistributionWithAi\('explorer'\)/)
    assert.match(statsPanel, /:disabled="!aiFeatureEnabled"/)
    assert.match(statsPanel, /:disabled="!aiFeatureEnabled \|\| !distribMk"/)
    assert.match(statsPanel, /Enable AI Assistant in Settings → AI/)
    assert.match(app, /@query-ai="queryAnalysisWithAi"/)
  })

  it('keeps explorer Metric/Task and actions on separate rows (desktop lockstep)', () => {
    const start = statsPanel.indexOf('Distribution Explorer{{ scopeSuffixStr }}')
    assert.ok(start >= 0)
    const chunk = statsPanel.slice(start, start + 1200)
    assert.match(chunk, /class="distrib-selectors"/)
    assert.match(chunk, /class="distrib-actions"/)
    const selectors = chunk.indexOf('class="distrib-selectors"')
    const actions = chunk.indexOf('class="distrib-actions"')
    assert.ok(selectors >= 0 && actions > selectors)
    assert.match(chunk, /Open histogram/)
    assert.match(chunk, /Query with AI…/)
    assert.match(chunk, /class="stats-tool-btn"/)
    assert.match(statsPanel, /\.distrib-toolbar \{[\s\S]*?flex-direction:\s*column/)
    assert.match(statsPanel, /\.distrib-actions \{[\s\S]*?flex-wrap:\s*nowrap/)
  })
})

describe('Statistics timeline anomalies Investigate', () => {
  it('matches desktop: always shown, AI-gated, theme-aware tool button', () => {
    const start = statsPanel.indexOf('Timeline Anomalies{{ scopeSuffixStr }}')
    assert.ok(start >= 0)
    const chunk = statsPanel.slice(start, start + 900)
    assert.match(chunk, /Investigate…/)
    assert.match(chunk, /class="stats-tool-btn"/)
    assert.match(chunk, /:disabled="!aiFeatureEnabled \|\| !anomalyRows\.length"/)
    assert.match(chunk, /Enable AI Assistant in Settings → AI/)
    assert.doesNotMatch(chunk, /compare-mig-btn/)
    assert.match(statsPanel, /\.stats-tool-btn \{[\s\S]*?color:\s*var\(--fg\)/)
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
