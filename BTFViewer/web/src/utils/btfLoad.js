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

/**
 * @param {Record<string, Uint8Array>} files
 * @returns {string}
 */
export function pickZipBtfMember(files) {
  const names = Object.keys(files || {}).filter(n => n && !n.endsWith('/'))
  if (!names.length) throw new Error('ZIP archive contains no files')
  const btf = names.filter(n => {
    const l = n.toLowerCase()
    return l.endsWith('.btf') && !l.endsWith('.btf.gz') && !l.endsWith('.btf.bz2')
  })
  if (btf.length === 1) return btf[0]
  if (btf.length > 1) {
    const top = btf.filter(n => !n.includes('/') && !n.includes('\\'))
    return (top.length ? top : btf).sort()[0]
  }
  if (names.length === 1) return names[0]
  throw new Error(
    `ZIP archive has no .btf member (found: ${names.sort().slice(0, 8).join(', ')}${names.length > 8 ? '…' : ''})`,
  )
}

function utf8Decode(bytes) {
  return new TextDecoder('utf-8', { fatal: false }).decode(bytes)
}

/**
 * @param {Uint8Array} bytes
 * @param {string} [name]
 * @returns {string} UTF-8 BTF text
 */
export function decompressBtfBytes(bytes, name = '') {
  const kind = sniffCompression(bytes) || compressionFromName(name)
  if (!kind) return utf8Decode(bytes)

  if (kind === 'gzip') {
    return utf8Decode(gunzipSync(bytes))
  }
  if (kind === 'bz2') {
    return utf8Decode(bz2.decompress(bytes))
  }
  if (kind === 'zip') {
    const files = unzipSync(bytes)
    const member = pickZipBtfMember(files)
    return utf8Decode(files[member])
  }
  return utf8Decode(bytes)
}

/**
 * @param {File|Blob} file
 * @param {string} [name]
 * @returns {Promise<string>}
 */
export async function loadBtfTextFromFile(file, name) {
  const label = name || (file && 'name' in file ? file.name : '') || ''
  const buf = await file.arrayBuffer()
  return decompressBtfBytes(new Uint8Array(buf), label)
}

/** @deprecated kept for callers that only need the extension check */
export function looksLikeBtfName(name) {
  return BTF_NAME_RE.test(name) || ARCHIVE_RE.test(name)
}
