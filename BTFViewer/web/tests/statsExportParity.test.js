import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { describe, it } from 'node:test'

const stats = readFileSync(new URL('../src/components/StatisticsPanel.vue', import.meta.url), 'utf8')

describe('mutex/queue export parity with desktop', () => {
  it('exports HTML only (CSV is per-table inside the HTML report)', () => {
    assert.match(stats, /Export HTML/)
    assert.match(stats, /@click="exportHtml"/)
    assert.doesNotMatch(stats, /Export CSV/)
    assert.doesNotMatch(stats, /function exportCsv\b/)
  })

  it('HTML mutex and queue summaries include a Bounces column', () => {
    assert.match(stats, /<th>Bounces<\/th><th>Avg hold<\/th><th>Status<\/th>/)
    assert.match(stats, /<th>Issues<\/th><th>Bounces<\/th><th>Avg hold<\/th><th>Status<\/th>/)
    assert.match(stats, /row\.bounceCount/)
  })

  it('scroll tail stays 0 at rest unless pin-scroll (desktop lockstep)', () => {
    assert.match(stats, /let scrollTailPinActive = false/)
    assert.match(stats, /function updateScrollTailHeight\(forPin = false\)/)
    assert.match(stats, /updateScrollTailHeight\(true\)/)
    assert.match(stats, /clearScrollTailPin\(\)/)
    assert.doesNotMatch(
      stats,
      /await nextTick\(\)\s*\n\s*updateScrollTailHeight\(\)\s*\n\s*await scrollDemoSectionIntoView/,
    )
  })
})
