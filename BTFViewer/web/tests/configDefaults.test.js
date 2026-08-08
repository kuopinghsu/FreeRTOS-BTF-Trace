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
  UI_FONT_SIZE,
} from '../src/config.js'
import { DEFAULT_SETTINGS } from '../src/utils/settingsStore.js'
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
  })

  it('feeds timeline layout and CPU-load pane defaults', () => {
    assert.equal(DEFAULT_TIMELINE_LAYOUT.labelFontSize, FONT_SIZE)
    assert.equal(DEFAULT_TIMELINE_LAYOUT.labelW, LABEL_WIDTH)
    assert.equal(DEFAULT_TIMELINE_LAYOUT.rowH, ROW_HEIGHT)
    assert.equal(DEFAULT_TIMELINE_LAYOUT.cpuLoadRowH, CPU_LOAD_ROW_H)
    assert.equal(HELPERS_ROW_H, CPU_LOAD_ROW_H)
  })

  it('keeps a first-run right-panel width', () => {
    assert.ok(RIGHT_PANEL_WIDTH >= 180)
    assert.ok(RIGHT_PANEL_WIDTH <= 520)
  })
})
