import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { describe, it } from 'node:test'

// There is no DOM test stack here, so guard the template invariant directly:
// the AI page must be hidden rather than unmounted, or the conversation is
// thrown away every time the user visits another right-panel tab.
const app = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')
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
