/**
 * AbortSignal polyfills for older embedded browsers.
 *
 * The Eclipse plug-in hosts the viewer in SWT's platform browser. On Linux GTK
 * that is WebKitGTK, and distributions still ship 2.36 (Safari 15 era), which
 * predates `AbortSignal.prototype.throwIfAborted` (Safari 16),
 * `AbortSignal.timeout` (Safari 16) and `AbortSignal.any` (Safari 17.4).
 * Trace loading calls `signal.throwIfAborted()` on every read step, so without
 * these the first `.btf`/`.btf.gz` open fails with
 * "signal.throwIfAborted is not a function".
 */

function abortReason(signal) {
  if (signal && 'reason' in signal && signal.reason !== undefined) return signal.reason
  const error = new Error('signal is aborted without reason')
  error.name = 'AbortError'
  return error
}

export function installAbortSignalPolyfills(scope = globalThis) {
  const Signal = scope?.AbortSignal
  if (typeof Signal !== 'function') return

  if (typeof Signal.prototype.throwIfAborted !== 'function') {
    Object.defineProperty(Signal.prototype, 'throwIfAborted', {
      configurable: true,
      writable: true,
      value: function throwIfAborted() {
        if (this.aborted) throw abortReason(this)
      },
    })
  }

  if (typeof Signal.timeout !== 'function') {
    Object.defineProperty(Signal, 'timeout', {
      configurable: true,
      writable: true,
      value: function timeout(ms) {
        const controller = new scope.AbortController()
        scope.setTimeout(() => {
          const error = new Error('signal timed out')
          error.name = 'TimeoutError'
          controller.abort(error)
        }, Number(ms) || 0)
        return controller.signal
      },
    })
  }

  if (typeof Signal.any !== 'function') {
    Object.defineProperty(Signal, 'any', {
      configurable: true,
      writable: true,
      value: function any(signals) {
        const list = Array.from(signals || [])
        const controller = new scope.AbortController()
        const already = list.find(s => s?.aborted)
        if (already) {
          controller.abort(abortReason(already))
          return controller.signal
        }
        const onAbort = event => {
          for (const s of list) s?.removeEventListener?.('abort', onAbort)
          controller.abort(abortReason(event?.target))
        }
        for (const s of list) s?.addEventListener?.('abort', onAbort, { once: true })
        return controller.signal
      },
    })
  }
}
