/** IndexedDB cache of parsed trace payloads for session tab restore. */

const DB_NAME = 'btf-viewer-traces-v1'
const STORE = 'traces'
const MAX_ENTRIES = 8

function openDb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1)
    req.onupgradeneeded = () => {
      const db = req.result
      if (!db.objectStoreNames.contains(STORE)) {
        db.createObjectStore(STORE, { keyPath: 'name' })
      }
    }
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

/** Store packed trace (from parser/worker) keyed by file name. */
export async function putTrace(name, packed) {
  if (!name || !packed) return
  try {
    const db = await openDb()
    await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, 'readwrite')
      tx.objectStore(STORE).put({ name, packed, updatedAt: Date.now() })
      tx.oncomplete = () => resolve()
      tx.onerror = () => reject(tx.error)
    })
    db.close()
  } catch {
    /* quota / private mode */
  }
}

export async function getTrace(name) {
  if (!name) return null
  try {
    const db = await openDb()
    const row = await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, 'readonly')
      const req = tx.objectStore(STORE).get(name)
      req.onsuccess = () => resolve(req.result ?? null)
      req.onerror = () => reject(req.error)
    })
    db.close()
    return row?.packed ?? null
  } catch {
    return null
  }
}

/** Drop cached traces not in *keepNames*; cap total entries. */
export async function pruneTraces(keepNames) {
  const keep = new Set(keepNames || [])
  try {
    const db = await openDb()
    const all = await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, 'readonly')
      const req = tx.objectStore(STORE).getAll()
      req.onsuccess = () => resolve(req.result || [])
      req.onerror = () => reject(req.error)
    })
    const sorted = all.sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0))
    const toDelete = sorted.filter(r => !keep.has(r.name)).map(r => r.name)
    if (sorted.length > MAX_ENTRIES) {
      for (const r of sorted.slice(MAX_ENTRIES)) {
        if (!toDelete.includes(r.name)) toDelete.push(r.name)
      }
    }
    if (toDelete.length) {
      await new Promise((resolve, reject) => {
        const tx = db.transaction(STORE, 'readwrite')
        const store = tx.objectStore(STORE)
        for (const n of toDelete) store.delete(n)
        tx.oncomplete = () => resolve()
        tx.onerror = () => reject(tx.error)
      })
    }
    db.close()
  } catch {
    /* ignore */
  }
}
