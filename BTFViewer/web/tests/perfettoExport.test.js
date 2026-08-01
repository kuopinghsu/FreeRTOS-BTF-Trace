import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  buildPerfettoChromeEvents,
  buildPerfettoChromeTrace,
  toTraceUs,
} from '../src/utils/perfettoExport.js'

describe('toTraceUs', () => {
  it('converts us-scale timestamps to Chrome Trace microseconds', () => {
    assert.equal(toTraceUs(1000, 'us'), 1000)
    assert.equal(toTraceUs(1, 'ms'), 1000)
    assert.equal(toTraceUs(1000, 'ns'), 1)
  })
})

describe('buildPerfettoChromeTrace', () => {
  const mk = '\x001\x00Worker'

  function miniTrace() {
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
      stiChannels: ['mutex', 'interval_start', 'interval_stop'],
      stiEvents: [
        { time: 120, core: 'Core_0', target: 'mutex', event: 'trigger', note: 'take' },
        { time: 110, core: 'Core_0', target: 'interval_start', event: 'trigger', note: 'spanA tid:1' },
        { time: 140, core: 'Core_0', target: 'interval_stop', event: 'trigger', note: 'spanA tid:1' },
      ],
      tickStiTimes: [200],
      intervalIds: ['spanA'],
      intervalInstances: [
        {
          id: 'spanA', startNs: 110, stopNs: 140,
          startCore: 'Core_0', stopCore: 'Core_0', taskId: '1',
        },
      ],
    }
  }

  it('emits process metadata for Cores, Tasks, STI, Intervals', () => {
    const events = buildPerfettoChromeEvents(miniTrace())
    const procs = events
      .filter(e => e.name === 'process_name')
      .map(e => e.args.name)
    assert.deepEqual(procs, ['Cores', 'Tasks', 'STI', 'Intervals'])
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
    assert.ok(instants.some(e => e.name === 'take'))
    assert.ok(instants.some(e => e.name === 'migrate'))
    assert.ok(instants.some(e => e.name === 'TICK'))
  })

  it('skips interval_start/stop in STI tracks (they become Intervals)', () => {
    const events = buildPerfettoChromeEvents(miniTrace())
    const stiThreads = events
      .filter(e => e.name === 'thread_name' && e.pid === 3)
      .map(e => e.args.name)
    assert.ok(!stiThreads.includes('interval_start'))
    assert.ok(!stiThreads.includes('interval_stop'))
    assert.ok(stiThreads.includes('mutex'))
    assert.ok(stiThreads.includes('TICK'))

    const stiChannels = new Set(
      events
        .filter(e => e.ph === 'i' && e.pid === 3 && e.cat === 'sti')
        .map(e => e.args?.channel)
        .filter(Boolean),
    )
    assert.ok(!stiChannels.has('interval_start'))
    assert.ok(!stiChannels.has('interval_stop'))
    assert.ok(stiChannels.has('mutex'))

    const intervals = events.filter(e => e.ph === 'X' && e.cat === 'interval')
    assert.equal(intervals.length, 1)
    assert.equal(intervals[0].name, 'spanA')
    assert.equal(intervals[0].ts, 110)
    assert.equal(intervals[0].dur, 30)
  })

  it('wraps events with displayTimeUnit and otherData', () => {
    const payload = buildPerfettoChromeTrace(miniTrace())
    assert.equal(payload.displayTimeUnit, 'ns')
    assert.equal(payload.otherData.timeScale, 'us')
    assert.equal(payload.otherData.btf_meta.creator, 'test')
    assert.ok(Array.isArray(payload.traceEvents))
    assert.ok(payload.traceEvents.length > 0)
  })
})
