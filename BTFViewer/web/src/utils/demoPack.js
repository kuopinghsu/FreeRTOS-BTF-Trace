/**
 * Load a demo pack folder: *.xml + voice clips + the BTF named in <meta><trace>.
 */

import { parseDemoXml } from './demoXml.js'
import { isBtfOpenName } from './btfLoad.js'

export function isXmlOpenName(name) {
  return String(name || '').toLowerCase().endsWith('.xml')
}

export function normalizePackPath(p) {
  return String(p || '')
    .replace(/\\/g, '/')
    .replace(/^\.\//, '')
    .replace(/\/{2,}/g, '/')
    .replace(/\/$/, '')
}

function xmlDirOf(xmlRel) {
  const n = normalizePackPath(xmlRel)
  const i = n.lastIndexOf('/')
  return i < 0 ? '.' : n.slice(0, i)
}

function lookupFile(files, rel) {
  const want = normalizePackPath(rel)
  if (files.has(want)) return files.get(want)
  const lower = want.toLowerCase()
  for (const [k, v] of files) {
    if (k.toLowerCase() === lower) return v
  }
  return null
}

function chooseXmlPath(files) {
  const xmls = [...files.keys()].filter(k => k.toLowerCase().endsWith('.xml'))
  if (!xmls.length) return ''
  const demoish = xmls.filter(k => /demo/i.test(k.split('/').pop() || ''))
  const pool = demoish.length ? demoish : xmls
  const withBtf = pool.find((xml) => {
    const dir = xmlDirOf(xml)
    return [...files.keys()].some((k) => {
      if (!/\.btf(\.gz|\.bz2|\.zip)?$/i.test(k)) return false
      const parent = xmlDirOf(k)
      return parent === dir || k.startsWith(dir === '.' ? '' : `${dir}/`)
    })
  })
  return withBtf || pool[0]
}

/**
 * @param {Map<string, File>} files  relative path → File
 */
export async function packFromFileMap(files) {
  const xmlRel = chooseXmlPath(files)
  if (!xmlRel) throw new Error('No .xml demo script in the selected folder')
  const xmlFile = files.get(xmlRel)
  const xmlText = await xmlFile.text()
  const xmlDir = xmlDirOf(xmlRel)
  const parsed = parseDemoXml(xmlText, { xmlDir })
  const traceRel = normalizePackPath(parsed.trace || '')
  let traceFile = traceRel ? lookupFile(files, traceRel) : null
  if (!traceFile) {
    const btfs = [...files.entries()].filter(([k]) => /\.btf(\.gz|\.bz2|\.zip)?$/i.test(k))
    if (btfs.length === 1) traceFile = btfs[0][1]
  }
  return {
    files,
    xmlRel,
    xmlDir,
    parsed,
    traceFile,
    resolve(rel) {
      return lookupFile(files, rel)
    },
  }
}

const SKIP_DIR_NAMES = new Set([
  '.git', 'node_modules', '.svn', '__pycache__', '.hg', '.ds_store',
])

async function grantRead(handle) {
  if (!handle) return false
  try {
    if (typeof handle.queryPermission === 'function') {
      const state = await handle.queryPermission({ mode: 'read' })
      if (state === 'granted') return true
    }
    if (typeof handle.requestPermission === 'function') {
      return (await handle.requestPermission({ mode: 'read' })) === 'granted'
    }
    return true
  } catch {
    return false
  }
}

async function walkDirectoryHandle(handle, prefix, out) {
  if (!handle || typeof handle.entries !== 'function') return
  let iterator
  try {
    iterator = handle.entries()
  } catch {
    return
  }
  for await (const [name, child] of iterator) {
    if (!name || name === '.' || name === '..') continue
    const rel = prefix ? `${prefix}/${name}` : name
    if (child.kind === 'directory') {
      if (SKIP_DIR_NAMES.has(name.toLowerCase()) || name.startsWith('.')) continue
      try {
        await walkDirectoryHandle(child, rel, out)
      } catch {
        // WSL / UNC shares often throw while iterating a child folder.
      }
      continue
    }
    try {
      out.set(normalizePackPath(rel), await child.getFile())
    } catch {
      // Skip unreadable entries (symlinks, pipes, WSL special files).
    }
  }
}

export async function packFromDirectoryHandle(handle) {
  const files = new Map()
  await walkDirectoryHandle(handle, '', files)
  return packFromFileMap(files)
}

function fileListToMap(list) {
  const files = new Map()
  for (const file of list || []) {
    const rel = normalizePackPath(file.webkitRelativePath || file.name)
    if (rel) files.set(rel, file)
  }
  return files
}

export function classifyOpenFiles(files) {
  const names = [...(files?.keys?.() || [])]
  if (names.some(n => isXmlOpenName(n))) return 'demo'
  if (names.some(n => isBtfOpenName(n))) return 'btf'
  return 'unknown'
}

function supportsDirectoryPicker() {
  return typeof window !== 'undefined'
    && window.isSecureContext
    && typeof window.showDirectoryPicker === 'function'
}

async function tryParentDirectoryPack(handle) {
  if (!handle || typeof handle.getParent !== 'function') return null
  try {
    const parent = await handle.getParent()
    if (!(await grantRead(parent))) return null
    return await packFromDirectoryHandle(parent)
  } catch {
    return null
  }
}

/**
 * Classify files from a single Open / drop. Never opens another native picker:
 * browsers reject a second chooser after the first (no remaining user activation).
 *
 * @returns {Promise<
 *   { kind: 'demo', pack: object } |
 *   { kind: 'demo-folder', xmlName: string, startIn: object|null } |
 *   { kind: 'btf', file: File } |
 *   null
 * >}
 */
export async function classifyPickedOpen(files, xmlHandle = null) {
  const kind = classifyOpenFiles(files)
  if (kind === 'demo') {
    let pack = await packFromFileMap(files)
    if (!pack.traceFile) {
      const parent = await tryParentDirectoryPack(xmlHandle)
      if (parent?.traceFile) pack = parent
    }
    if (pack.traceFile) return { kind: 'demo', pack }
    return {
      kind: 'demo-folder',
      xmlName: (pack.xmlRel || '').split('/').pop() || 'demo.xml',
      startIn: xmlHandle || null,
    }
  }
  const btf = [...(files?.values?.() || [])].find(f => isBtfOpenName(f.name))
  return btf ? { kind: 'btf', file: btf } : null
}

function isPickerCancel(err) {
  return !!err && err.name === 'AbortError'
}

/**
 * Open a folder picker (File System Access API) or a webkitdirectory fallback.
 * Must be called from a user gesture (button click), not after another picker.
 * @returns {Promise<object|null>} pack or null if cancelled
 */
export async function pickDemoPack(opts = {}) {
  if (supportsDirectoryPicker()) {
    try {
      const dirOpts = { id: 'btf-demo-pack' }
      if (opts.startIn) dirOpts.startIn = opts.startIn
      let dir
      try {
        dir = await window.showDirectoryPicker(dirOpts)
      } catch (err) {
        if (isPickerCancel(err)) return null
        // WSL / UNC: startIn from a Linux file handle is often invalid.
        if (!opts.startIn) throw err
        dir = await window.showDirectoryPicker({ id: 'btf-demo-pack' })
      }
      if (dir && typeof dir.requestPermission === 'function') {
        await grantRead(dir)
      }
      return await packFromDirectoryHandle(dir)
    } catch (err) {
      if (isPickerCancel(err)) return null
      // Chrome on Windows cannot walk \\wsl$ / \\wsl.localhost via FSA.
      return pickDemoPackViaInput()
    }
  }
  return pickDemoPackViaInput()
}

function pickDemoPackViaInput() {
  return new Promise((resolve, reject) => {
    if (typeof document === 'undefined') {
      resolve(null)
      return
    }
    const input = document.createElement('input')
    input.type = 'file'
    input.setAttribute('webkitdirectory', '')
    input.setAttribute('directory', '')
    input.multiple = true
    input.style.display = 'none'
    const cleanup = () => {
      input.remove()
    }
    input.addEventListener('change', async () => {
      try {
        const list = input.files
        cleanup()
        if (!list || !list.length) {
          resolve(null)
          return
        }
        resolve(await packFromFileMap(fileListToMap(list)))
      } catch (err) {
        reject(err)
      }
    })
    document.body.appendChild(input)
    input.click()
    // If the user cancels, some browsers never fire change; drop the node later.
    setTimeout(() => {
      if (document.body.contains(input) && (!input.files || !input.files.length)) {
        // Keep the input until change; a second click replaces it.
      }
    }, 0)
  })
}

/** Build a pack from an <input webkitdirectory> FileList (Toolbar fallback). */
export async function packFromFileList(list) {
  const files = fileListToMap(list)
  if (!files.size) {
    throw new Error(
      'Could not read that folder. Copy the demo pack to a local disk '
      + '(browser open often fails for WSL \\\\wsl$ / \\\\wsl.localhost paths) '
      + 'and choose the copied folder.',
    )
  }
  return packFromFileMap(files)
}

function readAllDirectoryEntries(reader) {
  return new Promise((resolve, reject) => {
    const all = []
    const next = () => {
      reader.readEntries((batch) => {
        if (!batch.length) {
          resolve(all)
          return
        }
        all.push(...batch)
        next()
      }, reject)
    }
    next()
  })
}

async function walkDroppedEntry(entry, prefix, out) {
  const rel = prefix ? `${prefix}/${entry.name}` : entry.name
  if (entry.isFile) {
    const file = await new Promise((resolve, reject) => entry.file(resolve, reject))
    out.set(normalizePackPath(rel), file)
    return
  }
  if (!entry.isDirectory) return
  const children = await readAllDirectoryEntries(entry.createReader())
  for (const child of children) await walkDroppedEntry(child, rel, out)
}

/**
 * Collect dropped files/folders into a relative-path map.
 * @param {DataTransfer} dt
 * @returns {Promise<Map<string, File>>}
 */
export async function collectDroppedFiles(dt) {
  const files = new Map()
  const items = [...(dt?.items || [])]
  const entries = items
    .map(item => (typeof item.webkitGetAsEntry === 'function' ? item.webkitGetAsEntry() : null))
    .filter(Boolean)
  if (entries.length) {
    for (const entry of entries) await walkDroppedEntry(entry, '', files)
    if (files.size) return files
  }
  return fileListToMap(dt?.files)
}
