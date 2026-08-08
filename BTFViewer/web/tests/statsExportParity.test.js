import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { describe, it } from 'node:test'

const stats = readFileSync(new URL('../src/components/StatisticsPanel.vue', import.meta.url), 'utf8')

describe('mutex/queue export parity with desktop', () => {
  it('CSV summary includes Bounces and lock-bounce subsection', () => {
    assert.match(stats, /Object,Kind,Holds,Issues,Bounces,Avg hold,Status/)
    assert.match(stats, /Core Affinity Violations \(lock bounce\)/)
    assert.match(stats, /hold\(s\) crossed core boundaries/)
  })

  it('HTML mutex and queue summaries include a Bounces column', () => {
    assert.match(stats, /<th>Bounces<\/th><th>Avg hold<\/th><th>Status<\/th>/)
    assert.match(stats, /<th>Issues<\/th><th>Bounces<\/th><th>Avg hold<\/th><th>Status<\/th>/)
  })
})
