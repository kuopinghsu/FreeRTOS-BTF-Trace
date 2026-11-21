/** Run one operation and release its worker on completion, failure, or abort. */
export function runTraceWorker(worker, request, { signal, transfer = [], onProgress } = {}) {
  return new Promise((resolve, reject) => {
    function finish(callback, value) {
      signal?.removeEventListener('abort', abort)
      worker.onmessage = worker.onerror = worker.onmessageerror = null
      worker.terminate()
      callback(value)
    }
    function abort() {
      finish(reject, signal.reason)
    }
    function fail(event) {
      finish(reject, new Error(event.message || 'Trace worker could not complete the operation'))
    }
    if (signal?.aborted) {
      abort()
      return
    }
    signal?.addEventListener('abort', abort, { once: true })
    worker.onerror = worker.onmessageerror = fail
    worker.onmessage = ({ data }) => {
      if (data.type === 'progress') {
        onProgress?.(data.pct, data.msg)
      } else if (data.type === 'error') {
        const error = new Error(data.message)
        error.name = data.name || 'Error'
        finish(reject, error)
      } else if (data.type === 'done') {
        finish(resolve, data)
      }
    }
    try {
      worker.postMessage(request, transfer)
    } catch (error) {
      finish(reject, error)
    }
  })
}
