import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { emptyStateMessage, emptyStateAction } from '../src/utils/emptyState.js'

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
})
