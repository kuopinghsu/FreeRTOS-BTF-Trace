import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import { filterBtfTextToRange, reconstructBtfSlice } from '../src/utils/btfSlice.js'

const SRC = [
  '#version 1.0.0',
  '#timeScale us',
  '0,Core_0,0,C,1000000',
  '100,Core_0,0,T,Worker,0,resume,',
  '150,Core_0,0,T,Worker,0,preempt,',
  '200,Core_0,0,T,Worker,0,resume,',
  '250,Core_0,0,STI,ERR,0,trigger,boom',
  '300,Core_0,0,T,Worker,0,preempt,',
].join('\n')

describe('btfSlice', () => {
  it('keeps meta, C rows, and in-range events', () => {
    const { text, kept } = filterBtfTextToRange(SRC, 200, 250)
    assert.match(text, /#version 1\.0\.0/)
    assert.match(text, /#sliced 200-250/)
    assert.match(text, /0,Core_0,0,C,1000000/)
    assert.match(text, /200,Core_0,0,T,Worker,0,resume,/)
    assert.match(text, /250,Core_0,0,STI,ERR,0,trigger,boom/)
    assert.doesNotMatch(text, /100,Core_0,0,T,Worker,0,resume,/)
    assert.equal(kept, 2)
  })

  it('swaps inverted ranges', () => {
    const { kept, text } = filterBtfTextToRange(SRC, 250, 200)
    assert.equal(kept, 2)
    assert.match(text, /#sliced 200-250/)
  })

  it('reconstructs a slice from segments and STI', () => {
    const { text, kept } = reconstructBtfSlice({
      timeScale: 'us',
      meta: { creator: 'test' },
      segments: [{ task: 'Worker', start: 100, end: 400, core: 'Core_0' }],
      stiEvents: [{ time: 220, core: 'Core_0', target: 'ERR', event: 'trigger', note: 'boom' }],
      tickStiTimes: [],
      taskRepr: { Worker: 'Worker' },
    }, 150, 250)
    assert.match(text, /#creator test/)
    assert.match(text, /#sliced 150-250/)
    assert.match(text, /150,Core_0,0,T,Worker,0,resume,/)
    assert.match(text, /250,Core_0,0,T,Worker,0,preempt,/)
    assert.match(text, /220,Core_0,0,STI,ERR,0,trigger,boom/)
    assert.equal(kept, 3)
  })
})
