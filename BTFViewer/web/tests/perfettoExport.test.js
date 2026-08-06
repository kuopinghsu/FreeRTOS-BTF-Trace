import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  buildPerfettoChromeEvents,
  buildPerfettoChromeTrace,
  normalizeExportRange,
  toTraceUs,
} from '../src/utils/perfettoExport.js'

describe('toTraceUs', () => {
  it('converts us-scale timestamps to Chrome Trace microseconds', () => {
    assert.equal(toTraceUs(1000, 'us'), 1000)
    assert.equal(toTraceUs(1, 'ms'), 1000)
    assert.equal(toTraceUs(1000, 'ns'), 1)
  })
})

describe('normalizeExportRange', () => {
  it('accepts both omitted or both set', () => {
    assert.deepEqual(normalizeExportRange(null, null), { lo: null, hi: null })
    assert.deepEqual(normalizeExportRange(10, 20), { lo: 10, hi: 20 })
  })
  it('rejects half-specified or inverted ranges', () => {
    assert.throws(() => normalizeExportRange(10, null))
    assert.throws(() => normalizeExportRange(20, 10))
  })
})

describe('buildPerfettoChromeTrace', () => {
  const mk = '\x001\x00Worker'

  function miniTrace(overrides = {}) {
    return {
      timeScale: 'us',
      timeMin: 100,
      timeMax: 500,
      meta: { creator: 'test' },
      coreNames: ['Core_0'],
      tasks: [mk],
      taskRepr: new Map([[mk, '[0/1]Worker']]),
      segments: [
        { start: 100, end: 150, task: '[0/1]Worker', core: 'Core_0' },
      ],
      migrations: [
        { ns: 150, mergeKey: mk, fromCore: 'Core_0', toCore: 'Core_1', gapNs: 0 },
      ],
      stiChannels: ['mutex', 'interval_start', 'interval_stop', 'tag0_event'],
      stiEvents: [
        { time: 120, core: 'Core_0', target: 'mutex', event: 'trigger', note: 'take 0xabc' },
        { time: 110, core: 'Core_0', target: 'interval_start', event: 'trigger', note: 'spanA tid:1' },
        { time: 140, core: 'Core_0', target: 'interval_stop', event: 'trigger', note: 'spanA tid:1' },
        { time: 125, core: 'Core_0', target: 'tag0_event', event: 'trigger', note: '42' },
      ],
      tickStiTimes: [200],
      intervalIds: ['spanA'],
      intervalInstances: [
        {
          id: 'spanA', startNs: 110, stopNs: 140,
          startCore: 'Core_0', stopCore: 'Core_0', taskId: '1',
        },
      ],
      tagChannels: ['tag0_event'],
      tagSamplesByChannel: new Map([
        ['tag0_event', [{ channel: 'tag0_event', timeNs: 125, value: 42, core: 'Core_0' }]],
      ]),
      syncObjects: new Map(),
      hasSyncObjectInstrumentation: false,
      ...overrides,
    }
  }

  function syncTrace() {
    return miniTrace({
      hasSyncObjectInstrumentation: true,
      syncObjects: new Map([
        ['mutex:0xabc', {
          key: 'mutex:0xabc',
          kind: 'mutex',
          ptr: '0xabc',
          createNs: 105,
          deleteNs: null,
          holds: [{
            startNs: 120,
            stopNs: 145,
            durationNs: 25,
            holderLabel: 'Worker',
            takeCore: 'Core_0',
            giveCore: 'Core_0',
            signal: false,
          }],
        }],
      ]),
    })
  }

  it('emits process metadata including Tags', () => {
    const events = buildPerfettoChromeEvents(miniTrace())
    const procs = events
      .filter(e => e.name === 'process_name')
      .map(e => e.args.name)
    assert.deepEqual(procs, ['Cores', 'Tasks', 'STI', 'Intervals', 'Tags'])
  })

  it('emits complete slices with µs timestamps', () => {
    const events = buildPerfettoChromeEvents(miniTrace())
    const runs = events.filter(e => e.ph === 'X' && e.name === 'run')
    assert.equal(runs.length, 1)
    assert.equal(runs[0].ts, 100)
    assert.equal(runs[0].dur, 50)
    assert.equal(runs[0].args.core, 'Core_0')
  })

  it('emits STI and migration instants', () => {
    const events = buildPerfettoChromeEvents(miniTrace())
    const instants = events.filter(e => e.ph === 'i')
    assert.ok(instants.some(e => e.name === 'take 0xabc'))
    assert.ok(instants.some(e => e.name === 'migrate'))
    assert.ok(instants.some(e => e.name === 'TICK'))
  })

  it('skips interval_start/stop and tags in STI tracks', () => {
    const events = buildPerfettoChromeEvents(miniTrace())
    const stiThreads = events
      .filter(e => e.name === 'thread_name' && e.pid === 3)
      .map(e => e.args.name)
    assert.ok(!stiThreads.includes('interval_start'))
    assert.ok(!stiThreads.includes('interval_stop'))
    assert.ok(!stiThreads.includes('tag0_event'))
    assert.ok(stiThreads.includes('mutex'))
    assert.ok(stiThreads.includes('TICK'))

    const intervals = events.filter(e => e.ph === 'X' && e.cat === 'interval')
    assert.equal(intervals.length, 1)
    assert.equal(intervals[0].name, 'spanA')
    assert.equal(intervals[0].ts, 110)
    assert.equal(intervals[0].dur, 30)
  })

  it('emits tag counter tracks (ph:C)', () => {
    const events = buildPerfettoChromeEvents(miniTrace())
    const counters = events.filter(e => e.ph === 'C')
    assert.equal(counters.length, 1)
    assert.equal(counters[0].pid, 5)
    assert.equal(counters[0].args.value, 42)
    assert.equal(counters[0].name, 'Tag 0')
  })

  it('emits sync hold slices and filters mutex STI', () => {
    const events = buildPerfettoChromeEvents(syncTrace())
    const procs = events.filter(e => e.name === 'process_name').map(e => e.args.name)
    assert.ok(procs.includes('Sync'))
    const holds = events.filter(e => e.ph === 'X' && e.cat === 'sync')
    assert.equal(holds.length, 1)
    assert.equal(holds[0].pid, 6)
    assert.equal(holds[0].name, 'Worker')
    assert.equal(holds[0].ts, 120)
    assert.equal(holds[0].dur, 25)
    const stiMutex = events.filter(
      e => e.pid === 3 && e.args?.channel === 'mutex',
    )
    assert.equal(stiMutex.length, 0)
  })

  it('clips segments and drops out-of-range STI for lo/hi', () => {
    const events = buildPerfettoChromeEvents(miniTrace(), { lo: 120, hi: 140 })
    const runs = events.filter(e => e.ph === 'X' && e.name === 'run')
    assert.equal(runs.length, 1)
    assert.equal(runs[0].ts, 120)
    assert.equal(runs[0].dur, 20)
    assert.ok(!events.some(e => e.ph === 'i' && e.name === 'TICK'))
    const counters = events.filter(e => e.ph === 'C')
    assert.equal(counters.length, 1)
    assert.equal(counters[0].ts, 125)
  })

  it('wraps events with displayTimeUnit and otherData', () => {
    const payload = buildPerfettoChromeTrace(miniTrace(), { lo: 100, hi: 200 })
    assert.equal(payload.displayTimeUnit, 'ns')
    assert.equal(payload.otherData.timeScale, 'us')
    assert.equal(payload.otherData.btf_meta.creator, 'test')
    assert.equal(payload.otherData.export_lo, 100)
    assert.equal(payload.otherData.export_hi, 200)
    assert.ok(Array.isArray(payload.traceEvents))
    assert.ok(payload.traceEvents.length > 0)
  })
})
