import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  formatElapsedSeconds,
  formatAnalysisStatus,
  toolUsageFromChatTools,
  formatToolUsageSummaryLine,
  planQueryBlocks,
} from '../src/utils/aiResponseFlow.js'

const EN = {}
const ZH = { analysis_completed: '分析完成', time_used: '用時', seconds_unit: '秒' }

describe('aiResponseFlow', () => {
  it('formats elapsed time to one decimal', () => {
    assert.equal(formatElapsedSeconds(28.268), '28.3')
    assert.equal(formatElapsedSeconds(1.84), '1.8')
    assert.equal(formatElapsedSeconds(0), '0.0')
    assert.equal(formatElapsedSeconds('bad'), '0.0')
  })

  it('formats the analysis status line per language', () => {
    assert.equal(formatAnalysisStatus(28.3, EN), 'Analysis completed · 28.3 s')
    assert.equal(formatAnalysisStatus(10.14, ZH), '分析完成 · 用時 10.1 秒')
  })

  it('rolls up chat tools so calls and unique tools agree', () => {
    const tools = [
      { name: 'query_raw_metric', status: 'applied', result: 'Max off-CPU 34.9 ms' },
      { name: 'query_raw_metric', status: 'applied', result: '' },
      { name: 'query_raw_metric', status: 'failed', result: 'no data' },
      { name: 'verify_claim', status: 'applied', result: 'inconclusive' },
    ]
    const s = toolUsageFromChatTools(tools)
    assert.equal(s.total, 4)
    assert.equal(s.unique, 2)
    assert.equal(s.failed, 1)
    assert.equal(s.groups[0].name, 'query_raw_metric')
    assert.equal(s.groups[0].count, 3)
    assert.equal(s.groups[0].failed, 1)
    assert.equal(formatToolUsageSummaryLine(tools, EN),
      'Tool usage · 4 calls / 2 tools · 1 failed')
    // grouped counts sum back to the total
    assert.equal(s.groups.reduce((n, g) => n + g.count, 0), s.total)
  })

  it('collapses a completed query into one block, hiding narration', () => {
    const msgs = [
      { role: 'user', content: 'Why the spike?', turnComplete: true, analysisElapsedS: 10.1 },
      { role: 'assistant', content: 'I will query the trace.', tools: [{ name: 'query_raw_metric', status: 'applied' }], batchId: 'b1' },
      { role: 'assistant', content: 'Let me verify this.', tools: [{ name: 'verify_claim', status: 'applied' }], batchId: 'b2' },
      { role: 'assistant', content: 'The spike aligns with an off-CPU interval.' },
    ]
    const { hidden, meta } = planQueryBlocks(msgs)
    assert.deepEqual([...hidden].sort(), [1, 2])
    assert.equal(meta.has(3), true)
    assert.equal(meta.get(3).elapsedS, 10.1)
    assert.equal(meta.get(3).tools.length, 2)
    assert.deepEqual(meta.get(3).batchIds, ['b1', 'b2'])
  })

  it('hides per-round tool-only turns even while the query is still running', () => {
    const msgs = [
      { role: 'user', content: 'q' },
      { role: 'assistant', content: '', tools: [{ name: 'set_cursors', status: 'pending' }], batchId: 'b1' },
      { role: 'assistant', content: 'Working on it…' },
    ]
    const { hidden, meta } = planQueryBlocks(msgs)
    assert.deepEqual([...hidden], [1])   // tool-only turn hidden
    assert.equal(hidden.has(2), false)   // prose stays
    assert.equal(meta.size, 0)           // no summary block until complete
  })

  it('hosts the block on the last tool turn when there is no written answer', () => {
    const msgs = [
      { role: 'user', content: 'q', turnComplete: true, analysisElapsedS: 3 },
      { role: 'assistant', content: '', tools: [{ name: 'query_raw_metric', status: 'applied' }], batchId: 'b1' },
    ]
    const { hidden, meta } = planQueryBlocks(msgs)
    assert.equal(hidden.size, 0)
    assert.equal(meta.has(1), true)
  })

  it('never hides the Evidence & Validation panel or other non-assistant entries', () => {
    const msgs = [
      { role: 'user', content: 'q', turnComplete: true, analysisElapsedS: 5 },
      { role: 'assistant', content: 'I will query.', tools: [{ name: 'query_raw_metric', status: 'applied' }], batchId: 'b1' },
      { role: 'assistant', content: 'The answer.' },
      { role: 'evidence', content: '**Verdict:** Correlated' },
    ]
    const { hidden, meta } = planQueryBlocks(msgs)
    assert.deepEqual([...hidden], [1])
    assert.equal(meta.has(2), true)
    assert.equal(hidden.has(3), false)
  })

  it('zero-tool completed query gets meta with no tools', () => {
    const msgs = [
      { role: 'user', content: 'q', turnComplete: true, analysisElapsedS: 1.8 },
      { role: 'assistant', content: 'Short answer.' },
    ]
    const { meta } = planQueryBlocks(msgs)
    assert.equal(meta.get(1).tools.length, 0)
  })
})
