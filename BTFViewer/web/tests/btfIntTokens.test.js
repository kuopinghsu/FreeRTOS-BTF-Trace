import test from 'node:test'
import assert from 'node:assert/strict'
import { tryParseBtfInt, normalizeSyncPtr } from '../src/utils/colors.js'
import { parseSyncObjectNote } from '../src/utils/syncObjectAnalysis.js'
import { parseCreatePriority, parsePriorityStiNote } from '../src/utils/priorityAnalysis.js'
import { tagRawUint32, interpretTagValue } from '../src/utils/tagAnalysis.js'

test('tryParseBtfInt accepts decimal and 0x hex', () => {
  assert.equal(tryParseBtfInt('42'), 42)
  assert.equal(tryParseBtfInt('0x2a'), 42)
  assert.equal(tryParseBtfInt('0X2A'), 42)
  assert.equal(tryParseBtfInt('+0x10'), 16)
  assert.equal(tryParseBtfInt('-0x10'), -16)
  assert.equal(tryParseBtfInt('0011'), 11)
  assert.equal(tryParseBtfInt(''), null)
  assert.equal(tryParseBtfInt('3.14'), null)
})

test('tag values accept decimal and hex', () => {
  assert.equal(tagRawUint32('255'), 255)
  assert.equal(tagRawUint32('0xff'), 255)
  assert.equal(interpretTagValue('0xffffffff', 'int32'), -1)
})

test('priority notes accept hex', () => {
  assert.equal(parseCreatePriority('create pri:4'), 4)
  assert.equal(parseCreatePriority('create pri:0x4'), 4)
  const p = parsePriorityStiNote('set_priority Worker[1] pri:0xA')
  assert.equal(p?.priority, 10)
})

test('sync pointers normalize decimal and hex to the same key', () => {
  assert.equal(normalizeSyncPtr('42'), '0x2a')
  assert.equal(normalizeSyncPtr('0x2A'), '0x2a')
  assert.deepEqual(parseSyncObjectNote('take 42'), { action: 'take', ptr: '0x2a' })
  assert.deepEqual(parseSyncObjectNote('take 0x2a'), { action: 'take', ptr: '0x2a' })
  assert.deepEqual(parseSyncObjectNote('give'), { action: 'give', ptr: '0x0' })
})
