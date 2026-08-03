import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  LB_GAUGE,
  classifyLoadBalance,
  loadBalanceGaugeImgHtml,
  loadBalanceGaugeSvg,
  needleTipPoint,
  scoreArcPath,
  scoreToNeedleDeg,
  semicirclePath,
} from '../src/utils/loadBalanceGauge.js'

describe('loadBalanceGauge', () => {
  it('maps score 0/50/100 across a 180° semicircle', () => {
    assert.equal(scoreToNeedleDeg(0), 180)
    assert.equal(scoreToNeedleDeg(50), 90)
    assert.equal(scoreToNeedleDeg(100), 0)
  })

  it('classifies red / amber / ok zones', () => {
    assert.equal(classifyLoadBalance(42, 10), 'red')
    assert.equal(classifyLoadBalance(69.9, 5), 'red')
    assert.equal(classifyLoadBalance(70, 35), 'amber')
    assert.equal(classifyLoadBalance(90, 12), 'ok')
  })

  it('keeps needle tip inside the arc hollow', () => {
    for (const score of [0, 25, 50, 75, 100]) {
      const tip = needleTipPoint(score)
      assert.ok(tip.y <= LB_GAUGE.cy + 0.01)
      assert.ok(tip.y >= LB_GAUGE.cy - LB_GAUGE.needleLen - 0.01)
    }
  })

  it('builds semicircle and score arc paths', () => {
    assert.match(semicirclePath(LB_GAUGE.cx, LB_GAUGE.cy, LB_GAUGE.rTrack), /^M /)
    assert.match(scoreArcPath(72), /^M /)
  })

  it('alerts Unbalanced in red zone SVG', () => {
    const svg = loadBalanceGaugeSvg({
      score: 42,
      gini: 0.58,
      stddev: 20,
      zone: 'red',
    })
    assert.match(svg, /Unbalanced/)
    assert.match(svg, /#C62828/)
    assert.doesNotMatch(svg, /σ &gt; 30%/)
  })

  it('shows σ chip in amber zone SVG', () => {
    const svg = loadBalanceGaugeSvg({
      score: 80,
      gini: 0.2,
      stddev: 35.2,
      zone: 'amber',
    })
    assert.match(svg, /σ &gt; 30%/)
    assert.doesNotMatch(svg, /Unbalanced/)
  })

  it('embeds gauge as SVG data-URI img for HTML export', () => {
    const html = loadBalanceGaugeImgHtml({
      score: 82,
      gini: 0.18,
      stddev: 12,
      zone: 'ok',
    }, { width: 280 })
    assert.match(html, /<img /)
    assert.match(html, /src="data:image\/svg\+xml/)
    assert.match(html, /alt="Load Balance Score 82%/)
    assert.doesNotMatch(html, /<svg /)
  })
})
