import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, it } from 'node:test'

import { parseBtf } from '../src/parser/btfParser.js'
import { decompressBtfBytes } from '../src/utils/btfLoad.js'
import { syncObjectStatsRows } from '../src/utils/syncObjectAnalysis.js'

const __dirname = dirname(fileURLToPath(import.meta.url))
const FIXTURE = join(__dirname, '../../tests/fixtures/example-4cores-sync-golden.json')
const TRACE = join(__dirname, '../../../tracedata/example-4cores.btf.gz')

describe('parser golden vectors', () => {
  it('sync object stats match Python fixture for example-4cores.btf.gz', async () => {
    assert.ok(existsSync(TRACE), `missing trace fixture: ${TRACE}`)
    assert.ok(existsSync(FIXTURE), `missing golden fixture: ${FIXTURE}`)

    const expected = JSON.parse(readFileSync(FIXTURE, 'utf8'))
    const text = decompressBtfBytes(new Uint8Array(readFileSync(TRACE)), 'example-4cores.btf.gz')
    const trace = await parseBtf(text)

    assert.equal(trace.hasSyncObjectInstrumentation, expected.hasSyncObjectInstrumentation)
    assert.equal(trace.syncObjects.size, expected.syncObjectCount)
    assert.equal(trace.syncIssues.length, expected.syncIssueCount)

    const rows = syncObjectStatsRows(trace, null, null)
    const actual = rows
      .map(r => ({
        kind: r.kind,
        ptr: r.ptr,
        holds: r.holdCount,
        issues: r.issueCount,
        status: r.status,
      }))
      .sort((a, b) => a.kind.localeCompare(b.kind) || a.ptr.localeCompare(b.ptr))

    assert.deepEqual(actual, expected.objects)
  })
})
