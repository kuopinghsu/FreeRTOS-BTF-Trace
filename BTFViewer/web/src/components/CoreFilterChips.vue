<template>
  <div
    class="core-filter-row"
    role="group"
    :aria-label="label || 'Cores'"
  >
    <span
      v-if="label"
      class="core-filter-label"
      :title="labelTitle"
    >{{ label }}</span>
    <button
      v-for="chip in chips"
      :key="chip.name"
      type="button"
      class="core-chip"
      :class="{ off: !chip.on }"
      :aria-pressed="chip.on"
      :title="(chip.on ? 'Hide ' : 'Show ') + chip.name"
      @click="toggle(chip.name)"
    >{{ chip.short }}</button>
    <button
      v-if="anyOff"
      type="button"
      class="core-chip-clear"
      title="Show all cores"
      @click="emit('coreFilterChange', null)"
    >All</button>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  /** Every core name in the trace, in order. */
  coreNames:      { type: Array, default: () => [] },
  /** Selected cores (App `timelineOptions.coreFilterKeys`). null / empty = all. */
  coreFilterKeys: { type: Array, default: null },
  /** Optional inline label before the chips. */
  label:          { type: String, default: '' },
  labelTitle:     { type: String, default: '' },
})

const emit = defineEmits(['coreFilterChange'])

/** Strip the "Core_" / "Core" prefix for a compact chip label. */
function coreShortLabel(name) {
  const m = /^Core[_ ]?(.+)$/.exec(name)
  return m ? m[1] : name
}

const chips = computed(() => props.coreNames.map(name => ({
  name,
  short: coreShortLabel(name),
  on: !props.coreFilterKeys?.length || props.coreFilterKeys.includes(name),
})))

const anyOff = computed(() => chips.value.some(c => !c.on))

function toggle(name) {
  const all = props.coreNames
  const cur = props.coreFilterKeys?.length ? props.coreFilterKeys : [...all]
  const on = cur.includes(name)
  const next = on ? cur.filter(c => c !== name) : [...new Set([...cur, name])]
  emit('coreFilterChange', next)
}
</script>

<style scoped>
.core-filter-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
}
.core-filter-label {
  font-size: 10px;
  color: var(--fg-dim);
  margin-right: 2px;
}
.core-chip {
  min-width: 20px;
  height: 18px;
  padding: 0 5px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--border);
  border-radius: 5px;
  background: var(--app-surface-2, transparent);
  color: var(--accent);
  font-family: var(--font-mono, monospace);
  font-variant-numeric: tabular-nums;
  font-size: 10px;
  font-weight: 600;
  cursor: pointer;
}
.core-chip:hover { border-color: var(--app-accent-line, var(--accent)); }
.core-chip.off {
  color: var(--fg-dim);
  background: transparent;
  text-decoration: line-through;
  opacity: 0.6;
}
.core-chip-clear {
  height: 18px;
  padding: 0 7px;
  border: 0;
  background: transparent;
  color: var(--accent);
  font-family: var(--font-ui, inherit);
  font-size: 10px;
  font-weight: 600;
  cursor: pointer;
}
.core-chip-clear:hover { text-decoration: underline; }
</style>
