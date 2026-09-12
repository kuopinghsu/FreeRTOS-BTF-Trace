/**
 * Load BTF text from a plain .btf file or a gz / bz2 / zip container.
 */

import { Gunzip } from 'fflate'
import bz2 from 'bz2'
import { readZipContainer } from './zipContainer.js'

export const BTF_MAX_INPUT_BYTES = 256 * 1024 * 1024
export const BTF_MAX_EXPANDED_BYTES = 256 * 1024 * 1024
export const BTF_MAX_ARCHIVE_ENTRIES = 256
export const BTF_MAX_COMPRESSION_RATIO = 250
export const BTF_BOMB_MIN_SIZE = 64 * 1024

const GZIP_INPUT_CHUNK_BYTES = 16 * 1024
const BZ2_BLOCK_MAGIC = [0x31, 0x41, 0x59, 0x26, 0x53, 0x59]

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

function assertByteLimit(size, limit, description) {
  if (!Number.isSafeInteger(size) || size < 0 || size > limit) {
    throw new Error(`${description} exceeds the ${Math.floor(limit / (1024 * 1024))} MB limit`)
  }
}

function assertCompressionRatio(inputSize, outputSize, maxRatio, bombMinSize, description) {
  if (outputSize > bombMinSize && inputSize > 0 && outputSize / inputSize > maxRatio) {
    throw new Error(`${description} looks like a compression bomb`)
  }
}

function concatChunks(chunks, total) {
  const output = new Uint8Array(total)
  let offset = 0
  for (const chunk of chunks) {
    output.set(chunk, offset)
    offset += chunk.length
  }
  return output
}

function gunzipBounded(bytes, { maxExpanded, maxRatio, bombMinSize }) {
  const chunks = []
  let total = 0
  const stream = new Gunzip((chunk) => {
    total += chunk.length
    assertByteLimit(total, maxExpanded, 'GZIP decompressed size')
    chunks.push(chunk)
  })
  for (let offset = 0; offset < bytes.length; offset += GZIP_INPUT_CHUNK_BYTES) {
    const end = Math.min(bytes.length, offset + GZIP_INPUT_CHUNK_BYTES)
    stream.push(bytes.subarray(offset, end), end === bytes.length)
  }
  assertCompressionRatio(bytes.length, total, maxRatio, bombMinSize, 'GZIP data')
  return concatChunks(chunks, total)
}

function matchesBz2BlockMagic(bytes, byteIndex, shift) {
  for (let i = 0; i < BZ2_BLOCK_MAGIC.length; i += 1) {
    const pair = (bytes[byteIndex + i] << 8) | (bytes[byteIndex + i + 1] || 0)
    if (((pair >>> (8 - shift)) & 0xff) !== BZ2_BLOCK_MAGIC[i]) return false
  }
  return true
}

/** Count bit-aligned bzip2 block headers without expanding the stream. */
export function bzip2BlockCount(bytes) {
  let count = 0
  for (let shift = 0; shift < 8; shift += 1) {
    for (let i = 4; i + BZ2_BLOCK_MAGIC.length < bytes.length; i += 1) {
      if (matchesBz2BlockMagic(bytes, i, shift)) count += 1
    }
  }
  return count
}

function bunzipBounded(bytes, { maxExpanded, maxRatio, bombMinSize }) {
  const blockSizeDigit = bytes[3]
  if (blockSizeDigit < 0x31 || blockSizeDigit > 0x39) {
    throw new Error('Invalid bzip2 block size')
  }
  const blocks = bzip2BlockCount(bytes)
  const maxBlockBytes = (blockSizeDigit - 0x30) * 100_000
  assertByteLimit(blocks * maxBlockBytes, maxExpanded, 'Bzip2 decompressed size')
  const output = bz2.decompress(bytes)
  assertByteLimit(output.length, maxExpanded, 'Bzip2 decompressed size')
  assertCompressionRatio(bytes.length, output.length, maxRatio, bombMinSize, 'Bzip2 data')
  return output
}

/** Read a fetch response without ever buffering more than the configured cap. */
export async function readResponseBytes(response, maxBytes = BTF_MAX_INPUT_BYTES) {
  const rawLength = response?.headers?.get?.('content-length')
  let contentLength = null
  if (rawLength != null && rawLength !== '') {
    contentLength = Number(rawLength)
    assertByteLimit(contentLength, maxBytes, 'Trace response')
  }
  if (!response?.body?.getReader) {
    const bytes = new Uint8Array(await response.arrayBuffer())
    assertByteLimit(bytes.length, maxBytes, 'Trace response')
    return bytes
  }
  const reader = response.body.getReader()
  const output = contentLength == null ? null : new Uint8Array(contentLength)
  const chunks = []
  let total = 0
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      const chunkLength = value?.byteLength || 0
      const offset = total
      total += chunkLength
      assertByteLimit(total, maxBytes, 'Trace response')
      if (output && total > output.length) throw new Error('Trace response exceeds Content-Length')
      if (chunkLength) {
        if (output) output.set(value, offset)
        else chunks.push(value)
      }
    }
  } catch (error) {
    await reader.cancel(error).catch(() => {})
    throw error
  }
  if (output) {
    if (total !== output.length) throw new Error('Trace response ended before Content-Length')
    return output
  }
  return concatChunks(chunks, total)
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
export function decompressBtfEntries(bytes, name = '', {
  maxInput = BTF_MAX_INPUT_BYTES,
  maxExpanded = BTF_MAX_EXPANDED_BYTES,
  maxEntries = BTF_MAX_ARCHIVE_ENTRIES,
  maxRatio = BTF_MAX_COMPRESSION_RATIO,
  bombMinSize = BTF_BOMB_MIN_SIZE,
} = {}) {
  assertByteLimit(bytes?.length, maxInput, 'Trace input')
  const kind = sniffCompression(bytes) || compressionFromName(name)
  if (!kind) {
    return [{ name: name || 'trace.btf', text: utf8Decode(bytes) }]
  }

  if (kind === 'gzip') {
    const outName = (name && name.replace(/\.gz$/i, '')) || 'trace.btf'
    const output = gunzipBounded(bytes, { maxExpanded, maxRatio, bombMinSize })
    return [{ name: outName.endsWith('.btf') ? outName : `${outName}.btf`, text: utf8Decode(output) }]
  }
  if (kind === 'bz2') {
    const outName = (name && name.replace(/\.bz2$/i, '')) || 'trace.btf'
    const output = bunzipBounded(bytes, { maxExpanded, maxRatio, bombMinSize })
    return [{ name: outName.endsWith('.btf') ? outName : `${outName}.btf`, text: utf8Decode(output) }]
  }
  if (kind === 'zip') {
    const { members: files } = readZipContainer(bytes, {
      containerDesc: 'BTF ZIP',
      maxEntries,
      maxUncompressed: maxExpanded,
      maxRatio,
      bombMinSize,
    })
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
  if (Number.isFinite(file?.size)) assertByteLimit(file.size, BTF_MAX_INPUT_BYTES, 'Trace input')
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
