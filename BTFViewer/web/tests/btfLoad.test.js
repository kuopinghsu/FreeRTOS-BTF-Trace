import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { describe, it } from 'node:test'
import { gzipSync, zipSync } from 'fflate'
import bz2 from 'bz2'

import {
  compressionFromName,
  decompressBtfBytes,
  decompressBtfEntries,
  isBtfOpenName,
  listZipBtfMembers,
  pickZipBtfMember,
  sniffCompression,
  zipMemberDisplayNames,
  zipNoBtfMessage,
} from '../src/utils/btfLoad.js'

const MINI = `#version 1.0.0
#timeScale us
100,Core_0,0,T,[0/1]A,0,resume
200,Core_0,0,T,[0/1]A,0,preempt
`

const MINI_B = `#version 1.0.0
#timeScale us
100,Core_0,0,T,[0/2]B,0,resume
150,Core_0,0,T,[0/2]B,0,preempt
`

describe('isBtfOpenName', () => {
  it('accepts plain and compressed names', () => {
    assert.equal(isBtfOpenName('a.btf'), true)
    assert.equal(isBtfOpenName('a.btf.gz'), true)
    assert.equal(isBtfOpenName('a.BZ2'), true)
    assert.equal(isBtfOpenName('pack.zip'), true)
    assert.equal(isBtfOpenName('a.csv'), false)
  })
})

describe('decompressBtfBytes', () => {
  it('passes through plain UTF-8', () => {
    const bytes = new TextEncoder().encode(MINI)
    assert.equal(sniffCompression(bytes), '')
    assert.match(decompressBtfBytes(bytes, 't.btf'), /resume/)
  })

  it('inflates gzip', () => {
    const gz = gzipSync(new TextEncoder().encode(MINI))
    assert.equal(sniffCompression(gz), 'gzip')
    assert.match(decompressBtfBytes(gz, 't.btf.gz'), /timeScale/)
  })

  it('inflates bz2', () => {
    const bzBytes = execFileSync('python3', ['-c',
      'import bz2,sys; sys.stdout.buffer.write(bz2.compress(sys.stdin.buffer.read()))'],
      { input: MINI })
    const bytes = new Uint8Array(bzBytes)
    assert.equal(sniffCompression(bytes), 'bz2')
    assert.equal(compressionFromName('t.btf.bz2'), 'bz2')
    assert.equal(typeof bz2.decompress, 'function')
    assert.match(decompressBtfBytes(bytes, 't.btf.bz2'), /resume/)
  })

  it('extracts .btf from zip', () => {
    const zipped = zipSync({
      'readme.txt': new TextEncoder().encode('nope'),
      'traces/demo.btf': new TextEncoder().encode(MINI),
    })
    assert.equal(sniffCompression(zipped), 'zip')
    assert.equal(pickZipBtfMember({
      'readme.txt': new Uint8Array(),
      'traces/demo.btf': new Uint8Array(),
    }), 'traces/demo.btf')
    assert.match(decompressBtfBytes(zipped, 'pack.zip'), /preempt/)
  })

  it('errors when zip has no .btf', () => {
    const zipped = zipSync({
      'readme.txt': new TextEncoder().encode('nope'),
    })
    assert.throws(
      () => decompressBtfEntries(zipped, 'empty.zip'),
      /no \.btf member/,
    )
    assert.match(zipNoBtfMessage(['readme.txt']), /no \.btf member/)
  })

  it('opens all .btf members from a multi-file zip', () => {
    const zipped = zipSync({
      'a.btf': new TextEncoder().encode(MINI),
      'nested/b.btf': new TextEncoder().encode(MINI_B),
      'readme.txt': new TextEncoder().encode('x'),
    })
    assert.deepEqual(
      listZipBtfMembers(['readme.txt', 'a.btf', 'nested/b.btf']),
      ['a.btf', 'nested/b.btf'],
    )
    const entries = decompressBtfEntries(zipped, 'pack.zip')
    assert.equal(entries.length, 2)
    assert.deepEqual(entries.map(e => e.name), ['a.btf', 'b.btf'])
    assert.match(entries[0].text, /\[0\/1\]A/)
    assert.match(entries[1].text, /\[0\/2\]B/)
  })

  it('disambiguates colliding basenames', () => {
    assert.deepEqual(
      zipMemberDisplayNames(['x/a.btf', 'y/a.btf']),
      ['x/a.btf', 'y/a.btf'],
    )
  })
})
