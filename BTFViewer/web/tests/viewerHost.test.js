import assert from 'node:assert/strict'
import test from 'node:test'

import { installViewerHostApi, notifyViewerHost } from '../src/utils/viewerHost.js'

test('standalone host exposes only the explicit API', async () => {
  globalThis.window = {}
  const calls = []
  const uninstall = installViewerHostApi({
    setTheme: value => calls.push(value),
  })
  assert.equal(window.BTFViewerHost.type, 'standalone')
  assert.deepEqual(Object.keys(window.BTFViewerHost).sort(), [
    'notify', 'openStatistics', 'openTraceCompare', 'openTraceUrl', 'setTheme', 'type',
  ])
  await window.BTFViewerHost.setTheme('dark')
  assert.deepEqual(calls, ['dark'])
  uninstall()
  assert.equal(window.BTFViewerHost, undefined)
  delete globalThis.window
})

test('eclipse host emits structured messages through the registered bridge', () => {
  const messages = []
  globalThis.window = {
    btfviewerEclipseBridge: value => messages.push(JSON.parse(value)),
  }
  const uninstall = installViewerHostApi({})
  assert.equal(window.BTFViewerHost.type, 'eclipse')
  assert.equal(notifyViewerHost('viewerReady', { ok: true }), true)
  assert.deepEqual(messages, [{ type: 'viewerReady', payload: { ok: true } }])
  uninstall()
  delete globalThis.window
})

test('unregistered operations reject instead of dispatching arbitrary names', async () => {
  globalThis.window = {}
  const uninstall = installViewerHostApi({})
  await assert.rejects(window.BTFViewerHost.openStatistics(), /operation is unavailable/)
  assert.equal(window.BTFViewerHost.runJava, undefined)
  uninstall()
  delete globalThis.window
})

