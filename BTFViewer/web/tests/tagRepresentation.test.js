import test from 'node:test'
import assert from 'node:assert/strict'

import {
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
  assert.equal(interpretTagValue('255', 'log2-uint32'), 8)
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
    [1, Math.log2(1025), Math.log2(1048577)],
  )
})

test('export samples honor the selected format', () => {
  const trace = { ...buildTagData([{ target: 'tag0_event', time: 0, note: '1065353216', core: 'Core_0' }]), timeScale: 'ns' }
  assert.equal(tagSampleDetailRows(trace, null, null, 0, { tag0_event: 'float32' })[0].valueNum, 1)
})
