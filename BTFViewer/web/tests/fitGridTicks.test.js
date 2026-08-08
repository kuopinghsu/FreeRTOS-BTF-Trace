import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import { createMockCanvas } from './mockCanvas.js'
import { render, RULER_H } from '../src/renderer/TimelineRenderer.js'
import { ROW_GAP, ROW_HEIGHT } from '../src/config.js'

if (typeof globalThis.Path2D === 'undefined') {
  globalThis.Path2D = class { rect() {} }
}

const mk = 'TaskA'

function miniTrace(taskCount = 0) {
  const tasks = []
  const taskRepr = new Map()
  const empty = new Map()
  for (let i = 0; i < taskCount; i++) {
    const key = i === 0 ? mk : `Task${i}`
    tasks.push(key)
    taskRepr.set(key, key)
    empty.set(key, [])
  }
  return {
    timeScale: 'ns',
    timeMin: 0,
    timeMax: 10_000_000,
    tasks,
    taskRepr,
    segments: [],
    segByMergeKey: new Map(empty),
    segStartByMergeKey: new Map(empty),
    segLodByMergeKey: new Map(empty),
    segLodStartsByMergeKey: new Map(empty),
    segLodUltraByMergeKey: new Map(empty),
    segLodUltraStartsByMergeKey: new Map(empty),
    lodTimescalePerPx: 200,
    lodUltraTimescalePerPx: 2000,
    tickStiTimes: [1_000_000, 2_000_000, 3_000_000],
    stiChannels: [],
    intervalChannels: [],
    wasmHandles: null,
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

function rowBands(log) {
  return log.fillRects.filter(r => (
    r.x === 0 && r.w === viewport.canvasW && r.h === ROW_HEIGHT && r.y >= RULER_H
  ))
}

const idleFit = {
  showGrid: true,
  showSti: false,
  darkMode: true,
  fastPaint: false,
  coarseLod: true,
}

describe('fit-to-window grid and TICK marks', () => {
  it('draws grid, ruler ticks, and TICK markers at coarse idle fit', () => {
    const { ctx, log } = createMockCanvas()
    render(ctx, miniTrace(), viewport, idleFit)
    assert.ok(gridLines(log).length >= 4, 'time grid lines at idle fit')
    assert.ok(majorTicks(log).length >= 4, 'ruler major ticks at idle fit')
    assert.equal(tickMarkers(log).length, 3, 'STI TICK markers at idle fit')
  })

  it('draws interleaved desktop-parity row bands at coarse idle fit', () => {
    const { ctx, log } = createMockCanvas()
    render(ctx, miniTrace(2), viewport, idleFit)
    const bands = rowBands(log)
    assert.equal(bands.length, 2, 'two task row bands')
    assert.equal(bands[0].fillStyle, '#252526')
    assert.equal(bands[1].fillStyle, '#2D2D2D')
    assert.equal(bands[1].y, RULER_H + ROW_HEIGHT + ROW_GAP)
  })

  it('skips grid and TICK markers only while fast-painting', () => {
    const { ctx, log } = createMockCanvas()
    render(ctx, miniTrace(1), viewport, {
      ...idleFit,
      fastPaint: true,
    })
    assert.equal(gridLines(log).length, 0)
    assert.equal(tickMarkers(log).length, 0)
    assert.ok(rowBands(log).length >= 1, 'row bands stay visible during zoom/pan')
    assert.ok(majorTicks(log).length >= 4, 'major ticks remain during fast paint')
  })

  it('keeps WebGL row stripes during fast paint off the segment layer', () => {
    const gpuBatch = { rects: [], addRect(...a) { this.rects.push(a) } }
    const gpuStripes = { rects: [], addRect(...a) { this.rects.push(a) } }
    const { ctx, log } = createMockCanvas()
    render(ctx, miniTrace(2), viewport, {
      ...idleFit, fastPaint: true, gpuBatch, gpuStripes,
    })
    assert.ok(gpuStripes.rects.length >= 2, 'stripes still upload while zooming')
    assert.equal(
      gpuBatch.rects.filter(r => r[4] === '#252526' || r[4] === '#2D2D2D').length,
      0,
    )
    assert.equal(rowBands(log).length, 0)
  })

  it('keeps WebGL row stripes off the segment batcher', () => {
    const gpuBatch = { rects: [], addRect(...a) { this.rects.push(a) } }
    const gpuStripes = { rects: [], addRect(...a) { this.rects.push(a) } }
    const { ctx, log } = createMockCanvas()
    render(ctx, miniTrace(2), viewport, { ...idleFit, gpuBatch, gpuStripes })
    assert.ok(gpuStripes.rects.length >= 2, 'stripe rects on stripe layer')
    assert.ok(gpuStripes.rects.every(r => r[4] === '#252526' || r[4] === '#2D2D2D'))
    assert.equal(
      gpuBatch.rects.filter(r => r[4] === '#252526' || r[4] === '#2D2D2D').length,
      0,
      'opaque stripes must not share the segment layer',
    )
    assert.equal(rowBands(log).length, 0, 'stripes are not painted on the 2D chrome canvas')
  })
})
