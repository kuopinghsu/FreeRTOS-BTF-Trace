import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import { parseBtf } from '../src/parser/btfParser.js'
import { taskMergeKey } from '../src/utils/colors.js'

function segSpan(trace, rawName) {
  const mk = taskMergeKey(rawName)
  const segs = trace.segByMergeKey?.get(mk) || []
  return segs.map((s) => [s.start, s.end, s.core])
}

describe('resume source dual dialect', () => {
  it('rebuilds segments when resume source is Core (BTF 2.3)', async () => {
    const text = [
      '#version 2.2.0',
      '#timeScale us',
      '100,Core_0,0,T,[0/0001]A,0,resume,',
      '200,Core_0,0,T,[0/0001]A,0,preempt,',
      '200,Core_0,0,T,[0/0002]B,0,resume,',
      '300,Core_0,0,T,[0/0002]B,0,preempt,',
      '',
    ].join('\n')
    const tr = await parseBtf(text)
    assert.deepEqual(segSpan(tr, '[0/0001]A'), [[100, 200, 'Core_0']])
    assert.deepEqual(segSpan(tr, '[0/0002]B'), [[200, 300, 'Core_0']])
  })

  it('rebuilds segments when resume source is previous task (legacy)', async () => {
    const text = [
      '#version 2.2.0',
      '#timeScale us',
      '100,Core_0,0,T,[0/0001]A,0,resume,',
      '200,Core_0,0,T,[0/0001]A,0,preempt,',
      '200,[0/0001]A,0,T,[0/0002]B,0,resume,',
      '300,Core_0,0,T,[0/0002]B,0,preempt,',
      '',
    ].join('\n')
    const tr = await parseBtf(text)
    assert.deepEqual(segSpan(tr, '[0/0001]A'), [[100, 200, 'Core_0']])
    assert.deepEqual(segSpan(tr, '[0/0002]B'), [[200, 300, 'Core_0']])
  })
})
