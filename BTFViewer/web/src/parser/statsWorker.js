/**
 * Web Worker: heavy statistics table computation off the main thread.
 */
import { SegStore } from './segStore.js'
import { computeStatsTables } from './statsCompute.js'

let _store = null
let _tasks = []
let _taskRepr = null
let _segIndicesByMk = null
let _timeMin = 0
let _timeMax = 0

self.onmessage = (e) => {
  const data = e.data
  if (data.type === 'register') {
    _store = SegStore.fromPacked(data.store)
    _tasks = data.tasks
    _taskRepr = new Map(data.taskRepr)
    _segIndicesByMk = new Map(
      data.segIndicesByMk.map(([mk, buf]) => [mk, new Uint32Array(buf)]),
    )
    _timeMin = data.timeMin
    _timeMax = data.timeMax
    self.postMessage({ type: 'registered' })
    return
  }

  if (data.type === 'compute') {
    if (!_store) {
      self.postMessage({ type: 'error', id: data.id, message: 'Stats worker not registered' })
      return
    }
    const lo = data.lo ?? null
    const hi = data.hi ?? null
    const totalNs = lo != null && hi != null ? hi - lo : _timeMax - _timeMin
    const result = computeStatsTables(_store, {
      tasks: _tasks,
      taskRepr: _taskRepr,
      segIndicesByMk: _segIndicesByMk,
      lo,
      hi,
      totalNs,
    })
    self.postMessage({
      type: 'result',
      id: data.id,
      exec: data.wantExec ? result.exec : null,
      block: data.wantBlock ? result.block : null,
      inter: data.wantInter ? result.inter : null,
      taskCpuNs: result.taskCpuNs,
    })
  }
}
