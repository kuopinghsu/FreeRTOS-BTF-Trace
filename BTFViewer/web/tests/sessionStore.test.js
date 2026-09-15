import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  applyTabState,
  isRestorableViewport,
  sanitizeTabFilters,
  snapshotTabFilters,
  snapshotTabState,
} from '../src/utils/sessionStore.js'
import { newInvestigation, addBookmark } from '../src/utils/investigationNotebook.js'

describe('sessionStore filters', () => {
  it('snapshotTabFilters keeps legend filters and drops heatmap spotlight', () => {
    const snap = snapshotTabFilters({
      taskFilterText: 'spi',
      migratedOnlyFilter: true,
      taskFilterKeys: ['A', 'B'],
      heatmapFilterLabel: 'Core_0',
    })
    assert.deepEqual(snap, {
      taskFilterText: 'spi',
      migratedOnlyFilter: true,
      taskFilterKeys: null,
      heatmapFilterLabel: null,
      coreFilterKeys: null,
    })
  })

  it('snapshotTabFilters persists coreFilterKeys (not ephemeral like the heatmap filter)', () => {
    const snap = snapshotTabFilters({ coreFilterKeys: ['Core_0', 'Core_2'] })
    assert.deepEqual(snap.coreFilterKeys, ['Core_0', 'Core_2'])
  })

  it('sanitizeTabFilters drops heatmap spotlight keys', () => {
    const out = sanitizeTabFilters({
      taskFilterKeys: ['T1', 'T2'],
      heatmapFilterLabel: 'Core_0',
      taskFilterText: 'x',
    })
    assert.equal(out.taskFilterKeys, null)
    assert.equal(out.heatmapFilterLabel, null)
    assert.equal(out.taskFilterText, 'x')
  })

  it('sanitizeTabFilters keeps coreFilterKeys', () => {
    const out = sanitizeTabFilters({ coreFilterKeys: ['Core_1'] })
    assert.deepEqual(out.coreFilterKeys, ['Core_1'])
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

describe('sessionStore investigation notebook persistence', () => {
  const baseTab = () => ({
    name: 't.btf',
    trace: { timeMin: 0, timeMax: 100 },
    timelineViewport: { timeStart: 0, timeEnd: 1, scrollY: 0, scrollX: 0, canvasW: 1, canvasH: 1 },
    cursors: [null, null, null, null],
    marks: [],
  })

  it('snapshots a non-empty notebook and applyTabState restores it', () => {
    const tab = baseTab()
    let inv = newInvestigation({ title: 'Case' })
    inv = addBookmark(inv, { type: 'observation', title: 'spike', bookmarkId: 'o1' })
    tab.investigation = inv

    const snap = snapshotTabState(tab)
    assert.ok(snap.investigation)
    assert.equal(snap.investigation.bookmarks.length, 1)

    const fresh = baseTab()
    applyTabState(fresh, snap)
    assert.equal(fresh.investigation.title, 'Case')
    assert.deepEqual(fresh.investigation.bookmarks.map(b => b.id), ['o1'])
  })

  it('drops an empty notebook from the snapshot', () => {
    const tab = baseTab()
    tab.investigation = newInvestigation({ title: 'Empty' })
    assert.equal(snapshotTabState(tab).investigation, null)
    assert.equal(snapshotTabState(baseTab()).investigation, null)
  })
})


describe('per-trace tag formats', () => {
  it('round-trips formats without sharing state between traces', () => {
    const first = { trace: {}, tagRepresentations: { tag0_event: 'float32', tag1_event: 'int32' } }
    const saved = JSON.parse(JSON.stringify(snapshotTabState(first)))
    const restored = { timelineViewport: {} }
    applyTabState(restored, saved)
    assert.deepEqual(restored.tagRepresentations, {tag0_event:{format:'float32',scale:'linear',includeZero:false},tag1_event:{format:'int32',scale:'linear',includeZero:false}})
    const other = { timelineViewport: {} }
    applyTabState(other, {})
    assert.deepEqual(other.tagRepresentations, {})
    restored.tagRepresentations.tag0_event = 'uint32'
    assert.equal(saved.tagRepresentations.tag0_event.format, 'float32')
  })
  it('ignores invalid saved channels and formats', () => {
    const tab = { timelineViewport: {} }
    applyTabState(tab, { tagRepresentations: { tag0_event: 'float32', tag1_event: 'invalid', unknown: 'int32' } })
    assert.deepEqual(tab.tagRepresentations, { tag0_event: {format:'float32',scale:'linear',includeZero:false} })
  })
})


it('migrates legacy logarithmic preferences and preserves independent display settings', () => {
  const tab = {timelineViewport:{}}
  applyTabState(tab, {tagRepresentations:{tag0_event:'log2-uint32', tag1_event:{format:'int32',scale:'log2',includeZero:true}}})
  assert.deepEqual(tab.tagRepresentations.tag0_event, {format:'uint32',scale:'log2',includeZero:false})
  assert.deepEqual(snapshotTabState({...tab,trace:{}}).tagRepresentations.tag1_event, {format:'int32',scale:'log2',includeZero:true})
})

it('restores per-trace aliases together with format and chart preferences', () => {
  const first={trace:{},tagRepresentations:{tag0_event:{format:'uint32',scale:'linear',includeZero:false,alias:'memory usage'}}}
  const saved=JSON.parse(JSON.stringify(snapshotTabState(first)))
  const restored={timelineViewport:{}}
  applyTabState(restored,saved)
  assert.equal(restored.tagRepresentations.tag0_event.alias,'memory usage')
  const other={timelineViewport:{}}
  applyTabState(other,{})
  assert.deepEqual(other.tagRepresentations,{})
})
