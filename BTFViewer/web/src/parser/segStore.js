/**
 * Flat segment storage + SegList views (index arrays into typed buffers).
 * Reduces worker→main transfer cost and memory vs. cloning segment objects.
 */

function internStrings(strings) {
  const table = []
  const id = new Map()
  for (const s of strings) {
    if (!id.has(s)) {
      id.set(s, table.length)
      table.push(s)
    }
  }
  return { table, id }
}

export class SegStore {
  constructor(starts, ends, taskIds, coreIds, taskStrings, coreStrings) {
    this.starts = starts
    this.ends = ends
    this.taskIds = taskIds
    this.coreIds = coreIds
    this.taskStrings = taskStrings
    this.coreStrings = coreStrings
    this.count = starts.length
    this._fly = []
  }

  getSeg(idx) {
    let v = this._fly[idx]
    if (!v) {
      v = {
        idx,
        start: this.starts[idx],
        end: this.ends[idx],
        task: this.taskStrings[this.taskIds[idx]],
        core: this.coreStrings[this.coreIds[idx]],
      }
      this._fly[idx] = v
    }
    return v
  }

  startsForIndices(indices) {
    const out = new Float64Array(indices.length)
    for (let i = 0; i < indices.length; i++) out[i] = this.starts[indices[i]]
    return out
  }

  /** Build store from parse-time segment objects (assigns .idx on each). */
  static fromSegments(segments) {
    const n = segments.length
    const starts = new Float64Array(n)
    const ends = new Float64Array(n)
    const taskTmp = []
    const coreTmp = []
    for (let i = 0; i < n; i++) {
      const s = segments[i]
      starts[i] = s.start
      ends[i] = s.end
      taskTmp.push(s.task)
      coreTmp.push(s.core)
      s.idx = i
    }
    const { table: taskStrings, id: taskId } = internStrings(taskTmp)
    const { table: coreStrings, id: coreId } = internStrings(coreTmp)
    const taskIds = new Uint16Array(n)
    const coreIds = new Uint8Array(n)
    for (let i = 0; i < n; i++) {
      taskIds[i] = taskId.get(taskTmp[i])
      coreIds[i] = coreId.get(coreTmp[i])
    }
    return new SegStore(starts, ends, taskIds, coreIds, taskStrings, coreStrings)
  }

  static fromPacked(packed) {
    return new SegStore(
      new Float64Array(packed.starts),
      new Float64Array(packed.ends),
      new Uint16Array(packed.taskIds),
      new Uint8Array(packed.coreIds),
      packed.taskStrings,
      packed.coreStrings,
    )
  }

  packBuffers() {
    return {
      starts: this.starts.buffer,
      ends: this.ends.buffer,
      taskIds: this.taskIds.buffer,
      coreIds: this.coreIds.buffer,
      taskStrings: this.taskStrings,
      coreStrings: this.coreStrings,
    }
  }

  allIndices() {
    const a = new Uint32Array(this.count)
    for (let i = 0; i < this.count; i++) a[i] = i
    return a
  }
}

function indicesFromSegArray(store, arr) {
  const n = arr.length
  const out = new Uint32Array(n)
  for (let i = 0; i < n; i++) {
    const s = arr[i]
    out[i] = s.idx ?? 0
  }
  return out
}

function convertSegMap(store, map) {
  const out = new Map()
  for (const [k, arr] of map) {
    out.set(k, createSegList(store, indicesFromSegArray(store, arr)))
  }
  return out
}

function convertNestedSegMap(store, map) {
  const out = new Map()
  for (const [core, inner] of map) {
    const innerOut = new Map()
    for (const [task, arr] of inner) {
      innerOut.set(task, createSegList(store, indicesFromSegArray(store, arr)))
    }
    out.set(core, innerOut)
  }
  return out
}

function convertStartsMap(store, segMap) {
  const out = new Map()
  for (const [k, list] of segMap) {
    out.set(k, store.startsForIndices(list._indices))
  }
  return out
}

function convertStartsFromLodMap(store, lodMap) {
  const out = new Map()
  for (const [k, lodList] of lodMap) {
    out.set(k, store.startsForIndices(lodList._indices))
  }
  return out
}

function convertNestedStartsMap(store, nestedLod) {
  const out = new Map()
  for (const [core, inner] of nestedLod) {
    const innerOut = new Map()
    for (const [task, lodList] of inner) {
      innerOut.set(task, store.startsForIndices(lodList._indices))
    }
    out.set(core, innerOut)
  }
  return out
}

/**
 * Replace segment object arrays with SegList views backed by a flat store.
 */
export function finalizeTraceStorage(trace) {
  const store = SegStore.fromSegments(trace.segments)

  trace.segStore = store
  trace.segments = createSegList(store, store.allIndices())

  trace.segByMergeKey = convertSegMap(store, trace.segByMergeKey)
  trace.segLodByMergeKey = convertSegMap(store, trace.segLodByMergeKey)
  trace.segLodUltraByMergeKey = convertSegMap(store, trace.segLodUltraByMergeKey)

  trace.segStartByMergeKey = convertStartsMap(store, trace.segByMergeKey)
  trace.segLodStartsByMergeKey = convertStartsFromLodMap(store, trace.segLodByMergeKey)
  trace.segLodUltraStartsByMergeKey = convertStartsFromLodMap(store, trace.segLodUltraByMergeKey)

  trace.coreSegs = convertSegMap(store, trace.coreSegs)
  trace.coreSegLod = convertSegMap(store, trace.coreSegLod)
  trace.coreSegLodUltra = convertSegMap(store, trace.coreSegLodUltra)
  trace.coreSegStarts = convertStartsMap(store, trace.coreSegs)
  trace.coreSegLodStarts = convertStartsFromLodMap(store, trace.coreSegLod)
  trace.coreSegLodUltraStarts = convertStartsFromLodMap(store, trace.coreSegLodUltra)

  trace.coreTaskSegs = convertNestedSegMap(store, trace.coreTaskSegs)
  trace.coreTaskSegLod = convertNestedSegMap(store, trace.coreTaskSegLod)
  trace.coreTaskSegLodUltra = convertNestedSegMap(store, trace.coreTaskSegLodUltra)
  trace.coreTaskSegStarts = convertNestedStartsMap(store, trace.coreTaskSegLod)
  trace.coreTaskSegLodStarts = convertNestedStartsMap(store, trace.coreTaskSegLod)
  trace.coreTaskSegLodUltraStarts = convertNestedStartsMap(store, trace.coreTaskSegLodUltra)

  return trace
}

export function createSegList(store, indices) {
  const idx = indices instanceof Uint32Array ? indices : new Uint32Array(indices)
  const state = { _startsF64: null, _endsF64: null }

  return new Proxy(state, {
    get(target, prop) {
      if (prop === '_store') return store
      if (prop === '_indices') return idx
      if (prop === 'length') return idx.length
      if (typeof prop === 'symbol') {
        if (prop === Symbol.iterator) {
          return function* () {
            for (let i = 0; i < idx.length; i++) yield store.getSeg(idx[i])
          }
        }
        return undefined
      }
      if (prop === 'map') {
        return (fn) => {
          const out = []
          for (let i = 0; i < idx.length; i++) out.push(fn(store.getSeg(idx[i]), i))
          return out
        }
      }
      if (prop === 'filter') {
        return (fn) => {
          const kept = []
          for (let i = 0; i < idx.length; i++) {
            const s = store.getSeg(idx[i])
            if (fn(s, i)) kept.push(idx[i])
          }
          return createSegList(store, Uint32Array.from(kept))
        }
      }
      if (prop === 'sort') {
        return (cmp) => {
          const order = Array.from({ length: idx.length }, (_, i) => i)
          order.sort((a, b) => cmp(store.getSeg(idx[a]), store.getSeg(idx[b])))
          const sorted = new Uint32Array(order.length)
          for (let i = 0; i < order.length; i++) sorted[i] = idx[order[i]]
          return createSegList(store, sorted)
        }
      }
      if (prop === 'findIndex') {
        return (fn) => {
          for (let i = 0; i < idx.length; i++) if (fn(store.getSeg(idx[i]), i)) return i
          return -1
        }
      }
      if (prop === 'find') {
        return (fn) => {
          for (let i = 0; i < idx.length; i++) {
            const s = store.getSeg(idx[i])
            if (fn(s, i)) return s
          }
          return undefined
        }
      }
      if (prop === 'slice') {
        return (from, to) => createSegList(store, idx.slice(from, to))
      }
      if (prop === 'forEach') {
        return (fn) => {
          for (let i = 0; i < idx.length; i++) fn(store.getSeg(idx[i]), i)
        }
      }
      if (prop === 'some') {
        return (fn) => {
          for (let i = 0; i < idx.length; i++) if (fn(store.getSeg(idx[i]), i)) return true
          return false
        }
      }
      const n = Number(prop)
      if (String(n) === prop && n >= 0 && n < idx.length) {
        return store.getSeg(idx[n])
      }
      return target[prop]
    },
    has(_target, prop) {
      if (prop === 'length') return true
      if (typeof prop === 'string' && /^\d+$/.test(prop)) {
        const n = Number(prop)
        return n >= 0 && n < idx.length
      }
      return false
    },
  })
}
