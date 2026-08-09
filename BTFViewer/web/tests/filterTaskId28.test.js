import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, it } from 'node:test'

import { parseBtf } from '../src/parser/btfParser.js'
import { packTrace, unpackTrace } from '../src/parser/tracePack.js'
import { decompressBtfBytes } from '../src/utils/btfLoad.js'
import { taskDisplayName, taskMergeKey } from '../src/utils/colors.js'
import {
  applyCorridorTaskFilter,
  buildCorridorInspectorModel,
} from '../src/utils/migrationAnalysis.js'
import { filteredTaskViewTasks } from '../src/utils/taskFilter.js'

const __dirname = dirname(fileURLToPath(import.meta.url))
const TRACE = join(__dirname, '../../../tracedata/example-8cores.btf.gz')

describe('example-8cores filter 28', () => {
  it('finds CS[28] in legend and corridor inspector after pack/unpack', async (t) => {
    if (!existsSync(TRACE)) {
      t.skip('missing example-8cores.btf.gz')
      return
    }
    const text = decompressBtfBytes(new Uint8Array(readFileSync(TRACE)), 'example-8cores.btf.gz')
    const parsed = await parseBtf(text)
    const trace = unpackTrace(packTrace(parsed).payload)

    const mk28 = taskMergeKey('[0/0028]CS')
    assert.equal(taskDisplayName(trace.taskRepr.get(mk28)), 'CS[28]')

    const legendHits = filteredTaskViewTasks(trace, false, null, '28')
    assert.equal(legendHits.length, 1)
    assert.equal(taskDisplayName(trace.taskRepr.get(legendHits[0])), 'CS[28]')

    const model = buildCorridorInspectorModel(trace, null, null, { topPct: 100, timeBins: 8 })
    const filtered = applyCorridorTaskFilter(model, '28')
    assert.equal(filtered.hasData, true)
    assert.ok(filtered.corridors.length > 0)
    assert.ok(filtered.corridors.every(c =>
      c.tasks.length === 1 && c.tasks[0].label === 'CS[28]'))
  })
})
