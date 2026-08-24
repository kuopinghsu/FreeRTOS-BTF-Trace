import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import {
  formatError,
  formatErrorToast,
  formatParseError,
} from '../src/utils/errorFormat.js'

describe('errorFormat', () => {
  it('formatError builds title and actionable message', () => {
    const err = formatError({
      operation: 'Could not open trace',
      subject: 'bad.btf',
      reason: 'invalid timestamp near line 482',
      suggestion: 'Check timestamps.',
    })
    assert.match(err.title, /bad\.btf/)
    assert.match(err.message, /invalid timestamp/)
    assert.match(err.message, /Check timestamps/)
  })

  it('formatParseError preserves detail separately from primary message', () => {
    const err = formatParseError(new Error('invalid timestamp near line 482'), 'demo.btf')
    assert.match(err.title, /demo\.btf/)
    assert.match(err.message, /invalid timestamp/)
    assert.ok(err.detail)
    assert.doesNotMatch(err.message, /Traceback/)
  })

  it('formatErrorToast flattens structured errors', () => {
    const text = formatErrorToast({
      title: 'Could not open trace: demo.btf',
      message: 'invalid timestamp Check timestamps.',
    })
    assert.match(text, /invalid timestamp/)
  })
})
