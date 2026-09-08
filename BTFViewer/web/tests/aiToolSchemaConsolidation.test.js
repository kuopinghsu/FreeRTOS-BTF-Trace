import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import { aiViewerTools, aiViewerToolsForMode, AI_VIEWER_TOOL_NAMES } from '../src/utils/aiTools.js'
import { AI_TOOL_MODEL_HIDDEN, toolNamesForContextMode } from '../src/utils/aiCase.js'

const emitted = () => aiViewerTools().map(t => t.function.name)
const modeNames = (m, s) => aiViewerToolsForMode(m, s).map(t => t.function.name)
const ON_REQUEST = [
  'what_if', 'optimize_experiment', 'recommend_experiments',
  'investigation_memory', 'find_similar_investigations',
  'record_experiment_outcome', 'close_investigation',
  'generate_report', 'export_report', 'export_investigation', 'cluster_findings',
]

describe('AI tool-schema consolidation', () => {
  it('functional aliases are not model-visible schemas but still dispatch', () => {
    const names = emitted()
    for (const alias of AI_TOOL_MODEL_HIDDEN) {
      assert.ok(!names.includes(alias), alias)
      assert.ok(AI_VIEWER_TOOL_NAMES.includes(alias), `${alias} still dispatchable`)
    }
    assert.deepEqual(
      names,
      AI_VIEWER_TOOL_NAMES.filter(n => !AI_TOOL_MODEL_HIDDEN.includes(n)),
    )
  })

  it('Full Evidence is a bounded subset, not the whole catalog', () => {
    const all = new Set(emitted())
    for (const stage of ['triage', 'investigate', 'experiment', 'report', 'verify', 'compare']) {
      const full = new Set(modeNames('full', stage))
      assert.ok(full.size < all.size, stage)
    }
  })

  it('Full Evidence keeps the measured-evidence loop', () => {
    const full = new Set(modeNames('full', 'triage'))
    for (const t of ['investigate', 'correlate_events', 'compare_performance',
      'regression_explain', 'detect_anomalies', 'query_raw_metric', 'verify_claim']) {
      assert.ok(full.has(t), t)
    }
  })

  it('ordinary triage excludes simulation / optimization / memory / clustering / export', () => {
    for (const mode of ['compact', 'balanced', 'full']) {
      const names = new Set(toolNamesForContextMode(mode, 'triage'))
      for (const gated of ON_REQUEST) assert.ok(!names.has(gated), `${mode}/${gated}`)
    }
  })

  it('experiment / report stages bring their capability tools back', () => {
    const exp = new Set(modeNames('full', 'experiment'))
    for (const t of ['what_if', 'optimize_experiment', 'recommend_experiments']) assert.ok(exp.has(t), t)
    const rep = new Set(modeNames('full', 'report'))
    for (const t of ['generate_report', 'export_report', 'export_investigation']) assert.ok(rep.has(t), t)
  })

  it('snapshot: small modes', () => {
    assert.deepEqual(toolNamesForContextMode('compact', 'triage'), [
      'detect_anomalies', 'suggest_scope', 'search_timeline',
      'query_raw_metric', 'summarize_investigation_context',
    ])
    assert.equal(toolNamesForContextMode('full', 'triage').length, 43)
  })
})
