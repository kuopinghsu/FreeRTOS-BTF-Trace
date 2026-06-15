#!/usr/bin/env node
/**
 * Headless BTF trace stats for CI regression.
 *
 * Usage:
 *   node scripts/cli-stats.mjs path/to/trace.btf [--json] [--baseline file.json]
 *
 * Exit codes:
 *   0 — OK (or matches baseline within tolerance)
 *   1 — parse/runtime error
 *   2 — baseline mismatch
 */

import { readFileSync, existsSync } from 'node:fs'
import { resolve } from 'node:path'
import { pathToFileURL } from 'node:url'

const args = process.argv.slice(2)
const jsonOut = args.includes('--json')
const baselineIdx = args.indexOf('--baseline')
const baselinePath = baselineIdx >= 0 ? args[baselineIdx + 1] : null
const fileArg = args.find(a => !a.startsWith('--') && a !== baselinePath)

if (!fileArg) {
  console.error('Usage: cli-stats.mjs <trace.btf> [--json] [--baseline golden.json]')
  process.exit(1)
}

const btfPath = resolve(fileArg)
if (!existsSync(btfPath)) {
  console.error(`File not found: ${btfPath}`)
  process.exit(1)
}

const parserUrl = pathToFileURL(resolve(import.meta.dirname, '../src/parser/btfParser.js')).href
const { parseBtf } = await import(parserUrl)
const tracePackUrl = pathToFileURL(resolve(import.meta.dirname, '../src/parser/tracePack.js')).href
const { finalizeAndEnrich } = await import(tracePackUrl)

const text = readFileSync(btfPath, 'utf8')
const trace = finalizeAndEnrich(await parseBtf(text))

const wcetUrl = pathToFileURL(resolve(import.meta.dirname, '../src/utils/wcetReport.js')).href
const { wcetReportRows } = await import(wcetUrl)

const report = {
  file: btfPath,
  timeScale: trace.timeScale,
  span: trace.timeMax - trace.timeMin,
  tasks: trace.tasks.length,
  segments: trace.segments.length,
  stiEvents: trace.stiEvents.length,
  tickCount: trace.tickHealth?.tickCount ?? 0,
  tickHealth: trace.tickHealth?.health ?? 'unknown',
  tickLargeGaps: trace.tickHealth?.largeGaps?.length ?? 0,
  missedTicksEstimate: trace.tickHealth?.missedTicksEstimate ?? 0,
  migrations: trace.migrations?.length ?? 0,
  migratedTasks: [...(trace.migrationsByMk?.keys() || [])].length,
  wcetTop: wcetReportRows(trace, null, null).slice(0, 5).map(r => ({
    name: r.name, wcetNs: r.wcetNs, bcetNs: r.bcetNs, runs: r.runs,
  })),
}

if (jsonOut || !baselinePath) {
  console.log(JSON.stringify(report, null, 2))
}

if (baselinePath) {
  if (!existsSync(baselinePath)) {
    console.error(`Baseline not found: ${baselinePath}`)
    process.exit(1)
  }
  const base = JSON.parse(readFileSync(baselinePath, 'utf8'))
  const diffs = []
  for (const key of ['tasks', 'segments', 'stiEvents', 'tickCount', 'migrations']) {
    if (base[key] != null && report[key] !== base[key]) {
      diffs.push(`${key}: expected ${base[key]}, got ${report[key]}`)
    }
  }
  if (diffs.length) {
    console.error('Baseline mismatch:\n' + diffs.join('\n'))
    process.exit(2)
  }
  console.error('Baseline OK')
}
