import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import { taskMergeKey } from '../src/utils/colors.js'
import {
  affinityMaskAtTime,
  buildCoreAffinityRows,
  formatAffinityMaskHistory,
} from '../src/utils/coreAffinityAnalysis.js'

describe('affinityMaskAtTime', () => {
  it('returns null before the first set', () => {
    const hist = [[100, 0x1], [200, 0x8]]
    assert.equal(affinityMaskAtTime(hist, 50), null)
    assert.equal(affinityMaskAtTime(hist, 100), 0x1)
    assert.equal(affinityMaskAtTime(hist, 150), 0x1)
    assert.equal(affinityMaskAtTime(hist, 200), 0x8)
  })
})

describe('formatAffinityMaskHistory', () => {
  it('collapses duplicate consecutive masks', () => {
    assert.equal(formatAffinityMaskHistory([[1, 1], [2, 1], [3, 8]]), '0x1 → 0x8')
  })
})

describe('buildCoreAffinityRows', () => {
  function makeTrace(sti, segsByLabel, cores = ['Core_0', 'Core_1', 'Core_2', 'Core_3']) {
    const segByMergeKey = new Map()
    const taskRepr = new Map()
    for (const [label, segs] of Object.entries(segsByLabel)) {
      const mk = taskMergeKey(label)
      taskRepr.set(mk, label)
      segByMergeKey.set(mk, segs.map(([start, end, core]) => ({
        task: label, start, end, core,
      })))
    }
    return {
      stiEvents: sti,
      segByMergeKey,
      taskRepr,
      coreNames: cores,
    }
  }

  it('flags a true static-mask violation', () => {
    const tr = makeTrace(
      [{ time: 50, target: 'task', note: 'affinity_set Pin[1] 0x1' }],
      {
        'Pin[1]': [
          [100, 200, 'Core_0'],
          [300, 400, 'Core_2'],
        ],
      },
    )
    const rows = buildCoreAffinityRows(tr)
    assert.equal(rows.length, 1)
    assert.equal(rows[0].maskHex, '0x1')
    assert.equal(rows[0].violations, 'Core_2')
  })

  it('does not false-flag pre-set runs or intentional mask changes', () => {
    const tr = makeTrace(
      [
        { time: 200, target: 'task', note: 'affinity_set AffM[5] 0x1' },
        { time: 500, target: 'task', note: 'affinity_set AffM[5] 0x8' },
      ],
      {
        'AffM[5]': [
          [50, 150, 'Core_2'],
          [250, 350, 'Core_0'],
          [450, 490, 'Core_0'],
          [550, 650, 'Core_3'],
        ],
      },
    )
    const rows = buildCoreAffinityRows(tr)
    assert.equal(rows.length, 1)
    assert.equal(rows[0].maskHex, '0x1 → 0x8')
    assert.match(rows[0].observedCores, /Core_2/)
    assert.equal(rows[0].violations, '—')
  })

  it('flags a violation after a mask change', () => {
    const tr = makeTrace(
      [
        { time: 100, target: 'task', note: 'affinity_set AffM[5] 0x1' },
        { time: 300, target: 'task', note: 'affinity_set AffM[5] 0x8' },
      ],
      {
        'AffM[5]': [
          [150, 200, 'Core_0'],
          [350, 400, 'Core_1'],
        ],
      },
    )
    assert.equal(buildCoreAffinityRows(tr)[0].violations, 'Core_1')
  })
})
