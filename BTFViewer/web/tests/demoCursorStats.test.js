import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { describe, it } from 'node:test'
import { fileURLToPath } from 'node:url'

import { parseBtf } from '../src/parser/btfParser.js'
import { finalizeAndEnrich } from '../src/parser/tracePack.js'
import { computeStatsTables, segIndicesMapFromTrace } from '../src/parser/statsCompute.js'
import { decompressBtfBytes } from '../src/utils/btfLoad.js'
import { demoTimeToTraceUnits } from '../src/utils/demoXml.js'
import { getStatsRange, segOverlapsRange } from '../src/utils/statsRange.js'
import { schedulingStats, preemptionChainRows } from '../src/utils/statsAnalysis.js'
import { tickHealthReport } from '../src/utils/tickHealth.js'
import { collectTraceAnalysisFindings } from '../src/utils/workflowAnalysis.js'
import { priorityStatsRows } from '../src/utils/priorityAnalysis.js'
import { concurrentCoreActiveRows, switchOverheadRows } from '../src/utils/schedulerSmpMetrics.js'
import { buildCoreTimeBreakdown, buildCorePairRows, migrationRows } from '../src/utils/migrationAnalysis.js'
import { buildTaskLifecycleRows } from '../src/utils/lifecycleAnalysis.js'
import { buildCoreAffinityRows } from '../src/utils/coreAffinityAnalysis.js'
import { computeDeadlineViolations } from '../src/utils/deadlineAnalysis.js'
const TRACE_PATH = fileURLToPath(
  new URL('../../demos/demo_8cores/demo_8cores.btf.gz', import.meta.url),
)

describe('demo_8cores cursor-scoped stats', () => {
  it('keeps statistics populated for the priority-inversion C1–C2 window', async () => {
    const text = decompressBtfBytes(new Uint8Array(readFileSync(TRACE_PATH)), 'demo_8cores.btf.gz')
    const trace = finalizeAndEnrich(await parseBtf(text))
    const lo = demoTimeToTraceUnits('3.085', 's', trace.timeScale)
    const hi = demoTimeToTraceUnits('3.310', 's', trace.timeScale)
    assert.equal(lo, 3085000)
    assert.equal(hi, 3310000)

    const cursors = [lo, hi, null, null]
    const range = getStatsRange(cursors, true)
    assert.ok(range)
    assert.equal(range.lo, lo)
    assert.equal(range.hi, hi)

    let taskCount = 0
    let segCount = 0
    for (const segs of trace.segByMergeKey.values()) {
      if (segs.some(s => segOverlapsRange(s, lo, hi))) taskCount++
      for (const s of segs) {
        if (s.end <= lo) continue
        if (s.start > hi) break
        if (segOverlapsRange(s, lo, hi)) segCount++
      }
    }
    assert.ok(taskCount > 0, `expected tasks in cursor range, got ${taskCount}`)
    assert.ok(segCount > 0, `expected segments in cursor range, got ${segCount}`)

    const sched = schedulingStats(trace, lo, hi)
    assert.ok(sched.contextSwitches > 0, 'expected context switches in cursor range')

    tickHealthReport(trace, lo, hi)
    concurrentCoreActiveRows(trace, lo, hi)
    switchOverheadRows(trace, lo, hi)
    buildCoreTimeBreakdown(trace, lo, hi)
    buildCorePairRows(trace, lo, hi)
    migrationRows(trace, lo, hi)
    buildTaskLifecycleRows(
      trace.stiEvents, trace.taskRepr, lo, hi, trace.taskCreateTimes, trace.segByMergeKey,
    )
    buildCoreAffinityRows(trace, lo, hi)
    computeDeadlineViolations(trace, {}, lo, hi)
    collectTraceAnalysisFindings(trace, lo, hi, {})

    const pri = priorityStatsRows(trace, lo, hi)
    assert.ok(pri.length > 0, 'expected priority boost rows in inversion window')
    assert.ok(pri.some(r => /low/i.test(r.label)), 'expected Low task boost in inversion window')

    const { rows: preempt } = preemptionChainRows(trace, lo, hi)
    assert.ok(Array.isArray(preempt))

    const tables = computeStatsTables(trace.segStore, {
      tasks: trace.tasks,
      taskRepr: trace.taskRepr,
      segIndicesByMk: segIndicesMapFromTrace(trace),
      lo,
      hi,
      totalNs: hi - lo,
    })
    assert.ok(tables.block.length > 0, `expected blocking rows, got ${tables.block.length}`)
    assert.ok(tables.exec.length > 0, `expected exec rows, got ${tables.exec.length}`)
    assert.ok(tables.taskCpuNs.length > 0, 'expected task CPU in cursor range')
  })
})
