import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  buildWorkflowAnalysisFindings,
  formatAnalysisFindingsText,
  renderWorkflowAnalysisHtml,
} from '../src/utils/workflowAnalysis.js'

describe('buildWorkflowAnalysisFindings', () => {
  it('flags load imbalance and thrashing', () => {
    const findings = buildWorkflowAnalysisFindings({
      coreRows: [
        { core: 'Core_0', pct: 80 },
        { core: 'Core_1', pct: 10 },
        { core: 'Core_2', pct: 5 },
        { core: 'Core_3', pct: 5 },
      ],
      execRows: [
        { name: 'Worker', cpuPct: 40, max: '10us', runs: 100 },
      ],
      migRows: [
        {
          name: 'ThrashTask',
          migrations: 25,
          pingPong: 5,
          ratePerS: 2.5,
          migrRate: '2.5/s',
          avgDwell: '50us',
          avgDwellTu: 50,
          primaryPct: 40,
          coreCount: 2,
        },
      ],
      pairRows: [
        {
          fromCore: 'Core_0',
          toCore: 'Core_1',
          count: 20,
          bounces: 10,
          bouncePct: 50,
          avgGapNs: 1000,
        },
      ],
      timeScale: 'us',
    })
    const titles = findings.map(f => f.title)
    assert.ok(titles.includes('Load imbalance across cores'))
    assert.ok(titles.includes('Excessive bouncing / core thrashing'))
    assert.ok(titles.includes('Hot core-pair migration traffic'))
  })

  it('warns on low load-balance score even when σ < 30%', () => {
    const findings = buildWorkflowAnalysisFindings({
      coreRows: [
        { pct: 55 }, { pct: 40 }, { pct: 30 }, { pct: 20 },
        { pct: 15 }, { pct: 10 }, { pct: 5 }, { pct: 2 },
      ],
    })
    const load = findings.find(f => /balance|imbalance/i.test(f.title))
    assert.ok(load)
    assert.equal(load.severity, 'warning')
    assert.equal(load.title, 'Load imbalance across cores')
    assert.doesNotMatch(load.text, /reasonably balanced/)
  })

  it('flags L/M/H priority pattern', () => {
    const findings = buildWorkflowAnalysisFindings({
      coreRows: [{ pct: 50 }, { pct: 50 }],
      priorityRows: [{ label: 'LowTask', pattern: 'L/M/H pattern' }],
    })
    const inv = findings.find(f => f.title.includes('Priority inversion'))
    assert.ok(inv)
    assert.match(inv.text, /LowTask/)
  })

  it('renders analysis findings HTML card without WORKFLOWS refs', () => {
    const html = renderWorkflowAnalysisHtml([
      {
        severity: 'warning',
        title: 'Load imbalance across cores',
        text: 'σ high',
      },
    ], ' (scoped)')
    assert.match(html, /Analysis Findings/)
    assert.match(html, /analysis-findings/)
    assert.match(html, /sev-warning/)
    assert.doesNotMatch(html, /WORKFLOWS/)
  })

  it('formats findings as plain text', () => {
    const text = formatAnalysisFindingsText([
      { severity: 'warning', title: 'Load imbalance', text: 'σ high' },
    ], ' (scoped)')
    assert.match(text, /Analysis Findings \(scoped\)/)
    assert.match(text, /\[WARNING\] Load imbalance/)
    assert.match(text, /σ high/)
  })
})
