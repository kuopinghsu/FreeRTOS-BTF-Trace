<template>
  <div
    class="lb-cluster"
    :class="{
      'lb-cluster-amber': zone === 'amber',
      'lb-cluster-red': zone === 'red',
    }"
    :title="tooltip"
  >
    <div class="lb-row">
      <!-- Score gauge -->
      <div class="lb-gauge">
        <div class="lb-top">
          <span class="lb-heading">Load Balance Score</span>
          <span
            v-if="scoreZone === 'red'"
            class="lb-chip lb-chip-red"
            title="Score below 70% — unbalanced"
          >Unbalanced</span>
        </div>
        <svg
          class="lb-svg"
          :viewBox="`0 0 ${G.viewW} ${G.viewH}`"
          role="img"
          :aria-label="`Load Balance Score ${scoreLabel}`"
        >
          <defs>
            <linearGradient :id="scoreGradId" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" :stop-color="scoreZone === 'red' ? '#EF5350' : '#3B82F6'" />
              <stop offset="55%" :stop-color="scoreZone === 'red' ? '#E53935' : '#14B8A6'" />
              <stop offset="100%" :stop-color="scoreFillEnd" />
            </linearGradient>
          </defs>
          <path
            class="lb-track"
            :d="scoreBg"
            fill="none"
            :stroke-width="G.strokeW"
            stroke-linecap="round"
          />
          <path
            class="lb-fill"
            :d="scoreFill"
            fill="none"
            :stroke="`url(#${scoreGradId})`"
            :stroke-width="G.strokeW"
            stroke-linecap="round"
          />
          <line
            class="lb-needle"
            :x1="G.cx"
            :y1="G.cy"
            :x2="scoreTip.x"
            :y2="scoreTip.y"
            stroke-width="2"
            stroke-linecap="round"
          />
          <circle
            class="lb-hub"
            :cx="G.cx"
            :cy="G.cy"
            :r="G.hubR"
            stroke-width="1.75"
          />
          <text
            class="lb-score"
            :class="{ red: scoreZone === 'red' }"
            :x="G.cx"
            :y="G.scoreY"
            text-anchor="middle"
            dominant-baseline="middle"
          >{{ scoreLabel }}</text>
        </svg>
        <div class="lb-caption">100 = evenly distributed · 0 = highly uneven</div>
      </div>

      <!-- σ gauge -->
      <div class="lb-gauge">
        <div class="lb-top">
          <span class="lb-heading">Std Deviation (σ)</span>
          <span
            v-if="sigmaZone === 'amber'"
            class="lb-chip lb-chip-amber"
            title="Population stddev of core utilisation exceeds 30%"
          >σ &gt; 30%</span>
          <span
            v-else-if="sigmaZone === 'red'"
            class="lb-chip lb-chip-red"
            title="Population stddev of core utilisation exceeds 50%"
          >σ &gt; 50%</span>
        </div>
        <svg
          class="lb-svg"
          :viewBox="`0 0 ${G.viewW} ${G.viewH}`"
          role="img"
          :aria-label="`Core utilisation sigma ${stddevLabel} percent`"
        >
          <defs>
            <linearGradient :id="sigmaGradId" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" :stop-color="sigmaZone === 'red' ? '#EF5350' : '#3B82F6'" />
              <stop offset="55%" :stop-color="sigmaZone === 'red' ? '#E53935' : '#14B8A6'" />
              <stop offset="100%" :stop-color="sigmaFillEnd" />
            </linearGradient>
          </defs>
          <path
            class="lb-track"
            :d="sigmaBg"
            fill="none"
            :stroke-width="G.strokeW"
            stroke-linecap="round"
          />
          <path
            class="lb-fill"
            :d="sigmaFill"
            fill="none"
            :stroke="`url(#${sigmaGradId})`"
            :stroke-width="G.strokeW"
            stroke-linecap="round"
          />
          <line
            class="lb-needle"
            :x1="G.cx"
            :y1="G.cy"
            :x2="sigmaTip.x"
            :y2="sigmaTip.y"
            stroke-width="2"
            stroke-linecap="round"
          />
          <circle
            class="lb-hub"
            :cx="G.cx"
            :cy="G.cy"
            :r="G.hubR"
            stroke-width="1.75"
          />
          <text
            class="lb-score"
            :class="{ amber: sigmaZone === 'amber', red: sigmaZone === 'red' }"
            :x="G.cx"
            :y="G.scoreY"
            text-anchor="middle"
            dominant-baseline="middle"
          >{{ stddevLabel }}%</text>
        </svg>
        <div class="lb-caption">0–{{ sigmaScale }}% · warn &gt; 30%</div>
      </div>
    </div>

    <div v-if="zone === 'red'" class="lb-alert">
      Red zone: score &lt; 70% — load is unbalanced
    </div>

    <div class="lb-meta">
      G={{ giniLabel }} · Score = 100 × (1 − Gini)
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import {
  LB_GAUGE,
  LB_SCORE_WARN,
  LB_SIGMA_SCALE,
  LB_ZONE_COLORS,
  classifyLoadBalance,
  classifySigma,
  needleTipPoint,
  semicirclePath,
  valueArcPath,
} from '../utils/loadBalanceGauge.js'

const props = defineProps({
  score: { type: Number, required: true },
  gini: { type: Number, required: true },
  stddev: { type: Number, required: true },
  amber: { type: Boolean, default: false },
  zone: { type: String, default: '' },
})

const G = LB_GAUGE
const sigmaScale = LB_SIGMA_SCALE
const uid = Math.random().toString(36).slice(2, 8)
const scoreGradId = `lbS-${uid}`
const sigmaGradId = `lbD-${uid}`

const zone = computed(() => {
  if (props.zone === 'ok' || props.zone === 'amber' || props.zone === 'red') return props.zone
  return classifyLoadBalance(props.score, props.stddev)
})
const scoreZone = computed(() => (props.score < LB_SCORE_WARN ? 'red' : 'ok'))
const sigmaZone = computed(() => classifySigma(props.stddev))
const scoreFillEnd = computed(() => (LB_ZONE_COLORS[scoreZone.value] || LB_ZONE_COLORS.ok).fillEnd)
const sigmaFillEnd = computed(() => (LB_ZONE_COLORS[sigmaZone.value] || LB_ZONE_COLORS.ok).fillEnd)

const scoreBg = semicirclePath(G.cx, G.cy, G.rBg)
const sigmaBg = scoreBg
const scoreFill = computed(() => valueArcPath(props.score, 100))
const sigmaFill = computed(() => valueArcPath(Math.min(props.stddev, LB_SIGMA_SCALE), LB_SIGMA_SCALE))
const scoreTip = computed(() => needleTipPoint(props.score, 100))
const sigmaTip = computed(() => needleTipPoint(Math.min(props.stddev, LB_SIGMA_SCALE), LB_SIGMA_SCALE))

const scoreLabel = computed(() => `${Math.max(0, Math.min(100, props.score)).toFixed(0)}%`)
const stddevLabel = computed(() => props.stddev.toFixed(1))
const giniLabel = computed(() => props.gini.toFixed(3))
const tooltip = computed(() => (
  `Load Balance Score = 100% × (1 − Gini); σ = population stddev of core util %. `
  + `Score red when < 70%. σ amber when > 30%. `
  + `Current: ${scoreLabel.value}, σ=${stddevLabel.value}%, G=${giniLabel.value}.`
))
</script>

<style scoped>
/* Match desktop _LoadBalanceGaugeWidget: one card, two columns, thin arcs. */
.lb-cluster {
  margin: 2px 0 10px;
  padding: 6px 8px 6px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel-bg);
}

.lb-cluster-red {
  border-color: #e57373;
  background: color-mix(in srgb, #c62828 6%, var(--panel-bg));
}

.lb-cluster-amber {
  border-color: #e0a020;
}

.lb-row {
  display: flex;
  gap: 8px;
  align-items: stretch;
}

.lb-gauge {
  flex: 1 1 0;
  min-width: 0;
}

.lb-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 4px;
  min-height: 16px;
  margin-bottom: 2px;
  padding: 0 2px;
}

.lb-heading {
  font-size: 10px;
  font-weight: 600;
  color: var(--fg);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.lb-chip {
  flex-shrink: 0;
  font-size: 9px;
  font-weight: 700;
  border-radius: 8px;
  padding: 1px 6px;
  line-height: 1.35;
}

.lb-chip-amber {
  color: #c47f00;
  background: #fff6e5;
  border: 1px solid #e0a020;
}

.lb-chip-red {
  color: #c62828;
  background: #fdecea;
  border: 1px solid #e57373;
}

.lb-svg {
  display: block;
  width: 100%;
  max-width: 180px;
  height: auto;
  margin: 0 auto;
}

.lb-track {
  stroke: color-mix(in srgb, var(--border) 85%, var(--fg));
  opacity: 0.85;
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
  font-family: system-ui, -apple-system, sans-serif;
  font-size: 12px;
  font-weight: 700;
}

.lb-score.amber {
  fill: #c47f00;
}

.lb-score.red {
  fill: #c62828;
}

.lb-caption {
  text-align: center;
  color: var(--fg-dim);
  font-size: 9px;
  line-height: 1.3;
  margin-top: 0;
  padding: 0 2px;
}

.lb-alert {
  margin: 6px 0 2px;
  padding: 2px 8px;
  border-radius: 5px;
  font-size: 9px;
  font-weight: 700;
  line-height: 1.35;
  text-align: center;
  color: #c62828;
  background: #fdecea;
  border: 1px solid #e57373;
}

.lb-meta {
  text-align: center;
  margin-top: 4px;
  color: var(--fg-dim);
  font-size: 10px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}
</style>
