<template>
  <div class="legend-panel">
    <div class="legend-title">Tasks</div>
    <div class="legend-list">
      <div
        v-for="mk in visibleTasks"
        :key="mk"
        class="legend-item"
        :class="{ highlighted: highlightKey === mk }"
        @mouseenter="emit('highlightChange', mk)"
        @mouseleave="emit('highlightChange', null)"
        @click="emit('highlightClick', mk)"
      >
        <span class="swatch" :style="{ background: taskColor(mk, trace.taskRepr.get(mk)) }" />
        <span class="name">{{ taskDisplayName(trace.taskRepr.get(mk) || mk) }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { taskColor, taskDisplayName } from '../utils/colors.js'

const props = defineProps({
  trace:        { type: Object, default: null },
  highlightKey: { type: [String, null], default: null },
})
const emit = defineEmits(['highlightChange', 'highlightClick'])

const visibleTasks = computed(() => props.trace?.tasks || [])
</script>

<style scoped>
.legend-panel {
  padding: 8px;
  overflow-y: auto;
  font-size: 11px;
}

.legend-title {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--fg-dim);
  margin-bottom: 6px;
  padding-bottom: 4px;
  border-bottom: 1px solid var(--border);
}

.legend-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 2px 4px;
  border-radius: 3px;
  cursor: pointer;
  transition: background 0.08s;
}
.legend-item:hover {
  background: var(--tb-btn-hover);
}
.legend-item.highlighted {
  background: rgba(255, 255, 180, 0.12);
}

.swatch {
  width: 10px;
  height: 10px;
  border-radius: 2px;
  flex-shrink: 0;
}

.name {
  font-family: monospace;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--fg);
}
</style>
