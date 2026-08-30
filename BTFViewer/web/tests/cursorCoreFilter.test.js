import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { describe, it } from 'node:test'
import { fileURLToPath } from 'node:url'

import { parseBtf } from '../src/parser/btfParser.js'
import { finalizeAndEnrich } from '../src/parser/tracePack.js'
import { decompressBtfBytes } from '../src/utils/btfLoad.js'
import { tasksAtTime, cursorComparisonRows } from '../src/utils/cursorAnalysis.js'
import { filteredTaskViewTasks, taskCoreSets, taskPassesRowFilter } from '../src/utils/taskFilter.js'
import { buildRowLayout } from '../src/renderer/TimelineRenderer.js'
import { taskMergeKey } from '../src/utils/colors.js'

const TRACE_PATH = fileURLToPath(
  new URL('../../demos/demo_8cores/demo_8cores.btf.gz', import.meta.url),
)

async function loadTrace() {
  const bytes = new Uint8Array(readFileSync(TRACE_PATH))
  const text = decompressBtfBytes(bytes, 'demo_8cores.btf.gz')
  return finalizeAndEnrich(await parseBtf(text))
}

/** Sample the trace span and return the timestamp with the most concurrent tasks. */
function busiestNs(trace) {
  let lo = Infinity
  let hi = -Infinity
  for (const segs of trace.segByMergeKey.values()) {
    if (!segs.length) continue
    lo = Math.min(lo, segs[0].start)
    hi = Math.max(hi, segs[segs.length - 1].end)
  }
  let best = lo
  let bestCount = -1
  const SAMPLES = 40
  for (let i = 1; i < SAMPLES; i++) {
    const ns = Math.floor(lo + ((hi - lo) * i) / SAMPLES)
    const r = tasksAtTime(trace, ns)
    const n = r === '—' ? 0 : r.split(', ').length
    if (n > bestCount) { bestCount = n; best = ns }
  }
  return best
}

describe('cursor Core Filter — Task at cursor', () => {
  it('narrows the task list to the selected cores and is a subset of the full list', async () => {
    const trace = await loadTrace()
    assert.ok(trace.coreNames.length > 1, 'demo_8cores should be multi-core')
    const ns = busiestNs(trace)

    const full = tasksAtTime(trace, ns)
    const fullSet = new Set(full.split(', '))
    assert.ok(fullSet.size >= 2, 'expected several concurrent tasks at the busiest instant')

    // Filtering to one core yields a strict-or-equal subset.
    const one = tasksAtTime(trace, ns, [trace.coreNames[0]])
    if (one !== '—') {
      for (const t of one.split(', ')) {
        assert.ok(fullSet.has(t), `${t} from single-core filter must appear in the full list`)
      }
    }

    // The union across every core reproduces the unfiltered list.
    const union = new Set()
    for (const c of trace.coreNames) {
      const r = tasksAtTime(trace, ns, [c])
      if (r !== '—') r.split(', ').forEach(t => union.add(t))
    }
    assert.deepEqual([...union].sort(), [...fullSet].sort())
  })

  it('treats an empty / full core selection as no filter', async () => {
    const trace = await loadTrace()
    const ns = busiestNs(trace)
    assert.equal(tasksAtTime(trace, ns, null), tasksAtTime(trace, ns))
    assert.equal(tasksAtTime(trace, ns, []), tasksAtTime(trace, ns))
    assert.equal(tasksAtTime(trace, ns, [...trace.coreNames]), tasksAtTime(trace, ns))
  })

  it('cursorComparisonRows forwards the core filter to the Task column', async () => {
    const trace = await loadTrace()
    const ns = busiestNs(trace)
    const cursors = [ns, null, null, null]
    const unfiltered = cursorComparisonRows(trace, cursors, trace.timeScale)
    const filtered = cursorComparisonRows(trace, cursors, trace.timeScale, [trace.coreNames[0]])
    assert.equal(unfiltered.length, 1)
    assert.equal(filtered.length, 1)
    assert.equal(filtered[0].task, tasksAtTime(trace, ns, [trace.coreNames[0]]))
    // Same cursor, so time / delta are unchanged by the core filter.
    assert.equal(filtered[0].time, unfiltered[0].time)
    assert.equal(filtered[0].delta, unfiltered[0].delta)
  })
})

describe('Core Filter — task-view rows', () => {
  it('hides task rows that never run on a selected core', async () => {
    const trace = await loadTrace()
    assert.ok(trace.coreNames.length > 2)

    const all = filteredTaskViewTasks(trace, false, null, '', null)
    assert.ok(all.length > 0)

    const oneCore = trace.coreNames[0]
    const oneSet = new Set([oneCore])
    const filtered = filteredTaskViewTasks(trace, false, null, '', [oneCore])

    // strict subset, and every survivor genuinely touches that core
    assert.ok(filtered.length < all.length, 'some rows should drop on a 1-core filter')
    for (const mk of filtered) {
      assert.ok(all.includes(mk))
      const cores = taskCoreSets(trace).get(mk)
      assert.ok(cores && [...cores].some(c => oneSet.has(c)),
        `${mk} kept but has no segment on ${oneCore}`)
    }
    // a task confined to another core must be gone
    const otherOnly = all.find(mk => {
      const c = taskCoreSets(trace).get(mk)
      return c && !c.has(oneCore)
    })
    assert.ok(otherOnly, 'demo should have a core-local task')
    assert.equal(filtered.includes(otherOnly), false)

    // union across every core reproduces the unfiltered set
    const union = new Set()
    for (const c of trace.coreNames) {
      for (const mk of filteredTaskViewTasks(trace, false, null, '', [c])) union.add(mk)
    }
    assert.deepEqual([...union].sort(), [...all].sort())
  })

  it('full / empty selection is a no-op; buildRowLayout drops the same rows', async () => {
    const trace = await loadTrace()
    const oneCore = trace.coreNames[0]

    assert.equal(
      taskPassesRowFilter(trace, trace.tasks[0], false, null, '', null),
      taskPassesRowFilter(trace, trace.tasks[0], false, null, '', [...trace.coreNames]),
    )

    const base = buildRowLayout(trace, 'task', new Set(), 0, false).rows
      .filter(r => r.type === 'task')
    const narrowed = buildRowLayout(trace, 'task', new Set(), 0, false, new Set(), false, null, '', [oneCore]).rows
      .filter(r => r.type === 'task')
    assert.ok(narrowed.length < base.length)
    const baseKeys = new Set(base.map(r => r.key))
    for (const r of narrowed) assert.ok(baseKeys.has(r.key))
  })
})
