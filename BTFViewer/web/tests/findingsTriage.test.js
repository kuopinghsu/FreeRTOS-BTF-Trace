import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  applyTriageAction,
  findingQueueStatus,
  filterByQueue,
  queueCounts,
  formatTriageAuditText,
  sortFindingsTriage,
  filterFindingsTriage,
  findingFilterFacets,
  groupFindingsByIncident,
  formatInvestigatePreview,
  SORT_TITLE,
  SORT_CATEGORY,
  QUEUE_OPEN,
  QUEUE_DONE,
  QUEUE_CASE,
  QUEUE_DISMISSED,
} from '../src/utils/findingsTriage.js'
import { addFindingToCase, emptyInvestigationCase } from '../src/utils/aiCase.js'
import { formatAnalysisFindingsText } from '../src/utils/workflowAnalysis.js'

describe('findings triage queue', () => {
  it('moves findings through Done, Case, and Dismissed', () => {
    const findings = [
      { id: 'a', title: 'A', severity: 'error' },
      { id: 'b', title: 'B', severity: 'warning' },
    ]
    let st = applyTriageAction(null, 'a', 'done')
    assert.equal(findingQueueStatus('a', st), QUEUE_DONE)
    assert.equal(findingQueueStatus('b', st), QUEUE_OPEN)
    st = applyTriageAction(st, 'a', 'case')
    assert.equal(findingQueueStatus('a', st), QUEUE_CASE)
    // 'Add to case' must be undoable: 'uncase' clears the case tag.
    const undo = applyTriageAction(
      applyTriageAction(null, 'z', 'case'), 'z', 'uncase')
    assert.equal(findingQueueStatus('z', undo), QUEUE_OPEN)
    assert.deepEqual(undo.case, [])
    st = applyTriageAction(st, 'b', 'dismiss', { reason: 'noise' })
    assert.equal(findingQueueStatus('b', st), QUEUE_DISMISSED)
    const counts = queueCounts(findings, st)
    assert.equal(counts[QUEUE_CASE], 1)
    assert.equal(counts[QUEUE_DISMISSED], 1)
    assert.deepEqual(
      filterByQueue(findings, st, { queue: QUEUE_CASE }).map(f => f.id),
      ['a'],
    )
    assert.match(formatTriageAuditText(findings, st), /noise/)
    const text = formatAnalysisFindingsText(findings, '', { triageState: st })
    assert.match(text, /Dismissed:/)
    assert.match(text, /In case:/)
  })

  it('addFindingToCase dedupes by id and sets goal', () => {
    const f = { id: 'x', title: 'Late', task: 'T1' }
    let cse = addFindingToCase(emptyInvestigationCase(), f)
    cse = addFindingToCase(cse, f)
    assert.equal(cse.suspected_findings.length, 1)
    assert.equal(cse.goal, 'Late')
    assert.ok(cse.scope.tasks.includes('T1'))
  })

  it('sorts by title and category', () => {
    const byTitle = sortFindingsTriage([
      { severity: 'error', title: 'Zebra' },
      { severity: 'info', title: 'Alpha' },
    ], { sortBy: SORT_TITLE })
    assert.equal(byTitle[0].title, 'Alpha')
    const byCat = sortFindingsTriage([
      { severity: 'info', title: 'Load imbalance' },
      { severity: 'error', title: 'Migration thrash' },
    ], { sortBy: SORT_CATEGORY })
    assert.equal(byCat[0].category, 'load')
    assert.equal(byCat[1].category, 'migration')
  })

  it('filters by category, task, and core', () => {
    const items = [
      { id: '1', severity: 'error', title: 'Migration thrash', task: 'ControlTask', text: 'Core_0 bounce' },
      { id: '2', severity: 'warning', title: 'Long blocking', task: 'Idle', text: 'mutex wait' },
    ]
    assert.deepEqual(filterFindingsTriage(items, { category: 'migration' }).map(f => f.id), ['1'])
    assert.deepEqual(filterFindingsTriage(items, { task: 'controltask' }).map(f => f.id), ['1'])
    assert.deepEqual(filterFindingsTriage(items, { core: 'core_0' }).map(f => f.id), ['1'])
    const facets = findingFilterFacets(items)
    assert.ok(facets.categories.includes('migration'))
    assert.ok(facets.tasks.includes('ControlTask'))
  })

  it('groups repeated findings by incident cluster', () => {
    const findings = [
      { id: 'a', title: 'Late A', severity: 'error' },
      { id: 'b', title: 'Late B', severity: 'warning' },
      { id: 'c', title: 'Other', severity: 'info' },
    ]
    const clusters = [{
      id: 'INC-1', count: 2, root_suspect: 'deadline',
      finding_ids: ['a', 'b'], findings: ['Late A', 'Late B'],
    }]
    const rows = groupFindingsByIncident(findings, clusters, { group: true })
    assert.equal(rows.filter(r => r.kind === 'header').length, 1)
    assert.ok(rows.filter(r => r.kind === 'finding').length >= 3)
    const flat = groupFindingsByIncident(findings, clusters, { group: false })
    assert.ok(flat.every(r => r.kind === 'finding'))
  })

  it('formats Investigate Scope preview', () => {
    const text = formatInvestigatePreview(
      { title: 'Late', id: 'x' },
      {
        scope: { lo: 10, hi: 20, reason: 'evidence window' },
        sectionId: 'response',
        sectionLabel: 'Response Time',
        currentLimit: true,
        currentLo: 1,
        currentHi: 5,
      },
    )
    assert.match(text, /Investigate will:/)
    assert.match(text, /Response Time/)
    assert.match(text, /10–20/)
    assert.match(text, /Replaces current Scope 1–5/)
    assert.match(text, /Undo/)
  })
})
