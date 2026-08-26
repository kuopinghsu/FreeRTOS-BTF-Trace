import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { describe, it } from 'node:test'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

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
  applyCorridorTopNFilter,
  applyCorridorSort,
  buildCorridorOverview,
  buildCorridorAiContext,
  defaultCorridorTopN,
  filterCorridorsByTopN,
  inspectorAnalysisScope,
  inspectorViewportBanner,
  inspectorViewportIsFull,
  INSPECTOR_FULL_VIEW_RATIO,
  netMigrationBalance,
  CORRIDOR_TREE_COLS,
  corridorTreeCell,
  corridorTreeColDefaults,
  CI_SPLIT_RATIO,
  scaleSplitSizes,
  CHORD_TAPER_DEST_RATIO,
  CHORD_GRAD_SOURCE_STOP,
} from '../src/utils/migrationAnalysis.js'

const webRoot = dirname(fileURLToPath(import.meta.url))
const statsPy = readFileSync(join(webRoot, '../../btf_viewer_pkg/stats.py'), 'utf8')
const ciVue = readFileSync(join(webRoot, '../src/components/CorridorInspectorDialog.vue'), 'utf8')
const appVue = readFileSync(join(webRoot, '../src/App.vue'), 'utf8')
const chordVue = readFileSync(join(webRoot, '../src/components/MiniChordPanel.vue'), 'utf8')
const plotVue = readFileSync(join(webRoot, '../src/components/StatisticsPanel.vue'), 'utf8')
const timelineVue = readFileSync(join(webRoot, '../src/components/TimelinePanel.vue'), 'utf8')

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

describe('filterCorridorsByTopN', () => {
  const rows = [
    { count: 100, label: 'a' }, { count: 50, label: 'b' },
    { count: 20, label: 'c' }, { count: 5, label: 'd' },
  ]
  it('keeps all when n is 0', () => {
    assert.equal(filterCorridorsByTopN(rows, 0).length, 4)
  })
  it('keeps the N busiest paths by count', () => {
    const kept = filterCorridorsByTopN(rows, 2)
    assert.deepEqual(kept.map(r => r.count), [100, 50])
  })
})

describe('defaultCorridorTopN', () => {
  it('returns all paths for small core counts and Top 10 for many cores', () => {
    assert.equal(defaultCorridorTopN(2), 0)
    assert.equal(defaultCorridorTopN(8), 0)
    assert.equal(defaultCorridorTopN(9), 10)
  })
})

describe('corridorTreeCell', () => {
  it('formats Sort by metrics for path, task, and group rows', () => {
    assert.deepEqual(CORRIDOR_TREE_COLS.map((c) => c.key), [
      'label', 'rate', 'count', 'pingpong', 'dwell', 'handoff', 'net', 'share',
    ])
    assert.deepEqual(CORRIDOR_TREE_COLS.map((c) => c.label), [
      'Core path', 'Rate', 'Count', 'Ping',
      'Dwell', 'Handoff', 'Net', 'Share',
    ])
    assert.deepEqual(CI_SPLIT_RATIO, [1, 2, 1])
    assert.equal(corridorTreeColDefaults()[0], 140)
    const sizes = scaleSplitSizes([1, 2, 1], 800, [100, 100, 100])
    assert.equal(sizes.length, 3)
    assert.equal(sizes.reduce((a, b) => a + b, 0), 800)
    assert.ok(sizes[1] > sizes[0])
    assert.equal(sizes[0], sizes[2])
    const row = {
      label: 'c0→c1', count: 12, ratePerS: 3.5,
      pingPongPct: 40, shortDwellShare: 25,
      handoffPct: 15, net: -3,
      primaryTask: { sharePct: 80 },
    }
    assert.equal(corridorTreeCell(row, 'rate'), '3.5/s')
    assert.equal(corridorTreeCell(row, 'pingpong'), '40%')
    assert.equal(corridorTreeCell(row, 'dwell'), '25%')
    assert.equal(corridorTreeCell(row, 'net'), '-3 ▼')
    assert.equal(corridorTreeCell(row, 'share'), '80%')
    assert.equal(corridorTreeCell({ count: 4, sharePct: 50 }, 'share', 'task'), '50%')
    assert.equal(corridorTreeCell({ label: 'from c0', count: 9 }, 'rate', 'group'), '—')
  })
})

describe('inspectorAnalysisScope', () => {
  const fmt = (ns) => `${ns}ns`
  it('defaults to Full Trace and does not use the viewport', () => {
    const full = inspectorAnalysisScope('full', [100, 200], 0, 1000, 'ns', fmt, { timeStart: 10, timeEnd: 20 })
    assert.equal(full.mode, 'full')
    assert.equal(full.lo, null)
    assert.equal(full.label, 'Full Trace')
    assert.match(full.detail, /trace unit: ns/)
  })
  it('follows zoom in auto mode', () => {
    const zoomed = inspectorAnalysisScope('auto', [], 0, 1000, 'ns', fmt, { timeStart: 100, timeEnd: 400 })
    assert.equal(zoomed.mode, 'viewport')
    assert.equal(zoomed.lo, 100)
    assert.equal(zoomed.hi, 400)
    const fit = inspectorAnalysisScope('auto', [], 0, 1000, 'ns', fmt, { timeStart: 0, timeEnd: 1000 })
    assert.equal(fit.mode, 'full')
    assert.equal(fit.lo, null)
    const fitMode = inspectorAnalysisScope('auto', [], 0, 1000, 'ns', fmt, { timeStart: 10, timeEnd: 20, fitMode: true })
    assert.equal(fitMode.mode, 'full')
    const defaulted = inspectorAnalysisScope(null, [], 0, 1000, 'ns', fmt, { timeStart: 100, timeEnd: 200 })
    assert.equal(defaulted.mode, 'viewport')
  })
  it('uses Cursor C1–Cn when two cursors exist', () => {
    const cur = inspectorAnalysisScope('cursor', [100, 200], 0, 1000, 'ns', fmt)
    assert.equal(cur.mode, 'cursor')
    assert.equal(cur.lo, 100)
    assert.equal(cur.hi, 200)
    assert.equal(cur.label, 'Cursor C1–C2')
    assert.equal(cur.canCursor, true)
  })
  it('disables cursor scope with a placement hint', () => {
    const none = inspectorAnalysisScope('cursor', [50], 0, 1000, 'ns', fmt)
    assert.equal(none.mode, 'full')
    assert.equal(none.canCursor, false)
    assert.match(none.cursorDisabledReason, /Place at least two cursors/)
  })
  it('uses the visible timeline window in Viewport mode', () => {
    const vp = inspectorAnalysisScope('viewport', [], 0, 1000, 'ns', fmt, { timeStart: 100, timeEnd: 400 })
    assert.equal(vp.mode, 'viewport')
    assert.equal(vp.label, 'Viewport')
    assert.equal(vp.lo, 100)
    assert.equal(vp.hi, 400)
    assert.equal(vp.scoped, true)
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
    assert.ok(c01.pingPongPct >= 0)
    assert.ok('shortDwellShare' in c01)
    assert.ok(model.hotspot)
    assert.equal(model.hotspot.fromCore, 'Core_0')
    assert.match(model.hotspot.summary, /ping-pong|migrations/)
    const overview = buildCorridorOverview(trace, model, { label: 'Full Trace' })
    assert.match(overview.headline, /Full Trace/)
    assert.equal(overview.migrations, 4)
    assert.ok(overview.hottestPath.includes('Core_0'))
    const extra = buildCorridorAiContext({
      scope: { label: 'Full Trace', unit: 'ns', detail: '0 … 1000' },
      corridor: c01,
      overview,
      inspectorFilters: 'None',
      timeScale: 'ns',
    })
    assert.match(extra, /Analysis scope: Full Trace/)
    assert.match(extra, /Handoff suspects/)
    assert.match(extra, /not a measured cache-line transfer/)
    assert.equal(CHORD_GRAD_SOURCE_STOP, 0.7)
    const half = applyCorridorTopNFilter(model, 1)
    assert.ok(half.corridors.length >= 1)
    assert.ok(half.corridors.length <= model.allCorridors.length)
    const sorted = applyCorridorSort(model, 'rate')
    assert.ok(sorted.corridors[0].count >= sorted.corridors[sorted.corridors.length - 1].count)
    const byCount = applyCorridorSort(model, 'count')
    assert.ok(byCount.corridors[0].count >= byCount.corridors[byCount.corridors.length - 1].count)
    const byCountAsc = applyCorridorSort(model, 'count', false)
    assert.ok(byCountAsc.corridors[0].count <= byCountAsc.corridors[byCountAsc.corridors.length - 1].count)
    const byNet = applyCorridorSort(model, 'net')
    assert.ok((byNet.corridors[0].net || 0) >= (byNet.corridors[byNet.corridors.length - 1].net || 0))
    const byLabel = applyCorridorSort(model, 'label', false)
    const labels = byLabel.corridors.map(c => c.label)
    const sortedLabels = [...labels].sort((a, b) => String(a).localeCompare(String(b)))
    assert.deepEqual(labels, sortedLabels)
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
    const padded = [
      { label: 'c0→c1', fromCore: 'Core_0', toCore: 'Core_1', tasks: [{ label: 'CS[11]', mk: '\x0011\x00CS' }] },
      { label: 'c2→c3', fromCore: 'Core_2', toCore: 'Core_3', tasks: [{ label: 'Idle', mk: 'idle:0' }] },
    ]
    assert.deepEqual(filterCorridorsByTaskQuery(padded, '11').map(c => c.label), ['c0→c1'])
    assert.deepEqual(filterCorridorsByTaskQuery(padded, '0011').map(c => c.label), ['c0→c1'])
    const mixed = [
      {
        label: 'c0→c1', fromCore: 'Core_0', toCore: 'Core_1',
        count: 5, revCount: 0, net: 0, bins: [2, 3], bounceBins: [0, 0],
        tasks: [
          { label: 'CS[28]', mk: '\x0028\x00CS', count: 2, bounces: 0, bins: [2, 0], bounceBins: [0, 0] },
          { label: 'CS[128]', mk: '\x00128\x00CS', count: 3, bounces: 0, bins: [0, 3], bounceBins: [0, 0] },
        ],
      },
      {
        label: 'c2→c3', fromCore: 'Core_2', toCore: 'Core_3',
        count: 1, revCount: 0, net: 0, bins: [1, 0], bounceBins: [0, 0],
        tasks: [
          { label: 'CS[128]', mk: '\x00128\x00CS', count: 1, bounces: 0, bins: [1, 0], bounceBins: [0, 0] },
        ],
      },
    ]
    const only28 = filterCorridorsByTaskQuery(mixed, '28')
    assert.deepEqual(only28.map(c => c.label), ['c0→c1'])
    assert.deepEqual(only28[0].tasks.map(t => t.label), ['CS[28]'])
    assert.equal(only28[0].count, 2)
    assert.deepEqual(only28[0].bins, [2, 0])
    assert.equal(filterCorridorsByTaskQuery(mixed, '128')[0].count, 3)
    assert.deepEqual(filterCorridorsByTaskQuery(mixed, '2'), [])
    const btfRaw = [
      {
        label: 'c0→c1', fromCore: 'Core_0', toCore: 'Core_1',
        count: 1, bins: [1], bounceBins: [0],
        tasks: [{ label: '[0/0028]CS', mk: '[0/0028]CS', count: 1, bins: [1], bounceBins: [0] }],
      },
    ]
    assert.equal(filterCorridorsByTaskQuery(btfRaw, '28').length, 1)
    const stripped = [
      {
        label: 'c0→c1', fromCore: 'Core_0', toCore: 'Core_1',
        count: 1, bins: [1], bounceBins: [0],
        tasks: [{ label: '28CS', mk: '28CS', count: 1, bins: [1], bounceBins: [0] }],
      },
    ]
    assert.equal(filterCorridorsByTaskQuery(stripped, '28').length, 1)
    const fffd = [
      {
        label: 'c0→c1', fromCore: 'Core_0', toCore: 'Core_1',
        count: 1, bins: [1], bounceBins: [0],
        tasks: [{ label: '\uFFFD28\uFFFDCS', mk: '\uFFFD28\uFFFDCS', count: 1, bins: [1], bounceBins: [0] }],
      },
    ]
    assert.equal(filterCorridorsByTaskQuery(fffd, '28').length, 1)
    const rare = buildCorridorInspectorModel(makeTrace([
      ...Array.from({ length: 40 }, (_, i) => (
        { ns: i, fromCore: 'Core_0', toCore: 'Core_1', mergeKey: 'hot', gapNs: 0 }
      )),
      { ns: 100, fromCore: 'Core_1', toCore: 'Core_2', mergeKey: '\x0011\x00CS', gapNs: 0 },
    ]), null, null, { topPct: 25, timeBins: 4 })
    const byId = applyCorridorTaskFilter(rare, '11')
    assert.ok(byId.corridors.some(c => c.fromCore === 'Core_1' && c.toCore === 'Core_2'))
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

describe('inspectorViewportBanner', () => {
  const fmt = (ns) => `${ns}ns`

  it('shows Full view for the whole trace and for Fit mode', () => {
    const full = inspectorViewportBanner(null, null, 0, 1000, 'ns', fmt)
    assert.equal(full.scoped, false)
    assert.equal(full.badge, 'Full view')
    assert.match(full.detail, /0ns … 1000ns/)
    const fitted = inspectorViewportBanner(10, 20, 0, 1000, 'ns', fmt, true)
    assert.equal(fitted.scoped, false)
    assert.equal(fitted.badge, 'Full view')
  })

  it('shows Viewport view when the window is zoomed in', () => {
    const vp = inspectorViewportBanner(100, 200, 0, 1000, 'ns', fmt)
    assert.equal(vp.scoped, true)
    assert.equal(vp.badge, 'Viewport view')
    assert.match(vp.detail, /100ns … 200ns/)
  })

  it('stays lockstep with Desktop stats.py for explicit analysis scope', () => {
    assert.equal(INSPECTOR_FULL_VIEW_RATIO, 0.92)
    assert.match(statsPy, /_INSPECTOR_FULL_VIEW_RATIO = 0\.92/)
    assert.match(timelineVue, /return ratio >= 0\.92/)
    assert.match(statsPy, /"Full Trace"/)
    assert.match(statsPy, /"Viewport"/)
    assert.match(statsPy, /"Cursor C1/)
    assert.match(statsPy, /Investigate with AI/)
    assert.match(statsPy, /Handoff suspects only/)
    assert.match(statsPy, /"Topology"/)
    assert.match(statsPy, /Path info/)
    assert.doesNotMatch(statsPy, /QPushButton\("Activity"\)/)
    assert.match(ciVue, /value: 'auto', label: 'Follow zoom'/)
    assert.match(ciVue, /value: 'viewport', label: 'Viewport'/)
    assert.match(ciVue, /analysisMode = ref\('auto'\)/)
    assert.match(statsPy, /_analysis_mode = "auto"/)
    assert.match(statsPy, /addItem\("Follow zoom", "auto"\)/)
    assert.match(appVue, /function onCorridorJump\(payload\)/)
    assert.match(appVue, /payload\.binLo/)
    assert.match(statsPy, /"binLo": bin_lo/)
    assert.match(statsPy, /"binHi": bin_hi/)
    assert.match(chordVue, /IC\.heatmap/)
    assert.match(chordVue, /IC\.chord/)
    assert.doesNotMatch(chordVue, />Circle</)
    assert.match(statsPy, /_IC_CHORD/)
    assert.match(statsPy, /ciCircleToggle/)
    assert.match(statsPy, /_matrix_pad_t/)
    assert.match(ciVue, /inspectorAnalysisScope\(/)
    assert.match(ciVue, /Analysis Scope/)
    assert.doesNotMatch(ciVue, /ci-scope-hint/)
    assert.doesNotMatch(ciVue, /Place at least two cursors/)
    assert.doesNotMatch(statsPy, /_sync_scope_hint/)
    assert.doesNotMatch(statsPy, /_CI_SCOPE_HINT_MIN_DLG_W/)
    assert.match(statsPy, /class _CiComboBox/)
    assert.match(statsPy, /def _ci_combo_menu_qss/)
    assert.match(statsPy, /def _ci_make_popup_menu/)
    assert.match(statsPy, /_sev_combo = _CiComboBox\(\)/)
    assert.match(statsPy, /_style_inspector_field\(combo\)/)
    assert.match(statsPy, /def showPopup/)
    assert.match(statsPy, /menu\.popup\(/)
    assert.match(statsPy, /_pin_inspector_bounce/)
    assert.match(ciVue, /persistInspectorLayout\(true\)/)
    assert.match(ciVue, /ci-field-dir/)
    assert.match(ciVue, /min-width: 108px/)
    assert.match(statsPy, /_pin_inspector_combo\(self\._dir_combo, 108\)/)
    assert.match(ciVue, /overflow-x: auto/)
    assert.match(statsPy, /_pin_inspector_label/)
    assert.match(statsPy, /ciToolbarScroll/)
    assert.match(statsPy, /_CI_TOOLBAR_H = _CI_FIELD_H \+ 2 \* _CI_TOOLBAR_PAD/)
    assert.match(ciVue, /min-height: 26px/)
    assert.match(ciVue, /padding: 2px 0/)
    assert.match(ciVue, /Investigate with AI/)
    assert.match(ciVue, /Handoff suspects only/)
    assert.match(ciVue, /Filter paths by task name or ID/)
    assert.match(ciVue, /Filter Inspector/)
    assert.match(ciVue, /Investigate this path/)
    assert.ok(ciVue.indexOf('ci-overview') < ciVue.indexOf('ci-toolbar'))
    assert.ok(ciVue.indexOf('ci-toolbar') < ciVue.indexOf('ci-scope-banner'))
    assert.ok(ciVue.indexOf('ci-filter-status') < ciVue.indexOf('ci-workspace'))
    assert.ok(ciVue.indexOf('ci-tree-pane') < ciVue.indexOf('ci-grid-pane'))
    assert.ok(ciVue.indexOf('ci-grid-pane') < ciVue.indexOf('ci-right-pane'))
    assert.match(ciVue, /onHeadClick\(col.key\)/)
    assert.match(ciVue, /toggleTreeSort\(key\)/)
    assert.match(ciVue, /corridorTreeCell/)
    assert.match(statsPy, /_on_tree_header_clicked/)
    assert.match(statsPy, /_TREE_SORT_COLS = tuple\(k for k, _lab in _CORRIDOR_TREE_COLS\)/)
    assert.match(statsPy, /sectionClicked.connect\(self._on_tree_header_clicked\)/)
    assert.match(ciVue, /ci-col-resizer/)
    assert.match(ciVue, /ci-split-handle/)
    assert.match(statsPy, /ResizeMode.Interactive/)
    assert.match(appVue, /\.trace-tab-close,\s*\n\.app-close-x \{/)
    assert.match(ciVue, /flex-wrap: nowrap/)
    assert.match(ciVue, /evidenceLinesText/)
    assert.match(statsPy, /_FlowLayout\(btn_row/)
    assert.match(ciVue, /ci-actions-row/)
    assert.match(ciVue, /ci-card-actions/)
    assert.match(statsPy, /Empty bins: no migrations in that interval/)
    assert.match(ciVue, /Empty bins: no migrations in that interval/)
    assert.doesNotMatch(statsPy, /QPushButton\("Jump To"\)/)
    assert.doesNotMatch(statsPy, /corridorInspectorSidebar/)
    assert.doesNotMatch(statsPy, /hatch: lock bounce/)
    assert.doesNotMatch(statsPy, /double-click to apply as Migration Filter/)
    assert.match(statsPy, /double-click to show events/)
    assert.match(ciVue, /double-click to show events/)
    assert.match(statsPy, /_HEAD_H = 28/)
    assert.match(ciVue, /GRID_HEAD_H = 28/)
    assert.match(statsPy, /def _handle_nav_key/)
    assert.match(ciVue, /onGridKeydown/)
    assert.doesNotMatch(ciVue, /viewportProgrammatic/)
    assert.equal(inspectorViewportIsFull(null, null, 0, 1000), true)
    assert.equal(inspectorViewportIsFull(100, 200, 0, 1000), false)
    assert.equal(inspectorViewportIsFull(100, 200, 0, 1000, true), true)
    assert.equal(inspectorViewportIsFull(0, 921, 0, 1000), true)
    assert.equal(inspectorViewportIsFull(0, 919, 0, 1000), false)
    assert.match(plotVue, /border-left: 4px solid #ff9800/)
    assert.match(ciVue, /border-left: 4px solid #ff9800/)
    assert.match(plotVue, /background: #ff9800/)
    assert.match(ciVue, /background: #ff9800/)
    assert.match(plotVue, /color: #1a1200/)
    assert.match(ciVue, /color: #1a1200/)
    assert.match(plotVue, /color-mix\(in srgb, #ff9800 18%, var\(--panel-bg\)\)/)
    assert.match(ciVue, /color-mix\(in srgb, #ff9800 18%, var\(--panel-bg\)\)/)
    assert.match(ciVue, /onHeaderPointerDown/)
    assert.match(ciVue, /dialogPos/)
    assert.match(ciVue, /ci-overlay-free/)
    assert.match(ciVue, /rgba\(91, 155, 213, 0\.18\)/)
    assert.match(ciVue, /\.ci-jump:hover:not\(:disabled\)/)
    assert.match(ciVue, /\.ci-show-all:hover:not\(:disabled\)/)
    assert.match(ciVue, /\.ci-show-all:disabled/)
    assert.match(ciVue, /\.ci-jump:disabled/)
    assert.match(statsPy, /#ciFilterBar/)
    assert.doesNotMatch(ciVue, /ci-field-sort/)
    assert.match(ciVue, /ci-split-handle/)
    assert.match(ciVue, /grid-template-columns: repeat\(3, minmax\(0, 1fr\)\)/)
    assert.match(ciVue, /const nLab = Math.max\(2, Math.min\(7/)
    assert.match(statsPy, /n_lab = max\(2, min\(7/)
    assert.match(statsPy, /setStretchFactor\(1, 2\)/)
    assert.match(statsPy, /_apply_split_layout/)
    assert.doesNotMatch(ciVue, /ci-overview-concern/)
    assert.match(statsPy, /grid.addWidget\(self\._ov_mig, 0, 2\)/)
    assert.match(statsPy, /self\._ov_headline.setWordWrap\(False\)/)
    assert.doesNotMatch(statsPy, /_ov_concern_detail/)
    assert.match(statsPy, /hover": "#E0E8F0"/)
    assert.match(statsPy, /combo_sel_fg/)
    assert.match(statsPy, /def _apply_ci_chrome/)
    assert.match(ciVue, /plotBottom - 0\.5/)
    assert.match(ciVue, /rgba\(91, 155, 213, 0\.35\)/)
    assert.match(statsPy, /plot_bottom - 0\.01/)
    assert.match(statsPy, /rgba\(91, 155, 213, 0\.22\)/)
    assert.match(statsPy, /def _ci_button_qss/)
    assert.match(statsPy, /def _ci_toolbar_qss/)
    assert.match(statsPy, /QPushButton:hover:!disabled/)
    assert.match(statsPy, /#ciFooter/)
    assert.match(statsPy, /combo_view/)
    assert.match(statsPy, /def _ci_combo_widget_qss/)
    assert.match(statsPy, /QAbstractItemView::item:hover/)
    assert.match(statsPy, /setStretchFactor\(0, 1\)/)
    assert.match(statsPy, /grid.setColumnStretch\(0, 1\)/)
    assert.match(statsPy, /self\._ov_scope.setWordWrap\(False\)/)
    assert.match(statsPy, /#ciOverview \{/)
    assert.match(statsPy, /f" border-radius: 6px; padding: 8px 10px; \}\}"/)
  })
})
