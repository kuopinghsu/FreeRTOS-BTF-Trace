/**
 * btfWorker.js – Web Worker wrapper around parseBtf().
 */
import { parseBtf } from './btfParser.js'
import { packTrace } from './tracePack.js'
import { initWasmAccel } from '../renderer/wasmAccel.js'

self.onmessage = async function (e) {
  const { text } = e.data
  try {
    await initWasmAccel()
    const trace = await parseBtf(text, (pct, msg) => {
      self.postMessage({ type: 'progress', pct, msg })
    })
    self.postMessage({ type: 'progress', pct: 99, msg: 'Packing trace…' })
    await new Promise(resolve => setTimeout(resolve, 0))
    const { payload } = packTrace(trace, (pct, msg) => {
      self.postMessage({ type: 'progress', pct, msg })
    })
    self.postMessage({ type: 'done', packed: payload })
  } catch (err) {
    self.postMessage({
      type: 'error',
      message: err?.message || String(err),
      name: err?.name || 'Error',
      stack: err?.stack || '',
    })
  }
}
