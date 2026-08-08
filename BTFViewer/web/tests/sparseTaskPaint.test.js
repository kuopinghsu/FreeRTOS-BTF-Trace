import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import { createMockCanvas } from './mockCanvas.js'
import { render, RULER_H } from '../src/renderer/TimelineRenderer.js'
import { taskMergeKey } from '../src/utils/colors.js'
import { makeLodSummary, LOD_SUMMARY_BINS, LOD_SUMMARY_BINS_ULTRA } from '../src/utils/lod.js'

if (typeof globalThis.Path2D === 'undefined') {
  globalThis.Path2D = class { rect() {} }
}

const RAW = '[*/0019]CS'
const MK = taskMergeKey(RAW)
const TIME_MIN = 1_000_000
const TIME_MAX = 3_420_000
const CANVAS_W = 1200

/** CS[19]-like: 80 short bursts in the first third of the trace. */
function burstSegs() {
  const segs = []
  for (let i = 0; i < 80; i++) {
    const start = TIME_MIN + 4000 + i * 9000
    segs.push({ task: RAW, core: 'Core_0', start, end: start + 40 })
  }
  return segs
}

function denseSegs(n = 6000) {
  const segs = []
  const span = TIME_MAX - TIME_MIN
  for (let i = 0; i < n; i++) {
    const start = TIME_MIN + Math.floor(i * span / n)
    segs.push({ task: '[0/1]Busy', core: 'Core_0', start, end: start + 80 })
  }
  return segs
}

function taskTrace(mk, raw, segs) {
  const timeSpan = TIME_MAX - TIME_MIN
  const lodTpp = timeSpan / LOD_SUMMARY_BINS
  const ultraTpp = timeSpan / LOD_SUMMARY_BINS_ULTRA
  const [lod, lodStarts] = makeLodSummary(segs, LOD_SUMMARY_BINS, lodTpp, TIME_MIN)
  const [ultra, ultraStarts] = makeLodSummary(lod, LOD_SUMMARY_BINS_ULTRA, ultraTpp, TIME_MIN)
  const starts = segs.map(s => s.start)
  return {
    timeScale: 'us',
    timeMin: TIME_MIN,
    timeMax: TIME_MAX,
    tasks: [mk],
    taskRepr: new Map([[mk, raw]]),
    segments: segs,
    segByMergeKey: new Map([[mk, segs]]),
    segStartByMergeKey: new Map([[mk, starts]]),
    segLodByMergeKey: new Map([[mk, lod]]),
    segLodStartsByMergeKey: new Map([[mk, lodStarts]]),
    segLodUltraByMergeKey: new Map([[mk, ultra]]),
    segLodUltraStartsByMergeKey: new Map([[mk, ultraStarts]]),
    lodTimescalePerPx: lodTpp,
    lodUltraTimescalePerPx: ultraTpp,
    tickStiTimes: [],
    stiChannels: [],
    intervalChannels: [],
    coreNames: ['Core_0'],
  }
}

function paint(trace, timeStart, timeEnd, extra = {}) {
  const gpuBatch = { rects: [], addRect(...a) { this.rects.push(a) } }
  const gpuStripes = { rects: [], addRect() {} }
  const { ctx } = createMockCanvas()
  render(ctx, trace, {
    timeStart,
    timeEnd,
    scrollY: 0,
    canvasW: CANVAS_W,
    canvasH: 400,
  }, {
    showGrid: false,
    showSti: false,
    darkMode: true,
    fastPaint: false,
    coarseLod: true,
    gpuBatch,
    gpuStripes,
    ...extra,
  })
  const segs = gpuBatch.rects.filter(r => r[1] >= RULER_H && r[3] < 30)
  return segs
}

function coveragePx(rects) {
  return rects.reduce((sum, r) => sum + Math.max(0, r[2]), 0)
}

describe('sparse task paint at fit / moderate zoom', () => {
  it('shows CS-style short bursts as a visible bar after Fit', () => {
    const segs = burstSegs()
    const trace = taskTrace(MK, RAW, segs)
    const rects = paint(trace, TIME_MIN, TIME_MAX)
    assert.ok(rects.length >= 1, 'at least one task bar')
    const clusterStart = segs[0].start
    const clusterEnd = segs[segs.length - 1].end
    const px0 = ((clusterStart - TIME_MIN) / (TIME_MAX - TIME_MIN)) * CANVAS_W
    const px1 = ((clusterEnd - TIME_MIN) / (TIME_MAX - TIME_MIN)) * CANVAS_W
    const cover = coveragePx(rects)
    assert.ok(cover >= (px1 - px0) * 0.7, `coverage ${cover} vs cluster ${px1 - px0}`)
    const leftmost = Math.min(...rects.map(r => r[0]))
    assert.ok(leftmost <= px0 + 4, 'bar starts near first burst')
  })

  it('keeps burst activity after a moderate zoom (between lod and ultra tpp)', () => {
    const segs = burstSegs()
    const trace = taskTrace(MK, RAW, segs)
    const mid = TIME_MIN + (TIME_MAX - TIME_MIN) * 0.22
    const half = (TIME_MAX - TIME_MIN) / 6
    const rects = paint(trace, mid - half, mid + half, { coarseLod: false })
    assert.ok(rects.length >= 1, 'bursts remain after zoom-in')
    assert.ok(coveragePx(rects) >= 20, 'zoomed bursts are wider than 1px dust')
    assert.ok(rects.every(r => r[2] >= 2), 'WebGL hairlines stay at least 2px wide')
  })

  it('does not collapse a dense row to ultra-only coverage at mid zoom', () => {
    const raw = '[0/1]Busy'
    const mk = taskMergeKey(raw)
    const segs = denseSegs(6000)
    const trace = taskTrace(mk, raw, segs)
    const nsPerPx = (trace.lodTimescalePerPx + trace.lodUltraTimescalePerPx) / 2
    const span = nsPerPx * CANVAS_W
    const lo = TIME_MIN
    const hi = lo + span
    const rects = paint(trace, lo, hi, { coarseLod: false })
    assert.ok(rects.length >= 1)
    assert.ok(
      coveragePx(rects) >= CANVAS_W * 0.45,
      `mid-zoom dense coverage ${coveragePx(rects)} / ${CANVAS_W}`,
    )
  })
})
