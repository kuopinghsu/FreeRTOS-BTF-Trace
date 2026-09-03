import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { describe, it } from 'node:test'
import { fileURLToPath } from 'node:url'

import { parseBtf } from '../src/parser/btfParser.js'
import { finalizeAndEnrich } from '../src/parser/tracePack.js'
import { computeStatsTables, segIndicesMapFromTrace } from '../src/parser/statsCompute.js'
import { decompressBtfBytes } from '../src/utils/btfLoad.js'
import { demoTimeToTraceUnits } from '../src/utils/demoXml.js'
import { segOverlapsRange } from '../src/utils/statsRange.js'
import { schedulingStats, blockingTimeSamples } from '../src/utils/statsAnalysis.js'
import { priorityStatsRows } from '../src/utils/priorityAnalysis.js'
import { buildTaskLifecycleRows } from '../src/utils/lifecycleAnalysis.js'
import { parseTaskName, isIdleTaskName, taskDisplayName } from '../src/utils/colors.js'

const __dirname = dirname(fileURLToPath(import.meta.url))
const FIXTURE = join(__dirname, '../../tests/fixtures/demo_8cores-cursor-stats-golden.json')
const TRACE = join(__dirname, '../../demos/demo_8cores/demo_8cores.btf.gz')

function sampleSummary(samples) {
  let min = samples[0]
  let max = samples[0]
  let sum = 0
  for (const v of samples) {
    if (v < min) min = v
    if (v > max) max = v
    sum += v
  }
  return { n: samples.length, min, max, sum }
}

async function cursorStatsSnapshot() {
  const text = decompressBtfBytes(new Uint8Array(readFileSync(TRACE)), 'demo_8cores.btf.gz')
  const trace = finalizeAndEnrich(await parseBtf(text))
  const lo = demoTimeToTraceUnits('3.085', 's', trace.timeScale)
  const hi = demoTimeToTraceUnits('3.310', 's', trace.timeScale)

  let taskCount = 0
  let segCount = 0
  for (const segs of trace.segByMergeKey.values()) {
    if (segs.some(s => segOverlapsRange(s, lo, hi))) taskCount++
    for (const s of segs) {
      if (segOverlapsRange(s, lo, hi)) segCount++
    }
  }

  const sched = schedulingStats(trace, lo, hi)
  const lifecycle = buildTaskLifecycleRows(
    trace.stiEvents, trace.taskRepr, lo, hi, trace.taskCreateTimes, trace.segByMergeKey,
  ).map(r => ({
    label: r.label,
    createNs: r.createNs,
    deleteNs: r.deleteNs,
    suspendCount: r.suspendCount,
    resumeCount: r.resumeCount,
    aliveNs: r.aliveSpanNs,
    eventCount: r.eventCount,
    runCount: r.runCount,
  })).sort((a, b) => a.label.localeCompare(b.label))

  const priority = priorityStatsRows(trace, lo, hi).map(r => ({
    label: r.label,
    basePri: r.basePri,
    peakPri: r.peakPri,
    episodeCount: r.episodeCount,
    totalBoostNs: r.totalBoostNs,
    invertWorstNs: r.invertWorstNs,
    invertTotalNs: r.invertTotalNs,
    pattern: r.pattern,
  })).sort((a, b) => a.label.localeCompare(b.label))

  const block = []
  const execRows = []
  for (const [mk, segs] of trace.segByMergeKey) {
    const raw = trace.taskRepr.get(mk) || mk
    const { name } = parseTaskName(raw)
    if (isIdleTaskName(name) || name === 'TICK') continue
    const label = taskDisplayName(raw)
    const bs = blockingTimeSamples(segs, lo, hi)
    if (bs.length) block.push({ label, ...sampleSummary(bs) })
    const es = []
    for (const s of segs) {
      const d = s.end - s.start
      if (d <= 0) continue
      if (s.start < lo || s.end > hi) continue
      es.push(d)
    }
    if (es.length) execRows.push({ label, ...sampleSummary(es) })
  }
  block.sort((a, b) => a.label.localeCompare(b.label))
  execRows.sort((a, b) => a.label.localeCompare(b.label))

  const tables = computeStatsTables(trace.segStore, {
    tasks: trace.tasks,
    taskRepr: trace.taskRepr,
    segIndicesByMk: segIndicesMapFromTrace(trace),
    lo,
    hi,
    totalNs: hi - lo,
  })

  return {
    snapshot: {
      trace: 'demo_8cores.btf.gz',
      timeScale: trace.timeScale,
      lo,
      hi,
      taskCount,
      segCount,
      scheduling: {
        contextSwitches: sched.contextSwitches,
        gapCount: sched.coreGaps.length,
        gapSum: sched.coreGaps.reduce((a, b) => a + b, 0),
      },
      priority,
      lifecycle,
      block,
      exec: execRows,
    },
    tables,
  }
}

describe('web ↔ desktop stats parity', () => {
  it('matches the shared demo_8cores C1–C2 golden', async () => {
    assert.ok(existsSync(TRACE), `missing trace fixture: ${TRACE}`)
    assert.ok(existsSync(FIXTURE), `missing golden fixture: ${FIXTURE}`)

    const expected = JSON.parse(readFileSync(FIXTURE, 'utf8'))
    const { snapshot, tables } = await cursorStatsSnapshot()

    assert.deepEqual(snapshot, expected)
    assert.equal(tables.block.length, expected.block.length)
    assert.equal(tables.exec.length, expected.exec.length)
    assert.ok(tables.taskCpuNs.length > 0, 'expected task CPU in cursor range')
  })
})
