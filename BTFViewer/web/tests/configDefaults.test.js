import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import {
  CPU_LOAD_ROW_H,
  DEFAULT_MAX_CURSORS,
  FONT_SIZE,
  LABEL_WIDTH,
  MAX_CURSORS,
  RIGHT_PANEL_WIDTH,
  ROW_HEIGHT,
  SHOW_FIND,
  SHOW_MARKS,
  STATS_TABLE_DISPLAY_ROW_CAP,
  UI_FONT_SIZE,
} from '../src/config.js'
import { STATS_TABLE_DISPLAY_ROW_CAP as LOAD_ROW_CAP } from '../src/utils/statsLoad.js'
import { DEFAULT_SETTINGS, normalizeSettings } from '../src/utils/settingsStore.js'
import { DEFAULT_TIMELINE_LAYOUT } from '../src/utils/timelineLayout.js'
import { CPU_LOAD_ROW_H as HELPERS_ROW_H } from '../src/utils/cpuLoadHelpers.js'

describe('config.js is the single source of web defaults', () => {
  it('feeds Settings / localStorage defaults', () => {
    assert.equal(DEFAULT_SETTINGS.labelFontSize, FONT_SIZE)
    assert.equal(DEFAULT_SETTINGS.uiFontSize, UI_FONT_SIZE)
    assert.equal(DEFAULT_SETTINGS.labelWidth, LABEL_WIDTH)
    assert.equal(DEFAULT_SETTINGS.rowHeight, ROW_HEIGHT)
    assert.equal(DEFAULT_SETTINGS.cpuLoadRowH, CPU_LOAD_ROW_H)
    assert.equal(DEFAULT_SETTINGS.maxCursors, DEFAULT_MAX_CURSORS)
    assert.ok(DEFAULT_SETTINGS.maxCursors <= MAX_CURSORS)
    assert.equal(DEFAULT_SETTINGS.showMarks, SHOW_MARKS)
    assert.equal(DEFAULT_SETTINGS.showFind, SHOW_FIND)
  })

  it('feeds timeline layout and CPU-load pane defaults', () => {
    assert.equal(DEFAULT_TIMELINE_LAYOUT.labelFontSize, FONT_SIZE)
    assert.equal(DEFAULT_TIMELINE_LAYOUT.labelW, LABEL_WIDTH)
    assert.equal(DEFAULT_TIMELINE_LAYOUT.rowH, ROW_HEIGHT)
    assert.equal(DEFAULT_TIMELINE_LAYOUT.cpuLoadRowH, CPU_LOAD_ROW_H)
    assert.equal(HELPERS_ROW_H, CPU_LOAD_ROW_H)
  })

  it('keeps Find/Marks panel flags in localStorage settings', () => {
    assert.equal(normalizeSettings(null).showFind, true)
    assert.equal(normalizeSettings(null).showMarks, true)
    assert.equal(normalizeSettings({ showFind: false }).showFind, false)
    assert.equal(normalizeSettings({ showMarks: false }).showMarks, false)
  })

  it('keeps a first-run right-panel width for wrapping AI chips', () => {
    assert.ok(RIGHT_PANEL_WIDTH >= 420)
    assert.ok(RIGHT_PANEL_WIDTH <= 520)
  })

  it('shares the stats table display row cap with desktop', () => {
    assert.equal(STATS_TABLE_DISPLAY_ROW_CAP, 2000)
    assert.equal(LOAD_ROW_CAP, STATS_TABLE_DISPLAY_ROW_CAP)
  })

  it('keeps inspector pane split ratios including fractional flex', () => {
    assert.deepEqual(DEFAULT_SETTINGS.inspectorSplit, [1, 2, 1])
    const frac = normalizeSettings({ inspectorSplit: [0.8, 2.4, 0.8] })
    assert.deepEqual(frac.inspectorSplit, [0.8, 2.4, 0.8])
    const px = normalizeSettings({ inspectorSplit: [240, 480, 240] })
    assert.deepEqual(px.inspectorSplit, [240, 480, 240])
    const bad = normalizeSettings({ inspectorSplit: [1, 2] })
    assert.deepEqual(bad.inspectorSplit, [1, 2, 1])
  })

  it('persists statistics collapse with pins and section order', () => {
    // Step 1.1: factory default is all collapsed; SMP expand+pin is applied
    // via defaultStatsPresentation(trace) on open / Reset, not in DEFAULT_SETTINGS.
    assert.equal(DEFAULT_SETTINGS.statsSectionCollapsed.cores, true)
    assert.equal(DEFAULT_SETTINGS.statsSectionCollapsed.health, true)
    assert.equal(DEFAULT_SETTINGS.statsSectionCollapsed.exec, true)
    const s = normalizeSettings({ statsSectionCollapsed: { exec: false } })
    assert.equal(s.statsSectionCollapsed.exec, false)
    assert.equal(s.statsSectionCollapsed.health, true)
    assert.deepEqual(s.statsPinnedSections, [])
    const expanded = Object.fromEntries(
      Object.keys(DEFAULT_SETTINGS.statsSectionCollapsed).map((k) => [k, false]),
    )
    const allOpen = normalizeSettings({ statsSectionCollapsed: expanded })
    assert.ok(Object.values(allOpen.statsSectionCollapsed).every((v) => v === false))
  })
})
