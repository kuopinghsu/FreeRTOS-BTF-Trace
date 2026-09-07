import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { describe, it } from 'node:test'
import { zipSync, strToU8, gzipSync } from 'fflate'

import {
  MANIFEST,
  MAX_ENTRIES,
  TRACE_MEMBER,
  WORKSPACE_SCHEMA,
  buildWorkspaceBlob,
  isSafeMember,
  migrateManifest,
  openWorkspaceBlob,
  readManifestBlob,
  workspaceSha256Hex,
  workspaceTraceStatus,
} from '../src/utils/workspace.js'
import { newInvestigation, addBookmark, setConclusion } from '../src/utils/investigationNotebook.js'
import { decompressBtfEntries } from '../src/utils/btfLoad.js'

const TRACE = new TextEncoder().encode('#version 2.2.0\n#timeScale us\n100,Core_0,0,T,[0/1]W,0,resume,\n')
const OK_MANIFEST = '{"schema":"btf-viewer-workspace/1","trace":{"embedded":false}}'

function inv() {
  let i = newInvestigation({ title: 'Case' })
  i = addBookmark(i, { type: 'observation', title: 'obs', bookmarkId: 'o' })
  i = addBookmark(i, { type: 'conclusion', title: 'done', bookmarkId: 'c' })
  return setConclusion(i, 'final')
}

describe('sha256 parity', () => {
  it('matches node:crypto exactly', () => {
    for (const s of ['', 'hello world', 'a'.repeat(1000)]) {
      const bytes = new TextEncoder().encode(s)
      assert.equal(workspaceSha256Hex(bytes), createHash('sha256').update(bytes).digest('hex'))
    }
  })
})

describe('round trip', () => {
  it('save -> open restores every section', () => {
    const { blob, manifest } = buildWorkspaceBlob({
      traceBytes: TRACE, traceName: 'mini.btf',
      viewState: {
        cursors: [1, 2],
        marks: [{ id: 1, ns: 50, label: 'b', type: 'bookmark' }],
        limit: true,
      },
      health: { status: 'pass' },
      findings: [{ id: 'blocking', rule_id: 'blocking', severity: 'info' }],
      investigation: inv(),
      aiCase: { investigation_case: { finding: { id: 'f1' } }, messages: [{ role: 'user', content: 'why?' }] },
      reportHtml: '<html>r</html>',
      attachments: { 'note.txt': strToU8('hi') },
      btfviewerVersion: '1.4.0', locale: 'en', ruleSetVersion: 'wf/1',
    })
    assert.equal(manifest.schema, WORKSPACE_SCHEMA)
    assert.equal(manifest.trace.sha256, createHash('sha256').update(Buffer.from(TRACE)).digest('hex'))
    assert.ok(manifest.trace.embedded)

    const ws = openWorkspaceBlob(blob)
    assert.deepEqual(Array.from(ws.trace_bytes), Array.from(TRACE))
    assert.deepEqual(ws.view_state.cursors, [1, 2])
    assert.equal(ws.view_state.marks[0].label, 'b')
    assert.equal(ws.ai_case.messages[0].content, 'why?')
    assert.deepEqual(ws.health, { status: 'pass' })
    assert.equal(ws.findings[0].rule_id, 'blocking')
    assert.equal(ws.investigation.conclusion, 'final')
    assert.deepEqual(ws.investigation.bookmarks.map(b => b.id), ['o', 'c'])
    assert.equal(ws.report_html, '<html>r</html>')
    assert.equal(new TextDecoder().decode(ws.attachments['note.txt']), 'hi')
    assert.equal(ws.read_only, false)
    assert.equal(ws.migrated, false)
    assert.deepEqual(ws.warnings, [])
  })

  it('container is a plain zip fflate/unzip can read', () => {
    const { blob } = buildWorkspaceBlob({ traceBytes: TRACE, traceName: 't.btf', investigation: inv() })
    assert.equal(blob[0], 0x50)
    assert.equal(blob[1], 0x4b)
    const man = readManifestBlob(blob)
    assert.equal(man.schema, WORKSPACE_SCHEMA)
  })

  it('external trace reference', () => {
    const { blob, manifest } = buildWorkspaceBlob({
      traceBytes: null, traceRef: '/traces/foo.btf', traceName: 'foo.btf',
      traceSha256: 'deadbeef', traceSize: 999, embedTrace: false, investigation: inv(),
    })
    assert.equal(manifest.trace.embedded, false)
    assert.equal(manifest.trace.ref, '/traces/foo.btf')
    const ws = openWorkspaceBlob(blob)
    assert.equal(ws.trace_bytes, null)
    assert.equal(ws.trace_ref, '/traces/foo.btf')
  })

  it('is reproducible with fixed timestamps', () => {
    const kw = { traceBytes: TRACE, traceName: 't.btf', investigation: inv(), viewState: { a: 1 } }
    const a = buildWorkspaceBlob({ ...kw, created: '2020-01-01T00:00:00Z', modified: '2020-01-01T00:00:00Z' })
    const b = buildWorkspaceBlob({ ...kw, created: '2020-01-01T00:00:00Z', modified: '2020-01-01T00:00:00Z' })
    assert.deepEqual(Array.from(a.blob), Array.from(b.blob))
  })
})

describe('safety', () => {
  const zip = (members) => zipSync(Object.fromEntries(
    members.map(([n, d]) => [n, typeof d === 'string' ? strToU8(d) : d])))

  it('isSafeMember screens traversal / absolute / drive', () => {
    for (const n of ['a/b.txt', 'manifest.json', 'trace/source.btf', 'a/b/']) assert.ok(isSafeMember(n), n)
    for (const n of ['../x', 'a/../b', '/x', 'C:\\x', 'a\\b', '  s', '', 'a/./b', '~/x']) assert.ok(!isSafeMember(n), n)
  })

  it('path-traversal members are skipped, not returned', () => {
    const ws = openWorkspaceBlob(zip([
      [MANIFEST, OK_MANIFEST], ['../../etc/passwd', 'pwned'], ['/abs', 'pwned'],
    ]))
    assert.equal(ws.warnings.length, 2)
    assert.deepEqual(ws.extra_members, [])
  })

  it('rejects too many entries', () => {
    const members = [[MANIFEST, OK_MANIFEST]]
    for (let i = 0; i < MAX_ENTRIES + 2; i++) members.push([`attachments/f${i}.txt`, 'x'])
    assert.throws(() => openWorkspaceBlob(zip(members)), /too many entries/)
  })

  it('rejects a compression bomb', () => {
    const bomb = zip([[MANIFEST, OK_MANIFEST], ['attachments/big.bin', new Uint8Array(4 * 1024 * 1024)]])
    assert.throws(() => openWorkspaceBlob(bomb), /compression bomb/)
  })

  it('enforces a decompressed-size cap', () => {
    const z = zip([[MANIFEST, OK_MANIFEST], ['attachments/a.bin', crypto.getRandomValues(new Uint8Array(1024))]])
    assert.throws(() => openWorkspaceBlob(z, { maxUncompressed: 100 }), /decompressed size/)
  })

  it('rejects non-zip input and a missing manifest', () => {
    assert.throws(() => openWorkspaceBlob(new TextEncoder().encode('not a zip')), /not a .btfw/)
    assert.throws(() => openWorkspaceBlob(zip([['state/view.json', '{}']])), /no manifest/)
  })
})

describe('migration + freshness', () => {
  it('newer schema opens read-only and keeps unknown fields', () => {
    const z = zipSync({ [MANIFEST]: strToU8(JSON.stringify({
      schema: 'btf-viewer-workspace/99', trace: { embedded: false }, _new_field: { x: 1 },
    })) })
    const ws = openWorkspaceBlob(z)
    assert.equal(ws.read_only, true)
    assert.deepEqual(ws.manifest._new_field, { x: 1 })
  })

  it('migrateManifest: identity for current, stamps unknown-old', () => {
    assert.deepEqual(migrateManifest({ schema: WORKSPACE_SCHEMA, trace: {} }),
      [{ schema: WORKSPACE_SCHEMA, trace: {} }, false])
    const [out, changed] = migrateManifest({ schema: 'btf-viewer-workspace/0', trace: {} })
    assert.equal(changed, true)
    assert.equal(out.schema, WORKSPACE_SCHEMA)
  })

  it('workspaceTraceStatus detects change / missing hash / size fallback', () => {
    const { manifest } = buildWorkspaceBlob({ traceBytes: TRACE, traceName: 't.btf' })
    assert.equal(workspaceTraceStatus(manifest, { currentSha256: workspaceSha256Hex(TRACE) }).matches, true)
    const diff = workspaceTraceStatus(manifest, { currentSha256: workspaceSha256Hex(new TextEncoder().encode('other')) })
    assert.equal(diff.matches, false)
    assert.match(diff.reason, /changed/)
    assert.equal(workspaceTraceStatus(manifest).matches, null)
    assert.equal(workspaceTraceStatus({ trace: { embedded: true } }, { currentSha256: 'abc' }).matches, null)
    const sz = workspaceTraceStatus({ trace: { sha256: 'x', size: 100, embedded: false } }, { currentSize: 200 })
    assert.equal(sz.matches, false)
    assert.match(sz.reason, /size/)
  })
})

describe('cross-tool interop', () => {
  it('opens a .btfw written by workspace.py', () => {
    // A byte-for-byte reconstruction of what save_workspace() produces.
    const investigation = inv()
    const { blob } = buildWorkspaceBlob({
      traceBytes: TRACE, traceName: 'mini.btf', investigation,
      health: { status: 'caution' }, viewState: { k: 1 },
      created: '2020-01-01T00:00:00Z', modified: '2020-01-01T00:00:00Z',
    })
    // sha256 in the manifest is a real SHA-256 → a Python reader accepts it.
    const man = readManifestBlob(blob)
    assert.equal(man.trace.sha256, createHash('sha256').update(Buffer.from(TRACE)).digest('hex'))
    const ws = openWorkspaceBlob(blob)
    assert.equal(ws.investigation.conclusion, 'final')
  })

  it('decodes an embedded trace that the desktop stored gzip-compressed', () => {
    // Desktop save_workspace() embeds the trace source file's *raw* bytes, so a
    // .btf.gz (or a .btf that is really gzip) lands in the container compressed.
    // The web open path must inflate it like a normal Open, not TextDecoder it.
    const gz = gzipSync(TRACE)
    const { blob } = buildWorkspaceBlob({ traceBytes: gz, traceName: 'example-8cores.btf' })
    const ws = openWorkspaceBlob(blob)
    assert.deepEqual(ws.trace_bytes, gz)
    const naive = new TextDecoder().decode(ws.trace_bytes)
    assert.ok(!naive.startsWith('#version'), 'raw decode must not yield BTF text')
    const entries = decompressBtfEntries(ws.trace_bytes, ws.manifest.trace.name)
    assert.equal(entries.length, 1)
    assert.equal(entries[0].text, new TextDecoder().decode(TRACE))
  })

  it('opens a workspace whose manifest name says .gz but the bytes are plain', () => {
    // Anonymized / web-authored workspaces embed plain text yet keep the
    // original .btf.gz name. Stripping the compression suffix before decoding
    // lets the magic-byte sniff win → no "Not a gzipped file (b'#v')".
    const { blob } = buildWorkspaceBlob({ traceBytes: TRACE, traceName: 'example-8cores.btf.gz' })
    const ws = openWorkspaceBlob(blob)
    const decodeName = ws.manifest.trace.name.replace(/\.(gz|bz2|zip)$/i, '')
    assert.equal(decodeName, 'example-8cores.btf')
    const entries = decompressBtfEntries(ws.trace_bytes, decodeName)
    assert.equal(entries.length, 1)
    assert.equal(entries[0].text, new TextDecoder().decode(TRACE))
    assert.equal(entries[0].name, 'example-8cores.btf')
  })
})
