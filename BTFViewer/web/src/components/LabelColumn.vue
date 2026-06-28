<template>
  <div
    ref="colEl"
    class="label-column"
    :style="{ width: labelWidth + 'px' }"
  >
    <!-- Ruler placeholder row -->
    <div
      class="ruler-placeholder"
      :style="{ height: RULER_H + 'px' }"
    />

    <!-- Task / Core label rows (virtualised — only visible rows in DOM) -->
    <div class="labels-body">
      <div
        class="labels-scroll"
        :style="labelsScrollStyle"
      >
        <template
          v-for="row in visibleRows"
          :key="row.key"
        >
          <!-- Core header row -->
          <div
            v-if="row.type === 'core'"
            class="label-row label-core"
            :style="labelRowStyle(row)"
            @click="toggleExpand(row.key)"
          >
          <span
            class="core-dot"
            :style="{ background: row.color }"
          />
          <span class="expand-arrow">{{ expanded.has(row.key) ? '▼' : '▶' }}</span>
          <span class="label-text">{{ row.label }}</span>
        </div>

        <!-- Core sub-task row -->
        <div
          v-else-if="row.type === 'core-task'"
          class="label-row label-core-task"
          :style="labelRowStyle(row)"
          :class="{ highlighted: highlightKey === taskRowKey(row) }"
          @mouseenter="emit('highlightChange', taskRowKey(row))"
          @mouseleave="emit('highlightChange', null)"
          @click="emit('highlightClick', taskRowKey(row))"
        >
          <span
            class="task-swatch"
            :style="{ background: row.color }"
          />
          <span class="label-text sub">{{ row.label }}</span>
        </div>

        <!-- Task row -->
        <div
          v-else-if="row.type === 'task'"
          class="label-row label-task"
          :style="labelRowStyle(row)"
          :class="{ highlighted: highlightKey === row.key }"
          @mouseenter="emit('highlightChange', row.key)"
          @mouseleave="emit('highlightChange', null)"
          @click="emit('highlightClick', row.key)"
        >
          <span
            class="task-swatch"
            :style="{ background: row.color }"
          />
          <span class="label-text">{{ row.label }}</span>
        </div>

        <!-- STI channel row (regular, non-tag) -->
        <div
          v-else-if="row.type === 'sti' && !row.isTag"
          class="label-row label-sti"
          :style="labelRowStyle(row)"
        >
          <span class="sti-dot">◆</span>
          <span class="label-text sti">{{ row.label }}</span>
        </div>

        <!-- STI tag-event channel row (expandable waveform) -->
        <div
          v-else-if="row.type === 'sti' && row.isTag"
          class="label-row label-sti label-sti-tag"
          :style="labelRowStyle(row)"
          @click="emit('stiExpandToggle', row.key)"
        >
          <span class="expand-arrow">{{ row.isExpanded ? '▼' : '▶' }}</span>
          <span class="sti-wave-icon">〰</span>
          <span class="label-text sti">{{ row.label }}</span>
        </div>

        <!-- Interval span row -->
        <div
          v-else-if="row.type === 'interval'"
          class="label-row label-interval"
          :style="labelRowStyle(row)"
        >
          <span
            class="task-swatch interval-swatch"
            :style="{ background: row.color }"
          />
          <span class="label-text">{{ row.label }}</span>
        </div>
      </template>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { rowBandHeight, visibleRowIndexRange, orthRowBuffer, RULER_H } from '../renderer/TimelineRenderer.js'
import { getTimelineLayout } from '../utils/timelineLayout.js'
import { taskMergeKey } from '../utils/colors.js'

function layout() {
  return getTimelineLayout()
}

const props = defineProps({
  trace:        { type: Object, default: null },
  labelWidth:   { type: Number, default: 160 },
  viewMode:     { type: String, default: 'task' },
  expanded:     { type: Object, default: () => new Set() },   // Set
  stiExpanded:  { type: Object, default: () => new Set() },   // Set of expanded tag-event STI channels
  scrollY:      { type: Number, default: 0 },
  bodyH:        { type: Number, default: 400 },
  rowLayout:    { type: Object, default: null },
  highlightKey: { type: [String, null], default: null },
  showSti:      { type: Boolean, default: true },
  migratedOnlyFilter: { type: Boolean, default: false },
})

const emit = defineEmits(['expandToggle', 'highlightChange', 'highlightClick', 'stiExpandToggle'])

const colEl = ref(null)
defineExpose({ colEl })

const totalHeight = computed(() => props.rowLayout?.totalHeight ?? 0)

const visibleRows = computed(() => {
  const rows = props.rowLayout?.rows
  if (!rows?.length) return []
  const { i0, i1 } = visibleRowIndexRange(
    rows, props.scrollY, props.bodyH, Math.max(5, orthRowBuffer(rows.length)),
  )
  return rows.slice(i0, i1)
})

const labelsScrollStyle = computed(() => ({
  height: `${totalHeight.value}px`,
  transform: `translateY(${-props.scrollY}px)`,
}))

function labelRowStyle(row) {
  return {
    position: 'absolute',
    top: `${row.y}px`,
    left: 0,
    right: 0,
    height: `${rowBandHeight(row)}px`,
  }
}

function toggleExpand(coreName) {
  emit('expandToggle', coreName)
}

function taskRowKey(row) {
  return row.type === 'core-task' ? taskMergeKey(row.taskKey) : row.key
}
</script>

<style scoped>
.label-column {
  flex-shrink: 0;
  overflow: hidden;
  border-right: 1px solid var(--border);
  background: var(--panel-bg);
  display: flex;
  flex-direction: column;
  position: relative;
  z-index: 2;
}

.ruler-placeholder {
  flex-shrink: 0;
  border-bottom: 1px solid var(--border);
  background: var(--ruler-bg);
}

.labels-body {
  flex: 1 1 0;
  min-height: 0;
  overflow: hidden;
  position: relative;
}

.labels-scroll {
  position: relative;
  will-change: transform;
}

.label-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 8px;
  cursor: pointer;
  font-size: v-bind('layout().labelFontSize + "px"');
  color: var(--fg);
  transition: background 0.08s;
  box-sizing: border-box;
  overflow: hidden;
}
.label-row:hover {
  background: var(--tb-btn-hover);
}
.label-row.highlighted {
  background: rgba(255, 255, 180, 0.12);
}

.label-core {
  font-weight: 600;
  font-size: 12px;
}

.label-core-task {
  padding-left: 24px;
}

.label-sti {
  cursor: default;
  opacity: 0.8;
}

.label-sti-tag {
  cursor: pointer;
  opacity: 1;
}

.label-interval {
  cursor: default;
  opacity: 1;
}

.interval-swatch {
  border: 1px solid rgba(0, 0, 0, 0.35);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.15);
}

.sti-wave-icon {
  font-size: 12px;
  color: #5BC8FF;
  flex-shrink: 0;
}

.core-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.expand-arrow {
  font-size: 9px;
  opacity: 0.6;
  flex-shrink: 0;
}

.task-swatch {
  width: 10px;
  height: 10px;
  border-radius: 2px;
  flex-shrink: 0;
}

.sti-dot {
  font-size: 9px;
  color: var(--accent);
  flex-shrink: 0;
}

.label-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  font-family: monospace;
}

.label-text.sub {
  opacity: 0.85;
}

.label-text.sti {
  font-style: italic;
  font-size: 10px;
}
</style>
