<template>
  <div class="cursor-panel">
    <div
      v-if="validCursors.length > 0"
      class="cursor-list"
    >
      <div
        v-for="(cur, idx) in cursors"
        :key="idx"
        class="cursor-row"
      >
        <template v-if="cur !== null">
          <span
            class="cursor-badge"
            :style="{ background: CURSOR_COLORS[idx] }"
          >C{{ idx + 1 }}</span>
          <span
            class="cursor-time clickable"
            title="Jump to cursor"
            @click="emit('jumpToCursor', cur)"
          >{{ formatTime(cur, timeScale) }}</span>
          <button
            class="cursor-del"
            title="Remove cursor"
            @click="emit('deleteCursor', idx)"
          >
            ×
          </button>
        </template>
        <span
          v-else
          class="cursor-empty"
        >–</span>
      </div>

      <template v-if="deltas.length > 0">
        <div class="delta-sep" />
        <div
          v-for="(d, idx) in deltas"
          :key="'d' + idx"
          class="delta-row"
        >
          <span class="delta-label">Δ{{ d.index }}</span>
          <span class="delta-value">{{ formatTime(d.delta, timeScale) }}</span>
          <span class="delta-freq">({{ d.freq }})</span>
        </div>
      </template>
    </div>
    <div
      v-else
      class="cursor-empty-msg"
    >
      Click timeline to place cursors
    </div>

    <div
      v-if="comparisonRows.length > 0"
      class="comparison-block"
    >
      <div class="comparison-title">
        Task at cursor
      </div>
      <table class="comparison-table">
        <thead>
          <tr>
            <th>#</th>
            <th>Time</th>
            <th>Task</th>
            <th>Δ C1</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in comparisonRows"
            :key="row.label"
            class="comparison-row"
            @click="emit('jumpToCursor', row.ns)"
          >
            <td>{{ row.label }}</td>
            <td>{{ row.time }}</td>
            <td class="task-cell">
              {{ row.task }}
            </td>
            <td>{{ row.delta }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="cursor-actions">
      <button
        class="action-btn"
        :disabled="validCursors.length === 0"
        title="Clear all cursors"
        @click="emit('clearAll')"
      >
        Clear All
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { formatTime } from '../utils/timeFormat.js'
import { CURSOR_COLORS } from '../utils/cursorColors.js'
import { cursorComparisonRows, cursorSortedPlaced, cursorDeltaSegments } from '../utils/cursorAnalysis.js'

const props = defineProps({
  cursors:   { type: Array, required: true },
  trace:     { type: Object, default: null },
  timeScale: { type: String, default: 'ns' },
})

const emit = defineEmits(['deleteCursor', 'jumpToCursor', 'clearAll'])

const validCursors = computed(() => props.cursors.filter(c => c !== null))

const comparisonRows = computed(() => {
  if (!props.trace) return []
  return cursorComparisonRows(props.trace, props.cursors, props.timeScale)
})

const deltas = computed(() => {
  const sorted = cursorSortedPlaced(props.cursors)
  return cursorDeltaSegments(sorted, props.timeScale)
})
</script>

<style scoped>
.cursor-panel {
  display: flex;
  flex-direction: column;
  font-size: 11px;
  font-family: monospace;
}

.cursor-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 12px 4px;
}

.cursor-empty-msg {
  padding: 8px 12px 4px;
  color: var(--fg-dim);
  font-size: 11px;
  font-family: monospace;
}

.cursor-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.cursor-time.clickable {
  cursor: pointer;
  text-decoration: underline dotted;
  opacity: 0.85;
}
.cursor-time.clickable:hover {
  opacity: 1;
  color: var(--accent, #4a9eff);
}

.cursor-del {
  margin-left: auto;
  background: transparent;
  border: none;
  cursor: pointer;
  color: var(--fg-dim);
  font-size: 14px;
  line-height: 1;
  padding: 0 3px;
  border-radius: 3px;
  opacity: 0.6;
}
.cursor-del:hover {
  color: #FF5555;
  opacity: 1;
  background: var(--tb-btn-hover);
}

.cursor-badge {
  color: #000;
  padding: 1px 6px;
  border-radius: 3px;
  font-weight: bold;
  font-size: 10px;
  min-width: 24px;
  text-align: center;
}

.cursor-time {
  color: var(--fg);
}

.cursor-empty {
  color: var(--fg-dim);
  opacity: 0.4;
}

.delta-sep {
  height: 1px;
  background: var(--border);
  margin: 4px 0;
}

.delta-row {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--fg-dim);
}

.delta-label {
  opacity: 0.7;
  min-width: 48px;
}

.delta-value {
  color: var(--fg);
  font-weight: 500;
}

.delta-freq {
  color: var(--fg-dim);
  font-size: 10px;
}

.comparison-block {
  padding: 6px 8px 4px;
  border-top: 1px solid var(--border);
}
.comparison-title {
  font-size: 10px;
  font-weight: 600;
  color: var(--fg-dim);
  margin-bottom: 4px;
  padding: 0 4px;
}
.comparison-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 10px;
}
.comparison-table th {
  text-align: left;
  color: var(--fg-dim);
  font-weight: 500;
  padding: 2px 4px;
  border-bottom: 1px solid var(--border);
}
.comparison-row {
  cursor: pointer;
}
.comparison-row:hover {
  background: var(--tb-btn-hover);
}
.comparison-table td {
  padding: 3px 4px;
  vertical-align: top;
}
.task-cell {
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cursor-actions {
  padding: 6px 12px 8px;
  border-top: 1px solid var(--border);
  margin-top: 2px;
}

.action-btn {
  font-size: 11px;
  padding: 2px 8px;
  border: 1px solid var(--border);
  border-radius: 3px;
  background: transparent;
  color: var(--fg);
  cursor: pointer;
}
.action-btn:hover:not(:disabled) {
  background: var(--tb-btn-hover);
}
.action-btn:disabled {
  color: var(--fg-dim);
  opacity: 0.4;
  cursor: default;
}
</style>
