/**
 * File System Access API handles for one-click Recent reopen (Chromium).
 */

const DB_NAME = 'btf-viewer-file-handles-v1'
const STORE = 'handles'
const DB_VERSION = 1

function openDb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION)
    req.onerror = () => reject(req.error)
    req.onupgradeneeded = () => {
      req.result.createObjectStore(STORE)
    }
    req.onsuccess = () => resolve(req.result)
  })
}

export function supportsFileHandles() {
  return typeof window !== 'undefined'
    && 'showOpenFilePicker' in window
    && typeof indexedDB !== 'undefined'
}

export async function storeFileHandle(name, handle) {
  if (!name || !handle) return
  try {
    const db = await openDb()
    await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, 'readwrite')
      tx.objectStore(STORE).put(handle, name)
      tx.oncomplete = () => resolve()
      tx.onerror = () => reject(tx.error)
    })
    db.close()
  } catch { /* private mode / quota */ }
}

export async function getFileHandle(name) {
  if (!name) return null
  try {
    const db = await openDb()
    const handle = await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, 'readonly')
      const req = tx.objectStore(STORE).get(name)
      req.onsuccess = () => resolve(req.result ?? null)
      req.onerror = () => reject(req.error)
    })
    db.close()
    return handle || null
  } catch {
    return null
  }
}

export async function readRecentFile(name) {
  const handle = await getFileHandle(name)
  if (!handle?.getFile) return null
  try {
    if (handle.queryPermission) {
      let perm = await handle.queryPermission({ mode: 'read' })
      if (perm !== 'granted') {
        perm = await handle.requestPermission({ mode: 'read' })
        if (perm !== 'granted') return null
      }
    }
    return await handle.getFile()
  } catch {
    return null
  }
}

export async function pickAndReadBtf() {
  if (!supportsFileHandles()) return null
  try {
    const [handle] = await window.showOpenFilePicker({
      types: [{
        description: 'BTF trace',
        accept: { 'text/plain': ['.btf'] },
      }],
      multiple: false,
    })
    const file = await handle.getFile()
    await storeFileHandle(file.name, handle)
    return file
  } catch {
    return null
  }
}
