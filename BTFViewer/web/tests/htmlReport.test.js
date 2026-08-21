import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  HTML_REPORT_TOC_SCRIPT,
  htmlApplyCollapsibleToc,
  htmlSectionSlug,
} from '../src/utils/htmlReport.js'
import { STATS_TOC_GROUPS } from '../src/utils/statsHtmlReport.js'

describe('htmlReport TOC', () => {
  it('statistics export TOC includes expand / collapse all', () => {
    const body = [
      '<!--TOC-->',
      '<section class="report-card analysis-findings"><h2>Analysis Findings</h2><p>x</p></section>',
      '<section class="report-card notes"><h2>Statistics Notes</h2><p>y</p></section>',
      '<section class="report-card"><h2>Core Migrations</h2><p>z</p></section>',
      HTML_REPORT_TOC_SCRIPT,
    ].join('\n')
    const html = htmlApplyCollapsibleToc(body, [
      'Analysis Findings',
      'Statistics Notes',
      'Core Utilisation (excl. IDLE/TICK)',
      'Top Tasks by CPU (excl. IDLE/TICK)',
      'Trace Health (TICK)',
    ])
    assert.match(html, /Expand all/)
    assert.match(html, /Collapse all/)
    assert.match(html, /data-toc="expand"/)
    assert.match(html, /data-toc="collapse"/)
    assert.match(html, /setAllOpen/)
    assert.match(html, new RegExp(`id="sec-${htmlSectionSlug('Analysis Findings')}" open`))
    assert.match(html, /Core Migrations/)
    assert.doesNotMatch(html, new RegExp(`id="sec-${htmlSectionSlug('Core Migrations')}" open`))
  })

  it('groups TOC entries and uses stable slugs', () => {
    const body = [
      '<!--TOC-->',
      '<section class="report-card"><h2>Analysis Scope</h2><p>s</p></section>',
      '<section class="report-card analysis-findings"><h2>Analysis Findings</h2><p>x</p></section>',
      '<section class="report-card"><h2>Core Migrations</h2><p>z</p></section>',
      HTML_REPORT_TOC_SCRIPT,
    ].join('\n')
    const html = htmlApplyCollapsibleToc(body, ['Analysis Findings'], STATS_TOC_GROUPS)
    assert.match(html, /Overview and Findings/)
    assert.match(html, /Migrations and Core Affinity/)
    assert.match(html, /toc-groups/)
    assert.match(html, /id="sec-analysis-findings" open/)
    assert.match(html, /href="#sec-core-migrations"/)
  })
})
