import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { templateRefEl } from '../src/utils/templateRefEl.js'

describe('templateRefEl', () => {
  it('returns a single element', () => {
    const el = { getBoundingClientRect() { return { top: 0 } } }
    assert.equal(templateRefEl(el), el)
  })

  it('unwraps a Vue v-for ref array', () => {
    const el = { getBoundingClientRect() { return { top: 0 } } }
    assert.equal(templateRefEl([el]), el)
  })

  it('rejects values without getBoundingClientRect', () => {
    assert.equal(templateRefEl(null), null)
    assert.equal(templateRefEl([{}]), null)
    assert.equal(templateRefEl({ contains() { return true } }), null)
  })
})
