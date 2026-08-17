import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { describe, it } from 'node:test'

import { selectedTaskFromHighlight } from '../src/utils/highlightLock.js'
import { taskMergeKey } from '../src/utils/colors.js'

describe('selectedTaskFromHighlight', () => {
  it('uses pinned legend/name lock when there is no segment', () => {
    assert.equal(
      selectedTaskFromHighlight({ pinnedHighlightKey: 'T1', highlightSegment: null }),
      'T1',
    )
  })

  it('prefers segment-click lock so CPU Load and timeline dimming stay in sync', () => {
    const seg = { task: 'CS[18]', start: 100, end: 200, core: 'Core_0' }
    const key = selectedTaskFromHighlight({
      pinnedHighlightKey: null,
      highlightSegment: seg,
    })
    assert.equal(key, taskMergeKey('CS[18]'))
    assert.ok(key)
  })

  it('returns null when nothing is locked', () => {
    assert.equal(selectedTaskFromHighlight(null), null)
    assert.equal(selectedTaskFromHighlight({}), null)
    assert.equal(selectedTaskFromHighlight({
      pinnedHighlightKey: '',
      highlightSegment: null,
    }), null)
  })
})

describe('App.vue tab-switch parity', () => {
  const app = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')

  it('restores lock from pin or segment after switching traces', () => {
    assert.match(app, /selectedTaskFromHighlight\(tab\)/)
    assert.match(app, /timelineOptions\.lockedTaskKey = lockKey/)
  })

  it('does not force Statistics when switching trace tabs', () => {
    const start = app.indexOf('watch(activeTabId')
    assert.ok(start >= 0)
    const next = app.indexOf('\nwatch(', start + 10)
    const block = app.slice(start, next > start ? next : start + 1200)
    assert.doesNotMatch(block, /focusStatisticsPanel/)
  })
})

describe('Statistics scope checkbox label', () => {
  it('matches desktop Limit to C1–Cn', () => {
    const src = readFileSync(
      new URL('../src/components/StatisticsPanel.vue', import.meta.url),
      'utf8',
    )
    assert.match(src, /Limit to C1–Cn/)
    assert.doesNotMatch(src, /Limit to cursor range \(C1–Cn\)/)
  })
})

describe('Timeline context menu mark clears', () => {
  it('matches desktop Clear all bookmarks / annotations', () => {
    const vue = readFileSync(
      new URL('../src/components/TimelinePanel.vue', import.meta.url),
      'utf8',
    )
    const app = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')
    assert.match(vue, /Clear all bookmarks/)
    assert.match(vue, /Clear all annotations/)
    assert.match(vue, /Clear all marks/)
    assert.match(vue, /clearBookmarks/)
    assert.match(vue, /clearAnnotations/)
    assert.match(vue, /clearAllMarks/)
    assert.match(vue, /disabled: !hasMarks/)
    const clearIdx = vue.indexOf('Clear all marks')
    const placeIdx = vue.indexOf('Place cursor here')
    assert.ok(clearIdx >= 0 && placeIdx > clearIdx)
    assert.match(app, /@clear-bookmarks="onClearBookmarks"/)
    assert.match(app, /@clear-annotations="onClearAnnotations"/)
    assert.match(app, /@clear-all-marks="onClearAllMarks"/)
  })

  it('stops menu presses from reaching the timeline interaction root', () => {
    const vue = readFileSync(
      new URL('../src/components/TimelinePanel.vue', import.meta.url),
      'utf8',
    )
    const handler = readFileSync(
      new URL('../src/renderer/InteractionHandler.js', import.meta.url),
      'utf8',
    )
    assert.match(vue, /@mousedown\.stop/)
    assert.match(vue, /<Teleport to="body">/)
    assert.match(vue, /position: fixed/)
    assert.match(handler, /\.context-menu/)
    assert.match(handler, /closest\?\.?\(/)
  })

  it('grays Ask AI items when AI is disabled', () => {
    const vue = readFileSync(
      new URL('../src/components/TimelinePanel.vue', import.meta.url),
      'utf8',
    )
    const app = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')
    assert.match(vue, /Ask AI about this event/)
    assert.match(vue, /Explain this region with AI/)
    assert.match(vue, /disabled: !aiFeatureEnabled/)
    assert.match(vue, /if \(!aiFeatureEnabled\.value\) return/)
    assert.match(vue, /\.ctx-item\.disabled/)
    assert.match(app, /:ai-enabled="appSettings.aiEnabled !== false"/)
  })
})

describe('AI panel UI font size', () => {
  it('template buttons follow --ui-font-size', () => {
    const vue = readFileSync(
      new URL('../src/components/AiAssistantPanel.vue', import.meta.url),
      'utf8',
    )
    assert.match(vue, /\.ai-panel\s*\{[^}]*font-size:\s*var\(--ui-font-size\)/s)
    assert.match(vue, /\.ai-tpl-btn,\s*\.ai-btn\s*\{[^}]*font-size:\s*inherit/s)
    assert.doesNotMatch(
      vue,
      /\.ai-tpl-btn,\s*\.ai-btn\s*\{[^}]*font-size:\s*\d+px/s,
    )
  })
})
