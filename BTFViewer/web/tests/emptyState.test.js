import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import {
  emptyStateMessage,
  emptyStateAction,
  emptyStateParts,
  EMPTY_STATES,
} from '../src/utils/emptyState.js'

const here = dirname(fileURLToPath(import.meta.url))

describe('emptyState', () => {
  it('emptyStateMessage returns prerequisite guidance', () => {
    assert.match(emptyStateMessage('noTrace'), /Open a BTF trace/)
    assert.match(emptyStateMessage('noCompare'), /two traces/)
    assert.match(emptyStateMessage('noCursors'), /two cursors/)
  })

  it('emptyStateMessage includes hints when defined', () => {
    assert.match(emptyStateMessage('noMarks'), /bookmark/)
    assert.match(emptyStateMessage('noMigration'), /Core View/)
  })

  it('emptyStateAction exposes direct actions', () => {
    assert.equal(emptyStateAction('noTrace'), 'open')
    assert.equal(emptyStateAction('noAiConfig'), 'settings')
    assert.equal(emptyStateAction('noCursors'), null)
  })

  it('stats-scoped empty states expose clear actions', () => {
    assert.equal(emptyStateAction('stats_scoped_empty'), 'clear_scope')
    assert.equal(emptyStateAction('stats_filtered_empty'), 'clear_filter')
    assert.equal(emptyStateAction('stats_needs_sti'), null)
    assert.equal(emptyStateAction('stats_needs_multicore'), null)
    assert.match(emptyStateMessage('stats_scoped_empty'), /Limit to C1/)
    assert.match(emptyStateMessage('stats_needs_sti'), /STI/)
    assert.match(emptyStateMessage('stats_needs_multicore'), /multiple cores/)
    assert.match(emptyStateMessage('stats_filtered_empty'), /Filter/)
  })

  it('Marks and Find panels use the shared empty catalog', () => {
    const marks = readFileSync(join(here, '../src/components/MarksPanel.vue'), 'utf8')
    const find = readFileSync(join(here, '../src/components/FindPanel.vue'), 'utf8')
    assert.match(marks, /emptyStateMessage\('noMarks'\)/)
    assert.match(find, /emptyStateMessage\('noFindQuery'\)/)
    assert.match(find, /emptyStateMessage\('noFindHits'\)/)
    const ai = readFileSync(join(here, '../src/components/AiAssistantPanel.vue'), 'utf8')
    assert.match(ai, /emptyStateMessage\('noAi'\)/)
  })

  it('emptyStateParts separates message hint and action', () => {
    const scoped = emptyStateParts('stats_scoped_empty')
    assert.match(scoped.message, /cursor range/)
    assert.match(scoped.hint || '', /Limit to C1/)
    assert.equal(scoped.action, 'clear_scope')
    assert.ok(EMPTY_STATES.stats_needs_sti)
  })
})
