<template>
  <div class="legend-panel">
    <div class="legend-title">
      Tasks
    </div>
    <input
      :value="taskFilterText"
      class="legend-search"
      type="search"
      placeholder="Filter tasks…"
      @input="onSearchInput"
    >
    <div
      v-if="taskFilterSet"
      class="heatmap-filter-banner"
    >
      <span>Heatmap: {{ heatmapFilterLabel || 'filtered' }} ({{ taskFilterSet.size }})</span>
      <button
        type="button"
        class="heatmap-filter-clear"
        @click="emit('clearTaskFilter')"
      >
        Clear
      </button>
    </div>
    <label class="migrated-filter">
      <input
        :checked="migratedOnlyFilter"
        type="checkbox"
        @change="onMigratedChange"
      >
      Migrated tasks only
    </label>
    <div class="legend-list">
      <div
        v-for="mk in visibleTasks"
        :key="String(mk).replace(/\0|\uFFFD/g, '|')"
        class="legend-item"
        :class="{ highlighted: highlightKey === mk }"
        @mouseenter="emit('highlightChange', mk)"
        @mouseleave="emit('highlightChange', null)"
        @click="emit('highlightClick', mk)"
      >
        <span
          class="swatch"
          :style="{ background: taskColor(mk, trace.taskRepr.get(mk)) }"
        />
        <span class="name">{{ taskDisplayName(trace.taskRepr.get(mk) || mk) }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { taskColor, taskDisplayName } from '../utils/colors.js'
import { isMigratedTask } from '../utils/migrationAnalysis.js'
import { mergeKeyMatchesTextFilter, normalizeTaskFilterText } from '../utils/taskFilter.js'

const props = defineProps({
  trace:        { type: Object, default: null },
  highlightKey: { type: [String, null], default: null },
  taskFilterKeys:     { type: Array, default: null },
  taskFilterText:     { type: String, default: '' },
  migratedOnlyFilter: { type: Boolean, default: false },
  heatmapFilterLabel: { type: String, default: null },
})
const emit = defineEmits(['highlightChange', 'highlightClick', 'migratedFilterChange', 'clearTaskFilter', 'filterChange'])

const taskFilterSet = computed(() => {
  const keys = props.taskFilterKeys
  if (!keys?.length) return null
  return new Set(keys)
})

function onSearchInput(e) {
  emit('filterChange', e.target.value)
}

function onMigratedChange(e) {
  emit('migratedFilterChange', e.target.checked)
}

const visibleTasks = computed(() => {
  const tasks = props.trace?.tasks || []
  const q = normalizeTaskFilterText(props.taskFilterText)
  return tasks.filter((mk) => {
    if (taskFilterSet.value && !taskFilterSet.value.has(mk)) return false
    if (props.migratedOnlyFilter && props.trace && !isMigratedTask(props.trace, mk)) return false
    if (!q) return true
    return mergeKeyMatchesTextFilter(props.trace, mk, q)
  })
})
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

.legend-search {
  width: 100%;
  box-sizing: border-box;
  margin-bottom: 8px;
  padding: 4px 6px;
  border: 1px solid var(--border);
  border-radius: 3px;
  background: var(--tb-bg);
  color: var(--fg);
  font: inherit;
}

.legend-search:focus {
  outline: none;
  border-color: rgba(91, 155, 213, 0.65);
}

.migrated-filter {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
  font-size: 11px;
  color: var(--fg);
  cursor: pointer;
}

.heatmap-filter-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
  padding: 5px 8px;
  border-radius: 4px;
  background: rgba(91, 155, 213, 0.12);
  border: 1px solid rgba(91, 155, 213, 0.35);
  font-size: 10px;
  color: var(--fg);
}

.heatmap-filter-clear {
  flex-shrink: 0;
  border: 1px solid var(--border);
  background: var(--tb-bg);
  color: var(--fg);
  border-radius: 3px;
  padding: 1px 6px;
  font-size: 10px;
  cursor: pointer;
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
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
