import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import { parseBtf } from '../src/parser/btfParser.js'
import { packTrace, unpackTrace } from '../src/parser/tracePack.js'
import { taskMergeKey } from '../src/utils/colors.js'
import { execSliceSamples, findWcetSegment } from '../src/utils/statsAnalysis.js'
import { intervalStatsRows, intervalBoundaryCount } from '../src/utils/intervalAnalysis.js'
import { syncObjectStatsRows, syncExclusionNote } from '../src/utils/syncObjectAnalysis.js'
import { migrationGapPlotPoints } from '../src/utils/migrationAnalysis.js'
import { computeStatsTables, segIndicesMapFromTrace } from '../src/parser/statsCompute.js'

const TEXT = [
  '#version 2.2.0',
  '#timeScale ns',
  '100,Core_0,0,T,[0/0001]A,0,resume,',
  '200,Core_0,0,T,[0/0001]A,0,preempt,',
  '200,Core_0,0,T,[0/0002]B,0,resume,',
  '300,Core_0,0,T,[0/0002]B,0,preempt,',
  '300,Core_0,0,T,[0/0001]A,0,resume,',
  '310,Core_0,0,STI,mutex,0,trigger,take 0x10',
  '320,Core_0,0,STI,interval_start,0,trigger,7',
  '320,Core_0,0,STI,interval_stop,0,trigger,7',
  '330,Core_0,0,STI,interval_stop,0,trigger,9',
  '340,Core_0,0,STI,interval_start,0,trigger,8',
  '360,Core_0,0,STI,interval_stop,0,trigger,8',
  '400,Core_0,0,T,[0/0001]A,0,preempt,',
  '400,Core_0,0,T,[0/0002]B,0,resume,',
  '420,Core_0,0,STI,mutex,0,trigger,give 0x10',
  '900,Core_0,0,STI,marker,0,trigger,end',
  '',
].join('\n')

describe('metric validity rules', () => {
  it('skips the slice still open at trace end in samples and finders', async () => {
    const tr = await parseBtf(TEXT)
    assert.ok(tr.openAtEndTasks.has('[0/0002]B'))
    const segs = tr.segByMergeKey.get(taskMergeKey('[0/0002]B'))
    assert.deepEqual(execSliceSamples(segs, null, null), [100, tr.timeMax - 400])
    assert.deepEqual(execSliceSamples(segs, null, null, tr), [100])
    const w = findWcetSegment(segs, null, null, tr)
    assert.deepEqual([w.start, w.end], [200, 300])
    const packed = unpackTrace(packTrace(tr))
    const { exec } = computeStatsTables(packed.segStore, {
      tasks: packed.tasks,
      taskRepr: packed.taskRepr,
      segIndicesByMk: segIndicesMapFromTrace(packed),
      lo: null,
      hi: null,
      totalNs: packed.timeMax - packed.timeMin,
      openAtEndTasks: packed.openAtEndTasks,
      timeMax: packed.timeMax,
    })
    const rowB = exec.find(r => r.mk === taskMergeKey('[0/0002]B'))
    assert.equal(rowB.runs, 1)
    const cpuNs = 100 + (tr.timeMax - 400)
    assert.ok(Math.abs(rowB.cpuPct - (100 * cpuNs) / (tr.timeMax - tr.timeMin)) < 1e-9)
  })

  it('survives pack/unpack', async () => {
    const tr = unpackTrace(packTrace(await parseBtf(TEXT)))
    assert.ok(tr.openAtEndTasks.has('[0/0002]B'))
    assert.equal(tr.intervalUnmatchedStops, 1)
    assert.ok(Array.isArray(tr.tickStiCounts))
  })

  it('counts unmatched stops and keeps zero-length spans', async () => {
    const tr = await parseBtf(TEXT)
    assert.equal(tr.intervalUnmatchedStops, 1)
    const durs = tr.intervalInstances.map(i => i.durationNs).sort((a, b) => a - b)
    assert.deepEqual(durs, [0, 20])
  })

  it('interval statistics need both endpoints in the window', async () => {
    const tr = await parseBtf(TEXT)
    const ids = intervalStatsRows(tr, 330, 350).map(r => r.id)
    assert.ok(!ids.includes('8'))
    assert.equal(intervalBoundaryCount(tr, 330, 350), 1)
    assert.deepEqual(intervalStatsRows(tr, null, null).map(r => r.id).sort(), ['7', '8'])
  })

  it('excludes cross-task mutex gives from hold samples', async () => {
    const tr = await parseBtf(TEXT)
    const rows = syncObjectStatsRows(tr, null, null)
    assert.equal(rows.length, 1)
    assert.equal(rows[0].holdCount, 0)
    assert.equal(rows[0].crossTaskExcluded, 1)
    assert.match(syncExclusionNote(rows), /1 cross-task mutex give/)
  })

  it('plots zero migration gaps', async () => {
    const tr = await parseBtf([
      '#version 2.2.0',
      '#timeScale ns',
      '100,Core_0,0,T,[0/0001]A,0,resume,',
      '200,Core_0,0,T,[0/0001]A,0,preempt,',
      '200,Core_1,0,T,[1/0001]A,0,resume,',
      '300,Core_1,0,T,[1/0001]A,0,preempt,',
      '',
    ].join('\n'))
    const mk = [...tr.migrationsByMk.keys()][0]
    assert.deepEqual(migrationGapPlotPoints(tr, mk, null, null).map(p => p.yValue), [0])
  })

  it('does not flag inheritance alone as inversion', async () => {
    const tr = await parseBtf([
      '#version 2.2.0',
      '#timeScale ns',
      '0,Core_0,0,T,[0/0001]L,0,resume,create pri:1',
      '0,Core_0,0,T,[0/0001]L,0,preempt,',
      '1,Core_0,0,T,[0/0002]H,0,resume,create pri:5',
      '2,Core_0,0,T,[0/0002]H,0,preempt,',
      '10,Core_0,0,T,[0/0001]L,0,resume,',
      '20,Core_0,0,STI,task,0,trigger,priority_inherit [0/0001]L pri:5',
      '40,Core_0,0,STI,task,0,trigger,priority_disinherit [0/0001]L pri:1',
      '50,Core_0,0,T,[0/0001]L,0,preempt,',
      '',
    ].join('\n'))
    assert.equal(tr.priorityEpisodes.length, 1)
    assert.equal(tr.priorityEpisodes[0].inherited, true)
    assert.equal(tr.priorityEpisodes[0].inversionSuspect, false)
  })
})
