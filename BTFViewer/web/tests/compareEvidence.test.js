import test from 'node:test'
import assert from 'node:assert/strict'
import { buildComparisonEvidence, describeCoreDistribution, formatEvidenceCell } from '../src/utils/compareEvidence.js'
const task = (values = {}) => ({ cpu: 0, runs: 0, cores: ['Core_0'], primary: 'Core_0', migrations: 0, execution: 0, blocking: 0, response: 0, ...values })
test('focused evidence preserves presence, zero baselines, migration signs and concentration', () => {
  const a = { same: task({ migrations: 2, execution: 10 }), missing: task({ migrations: 6 }) }
  const b = { same: task({ migrations: 4, execution: 20 }), added: task({ response: 100 }) }
  const out = buildComparisonEvidence(a, b, [['Task count', 2, 2]])
  assert.deepEqual(out.task_presence.map(r => [r[0], r[1], r[2], r[7]]), [['added', false, true, 'New in Candidate'], ['missing', true, false, 'Missing in Candidate']])
  const same = out.migration_concentration.find(r => r[0] === 'same')
  assert.deepEqual(same.slice(1), [2, 4, 25, 100, 75])
  assert.equal(out.timing_change_candidates.find(r => r[0] === 'same')[4], -2)
  assert.equal(out.relative_changes.find(r => r[0] === 'Response P99 / added')[4], null)
  assert.equal(formatEvidenceCell('relative_changes', null, 4), 'new')
  assert.equal(formatEvidenceCell('relative_changes', 0, 4), '0.0')
  assert.equal(out.relative_changes.find(r => r[0] === 'Execution Max / same')[4], 100)
})
test('core distribution compares actual sets and primary identity', () => {
  assert.equal(describeCoreDistribution(task(), task()), 'Stable')
  assert.equal(describeCoreDistribution(task(), task({ cores: ['Core_1'] })), 'Core set changed')
  assert.equal(describeCoreDistribution(task(), task({ cores: ['Core_0', 'Core_1'] })), 'Expanded')
  assert.equal(describeCoreDistribution(task({ cores: ['Core_0', 'Core_1'] }), task()), 'Reduced')
  assert.equal(describeCoreDistribution(task({ primary: 'Core_1' }), task()), 'Primary changed')
})
