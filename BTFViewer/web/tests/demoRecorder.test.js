import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import { displaySurfaceNeedsCursorOverlay } from '../src/utils/demoRecorder.js'

describe('demoRecorder cursor overlay', () => {
  it('paints an overlay for tab capture, not window or monitor', () => {
    assert.equal(displaySurfaceNeedsCursorOverlay('browser'), true)
    assert.equal(displaySurfaceNeedsCursorOverlay(undefined), true)
    assert.equal(displaySurfaceNeedsCursorOverlay(''), true)
    assert.equal(displaySurfaceNeedsCursorOverlay('window'), false)
    assert.equal(displaySurfaceNeedsCursorOverlay('monitor'), false)
  })
})
