import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import { createMockCanvas } from './mockCanvas.js'
import {
  RULER_W,
  drawCursors,
  drawCursorsVertical,
  drawHoverLineVertical,
  findNearestCursorIndex,
} from '../src/renderer/TimelineRenderer.js'

const trace = { timeScale: 'ns', timeMin: 0, timeMax: 1_000_000 }

describe('timeline overlay draws', () => {
  it('drawHoverLineVertical places label in ruler column (parity with desktop)', () => {
    const { ctx, log } = createMockCanvas(72)
    const headerH = 160
    const canvasW = 800
    const canvasH = 600
    const t = 200
    const pxPerNs = 1

    drawHoverLineVertical(ctx, t, trace, 0, pxPerNs, canvasW, canvasH, headerH, false)

    const hoverLine = log.lines.find(l => l.op === 'moveTo' && l.x === RULER_W)
    assert.ok(hoverLine, 'hover line starts at RULER_W')

    const expectedTw = 72 + 8
    const labelRect = log.fillRects.find(r => r.x === RULER_W - 2 - expectedTw)
    assert.ok(labelRect, 'time label badge is right-aligned in ruler column')
    assert.ok(log.save >= 1 && log.restore >= 1, 'canvas state is isolated with save/restore')
  })

  it('drawCursorsVertical aligns Δ badge to later cursor row', () => {
    const { ctx, log } = createMockCanvas(60)
    const headerH = 160
    const canvasW = 800
    const canvasH = 600
    const cursors = [100, 200]
    const pxPerNs = 1

    drawCursorsVertical(ctx, cursors, trace, 0, pxPerNs, canvasW, canvasH, headerH, false)

    const deltaRects = log.fillRects.filter(r => r.x === RULER_W + 4)
    assert.equal(deltaRects.length, 1, 'one vertical Δ badge')
    const laterCursorY = headerH + 200
    const expectedTy = Math.min(laterCursorY + 2, canvasH - 14 - 2)
    assert.equal(deltaRects[0].y, expectedTy)
  })

  it('drawCursors gives the Δ badge its own row, never the later cursor\'s row', () => {
    // Regression: the Δ badge used to share a row with the later cursor's
    // own badge, positioned at their midpoint. When the two cursors are
    // close together on screen, that midpoint lands on top of the cursor's
    // own badge and both become unreadable. The Δ badge must always get a
    // dedicated row below every cursor badge instead.
    const { ctx, log } = createMockCanvas(60)
    const canvasW = 900
    const canvasH = 400
    const cursors = [100, 200]
    const pxPerNs = 1

    drawCursors(ctx, cursors, trace, 0, pxPerNs, canvasW, canvasH, false)

    const deltaTexts = log.fillTexts.filter(t => t.text.startsWith('Δ'))
    assert.equal(deltaTexts.length, 1)
    const th = 16
    const laterLabelY = 2 + 2 * (th + 2)
    const deltaRowY = 2 + 3 * (th + 2)
    assert.notEqual(deltaTexts[0].y, laterLabelY + 2)
    assert.equal(deltaTexts[0].y, deltaRowY + 2)
  })

  it('findNearestCursorIndex returns closest cursor within snap window', () => {
    const cursors = [1000, 5000, 9000]
    assert.equal(findNearestCursorIndex(cursors, 4800, 500), 1)
    assert.equal(findNearestCursorIndex(cursors, 4800, 100), -1)
    assert.equal(findNearestCursorIndex(cursors, 1000, 0), 0)
  })
})
