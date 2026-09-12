import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { describe, it } from 'node:test'
import { gzipSync, zipSync } from 'fflate'
import bz2 from 'bz2'

import {
  bzip2BlockCount,
  compressionFromName,
  decompressBtfBytes,
  decompressBtfEntries,
  isBtfOpenName,
  listZipBtfMembers,
  pickZipBtfMember,
  readResponseBytes,
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
    assert.equal(isBtfOpenName('demo.xml'), false)
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

  it('caps gzip expansion before collecting an oversized result', () => {
    const gz = gzipSync(new Uint8Array(256 * 1024))
    assert.throws(
      () => decompressBtfEntries(gz, 'bomb.btf.gz', {
        maxExpanded: 64 * 1024,
        bombMinSize: Number.MAX_SAFE_INTEGER,
      }),
      /decompressed size exceeds/,
    )
  })

  it('inflates bz2', () => {
    const bzBytes = execFileSync('python3', ['-c',
      'import bz2,sys; sys.stdout.buffer.write(bz2.compress(sys.stdin.buffer.read()))'],
      { input: MINI })
    const bytes = new Uint8Array(bzBytes)
    assert.equal(sniffCompression(bytes), 'bz2')
    assert.equal(compressionFromName('t.btf.bz2'), 'bz2')
    assert.equal(typeof bz2.decompress, 'function')
    assert.equal(bzip2BlockCount(bytes), 1)
    assert.match(decompressBtfBytes(bytes, 't.btf.bz2'), /resume/)
  })

  it('uses bzip2 block bounds before decompression', () => {
    const bzBytes = execFileSync('python3', ['-c',
      'import bz2,sys; sys.stdout.buffer.write(bz2.compress(sys.stdin.buffer.read()))'],
      { input: MINI })
    assert.throws(
      () => decompressBtfEntries(new Uint8Array(bzBytes), 't.btf.bz2', { maxExpanded: 1024 }),
      /decompressed size exceeds/,
    )
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
    assert.deepEqual(entries.map(e => e.name), ['pack.zip::a.btf', 'pack.zip::b.btf'])
    assert.match(entries[0].text, /\[0\/1\]A/)
    assert.match(entries[1].text, /\[0\/2\]B/)
  })

  it('disambiguates colliding basenames', () => {
    assert.deepEqual(
      zipMemberDisplayNames(['x/a.btf', 'y/a.btf']),
      ['x/a.btf', 'y/a.btf'],
    )
    assert.deepEqual(
      zipMemberDisplayNames(['x/a.btf', 'y/a.btf'], 'pack.zip'),
      ['pack.zip::x/a.btf', 'pack.zip::y/a.btf'],
    )
  })

  it('caps ZIP members and aggregate expansion', () => {
    const zipped = zipSync({
      'a.btf': new TextEncoder().encode(MINI),
      'b.btf': new TextEncoder().encode(MINI_B),
    })
    assert.throws(
      () => decompressBtfEntries(zipped, 'pack.zip', { maxEntries: 1 }),
      /too many entries/,
    )
    assert.throws(
      () => decompressBtfEntries(zipped, 'pack.zip', { maxExpanded: 10 }),
      /decompressed size exceeds/,
    )
  })

  it('rejects oversized raw input before decoding', () => {
    assert.throws(
      () => decompressBtfEntries(new Uint8Array(11), 'large.btf', { maxInput: 10 }),
      /Trace input exceeds/,
    )
  })
})

describe('readResponseBytes', () => {
  it('uses Content-Length for an early rejection', async () => {
    const response = new Response(new Uint8Array([1]), {
      headers: { 'content-length': '11' },
    })
    await assert.rejects(readResponseBytes(response, 10), /Trace response exceeds/)
  })

  it('caps a chunked response while streaming', async () => {
    const response = new Response(new ReadableStream({
      start(controller) {
        controller.enqueue(new Uint8Array(6))
        controller.enqueue(new Uint8Array(6))
        controller.close()
      },
    }))
    await assert.rejects(readResponseBytes(response, 10), /Trace response exceeds/)
  })
})
