<template>
  <div
    class="column-header-row"
    :style="{ height: headerH + 'px' }"
  >
    <div
      class="ruler-corner"
      :style="{ width: RULER_W + 'px' }"
    />
    <div class="headers-body">
      <div
        class="headers-scroll"
        :style="headersScrollStyle"
      >
        <div
          v-for="col in visibleCols"
          :key="col.key"
          class="col-header"
          :class="colClass(col)"
          :style="colHeaderStyle(col)"
          @click="onColClick(col)"
          @mouseenter="onColHover(col, true)"
          @mouseleave="onColHover(col, false)"
        >
          <span
            v-if="col.type === 'core'"
            class="expand-arrow"
          >{{ expanded.has(col.key) ? '▼' : '▶' }}</span>
          <span
            v-if="col.isExpandable"
            class="expand-arrow"
          >{{ col.isExpanded ? '▼' : '▶' }}</span>
          <span
            v-if="col.type === 'task' || col.type === 'core-task'"
            class="task-swatch"
            :style="{ background: col.color }"
          />
          <span
            v-else-if="col.type === 'interval'"
            class="task-swatch interval-swatch"
            :style="{ background: col.color }"
          />
          <span class="col-label">{{ displayLabel(col) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { colBandWidth, visibleColumnIndexRange, RULER_W, HEADER_H } from '../renderer/TimelineRenderer.js'
import { taskMergeKey } from '../utils/colors.js'

const props = defineProps({
  columnLayout: { type: Object, default: null },
  scrollX:      { type: Number, default: 0 },
  canvasW:      { type: Number, default: 800 },
  headerH:      { type: Number, default: HEADER_H },
  highlightKey: { type: [String, null], default: null },
  expanded:     { type: Object, default: () => new Set() },
})

const emit = defineEmits(['expandToggle', 'stiExpandToggle', 'highlightChange', 'highlightClick'])

const totalWidth = computed(() => props.columnLayout?.totalWidth ?? 0)
const bodyWidth = computed(() => Math.max(0, totalWidth.value - RULER_W))

const visibleCols = computed(() => {
  const cols = props.columnLayout?.cols
  if (!cols?.length) return []
  const { i0, i1 } = visibleColumnIndexRange(
    cols, props.scrollX || 0, props.canvasW, 3, RULER_W,
  )
  return cols.slice(i0, i1)
})

const headersScrollStyle = computed(() => ({
  width: `${bodyWidth.value}px`,
  height: `${props.headerH}px`,
  transform: `translateX(${-(props.scrollX || 0)}px)`,
}))

function colHeaderStyle(col) {
  const cw = colBandWidth(col)
  return {
    position: 'absolute',
    left: `${col.x - RULER_W}px`,
    top: 0,
    width: `${cw}px`,
    height: `${props.headerH}px`,
  }
}

function colClass(col) {
  const key = taskRowKey(col)
  return {
    highlighted: props.highlightKey != null && props.highlightKey === key,
    'col-core': col.type === 'core',
    'col-sti': col.type === 'sti',
    'col-interval': col.type === 'interval',
  }
}

function displayLabel(col) {
  let raw = col.label
  const maxChars = Math.max(1, Math.floor((props.headerH - 20) / 7))
  if (raw.length > maxChars) raw = raw.substring(0, maxChars - 1) + '…'
  return raw
}

function taskRowKey(col) {
  if (col.type === 'core-task') return taskMergeKey(col.taskKey)
  return col.key
}

function onColClick(col) {
  if (col.type === 'core') {
    emit('expandToggle', col.key)
    return
  }
  if (col.isExpandable) {
    emit('stiExpandToggle', col.key)
    return
  }
  const key = taskRowKey(col)
  if (col.type === 'task' || col.type === 'core-task') {
    emit('highlightClick', key)
  }
}

function onColHover(col, enter) {
  if (col.type === 'task' || col.type === 'core-task') {
    emit('highlightChange', enter ? taskRowKey(col) : null)
  }
}

</script>

<style scoped>
.column-header-row {
  flex-shrink: 0;
  z-index: 10;
  display: flex;
  overflow: hidden;
  pointer-events: auto;
}

.ruler-corner {
  flex-shrink: 0;
  background: var(--ruler-bg);
  border-right: 1px solid var(--border);
}

.headers-body {
  flex: 1 1 0;
  min-width: 0;
  height: 100%;
  overflow: hidden;
  position: relative;
  background: var(--panel-bg);
  border-bottom: 1px solid var(--border);
}

.headers-scroll {
  position: relative;
  will-change: transform;
}

.col-header {
  box-sizing: border-box;
  cursor: pointer;
  border-left: 1px solid var(--border);
  overflow: visible;
}

.col-header:hover {
  background: var(--tb-btn-hover);
}

.col-header.highlighted {
  background: rgba(255, 255, 180, 0.12);
}

.col-sti {
  color: #88aabb;
}

.col-interval {
  cursor: default;
}

.task-swatch {
  position: absolute;
  top: 6px;
  left: 50%;
  transform: translateX(-50%);
  width: 8px;
  height: 8px;
  border-radius: 1px;
}

.interval-swatch {
  border-radius: 2px;
}

.expand-arrow {
  position: absolute;
  top: 4px;
  left: 3px;
  font-size: 8px;
  line-height: 1;
  opacity: 0.75;
}

.col-label {
  position: absolute;
  left: 50%;
  bottom: 10px;
  transform: translateX(-50%) rotate(-90deg);
  transform-origin: center center;
  white-space: nowrap;
  font: 11px monospace;
  color: var(--fg);
  max-width: 140px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.col-sti .col-label {
  color: #88aabb;
}
</style>
