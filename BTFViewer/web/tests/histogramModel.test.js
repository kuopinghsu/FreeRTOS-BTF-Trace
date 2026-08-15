import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  buildHistogramModel,
  histogramBarTooltip,
  summarizeNumericSamples,
} from '../src/utils/histogramModel.js'

describe('histogram variability overlays', () => {
  it('calculates population standard deviation', () => {
    const summary = summarizeNumericSamples([10, 20, 30])
    assert.ok(summary)
    assert.ok(Math.abs(summary.stddev - Math.sqrt(200 / 3)) < 1e-9)
  })

  it('adds the sigma band only when requested', () => {
    const options = {
      scaleMode: 'linear',
      formatValue: String,
      showVariability: true,
    }
    const model = buildHistogramModel([10, 20, 30], options)
    assert.ok(model.sigmaBand)
    assert.ok(model.sigmaBand.width > 0)
    // Min/Max are already evident from the axis extents — no marker lines.
    assert.deepEqual(
      model.referenceLines.map(line => line.label),
      ['avg', 'p5', 'p50', 'p95'],
    )

    const plain = buildHistogramModel(
      [10, 20, 30],
      { scaleMode: 'linear', formatValue: String },
    )
    assert.equal(plain.sigmaBand, null)
    assert.deepEqual(
      plain.referenceLines.map(line => line.label),
      ['avg', 'p5', 'p50', 'p95'],
    )
  })
})

describe('histogram bar hover tips', () => {
  it('puts count and bin edges on each bar', () => {
    const model = buildHistogramModel([10, 20, 30], {
      scaleMode: 'linear',
      formatValue: String,
    })
    assert.equal(model.sampleCount, 3)
    assert.ok(model.bars.length > 0)
    const populated = model.bars.find(bar => bar.count > 0)
    assert.ok(populated)
    assert.equal(typeof populated.edgeLo, 'number')
    assert.equal(typeof populated.edgeHi, 'number')
    const tip = histogramBarTooltip(populated, model.sampleCount, String)
    assert.ok(tip.line1.includes('–'))
    assert.match(tip.line2, / of 3 \(/)
  })

  it('labels overflow and underflow buckets', () => {
    assert.deepEqual(
      histogramBarTooltip({ kind: 'underflow', count: 1 }, 10, String),
      { line1: '< p5', line2: '1 of 10 (10%)' },
    )
    assert.deepEqual(
      histogramBarTooltip({ kind: 'overflow', count: 2 }, 10, String),
      { line1: '> p95', line2: '2 of 10 (20%)' },
    )
  })
})
