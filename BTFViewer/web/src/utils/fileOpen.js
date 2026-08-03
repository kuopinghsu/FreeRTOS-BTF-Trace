/**
 * File open helpers: optional FSA picker on http(s)/localhost, native
 * <input type="file"> on file://.
 */

import { BTF_FILE_PICKER_ACCEPT } from './btfLoad.js'

const PICKER_ID = 'btf-trace-open'

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
  if (!supportsFileHandles()) return null
  try {
    const [handle] = await window.showOpenFilePicker({
      types: [{
        description: 'BTF trace',
        accept: BTF_FILE_PICKER_ACCEPT,
      }],
      multiple: false,
      id: PICKER_ID,
    })
    return handle.getFile()
  } catch {
    return null
  }
}
