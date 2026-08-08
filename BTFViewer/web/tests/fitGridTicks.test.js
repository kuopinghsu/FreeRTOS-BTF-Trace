import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import { createMockCanvas } from './mockCanvas.js'
import { render, RULER_H } from '../src/renderer/TimelineRenderer.js'

function miniTrace() {
  return {
    timeScale: 'ns',
    timeMin: 0,
    timeMax: 10_000_000,
    tasks: [],
    taskRepr: new Map(),
    segments: [],
    segByMergeKey: new Map(),
    segStartByMergeKey: new Map(),
    tickStiTimes: [1_000_000, 2_000_000, 3_000_000],
    stiChannels: [],
    intervalChannels: [],
  }
}

const viewport = {
  timeStart: 0,
  timeEnd: 10_000_000,
  scrollY: 0,
  canvasW: 900,
  canvasH: 400,
}

function gridLines(log) {
  return log.lines.filter((l, i) => (
    l.op === 'moveTo' && l.y === RULER_H && log.lines[i + 1]?.op === 'lineTo'
      && log.lines[i + 1].y === viewport.canvasH
  ))
}

function majorTicks(log) {
  return log.lines.filter((l, i) => (
    l.op === 'moveTo' && l.y === RULER_H - 10 && log.lines[i + 1]?.op === 'lineTo'
      && log.lines[i + 1].y === RULER_H
  ))
}

function tickMarkers(log) {
  return log.fillRects.filter(r => r.y === RULER_H - 10 && r.h === 8 && r.w === 2)
}

describe('fit-to-window grid and TICK marks', () => {
  it('draws grid, ruler ticks, and TICK markers at coarse idle fit', () => {
    const { ctx, log } = createMockCanvas()
    render(ctx, miniTrace(), viewport, {
      showGrid: true,
      showSti: false,
      darkMode: true,
      fastPaint: false,
      coarseLod: true,
    })
    assert.ok(gridLines(log).length >= 4, 'time grid lines at idle fit')
    assert.ok(majorTicks(log).length >= 4, 'ruler major ticks at idle fit')
    assert.equal(tickMarkers(log).length, 3, 'STI TICK markers at idle fit')
  })

  it('skips grid and TICK markers only while fast-painting', () => {
    const { ctx, log } = createMockCanvas()
    render(ctx, miniTrace(), viewport, {
      showGrid: true,
      showSti: false,
      darkMode: true,
      fastPaint: true,
      coarseLod: true,
    })
    assert.equal(gridLines(log).length, 0)
    assert.equal(tickMarkers(log).length, 0)
    assert.ok(majorTicks(log).length >= 4, 'major ticks remain during fast paint')
  })
})
