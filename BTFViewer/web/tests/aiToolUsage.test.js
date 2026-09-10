import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  AI_TOOL_USAGE_CATEGORIES,
  aiToolUsageCategory,
  isTraceQueryTool,
  recordToolUsage,
  seedToolUsage,
  summarizeToolUsage,
  toolBriefResult,
} from '../src/utils/aiToolUsage.js'

describe('aiToolUsage authoritative record', () => {
  it('categorises tools into a stable set', () => {
    assert.deepEqual(AI_TOOL_USAGE_CATEGORIES, ['Evidence', 'Analysis', 'Verification', 'Viewer'])
    assert.equal(aiToolUsageCategory('query_raw_metric'), 'Evidence')
    assert.equal(aiToolUsageCategory('search_timeline'), 'Evidence')
    assert.equal(aiToolUsageCategory('correlate_events'), 'Analysis')
    assert.equal(aiToolUsageCategory('find_critical_path'), 'Analysis')
    assert.equal(aiToolUsageCategory('verify_claim'), 'Verification')
    assert.equal(aiToolUsageCategory('challenge_conclusion'), 'Verification')
    assert.equal(aiToolUsageCategory('set_cursors'), 'Viewer')
    assert.equal(aiToolUsageCategory('highlight_task'), 'Viewer')
    assert.equal(aiToolUsageCategory('totally_unknown_tool'), 'Analysis')
  })

  it('trace queries are exactly the Evidence category', () => {
    assert.equal(isTraceQueryTool('query_raw_metric'), true)
    assert.equal(isTraceQueryTool('correlate_events'), false)
    assert.equal(isTraceQueryTool('set_cursors'), false)
  })

  it('summarises an empty record', () => {
    const s = summarizeToolUsage({ calls: [] })
    assert.equal(s.total, 0)
    assert.equal(s.unique, 0)
    assert.equal(s.ok, 0)
    assert.equal(s.failed, 0)
    assert.equal(s.traceQueries, 0)
    assert.deepEqual(s.groups, [])
  })

  it('records one call with a brief', () => {
    const u = recordToolUsage({ calls: [] }, {
      name: 'query_raw_metric',
      result: { ok: true, data: { metric: 'off_cpu', id: 267, stat: 'Max', value: 34.924, unit: ' ms' } },
    })
    const s = summarizeToolUsage(u)
    assert.equal(s.total, 1)
    assert.equal(s.unique, 1)
    assert.equal(s.traceQueries, 1)
    assert.equal(s.groups[0].brief, 'Found off_cpu[267] Max = 34.924 ms')
  })

  it('groups repeated calls to one row with a count', () => {
    let u = { calls: [] }
    for (let i = 0; i < 3; i += 1) {
      u = recordToolUsage(u, { name: 'query_raw_metric', result: { ok: true } })
    }
    u = recordToolUsage(u, { name: 'search_timeline', result: { ok: true } })
    const s = summarizeToolUsage(u)
    assert.equal(s.total, 4)
    assert.equal(s.unique, 2)
    assert.equal(s.groups[0].name, 'query_raw_metric')
    assert.equal(s.groups[0].count, 3)
    assert.equal(s.groups[1].count, 1)
  })

  it('counts failed calls and per-category totals', () => {
    let u = { calls: [] }
    u = recordToolUsage(u, { name: 'query_raw_metric', result: { ok: true } })
    u = recordToolUsage(u, { name: 'query_raw_metric', result: { ok: false, error: 'no data' } })
    u = recordToolUsage(u, { name: 'correlate_events', result: { ok: true } })
    u = recordToolUsage(u, { name: 'verify_claim', result: { ok: true, data: { verdict: 'inconclusive' } } })
    u = recordToolUsage(u, { name: 'set_cursors', result: { ok: true } })
    const s = summarizeToolUsage(u)
    assert.equal(s.ok, 4)
    assert.equal(s.failed, 1)
    assert.equal(s.traceQueries, 2)
    assert.deepEqual(s.byCategory, { Evidence: 2, Analysis: 1, Verification: 1, Viewer: 1 })
    assert.equal(s.groups[0].failed, 1)
  })

  it('seedToolUsage builds a record from names only', () => {
    const s = summarizeToolUsage(seedToolUsage(['query_raw_metric', 'verify_claim', { name: 'set_cursors' }]))
    assert.equal(s.total, 3)
    assert.equal(s.ok, 3)
    assert.equal(s.failed, 0)
  })

  it('toolBriefResult keeps verify verdicts factual and never invents text', () => {
    assert.equal(
      toolBriefResult('verify_claim', { data: { verdict: 'inconclusive', reason: 'mutex ownership was not established' } }),
      'Inconclusive — mutex ownership was not established',
    )
    assert.equal(toolBriefResult('verify_claim', { data: { verdict: 'confirmed' } }), 'Confirmed')
    assert.equal(toolBriefResult('set_cursors', { ok: true }), '')
    assert.equal(toolBriefResult('correlate_events', { ok: true, message: 'ok' }), '')
  })
})
