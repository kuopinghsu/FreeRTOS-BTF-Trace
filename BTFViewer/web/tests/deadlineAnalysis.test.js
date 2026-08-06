import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import { computeDeadlineViolations, deadlineSliceAnnotationNote } from '../src/utils/deadlineAnalysis.js'
import { formatTimeFixed, nsToTraceUnits } from '../src/utils/timeFormat.js'

describe('nsToTraceUnits', () => {
  it('maps 1000 ns to 1 µs on us-scale traces', () => {
    assert.equal(nsToTraceUnits(1000, 'us'), 1)
    assert.equal(formatTimeFixed(nsToTraceUnits(1000, 'us'), 'us'), '1.000 µs')
  })

  it('keeps nanoseconds unchanged on ns-scale traces', () => {
    assert.equal(nsToTraceUnits(1000, 'ns'), 1000)
    assert.equal(formatTimeFixed(nsToTraceUnits(1000, 'ns'), 'ns'), '1.000 µs')
  })
})

describe('computeDeadlineViolations ns deadlines', () => {
  function miniTrace(scale, segsByMk) {
    return {
      timeScale: scale,
      timeMin: 0,
      timeMax: 1e6,
      segByMergeKey: new Map(Object.entries(segsByMk)),
      taskRepr: Object.fromEntries(Object.keys(segsByMk).map(k => [k, k])),
    }
  }

  it('treats Settings deadlines as nanoseconds on us traces', () => {
    // 1000 ns = 1 µs. A 2 µs slice should violate; a 1 µs slice should not.
    const trace = miniTrace('us', {
      'CS[16]': [
        { task: 'CS[16]', start: 0, end: 2 },
        { task: 'CS[16]', start: 10, end: 11 },
      ],
    })
    const { sliceViolations } = computeDeadlineViolations(trace, {
      taskDeadlines: { 'CS[16]': 1000 },
    })
    assert.equal(sliceViolations.length, 1)
    assert.equal(sliceViolations[0].limit, '1.000 µs')
    assert.equal(sliceViolations[0].duration, '2.000 µs')
    // Must not treat 1000 as 1000 µs (= 1 ms).
    assert.notEqual(sliceViolations[0].limit, '1.000 ms')
    assert.equal(sliceViolations[0].mk, 'CS[16]')
    assert.equal(sliceViolations[0].startNs, 0)
    assert.ok(sliceViolations[0].segment)
    assert.match(
      deadlineSliceAnnotationNote(trace, sliceViolations[0]),
      /over deadline: 2\.000 µs > 1\.000 µs at/,
    )
  })
})
