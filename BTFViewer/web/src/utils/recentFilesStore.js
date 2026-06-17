/** Recent trace filenames in localStorage (web cannot auto-reload file contents). */

const RECENT_KEY = 'btf-viewer-recent-v1'
const MAX_RECENT = 8

export function loadRecentFiles() {
  try {
    const raw = localStorage.getItem(RECENT_KEY)
    const list = raw ? JSON.parse(raw) : []
    return Array.isArray(list) ? list.filter(n => typeof n === 'string').slice(0, MAX_RECENT) : []
  } catch {
    return []
  }
}

export function addRecentFile(name) {
  if (!name) return loadRecentFiles()
  const cur = loadRecentFiles().filter(n => n !== name)
  cur.unshift(name)
  const next = cur.slice(0, MAX_RECENT)
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify(next))
  } catch { /* quota */ }
  return next
}
