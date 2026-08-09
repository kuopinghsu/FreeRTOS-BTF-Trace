import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  applyCorridorDirectionFilter,
  applyCorridorTaskFilter,
  applyCorridorTopFilter,
  buildChordLayout,
  buildCorridorInspectorModel,
  buildTaperedRibbonPath,
  defaultCorridorTopPct,
  filterCorridorsByTaskQuery,
  filterCorridorsByTopPct,
  netMigrationBalance,
  CHORD_TAPER_DEST_RATIO,
  CHORD_GRAD_SOURCE_STOP,
} from '../src/utils/migrationAnalysis.js'

describe('defaultCorridorTopPct', () => {
  it('returns 100 for small core counts', () => {
    assert.equal(defaultCorridorTopPct(2), 100)
    assert.equal(defaultCorridorTopPct(8), 100)
  })
  it('returns 25 for medium and large core counts', () => {
    assert.equal(defaultCorridorTopPct(9), 25)
    assert.equal(defaultCorridorTopPct(16), 25)
    assert.equal(defaultCorridorTopPct(32), 25)
  })
})

describe('filterCorridorsByTopPct', () => {
  const rows = [
    { count: 100 }, { count: 50 }, { count: 20 }, { count: 5 },
  ]
  it('keeps all when topPct is 100', () => {
    assert.equal(filterCorridorsByTopPct(rows, 100).length, 4)
  })
  it('keeps the top quartile by volume', () => {
    const kept = filterCorridorsByTopPct(rows, 25)
    assert.ok(kept.every(r => r.count >= 100))
    assert.equal(kept.length, 1)
  })
})

describe('netMigrationBalance', () => {
  it('is incoming minus outgoing', () => {
    assert.equal(netMigrationBalance(420, 0), 420)
    assert.equal(netMigrationBalance(0, 180), -180)
    assert.equal(netMigrationBalance(10, 10), 0)
  })
})

describe('buildChordLayout enhancements', () => {
  it('exposes out/in totals and egress/ingress ticks', () => {
    const cores = ['Core_0', 'Core_1']
    const grid = [[0, 10], [2, 0]]
    const layout = buildChordLayout(cores, grid)
    assert.equal(layout.arcs[0].outTotal, 10)
    assert.equal(layout.arcs[0].inTotal, 2)
    assert.ok(layout.egressTickAngle(0, 1) >= layout.arcs[0].startAngle)
    assert.ok(layout.ingressTickAngle(0, 1) >= layout.arcs[0].startAngle)
  })

  it('tapers dest half-width relative to source', () => {
    const cores = ['Core_0', 'Core_1']
    const grid = [[0, 100], [0, 0]]
    const layout = buildChordLayout(cores, grid)
    const { srcHalf, dstHalf } = layout.ribbonHalfWidths(0, 1, 100)
    assert.ok(srcHalf > dstHalf)
    assert.ok(Math.abs(dstHalf / srcHalf - CHORD_TAPER_DEST_RATIO) < 1e-6)
  })
})

describe('buildTaperedRibbonPath', () => {
  it('returns a closed SVG path string', () => {
    const r = buildTaperedRibbonPath(100, 100, 50, 0, Math.PI / 2, 4, 1.6, 0)
    assert.ok(r.d.startsWith('M '))
    assert.ok(r.d.endsWith('Z'))
    assert.ok(r.p1 && r.p2 && r.ctrl)
  })
})

describe('buildCorridorInspectorModel', () => {
  function makeTrace(migrations, cores = ['Core_0', 'Core_1', 'Core_2']) {
    return {
      coreNames: cores,
      timeMin: 0,
      timeMax: 1000,
      timeScale: 'ns',
      migrations,
      hasSyncObjectInstrumentation: false,
      syncObjects: new Map(),
      tasks: [],
      segByMergeKey: new Map(),
    }
  }

  it('returns empty model for null trace', () => {
    const m = buildCorridorInspectorModel(null)
    assert.equal(m.hasData, false)
    assert.deepEqual(m.corridors, [])
  })

  it('aggregates corridors, bins, tasks, and hotspot', () => {
    const trace = makeTrace([
      { ns: 100, fromCore: 'Core_0', toCore: 'Core_1', mergeKey: 't1', gapNs: 10 },
      { ns: 200, fromCore: 'Core_0', toCore: 'Core_1', mergeKey: 't1', gapNs: 20 },
      { ns: 300, fromCore: 'Core_0', toCore: 'Core_1', mergeKey: 't2', gapNs: 5 },
      { ns: 400, fromCore: 'Core_1', toCore: 'Core_0', mergeKey: 't1', gapNs: 8 },
    ])
    // taskLabelForMergeKey falls back when segs missing
    const model = buildCorridorInspectorModel(trace, null, null, { topPct: 100, timeBins: 4 })
    assert.equal(model.hasData, true)
    assert.ok(model.corridors.length >= 1)
    const c01 = model.corridors.find(c => c.fromCore === 'Core_0' && c.toCore === 'Core_1')
    assert.equal(c01.count, 3)
    assert.equal(c01.revCount, 1)
    assert.equal(c01.net, 1 - 3)
    assert.equal(c01.tasks.length, 2)
    assert.equal(c01.primaryTask.mk, 't1')
    assert.ok(model.hotspot)
    assert.equal(model.hotspot.fromCore, 'Core_0')
    assert.equal(CHORD_GRAD_SOURCE_STOP, 0.7)
  })

  it('applies topPct filtering', () => {
    const migs = []
    for (let i = 0; i < 50; i++) {
      migs.push({ ns: i, fromCore: 'Core_0', toCore: 'Core_1', mergeKey: 'a', gapNs: 0 })
    }
    for (let i = 0; i < 5; i++) {
      migs.push({ ns: 100 + i, fromCore: 'Core_1', toCore: 'Core_2', mergeKey: 'b', gapNs: 0 })
    }
    const trace = makeTrace(migs)
    const model = buildCorridorInspectorModel(trace, null, null, { topPct: 25, timeBins: 8 })
    assert.ok(model.corridors.every(c => c.count >= 50))
  })

  it('re-filters with applyCorridorTopFilter without dropping allCorridors', () => {
    const migs = []
    for (let i = 0; i < 50; i++) {
      migs.push({ ns: i, fromCore: 'Core_0', toCore: 'Core_1', mergeKey: 'a', gapNs: 0 })
    }
    for (let i = 0; i < 5; i++) {
      migs.push({ ns: 100 + i, fromCore: 'Core_1', toCore: 'Core_2', mergeKey: 'b', gapNs: 0 })
    }
    const trace = makeTrace(migs)
    const full = buildCorridorInspectorModel(trace, null, null, { topPct: 100, timeBins: 8 })
    const half = applyCorridorTopFilter(full, 50)
    assert.ok(half.corridors.length >= 1)
    assert.ok(half.corridors.length <= full.allCorridors.length)
    assert.equal(full.allCorridors.length, half.allCorridors.length)
  })

  it('applyCorridorDirectionFilter keeps source or dest of the selection', () => {
    const trace = makeTrace([
      { ns: 1, fromCore: 'Core_0', toCore: 'Core_1', mergeKey: 'a', gapNs: 0 },
      { ns: 2, fromCore: 'Core_0', toCore: 'Core_2', mergeKey: 'a', gapNs: 0 },
      { ns: 3, fromCore: 'Core_1', toCore: 'Core_0', mergeKey: 'a', gapNs: 0 },
    ])
    const full = buildCorridorInspectorModel(trace, null, null, { topPct: 100, timeBins: 4 })
    const sel = { fromCore: 'Core_0', toCore: 'Core_1' }
    const egress = applyCorridorDirectionFilter(full, 'egress', sel)
    assert.ok(egress.corridors.every(c => c.fromCore === 'Core_0'))
    assert.ok(egress.corridors.length >= 2)
    const ingress = applyCorridorDirectionFilter(full, 'ingress', sel)
    assert.ok(ingress.corridors.every(c => c.toCore === 'Core_1'))
    assert.equal(applyCorridorDirectionFilter(full, 'all', sel), full)
  })

  it('applyCorridorTaskFilter keeps corridors matching task name or id', () => {
    const trace = makeTrace([
      { ns: 1, fromCore: 'Core_0', toCore: 'Core_1', mergeKey: 'cs:22', gapNs: 0 },
      { ns: 2, fromCore: 'Core_1', toCore: 'Core_0', mergeKey: 'idle:0', gapNs: 0 },
    ])
    const full = buildCorridorInspectorModel(trace, null, null, { topPct: 100, timeBins: 4 })
    const filtered = applyCorridorTaskFilter(full, 'cs:22')
    assert.ok(filtered.corridors.every(c =>
      c.tasks.some(t => t.mk === 'cs:22') || c.fromCore.includes('0')))
    assert.ok(filtered.corridors.length >= 1)
    assert.ok(filtered.corridors.length <= full.corridors.length)
    assert.equal(applyCorridorTaskFilter(full, ''), full)
    const rows = [
      { label: 'c0→c1', fromCore: 'Core_0', toCore: 'Core_1', tasks: [{ label: 'CS[22]', mk: 'cs:22' }] },
      { label: 'c2→c3', fromCore: 'Core_2', toCore: 'Core_3', tasks: [{ label: 'Idle', mk: 'idle:0' }] },
    ]
    assert.deepEqual(filterCorridorsByTaskQuery(rows, 'cs[22]').map(c => c.label), ['c0→c1'])
  })

  it('groups tree by source when there are more than 16 cores', () => {
    const cores = Array.from({ length: 18 }, (_, i) => `Core_${i}`)
    const migrations = [
      { ns: 1, fromCore: 'Core_0', toCore: 'Core_1', mergeKey: 't', gapNs: 0 },
      { ns: 2, fromCore: 'Core_0', toCore: 'Core_2', mergeKey: 't', gapNs: 0 },
      { ns: 3, fromCore: 'Core_1', toCore: 'Core_0', mergeKey: 't', gapNs: 0 },
    ]
    const model = buildCorridorInspectorModel(makeTrace(migrations, cores), null, null, {
      topPct: 100, timeBins: 4,
    })
    assert.equal(model.groupBySource, true)
    assert.ok(model.groups.length >= 2)
    assert.equal(model.groups[0].source, 'Core_0')
    assert.equal(model.groups[0].corridors.length, 2)
  })
})
