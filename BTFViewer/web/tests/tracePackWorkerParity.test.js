import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import { parseBtf } from '../src/parser/btfParser.js'
import { packTrace, unpackTrace, finalizeAndEnrich } from '../src/parser/tracePack.js'

/**
 * A single task with many short, tightly-packed resume/preempt segments on
 * one core, so its per-task LOD summary (bounded to LOD_SUMMARY_BINS = 4096
 * bins) actually reduces the raw segment count. This is required to exercise
 * the regression below: with few enough segments, the LOD summary is a
 * pass-through and a bug that swaps the segment source wouldn't be visible.
 */
function syntheticBtfText(segmentCount) {
  const lines = ['#version 2.2.0', '#timeScale us']
  let t = 0
  for (let i = 0; i < segmentCount; i++) {
    lines.push(`${t},Core_0,0,T,Worker,0,resume,`)
    t += 10
    lines.push(`${t},Core_0,0,T,Worker,0,preempt,`)
    t += 5
  }
  lines.push('')
  return lines.join('\n')
}

// Regression test for the P1 fix: the packed worker reconstruction path
// (tracePack.js#enrichStartsMaps) used to build `coreTaskSegStarts` from
// `coreTaskSegLod` instead of `coreTaskSegs`, which silently diverges from
// the main-thread path (segStore.js#finalizeTraceStorage) whenever LOD
// reduction actually shrinks the per-task segment count
// (coreTaskSegs.length > coreTaskSegLod.length).
describe('worker (pack/unpack) vs main-thread trace reconstruction parity', () => {
  it('coreTaskSeg*/coreTaskSeg*Starts pairs match between the two paths under LOD reduction', async () => {
    const text = syntheticBtfText(6000)

    const mainTrace = finalizeAndEnrich(await parseBtf(text))
    const workerTrace = unpackTrace(packTrace(await parseBtf(text)).payload)

    // Sanity: this synthetic trace must actually exercise LOD reduction,
    // otherwise the regression this test guards against would never trigger.
    const rawLen = mainTrace.coreTaskSegs.get('Core_0').get('Worker').length
    const lodLen = mainTrace.coreTaskSegLod.get('Core_0').get('Worker').length
    assert.ok(lodLen < rawLen, `expected LOD reduction (raw=${rawLen}, lod=${lodLen})`)

    const pairs = [
      ['coreTaskSegs', 'coreTaskSegStarts'],
      ['coreTaskSegLod', 'coreTaskSegLodStarts'],
      ['coreTaskSegLodUltra', 'coreTaskSegLodUltraStarts'],
    ]

    for (const [segKey, startsKey] of pairs) {
      const mainSegs = mainTrace[segKey]
      const mainStarts = mainTrace[startsKey]
      const workerSegs = workerTrace[segKey]
      const workerStarts = workerTrace[startsKey]

      assert.deepEqual([...mainSegs.keys()].sort(), [...workerSegs.keys()].sort(),
        `${segKey}: core set mismatch`)

      for (const core of mainSegs.keys()) {
        const mainInner = mainSegs.get(core)
        const workerInner = workerSegs.get(core)
        assert.deepEqual([...mainInner.keys()].sort(), [...workerInner.keys()].sort(),
          `${segKey}[${core}]: task set mismatch`)

        for (const task of mainInner.keys()) {
          const segs = mainInner.get(task)
          const starts = mainStarts.get(core).get(task)
          const wSegs = workerInner.get(task)
          const wStarts = workerStarts.get(core).get(task)

          // Invariant: starts[i] == segments[i].start, on both paths.
          assert.equal(starts.length, segs.length,
            `${startsKey}[${core}][${task}]: main-thread length mismatch`)
          assert.equal(wStarts.length, wSegs.length,
            `${startsKey}[${core}][${task}]: worker length mismatch`)
          for (let i = 0; i < segs.length; i++) {
            assert.equal(starts[i], segs[i].start,
              `${startsKey}[${core}][${task}][${i}]: main-thread starts[i] != segments[i].start`)
          }
          for (let i = 0; i < wSegs.length; i++) {
            assert.equal(wStarts[i], wSegs[i].start,
              `${startsKey}[${core}][${task}][${i}]: worker starts[i] != segments[i].start`)
          }

          // Cross-path parity: worker reconstruction must match main-thread.
          assert.equal(wSegs.length, segs.length,
            `${segKey}[${core}][${task}]: worker/main-thread segment count mismatch`)
          assert.deepEqual([...wStarts], [...starts],
            `${startsKey}[${core}][${task}]: worker/main-thread starts mismatch`)
        }
      }
    }
  })
})
