<template>
  <div
    v-if="showStrip"
    class="analysis-context-strip"
    role="status"
    :aria-label="ariaLabel"
  >
    <span
      v-for="(line, i) in lines"
      :key="i"
      class="ctx-chip"
      :class="{ 'ctx-note': line === cursorsNote }"
      :title="line === cursorsNote
        ? 'Cursors are placed, but Limit to C1–Cn is off — Statistics still use the full trace'
        : line"
    >{{ line }}</span>
    <button
      v-if="stale"
      type="button"
      class="ctx-recalc"
      @click="$emit('recalculate')"
    >
      {{ staleAction }}
    </button>
    <button
      v-if="showClearFilters && onClearFilters"
      type="button"
      class="ctx-clear"
      title="Clear filters"
      @click="onClearFilters()"
    >
      Clear filters
    </button>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { formatAnalysisContextLines, staleResultBanner, CURSORS_NOT_LIMITING_NOTE } from '../utils/analysisContext.js'

const props = defineProps({
  context: { type: Object, default: null },
  stale: { type: Boolean, default: false },
  compact: { type: Boolean, default: false },
  showClearFilters: { type: Boolean, default: false },
  onClearFilters: { type: Function, default: null },
})

defineEmits(['recalculate'])

const cursorsNote = CURSORS_NOT_LIMITING_NOTE
const lines = computed(() => formatAnalysisContextLines(props.context, {
  compact: props.compact,
}))
const staleAction = computed(() => staleResultBanner(true)?.action || 'Recalculate with current context')
const ariaLabel = computed(() => {
  const base = lines.value.join('. ')
  return props.stale ? `${base}. Results may be outdated.` : base
})
const showStrip = computed(() =>
  lines.value.length > 0 || props.stale || (props.showClearFilters && props.onClearFilters))
</script>

<style scoped>
.analysis-context-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  padding: 4px 8px;
  font-size: 11px;
  line-height: 1.35;
  border-bottom: 1px solid var(--border, #3a4658);
  background: transparent;
}
.ctx-chip {
  padding: 2px 6px;
  border-radius: 4px;
  background: color-mix(in srgb, var(--fg) 8%, transparent);
  color: var(--fg-dim);
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ctx-chip.ctx-note {
  color: #c9a227;
  background: rgba(201, 162, 39, 0.12);
}
.ctx-recalc,
.ctx-clear {
  margin-left: auto;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 4px;
  border: 1px solid var(--accent, #2a6fb2);
  background: transparent;
  color: var(--accent, #5b9bd5);
  cursor: pointer;
}
.ctx-clear {
  margin-left: 0;
}
</style>
