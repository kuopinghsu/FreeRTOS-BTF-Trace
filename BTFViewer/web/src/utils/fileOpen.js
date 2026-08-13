/**
 * File open helpers: optional FSA picker on http(s)/localhost, native
 * <input type="file"> on file://.
 */

import { BTF_FILE_ACCEPT, BTF_FILE_PICKER_ACCEPT, isBtfOpenName } from './btfLoad.js'
import { classifyPickedOpen, isXmlOpenName, packFromDirectoryHandle } from './demoPack.js'

const PICKER_ID = 'btf-trace-open'

export const OPEN_FILE_ACCEPT = `${BTF_FILE_ACCEPT},.xml`

export const OPEN_FILE_PICKER_ACCEPT = {
  ...BTF_FILE_PICKER_ACCEPT,
  'text/xml': ['.xml'],
  'application/xml': ['.xml'],
}

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
      types: [{
        description: 'BTF trace or demo XML',
        accept: OPEN_FILE_PICKER_ACCEPT,
      }],
      multiple: true,
      id: PICKER_ID,
    })
    const files = new Map()
    let xmlHandle = null
    for (const handle of handles) {
      const file = await handle.getFile()
      files.set(file.name, file)
      if (isXmlOpenName(file.name) && !xmlHandle) xmlHandle = handle
    }
    return await classifyPickedOpen(files, xmlHandle)
  } catch (err) {
    if (err && err.name === 'AbortError') return null
    throw err
  }
}

export { isBtfOpenName, isXmlOpenName, packFromDirectoryHandle }

