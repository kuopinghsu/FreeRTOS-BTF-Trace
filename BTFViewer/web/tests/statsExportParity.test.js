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

  it('HTML mutex and queue summaries include Bounces + Bounce % columns', () => {
    assert.match(stats, /<th>Bounces<\/th><th>Bounce %<\/th><th>Avg hold<\/th><th>Status<\/th>/)
    assert.match(stats, /<th>Issues<\/th><th>Bounces<\/th><th>Bounce %<\/th><th>Avg hold<\/th><th>Status<\/th>/)
    assert.match(stats, /row\.bounceCount/)
    assert.match(stats, /syncBouncePctCell/)
  })

  it('Export HTML offers an Anonymize toggle (desktop `report --anonymize` parity)', () => {
    assert.match(stats, /const exportAnon = ref\(/)
    assert.match(stats, /aiRedactTaskNames/)
    assert.match(stats, /function buildExportAnonymizer\(/)
    assert.match(stats, /Task-\$\{i \+ 1\}/)
    assert.match(stats, /_exportAnonFn = buildExportAnonymizer\(tr, exportAnon\.value\)/)
    assert.match(stats, /class="stats-export-anon"/)
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
