import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  formatDeadlinesText,
  parseDeadlinesText,
  shouldReplaceDeadlinesText,
} from '../src/utils/settingsStore.js'

describe('task deadlines textarea', () => {
  it('parses complete TaskName=ns lines', () => {
    assert.deepEqual(parseDeadlinesText('Runner1=500000\n# skip\nFoo=1000'), {
      Runner1: 500000,
      Foo: 1000,
    })
  })

  it('ignores incomplete lines while typing', () => {
    assert.deepEqual(parseDeadlinesText('Run'), {})
    assert.deepEqual(parseDeadlinesText('Runner1='), {})
    assert.deepEqual(parseDeadlinesText('Runner1=500000\nBar'), {
      Runner1: 500000,
    })
  })

  it('does not wipe in-progress text on preview round-trip', () => {
    // User typed an incomplete line; preview parsed to {} and pushed that back.
    assert.equal(shouldReplaceDeadlinesText('Run', {}), false)
    assert.equal(shouldReplaceDeadlinesText('Runner1=', {}), false)
    assert.equal(
      shouldReplaceDeadlinesText('Runner1=500000\nBar', { Runner1: 500000 }),
      false,
    )
  })

  it('still syncs when deadlines actually change (Reset / load)', () => {
    assert.equal(shouldReplaceDeadlinesText('Runner1=500000', {}), true)
    assert.equal(
      shouldReplaceDeadlinesText('', { Runner1: 500000 }),
      true,
    )
    assert.equal(
      shouldReplaceDeadlinesText('Runner1=500000', { Runner1: 500000 }),
      false,
    )
  })

  it('round-trips format ↔ parse for stable maps', () => {
    const map = { A: 1, B: 2 }
    assert.equal(
      formatDeadlinesText(parseDeadlinesText(formatDeadlinesText(map))),
      formatDeadlinesText(map),
    )
  })
})
