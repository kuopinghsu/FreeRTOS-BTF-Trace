import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  SESSION_PORTABLE_VERSION,
  applyPortableSession,
  buildPortableSession,
  parsePortableSession,
  sessionCursorsSlotCount,
} from '../src/utils/sessionPortable.js'

describe('portable session', () => {
  it('buildPortableSession captures timeline options subset', () => {
    const payload = buildPortableSession({
      traceName: 'demo.btf',
      cursors: [100, null, 200],
      marks: [{ id: 1, ns: 50, label: 'a', type: 'bookmark' }],
      markNextId: 2,
      timelineViewport: { timeStart: 0, timeEnd: 1000, scrollY: 0, scrollX: 0, canvasW: 800, canvasH: 600 },
      timelineOptions: {
        viewMode: 'core',
        orientation: 'v',
        showGrid: true,
        showSti: false,
        showCpuLoad: true,
        darkMode: true,
        extraField: true,
      },
      tabFilters: { taskFilterText: 'idle', migratedOnlyFilter: false },
      findQuery: 'spi',
      findMode: 'exact',
      pinnedHighlightKey: 'T1',
    })
    assert.equal(payload.version, SESSION_PORTABLE_VERSION)
    assert.equal(payload.traceName, 'demo.btf')
    assert.equal(payload.timelineOptions.viewMode, 'core')
    assert.equal(payload.timelineOptions.extraField, undefined)
    assert.equal(payload.findQuery, 'spi')
  })

  it('parsePortableSession rejects unsupported version', () => {
    assert.throws(
      () => parsePortableSession(JSON.stringify({ version: 99 })),
      /Unsupported session version/,
    )
  })

  it('sessionCursorsSlotCount respects MAX_CURSORS', () => {
    const data = { cursors: [1, 2, 3, 4, 5, 6, 7, 8, 9] }
    assert.equal(sessionCursorsSlotCount(data, 4), 8)
    assert.equal(sessionCursorsSlotCount({ cursors: [null, null] }, 4), 4)
  })

  it('applyPortableSession sanitizes marks and filters', () => {
    const tab = {
      cursors: [],
      marks: [],
      markNextId: 1,
      timelineViewport: {},
      findQuery: '',
      findMode: 'contains',
      pinnedHighlightKey: null,
      taskFilterText: '',
      migratedOnlyFilter: false,
      taskFilterKeys: null,
      heatmapFilterLabel: null,
    }
    const timelineOptions = {
      highlightKey: null,
      lockedTaskKey: null,
      taskFilterText: '',
      migratedOnlyFilter: false,
      taskFilterKeys: null,
      heatmapFilterLabel: null,
    }
    applyPortableSession(tab, {
      version: SESSION_PORTABLE_VERSION,
      marks: [
        { id: 3, ns: 42, label: 'ok', type: 'bookmark' },
        { id: 'x', ns: 1, label: 'bad' },
      ],
      findMode: 'regex',
      findQuery: 'abc',
      timelineOptions: { viewMode: 'task', darkMode: true },
      tabFilters: { taskFilterText: 'idle', taskFilterKeys: ['T1', ''] },
      pinnedHighlightKey: 'T1',
    }, timelineOptions)

    assert.equal(tab.marks.length, 1)
    assert.equal(tab.marks[0].ns, 42)
    assert.equal(tab.findMode, 'regex')
    assert.equal(tab.taskFilterText, 'idle')
    assert.equal(tab.taskFilterKeys, null)
    assert.equal(tab.pinnedHighlightKey, 'T1')
    assert.equal(timelineOptions.highlightKey, 'T1')
    assert.equal(timelineOptions.lockedTaskKey, 'T1')
  })

  it('restores lockedTaskKey from a segment-click highlight', () => {
    const tab = {
      cursors: [],
      marks: [],
      markNextId: 1,
      timelineViewport: {},
      findQuery: '',
      findMode: 'contains',
      pinnedHighlightKey: null,
      highlightSegment: { task: 'CS[18]', start: 10, end: 20, core: 'Core_0' },
      taskFilterText: '',
      migratedOnlyFilter: false,
      taskFilterKeys: null,
      heatmapFilterLabel: null,
    }
    const timelineOptions = {
      highlightKey: null,
      lockedTaskKey: null,
    }
    applyPortableSession(tab, {
      version: SESSION_PORTABLE_VERSION,
      timelineOptions: { viewMode: 'task', darkMode: true },
      pinnedHighlightKey: null,
    }, timelineOptions)
    assert.ok(timelineOptions.lockedTaskKey)
    assert.equal(timelineOptions.lockedTaskKey, timelineOptions.highlightKey)
    assert.match(String(timelineOptions.lockedTaskKey), /CS/)
  })
})
