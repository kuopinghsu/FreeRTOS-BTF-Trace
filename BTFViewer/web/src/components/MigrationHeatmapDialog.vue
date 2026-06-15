<template>
  <div
    class="heatmap-overlay"
    @click.self="emit('close')"
  >
    <div
      class="heatmap-dialog"
      role="dialog"
      aria-modal="true"
      aria-label="Migration heatmap"
    >
      <div class="heatmap-header">
        <span class="heatmap-title">Migration Heatmap</span>
        <button
          type="button"
          class="heatmap-close"
          @click="emit('close')"
        >
          Close
        </button>
      </div>
      <p class="heatmap-sub">
        Core-pair migrations over time bins{{ scopeSuffix }}
      </p>
      <div
        v-if="!hasData"
        class="heatmap-empty"
      >
        No migrations in scope.
      </div>
      <div
        v-else
        class="heatmap-scroll"
      >
        <div class="heatmap-body">
          <div
            v-for="(row, ri) in heatmap.grid"
            :key="ri"
            class="hm-row"
          >
            <span class="hm-label">{{ heatmap.pairs[ri].label }}</span>
            <div class="hm-cells">
              <div
                v-for="(v, bi) in row"
                :key="bi"
                class="hm-cell"
                :style="{ background: cellColor(v) }"
                :title="`${heatmap.pairs[ri].label} bin ${bi}: ${v}`"
              />
            </div>
          </div>
        </div>
      </div>
      <p class="heatmap-hint">
        Rows: from→to core pairs · Columns: time bins
      </p>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { formatTime } from '../renderer/TimelineRenderer.js'
import { migrationHeatmapGrid } from '../utils/migrationAnalysis.js'
import { getStatsRange } from '../utils/statsRange.js'

const props = defineProps({
  trace:   { type: Object, required: true },
  cursors: { type: Array, default: () => [] },
})

const emit = defineEmits(['close'])

const statsRange = computed(() => getStatsRange(props.cursors, props.trace))

const scopeSuffix = computed(() => {
  const r = statsRange.value
  if (!r) return ''
  const n = props.cursors.filter(c => c != null).length
  return ` (C1–C${n}: ${formatTime(r.lo, props.trace.timeScale)} … ${formatTime(r.hi, props.trace.timeScale)})`
})

const heatmap = computed(() => {
  const r = statsRange.value
  const lo = r?.lo ?? null
  const hi = r?.hi ?? null
  return migrationHeatmapGrid(props.trace, lo, hi)
})

const heatMax = computed(() => {
  let m = 0
  for (const row of heatmap.value.grid) {
    for (const v of row) if (v > m) m = v
  }
  return m
})

const hasData = computed(() =>
  heatmap.value.pairs.length > 0
  && heatmap.value.grid.some(row => row.some(v => v > 0)))

function cellColor(v) {
  if (!v) return 'rgba(91, 155, 213, 0.06)'
  const alpha = heatMax.value ? 0.2 + 0.7 * (v / heatMax.value) : 0.3
  return `rgba(91, 155, 213, ${alpha})`
}
</script>

<style scoped>
.heatmap-overlay {
  position: fixed;
  inset: 0;
  z-index: 2000;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}
.heatmap-dialog {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  min-width: 420px;
  max-width: min(92vw, 720px);
  max-height: 85vh;
  display: flex;
  flex-direction: column;
  padding: 12px 14px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.35);
}
.heatmap-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.heatmap-title {
  font-weight: 600;
  font-size: 14px;
}
.heatmap-close {
  border: 1px solid var(--border);
  background: var(--tb-bg);
  color: var(--fg);
  border-radius: 4px;
  padding: 4px 10px;
  cursor: pointer;
  font-size: 12px;
}
.heatmap-sub {
  margin: 8px 0 6px;
  font-size: 12px;
  color: var(--fg-dim);
}
.heatmap-empty {
  padding: 24px 0;
  text-align: center;
  color: var(--fg-dim);
  font-size: 13px;
}
.heatmap-scroll {
  overflow: auto;
  flex: 1;
  min-height: 0;
  max-height: 60vh;
}
.heatmap-body {
  min-width: max-content;
  padding: 4px 0;
}
.hm-row {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 16px;
  margin-bottom: 2px;
}
.hm-label {
  flex: 0 0 auto;
  min-width: 3.5em;
  font-size: 11px;
  color: var(--fg-dim);
  text-align: left;
  white-space: nowrap;
  padding-left: 2px;
}
.hm-cells {
  display: flex;
  flex: 1;
  gap: 1px;
  min-width: 0;
}
.hm-cell {
  flex: 1 1 8px;
  min-width: 6px;
  height: 13px;
  border-radius: 1px;
}
.heatmap-hint {
  margin: 8px 0 0;
  font-size: 11px;
  color: var(--fg-dim);
}
</style>
