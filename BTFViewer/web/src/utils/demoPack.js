/**
 * Load a demo pack folder: *.xml + voice clips + the BTF named in <meta><trace>.
 * Shareable ``.xtf`` archives are zip packs of the same layout.
 */

import { unzipSync } from 'fflate'
import { parseDemoXml } from './demoXml.js'
import { isBtfOpenName } from './btfLoad.js'

export function isXmlOpenName(name) {
  return String(name || '').toLowerCase().endsWith('.xml')
}

/** Shareable demo tour pack (zip of xml + btf + voice/). */
export function isXtfOpenName(name) {
  return String(name || '').toLowerCase().endsWith('.xtf')
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

function basename(p) {
  const n = normalizePackPath(p)
  const i = n.lastIndexOf('/')
  return i < 0 ? n : n.slice(i + 1)
}

function lookupFile(files, rel) {
  const want = normalizePackPath(rel)
  if (files.has(want)) return files.get(want)
  const lower = want.toLowerCase()
  for (const [k, v] of files) {
    if (k.toLowerCase() === lower) return v
  }
  const base = basename(want).toLowerCase()
  if (!base) return null
  let hit = null
  let n = 0
  for (const [k, v] of files) {
    if (basename(k).toLowerCase() === base) {
      hit = v
      n++
    }
  }
  return n === 1 ? hit : null
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

async function walkDirectoryHandle(handle, prefix, out) {
  if (!handle || typeof handle.entries !== 'function') return
  for await (const [name, child] of handle.entries()) {
    const rel = prefix ? `${prefix}/${name}` : name
    if (child.kind === 'directory') await walkDirectoryHandle(child, rel, out)
    else {
      try {
        out.set(normalizePackPath(rel), await child.getFile())
      } catch {
        /* skip unreadable children */
      }
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

function addDroppedFile(out, file, relHint = '') {
  if (!file || looksLikeDirectoryPlaceholder(file)) return
  const rel = normalizePackPath(relHint || file.webkitRelativePath || file.name)
  if (rel) out.set(rel, file)
}

function looksLikeDirectoryPlaceholder(file) {
  const n = String(file?.name || '')
  if (!n || n === '.' || n === '..') return true
  if (n.includes('.')) return false
  const t = String(file.type || '')
  return file.size === 0 || /directory/i.test(t)
}

function filesFromDataTransfer(dt) {
  const files = fileListToMap(dt?.files)
  for (const item of dt?.items || []) {
    try {
      if (item.kind !== 'file' || typeof item.getAsFile !== 'function') continue
      const file = item.getAsFile()
      addDroppedFile(files, file)
    } catch {
      /* ignore */
    }
  }
  return files
}

function lookupDroppedFile(byName, entry, rel) {
  if (!byName?.size) return null
  return byName.get(rel)
    || byName.get(entry?.name)
    || byName.get(normalizePackPath(entry?.name || ''))
    || null
}

export function classifyOpenFiles(files) {
  const names = [
    ...(files?.keys?.() || []),
    ...[...(files?.values?.() || [])].map(f => f?.name || ''),
  ]
  if (names.some(n => isXtfOpenName(n))) return 'xtf'
  if (names.some(n => isXmlOpenName(n))) return 'demo'
  if (names.some(n => isBtfOpenName(n))) return 'btf'
  return 'unknown'
}

/**
 * Expand a ``.xtf`` (zip) File into a relative-path File map for packFromFileMap.
 * @param {File} file
 * @returns {Promise<Map<string, File>>}
 */
export async function filesFromXtf(file) {
  if (!file) throw new Error('No .xtf file')
  const bytes = new Uint8Array(await file.arrayBuffer())
  let entries
  try {
    entries = unzipSync(bytes)
  } catch (err) {
    throw new Error(`Invalid .xtf archive: ${err?.message || err}`)
  }
  const files = new Map()
  for (const [rawName, data] of Object.entries(entries || {})) {
    const rel = normalizePackPath(rawName)
    if (!rel || rel.endsWith('/')) continue
    const base = basename(rel)
    const ab = data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength)
    files.set(rel, new File([ab], base))
  }
  if (![...files.keys()].some(k => isXmlOpenName(k))) {
    throw new Error('No .xml demo script inside the .xtf archive')
  }
  return files
}

function supportsDirectoryPicker() {
  return typeof window !== 'undefined'
    && window.isSecureContext
    && typeof window.showDirectoryPicker === 'function'
}

export const FILE_OPEN_PICKER_ID = 'btf-trace-open-v3'

let lastFileOpenHandle = null

export function rememberFileOpenHandle(handle) {
  if (handle && (handle.kind === 'file' || handle.kind === 'directory')) {
    lastFileOpenHandle = handle
  }
}

export function lastRememberedFileOpenHandle() {
  return lastFileOpenHandle
}

/**
 * Same options as toolbar Open. Directory pickers on macOS Chrome are a
 * different panel and always start in Documents; file pickers remember
 * the last Open folder via this id.
 */
export function filePickerOptions(startIn) {
  const opts = { id: FILE_OPEN_PICKER_ID, multiple: true }
  if (startIn && (startIn.kind === 'file' || startIn.kind === 'directory')) {
    opts.startIn = startIn
  }
  return opts
}

/** Folder dialog (Select/OK on a directory). Separate id from Open's file picker. */
export function directoryPickerOptions(startIn) {
  const opts = { id: 'btf-demo-pack' }
  if (startIn && (startIn.kind === 'file' || startIn.kind === 'directory')) {
    opts.startIn = startIn
  }
  return opts
}

export async function resolveDirectoryStartIn(handle) {
  if (!handle) return null
  if (handle.kind === 'directory') return handle
  if (typeof handle.getParent !== 'function') return null
  try {
    const parent = await handle.getParent()
    return parent && parent.kind === 'directory' ? parent : null
  } catch {
    return null
  }
}

/** Folder the XML already names: same directory as the script, plus <trace> basename. */
export function demoPackHintFromParsed(parsed, xmlRel = '') {
  return {
    xmlName: basename(xmlRel) || 'demo.xml',
    traceName: basename(parsed?.trace || ''),
  }
}

async function ensureReadPermission(handle) {
  if (!handle || typeof handle.queryPermission !== 'function') return true
  try {
    const q = await handle.queryPermission({ mode: 'read' })
    if (q === 'granted') return true
    if (typeof handle.requestPermission !== 'function') return false
    return (await handle.requestPermission({ mode: 'read' })) === 'granted'
  } catch {
    return false
  }
}

/**
 * Read the pack folder next to a File System Access XML handle.
 * Needs a user gesture for requestPermission (Confirm click or the original Open).
 */
export async function tryOpenXmlParentPack(xmlHandle) {
  const parent = await resolveDirectoryStartIn(xmlHandle)
  if (!parent) return null
  try {
    if (!(await ensureReadPermission(parent))) return null
    const pack = await packFromDirectoryHandle(parent)
    return pack?.traceFile ? pack : null
  } catch {
    return null
  }
}

async function tryParentDirectoryPack(handle) {
  return tryOpenXmlParentPack(handle)
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
  let map = files
  const xtf = [...(files?.values?.() || [])].find(f => isXtfOpenName(f.name))
    || [...(files?.entries?.() || [])].find(([k]) => isXtfOpenName(k))?.[1]
  if (xtf) {
    map = await filesFromXtf(xtf)
  }
  const kind = classifyOpenFiles(map)
  if (kind === 'demo' || kind === 'xtf') {
    let pack = await packFromFileMap(map)
    const folderHandle = (await resolveDirectoryStartIn(xmlHandle)) || xmlHandle || null
    if (!pack.traceFile) {
      const parent = await tryParentDirectoryPack(xmlHandle)
      if (parent?.traceFile) pack = parent
    }
    if (pack.traceFile) return { kind: 'demo', pack }
    if (xtf) {
      throw new Error('Demo .xtf has no .btf / .btf.gz trace')
    }
    const hint = demoPackHintFromParsed(pack.parsed, pack.xmlRel)
    return {
      kind: 'demo-folder',
      xmlName: hint.xmlName,
      traceName: hint.traceName,
      startIn: folderHandle,
      files: map,
    }
  }
  const btf = [...(map?.values?.() || [])].find(f => isBtfOpenName(f.name))
  return btf ? { kind: 'btf', file: btf } : null
}

/**
 * Native folder picker so Select/OK is enabled on a directory.
 * (A file picker cannot confirm a folder.)
 */
export async function pickDemoPack(opts = {}) {
  if (supportsDirectoryPicker()) {
    const hint = opts.startIn || lastFileOpenHandle
    const startIn = (await resolveDirectoryStartIn(hint)) || hint || null
    try {
      const dir = await window.showDirectoryPicker(directoryPickerOptions(startIn))
      rememberFileOpenHandle(dir)
      return packFromDirectoryHandle(dir)
    } catch (err) {
      if (err && (err.name === 'AbortError' || err.name === 'NotAllowedError')) return null
      try {
        const dir = await window.showDirectoryPicker({ id: 'btf-demo-pack' })
        rememberFileOpenHandle(dir)
        return packFromDirectoryHandle(dir)
      } catch (err2) {
        if (err2 && (err2.name === 'AbortError' || err2.name === 'NotAllowedError')) return null
        throw err
      }
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
  })
}

/** Build a pack from an <input webkitdirectory> FileList (Toolbar fallback). */
export async function packFromFileList(list) {
  return packFromFileMap(fileListToMap(list))
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

async function walkDroppedEntry(entry, prefix, out, byName) {
  const rel = prefix ? `${prefix}/${entry.name}` : entry.name
  if (entry.isFile) {
    let file = lookupDroppedFile(byName, entry, rel)
    if (!file) {
      try {
        file = await new Promise((resolve, reject) => {
          try {
            entry.file(resolve, reject)
          } catch (err) {
            reject(err)
          }
        })
      } catch {
        file = null
      }
    }
    if (file) addDroppedFile(out, file, rel)
    return
  }
  if (!entry.isDirectory) return
  if (typeof entry.createReader !== 'function') return
  const children = await readAllDirectoryEntries(entry.createReader())
  for (const child of children) await walkDroppedEntry(child, rel, out, byName)
}

/**
 * Collect dropped files/folders into a relative-path map.
 * getAsFileSystemHandle() must be called synchronously in the drop handler
 * (before any await) or Chrome refuses the directory.
 */
export async function collectDroppedFiles(dt) {
  const handleJobs = []
  const entries = []
  for (const item of dt?.items || []) {
    if (typeof item.getAsFileSystemHandle === 'function') {
      try {
        handleJobs.push(item.getAsFileSystemHandle())
      } catch {
        /* ignore */
      }
    }
    try {
      if (typeof item.webkitGetAsEntry === 'function') {
        const entry = item.webkitGetAsEntry()
        if (entry) entries.push(entry)
      }
    } catch {
      /* ignore */
    }
  }
  const fromList = filesFromDataTransfer(dt)
  const files = new Map(fromList)
  for (const job of handleJobs) {
    try {
      const handle = await job
      if (!handle) continue
      if (handle.kind === 'directory') {
        rememberFileOpenHandle(handle)
        await walkDirectoryHandle(handle, handle.name || '', files)
      } else if (handle.kind === 'file') {
        addDroppedFile(files, await handle.getFile())
      }
    } catch {
      /* ignore */
    }
  }
  if (classifyOpenFiles(files) !== 'unknown') return files

  const byName = new Map()
  for (const [k, v] of files) {
    byName.set(k, v)
    byName.set(v.name, v)
    byName.set(basename(k), v)
  }
  for (const entry of entries) {
    try {
      await walkDroppedEntry(entry, '', files, byName)
    } catch {
      /* keep files already collected */
    }
  }
  return files
}
