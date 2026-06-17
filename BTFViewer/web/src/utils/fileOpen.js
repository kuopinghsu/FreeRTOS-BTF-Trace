/**
 * Open .btf via File System Access API (http://localhost only).
 */

const PICKER_ID = 'btf-trace-open'

export function supportsFileHandles() {
  return typeof window !== 'undefined'
    && window.isSecureContext
    && 'showOpenFilePicker' in window
}

/** Open via native picker. Returns null on cancel. */
export async function pickAndReadBtf() {
  if (!supportsFileHandles()) return null
  try {
    const [handle] = await window.showOpenFilePicker({
      types: [{
        description: 'BTF trace',
        accept: { 'text/plain': ['.btf'] },
      }],
      multiple: false,
      id: PICKER_ID,
    })
    return handle.getFile()
  } catch {
    return null
  }
}
