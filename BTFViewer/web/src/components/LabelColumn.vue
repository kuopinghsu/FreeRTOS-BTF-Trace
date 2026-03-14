<template>
  <div
    ref="colEl"
    class="label-column"
    :style="{ width: LABEL_W + 'px' }"
  >
    <!-- Ruler placeholder row -->
    <div
      class="ruler-placeholder"
      :style="{ height: RULER_H + 'px' }"
    />

    <!-- Task / Core label rows -->
    <div
      class="labels-body"
      :style="{ transform: `translateY(${-scrollY}px)` }"
    >
      <template
        v-for="row in rows"
        :key="row.key"
      >
        <!-- Core header row -->
        <div
          v-if="row.type === 'core'"
          class="label-row label-core"
          :style="{ height: ROW_H + 'px', marginBottom: ROW_GAP + 'px' }"
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
          :style="{ height: ROW_H + 'px', marginBottom: ROW_GAP + 'px' }"
          :class="{ highlighted: highlightKey === row.taskKey }"
          @mouseenter="emit('highlightChange', row.taskKey)"
          @mouseleave="emit('highlightChange', null)"
          @click="emit('highlightClick', row.taskKey)"
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
          :style="{ height: ROW_H + 'px', marginBottom: ROW_GAP + 'px' }"
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

        <!-- STI channel row -->
        <div
          v-else-if="row.type === 'sti'"
          class="label-row label-sti"
          :style="{ height: STI_ROW_H + 'px', marginBottom: ROW_GAP + 'px' }"
        >
          <span class="sti-dot">◆</span>
          <span class="label-text sti">{{ row.label }}</span>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { buildRowLayout, LABEL_W, RULER_H, ROW_H, ROW_GAP, STI_ROW_H } from '../renderer/TimelineRenderer.js'

const props = defineProps({
  trace:        { type: Object, default: null },
  viewMode:     { type: String, default: 'task' },
  expanded:     { type: Object, default: () => new Set() },   // Set
  scrollY:      { type: Number, default: 0 },
  highlightKey: { type: [String, null], default: null },
  showSti:      { type: Boolean, default: true },
})

const emit = defineEmits(['expandToggle', 'highlightChange', 'highlightClick'])

const rows = computed(() => {
  if (!props.trace) return []
  return buildRowLayout(props.trace, props.viewMode, props.expanded, 0, props.showSti).rows
})

function toggleExpand(coreName) {
  emit('expandToggle', coreName)
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
  will-change: transform;
}

.label-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 8px;
  cursor: pointer;
  font-size: 11px;
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
