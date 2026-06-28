import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import { bisectLeft, bisectRight } from '../src/utils/bisect.js'

describe('bisect', () => {
  const arr = [10, 20, 20, 40, 50]

  it('bisectLeft finds first index >= value', () => {
    assert.equal(bisectLeft(arr, 20), 1)
    assert.equal(bisectLeft(arr, 5), 0)
    assert.equal(bisectLeft(arr, 60), 5)
  })

  it('bisectRight finds insertion point after equal run', () => {
    assert.equal(bisectRight(arr, 20), 3)
    assert.equal(bisectRight(arr, 5), 0)
    assert.equal(bisectRight(arr, 50), 5)
  })
})
