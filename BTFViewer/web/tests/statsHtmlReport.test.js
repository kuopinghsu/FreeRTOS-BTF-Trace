import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  htmlFindingCards,
  htmlGlossary,
  htmlInvestigateAnomalies,
  htmlScopeIdentityCard,
} from '../src/utils/statsHtmlReport.js'

describe('stats HTML helpers', () => {
  it('glossary avoids misleading terms', () => {
    const html = htmlGlossary({ rangeNote: '<li><strong>Cursor range:</strong> C1–C2</li>' })
    assert.match(html, /Statistics Notes/)
    assert.match(html, /highly uneven/)
    assert.match(html, /does not prove zero system load/)
    assert.doesNotMatch(html, /best metric for user experience/)
    assert.doesNotMatch(html, /0 = overload/)
    assert.match(html, /Off-CPU Time \(Blocking Time\)/)
    assert.match(html, /not a stacked split/)
    assert.equal(html.includes('<li><li>'), false)
    assert.match(html, /Cursor range/)
  })

  it('finding cards include inspect links and no click-Max wording', () => {
    const html = htmlFindingCards([{
      severity: 'warning',
      title: 'Excessive core migration',
      text: 'CS[19] migrated often.',
      impact: 'Cache misses',
      evidence_text: '564 migrations',
      inspect: 'Core Migrations',
      confidence: 'Medium — heuristic threshold',
    }])
    assert.match(html, /finding-card/)
    assert.match(html, /href="#sec-core-migrations"/)
    assert.match(html, /Impact:/)
    assert.doesNotMatch(html, /click Max/)
  })

  it('scope card and investigate tabs are present', () => {
    const scope = htmlScopeIdentityCard({
      filename: 'example.btf.gz',
      scopeType: 'Full trace',
      start: '0 us',
      end: '2.4 s',
      duration: '2.4 s',
      cores: 4,
      filters: 'None',
      timestampMode: 'Trace capture origin (not wall-clock)',
      taskCount: 12,
    })
    assert.match(scope, /Analysis Scope/)
    assert.match(scope, /example\.btf\.gz/)
    const html = htmlInvestigateAnomalies({
      anomaliesTable: '<table></table>',
      worstTable: '<table></table>',
      patternsTable: '<table></table>',
      critPathTable: '<table></table>',
      critNote: '<p>overlap</p>',
    })
    assert.match(html, /Investigate Anomalies/)
    assert.match(html, /data-tab="crit"/)
    assert.match(html, /can overlap/)
  })
})
