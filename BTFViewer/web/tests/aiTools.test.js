import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import {
  AI_TOOL_SYSTEM_ADDENDUM,
  AI_VIEWER_TOOL_NAMES,
  aiViewerTools,
  extractToolCalls,
  mergeToolCalls,
  parseAiAutoApply,
  parseToolCallsFromText,
  resolveTaskKey,
  stripParsedToolMarkup,
  summariseToolCall,
  validateToolCall,
} from '../src/utils/aiTools.js'

describe('aiTools', () => {
  it('exports the five viewer tools', () => {
    const names = aiViewerTools().map(t => t.function.name)
    assert.deepEqual(names, [...AI_VIEWER_TOOL_NAMES])
  })

  it('validates set_cursors and zoom_to_range', () => {
    const a = validateToolCall('set_cursors', { timestamps: [1, 2] })
    assert.equal(a.error, '')
    assert.deepEqual(a.args.timestamps, [1, 2])
    const z = validateToolCall('zoom_to_range', { start_time: 20, end_time: 10 })
    assert.equal(z.error, '')
    assert.equal(z.args.start_time, 10)
    assert.equal(z.args.end_time, 20)
  })

  it('extracts OpenAI tool_calls', () => {
    const calls = extractToolCalls({
      tool_calls: [{
        id: 'c1',
        function: { name: 'highlight_task', arguments: '{"task_name_or_id":"Low[266]"}' },
      }],
    })
    assert.equal(calls[0].name, 'highlight_task')
    assert.equal(calls[0].arguments.task_name_or_id, 'Low[266]')
    assert.match(summariseToolCall(calls[0].name, calls[0].arguments), /Low\[266\]/)
    const asStr = extractToolCalls({
      tool_calls: JSON.stringify([{
        id: 'c2',
        name: 'set_view_mode',
        arguments: { mode: 'core' },
      }]),
    })
    assert.equal(asStr[0].name, 'set_view_mode')
  })

  it('parses ```btftool fences and XML fallbacks', () => {
    const text = [
      'Zooming in.',
      '```btftool',
      '{"name": "set_cursors", "arguments": {"timestamps": [10, 20]}}',
      '```',
      '<tool_call>',
      '{"name": "zoom_to_range", "arguments": {"start_time": 10, "end_time": 20}}',
      '</tool_call>',
    ].join('\n')
    const calls = parseToolCallsFromText(text)
    assert.deepEqual(calls.map(c => c.name), ['set_cursors', 'zoom_to_range'])
    assert.deepEqual(calls[0].arguments.timestamps, [10, 20])
    const stripped = stripParsedToolMarkup(text)
    assert.doesNotMatch(stripped, /btftool/)
    assert.doesNotMatch(stripped, /tool_call/)
    const merged = mergeToolCalls(
      [{ name: 'set_cursors', arguments: { timestamps: [10, 20] } }],
      calls,
    )
    assert.equal(merged.length, 2)
    assert.match(AI_TOOL_SYSTEM_ADDENDUM, /```btftool/)
  })

  it('resolves task keys and auto-apply default', () => {
    assert.equal(resolveTaskKey('266', ['Idle[1]', 'Low[266]']), 'Low[266]')
    assert.equal(parseAiAutoApply(undefined), false)
    assert.equal(parseAiAutoApply(true), true)
    assert.match(AI_TOOL_SYSTEM_ADDENDUM, /mermaid sequenceDiagram/)
  })
})
