/** Simple undo/redo stack for cursors + marks state. */

const MAX_DEPTH = 50

export function createUndoStack() {
  const past = []
  const future = []

  function snapshotOf({ cursors, marks, markNextId }) {
    return {
      cursors: cursors ? [...cursors] : [],
      marks: marks ? JSON.parse(JSON.stringify(marks)) : [],
      markNextId: markNextId ?? 1,
    }
  }

  function push(state) {
    past.push(snapshotOf(state))
    if (past.length > MAX_DEPTH) past.shift()
    future.length = 0
  }

  function canUndo() { return past.length > 0 }
  function canRedo() { return future.length > 0 }

  function undo(current) {
    if (!past.length) return null
    future.push(snapshotOf(current))
    return past.pop()
  }

  function redoAction(current) {
    if (!future.length) return null
    past.push(snapshotOf(current))
    return future.pop()
  }

  function clear() {
    past.length = 0
    future.length = 0
  }

  return { push, undo, redo: redoAction, canUndo, canRedo, clear }
}
