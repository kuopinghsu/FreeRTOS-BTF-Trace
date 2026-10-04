import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import { parseBtf } from '../src/parser/btfParser.js'
import {
  syncObjectStatsRows,
  syncObjectHoldDetailRows,
  syncExclusionNote,
  syncKindDisplay,
} from '../src/utils/syncObjectAnalysis.js'

const TEXT = [
  '#version 2.2.0',
  '#timeScale ns',
  '0,Core_0,0,T,[0/0001]A,0,resume,',
  '10,Core_0,0,STI,mutex,0,trigger,create 0x1',
  '12,Core_0,0,STI,mutex,0,trigger,give 0x1',
  '1500,Core_0,0,STI,mutex,0,trigger,take 0x1',
  '1600,Core_0,0,STI,mutex,0,trigger,give 0x1',
  '900,Core_0,0,STI,sem,0,trigger,create 0x2',
  '2000,Core_0,0,STI,sem,0,trigger,give 0x2',
  '2100,Core_0,0,STI,sem,0,trigger,take 0x2',
  '2200,Core_0,0,STI,queue,0,trigger,send 0x3',
  '2300,Core_0,0,STI,queue,0,trigger,recv 0x3',
  '2400,Core_0,0,STI,mutex,0,trigger,delete 0x1',
  '2500,Core_0,0,STI,mutex,0,trigger,create 0x1',
  '2510,Core_0,0,STI,mutex,0,trigger,give 0x1',
  '3600,Core_0,0,STI,mutex,0,trigger,take 0x1',
  '3700,Core_0,0,STI,mutex,0,trigger,give 0x1',
  '5000,Core_0,0,T,[0/0001]A,0,preempt,',
  '',
].join('\n')

describe('sync span kinds and lifecycle generations', () => {
  it('labels each span by object type', async () => {
    const tr = await parseBtf(TEXT)
    const kinds = new Set([...tr.syncObjects.values()].flatMap(o => o.holds.map(h => h.spanKind)))
    assert.deepEqual([...kinds].sort(), ['mutex_hold', 'queue_send_recv', 'sem_give_take'])
    const rows = new Map(syncObjectStatsRows(tr).map(r => [r.label, r]))
    assert.equal(syncKindDisplay(rows.get('sem 0x2')), 'sem · give→take')
    assert.equal(syncKindDisplay(rows.get('queue 0x3')), 'queue · send→recv')
  })

  it('keeps a re-created handle as its own generation', async () => {
    const tr = await parseBtf(TEXT)
    assert.ok(tr.syncObjects.has('mutex:0x1#1'))
    assert.equal(tr.syncObjects.get('mutex:0x1').generation, 2)
    const labels = syncObjectStatsRows(tr).map(r => r.label)
    assert.ok(labels.includes('mutex 0x1 (gen 1)'))
    assert.ok(labels.includes('mutex 0x1 (gen 2)'))
    const details = syncObjectHoldDetailRows(tr).map(d => `${d.object}|${d.span}`)
    assert.ok(details.includes('mutex 0x1 (gen 1)|hold'))
    assert.ok(details.includes('mutex 0x1 (gen 2)|hold'))
  })

  it('counts kernel post-create gives in the exclusion note', async () => {
    const tr = await parseBtf(TEXT)
    const rows = syncObjectStatsRows(tr)
    assert.equal(rows.reduce((a, r) => a + r.postCreateGives, 0), 2)
    assert.match(syncExclusionNote(rows), /2 kernel give\(s\) right after create/)
  })
})
