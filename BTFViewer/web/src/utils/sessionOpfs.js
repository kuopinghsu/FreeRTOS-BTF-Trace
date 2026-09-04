/**
 * OPFS backup for the web session JSON (complements localStorage).
 * Trace payloads remain in IndexedDB (traceCache.js).
 */

const SESSION_FILE = 'btf-viewer-session-v2.json'

async function opfsRoot() {
  if (typeof navigator === 'undefined' || !navigator.storage?.getDirectory) return null
  try {
    return await navigator.storage.getDirectory()
  } catch {
    return null
  }
}

/** @param {object} session */
export async function saveSessionOpfs(session) {
  const root = await opfsRoot()
  if (!root || !session) return false
  try {
    const handle = await root.getFileHandle(SESSION_FILE, { create: true })
    const writable = await handle.createWritable()
    await writable.write(JSON.stringify(session))
    await writable.close()
    return true
  } catch {
    return false
  }
}

/** @returns {Promise<object|null>} */
export async function loadSessionOpfs() {
  const root = await opfsRoot()
  if (!root) return null
  try {
    const handle = await root.getFileHandle(SESSION_FILE)
    const file = await handle.getFile()
    const text = await file.text()
    return text ? JSON.parse(text) : null
  } catch {
    return null
  }
}
