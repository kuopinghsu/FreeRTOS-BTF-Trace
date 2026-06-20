/**
 * Golden checks for priority inheritance parsing on example-4cores.btf.
 * Usage: node scripts/test-priority-analysis.mjs [path/to/trace.btf]
 */
import { readFileSync } from 'fs'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'
import { parseBtf } from '../src/parser/btfParser.js'
import { finalizeAndEnrich } from '../src/parser/tracePack.js'
import { priorityEpisodePlotPoints, priorityStatsRows } from '../src/utils/priorityAnalysis.js'
import { taskDisplayName, taskReprGet } from '../src/utils/colors.js'

const __dirname = dirname(fileURLToPath(import.meta.url))
const defaultBtf = resolve(__dirname, '../../../tracedata/example-4cores.btf')
const btfPath = resolve(process.argv[2] || defaultBtf)

function findMkByDisplay(trace, display) {
  for (const [mk, repr] of trace.taskRepr) {
    if (taskDisplayName(repr) === display) return mk
  }
  return null
}

function assert(cond, msg) {
  if (!cond) throw new Error(msg)
}

const text = readFileSync(btfPath, 'utf8')
const trace = finalizeAndEnrich(await parseBtf(text))

assert(trace.hasPriorityInstrumentation, 'expected priority instrumentation in trace')

const ilMk = findMkByDisplay(trace, 'IL[150]')
assert(ilMk, 'IL[150] merge key not found')
const ilEps = trace.priorityEpisodesByMk.get(ilMk) || []
assert(ilEps.length === 1, `IL[150] expected 1 episode, got ${ilEps.length}`)
const ilEp = ilEps[0]
assert(ilEp.startNs === 703266, `IL start expected 703266, got ${ilEp.startNs}`)
assert(ilEp.stopNs === 707222, `IL stop expected 707222, got ${ilEp.stopNs}`)
assert(ilEp.basePri === 2 && ilEp.peakPri === 4, 'IL base/peak priority')
assert(ilEp.inherited === true, 'IL episode should be mutex inherit')
assert(ilEp.inversionSuspect === true, 'IL episode should be inversion suspect')

const psMk = findMkByDisplay(trace, 'PS[128]')
assert(psMk, 'PS[128] merge key not found')
const psEps = trace.priorityEpisodesByMk.get(psMk) || []
assert(psEps.length >= 1, 'PS[128] expected at least one boost episode')

const rows = priorityStatsRows(trace)
assert(rows.some(r => r.label === 'IL[150]'), 'stats rows should include IL[150]')
const plotPts = priorityEpisodePlotPoints(trace, ilMk)
assert(plotPts.length === 1 && plotPts[0].payload.inversionSuspect, 'IL plot point')

console.log(`ok: priority analysis (${btfPath})`)
console.log(`  IL[150]: ${ilEp.startNs}–${ilEp.stopNs} us, pri ${ilEp.basePri}→${ilEp.peakPri}`)
