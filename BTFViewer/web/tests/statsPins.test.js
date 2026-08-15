import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  STATS_PINNABLE_SECTIONS,
  defaultSectionCollapsed,
  mergeSectionCollapsed,
  normalizeStatsPins,
  toggleStatsPin,
} from '../src/utils/statsPins.js'

describe('statsPins', () => {
  it('normalizes and dedupes', () => {
    assert.deepEqual(normalizeStatsPins('cores,bogus,tasks,cores'), ['cores', 'tasks'])
    assert.deepEqual(normalizeStatsPins(['tags', 'tags', '']), ['tags'])
    assert.deepEqual(normalizeStatsPins(null), [])
  })

  it('toggles pins', () => {
    assert.deepEqual(toggleStatsPin([], 'cores'), ['cores'])
    assert.deepEqual(toggleStatsPin(['cores', 'tasks'], 'cores'), ['tasks'])
    assert.deepEqual(toggleStatsPin(['cores'], 'nope'), ['cores'])
  })

  it('catalogue includes common sections', () => {
    for (const sid of ['cores', 'tasks', 'tags', 'migrations', 'affinity',
      'period', 'task_core', 'wait_owner', 'task_health',
      'response', 'crit_path', 'jitter', 'distrib', 'patterns',
      'preempt_matrix', 'mutex_block', 'core_time']) {
      assert.ok(STATS_PINNABLE_SECTIONS.includes(sid), sid)
    }
    assert.deepEqual(STATS_PINNABLE_SECTIONS.slice(0, 9), [
      'cores', 'health', 'core_breakdown', 'concurrency',
      'switch_overhead', 'tasks', 'migrations', 'core_pairs', 'affinity',
    ])
  })

  it('defaults Core utilisation and Trace Health expanded', () => {
    const flags = defaultSectionCollapsed()
    assert.equal(flags.cores, false)
    assert.equal(flags.health, false)
    assert.equal(flags.exec, true)
    assert.equal(mergeSectionCollapsed({ exec: false }).exec, false)
    assert.equal(mergeSectionCollapsed({ exec: false }).health, false)
  })
})
