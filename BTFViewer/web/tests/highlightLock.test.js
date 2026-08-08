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
