import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import {
  displayNameFromMergeKey,
  taskDisplayName,
  taskMergeKey,
} from '../src/utils/colors.js'

describe('taskDisplayName (desktop lockstep)', () => {
  it('decodes merge-key strings like Desktop _task_display_name', () => {
    assert.equal(taskDisplayName('\x00267\x00Med'), 'Med[267]')
    assert.equal(taskDisplayName('\x0028\x00CS'), 'CS[28]')
    assert.equal(displayNameFromMergeKey('\x00267\x00Med'), 'Med[267]')
  })

  it('still formats raw bracket / suffix names', () => {
    assert.equal(taskDisplayName('[0/0267]Med'), 'Med[267]')
    assert.equal(taskDisplayName('Med[267]'), 'Med[267]')
    assert.equal(taskMergeKey('[0/0267]Med'), '\x00267\x00Med')
  })
})
