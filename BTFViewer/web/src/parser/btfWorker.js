/**
 * btfWorker.js – Web Worker wrapper around parseBtf().
 */
import { parseBtf } from './btfParser.js'
import { packTrace } from './tracePack.js'
import { initWasmAccel } from '../renderer/wasmAccel.js'
import { decompressBtfEntries } from '../utils/btfLoad.js'
import { openWorkspaceBlob } from '../utils/workspace.js'

async function parseAndPack(text) {
  await initWasmAccel()
  const progress = (pct, msg) => self.postMessage({ type: 'progress', pct, msg })
  const trace = await parseBtf(text, progress, { includeUxEvents: false })
  progress(99, 'Packing trace…')
  return packTrace(trace, progress, { transfer: true })
}

self.onmessage = async function (e) {
  const { text, bytes, file, name, workspace } = e.data
  try {
    if (bytes || file) {
      const input = bytes || new Uint8Array(await file.arrayBuffer())
      if (workspace) {
        const opened = openWorkspaceBlob(input)
        const buffer = opened.trace_bytes?.buffer
        self.postMessage({ type: 'done', workspace: opened }, buffer ? [buffer] : [])
        return
      }
      const entries = decompressBtfEntries(input, name)
      if (entries.length === 1) {
        const entry = entries[0]
        const { payload, transferables } = await parseAndPack(entry.text)
        self.postMessage({ type: 'done', entries: [{ ...entry, packed: payload }] }, transferables)
      } else {
        self.postMessage({ type: 'done', entries })
      }
      return
    }
    const { payload, transferables } = await parseAndPack(text)
    self.postMessage({ type: 'done', packed: payload }, transferables)
  } catch (err) {
    self.postMessage({
      type: 'error',
      message: err?.message || String(err),
      name: err?.name || 'Error',
      stack: err?.stack || '',
    })
  }
}
