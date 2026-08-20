import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

import {
  domSelectValueEqual,
  normalizeDomSelectOptions,
  placeDomSelectList,
} from '../src/utils/domSelect.js'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')

describe('domSelect', () => {
  it('normalizes string and object options', () => {
    assert.deepEqual(normalizeDomSelectOptions(['English', '日本語']), [
      { value: 'English', label: 'English', disabled: false, title: '' },
      { value: '日本語', label: '日本語', disabled: false, title: '' },
    ])
    assert.deepEqual(normalizeDomSelectOptions([
      { value: true, label: 'Dark' },
      { value: 'fit', label: 'Fit', title: 'Fit view' },
    ]), [
      { value: true, label: 'Dark', disabled: false, title: '' },
      { value: 'fit', label: 'Fit', disabled: false, title: 'Fit view' },
    ])
  })

  it('compares values with strict equality', () => {
    assert.equal(domSelectValueEqual(10, 10), true)
    assert.equal(domSelectValueEqual('10', 10), false)
    assert.equal(domSelectValueEqual(true, true), true)
  })

  it('places a fixed listbox under the trigger by default', () => {
    const style = placeDomSelectList({ left: 40, top: 20, width: 160, bottom: 44 })
    assert.equal(style.position, 'fixed')
    assert.ok(Number(style.top.replace('px', '')) >= 44)
    assert.match(style.left, /^40px$/)
    assert.match(style.width, /^160px$/)
  })

  it('wires DomSelect into AI panel and documents tab-capture gap', () => {
    const ai = readFileSync(join(root, 'src/components/AiAssistantPanel.vue'), 'utf8')
    const rec = readFileSync(join(root, 'src/utils/demoRecorder.js'), 'utf8')
    assert.match(ai, /DomSelect/)
    assert.doesNotMatch(ai, /<select/)
    assert.ok(rec.includes('DomSelect.vue'))
    assert.ok(rec.includes('<select>'))
  })
})
