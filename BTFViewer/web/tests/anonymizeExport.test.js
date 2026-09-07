import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  ANON_PREFIX,
  anonymizeBtfText,
  anonymizeJsonStrings,
  anonymizeWithMap,
  buildTaskAliasMap,
} from '../src/utils/anonymizeExport.js'

const NAMES = ['ControlTask', 'IdleHook', 'ControlTaskHelper', 'Sensor']

describe('buildTaskAliasMap', () => {
  it('sorts names and numbers them stably', () => {
    assert.deepEqual([...buildTaskAliasMap(NAMES).entries()], [
      ['ControlTask', 'Task-1'],
      ['ControlTaskHelper', 'Task-2'],
      ['IdleHook', 'Task-3'],
      ['Sensor', 'Task-4'],
    ])
  })
  it('dedupes and trims blanks', () => {
    assert.deepEqual([...buildTaskAliasMap(['  A ', 'A', '', null, 'B']).entries()],
      [['A', 'Task-1'], ['B', 'Task-2']])
  })
  it('exposes the prefix', () => {
    assert.equal(ANON_PREFIX, 'Task-')
  })
})

describe('anonymizeWithMap', () => {
  const m = buildTaskAliasMap(NAMES)

  it('replaces whole tokens only', () => {
    assert.equal(
      anonymizeWithMap('ControlTaskHelper ran after ControlTask', m),
      'Task-2 ran after Task-1',
    )
  })

  it('rewrites BTF csv lines', () => {
    const line = '1000,Core_0,0,T,ControlTask,0,resume,\n2000,Core_0,0,T,Sensor,0,preempt,'
    const out = anonymizeBtfText(line, m)
    assert.ok(out.includes(',T,Task-1,0,resume,'))
    assert.ok(out.includes(',T,Task-4,0,preempt,'))
    assert.ok(!out.includes('ControlTask'))
  })

  it('passes through empty text / empty map', () => {
    assert.equal(anonymizeWithMap('ControlTask', new Map()), 'ControlTask')
    assert.equal(anonymizeWithMap('', m), '')
  })
})

describe('anonymizeJsonStrings', () => {
  const m = buildTaskAliasMap(NAMES)
  it('rewrites strings recursively, leaves other values', () => {
    const out = anonymizeJsonStrings({
      title: 'ControlTask misses deadline',
      rows: [{ label: 'Sensor', n: 3 }],
      nested: { note: 'see IdleHook' },
      keep_number: 42,
    }, m)
    assert.equal(out.title, 'Task-1 misses deadline')
    assert.equal(out.rows[0].label, 'Task-4')
    assert.equal(out.rows[0].n, 3)
    assert.equal(out.nested.note, 'see Task-3')
    assert.equal(out.keep_number, 42)
  })
})
