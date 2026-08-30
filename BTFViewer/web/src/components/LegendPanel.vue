<template>
  <div class="legend-panel">
    <div class="legend-header">
      <div class="legend-title">
        Tasks
      </div>
      <div class="legend-search-wrap">
        <svg class="legend-search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="M21 21l-4.3-4.3" /></svg>
        <input
          :value="taskFilterText"
          class="legend-search"
          type="search"
          placeholder="Filter tasks…"
          @input="onSearchInput"
        >
      </div>
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
        <span
          v-if="coreFilterKeys?.length"
          class="legend-cores-count"
        >{{ coreFilterKeys.length }} of {{ trace.coreNames.length }}</span>
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
      <p class="legend-cores-hint">Shared filter — also scopes the timeline &amp; Cursors panel.</p>
      <CoreFilterChips
        :core-names="trace.coreNames"
        :core-filter-keys="coreFilterKeys"
        @core-filter-change="emit('coreFilterChange', $event)"
      />
    </div>
  </div>
</template>


<script setup>
import { computed } from 'vue'
import { taskColor, taskDisplayName } from '../utils/colors.js'
import { isMigratedTask } from '../utils/migrationAnalysis.js'
import { mergeKeyMatchesTextFilter, normalizeTaskFilterText, taskRunsOnSelectedCore } from '../utils/taskFilter.js'
import CoreFilterChips from './CoreFilterChips.vue'

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
    // Core Filter — mirror the timeline task panel: hide tasks with no segment
    // on any selected core.
    if (!taskRunsOnSelectedCore(props.trace, mk, props.coreFilterKeys)) return false
    if (!q) return true
    return mergeKeyMatchesTextFilter(props.trace, mk, q)
  })
})

/**
 * Core Filter — a subset of cores shared across the app (`timelineOptions.coreFilterKeys`):
 * in Core View it narrows the timeline layout; it also scopes the Cursors panel's
 * "Task at cursor" list and the status-bar Core chip. Shown for any multi-core trace.
 */
const showCoreFilter = computed(() => (props.trace?.coreNames?.length ?? 0) > 1)
</script>

<style scoped>
.legend-panel {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  padding: var(--sp-3, 12px);
  font-family: var(--font-ui, inherit);
  font-size: var(--type-meta, 11px);
}

.legend-header {
  flex-shrink: 0;
}

.legend-title {
  font-family: var(--font-ui, inherit);
  font-size: var(--type-meta, 11px);
  font-weight: 600;
  letter-spacing: 0.01em;
  color: var(--fg);
  margin-bottom: var(--sp-2, 8px);
}

.legend-search-wrap {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: var(--sp-2, 8px);
  padding: 4px 8px;
  border: 1px solid var(--border);
  border-radius: var(--rp-r-1, 6px);
  background: var(--rp-surface-2, var(--tb-bg));
}
.legend-search-wrap:focus-within {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--rp-sel-bg, rgba(79, 139, 255, 0.15));
}
.legend-search-icon {
  width: 13px;
  height: 13px;
  flex-shrink: 0;
  color: var(--fg-dim);
}

.legend-search {
  flex: 1;
  min-width: 0;
  box-sizing: border-box;
  padding: 2px 0;
  border: 0;
  background: transparent;
  color: var(--fg);
  font-family: var(--font-ui, inherit);
  font-size: var(--type-meta, 11px);
}
.legend-search:focus { outline: none; }
.legend-search::-webkit-search-cancel-button { display: none; }

.migrated-filter {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: var(--sp-2, 8px);
  font-size: var(--type-meta, 11px);
  color: var(--fg);
  cursor: pointer;
}

.heatmap-filter-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: var(--sp-2, 8px);
  padding: 4px 6px 4px 9px;
  border-radius: 999px;
  background: var(--rp-sel-bg, rgba(79, 139, 255, 0.12));
  border: 1px solid var(--rp-accent-line, rgba(79, 139, 255, 0.35));
  font-family: var(--font-mono, monospace);
  font-size: 10px;
  color: var(--accent);
}

.heatmap-filter-clear {
  flex-shrink: 0;
  border: 1px solid var(--border);
  background: transparent;
  color: var(--fg-dim);
  border-radius: var(--rp-r-1, 6px);
  padding: 2px 8px;
  font-family: var(--font-ui, inherit);
  font-size: 10px;
  cursor: pointer;
}
.heatmap-filter-clear:hover {
  color: var(--fg);
  border-color: var(--rp-accent-line, var(--accent));
}

.legend-list {
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.legend-list-scroll {
  flex: 1;
  min-height: 40px;
  overflow-y: auto;
}

.legend-cores {
  flex-shrink: 0;
  margin-top: var(--sp-3, 12px);
  padding-top: var(--sp-2, 8px);
  border-top: 1px solid var(--rp-border-soft, var(--border));
}

.legend-cores-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 2px;
}

.legend-cores-title {
  margin-bottom: 0;
  flex: 1;
}

.legend-cores-count {
  font-family: var(--font-mono, monospace);
  font-variant-numeric: tabular-nums;
  font-size: 9px;
  color: var(--fg-dim);
  background: var(--rp-surface-3, var(--tb-btn-hover));
  padding: 1px 6px;
  border-radius: 999px;
}

.legend-cores-hint {
  margin: 0 0 6px;
  font-size: 9px;
  color: var(--fg-dim);
  opacity: 0.75;
  line-height: 1.3;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 6px;
  border-radius: var(--rp-r-1, 6px);
  cursor: pointer;
  transition: background 0.08s;
}
.legend-item:hover {
  background: var(--rp-hover-bg, var(--tb-btn-hover));
}
.legend-item.highlighted {
  background: var(--rp-hover-bg, rgba(255, 255, 180, 0.12));
}
.legend-item.selected {
  background: var(--rp-sel-bg, rgba(255, 255, 180, 0.12));
  box-shadow: inset 3px 0 0 var(--accent);
}
.legend-item.filtered {
  box-shadow: inset 3px 0 0 var(--cmp-b, #5B9BD5);
}
.legend-item.selected.filtered {
  box-shadow: inset 3px 0 0 var(--accent), inset 6px 0 0 var(--cmp-b, #5B9BD5);
}

.swatch {
  width: 10px;
  height: 10px;
  border-radius: 3px;
  flex-shrink: 0;
  box-shadow: inset 0 0 0 1px rgba(0, 0, 0, 0.2);
}

.name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
