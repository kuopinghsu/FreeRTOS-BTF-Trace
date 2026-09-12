/**
 * Narrow host adapter for embedding the existing viewer.
 *
 * Hosts register one callable bridge before this module is loaded. The viewer
 * exposes only the explicit operations registered by App.vue; arbitrary Java
 * methods and arbitrary JavaScript evaluation are never dispatched here.
 */

const ECLIPSE_BRIDGE_NAME = 'btfviewerEclipseBridge'

let registeredApi = Object.freeze({})

function eclipseBridge() {
  if (typeof window === 'undefined') return null
  const bridge = window[ECLIPSE_BRIDGE_NAME]
  return typeof bridge === 'function' ? bridge : null
}

function notify(type, payload = {}) {
  const bridge = eclipseBridge()
  if (!bridge) return false
  bridge(JSON.stringify({ type: String(type), payload }))
  return true
}

function callApi(name, ...args) {
  const fn = registeredApi[name]
  if (typeof fn !== 'function') {
    return Promise.reject(new Error(`Viewer host operation is unavailable: ${name}`))
  }
  try {
    return Promise.resolve(fn(...args))
  } catch (err) {
    return Promise.reject(err)
  }
}

/** Install the host surface once the Vue application is ready. */
export function installViewerHostApi(api = {}) {
  registeredApi = Object.freeze({ ...api })
  if (typeof window === 'undefined') return () => {}

  const host = Object.freeze({
    type: eclipseBridge() ? 'eclipse' : 'standalone',
    notify,
    openTraceUrl: (traceRef, name) => callApi('openTraceUrl', traceRef, name),
    setTheme: theme => callApi('setTheme', theme),
    openStatistics: () => callApi('openStatistics'),
    openTraceCompare: () => callApi('openTraceCompare'),
  })
  Object.defineProperty(window, 'BTFViewerHost', {
    configurable: true,
    enumerable: true,
    value: host,
  })
  return () => {
    registeredApi = Object.freeze({})
    if (window.BTFViewerHost === host) delete window.BTFViewerHost
  }
}

export function notifyViewerHost(type, payload = {}) {
  return notify(type, payload)
}

