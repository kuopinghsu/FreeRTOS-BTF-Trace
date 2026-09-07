/**
 * Hardened ZIP-container reader — one safe path for every archive BTFViewer opens.
 * Keep in sync with btf_viewer_pkg/zip_container.py.
 *
 * Shared by the .btfw portable-workspace reader (workspace.js) and the .xtf
 * demo-pack reader (demoPack.js filesFromXtf).
 *
 * Guarantees for any archive read through here:
 *  - member names are plain relative POSIX paths — no `..`, no absolute / drive /
 *    UNC roots, no backslashes or NUL (unsafe names are skipped with a warning);
 *  - the entry count is capped (CONTAINER_MAX_ENTRIES);
 *  - the total decompressed size is capped (CONTAINER_MAX_UNCOMPRESSED_BYTES);
 *  - entries whose decompressed / stored ratio is implausible are refused as
 *    compression bombs;
 *  - nothing in the archive is executed and nothing is fetched.
 */
import { unzipSync } from 'fflate'

export const CONTAINER_MAX_ENTRIES = 4096
export const CONTAINER_MAX_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
export const CONTAINER_MAX_COMPRESSION_RATIO = 250
export const CONTAINER_BOMB_MIN_SIZE = 64 * 1024

/** A plain relative POSIX path with no traversal / root. */
export function isSafeMember(name) {
  const n = String(name ?? '')
  if (!n || n !== n.trim()) return false
  if (n.includes('\\') || n.includes('\0')) return false
  if (n.startsWith('/') || n.startsWith('~')) return false
  // Windows drive / UNC (`C:\...`).
  if (n.length >= 2 && n[1] === ':') return false
  const parts = n.split('/')
  for (let i = 0; i < parts.length; i += 1) {
    const p = parts[i]
    if (p === '.' || p === '..') return false
    if (p === '' && i !== parts.length - 1) return false
  }
  return true
}

/**
 * Read `bytes` as a hardened ZIP container.
 * @returns {{ members: Record<string, Uint8Array>, warnings: string[] }}
 *   only the safe-named, non-directory members.
 */
export function readZipContainer(bytes, {
  containerDesc = 'ZIP',
  maxEntries = CONTAINER_MAX_ENTRIES,
  maxUncompressed = CONTAINER_MAX_UNCOMPRESSED_BYTES,
  maxRatio = CONTAINER_MAX_COMPRESSION_RATIO,
  bombMinSize = CONTAINER_BOMB_MIN_SIZE,
} = {}) {
  if (!(bytes instanceof Uint8Array) || bytes.length < 4
      || bytes[0] !== 0x50 || bytes[1] !== 0x4b) {
    throw new Error(`not a ${containerDesc} container`)
  }
  let count = 0
  let total = 0
  const warnings = []
  const raw = unzipSync(bytes, {
    filter: (f) => {
      count += 1
      if (count > maxEntries) {
        throw new Error(`archive has too many entries (> ${maxEntries})`)
      }
      if (f.name.endsWith('/')) return false
      if (!isSafeMember(f.name)) {
        warnings.push(`skipped unsafe member name: ${JSON.stringify(f.name)}`)
        return false
      }
      if (f.originalSize > bombMinSize && f.size > 0
          && f.originalSize / f.size > maxRatio) {
        throw new Error(`archive entry ${JSON.stringify(f.name)} looks like a compression bomb`)
      }
      total += f.originalSize
      if (total > maxUncompressed) {
        throw new Error('archive decompressed size exceeds the limit')
      }
      return true
    },
  })
  return { members: raw, warnings }
}
