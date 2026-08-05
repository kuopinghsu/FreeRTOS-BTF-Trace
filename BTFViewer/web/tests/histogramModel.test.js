import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  buildHistogramModel,
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
      ['avg', 'p50', 'p95'],
    )

    const plain = buildHistogramModel(
      [10, 20, 30],
      { scaleMode: 'linear', formatValue: String },
    )
    assert.equal(plain.sigmaBand, null)
    assert.deepEqual(
      plain.referenceLines.map(line => line.label),
      ['avg', 'p50', 'p95'],
    )
  })
})
