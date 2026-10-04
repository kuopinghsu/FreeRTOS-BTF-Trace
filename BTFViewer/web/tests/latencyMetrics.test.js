import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import { parseBtf } from '../src/parser/btfParser.js'
import { taskMergeKey } from '../src/utils/colors.js'
import { collectDispatchLatencyByMk } from '../src/utils/schedulerSmpMetrics.js'
import { priorityEpisodeDetailRows } from '../src/utils/priorityAnalysis.js'
import { intervalInstanceDetailRows } from '../src/utils/intervalAnalysis.js'
import {
  dispatchSourceNote,
  sameCoreGapSamples,
  migrationGapBaselineNote,
  priorityEpisodeCpuSplit,
  priorityHolderNote,
  affinityChangeToRunSamples,
  affinityChangeNote,
  suspendedSpans,
  suspendedDurationNote,
  intervalExecSplit,
  intervalExecNote,
} from '../src/utils/latencyMetrics.js'

const TEXT = [
  '#version 2.2.0',
  '#timeScale ns',
  '0,Core_0,0,T,[0/0001]A,0,resume,create pri:1',
  '100,Core_0,0,T,[0/0001]A,0,preempt,',
  '100,Core_0,0,T,[0/0002]B,0,resume,create pri:3',
  '150,Core_0,0,STI,interval_start,0,trigger,5',
  '200,Core_0,0,T,[0/0002]B,0,preempt,',
  '200,Core_0,0,T,[0/0001]A,0,resume,',
  '250,Core_0,0,STI,interval_stop,0,trigger,5',
  '300,Core_0,0,T,[0/0001]A,0,preempt,',
  '300,Core_0,0,T,[0/0002]B,0,resume,',
  '310,Core_0,0,STI,task,0,trigger,suspend [0/0001]A',
  '320,Core_0,0,STI,task,0,trigger,resume [0/0001]A',
  '330,Core_0,0,STI,task,0,trigger,resume [0/0001]A',
  '350,Core_0,0,STI,task,0,trigger,priority_inherit [0/0002]B pri:5',
  '400,Core_0,0,T,[0/0002]B,0,preempt,',
  '420,Core_0,0,STI,task,0,trigger,affinity_set [0/0001]A 0x2',
  '450,Core_0,0,STI,task,0,trigger,priority_disinherit [0/0002]B pri:3',
  '500,Core_1,0,T,[1/0001]A,0,resume,',
  '600,Core_1,0,T,[1/0001]A,0,preempt,',
  '',
].join('\n')

const MK_A = taskMergeKey('[0/0001]A')
const MK_B = taskMergeKey('[0/0002]B')

describe('latency metrics from existing trace data', () => {
  it('tags dispatch source and merges repeated resumes', async () => {
    const tr = await parseBtf(TEXT)
    const byMk = collectDispatchLatencyByMk(tr, null, null)
    const a = byMk.get(MK_A)
    assert.deepEqual(a.samples, [0, 180])
    assert.deepEqual(a.sources, ['create', 'resume'])
    assert.equal(a.duplicates, 1)
    const note = dispatchSourceNote(tr, byMk)
    assert.match(note, /\(n=2\)/)
    assert.match(note, /resume→run avg/)
    assert.match(note, /1 repeated ready event\(s\)/)
  })

  it('computes the same-core gap baseline', async () => {
    const tr = await parseBtf(TEXT)
    assert.deepEqual(sameCoreGapSamples(tr).sort((x, y) => x - y), [100, 100])
    assert.match(migrationGapBaselineNote(tr), /over 2 gap\(s\)/)
  })

  it('splits boosted time into on/off CPU with boost→run', async () => {
    const tr = await parseBtf(TEXT)
    assert.deepEqual(priorityEpisodeCpuSplit(tr, tr.priorityEpisodes[0]), { onNs: 50, offNs: 50, boostToRunNs: 0 })
    assert.ok('onCpu' in priorityEpisodeDetailRows(tr, null, null)[0])
    assert.match(priorityHolderNote(tr), /\(50%\)/)
  })

  it('measures affinity change to first allowed run', async () => {
    const tr = await parseBtf(TEXT)
    const { samples, noRun } = affinityChangeToRunSamples(tr)
    assert.deepEqual(samples, [[420, 80, MK_A]])
    assert.equal(noRun, 0)
    assert.match(affinityChangeNote(tr), /over 1 change\(s\)/)
  })

  it('pairs suspend with resume of the same task', async () => {
    const tr = await parseBtf(TEXT)
    const { spans, still } = suspendedSpans(tr)
    assert.deepEqual(spans, [[310, 320, MK_A]])
    assert.equal(still, 0)
    assert.match(suspendedDurationNote(tr), /over 1 span\(s\)/)
  })

  it('splits an interval into the starting task on/off CPU', async () => {
    const tr = await parseBtf(TEXT)
    const inst = tr.intervalInstancesById.get('5')[0]
    assert.deepEqual(intervalExecSplit(tr, inst), { mk: MK_B, onNs: 50, offNs: 50 })
    assert.equal(intervalInstanceDetailRows(tr, null, null)[0].execTask, 'B[2]')
    assert.match(intervalExecNote(tr), /on-CPU 50%/)
  })
})
