<template>
  <div class="legend-panel">
    <div class="legend-header">
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
        <span>Migration: {{ heatmapFilterLabel || 'tasks' }} ({{ taskFilterSet.size }})</span>
        <button
          type="button"
          class="heatmap-filter-clear"
          title="Clear this Filter"
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
    </div>

    <div class="legend-list-scroll">
      <div class="legend-list">
        <div
          v-for="mk in visibleTasks"
          :key="String(mk).replace(/\0|\uFFFD/g, '|')"
          class="legend-item"
          :class="{ highlighted: highlightKey === mk, selected: selectedKey === mk, filtered: taskFilterSet && taskFilterSet.has(mk) }"
          :title="`${taskDisplayName(trace.taskRepr.get(mk) || mk)} \u2014 hover to Highlight, click to Select`"
          @mouseenter="emit('highlightChange', mk)"
          @mouseleave="emit('highlightChange', null)"
          @click="emit('highlightClick', mk)"
        >
          <span
            class="swatch"
            :style="{ background: swatchColor(mk, trace.taskRepr.get(mk)) }"
          />
          <span class="name">{{ taskDisplayName(trace.taskRepr.get(mk) || mk) }}</span>
        </div>
      </div>
    </div>

    <div
      v-if="showCoreFilter"
      class="legend-cores"
    >
      <div class="legend-cores-header">
        <span class="legend-title legend-cores-title">Cores</span>
        <button
          v-if="coreFilterKeys?.length"
          type="button"
          class="heatmap-filter-clear"
          title="Clear Core Filter and show all cores"
          @click="emit('coreFilterChange', null)"
        >
          Clear
        </button>
      </div>
      <div class="legend-cores-scroll">
        <label
          v-for="coreName in trace.coreNames"
          :key="coreName"
          class="migrated-filter core-filter-item"
        >
          <input
            :checked="coreChecked(coreName)"
            type="checkbox"
            @change="onCoreCheckChange(coreName, $event.target.checked)"
          >
          {{ coreName }}
        </label>
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
  selectedKey:  { type: [String, null], default: null },
  taskFilterKeys:     { type: Array, default: null },
  taskFilterText:     { type: String, default: '' },
  migratedOnlyFilter: { type: Boolean, default: false },
  heatmapFilterLabel: { type: String, default: null },
  viewMode:           { type: String, default: 'task' },
  coreFilterKeys:     { type: Array, default: null },
  darkMode:           { type: Boolean, default: true },
  colorblindSafe:     { type: Boolean, default: false },
})
const emit = defineEmits(['highlightChange', 'highlightClick', 'migratedFilterChange', 'clearTaskFilter', 'filterChange', 'coreFilterChange'])

function swatchColor(mk, repr) {
  // taskColor() reads non-reactive module state; touch the props here so
  // Vue re-renders swatches when the theme or colorblind-safe setting changes.
  void props.darkMode
  void props.colorblindSafe
  return taskColor(mk, repr)
}

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

/** Core Filter (Core View only) — narrows Scope to a subset of cores, mirrors the Task list. */
const showCoreFilter = computed(() => props.viewMode === 'core' && (props.trace?.coreNames?.length ?? 0) > 1)

function coreChecked(coreName) {
  return !props.coreFilterKeys?.length || props.coreFilterKeys.includes(coreName)
}

function onCoreCheckChange(coreName, checked) {
  const all = props.trace?.coreNames || []
  const cur = props.coreFilterKeys?.length ? props.coreFilterKeys : [...all]
  const next = checked ? [...new Set([...cur, coreName])] : cur.filter(c => c !== coreName)
  emit('coreFilterChange', next)
}
</script>

<style scoped>
.legend-panel {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  padding: 8px;
  font-size: 11px;
}

.legend-header {
  flex-shrink: 0;
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

.legend-list-scroll {
  flex: 1;
  min-height: 40px;
  overflow-y: auto;
}

.legend-cores {
  flex-shrink: 0;
  margin-top: 12px;
  padding-top: 8px;
  border-top: 1px solid var(--border);
}

.legend-cores-scroll {
  max-height: 160px;
  overflow-y: auto;
}

.legend-cores-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}

.legend-cores-title {
  margin-bottom: 0;
  padding-bottom: 0;
  border-bottom: none;
}

.core-filter-item {
  margin-bottom: 4px;
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
.legend-item.selected {
  background: rgba(255, 255, 180, 0.12);
  border: 1px solid var(--accent);
  padding: 1px 3px;
}
.legend-item.filtered {
  border-left: 2px solid #5B9BD5;
  padding-left: 2px;
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
