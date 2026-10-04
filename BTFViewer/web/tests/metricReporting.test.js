import assert from 'node:assert/strict'
import { before, describe, it } from 'node:test'

import { parseBtf } from '../src/parser/btfParser.js'
import { buildTraceHealthResult, metricAvailabilityLines } from '../src/utils/traceHealth.js'
import { htmlMetricDefinitionsCard, htmlTraceHealthCard } from '../src/utils/statsHtmlReport.js'
import { buildEvidencePackage, formatEvidencePackagePreview } from '../src/utils/aiEvidencePackage.js'
import { plotPointEndpoints, plotPointEndpointNotes } from '../src/utils/plotPointEndpoints.js'
import {
  METRIC_DEFINITIONS,
  PERCENTILE_METHOD_NOTE,
  metricDefinitionsFor,
  percentileSampleNote,
} from '../src/utils/latencyMetrics.js'

const TEXT = [
  '#version 2.2.0',
  '#timeScale ns',
  '0,Core_0,0,T,[0/0001]A,0,resume,create pri:1',
  '100,Core_0,0,T,[0/0001]A,0,preempt,',
  '100,Core_0,0,T,[0/0002]B,0,resume,create pri:3',
  '150,Core_0,0,STI,interval_start,0,trigger,5',
  '200,Core_0,0,T,[0/0002]B,0,preempt,',
  '200,Core_0,0,T,[0/0001]A,0,resume,',
  '250,Core_0,0,STI,interval_stop,0,trigger,5',
  '300,Core_0,0,T,[0/0001]A,0,preempt,',
  '300,Core_0,0,T,[0/0002]B,0,resume,',
  '310,Core_0,0,STI,task,0,trigger,suspend [0/0001]A',
  '320,Core_0,0,STI,task,0,trigger,resume [0/0001]A',
  '330,Core_0,0,STI,task,0,trigger,resume [0/0001]A',
  '350,Core_0,0,STI,task,0,trigger,priority_inherit [0/0002]B pri:5',
  '400,Core_0,0,T,[0/0002]B,0,preempt,',
  '420,Core_0,0,STI,task,0,trigger,affinity_set [0/0001]A 0x2',
  '450,Core_0,0,STI,task,0,trigger,priority_disinherit [0/0002]B pri:3',
  '500,Core_1,0,T,[1/0001]A,0,resume,',
  '600,Core_1,0,T,[1/0001]A,0,preempt,',
  '',
].join('\n')

describe('metric reporting: availability, percentiles, endpoints, definitions', () => {
  let health
  before(async () => {
    health = buildTraceHealthResult(await parseBtf(TEXT), 0, 600)
  })

  it('reports per-metric availability with reasons', () => {
    const by = Object.fromEntries(health.metricAvailability.map(a => [a.metric, a]))
    assert.equal(by['Dispatch / Scheduling Latency'].state, 'available')
    assert.equal(by['Mutex / Semaphore / Queue'].state, 'unavailable')
    assert.match(by['Mutex / Semaphore / Queue'].reason, /no mutex/)
    assert.equal(by['Trace Health (TICK)'].state, 'unavailable')
    const lines = metricAvailabilityLines(health)
    assert.equal(lines.length, 2)
    assert.ok(lines.every(l => l.includes(' — ')))
  })

  it('lists availability in the health card', () => {
    const html = htmlTraceHealthCard(health)
    assert.ok(html.includes('Metric availability'))
    assert.ok(html.includes('no TICK events'))
  })

  it('discloses the percentile method for small samples', () => {
    assert.equal(percentileSampleNote([100, 500]), '')
    const note = percentileSampleNote([5, 50, 200])
    assert.ok(note.includes('fewer than 20 samples'))
    assert.ok(note.includes('20–99 samples'))
    assert.ok(note.endsWith(PERCENTILE_METHOD_NOTE))
  })

  it('returns two endpoints for spans', () => {
    assert.deepEqual(plotPointEndpoints('priority', { startNs: 10, stopNs: 20 }), { startNs: 10, stopNs: 20 })
    assert.equal(plotPointEndpoints('exec', { startNs: 10, stopNs: 20 }), null)
    assert.deepEqual(plotPointEndpointNotes('x'), ['x — start', 'x — end'])
  })

  it('adds definitions to the HTML card and evidence package', () => {
    const card = htmlMetricDefinitionsCard()
    for (const [, term] of METRIC_DEFINITIONS) assert.ok(card.includes(term.replace(/&/g, '&amp;')))
    assert.deepEqual(metricDefinitionsFor(['Dispatch p95']).map(d => d.key), ['dispatch', 'percentile'])
    const pkg = buildEvidencePackage({
      question: 'why late?',
      health,
      statistics: [{ name: 'Dispatch p95', value: 10, unit: 'ns', sample_count: 3 }],
    })
    assert.deepEqual(pkg.definitions.map(d => d.key), ['dispatch', 'percentile'])
    assert.deepEqual(new Set(pkg.trace_health.availability.map(a => a.metric)),
      new Set(['Mutex / Semaphore / Queue', 'Trace Health (TICK)']))
    const preview = formatEvidencePackagePreview(pkg)
    assert.ok(preview.includes('Definitions (2):'))
    assert.ok(preview.includes('no TICK events'))
  })
})
