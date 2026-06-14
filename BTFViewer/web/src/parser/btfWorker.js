/**
 * btfWorker.js – Web Worker wrapper around parseBtf().
 *
 * Receives: { text: string }
 * Posts back:
 *   { type: 'progress', pct: number, msg: string }
 *   { type: 'done',     trace: BtfTrace }
 *   { type: 'error',    message: string }
 */

import { parseBtf } from './btfParser.js'

self.onmessage = async function (e) {
  const { text } = e.data
  try {
    const trace = await parseBtf(text, (pct, msg) => {
      self.postMessage({ type: 'progress', pct, msg })
    })
    self.postMessage({ type: 'progress', pct: 99, msg: 'Transferring trace…' })
    await new Promise(resolve => setTimeout(resolve, 0))
    try {
      self.postMessage({ type: 'done', trace })
    } catch (postErr) {
      self.postMessage({
        type: 'error',
        message: postErr?.message || String(postErr),
        name: postErr?.name || 'DataCloneError',
      })
    }
  } catch (err) {
    self.postMessage({
      type: 'error',
      message: err?.message || String(err),
      name: err?.name || 'Error',
      stack: err?.stack || '',
    })
  }
}
