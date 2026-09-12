import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import { BTF_HTML_REPORT_CSS } from '../src/utils/htmlReport.js'
import {
  STATS_HTML_EXTRA_CSS,
  evidenceRefsFromFindings,
  htmlEvidenceRefsCard,
  htmlFindingCards,
  htmlGlossary,
  htmlHealthBars,
  htmlInvestigateAnomalies,
  htmlKpi,
  htmlRankBars,
  htmlReportVerdict,
  htmlResponseP99Chart,
  htmlSchedulingBalanceChart,
  htmlScopeIdentityCard,
  htmlUtilBarRow,
  htmlUtilSection,
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

  it('evidence refs card from findings', () => {
    const refs = evidenceRefsFromFindings([{
      title: 'Excessive core migration',
      evidence_text: '564 migrations',
      evidence: [{ label: 'burst', time: 1487000 }],
    }], { formatNs: ns => `${(ns / 1e6).toFixed(3)} ms` })
    assert.equal(refs[0].label, 'Excessive core migration')
    assert.match(refs[0].time_text, /ms/)
    const html = htmlEvidenceRefsCard(refs)
    assert.match(html, /Evidence Refs/)
    assert.match(html, /Excessive core migration/)
    assert.equal(htmlEvidenceRefsCard([]), '')
  })

  it('KPI metric classes and verdict use theme tokens', () => {
    assert.match(htmlKpi('Core Utilization range', '1–2%', { kind: 'metric-util' }), /class="kpi metric-util"/)
    assert.match(htmlKpi('Worst response P99', '1 ms', { kind: 'metric-latency' }), /class="kpi metric-latency"/)
    assert.match(htmlKpi('Migration activity', '12', { kind: 'metric-migration' }), /class="kpi metric-migration"/)
    const html = htmlReportVerdict('warn', 'load balance 95%')
    assert.match(html, /class="report-verdict warn"/)
    assert.doesNotMatch(html, /style=/)
    assert.doesNotMatch(html, /#fdf3e3/)
    assert.match(STATS_HTML_EXTRA_CSS, /--data-bar: #0284C7/)
  })

  it('response P99 chart ranks top eight from the same rows', () => {
    const rows = [10, 80, 30, 90, 20, 70, 40, 60, 50, 100]
      .map((ns, i) => ({ task: `T${i + 1}`, p99_ns: ns }))
    const html = htmlResponseP99Chart(rows, { formatP99: ns => `${ns} ns` })
    assert.match(html, /Highest response P99/)
    assert.match(html, /T10/)
    assert.match(html, /100 ns/)
    assert.equal((html.match(/class="rank-bar"/g) || []).length, 8)
    assert.match(html, /width:100\.0%/)
    assert.doesNotMatch(html, /deadline/i)
  })

  it('load balance chart plots every sample and lowest callout', () => {
    const html = htmlSchedulingBalanceChart([
      { time: '1.01 s', score: 99, sigma: 1.1 },
      { time: '2.27 s', score: 58, sigma: 33.0 },
      { time: '3.22 s', score: 13, sigma: 29.9 },
      { time: '3.38 s', score: 39, sigma: 14.8 },
    ])
    assert.match(html, /Load balance over time/)
    assert.equal((html.match(/<circle/g) || []).length, 4)
    assert.match(html, /<strong>13<\/strong>/)
    assert.match(html, /at 3\.22 s/)
    assert.match(html, /1\.01 s · Load balance 99 · Util σ 1\.1%/)
    assert.match(html, /chart-point-low/)
    assert.doesNotMatch(html, /data:image\/svg\+xml/)
    assert.equal(htmlSchedulingBalanceChart([]), '')
  })

  it('task health bars share the quantitative bar color', () => {
    const html = htmlHealthBars([
      { task: 'Worker[1]', score: 32, marks: { execution: 'jitter' } },
      { task: 'Idle[2]', score: 95, marks: {} },
    ])
    assert.doesNotMatch(html, /var\(--danger\)|var\(--warning\)|var\(--success\)/)
    assert.doesNotMatch(html, /background:/)
    assert.match(html, /class="fill" style="width:32%"/)
    assert.match(STATS_HTML_EXTRA_CSS, /\.pct-bar \.fill \{ height: 100%; border-radius: 999px; background: var\(--data-bar\); \}/)
  })

  it('bar rows hover and carry tooltips', () => {
    const health = htmlHealthBars([{ task: 'Worker[1]', score: 32, marks: { execution: 'jitter' } }])
    assert.match(health, /title="Worker\[1\]: score 32\/100 · execution"/)
    const ranked = htmlRankBars([['Worker[1]', 5, '5 ms']])
    assert.match(ranked, /<div class="rank-bar" title="Worker\[1\]: 5 ms">/)
    assert.doesNotMatch(ranked, /class="rank-bar-label" title=/)
    assert.match(STATS_HTML_EXTRA_CSS, /\.pct-bar:hover \.track \{ border-color: var\(--accent\); \}/)
    assert.match(STATS_HTML_EXTRA_CSS, /\.pct-bar:hover \.fill \{ filter: brightness\(1\.08\); \}/)
  })

  it('table rows, heat cells and table tools respond to hover', () => {
    const css = STATS_HTML_EXTRA_CSS
    assert.match(css, /tbody tr:hover td,/)
    assert.match(css, /tbody tr:hover th,/)
    assert.match(css, /\.table-scroll tbody tr:hover td:first-child,/)
    assert.match(css, /\.table-scroll tbody tr:hover th:first-child \{ background: var\(--accent-soft\); \}/)
    // Declared after the stripe / sticky rules it has to win against.
    assert.ok(css.indexOf('tbody tr:nth-child(even) td {') < css.indexOf('tbody tr:hover td,'))
    assert.ok(css.indexOf('.table-scroll tbody tr:nth-child(even) td:first-child {')
      < css.indexOf('.table-scroll tbody tr:hover td:first-child,'))
    // Heat cells outline instead of restyling: the value keeps its heat bin.
    assert.match(css, /\.heat-grid-cell:hover \{ outline: 2px solid var\(--accent\); outline-offset: -2px; \}/)
    assert.match(css, /\.table-search:hover \{ border-color: var\(--accent\); \}/)
    assert.match(css, /\.table-search:focus-visible \{/)
    assert.match(css, /\.table-action:focus-visible \{/)
    assert.match(css, /\.table-check:hover \{ color: var\(--accent\); cursor: pointer; \}/)
    assert.match(css, /thead th\.sortable:hover \{ background: var\(--accent-soft\); \}/)
  })

  it('print keeps table headers instead of hiding every sortable th', () => {
    const printCss = BTF_HTML_REPORT_CSS.split('@media print {')[1].split('\n}')[0]
    assert.doesNotMatch(printCss, /\.sortable \{ display: none/)
    assert.doesNotMatch(printCss, /\.ai-ev-panel-toggle, \.sortable/)
    assert.match(printCss, /\.sortable \{ cursor: default; \}/)
    assert.match(printCss, /\.ai-ev-panel-toggle \{ display: none !important; \}/)
  })

  it('KPI without a status kind gets the accent outline', () => {
    const css = STATS_HTML_EXTRA_CSS
    const base = css.split('.kpi {')[1].split('}')[0]
    const strip = css.split('.kpi::before {')[1].split('}')[0]
    assert.match(base, /border: 1px solid var\(--accent-border\);/)
    assert.match(strip, /background: var\(--accent\);/)
    assert.equal(strip.includes('var(--line-strong)'), false)
    assert.match(css, /\.kpi\.warn \{ border-color: var\(--warn-border\); \}/)
    assert.match(htmlKpi('Total migrations', '18,992'), /<article class="kpi">/)
  })

  it('all report bars share one track geometry', () => {
    const css = STATS_HTML_EXTRA_CSS
    for (const name of ['.util-bar {', '.rank-bar-track {', '.pct-bar .track {']) {
      const rule = css.split(name)[1].split('}')[0]
      assert.match(rule, /height: 12px/, name)
      assert.match(rule, /border-radius: 999px/, name)
      assert.match(rule, /var\(--bar-track-bg\)/, name)
      assert.match(rule, /var\(--bar-track-border\)/, name)
    }
    for (const name of ['.util-bar-fill, .util-row-task .util-bar-fill {',
      '.rank-bar-fill {', '.pct-bar .fill {']) {
      const rule = css.split(name)[1].split('}')[0]
      assert.match(rule, /height: 100%/, name)
      assert.match(rule, /border-radius: 999px/, name)
    }
    const legend = css.split('.heat-legend-bar {')[1].split('}')[0]
    assert.match(legend, /height: 12px/)
    assert.match(legend, /border-radius: 999px/)
    assert.equal(css.includes('height: 8px'), false)
    assert.equal(css.includes('height: 10px'), false)
    assert.equal((css.match(/border-radius: 4px/g) || []).length, 1)
  })

  it('util section places lead markup after the heading', () => {
    const html = htmlUtilSection(
      'Core Utilization (excl. IDLE/TICK)',
      [['Core_0', 72.28], ['Core_1', 0]],
      'core',
      { leadHtml: "<svg class='lb-gauge-svg'></svg>" },
    )
    assert.ok(html.indexOf('lb-gauge-svg') < html.indexOf('util-list'))
    assert.match(html, /title="Core_0: 72\.3%"/)
    assert.match(html, /class="util-bar-fill" style="width:72\.3%"/)
    const empty = htmlUtilSection('Top Tasks by CPU', [], 'task', { leadHtml: '<i>x</i>' })
    assert.match(empty, /<i>x<\/i>/)
    assert.match(empty, /class="empty"/)
    assert.match(htmlUtilBarRow('W', 5, 'task'), /util-row-task/)
    assert.equal((STATS_HTML_EXTRA_CSS.match(/\.util-bar \{/g) || []).length, 1)
  })
})
