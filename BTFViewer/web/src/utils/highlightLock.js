/**
 * Timeline lock-highlight + CPU Load filter share one selected-task key.
 * Segment click and legend/name pin are mutually exclusive in the UI;
 * if both are present, the segment wins (same as CpuLoadPanel).
 */
import { taskMergeKey } from './colors.js'

export function selectedTaskFromHighlight(state) {
  if (!state) return null
  const seg = state.highlightSegment
  if (seg?.task) return taskMergeKey(seg.task)
  const pin = state.pinnedHighlightKey
  return (pin != null && pin !== '') ? pin : null
}
