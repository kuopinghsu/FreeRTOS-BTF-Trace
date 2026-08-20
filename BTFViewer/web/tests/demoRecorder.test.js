import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import { shouldHideNativeCursor, shouldHideSimulatedCursorOnMove } from '../src/utils/demoPointer.js'
import {
  displayCaptureVideoConstraints,
  displaySurfaceNeedsCursorOverlay,
  pickRecordMimeType,
  videoBitrateForCapture,
} from '../src/utils/demoRecorder.js'

describe('demoRecorder cursor overlay', () => {
  it('paints an overlay for tab capture, not window or monitor', () => {
    assert.equal(displaySurfaceNeedsCursorOverlay('browser'), true)
    assert.equal(displaySurfaceNeedsCursorOverlay(undefined), true)
    assert.equal(displaySurfaceNeedsCursorOverlay(''), true)
    assert.equal(displaySurfaceNeedsCursorOverlay('window'), false)
    assert.equal(displaySurfaceNeedsCursorOverlay('monitor'), false)
  })

  it('does not hide the OS cursor for demo or tab recording', () => {
    assert.equal(shouldHideNativeCursor(['record']), false)
    assert.equal(shouldHideNativeCursor(['demo']), false)
    assert.equal(shouldHideNativeCursor(['demo', 'record']), false)
  })

  it('hides the simulated cursor only on a trusted user move during demo', () => {
    assert.equal(shouldHideSimulatedCursorOnMove({ isTrusted: true }, ['demo']), true)
    assert.equal(shouldHideSimulatedCursorOnMove({ isTrusted: false }, ['demo']), false)
    assert.equal(shouldHideSimulatedCursorOnMove({ isTrusted: true }, ['record']), false)
    assert.equal(shouldHideSimulatedCursorOnMove({ isTrusted: true }, ['demo', 'record']), true)
  })

  it('prefers VP9 over AV1 and VP8 for screen/UI encode', () => {
    const seen = []
    const mime = pickRecordMimeType((t) => { seen.push(t); return t.includes('vp9') && t.includes('opus') })
    assert.equal(mime, 'video/webm;codecs=vp9,opus')
    assert.equal(seen[0], 'video/webm;codecs=vp9,opus')
  })

  it('scales bitrate with pixel count and floors above the old 12 Mbps target', () => {
    assert.equal(videoBitrateForCapture(1920, 1080, 30), 31_104_000)
    assert.ok(videoBitrateForCapture(1280, 720, 30) >= 24_000_000)
    assert.equal(videoBitrateForCapture(3840, 2160, 30), 80_000_000)
  })

  it('requests device-pixel capture without UA downscale', () => {
    const c = displayCaptureVideoConstraints(2, 1600, 900)
    assert.equal(c.width.ideal, 3200)
    assert.equal(c.height.ideal, 1800)
    assert.equal(c.resizeMode, 'none')
    assert.equal(c.frameRate.max, 30)
  })
})
