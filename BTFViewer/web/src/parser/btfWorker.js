/**
 * btfWorker.js – Web Worker wrapper around parseBtf().
 */
import { parseBtf } from './btfParser.js'
import { packTrace } from './tracePack.js'
import { initWasmAccel } from '../renderer/wasmAccel.js'
import { decompressBtfEntries } from '../utils/btfLoad.js'
import { openWorkspaceBlob } from '../utils/workspace.js'

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
      self.postMessage({ type: 'done', entries: decompressBtfEntries(input, name) })
      return
    }
    await initWasmAccel()
    const trace = await parseBtf(text, (pct, msg) => {
      self.postMessage({ type: 'progress', pct, msg })
    })
    self.postMessage({ type: 'progress', pct: 99, msg: 'Packing trace…' })
    await new Promise(resolve => setTimeout(resolve, 0))
    const { payload, transferables } = packTrace(trace, (pct, msg) => {
      self.postMessage({ type: 'progress', pct, msg })
    }, { transfer: true })
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
