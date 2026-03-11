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

self.onmessage = function (e) {
  const { text } = e.data
  try {
    const trace = parseBtf(text, (pct, msg) => {
      self.postMessage({ type: 'progress', pct, msg })
    })
    self.postMessage({ type: 'done', trace })
  } catch (err) {
    self.postMessage({ type: 'error', message: err.message })
  }
}
