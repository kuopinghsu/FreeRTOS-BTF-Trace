import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  ZOOM_PRESET_PERCENTAGES,
  buildZoomPresetOptions,
  matchZoomPresetValue,
} from '../src/utils/zoomPresets.js'

describe('zoomPresets', () => {
  it('matches desktop percentage list and Fit last', () => {
    assert.deepEqual([...ZOOM_PRESET_PERCENTAGES], [1, 2, 5, 10, 25, 50, 75])
    const opts = buildZoomPresetOptions(100, 0.5)
    assert.deepEqual(opts.map(o => o.label), ['1%', '2%', '5%', '10%', '25%', '50%', '75%', 'Fit'])
    assert.equal(opts.at(-1).value, 'fit')
  })

  it('drops presets tighter than the 1:1 floor', () => {
    const opts = buildZoomPresetOptions(100, 8)
    assert.deepEqual(opts.map(o => o.label), ['10%', '25%', '50%', '75%', 'Fit'])
  })

  it('selects Fit near full span and matches 50% within 1%', () => {
    const opts = buildZoomPresetOptions(100, 0.5)
    assert.equal(matchZoomPresetValue(1, opts), 'fit')
    assert.equal(matchZoomPresetValue(0.995, opts), 'fit')
    assert.equal(matchZoomPresetValue(0.5, opts), '50')
    assert.equal(matchZoomPresetValue(0.503, opts), '50')
    assert.equal(matchZoomPresetValue(0.37, opts), '')
    assert.equal(
      matchZoomPresetValue(1.43, opts), 'fit',
      'at or past Fit (span >= full trace) selects Fit so Zoom Out stays grayed')
  })
})
