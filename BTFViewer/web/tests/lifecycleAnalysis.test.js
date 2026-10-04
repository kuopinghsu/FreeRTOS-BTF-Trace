import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import { buildTaskLifecycleRows, parseTaskLifecycleNote } from '../src/utils/lifecycleAnalysis.js'

describe('parseTaskLifecycleNote', () => {
  it('ignores unnamed resume / resume-from-ISR rows', () => {
    assert.equal(parseTaskLifecycleNote('resume'), null)
    assert.equal(parseTaskLifecycleNote('resume/isr'), null)
    assert.deepEqual(parseTaskLifecycleNote('resume B[2]'), { action: 'resume', label: 'B[2]' })
  })
})

function fakeSegList(items) {
  return {
    length: items.length,
    [Symbol.iterator]: function* () { yield* items },
  }
}

describe('buildTaskLifecycleRows', () => {
  it('counts overlapping runs in a cursor range without Array.reduce', () => {
    const segs = fakeSegList([
      { start: 10, end: 20 },
      { start: 50, end: 60 },
    ])
    const rows = buildTaskLifecycleRows(
      [],
      new Map([['Low', 'Low[266]']]),
      0,
      30,
      new Map([['Low', 5]]),
      new Map([['Low', segs]]),
    )
    assert.equal(rows.length, 1)
    assert.equal(rows[0].runCount, 1)
  })
})
