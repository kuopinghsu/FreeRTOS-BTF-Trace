import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  btfSliceFilename,
  cursorRange,
  defaultExportTarget,
  exportBaseName,
  exportTargets,
  perfettoFilename,
  workspaceFilename,
} from '../src/utils/exportActions.js'

describe('exportActions filenames', () => {
  it('strips known trace extensions before appending a new one', () => {
    assert.equal(exportBaseName('demo.btf'), 'demo')
    assert.equal(exportBaseName('demo.btf.gz'), 'demo')
    assert.equal(exportBaseName('demo.btf.bz2'), 'demo')
    assert.equal(exportBaseName('demo.btf.zip'), 'demo')
    assert.equal(exportBaseName('demo.gz'), 'demo')
    assert.equal(exportBaseName('demo.json'), 'demo')
    assert.equal(exportBaseName('demo.btfw'), 'demo')
    assert.equal(exportBaseName('demo.v2'), 'demo.v2')
    assert.equal(exportBaseName('', 'x'), 'x')
    assert.equal(perfettoFilename('a.btf'), 'a.json')
    assert.equal(workspaceFilename('a.btf'), 'a.btfw')
    // example-8cores.btf.gz must become example-8cores.btfw, not …btf.btfw
    assert.equal(workspaceFilename('example-8cores.btf.gz'), 'example-8cores.btfw')
    assert.equal(perfettoFilename('example-8cores.btf.gz'), 'example-8cores.json')
    assert.equal(btfSliceFilename('a.btf', 10, 20), 'a_10-20.btf')
  })
})

describe('cursorRange', () => {
  it('returns min/max only with >=2 distinct finite cursors', () => {
    assert.deepEqual(cursorRange([30, 10, 20]), { lo: 10, hi: 30 })
    assert.equal(cursorRange([5]), null)
    assert.equal(cursorRange([5, 5]), null)
    // Non-finite entries are dropped (caller passes already-placed cursors).
    assert.equal(cursorRange([7, undefined, NaN]), null)
    assert.deepEqual(cursorRange([7, 9]), { lo: 7, hi: 9 })
  })
})

describe('exportTargets / defaultExportTarget', () => {
  it('gates every target on a trace', () => {
    const rows = exportTargets({ hasTrace: false })
    assert.equal(rows.length, 3)
    assert.ok(rows.every((r) => !r.available && r.reason))
  })

  it('gates the BTF slice on two cursors', () => {
    const rows = exportTargets({ hasTrace: true, placedCursorCount: 1 })
    const byId = Object.fromEntries(rows.map((r) => [r.id, r]))
    assert.equal(byId.workspace.available, true)
    assert.equal(byId.perfetto.available, true)
    assert.equal(byId['btf-slice'].available, false)
    assert.match(byId['btf-slice'].reason, /two cursors/)

    const ok = exportTargets({ hasTrace: true, placedCursorCount: 2 })
    assert.equal(ok.find((r) => r.id === 'btf-slice').available, true)
  })

  it('defaultExportTarget prefers the requested target when available', () => {
    const rows = exportTargets({ hasTrace: true, placedCursorCount: 0 })
    assert.equal(defaultExportTarget(rows, 'perfetto'), 'perfetto')
    assert.equal(defaultExportTarget(rows, 'btf-slice'), 'workspace')
    assert.equal(defaultExportTarget(exportTargets({ hasTrace: false }), 'perfetto'), 'workspace')
  })
})
