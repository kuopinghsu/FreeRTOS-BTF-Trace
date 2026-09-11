import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { describe, it } from 'node:test'

// There is no DOM test stack here, so guard the template invariant directly
// (same approach as aiPanelPersistence.test.js).
const legendPanel = readFileSync(
  new URL('../src/components/LegendPanel.vue', import.meta.url), 'utf8',
)

describe('LegendPanel empty state', () => {
  it('shows a message instead of a blank list when the filter matches nothing', () => {
    // Desktop parity: btf_viewer_pkg/stats.py _LegendWidget._filter_tasks()'s
    // "No tasks match the current filter." placeholder row.
    assert.match(legendPanel, /v-if="visibleTasks\.length"/)
    assert.match(legendPanel, /v-else\s+class="legend-empty"/)
    assert.match(legendPanel, /No tasks match the current filter\./)
    assert.match(legendPanel, /\.legend-empty\s*\{/)
  })
})
