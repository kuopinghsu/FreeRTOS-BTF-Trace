<template>
  <div class="legend-panel">
    <div class="legend-title">
      Tasks
    </div>
    <div class="core-tint-legend">
      <div class="tint-title">Core tints (Task View)</div>
      <div
        v-for="item in coreTintItems"
        :key="item.core"
        class="tint-row"
      >
        <span
          class="swatch"
          :style="{ background: item.color }"
        />
        <span>{{ item.label }}</span>
      </div>
    </div>
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
        v-model="migratedOnly"
        type="checkbox"
      >
      Migrated tasks only
    </label>
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
import { computed, ref, watch } from 'vue'
import { coreColor, taskColor, taskDisplayName } from '../utils/colors.js'
import { isMigratedTask } from '../utils/migrationAnalysis.js'

const props = defineProps({
  trace:        { type: Object, default: null },
  highlightKey: { type: [String, null], default: null },
  filterText:   { type: String, default: '' },
  taskFilterKeys:     { type: Array, default: null },
  heatmapFilterLabel: { type: String, default: null },
})
const emit = defineEmits(['highlightChange', 'highlightClick', 'migratedFilterChange', 'clearTaskFilter'])

const migratedOnly = ref(false)

const taskFilterSet = computed(() => {
  const keys = props.taskFilterKeys
  if (!keys?.length) return null
  return new Set(keys)
})

watch(migratedOnly, (v) => emit('migratedFilterChange', v))

const coreTintItems = [
  { core: 'Core_0', color: coreColor('Core_0'), label: 'Core_0: base colour' },
  { core: 'Core_1', color: coreColor('Core_1'), label: 'Core_1: blue tint' },
  { core: 'Core_2', color: coreColor('Core_2'), label: 'Core_2: green tint' },
  { core: 'Core_3', color: coreColor('Core_3'), label: 'Core_3: red tint' },
]

const visibleTasks = computed(() => {
  const tasks = props.trace?.tasks || []
  const q = (props.filterText || '').trim().toLowerCase()
  return tasks.filter((mk) => {
    if (taskFilterSet.value && !taskFilterSet.value.has(mk)) return false
    if (migratedOnly.value && props.trace && !isMigratedTask(props.trace, mk)) return false
    if (!q) return true
    const raw = props.trace?.taskRepr?.get(mk) || mk
    const disp = taskDisplayName(raw)
    const hay = `${mk} ${raw} ${disp}`.toLowerCase()
    return hay.includes(q)
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

.core-tint-legend {
  margin-bottom: 8px;
  font-size: 10px;
  color: var(--fg-dim);
  line-height: 1.35;
}

.tint-title {
  font-weight: 600;
  margin-bottom: 2px;
}

.tint-row {
  display: flex;
  align-items: center;
  gap: 6px;
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
