import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  STATS_CATEGORY_BADGE_COLORS,
  STATS_PINNABLE_SECTIONS,
  STATS_SECTION_CATEGORIES,
  STATS_SECTION_CATEGORY,
  defaultSectionCollapsed,
  defaultStatsPresentation,
  mergeSectionCollapsed,
  normalizeStatsPins,
  statsCategoryBadgeColors,
  statsTraceIsSmpActive,
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

  it('catalogue is OVERVIEW-first with categories', () => {
    for (const sid of ['cores', 'tasks', 'tags', 'migrations', 'affinity',
      'period', 'task_core', 'wait_owner', 'task_health',
      'response', 'crit_path', 'jitter', 'distrib', 'patterns',
      'preempt_matrix', 'mutex_block', 'core_time']) {
      assert.ok(STATS_PINNABLE_SECTIONS.includes(sid), sid)
      assert.ok(STATS_SECTION_CATEGORY[sid], sid)
    }
    assert.deepEqual(STATS_PINNABLE_SECTIONS.slice(0, 9), [
      'cores', 'health', 'task_health',
      'anomalies', 'worst', 'patterns',
      'response', 'exec', 'dispatch',
    ])
    assert.deepEqual([...STATS_SECTION_CATEGORIES], [
      'OVERVIEW', 'TRIAGE', 'TIMING', 'SCHED', 'SYNC', 'DETAIL',
    ])
    assert.equal(STATS_SECTION_CATEGORY.cores, 'OVERVIEW')
    assert.equal(STATS_SECTION_CATEGORY.anomalies, 'TRIAGE')
    assert.equal(STATS_SECTION_CATEGORY.response, 'TIMING')
    assert.equal(STATS_SECTION_CATEGORY.migrations, 'SCHED')
    assert.equal(STATS_SECTION_CATEGORY.sync, 'SYNC')
    assert.equal(STATS_SECTION_CATEGORY.tasks, 'DETAIL')
  })

  it('factory defaults are all collapsed', () => {
    const flags = defaultSectionCollapsed()
    assert.equal(flags.cores, true)
    assert.equal(flags.health, true)
    assert.equal(flags.exec, true)
    assert.ok(Object.values(flags).every(Boolean))
    assert.equal(mergeSectionCollapsed({ exec: false }).exec, false)
    assert.equal(mergeSectionCollapsed({ exec: false }).health, true)
  })

  it('SMP-active presentation pins Core Utilisation only', () => {
    const uni = {
      coreNames: ['Core_0', 'Core_1', 'Core_2'],
      coreUtilPct: { Core_0: 40, Core_1: 0, Core_2: 0 },
    }
    assert.equal(statsTraceIsSmpActive(uni), false)
    const { pins: p0, collapsed: c0 } = defaultStatsPresentation(uni)
    assert.deepEqual(p0, [])
    assert.equal(c0.cores, true)

    const smp = {
      coreNames: ['Core_0', 'Core_1'],
      coreUtilPct: { Core_0: 40, Core_1: 12 },
    }
    assert.equal(statsTraceIsSmpActive(smp), true)
    const { pins, collapsed } = defaultStatsPresentation(smp)
    assert.deepEqual(pins, ['cores'])
    assert.equal(collapsed.cores, false)
    assert.ok(Object.entries(collapsed).every(([sid, v]) => sid === 'cores' || v === true))
  })

  it('category badge palette covers all categories with soft tints', () => {
    assert.deepEqual(
      Object.keys(STATS_CATEGORY_BADGE_COLORS).sort(),
      [...STATS_SECTION_CATEGORIES].sort(),
    )
    for (const cat of STATS_SECTION_CATEGORIES) {
      for (const dark of [true, false]) {
        const { bg, fg, border } = statsCategoryBadgeColors(cat, dark)
        assert.match(bg, /^#[0-9A-Fa-f]{6}$/)
        assert.match(fg, /^#[0-9A-Fa-f]{6}$/)
        assert.match(border, /^#[0-9A-Fa-f]{6}$/)
        assert.notEqual(bg.toUpperCase(), fg.toUpperCase())
      }
    }
    assert.deepEqual(statsCategoryBadgeColors('TRIAGE', false), {
      bg: '#F7EDD7', fg: '#8A641F', border: '#DFC68E',
    })
    assert.deepEqual(statsCategoryBadgeColors('TIMING', true), {
      bg: '#243449', fg: '#A9C5E8', border: '#47658A',
    })
  })
})
