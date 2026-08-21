import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import { drawableTimeRange, parseBtf } from '../src/parser/btfParser.js'

describe('drawableTimeRange', () => {
  it('returns null when nothing is painted', () => {
    assert.equal(drawableTimeRange([], [], []), null)
  })

  it('uses segment start/end, not earlier create-only timestamps', () => {
    const r = drawableTimeRange(
      [{ task: 'W', start: 22_000, end: 30_000, core: 'Core_0' }],
      [],
      [],
    )
    assert.deepEqual(r, { lo: 22_000, hi: 30_000 })
  })

  it('includes STI and tick marks', () => {
    const r = drawableTimeRange(
      [{ task: 'W', start: 100, end: 200, core: 'Core_0' }],
      [{ time: 50, core: 'Core_0', target: 'mutex', event: 'trigger', note: '' }],
      [250],
    )
    assert.deepEqual(r, { lo: 50, hi: 250 })
  })
})

describe('parseBtf time bounds', () => {
  it('anchors timeMin to first resume, skipping task_create storm', async () => {
    const text = [
      '#version 2.2.0',
      '#timeScale us',
      '0,Core_0,0,C,Core_0,0,set_frequency,1000000',
      '100,Core_0,0,T,IDLE0,0,preempt,task_create',
      '200,Core_0,0,T,Worker,0,preempt,task_create',
      '22000,Core_0,0,T,Worker,0,resume,',
      '30000,Core_0,0,T,Worker,0,preempt,',
      '',
    ].join('\n')

    const trace = await parseBtf(text)
    assert.equal(trace.timeMin, 22_000)
    assert.equal(trace.timeMax, 30_000)
    assert.equal(trace.segments.length, 1)
    assert.equal(trace.segments[0].start, 22_000)
    assert.equal(trace.segments[0].end, 30_000)
  })

  it('accepts #timeScale / #timescale case-insensitively', async () => {
    for (const header of ['#timeScale us', '#timescale us', '#TIMESCALE us', '#TimeScale us']) {
      const text = [
        '#version 2.2.0',
        header,
        '1000,Core_0,0,T,Worker,0,resume,',
        '2000,Core_0,0,T,Worker,0,preempt,',
        '',
      ].join('\n')
      const trace = await parseBtf(text)
      assert.equal(trace.timeScale, 'us', header)
      assert.equal(trace.meta?.timeScale, 'us', header)
    }
  })
})
