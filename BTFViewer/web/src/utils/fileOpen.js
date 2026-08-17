/**
 * File open helpers: optional FSA picker on http(s)/localhost, native
 * <input type="file"> on file://.
 */

import { BTF_FILE_ACCEPT, isBtfOpenName } from './btfLoad.js'
import { classifyPickedOpen, isXmlOpenName, isXtfOpenName, packFromDirectoryHandle, filePickerOptions, rememberFileOpenHandle, lastRememberedFileOpenHandle } from './demoPack.js'

export const OPEN_FILE_ACCEPT = `${BTF_FILE_ACCEPT},.xml,.xtf`

/**
 * Chromium's showOpenFilePicker strips unknown extensions from typed MIME
 * lists (e.g. ``.xtf`` under ``application/zip``). Put every Open extension
 * under ``application/octet-stream`` in one type entry so the *default*
 * filter accepts ``.xtf`` on the first dialog open.
 */
export const OPEN_FILE_PICKER_TYPES = [
  {
    description: 'BTF trace, demo XML, or .xtf pack',
    accept: {
      'application/octet-stream': [
        '.btf', '.btf.gz', '.gz', '.btf.bz2', '.bz2', '.btf.zip', '.zip',
        '.xml', '.xtf',
      ],
    },
  },
]

/** @deprecated Prefer OPEN_FILE_PICKER_TYPES; kept for tests / callers. */
export const OPEN_FILE_PICKER_ACCEPT = OPEN_FILE_PICKER_TYPES[0].accept

function isHttpOrigin() {
  if (typeof window === 'undefined') return false
  const { protocol, hostname } = window.location
  if (protocol === 'file:') return false
  return protocol === 'https:'
    || hostname === 'localhost'
    || hostname === '127.0.0.1'
}

export function supportsFileHandles() {
  return isHttpOrigin()
    && window.isSecureContext
    && 'showOpenFilePicker' in window
}

/** Open via FSA picker (http(s)/localhost). Returns null on cancel. */
export async function pickAndReadBtf() {
  const picked = await pickAndReadOpen()
  if (!picked || picked.kind !== 'btf') return null
  return picked.file
}

/**
 * Unified Open: BTF → `{ kind: 'btf', file }`, demo XML → `{ kind: 'demo', pack }`.
 * Returns null on cancel.
 */
export async function pickAndReadOpen() {
  if (!supportsFileHandles()) return null
  try {
    const handles = await window.showOpenFilePicker({
      ...filePickerOptions(lastRememberedFileOpenHandle()),
      types: OPEN_FILE_PICKER_TYPES,
      excludeAcceptAllOption: false,
    })
    const files = new Map()
    let xmlHandle = null
    for (const handle of handles) {
      const file = await handle.getFile()
      files.set(file.name, file)
      if (isXmlOpenName(file.name) && !xmlHandle) xmlHandle = handle
    }
    rememberFileOpenHandle(xmlHandle || handles[0] || null)
    return await classifyPickedOpen(files, xmlHandle)
  } catch (err) {
    if (err && err.name === 'AbortError') return null
    throw err
  }
}

export { isBtfOpenName, isXmlOpenName, isXtfOpenName, packFromDirectoryHandle }
