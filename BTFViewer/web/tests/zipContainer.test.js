import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { zipSync, strToU8 } from 'fflate'

import {
  CONTAINER_MAX_ENTRIES,
  isSafeMember,
  readZipContainer,
} from '../src/utils/zipContainer.js'

function zip(entries) {
  const files = {}
  for (const [name, data] of entries) {
    files[name] = typeof data === 'string' ? strToU8(data) : data
  }
  return zipSync(files, { level: 0 })
}

describe('isSafeMember', () => {
  it('accepts plain relative paths', () => {
    for (const n of ['a.txt', 'a/b.txt', 'trace/source.btf', 'voice/en/01.mp3', 'a/b/']) {
      assert.equal(isSafeMember(n), true, n)
    }
  })
  it('rejects traversal and roots', () => {
    for (const n of ['../x', 'a/../b', '/x', '~/x', 'C:\\x', 'a\\b', ' s', '', 'a/./b', 'a\0b']) {
      assert.equal(isSafeMember(n), false, n)
    }
  })
})

describe('readZipContainer', () => {
  it('returns only safe members, with warnings for the rest', () => {
    const out = readZipContainer(zip([
      ['ok/a.txt', 'a'],
      ['../evil', 'x'],
      ['/abs', 'x'],
    ]))
    assert.deepEqual(Object.keys(out.members).sort(), ['ok/a.txt'])
    assert.equal(out.warnings.length, 2)
  })

  it('rejects a non-zip input', () => {
    assert.throws(
      () => readZipContainer(new TextEncoder().encode('not a zip'), { containerDesc: '.btfw / ZIP' }),
      /not a .btfw \/ ZIP container/,
    )
  })

  it('rejects too many entries', () => {
    const entries = []
    for (let i = 0; i < CONTAINER_MAX_ENTRIES + 2; i += 1) entries.push([`f${i}.txt`, 'x'])
    assert.throws(() => readZipContainer(zip(entries)), /too many entries/)
  })

  it('rejects a compression bomb', () => {
    const bomb = zipSync({ 'big.bin': new Uint8Array(4 * 1024 * 1024) }, { level: 6 })
    assert.throws(() => readZipContainer(bomb), /compression bomb/)
  })

  it('caps total decompressed size', () => {
    const z = zipSync({ 'a.bin': new Uint8Array(2048) }, { level: 6 })
    assert.throws(() => readZipContainer(z, { maxUncompressed: 100 }), /decompressed size/)
  })
})
