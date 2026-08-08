import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import { InteractionHandler } from '../src/renderer/InteractionHandler.js'

function mockEl() {
  return {
    addEventListener() {},
    removeEventListener() {},
    getBoundingClientRect() {
      return { left: 0, top: 0, width: 800, height: 600 }
    },
  }
}

describe('InteractionHandler.cancelPendingViewport', () => {
  it('drops queued wheel zoom so Fit is not overwritten', () => {
    const canvas = mockEl()
    const handler = new InteractionHandler(canvas, {
      getTrace: () => null,
      getViewport: () => ({ timeStart: 0, timeEnd: 1000, canvasW: 800, canvasH: 600 }),
      getOptions: () => ({ orientation: 'h' }),
    })
    handler._vpQueue = [vp => vp]
    handler._vpFlushRaf = 1
    handler.cancelPendingViewport()
    assert.equal(handler._vpQueue, null)
    assert.equal(handler._vpFlushRaf, null)
    handler.destroy()
  })
})
