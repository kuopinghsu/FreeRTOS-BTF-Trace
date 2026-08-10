import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import {
  AI_TOOL_SYSTEM_ADDENDUM,
  AI_VIEWER_TOOL_NAMES,
  aiViewerTools,
  btfHighlightHref,
  btfJumpHref,
  parseBtfHighlightHref,
  parseBtfJumpHref,
  extractToolCalls,
  mergeToolCalls,
  canonicalAssistantToolMessage,
  normalizeToolChatMessages,
  parseAiAutoApply,
  parseToolCallsFromText,
  resolveCoreKey,
  resolveTaskKey,
  stripParsedToolMarkup,
  summariseToolCall,
  toolResultMessage,
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
    assert.ok(validateToolCall('set_cursors', { timestamps: [] }).error)
    const clipped = validateToolCall('set_cursors', { timestamps: [...Array(12).keys()] })
    assert.equal(clipped.args.timestamps.length, 8)
    assert.ok(validateToolCall('zoom_to_range', { start_time: 5, end_time: 5 }).error)
  })

  it('validates highlight, view mode, and corridor tools', () => {
    const hl = validateToolCall('highlight_task', { task_name_or_id: '  PS[228] ' })
    assert.equal(hl.error, '')
    assert.equal(hl.args.task_name_or_id, 'PS[228]')
    const clear = validateToolCall('highlight_task', { task_name_or_id: '' })
    assert.equal(clear.args.task_name_or_id, '')
    const mode = validateToolCall('set_view_mode', { mode: 'CORE', orientation: 'v' })
    assert.deepEqual(mode.args, { mode: 'core', orientation: 'vertical' })
    const horiz = validateToolCall('set_view_mode', { mode: 'task', orientation: 'horiz' })
    assert.equal(horiz.args.orientation, 'horizontal')
    assert.ok(validateToolCall('set_view_mode', { mode: 'gantt' }).error)
    const pair = validateToolCall('open_corridor_inspector', { core_from: ' 0 ', core_to: 'Core_1' })
    assert.deepEqual(pair.args, { core_from: '0', core_to: 'Core_1' })
    const open = validateToolCall('open_corridor_inspector', {})
    assert.deepEqual(open.args, { core_from: '', core_to: '' })
  })

  it('summarises each viewer tool', () => {
    assert.match(summariseToolCall('set_cursors', { timestamps: [10, 20] }), /10/)
    assert.match(summariseToolCall('zoom_to_range', { start_time: 10, end_time: 20 }), /Zoom to range/)
    assert.match(summariseToolCall('highlight_task', { task_name_or_id: 'PS[228]' }), /PS\[228\]/)
    assert.match(summariseToolCall('highlight_task', { task_name_or_id: '' }), /Clear/)
    assert.match(summariseToolCall('set_view_mode', { mode: 'core', orientation: 'vertical' }), /core/)
    assert.match(summariseToolCall('open_corridor_inspector', { core_from: 'Core_0', core_to: 'Core_1' }), /Core_0/)
    assert.equal(summariseToolCall('open_corridor_inspector', {}), 'Open corridor inspector')
  })

  it('resolves core aliases like CLI Core_0 / 0 / c0', () => {
    const cores = ['Core_0', 'Core_1', 'Core_10']
    assert.equal(resolveCoreKey('Core_0', cores), 'Core_0')
    assert.equal(resolveCoreKey('0', cores), 'Core_0')
    assert.equal(resolveCoreKey('c1', cores), 'Core_1')
    assert.equal(resolveCoreKey('C0', cores), 'Core_0')
    assert.equal(resolveCoreKey('C1', cores), 'Core_1')
    assert.equal(resolveCoreKey('Core_2', ['Core_0', 'Core_1', 'Core_2']), 'Core_2')
    assert.equal(resolveCoreKey('Core 10', cores), 'Core_10')
    assert.equal(resolveCoreKey('core_1', cores), 'Core_1')
    assert.equal(resolveCoreKey('99', cores), null)
    assert.equal(resolveCoreKey('', cores), null)
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
      '```btftool',
      '{"name": "set_view_mode", "arguments": {"mode": "core", "orientation": "v"}}',
      '```',
      '```btftool',
      '{"name": "open_corridor_inspector", "arguments": {"core_from": "0", "core_to": "1"}}',
      '```',
    ].join('\n')
    const calls = parseToolCallsFromText(text)
    assert.deepEqual(calls.map(c => c.name), [
      'set_cursors', 'set_view_mode', 'open_corridor_inspector', 'zoom_to_range',
    ])
    assert.deepEqual(calls[0].arguments.timestamps, [10, 20])
    assert.equal(calls[1].arguments.orientation, 'vertical')
    assert.equal(calls[2].arguments.core_from, '0')
    const stripped = stripParsedToolMarkup(text)
    assert.doesNotMatch(stripped, /btftool/)
    assert.doesNotMatch(stripped, /tool_call/)
    const merged = mergeToolCalls(
      [{ name: 'set_cursors', arguments: { timestamps: [10, 20] } }],
      calls,
    )
    assert.equal(merged.length, 4)
    assert.match(AI_TOOL_SYSTEM_ADDENDUM, /```btftool/)
  })

  it('resolves task keys and auto-apply default', () => {
    assert.equal(resolveTaskKey('266', ['Idle[1]', 'Low[266]']), 'Low[266]')
    const ps = '\x00228\x00PS'
    const low = '\x00266\x00Low'
    assert.equal(resolveTaskKey('PS[228]', [ps, low]), ps)
    assert.equal(resolveTaskKey('228', [ps, low]), ps)
    assert.equal(resolveTaskKey('PS', [ps, low]), ps)
    assert.equal(
      resolveTaskKey('Low[266] (Core 0)', ['Idle[1]', 'Low[266]', 'High[268]']),
      'Low[266]',
    )
    assert.equal(resolveTaskKey('Mutex(0x80018700)', ['Idle[1]', 'Low[266]']), null)
    assert.equal(resolveTaskKey('Core_0', ['Idle[1]', 'Low[266]']), null)
    assert.equal(parseAiAutoApply(undefined), false)
    assert.equal(parseAiAutoApply(true), true)
    assert.match(AI_TOOL_SYSTEM_ADDENDUM, /mermaid sequenceDiagram/)
    assert.equal(parseBtfJumpHref(btfJumpHref(1805120)), 1805120)
    assert.equal(parseBtfJumpHref('btfjump:1805120'), 1805120)
    assert.equal(parseBtfHighlightHref(btfHighlightHref('PS[228]')), 'PS[228]')
  })

  it('fills Gemini function_response.name on tool follow-ups', () => {
    const asst = canonicalAssistantToolMessage('Applying.', [
      { id: 'c1', name: 'set_cursors', arguments: { timestamps: [1, 2] } },
      { id: 'c2', name: 'highlight_task', arguments: { task_name_or_id: 'PS[228]' } },
    ])
    assert.equal(asst.tool_calls[0].function.name, 'set_cursors')
    const fixed = normalizeToolChatMessages([
      { role: 'user', content: 'fix inversion' },
      asst,
      { role: 'tool', tool_call_id: 'c1', content: '{"ok":true}' },
      { role: 'tool', tool_call_id: 'c2', content: '{"ok":true}' },
    ])
    assert.deepEqual(
      fixed.filter(m => m.role === 'tool').map(m => m.name),
      ['set_cursors', 'highlight_task'],
    )
    const byOrder = normalizeToolChatMessages([
      asst,
      toolResultMessage({ toolCallId: '', name: '', content: { ok: true } }),
      { role: 'tool', content: '{"ok":true}' },
    ])
    assert.deepEqual(
      byOrder.filter(m => m.role === 'tool').map(m => m.name),
      ['set_cursors', 'highlight_task'],
    )
    assert.ok(byOrder.filter(m => m.role === 'tool').every(m => m.tool_call_id))
  })
})
