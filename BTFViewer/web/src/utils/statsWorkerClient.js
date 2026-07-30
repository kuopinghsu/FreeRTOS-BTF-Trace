/**
 * Client for the statistics Web Worker (register trace + debounced table compute).
 */
import { segIndicesMapFromTrace } from '../parser/statsCompute.js'

let _worker = null
let _ready = false
let _pendingRegister = null
let _initPromise = null
let _seq = 0
const _callbacks = new Map()

function wireWorker(worker) {
  worker.onmessage = ({ data }) => {
    if (data.type === 'registered') {
      _ready = true
      _pendingRegister?.resolve()
      _pendingRegister = null
      return
    }
    if (data.type === 'result') {
      const cb = _callbacks.get(data.id)
      if (cb) {
        _callbacks.delete(data.id)
        cb(data)
      }
      return
    }
    if (data.type === 'error') {
      const cb = _callbacks.get(data.id)
      if (cb) {
        _callbacks.delete(data.id)
        cb(data)
      }
    }
  }
  worker.onerror = () => {
    _ready = false
    _pendingRegister?.reject(new Error('Stats worker error'))
    _pendingRegister = null
    for (const cb of _callbacks.values()) cb({ type: 'error' })
    _callbacks.clear()
  }
}

async function ensureWorker() {
  if (_worker) return _worker
  if (_initPromise) return _initPromise

  _initPromise = (async () => {
    try {
      if (!globalThis.Worker) return null
      const InlineWorker = (await import('../parser/statsWorker.js?worker&inline')).default
      const worker = new InlineWorker()
      wireWorker(worker)
      _worker = worker
      return worker
    } catch {
      return null
    }
  })()

  return _initPromise
}

export function statsWorkerAvailable() {
  return _worker != null
}

function copyArrayBuffer(buf) {
  return buf.slice(0)
}

export async function registerTraceWithStatsWorker(trace) {
  const worker = await ensureWorker()
  if (!worker || !trace?.segStore) return false

  _ready = false
  // A new registration supersedes any still-pending one - reject it now so its
  // caller doesn't hang forever instead of silently losing its promise.
  _pendingRegister?.reject(new Error('Superseded by a newer registration'))
  const store = trace.segStore
  const segIndicesByMk = [...segIndicesMapFromTrace(trace).entries()].map(([mk, idx]) => [
    mk, idx.buffer,
  ])

  const regPromise = new Promise((resolve, reject) => {
    _pendingRegister = { resolve, reject }
  })
  const timeout = setTimeout(() => {
    if (_pendingRegister) {
      _pendingRegister.reject(new Error('Stats worker registration timeout'))
      _pendingRegister = null
    }
  }, 60_000)

  try {
    worker.postMessage({
      type: 'register',
      store: {
        starts: copyArrayBuffer(store.starts.buffer),
        ends: copyArrayBuffer(store.ends.buffer),
        taskIds: copyArrayBuffer(store.taskIds.buffer),
        coreIds: copyArrayBuffer(store.coreIds.buffer),
        taskStrings: store.taskStrings,
        coreStrings: store.coreStrings,
      },
      tasks: trace.tasks,
      taskRepr: [...trace.taskRepr.entries()],
      segIndicesByMk,
      timeMin: trace.timeMin,
      timeMax: trace.timeMax,
    })
    await regPromise
    return true
  } catch {
    _ready = false
    return false
  } finally {
    clearTimeout(timeout)
  }
}

export async function requestStatsCompute({
  lo,
  hi,
  wantExec,
  wantBlock,
  wantInter,
}) {
  const worker = await ensureWorker()
  if (!worker || !_ready) return null

  const id = ++_seq
  return new Promise((resolve) => {
    _callbacks.set(id, (data) => {
      if (data.type === 'error') {
        resolve(null)
        return
      }
      resolve(data)
    })
    worker.postMessage({
      type: 'compute',
      id,
      lo,
      hi,
      wantExec: !!wantExec,
      wantBlock: !!wantBlock,
      wantInter: !!wantInter,
    })
  })
}

export function terminateStatsWorker() {
  if (_worker) {
    _worker.terminate()
    _worker = null
    _ready = false
    _initPromise = null
    _callbacks.clear()
  }
}
