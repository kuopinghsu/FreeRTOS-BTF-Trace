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
          >{{ formatTime(cur, timeScale, timeDecimals) }}</span>
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
          <span class="delta-value">{{ formatTime(d.delta, timeScale, timeDecimals) }}</span>
          <span class="delta-freq">({{ d.freq }})</span>
        </div>
      </template>
    </div>
    <div
      v-else
      class="cursor-empty-msg"
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M12 3v4M12 17v4M3 12h4M17 12h4"/><circle cx="12" cy="12" r="3"/></svg>
      <span>Click the timeline to place a cursor. Add a second to measure a range.</span>
    </div>

    <div
      v-if="comparisonRows.length > 0"
      class="comparison-block"
    >
      <div class="comparison-title">
        Task at cursor
      </div>
      <CoreFilterChips
        v-if="(trace?.coreNames?.length ?? 0) > 1"
        class="cursor-core-filter"
        label="Cores"
        label-title="Same Core Filter as the Legend — also filters the timeline"
        :core-names="trace.coreNames"
        :core-filter-keys="coreFilterKeys"
        @core-filter-change="emit('coreFilterChange', $event)"
      />
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
import CoreFilterChips from './CoreFilterChips.vue'

const props = defineProps({
  cursors:      { type: Array, required: true },
  trace:        { type: Object, default: null },
  timeScale:    { type: String, default: 'ns' },
  timeDecimals: { type: Number, default: 3 },
  /** Shared with the Legend Core Filter (App `timelineOptions.coreFilterKeys`).
   *  null / empty = every core. */
  coreFilterKeys: { type: Array, default: null },
})

const emit = defineEmits(['deleteCursor', 'jumpToCursor', 'clearAll', 'coreFilterChange'])

const validCursors = computed(() => props.cursors.filter(c => c !== null))

const comparisonRows = computed(() => {
  if (!props.trace) return []
  return cursorComparisonRows(
    props.trace, props.cursors, props.timeScale, props.coreFilterKeys)
})

const deltas = computed(() => {
  const sorted = cursorSortedPlaced(props.cursors)
  return cursorDeltaSegments(sorted, props.timeScale, props.timeDecimals)
})
</script>

<style scoped>
.cursor-panel {
  display: flex;
  flex-direction: column;
  font-family: var(--font-ui, inherit);
  font-size: var(--type-meta, 11px);
}

.cursor-list {
  display: flex;
  flex-direction: column;
  gap: 1px;
  padding: var(--sp-2, 8px);
}

.cursor-empty-msg {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: var(--sp-3, 12px);
  color: var(--fg-dim);
  font-size: var(--type-meta, 11px);
  line-height: 1.45;
}
.cursor-empty-msg svg {
  width: 15px;
  height: 15px;
  flex-shrink: 0;
  margin-top: 1px;
  opacity: 0.7;
}

.cursor-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 6px;
  border-radius: var(--rp-r-1, 6px);
}
.cursor-row:hover {
  background: var(--rp-hover-bg, rgba(127,127,127,0.08));
}

.cursor-time.clickable {
  cursor: pointer;
  opacity: 0.9;
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
  padding: 0 4px;
  border-radius: 4px;
  opacity: 0;
}
.cursor-row:hover .cursor-del { opacity: 0.7; }
.cursor-del:hover {
  color: var(--semantic-error, #FF5555);
  opacity: 1;
  background: var(--tb-btn-hover);
}

.cursor-badge {
  color: #000;
  padding: 1px 6px;
  border-radius: 4px;
  font-weight: 700;
  font-size: 10px;
  min-width: 24px;
  text-align: center;
}

.cursor-time {
  color: var(--fg);
  font-family: var(--font-mono, monospace);
  font-variant-numeric: tabular-nums;
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
  font-family: var(--font-mono, monospace);
  font-variant-numeric: tabular-nums;
  padding: 2px 6px;
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

.cursor-core-filter {
  padding: 2px 4px 6px;
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
  padding: var(--sp-2, 8px);
  border-top: 1px solid var(--rp-border-soft, var(--border));
}

.action-btn {
  font-family: var(--font-ui, inherit);
  font-size: var(--type-meta, 11px);
  padding: 4px 10px;
  border: 1px solid var(--border);
  border-radius: var(--rp-r-1, 6px);
  background: transparent;
  color: var(--fg);
  cursor: pointer;
}
.action-btn:hover:not(:disabled) {
  background: var(--tb-btn-hover);
  border-color: var(--rp-accent-line, var(--accent));
}
.action-btn:disabled {
  color: var(--fg-dim);
  opacity: 0.4;
  cursor: default;
}
</style>
