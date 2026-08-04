import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  TICKLESS_CV_THRESHOLD,
  analyzeTickHealth,
  tickHealthReport,
} from '../src/utils/tickHealth.js'
import {
  buildSummaryCompareRows,
  traceSummarySnapshot,
} from '../src/utils/traceCompare.js'
import { buildMigrationIndex } from '../src/utils/migrationAnalysis.js'

function makeSeg(task, core, start, end) {
  return { task, core, start, end }
}

function makeTrace({ timeMax = 10000, segments = [], tickStiTimes = [] } = {}) {
  const tasks = []
  const taskRepr = new Map()
  const segByMergeKey = new Map()
  const coreSegs = new Map()
  const coreNames = []

  for (const s of segments) {
    const mk = s.task
    if (!segByMergeKey.has(mk)) {
      segByMergeKey.set(mk, [])
      tasks.push(mk)
      taskRepr.set(mk, mk)
    }
    segByMergeKey.get(mk).push(s)
    if (!coreSegs.has(s.core)) {
      coreSegs.set(s.core, [])
      coreNames.push(s.core)
    }
    coreSegs.get(s.core).push(s)
  }
  for (const segs of coreSegs.values()) segs.sort((a, b) => a.start - b.start)
  for (const segs of segByMergeKey.values()) segs.sort((a, b) => a.start - b.start)
  const { migrations, migrationsByMk } = buildMigrationIndex(segByMergeKey)

  return {
    timeMin: 0,
    timeMax,
    timeScale: 'us',
    tasks,
    taskRepr,
    segments,
    segByMergeKey,
    coreNames,
    coreSegs,
    stiEvents: [],
    tickStiTimes,
    migrations,
    migrationsByMk,
    hasSyncObjectInstrumentation: false,
  }
}

describe('analyzeTickHealth — tick vs tickless', () => {
  it('classifies regular periods as TICK', () => {
    const times = Array.from({ length: 10 }, (_, i) => i * 1000)
    const report = analyzeTickHealth(times)
    assert.equal(report.tickCount, 10)
    assert.equal(report.isTickless, false)
    assert.ok(report.tickCv <= TICKLESS_CV_THRESHOLD)
    assert.equal(report.health, 'good')
    assert.equal(report.missedTicksEstimate, 0)
  })

  it('classifies multi-tick idle gaps as TICKLESS', () => {
    const times = [0, 1000, 2000, 5000, 6000, 10000, 11000, 12000]
    const report = analyzeTickHealth(times)
    assert.equal(report.isTickless, true)
    assert.ok(report.tickCv > TICKLESS_CV_THRESHOLD)
    assert.equal(report.health, 'warning')
    assert.ok(report.missedTicksEstimate > 0)
    assert.ok(report.maxGap > 2000)
  })

  it('returns unknown / not tickless for empty input', () => {
    const report = analyzeTickHealth([])
    assert.equal(report.tickCount, 0)
    assert.equal(report.health, 'unknown')
    assert.equal(report.isTickless, false)
  })

  it('busy-window scope can look tickful on a tickless trace', () => {
    const times = [0, 1000, 2000, 8000, 9000, 10000, 11000, 12000]
    const full = analyzeTickHealth(times)
    assert.equal(full.isTickless, true)
    const busy = tickHealthReport({ tickStiTimes: times }, 8000, 12000)
    assert.equal(busy.isTickless, false)
    assert.equal(busy.tickCount, 5)
    assert.equal(busy.missedTicksEstimate, 0)
  })
})

describe('Trace Compare — tickless vs tickful', () => {
  it('reports Tick mode and context-switch delta', () => {
    const tickless = makeTrace({
      timeMax: 10000,
      segments: [makeSeg('Worker[1]', 'Core_0', 0, 10000)],
      tickStiTimes: [0, 1000, 5000, 6000, 10000],
    })
    const tickful = makeTrace({
      timeMax: 10000,
      segments: [
        makeSeg('Worker[1]', 'Core_0', 0, 4000),
        makeSeg('Helper[2]', 'Core_0', 4000, 5000),
        makeSeg('Worker[1]', 'Core_0', 5000, 9000),
      ],
      tickStiTimes: Array.from({ length: 10 }, (_, i) => i * 1000),
    })

    const snapA = traceSummarySnapshot(tickless)
    const snapB = traceSummarySnapshot(tickful)
    assert.equal(snapA.tickMode, 'TICKLESS')
    assert.equal(snapB.tickMode, 'TICK')
    assert.ok(snapA.tickCount < snapB.tickCount)
    assert.ok(snapA.contextSwitches < snapB.contextSwitches)

    const rows = buildSummaryCompareRows(tickless, tickful)
    const mode = rows.find(r => r.label === 'Tick mode')
    assert.equal(mode.a, 'TICKLESS')
    assert.equal(mode.b, 'TICK')
    const ctx = rows.find(r => r.label === 'Context switches')
    assert.ok(ctx.a < ctx.b)
  })
})
