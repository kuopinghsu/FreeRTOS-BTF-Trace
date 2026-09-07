/**
 * Portable Workspace (.btfw) — versioned, ZIP-compatible container.
 * Keep in sync with btf_viewer_pkg/workspace.py.
 *
 * A .btfw saves the complete investigation state — the trace, the view state,
 * the deterministic analysis (health + findings), the investigation notebook,
 * and optionally a rendered report — in one file that stays inspectable with
 * any ZIP tool and depends on no installed BTFViewer or online service.
 *
 * Opening rejects absolute paths and `..` segments, caps entry count and
 * decompressed size, guards against compression bombs, never executes
 * workspace content, and never fetches remote resources. Unknown fields are
 * preserved; older schemas migrate, newer ones open read-only.
 */
import { zipSync, strToU8, strFromU8 } from 'fflate'

import { loadInvestigation } from './investigationNotebook.js'
import {
  CONTAINER_MAX_COMPRESSION_RATIO,
  CONTAINER_MAX_ENTRIES,
  CONTAINER_MAX_UNCOMPRESSED_BYTES,
  isSafeMember,
  readZipContainer,
} from './zipContainer.js'

export const WORKSPACE_SCHEMA_PREFIX = 'btf-viewer-workspace/'
export const WORKSPACE_VERSION = 1
export const WORKSPACE_SCHEMA = `${WORKSPACE_SCHEMA_PREFIX}${WORKSPACE_VERSION}`
export const WORKSPACE_EXT = '.btfw'

export const MANIFEST = 'manifest.json'
export const TRACE_MEMBER = 'trace/source.btf'
export const STATE_VIEW = 'state/view.json'
export const ANALYSIS_HEALTH = 'analysis/health.json'
export const ANALYSIS_FINDINGS = 'analysis/findings.json'
export const INVESTIGATION_BOOKMARKS = 'investigation/bookmarks.json'
export const INVESTIGATION_AI_CASE = 'investigation/ai_case.json'
export const REPORT_HTML = 'reports/report.html'
export const ATTACHMENTS_PREFIX = 'attachments/'

const KNOWN_MEMBERS = [
  MANIFEST, TRACE_MEMBER, STATE_VIEW, ANALYSIS_HEALTH,
  ANALYSIS_FINDINGS, INVESTIGATION_BOOKMARKS, INVESTIGATION_AI_CASE, REPORT_HTML,
]

// Archive-level caps come from the shared reader (zipContainer.js); only the
// manifest cap is workspace-only.
export const MAX_ENTRIES = CONTAINER_MAX_ENTRIES
export const MAX_UNCOMPRESSED_BYTES = CONTAINER_MAX_UNCOMPRESSED_BYTES
export const MAX_COMPRESSION_RATIO = CONTAINER_MAX_COMPRESSION_RATIO
export const MANIFEST_MAX_BYTES = 1 * 1024 * 1024
const CONTAINER_DESC = '.btfw / ZIP'

export { isSafeMember }

const FIXED_MTIME = new Date(Date.UTC(1980, 0, 1))

// ---------------------------------------------------------------------------
// Synchronous SHA-256 so trace/attachment hashes match workspace.py exactly
// (a .btfw is a cross-tool format). Small, dependency-free, no Web Crypto
// async ceremony.
const _K = new Uint32Array([
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
])

export function workspaceSha256Hex(bytes) {
  const msg = bytes instanceof Uint8Array ? bytes : new Uint8Array(0)
  const bitLen = msg.length * 8
  const withPad = new Uint8Array((((msg.length + 8) >> 6) + 1) << 6)
  withPad.set(msg)
  withPad[msg.length] = 0x80
  const dv = new DataView(withPad.buffer)
  dv.setUint32(withPad.length - 4, bitLen >>> 0, false)
  dv.setUint32(withPad.length - 8, Math.floor(bitLen / 0x100000000), false)

  const h = new Uint32Array([
    0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
    0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
  ])
  const w = new Uint32Array(64)
  const rotr = (x, n) => (x >>> n) | (x << (32 - n))

  for (let off = 0; off < withPad.length; off += 64) {
    for (let i = 0; i < 16; i++) w[i] = dv.getUint32(off + i * 4, false)
    for (let i = 16; i < 64; i++) {
      const s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >>> 3)
      const s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >>> 10)
      w[i] = (w[i - 16] + s0 + w[i - 7] + s1) >>> 0
    }
    let [a, b, c, d, e, f, g, hh] = h
    for (let i = 0; i < 64; i++) {
      const S1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)
      const ch = (e & f) ^ (~e & g)
      const t1 = (hh + S1 + ch + _K[i] + w[i]) >>> 0
      const S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)
      const maj = (a & b) ^ (a & c) ^ (b & c)
      const t2 = (S0 + maj) >>> 0
      hh = g; g = f; f = e; e = (d + t1) >>> 0
      d = c; c = b; b = a; a = (t1 + t2) >>> 0
    }
    h[0] = (h[0] + a) >>> 0; h[1] = (h[1] + b) >>> 0; h[2] = (h[2] + c) >>> 0; h[3] = (h[3] + d) >>> 0
    h[4] = (h[4] + e) >>> 0; h[5] = (h[5] + f) >>> 0; h[6] = (h[6] + g) >>> 0; h[7] = (h[7] + hh) >>> 0
  }
  let out = ''
  for (let i = 0; i < 8; i++) out += h[i].toString(16).padStart(8, '0')
  return out
}

export function nowIso(when = null) {
  const d = when instanceof Date ? when : new Date()
  return d.toISOString().replace(/\.\d{3}Z$/, 'Z')
}

function dumps(obj) {
  return strToU8(JSON.stringify(sortKeys(obj), null, 2) + '\n')
}

function sortKeys(v) {
  if (Array.isArray(v)) return v.map(sortKeys)
  if (v && typeof v === 'object') {
    const out = {}
    for (const k of Object.keys(v).sort()) out[k] = sortKeys(v[k])
    return out
  }
  return v
}

function sanitizeAttachmentName(name) {
  let base = String(name || '').replace(/\\/g, '/')
  base = base.slice(base.lastIndexOf('/') + 1).trim().replace(/^\.+/, '') || 'attachment'
  base = [...base].filter(c => /[a-zA-Z0-9\-._ ()]/.test(c)).join('').trim()
  return base || 'attachment'
}

// ---------------------------------------------------------------------------
export function buildManifest({
  btfviewerVersion = '', traceName = '', traceSize = 0, traceSha256 = '',
  traceEmbedded = true, traceRef = '', analysisSettings = null,
  ruleSetVersion = '', locale = '', report = null, attachments = null,
  contents = null, created = null, modified = null,
} = {}) {
  const stamp = nowIso()
  return {
    schema: WORKSPACE_SCHEMA,
    btfviewer_version: String(btfviewerVersion || ''),
    created: String(created || stamp),
    modified: String(modified || stamp),
    trace: {
      name: String(traceName || ''),
      size: Number(traceSize || 0),
      sha256: String(traceSha256 || ''),
      embedded: !!traceEmbedded,
      ref: traceEmbedded ? '' : String(traceRef || ''),
    },
    analysis: {
      settings: { ...(analysisSettings || {}) },
      rule_set_version: String(ruleSetVersion || ''),
    },
    locale: String(locale || ''),
    report: (report && typeof report === 'object') ? { ...report } : null,
    attachments: [...(attachments || [])],
    contents: [...new Set(contents || [])].sort(),
  }
}

// --- migration -------------------------------------------------------------
function schemaVersion(schema) {
  const s = String(schema || '')
  if (!s.startsWith(WORKSPACE_SCHEMA_PREFIX)) return null
  const n = Number(s.slice(WORKSPACE_SCHEMA_PREFIX.length))
  return Number.isInteger(n) ? n : null
}

const MIGRATIONS = {}

export function migrateManifest(manifest) {
  let out = { ...(manifest || {}) }
  let ver = schemaVersion(out.schema)
  if (ver == null || ver >= WORKSPACE_VERSION) return [out, false]
  let changed = false
  while (ver < WORKSPACE_VERSION && MIGRATIONS[ver]) {
    out = MIGRATIONS[ver]({ ...out })
    ver += 1
    out.schema = `${WORKSPACE_SCHEMA_PREFIX}${ver}`
    changed = true
  }
  if (ver < WORKSPACE_VERSION) {
    out.schema = WORKSPACE_SCHEMA
    changed = true
  }
  return [out, changed]
}

// --- save ----------------------------------------------------------------
export function buildWorkspaceBlob({
  traceBytes = null, traceRef = '', traceName = '', traceSha256 = '',
  traceSize = null, embedTrace = true,
  viewState = null, health = null, findings = null, investigation = null,
  aiCase = null,
  reportHtml = null, attachments = null, analysisSettings = null,
  ruleSetVersion = '', locale = '', btfviewerVersion = '',
  created = null, modified = null,
} = {}) {
  const embedded = !!(embedTrace && traceBytes)
  let sha = traceSha256
  let size = traceSize
  if (embedded) {
    size = traceBytes.length
    if (!sha) sha = workspaceSha256Hex(traceBytes)
  } else {
    size = Number(size || 0)
  }

  const attItems = []
  const attManifest = []
  const seen = new Set()
  for (const [rawName, blob] of Object.entries(attachments || {})) {
    let nm = sanitizeAttachmentName(rawName)
    while (seen.has(nm)) nm = '_' + nm
    seen.add(nm)
    const data = blob instanceof Uint8Array ? blob : strToU8(String(blob))
    attItems.push([ATTACHMENTS_PREFIX + nm, data])
    attManifest.push({ name: nm, size: data.length, sha256: workspaceSha256Hex(data) })
  }

  const contents = []
  if (viewState != null) contents.push(STATE_VIEW)
  if (health != null) contents.push(ANALYSIS_HEALTH)
  if (findings != null) contents.push(ANALYSIS_FINDINGS)
  if (investigation != null) contents.push(INVESTIGATION_BOOKMARKS)
  if (aiCase != null) contents.push(INVESTIGATION_AI_CASE)
  if (reportHtml != null) contents.push(REPORT_HTML)
  if (embedded) contents.push(TRACE_MEMBER)
  for (const [nm] of attItems) contents.push(nm)

  let reportMeta = null
  if (reportHtml != null) {
    const rb = strToU8(reportHtml)
    reportMeta = { path: REPORT_HTML, size: rb.length, sha256: workspaceSha256Hex(rb) }
  }

  const manifest = buildManifest({
    btfviewerVersion,
    traceName: traceName || (traceRef ? traceRef.split('/').pop() : ''),
    traceSize: size,
    traceSha256: sha,
    traceEmbedded: embedded,
    traceRef,
    analysisSettings,
    ruleSetVersion,
    locale,
    report: reportMeta,
    attachments: attManifest,
    contents,
    created,
    modified,
  })

  const files = { [MANIFEST]: [dumps(manifest), { mtime: FIXED_MTIME }] }
  if (embedded) files[TRACE_MEMBER] = [traceBytes, { mtime: FIXED_MTIME }]
  if (viewState != null) files[STATE_VIEW] = [dumps(viewState), { mtime: FIXED_MTIME }]
  if (health != null) files[ANALYSIS_HEALTH] = [dumps(health), { mtime: FIXED_MTIME }]
  if (findings != null) files[ANALYSIS_FINDINGS] = [dumps([...findings]), { mtime: FIXED_MTIME }]
  if (investigation != null) files[INVESTIGATION_BOOKMARKS] = [dumps(loadInvestigation(investigation)), { mtime: FIXED_MTIME }]
  if (aiCase != null) files[INVESTIGATION_AI_CASE] = [dumps(aiCase), { mtime: FIXED_MTIME }]
  if (reportHtml != null) files[REPORT_HTML] = [strToU8(reportHtml), { mtime: FIXED_MTIME }]
  for (const [nm, data] of attItems) files[nm] = [data, { mtime: FIXED_MTIME }]

  return { blob: zipSync(files, { level: 6 }), manifest }
}

// --- open (hardened) -------------------------------------------------------
// The archive is read through the shared hardened container reader
// (zipContainer.js); everything below is .btfw interpretation on top of the
// safe member map it returns.
function readJsonMember(members, name) {
  if (!(name in members)) return null
  try {
    return JSON.parse(strFromU8(members[name]))
  } catch {
    return null
  }
}

export function readManifestBlob(bytes) {
  const { members } = readZipContainer(bytes, { containerDesc: CONTAINER_DESC })
  if (!(MANIFEST in members)) throw new Error('workspace has no manifest.json')
  if (members[MANIFEST].length > MANIFEST_MAX_BYTES) {
    throw new Error('manifest.json is implausibly large')
  }
  const raw = JSON.parse(strFromU8(members[MANIFEST]))
  return migrateManifest(raw)[0]
}

export function openWorkspaceBlob(bytes, {
  maxEntries = MAX_ENTRIES, maxUncompressed = MAX_UNCOMPRESSED_BYTES, loadReport = true,
} = {}) {
  const { members, warnings } = readZipContainer(bytes, {
    containerDesc: CONTAINER_DESC, maxEntries, maxUncompressed,
  })
  if (!(MANIFEST in members)) throw new Error('workspace has no manifest.json')
  if (members[MANIFEST].length > MANIFEST_MAX_BYTES) {
    throw new Error('manifest.json is implausibly large')
  }

  const rawManifest = JSON.parse(strFromU8(members[MANIFEST]))
  const rawVer = schemaVersion(rawManifest.schema)
  const readOnly = rawVer != null && rawVer > WORKSPACE_VERSION
  const [manifest, migrated] = migrateManifest(rawManifest)

  const traceMeta = manifest.trace || {}
  let traceBytes = null
  if (traceMeta.embedded && (TRACE_MEMBER in members)) {
    traceBytes = members[TRACE_MEMBER]
    if (traceMeta.sha256 && workspaceSha256Hex(traceBytes) !== traceMeta.sha256) {
      warnings.push('embedded trace hash does not match the manifest')
    }
  }

  const rawInv = readJsonMember(members, INVESTIGATION_BOOKMARKS)
  const attachments = {}
  const extra = []
  for (const name of Object.keys(members).sort()) {
    if (name.startsWith(ATTACHMENTS_PREFIX)) attachments[name.slice(ATTACHMENTS_PREFIX.length)] = members[name]
    else if (!KNOWN_MEMBERS.includes(name)) extra.push(name)
  }

  return {
    manifest,
    schema: manifest.schema,
    read_only: readOnly,
    migrated,
    trace_bytes: traceBytes,
    trace_embedded: !!traceMeta.embedded,
    trace_ref: String(traceMeta.ref || ''),
    view_state: readJsonMember(members, STATE_VIEW),
    health: readJsonMember(members, ANALYSIS_HEALTH),
    findings: readJsonMember(members, ANALYSIS_FINDINGS),
    investigation: rawInv != null ? loadInvestigation(rawInv) : null,
    ai_case: readJsonMember(members, INVESTIGATION_AI_CASE),
    report_html: (loadReport && (REPORT_HTML in members)) ? strFromU8(members[REPORT_HTML]) : null,
    attachments,
    extra_members: extra.sort(),
    warnings,
  }
}

// --- trace freshness --------------------------------------------------
export function workspaceTraceStatus(manifest, { currentSha256 = '', currentSize = null } = {}) {
  const trace = (manifest || {}).trace || {}
  const stored = String(trace.sha256 || '')
  const embedded = !!trace.embedded
  const ref = String(trace.ref || '')
  if (!currentSha256 && currentSize == null) {
    return { embedded, referenced: ref, matches: null, reason: 'no current trace to compare' }
  }
  if (!stored) {
    return { embedded, referenced: ref, matches: null, reason: 'workspace stored no trace hash' }
  }
  if (currentSha256) {
    return currentSha256 === stored
      ? { embedded, referenced: ref, matches: true, reason: 'trace hash matches' }
      : { embedded, referenced: ref, matches: false, reason: 'trace content changed since the workspace was saved' }
  }
  if (currentSize != null && Number(currentSize) !== Number(trace.size ?? -1)) {
    return { embedded, referenced: ref, matches: false, reason: 'trace size changed since the workspace was saved' }
  }
  return { embedded, referenced: ref, matches: null, reason: 'size matches but content not verified' }
}
