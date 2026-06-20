/**
 * Golden checks for mutex/sem pointer pairing on example-4cores.btf.
 * Usage: node scripts/test-sync-object-analysis.mjs [path/to/trace.btf]
 */
import { readFileSync } from 'fs'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'
import { parseBtf } from '../src/parser/btfParser.js'
import { finalizeAndEnrich } from '../src/parser/tracePack.js'
import { syncObjectStatsRows, syncObjectIssueRows } from '../src/utils/syncObjectAnalysis.js'

const __dirname = dirname(fileURLToPath(import.meta.url))
const defaultBtf = resolve(__dirname, '../../../tracedata/example-4cores.btf')
const btfPath = resolve(process.argv[2] || defaultBtf)

function assert(cond, msg) {
  if (!cond) throw new Error(msg)
}

const text = readFileSync(btfPath, 'utf8')
const trace = finalizeAndEnrich(await parseBtf(text))

assert(trace.hasSyncObjectInstrumentation, 'expected mutex/sem STI instrumentation')
assert(trace.syncObjects.size >= 2, 'expected at least mutex + sem objects')

const mtx = trace.syncObjects.get('mutex:0x80018700')
assert(mtx, 'expected mutex 0x80018700')
assert(mtx.holds.length > 0, 'mutex should have paired holds')
assert(mtx.issues.length === 0, `main mutex should have no issues, got ${mtx.issues.length}`)

const orphans = syncObjectIssueRows(trace).filter(i => i.kind === 'orphan_give')
assert(orphans.length === 0, `expected no orphan gives, got ${orphans.length}`)

const rows = syncObjectStatsRows(trace)
assert(rows.some(r => r.key === 'mutex:0x80018700' && r.status === 'ok'),
  'main mutex row should be OK')

console.log(`ok: sync object analysis (${btfPath})`)
console.log(`  mutex ${mtx.ptr}: ${mtx.holds.length} holds, 0 issues`)
console.log(`  ${trace.syncObjects.size} objects, ${syncObjectIssueRows(trace).length} scoped issues`)
