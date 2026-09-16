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
    assert.equal(payload.statsSectionCollapsed, null)
  })

  it('buildPortableSession copies statsSectionCollapsed', () => {
    const payload = buildPortableSession({
      traceName: 'demo.btf',
      statsSectionCollapsed: { exec: true, cores: false },
    })
    assert.deepEqual(payload.statsSectionCollapsed, { exec: true, cores: false })
  })

  it('parsePortableSession rejects unsupported version', () => {
    assert.throws(
      () => parsePortableSession(JSON.stringify({ version: 99 })),
      /Unsupported session version/,
    )
  })

  it('parsePortableSession accepts legacy v1/v2 and current v3', () => {
    for (const version of [1, 2, SESSION_PORTABLE_VERSION]) {
      const data = parsePortableSession(JSON.stringify({ version }))
      assert.equal(data.version, version)
    }
  })

  it('buildPortableSession no longer emits compareScopeToCursors', () => {
    const payload = buildPortableSession({ traceName: 'demo.btf' })
    assert.equal(payload.version, 3)
    assert.ok(!('compareScopeToCursors' in payload))
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
      statsSectionCollapsed: { exec: true, cores: false, bad: 'x' },
    }, timelineOptions)

    assert.equal(tab.marks.length, 1)
    assert.equal(tab.marks[0].ns, 42)
    assert.equal(tab.findMode, 'regex')
    assert.equal(tab.taskFilterText, 'idle')
    assert.equal(tab.taskFilterKeys, null)
    assert.equal(tab.pinnedHighlightKey, 'T1')
    assert.equal(timelineOptions.highlightKey, 'T1')
    assert.equal(timelineOptions.lockedTaskKey, 'T1')
    assert.deepEqual(tab.statsSectionCollapsed, { exec: true, cores: false })
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

  it('applyPortableSession restores coreFilterKeys onto the tab and timelineOptions', () => {
    // Parity.md #10: coreFilterKeys is a supported portable filter (Desktop
    // _snapshot_tab_filters / _sanitize_tab_filters carry it too) and must
    // survive a Desktop <-> Web .btfw / Session round trip.
    const tab = {
      cursors: [], marks: [], markNextId: 1, timelineViewport: {},
      findQuery: '', findMode: 'contains', pinnedHighlightKey: null,
      taskFilterText: '', migratedOnlyFilter: false,
      taskFilterKeys: null, heatmapFilterLabel: null, coreFilterKeys: null,
    }
    const timelineOptions = { coreFilterKeys: null }
    applyPortableSession(tab, {
      version: SESSION_PORTABLE_VERSION,
      tabFilters: { taskFilterText: '', migratedOnlyFilter: false, coreFilterKeys: ['Core_0', 'Core_2'] },
    }, timelineOptions)
    assert.deepEqual(tab.coreFilterKeys, ['Core_0', 'Core_2'])
    assert.deepEqual(timelineOptions.coreFilterKeys, ['Core_0', 'Core_2'])
  })

  it('accepts a Desktop-shaped .btfw view_state (Parity.md #22)', () => {
    // The exact field set BTFViewer/btf_viewer_pkg/mainwindow.py's
    // _build_portable_session_payload() / _workspace_view_state() produce —
    // a Desktop-authored .btfw or Session must restore completely on Web.
    const desktopPayload = {
      version: SESSION_PORTABLE_VERSION,
      traceName: 'example-2cores.btf',
      exportedAt: '2026-01-01T00:00:00Z',
      cursors: [1000, 2000, null, null],
      marks: [
        { id: 1, ns: 1000, label: 'bm', type: 'bookmark' },
        { id: 2, ns: 2000, label: 'an', type: 'annotation' },
      ],
      markNextId: 3,
      timelineViewport: {
        timeStart: 0, timeEnd: 5000, scrollY: 0, scrollX: 0, canvasW: 800, canvasH: 600,
      },
      timelineOptions: {
        viewMode: 'core', orientation: 'v', showGrid: false,
        showSti: false, showCpuLoad: true, darkMode: true,
      },
      tabFilters: {
        taskFilterText: 'idle', migratedOnlyFilter: true,
        taskFilterKeys: null, heatmapFilterLabel: null,
        coreFilterKeys: ['Core_0'],
      },
      findQuery: 'worker', findMode: 'exact',
      pinnedHighlightKey: 'T1',
      scopeToCursors: false,
      openPlot: null,
      statsSectionCollapsed: { exec: true },
    }
    const tab = {
      cursors: [], marks: [], markNextId: 1, timelineViewport: {},
      findQuery: '', findMode: 'contains', pinnedHighlightKey: null,
      taskFilterText: '', migratedOnlyFilter: false,
      taskFilterKeys: null, heatmapFilterLabel: null, coreFilterKeys: null,
    }
    const timelineOptions = {
      viewMode: 'task', orientation: 'h', showGrid: true, showSti: true,
      showCpuLoad: false, darkMode: false,
      taskFilterText: '', migratedOnlyFilter: false,
      taskFilterKeys: null, heatmapFilterLabel: null, coreFilterKeys: null,
      highlightKey: null, lockedTaskKey: null,
    }
    applyPortableSession(tab, desktopPayload, timelineOptions)

    assert.deepEqual(tab.cursors, [1000, 2000, null, null])
    assert.equal(tab.marks.length, 2)
    assert.equal(tab.findQuery, 'worker')
    assert.equal(tab.findMode, 'exact')
    assert.equal(tab.pinnedHighlightKey, 'T1')
    assert.equal(tab.scopeToCursors, false)
    assert.deepEqual(tab.statsSectionCollapsed, { exec: true })
    assert.equal(tab.taskFilterText, 'idle')
    assert.equal(tab.migratedOnlyFilter, true)
    assert.deepEqual(tab.coreFilterKeys, ['Core_0'])
    assert.deepEqual(tab.timelineViewport, {
      timeStart: 0, timeEnd: 5000, scrollY: 0, scrollX: 0, canvasW: 800, canvasH: 600,
    })
    assert.equal(timelineOptions.viewMode, 'core')
    assert.equal(timelineOptions.orientation, 'v')
    assert.equal(timelineOptions.showGrid, false)
    assert.equal(timelineOptions.showSti, false)
    assert.equal(timelineOptions.showCpuLoad, true)
    assert.equal(timelineOptions.darkMode, true)
    assert.deepEqual(timelineOptions.coreFilterKeys, ['Core_0'])
    assert.equal(timelineOptions.lockedTaskKey, 'T1')
  })
})
