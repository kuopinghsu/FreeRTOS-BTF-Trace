import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  isRestorableViewport,
  sanitizeTabFilters,
  snapshotTabFilters,
} from '../src/utils/sessionStore.js'

describe('sessionStore filters', () => {
  it('snapshotTabFilters copies active filter state', () => {
    const snap = snapshotTabFilters({
      taskFilterText: 'spi',
      migratedOnlyFilter: true,
      taskFilterKeys: ['A', 'B'],
      heatmapFilterLabel: 'Core_0',
    })
    assert.deepEqual(snap, {
      taskFilterText: 'spi',
      migratedOnlyFilter: true,
      taskFilterKeys: ['A', 'B'],
      heatmapFilterLabel: 'Core_0',
    })
  })

  it('sanitizeTabFilters drops empty key lists', () => {
    const out = sanitizeTabFilters({
      taskFilterKeys: ['', null],
      taskFilterText: 'x',
    })
    assert.equal(out.taskFilterKeys, null)
    assert.equal(out.taskFilterText, 'x')
  })

  it('sanitizeTabFilters returns null for non-objects', () => {
    assert.equal(sanitizeTabFilters(null), null)
    assert.equal(sanitizeTabFilters('bad'), null)
  })
})

describe('isRestorableViewport', () => {
  const trace = { timeMin: 0, timeMax: 1_000_000 }

  it('rejects placeholder 0..1 viewport', () => {
    assert.equal(isRestorableViewport({
      timeStart: 0,
      timeEnd: 1,
      scrollY: 0,
      scrollX: 0,
      canvasW: 800,
      canvasH: 600,
    }, trace), false)
  })

  it('accepts overlapping zoom window', () => {
    assert.equal(isRestorableViewport({
      timeStart: 100_000,
      timeEnd: 500_000,
      scrollY: 0,
      scrollX: 0,
      canvasW: 800,
      canvasH: 600,
    }, trace), true)
  })
})
