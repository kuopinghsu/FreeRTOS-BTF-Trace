import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  CHECK_CAPTURE_TRUNCATION,
  CHECK_CORE_INTERVAL_OVERLAP,
  CHECK_EMPTY_TRACE,
  CHECK_LONG_GAP,
  CHECK_METRIC_PREREQUISITES,
  CHECK_MISSING_TASK_IDENTITY,
  CHECK_SYNC_PAIRING,
  CHECK_TIMESTAMP_SKIPS,
  CHECK_TIMESTAMP_UNITS,
  CHECK_UNKNOWN_CORE,
  CHECK_UNMATCHED_INTERVALS,
  STATUS_CAUTION,
  STATUS_INSUFFICIENT,
  STATUS_PASS,
  buildTraceHealthResult,
  traceHealthStatusLabel,
  traceHealthSummary,
} from '../src/utils/traceHealth.js'
import { collectTraceQualityWarnings } from '../src/utils/traceQuality.js'
import { htmlTraceHealthCard } from '../src/utils/statsHtmlReport.js'

function seg(start, end, core = 'Core_0') {
  return { task: 'T', core, start, end }
}

function makeTrace(over = {}) {
  return {
    segments: [],
    stiEvents: [],
    meta: {},
    timeScale: 'us',
    coreNames: ['Core_0', 'Core_1'],
    taskRepr: new Map(),
    tasks: [],
    tickStiTimes: [10, 20, 30],
    stiChannels: ['mutex', 'interval_start'],
    intervalUnmatchedStarts: 0,
    intervalIds: ['1'],
    syncIssues: [],
    hasSyncObjectInstrumentation: true,
    hasPriorityInstrumentation: true,
    timeMin: 0,
    timeMax: 1000,
    ...over,
  }
}

const ids = (r) => new Set(r.checks.map(c => c.id))
const byId = (r, id) => r.checks.find(c => c.id === id)

describe('buildTraceHealthResult', () => {
  it('treats a missing trace as insufficient', () => {
    const r = buildTraceHealthResult(null)
    assert.equal(r.status, STATUS_INSUFFICIENT)
    assert.deepEqual([...ids(r)], [CHECK_EMPTY_TRACE])
  })

  it('short-circuits on an empty trace', () => {
    const r = buildTraceHealthResult(makeTrace({ segments: [], stiEvents: [] }))
    assert.equal(r.status, STATUS_INSUFFICIENT)
    assert.deepEqual([...ids(r)], [CHECK_EMPTY_TRACE])
  })

  it('passes a clean trace', () => {
    const r = buildTraceHealthResult(makeTrace({
      segments: [seg(0, 10, 'Core_0'), seg(10, 20, 'Core_1')],
    }))
    assert.equal(r.status, STATUS_PASS)
    assert.equal(r.issueCount, 0)
    assert.deepEqual(r.checks, [])
  })

  it('grades core-interval overlap by ratio', () => {
    const segs = []
    for (let i = 0; i < 200; i++) segs.push(seg(i * 10, i * 10 + 10, 'Core_0'))
    segs.push(seg(2, 8, 'Core_0')) // contained, no cascade
    const warn = buildTraceHealthResult(makeTrace({ segments: segs }))
    assert.equal(byId(warn, CHECK_CORE_INTERVAL_OVERLAP).severity, 'warning')
    assert.equal(warn.status, STATUS_CAUTION)

    const bad = buildTraceHealthResult(makeTrace({
      segments: [seg(0, 100, 'Core_0'), seg(10, 110, 'Core_0'),
        seg(20, 120, 'Core_0'), seg(30, 130, 'Core_0')],
    }))
    const chk = byId(bad, CHECK_CORE_INTERVAL_OVERLAP)
    assert.equal(chk.severity, 'error')
    assert.equal(bad.status, STATUS_INSUFFICIENT)
    assert.deepEqual(chk.affectedEntities, ['Core_0'])
    assert.ok(chk.affectedRange)
    assert.ok(chk.evidenceRefs.length)
  })

  it('does not treat touching slices as overlaps', () => {
    const r = buildTraceHealthResult(makeTrace({
      segments: [seg(0, 10, 'Core_0'), seg(10, 20, 'Core_0')],
    }))
    assert.ok(!ids(r).has(CHECK_CORE_INTERVAL_OVERLAP))
  })

  it('flags unknown core identifiers', () => {
    const r = buildTraceHealthResult(makeTrace({
      segments: [seg(0, 10, 'Core_0')],
      coreNames: ['Core_0', 'Core_99', 'weird'],
    }))
    const chk = byId(r, CHECK_UNKNOWN_CORE)
    assert.equal(chk.severity, 'warning')
    assert.ok(chk.affectedEntities.includes('Core_99'))
  })

  it('flags missing task identity from overflow + placeholder', () => {
    const repr = new Map([['a', '[0/0007]'], ['b', 'Runner'], ['c', '']])
    const r = buildTraceHealthResult(makeTrace({
      segments: [seg(0, 10, 'Core_0')],
      meta: { taskTableOverflow: 'true' },
      taskRepr: repr,
    }))
    assert.equal(byId(r, CHECK_MISSING_TASK_IDENTITY).severity, 'warning')
  })

  it('flags unmatched intervals', () => {
    const r = buildTraceHealthResult(makeTrace({
      segments: [seg(0, 10, 'Core_0')], intervalUnmatchedStarts: 4,
    }))
    assert.equal(byId(r, CHECK_UNMATCHED_INTERVALS).severity, 'warning')
  })

  it('carries evidence for sync pairing issues', () => {
    const r = buildTraceHealthResult(makeTrace({
      segments: [seg(0, 10, 'Core_0')],
      syncIssues: [
        { kind: 'ORPHAN_GIVE', time_ns: 1234 },
        { kind: 'UNMATCHED_TAKE', time_ns: 5678 },
      ],
    }), null, null, ns => `${ns} u`)
    const chk = byId(r, CHECK_SYNC_PAIRING)
    assert.equal(chk.severity, 'warning')
    assert.ok(chk.evidenceRefs.includes('ORPHAN_GIVE @ 1234 u'))
  })

  it('folds capture-truncation metadata warnings', () => {
    const r = buildTraceHealthResult(makeTrace({
      segments: [seg(0, 10, 'Core_0')],
      meta: { ringOverflow: 'true', truncated: 'true' },
    }))
    const chk = byId(r, CHECK_CAPTURE_TRUNCATION)
    assert.equal(chk.severity, 'warning')
    assert.match(chk.summary, /ring buffer overflow/)
  })

  it('uses the shared trace-quality normalization', () => {
    for (const value of [1, 'yes']) {
      const trace = makeTrace({
        segments: [seg(0, 10, 'Core_0')],
        meta: { ringOverflow: value },
      })
      const warnings = collectTraceQualityWarnings(trace)
      const chk = byId(buildTraceHealthResult(trace), CHECK_CAPTURE_TRUNCATION)
      assert.equal(warnings.length, 1)
      assert.equal(chk.summary, warnings[0])
    }
  })

  it('treats an unknown timestamp unit as an error', () => {
    const r = buildTraceHealthResult(makeTrace({
      segments: [seg(0, 10, 'Core_0')], timeScale: 'furlongs',
    }))
    assert.equal(byId(r, CHECK_TIMESTAMP_UNITS).severity, 'error')
    assert.equal(r.status, STATUS_INSUFFICIENT)
  })

  it('reads dropped-line counts from meta / skippedLines', () => {
    for (const t of [
      makeTrace({ segments: [seg(0, 10, 'Core_0')], meta: { _skipped_lines: '7' } }),
      makeTrace({ segments: [seg(0, 10, 'Core_0')], skippedLines: 7 }),
    ]) {
      const r = buildTraceHealthResult(t)
      assert.equal(byId(r, CHECK_TIMESTAMP_SKIPS).severity, 'warning')
    }
  })

  it('reports a long data gap as info with a range', () => {
    const r = buildTraceHealthResult(makeTrace({
      segments: [seg(0, 10, 'Core_0'), seg(900, 1000, 'Core_0')],
      timeMin: 0, timeMax: 1000,
    }))
    const chk = byId(r, CHECK_LONG_GAP)
    assert.equal(chk.severity, 'info')
    assert.deepEqual(chk.affectedRange, { start: 10, end: 900 })
    assert.equal(r.status, STATUS_PASS)
  })

  it('lists missing event types under metric prerequisites', () => {
    const r = buildTraceHealthResult(makeTrace({
      segments: [seg(0, 10, 'Core_0')],
      tickStiTimes: [],
      stiChannels: [],
      intervalIds: [],
      hasSyncObjectInstrumentation: false,
      hasPriorityInstrumentation: false,
    }))
    const chk = byId(r, CHECK_METRIC_PREREQUISITES)
    assert.equal(chk.severity, 'info')
    assert.match(chk.summary, /no TICK events/)
    assert.ok(chk.metricLimitations.includes('Trace Health (TICK)'))
  })

  it('respects the scope window', () => {
    const segs = [seg(0, 100, 'Core_0'), seg(50, 150, 'Core_0')]
    assert.ok(ids(buildTraceHealthResult(makeTrace({ segments: segs })))
      .has(CHECK_CORE_INTERVAL_OVERLAP))
    assert.ok(!ids(buildTraceHealthResult(makeTrace({ segments: segs }), 0, 40))
      .has(CHECK_CORE_INTERVAL_OVERLAP))
  })

  it('is deterministic', () => {
    const t = makeTrace({
      segments: [seg(0, 100, 'Core_0'), seg(10, 110, 'Core_0')],
      syncIssues: [{ kind: 'X', time_ns: 1 }],
      meta: { truncated: 'true' },
    })
    assert.deepEqual(buildTraceHealthResult(t), buildTraceHealthResult(t))
  })

  it('sorts checks by severity, errors first', () => {
    const r = buildTraceHealthResult(makeTrace({
      segments: [seg(0, 100, 'Core_0'), seg(10, 110, 'Core_0'), seg(20, 120, 'Core_0')],
      syncIssues: [{ kind: 'X', time_ns: 1 }],
    }))
    const rank = { error: 2, warning: 1, info: 0 }
    const seq = r.checks.map(c => rank[c.severity])
    assert.deepEqual(seq, [...seq].sort((a, b) => b - a))
  })
})

describe('labels + summary', () => {
  it('maps status tokens to labels', () => {
    assert.equal(traceHealthStatusLabel(STATUS_PASS), 'Pass')
    assert.equal(traceHealthStatusLabel(STATUS_CAUTION), 'Caution')
    assert.equal(traceHealthStatusLabel(STATUS_INSUFFICIENT), 'Insufficient data')
  })

  it('summarises with an issue count', () => {
    const clean = buildTraceHealthResult(makeTrace({ segments: [seg(0, 10, 'Core_0')] }))
    assert.equal(traceHealthSummary(clean), 'Trace health: Pass')
    const noisy = buildTraceHealthResult(makeTrace({
      segments: [seg(0, 10, 'Core_0')], meta: { truncated: 'true' },
    }))
    assert.match(traceHealthSummary(noisy), /Caution/)
    assert.match(traceHealthSummary(noisy), /issue\(s\)/)
  })
})

describe('htmlTraceHealthCard', () => {
  it('renders status, checks and limited-metric roll-up', () => {
    const r = buildTraceHealthResult(makeTrace({
      segments: [seg(0, 100, 'Core_0'), seg(10, 110, 'Core_0')],
      meta: { truncated: 'true' },
    }), null, null, ns => `${ns}us`)
    const html = htmlTraceHealthCard(r, { formatNs: ns => `${ns}us`, scopeTitle: ' (C1–C2)' })
    assert.match(html, /<h2>Trace Health Check \(C1–C2\)<\/h2>/)
    assert.match(html, /Status: Insufficient data/)
    assert.match(html, /Trace Health \(TICK\)/)
    assert.match(html, /Limited metrics/)
    assert.match(html, /<details/)
    assert.equal((html.match(/<section/g) || []).length, 1)
    assert.equal((html.match(/<\/section>/g) || []).length, 1)
  })

  it('returns empty string for a missing result', () => {
    assert.equal(htmlTraceHealthCard(null), '')
  })

  it('shows the clean-state message when there are no checks', () => {
    const r = buildTraceHealthResult(makeTrace({
      segments: [seg(0, 10, 'Core_0'), seg(10, 20, 'Core_1')],
    }))
    assert.deepEqual(r.checks, [])
    const html = htmlTraceHealthCard(r)
    assert.match(html, /Status: Pass/)
    assert.match(html, /No structural inconsistencies/)
  })
})
