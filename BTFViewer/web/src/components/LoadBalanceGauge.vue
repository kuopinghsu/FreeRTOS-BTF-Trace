<template>
  <div
    class="lb-gauge"
    :class="{
      'lb-gauge-amber': zone === 'amber',
      'lb-gauge-red': zone === 'red',
    }"
    :title="tooltip"
  >
    <div class="lb-top">
      <span class="lb-heading">Load Balance Score</span>
      <span
        v-if="zone === 'red'"
        class="lb-chip lb-chip-red"
        title="Load Balance Score below 70% — cores are unbalanced (red zone)"
      >Unbalanced</span>
      <span
        v-else-if="zone === 'amber'"
        class="lb-chip lb-chip-amber"
        title="Population stddev of core utilisation exceeds 30%"
      >σ &gt; 30%</span>
    </div>

    <svg
      class="lb-svg"
      viewBox="20 20 240 110"
      role="img"
      :aria-label="`Load Balance Score ${scoreLabel}${zone === 'red' ? ', unbalanced' : ''}`"
    >
      <defs>
        <linearGradient :id="gradId" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" :stop-color="zone === 'red' ? '#EF5350' : '#3B82F6'" />
          <stop offset="55%" :stop-color="zone === 'red' ? '#E53935' : '#14B8A6'" />
          <stop offset="100%" :stop-color="fillEnd" />
        </linearGradient>
      </defs>

      <path
        class="lb-track"
        :d="bgPath"
        fill="none"
        stroke-width="12"
        stroke-linecap="round"
      />
      <path
        class="lb-fill"
        :d="fillPath"
        fill="none"
        :stroke="`url(#${gradId})`"
        stroke-width="12"
        stroke-linecap="round"
      />
      <line
        class="lb-needle"
        :x1="G.cx"
        :y1="G.cy"
        :x2="tip.x"
        :y2="tip.y"
        stroke-width="2.25"
        stroke-linecap="round"
      />
      <circle class="lb-hub" :cx="G.cx" :cy="G.cy" r="5" stroke-width="2" />

      <text class="lb-score" :x="G.cx" :y="G.scoreY" text-anchor="middle">
        {{ scoreLabel }}
      </text>
    </svg>

    <div v-if="zone === 'red'" class="lb-alert">
      Red zone: score &lt; 70% — load is unbalanced across cores
    </div>

    <div class="lb-meta">
      <div class="lb-formula">100 × (1 − Gini coefficient)</div>
      <div class="lb-stats">
        σ={{ stddevLabel }}% · G={{ giniLabel }}
      </div>
      <div class="lb-legend">
        100 = perfect balance · 0 = single-core overload
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import {
  LB_GAUGE,
  LB_ZONE_COLORS,
  classifyLoadBalance,
  needleTipPoint,
  scoreArcPath,
  semicirclePath,
} from '../utils/loadBalanceGauge.js'

const props = defineProps({
  score: { type: Number, required: true },
  gini: { type: Number, required: true },
  stddev: { type: Number, required: true },
  /** @deprecated prefer zone from classifyLoadBalance */
  amber: { type: Boolean, default: false },
  zone: { type: String, default: '' },
})

const G = LB_GAUGE
const uid = Math.random().toString(36).slice(2, 8)
const gradId = `lbGrad-${uid}`

const zone = computed(() => {
  if (props.zone === 'ok' || props.zone === 'amber' || props.zone === 'red') return props.zone
  return classifyLoadBalance(props.score, props.stddev)
})
const fillEnd = computed(() => (LB_ZONE_COLORS[zone.value] || LB_ZONE_COLORS.ok).fillEnd)

const bgPath = semicirclePath(G.cx, G.cy, G.rBg)
const fillPath = computed(() => scoreArcPath(props.score))
const tip = computed(() => needleTipPoint(props.score))
const scoreLabel = computed(() => `${Math.max(0, Math.min(100, props.score)).toFixed(0)}%`)
const stddevLabel = computed(() => props.stddev.toFixed(1))
const giniLabel = computed(() => props.gini.toFixed(3))
const tooltip = computed(() => (
  `Load Balance Score = 100% × (1 − Gini). `
  + `Red zone (Unbalanced) when score < 70%. Amber when σ > 30%. `
  + `Current: ${scoreLabel.value}, σ=${stddevLabel.value}%, G=${giniLabel.value}.`
))
</script>

<style scoped>
.lb-gauge {
  margin: 2px 0 10px;
  padding: 8px 10px 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: color-mix(in srgb, var(--panel-bg) 92%, var(--bg));
}

.lb-gauge-red {
  border-color: color-mix(in srgb, #e57373 70%, var(--border));
  background: color-mix(in srgb, #c62828 6%, var(--panel-bg));
}

.lb-gauge-amber {
  border-color: color-mix(in srgb, #e0a020 55%, var(--border));
}

.lb-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 2px;
}

.lb-heading {
  font-size: 11px;
  font-weight: 600;
  color: var(--fg);
  letter-spacing: 0.01em;
}

.lb-chip {
  flex-shrink: 0;
  font-size: 10px;
  font-weight: 700;
  border-radius: 999px;
  padding: 1px 7px;
  line-height: 1.4;
}

.lb-chip-amber {
  color: #b07800;
  background: color-mix(in srgb, #e0a020 18%, var(--panel-bg));
  border: 1px solid color-mix(in srgb, #e0a020 55%, var(--border));
}

.lb-chip-red {
  color: #c62828;
  background: color-mix(in srgb, #c62828 14%, var(--panel-bg));
  border: 1px solid color-mix(in srgb, #e57373 70%, var(--border));
}

.lb-svg {
  display: block;
  width: 100%;
  max-width: 260px;
  height: auto;
  margin: 0 auto;
}

.lb-track {
  stroke: var(--border);
}

.lb-needle {
  stroke: var(--fg);
}

.lb-hub {
  fill: var(--panel-bg);
  stroke: var(--fg);
}

.lb-score {
  fill: #1a8a2a;
  font-family: system-ui, sans-serif;
  font-size: 28px;
  font-weight: 700;
}

.lb-gauge-amber .lb-score {
  fill: #b07800;
}

.lb-gauge-red .lb-score {
  fill: #c62828;
}

.lb-alert {
  margin: 2px 0 6px;
  padding: 4px 8px;
  border-radius: 6px;
  font-size: 10px;
  font-weight: 600;
  line-height: 1.35;
  text-align: center;
  color: #c62828;
  background: color-mix(in srgb, #c62828 12%, var(--panel-bg));
  border: 1px solid color-mix(in srgb, #e57373 55%, var(--border));
}

.lb-meta {
  text-align: center;
  margin-top: 2px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.lb-formula,
.lb-stats,
.lb-legend {
  color: var(--fg-dim);
  font-size: 10px;
  line-height: 1.35;
}

.lb-formula,
.lb-stats {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}
</style>
