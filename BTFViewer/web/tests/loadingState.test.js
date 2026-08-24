import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import {
  LOADING_STAGES,
  formatLoadingMessage,
  formatLoadingPct,
  isLoadingCancellable,
  resolveLoadingStage,
} from '../src/utils/loadingState.js'

describe('loadingState', () => {
  it('maps internal parser messages to user-facing stages', () => {
    assert.equal(formatLoadingMessage('Reading file…'), LOADING_STAGES.reading)
    assert.equal(formatLoadingMessage('Reconstructing segments…'), LOADING_STAGES.parsing)
    assert.equal(formatLoadingMessage('Building task LOD summaries…'), LOADING_STAGES.building)
    assert.equal(formatLoadingMessage('Preparing statistics…'), LOADING_STAGES.computing)
    assert.equal(formatLoadingMessage('Packing trace…'), LOADING_STAGES.opening)
    assert.equal(formatLoadingMessage('Building scene…'), LOADING_STAGES.building)
  })

  it('resolveLoadingStage returns stable keys', () => {
    assert.equal(resolveLoadingStage('Indexing migrations…'), 'parsing')
    assert.equal(resolveLoadingStage(''), 'reading')
  })

  it('formatLoadingPct rounds to 5% steps', () => {
    assert.equal(formatLoadingPct(0), '')
    assert.equal(formatLoadingPct(3), '5')
    assert.equal(formatLoadingPct(47), '45')
    assert.equal(formatLoadingPct(100), '100')
  })

  it('isLoadingCancellable only for parse/read phases', () => {
    assert.equal(isLoadingCancellable('parse'), true)
    assert.equal(isLoadingCancellable('read'), true)
    assert.equal(isLoadingCancellable('open'), false)
  })
})
