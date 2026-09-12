<template>
  <!-- All labels and values are escaped by the shared report renderer. -->
  <!-- eslint-disable vue/no-v-html -->
  <div
    class="shared-compare-chart"
    v-html="markup"
  />
</template>
<script setup>
import { computed } from 'vue'
import { comparePairedBarsHtml } from '../utils/uxExplore.js'
const props = defineProps({ rows: { type: Array, default: () => [] }, options: { type: Object, required: true } })
const markup = computed(() => comparePairedBarsHtml(props.rows, props.options))
</script>
<style scoped>
.shared-compare-chart { font-size:12px; line-height:1.45; margin:10px 0; }
:deep(.compare-visual-head) { display:flex; justify-content:space-between; gap:12px; margin-bottom:8px; }
:deep(.compare-visual-title) { font-size:14px; font-weight:600; }
:deep(.compare-visual-sub) { color:var(--fg-dim); font-size:11px; }
:deep(.compare-legend) { display:flex; gap:10px; font-size:10px; }
:deep(.legend-swatch) { display:inline-block; width:12px; height:10px; border-radius:5px; margin-right:4px; }
:deep(.legend-swatch.a), :deep(.paired-fill.a) { background:var(--compare-a); }
:deep(.legend-swatch.b), :deep(.paired-fill.b) { background:var(--compare-b); }
:deep(.paired-bars) { display:grid; gap:7px; }
:deep(.paired-row) { display:grid; grid-template-columns:140px minmax(0, 1fr); gap:10px; align-items:center; }
:deep(.paired-label) { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
:deep(.paired-pair) { display:grid; gap:5px; }
:deep(.paired-line) { display:grid; grid-template-columns:16px minmax(0, 1fr) 90px; gap:6px; align-items:center; }
:deep(.paired-tag) { font-size:10px; }
:deep(.paired-track) { display:block; height:10px; border-radius:5px; background:color-mix(in srgb, var(--fg) 8%, transparent); overflow:hidden; }
:deep(.paired-fill) { display:block; height:10px; border-radius:5px; width:var(--w); }
:deep(.paired-value) { text-align:right; font-variant-numeric:tabular-nums; }
</style>
