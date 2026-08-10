/**
 * Load BTF text from a plain .btf file or a gz / bz2 / zip container.
 */

import { gunzipSync, unzipSync } from 'fflate'
import bz2 from 'bz2'

const BTF_NAME_RE = /\.btf(\.(gz|bz2|zip))?$/i
const ARCHIVE_RE = /\.(gz|bz2|zip)$/i

/** @param {string} name */
export function isBtfOpenName(name) {
  const lower = String(name || '').toLowerCase()
  return lower.endsWith('.btf')
    || lower.endsWith('.btf.gz')
    || lower.endsWith('.btf.bz2')
    || lower.endsWith('.btf.zip')
    || lower.endsWith('.gz')
    || lower.endsWith('.bz2')
    || lower.endsWith('.zip')
}

/** File picker `accept` attribute value. */
export const BTF_FILE_ACCEPT = '.btf,.btf.gz,.gz,.btf.bz2,.bz2,.btf.zip,.zip'

/** showOpenFilePicker accept map. */
export const BTF_FILE_PICKER_ACCEPT = {
  'application/octet-stream': [
    '.btf', '.btf.gz', '.gz', '.btf.bz2', '.bz2', '.btf.zip', '.zip',
  ],
  'text/plain': ['.btf'],
  'application/gzip': ['.gz', '.btf.gz'],
  'application/x-bzip2': ['.bz2', '.btf.bz2'],
  'application/zip': ['.zip', '.btf.zip'],
}

/**
 * @param {Uint8Array} bytes
 * @returns {'gzip'|'bz2'|'zip'|''}
 */
export function sniffCompression(bytes) {
  if (!bytes || bytes.length < 3) return ''
  if (bytes[0] === 0x1f && bytes[1] === 0x8b) return 'gzip'
  if (bytes[0] === 0x42 && bytes[1] === 0x5a && bytes[2] === 0x68) return 'bz2'
  if (bytes[0] === 0x50 && bytes[1] === 0x4b) return 'zip'
  return ''
}

/**
 * @param {string} name
 * @returns {'gzip'|'bz2'|'zip'|''}
 */
export function compressionFromName(name) {
  const lower = String(name || '').toLowerCase()
  if (lower.endsWith('.gz') || lower.endsWith('.btf.gz')) return 'gzip'
  if (lower.endsWith('.bz2') || lower.endsWith('.btf.bz2')) return 'bz2'
  if (lower.endsWith('.zip') || lower.endsWith('.btf.zip')) return 'zip'
  return ''
}

/** @param {string} member */
function zipMemberBaseName(member) {
  const parts = String(member || '').replace(/\\/g, '/').split('/')
  return parts[parts.length - 1] || member
}

/**
 * Unique tab labels for zip members (bare basename, or full path on collision).
 * Multi-member archives prefix ``archive.zip::`` so two zips with the same
 * ``foo.btf`` stay distinct (desktop ``zip::member`` parity).
 * @param {string[]} members
 * @param {string} [archiveName]
 * @returns {string[]}
 */
export function zipMemberDisplayNames(members, archiveName = '') {
  const archive = zipMemberBaseName(archiveName)
  const bases = members.map(zipMemberBaseName)
  const counts = new Map()
  for (const b of bases) counts.set(b, (counts.get(b) || 0) + 1)
  return members.map((m, i) => {
    const base = bases[i]
    const inner = (counts.get(base) || 0) > 1 ? String(m).replace(/\\/g, '/') : base
    if (archive && members.length > 1) return `${archive}::${inner}`
    return inner
  })
}

/**
 * @param {string[]} names
 * @returns {string[]}
 */
export function listZipBtfMembers(names) {
  const files = (names || []).filter(n => n && !n.endsWith('/') && !n.endsWith('\\'))
  const btf = files.filter(n => {
    const l = n.toLowerCase()
    return l.endsWith('.btf') && !l.endsWith('.btf.gz') && !l.endsWith('.btf.bz2')
  })
  return btf.slice().sort((a, b) => {
    const da = (a.match(/[/\\]/g) || []).length
    const db = (b.match(/[/\\]/g) || []).length
    if (da !== db) return da - db
    return a.toLowerCase().localeCompare(b.toLowerCase())
  })
}

/**
 * @param {string[]} names
 * @returns {string}
 */
export function zipNoBtfMessage(names) {
  const files = (names || []).filter(n => n && !n.endsWith('/') && !n.endsWith('\\'))
  if (!files.length) return 'ZIP archive contains no files'
  const sample = files.slice().sort().slice(0, 8).join(', ')
  const more = files.length > 8 ? '…' : ''
  return `ZIP archive has no .btf member (found: ${sample}${more})`
}

/**
 * @param {Record<string, Uint8Array>|string[]} filesOrNames
 * @returns {string}
 */
export function pickZipBtfMember(filesOrNames) {
  const names = Array.isArray(filesOrNames)
    ? filesOrNames
    : Object.keys(filesOrNames || {})
  const btf = listZipBtfMembers(names)
  if (btf.length === 1) return btf[0]
  if (btf.length > 1) {
    const top = btf.filter(n => !n.includes('/') && !n.includes('\\'))
    return (top.length ? top : btf).slice().sort()[0]
  }
  throw new Error(zipNoBtfMessage(names))
}

function utf8Decode(bytes) {
  return new TextDecoder('utf-8', { fatal: false }).decode(bytes)
}

/**
 * @typedef {{ name: string, text: string }} BtfEntry
 */

/**
 * Decompress bytes into one or more BTF text entries (multi-BTF zip → many).
 * @param {Uint8Array} bytes
 * @param {string} [name]
 * @returns {BtfEntry[]}
 */
export function decompressBtfEntries(bytes, name = '') {
  const kind = sniffCompression(bytes) || compressionFromName(name)
  if (!kind) {
    return [{ name: name || 'trace.btf', text: utf8Decode(bytes) }]
  }

  if (kind === 'gzip') {
    const outName = (name && name.replace(/\.gz$/i, '')) || 'trace.btf'
    return [{ name: outName.endsWith('.btf') ? outName : `${outName}.btf`, text: utf8Decode(gunzipSync(bytes)) }]
  }
  if (kind === 'bz2') {
    const outName = (name && name.replace(/\.bz2$/i, '')) || 'trace.btf'
    return [{ name: outName.endsWith('.btf') ? outName : `${outName}.btf`, text: utf8Decode(bz2.decompress(bytes)) }]
  }
  if (kind === 'zip') {
    const files = unzipSync(bytes)
    const members = listZipBtfMembers(Object.keys(files))
    if (!members.length) throw new Error(zipNoBtfMessage(Object.keys(files)))
    const labels = zipMemberDisplayNames(members, name)
    return members.map((member, i) => ({
      name: labels[i],
      text: utf8Decode(files[member]),
    }))
  }
  return [{ name: name || 'trace.btf', text: utf8Decode(bytes) }]
}

/**
 * @param {Uint8Array} bytes
 * @param {string} [name]
 * @returns {string} UTF-8 BTF text (first entry; multi-zip callers should use decompressBtfEntries)
 */
export function decompressBtfBytes(bytes, name = '') {
  const entries = decompressBtfEntries(bytes, name)
  return entries[0].text
}

/**
 * @param {File|Blob} file
 * @param {string} [name]
 * @returns {Promise<BtfEntry[]>}
 */
export async function loadBtfEntriesFromFile(file, name) {
  const label = name || (file && 'name' in file ? file.name : '') || ''
  const buf = await file.arrayBuffer()
  return decompressBtfEntries(new Uint8Array(buf), label)
}

/**
 * @param {File|Blob} file
 * @param {string} [name]
 * @returns {Promise<string>}
 */
export async function loadBtfTextFromFile(file, name) {
  const entries = await loadBtfEntriesFromFile(file, name)
  return entries[0].text
}

/** @deprecated kept for callers that only need the extension check */
export function looksLikeBtfName(name) {
  return BTF_NAME_RE.test(name) || ARCHIVE_RE.test(name)
}
