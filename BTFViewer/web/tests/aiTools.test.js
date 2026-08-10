import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import {
  AI_RAW_METRIC_PRIORITY,
  AI_TOOL_SYSTEM_ADDENDUM,
  AI_VIEWER_TOOL_NAMES,
  GEMINI_SKIP_THOUGHT_SIGNATURE,
  aiViewerTools,
  btfHighlightHref,
  btfJumpHref,
  buildAiReportCsv,
  buildAiReportHtml,
  parseBtfHighlightHref,
  parseBtfJumpHref,
  extractToolCalls,
  ensureGeminiThoughtSignatures,
  mergeToolCalls,
  needsGeminiThoughtSignatures,
  canonicalAssistantToolMessage,
  normalizeRawMetric,
  normalizeToolChatMessages,
  parseAiAutoApply,
  parseToolCallsFromText,
  queryRawMetric,
  resolveCoreKey,
  resolveTaskKey,
  searchTimelineHits,
  stripParsedToolMarkup,
  summariseToolCall,
  toolBatchAutoRuns,
  toolMutatesGui,
  toolResultMessage,
  validateToolCall,
} from '../src/utils/aiTools.js'

describe('aiTools', () => {
  it('exports the viewer tools', () => {
    const names = aiViewerTools().map(t => t.function.name)
    assert.deepEqual(names, [...AI_VIEWER_TOOL_NAMES])
    assert.ok(names.includes('add_annotation'))
    assert.ok(names.includes('query_raw_metric'))
    assert.ok(names.includes('export_report'))
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

  it('validates annotation, query_raw_metric, and export_report', () => {
    const ann = validateToolCall('add_annotation', { time: 1805120, note: '  spike  ' })
    assert.equal(ann.error, '')
    assert.equal(ann.args.note, 'spike')
    assert.ok(validateToolCall('add_annotation', { time: 1, note: '' }).error)
    const q = validateToolCall('query_raw_metric', { task: 'Low[266]', metric: 'pi' })
    assert.equal(q.error, '')
    assert.equal(q.args.metric, AI_RAW_METRIC_PRIORITY)
    assert.ok(validateToolCall('query_raw_metric', { task: 'Low[266]', metric: 'nope' }).error)
    const exp = validateToolCall('export_report', {})
    assert.equal(exp.args.format, 'html')
    assert.equal(validateToolCall('export_report', { format: 'CSV' }).args.format, 'csv')
    assert.match(summariseToolCall('add_annotation', { time: 1805120, note: 'spike' }), /1805120/)
    assert.equal(toolMutatesGui('add_annotation'), true)
    assert.equal(toolMutatesGui('query_raw_metric'), false)
    assert.equal(toolBatchAutoRuns([{ name: 'query_raw_metric' }]), true)
    assert.equal(toolBatchAutoRuns([
      { name: 'query_raw_metric' }, { name: 'add_annotation' },
    ]), false)
    assert.equal(normalizeRawMetric('priority-inheritance'), AI_RAW_METRIC_PRIORITY)
  })

  it('validates clear_marks, reset_view, search_timeline, trigger_compare', () => {
    const clr = validateToolCall('clear_marks', {})
    assert.equal(clr.error, '')
    assert.equal(clr.args.what, 'all')
    assert.equal(validateToolCall('clear_marks', { what: 'marks' }).args.what, 'all')
    assert.ok(validateToolCall('clear_marks', { what: 'nope' }).error)
    assert.equal(validateToolCall('reset_view', {}).error, '')
    const s = validateToolCall('search_timeline', { query: 'TICK', mode: 'tags' })
    assert.equal(s.error, '')
    assert.equal(s.args.mode, 'tags')
    assert.ok(validateToolCall('search_timeline', { query: '' }).error)
    const cmp = validateToolCall('trigger_compare', { tab_a: '0', tab_b: 'tickless' })
    assert.equal(cmp.args.tab_b, 'tickless')
    assert.equal(toolMutatesGui('clear_marks'), true)
    assert.equal(toolMutatesGui('reset_view'), true)
    assert.equal(toolMutatesGui('search_timeline'), false)
    assert.equal(toolBatchAutoRuns([{ name: 'search_timeline' }]), true)
    assert.equal(toolBatchAutoRuns([{ name: 'trigger_compare' }]), true)
    assert.equal(toolBatchAutoRuns([
      { name: 'search_timeline' }, { name: 'clear_marks' },
    ]), false)
    assert.match(summariseToolCall('clear_marks', { what: 'all' }), /all/)
    assert.equal(summariseToolCall('reset_view', {}), 'Reset view')
  })

  it('searchTimelineHits wraps Find', () => {
    const out = searchTimelineHits(
      { segByMergeKey: new Map(), taskRepr: new Map(), migrations: [] },
      'watch',
      'contains',
      [{ ns: 500, label: 'watchdog timeout' }],
    )
    assert.equal(out.ok, true)
    assert.deepEqual(out.data.times, [500])
    assert.equal(out.data.count, 1)
    assert.equal(searchTimelineHits(null, '', 'contains').ok, false)
    assert.equal(searchTimelineHits(null, 'x', 'contains').message, 'No trace loaded')
    const badRe = searchTimelineHits(
      { segByMergeKey: new Map(), taskRepr: new Map(), migrations: [] },
      '[',
      'regex',
    )
    assert.equal(badRe.ok, false)
    assert.match(badRe.message, /Regex/)
  })

  it('queryRawMetric returns priority episodes', () => {
    const mk = '\x00266\x00Low'
    const ep = {
      mk, taskLabel: 'Low[266]', basePri: 1, peakPri: 4,
      startNs: 3100000, stopNs: 3134000, inherited: true,
      inversionSuspect: true, mediumTasks: [{ label: 'Med[267]' }],
      pattern: 'Mutex inherit L/M/H (Med[267])',
    }
    const trace = {
      tasks: ['Low[266]', 'Med[267]'],
      taskRepr: new Map([[mk, 'Low[266]']]),
      segByMergeKey: new Map([[mk, [{ task: 'Low[266]', start: 3090000, end: 3095000, core: 'Core_0' }]]]),
      priorityEpisodes: [ep],
      priorityEpisodesByMk: new Map([[mk, [ep]]]),
      migrationsByMk: new Map(),
      stiEvents: [],
    }
    const out = queryRawMetric(trace, 'Low[266]', 'priority_inheritance')
    assert.equal(out.ok, true)
    assert.equal(out.data.count, 1)
    assert.equal(out.data.episodes[0].peak_pri, 4)
    assert.ok(out.data.episodes[0].medium_tasks.includes('Med[267]'))
    const execOut = queryRawMetric(trace, 'Low[266]', 'execution')
    assert.equal(execOut.data.count, 1)
    const miss = queryRawMetric(trace, 'NoSuch', 'execution')
    assert.equal(miss.ok, false)
  })

  it('builds AI report CSV and HTML', () => {
    const csv = buildAiReportCsv({
      meta: { file: 'demo.btf' },
      gui: { cursors: [10, 20], view_mode: 'task' },
      findings: '1. [WARNING] Thrash',
      annotations: [{ time: 15, note: 'spike' }],
      conversation: 'You:\nhello\n',
    })
    assert.match(csv, /demo\.btf/)
    assert.match(csv, /spike/)
    const html = buildAiReportHtml({
      meta: { file: 'demo.btf' },
      gui: { highlight: 'Low[266]' },
      findings: 'ok',
      annotations: [{ time: 1, note: 'n' }],
      conversationHtml: '<p>hi</p>',
    })
    assert.match(html, /AI Report/)
    assert.match(html, /Low\[266\]/)
    assert.match(html, /<p>hi<\/p>/)
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

  it('preserves Gemini thought signatures and skips only the first missing call', () => {
    const sig = 'CvcQAdHtimRealSignature=='
    const extracted = extractToolCalls({
      role: 'assistant',
      tool_calls: [
        {
          id: 'c1',
          type: 'function',
          function: { name: 'set_cursors', arguments: '{"timestamps":[1,2]}' },
          extra_content: { google: { thought_signature: sig } },
        },
        {
          id: 'c2',
          type: 'function',
          function: {
            name: 'highlight_task',
            arguments: '{"task_name_or_id":"PS[228]"}',
          },
        },
      ],
    })
    assert.equal(extracted[0].thought_signature, sig)
    assert.equal(extracted[1].thought_signature, undefined)
    const canon = canonicalAssistantToolMessage(null, extracted)
    assert.equal(
      canon.tool_calls[0].extra_content.google.thought_signature,
      sig,
    )
    assert.equal(canon.tool_calls[1].extra_content, undefined)
    const again = normalizeToolChatMessages([canon])
    assert.equal(
      again[0].tool_calls[0].extra_content.google.thought_signature,
      sig,
    )
    const filled = ensureGeminiThoughtSignatures([
      canonicalAssistantToolMessage('Applying.', [
        { id: 'c1', name: 'highlight_task', arguments: { task_name_or_id: 'PS[228]' } },
        { id: 'c2', name: 'set_cursors', arguments: { timestamps: [1, 2] } },
      ]),
    ])
    assert.equal(
      filled[0].tool_calls[0].extra_content.google.thought_signature,
      GEMINI_SKIP_THOUGHT_SIGNATURE,
    )
    assert.equal(filled[0].tool_calls[1].extra_content, undefined)
    assert.equal(needsGeminiThoughtSignatures({
      baseUrl: 'https://generativelanguage.googleapis.com/v1beta/openai',
      preset: 'custom',
    }), true)
    assert.equal(needsGeminiThoughtSignatures({ preset: 'gemini' }), true)
    assert.equal(needsGeminiThoughtSignatures({
      baseUrl: 'http://127.0.0.1:11434/v1',
      model: 'gemini-2.5-flash',
      preset: 'ollama',
    }), false)
  })
})
