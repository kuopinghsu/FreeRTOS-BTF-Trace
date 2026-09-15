import test from 'node:test'
import assert from 'node:assert/strict'

import {
  tagChannelLabel, normalizeTagAlias, tagPreferences, tagAxisBounds, tagTransform, tagInverse, updateTagPreferences,
  buildTagData,
  interpretTagValue,
  recommendTagRepresentation,
  tagPlotPoints,
  tagStatsRows,
  tagSampleDetailRows,
} from '../src/utils/tagAnalysis.js'

test('tag payloads reinterpret the same 32-bit word', () => {
  assert.equal(interpretTagValue('-1', 'uint32'), 0xffffffff)
  assert.equal(interpretTagValue('4294967295', 'int32'), -1)
  assert.equal(interpretTagValue('1065353216', 'float32'), 1)
  assert.equal(interpretTagValue('255', 'log2-uint32'), 255)
  assert.equal(tagTransform(255, tagPreferences('log2-uint32')), 8)
})

test('tag statistics and plot points use the selected per-channel representation', () => {
  const events = [
    { target: 'tag0_event', time: 1, note: '1065353216', core: 'Core_0' },
    { target: 'tag0_event', time: 2, note: '1073741824', core: 'Core_0' },
  ]
  const trace = { ...buildTagData(events), timeScale: 'ns' }
  const representations = { tag0_event: 'float32' }
  const [row] = tagStatsRows(trace, null, null, representations)
  assert.equal(row.minVal, 1)
  assert.equal(row.maxVal, 2)
  assert.deepEqual(tagPlotPoints(trace, 'tag0_event', null, null, representations).map(p => p.yValue), [1, 2])
})

test('wide sparse unsigned ranges recommend log2 uint32', () => {
  const events = [1, 1024, 1048576].map((note, index) => ({
    target: 'tag3_event', time: index, note: String(note), core: 'Core_0',
  }))
  const trace = buildTagData(events)
  assert.equal(recommendTagRepresentation(trace, 'tag3_event'), 'log2-uint32')
  assert.deepEqual(
    tagPlotPoints(trace, 'tag3_event', null, null).map(point => point.yValue),
    [1, 1024, 1048576],
  )
})

test('export samples honor the selected format', () => {
  const trace = { ...buildTagData([{ target: 'tag0_event', time: 0, note: '1065353216', core: 'Core_0' }]), timeScale: 'ns' }
  assert.equal(tagSampleDetailRows(trace, null, null, 0, { tag0_event: 'float32' })[0].valueNum, 1)
})

test('all formats fit ranges, with explicit zero and consistent constant padding', () => {
  for (const values of [[2,8], [-20,-2], [1.14e-41,1.13e-40]]) {
    assert.deepEqual(tagAxisBounds(values), values)
    const p = { scale: 'log2' }
    assert.ok(tagTransform(values[1], p) > tagTransform(values[0], p))
    assert.ok(Math.abs(tagInverse(tagTransform(values[0], p), p) / values[0] - 1) < 1e-12)
  }
  assert.deepEqual(tagAxisBounds([10,10]), [9.5,10.5])
  assert.deepEqual(tagAxisBounds([2,8], {includeZero:true}), [0,8])
})
test('scale never changes statistics and reset restores defaults', () => {
  let preferences = updateTagPreferences(null, 'float32')
  preferences = updateTagPreferences(preferences, 'log2')
  preferences = updateTagPreferences(preferences, 'zero')
  assert.equal(interpretTagValue('1065353216', preferences), 1)
  assert.deepEqual(preferences, {format:'float32',scale:'log2',includeZero:true})
  assert.equal(updateTagPreferences(preferences, 'reset'), null)
})

test('tag aliases change display labels without changing channel keys or values', () => {
  const trace = {...buildTagData([{target:'tag0_event',time:0,note:'42',core:'Core_0'}]),timeScale:'ns'}
  const settings = {tag0_event:updateTagPreferences({format:'int32',scale:'log2'},'alias:  memory usage  ')}
  assert.equal(tagChannelLabel('tag0_event',settings),'memory usage')
  const row = tagStatsRows(trace,null,null,settings)[0]
  assert.equal(row.channel,'tag0_event')
  assert.equal(row.label,'memory usage')
  assert.equal(row.minVal,42)
  assert.equal(tagSampleDetailRows(trace,null,null,0,settings)[0].label,'memory usage')
  assert.equal(updateTagPreferences(settings.tag0_event,'float32').alias,'memory usage')
  assert.equal(updateTagPreferences(settings.tag0_event,'reset').alias,'memory usage')
  assert.equal(tagChannelLabel('tag0_event',{tag0_event:updateTagPreferences(settings.tag0_event,'alias:')}),'Tag 0')
  assert.equal(normalizeTagAlias(123),'')
  assert.equal(normalizeTagAlias('x'.repeat(100)).length,80)
})
