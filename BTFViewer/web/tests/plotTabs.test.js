import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  MIG_PLOT_TABS,
  PAIR_PLOT_TABS,
  TAG_PLOT_TABS,
  plotTabsForKind,
  resolvePlotTabSwitch,
} from '../src/utils/plotTabs.js'

describe('plotTabsForKind', () => {
  it('maps metric kinds to their tab sets', () => {
    assert.equal(plotTabsForKind('mig_dwell'), MIG_PLOT_TABS)
    assert.equal(plotTabsForKind('mig_gap'), MIG_PLOT_TABS)
    assert.equal(plotTabsForKind('pair_rate'), PAIR_PLOT_TABS)
    assert.equal(plotTabsForKind('tag_interval'), TAG_PLOT_TABS)
  })

  it('returns null for metrics without variants', () => {
    assert.equal(plotTabsForKind('exec'), null)
    assert.equal(plotTabsForKind(null), null)
  })
})

describe('resolvePlotTabSwitch', () => {
  it('returns the next descriptor and keeps sibling fields', () => {
    const open = { kind: 'pair_gap', fromCore: 'Core_5', toCore: 'Core_7' }
    assert.deepEqual(resolvePlotTabSwitch(open, 'pair_rate'),
      { kind: 'pair_rate', fromCore: 'Core_5', toCore: 'Core_7' })
  })

  it('leaves the original descriptor untouched', () => {
    const open = { kind: 'mig_dwell', mk: 'T:1' }
    resolvePlotTabSwitch(open, 'mig_gap')
    assert.equal(open.kind, 'mig_dwell')
  })

  it('rejects the tab already on screen', () => {
    assert.equal(resolvePlotTabSwitch({ kind: 'mig_dwell', mk: 'T:1' }, 'mig_dwell'), null)
  })

  it('rejects a kind that is not a tab of the open metric', () => {
    const open = { kind: 'mig_dwell', mk: 'T:1' }
    assert.equal(resolvePlotTabSwitch(open, 'pair_gap'), null)
    assert.equal(resolvePlotTabSwitch(open, 'exec'), null)
    assert.equal(resolvePlotTabSwitch(null, 'mig_rate'), null)
  })
})
