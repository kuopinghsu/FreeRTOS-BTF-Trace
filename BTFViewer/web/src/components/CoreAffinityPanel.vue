<template>
  <div class="core-affinity">
    <div class="affinity-header">
      <span class="affinity-title">Core affinity</span>
      <span class="affinity-task">{{ taskLabel }}</span>
    </div>
    <canvas
      ref="canvasEl"
      class="affinity-canvas"
      :style="{ height: canvasH + 'px' }"
      @click="onCanvasClick"
    />
    <div
      v-if="!cores.length"
      class="affinity-empty"
    >
      No segments in view
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { coreAffinityData } from '../utils/coreAffinity.js'
import { taskLabelForMergeKey } from '../utils/colors.js'

const props = defineProps({
  trace: { type: Object, required: true },
  mergeKey: { type: String, required: true },
  viewport: { type: Object, required: true },
  darkMode: { type: Boolean, default: true },
})

const emit = defineEmits(['jump'])

const canvasEl = ref(null)
const ROW_H = 14
const PAD = 4

const tLo = computed(() => props.viewport?.timeStart ?? props.trace.timeMin)
const tHi = computed(() => props.viewport?.timeEnd ?? props.trace.timeMax)

const affinity = computed(() => coreAffinityData(props.trace, props.mergeKey, tLo.value, tHi.value))
const cores = computed(() => affinity.value.cores)
const taskLabel = computed(() => taskLabelForMergeKey(props.trace, props.mergeKey))

const canvasH = computed(() => Math.max(ROW_H + PAD * 2, cores.value.length * (ROW_H + 2) + PAD * 2))

function paint() {
  const canvas = canvasEl.value
  if (!canvas) return
  const dpr = window.devicePixelRatio || 1
  const w = canvas.clientWidth
  const h = canvasH.value
  canvas.width = Math.round(w * dpr)
  canvas.height = Math.round(h * dpr)
  const ctx = canvas.getContext('2d')
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.fillStyle = props.darkMode ? '#1a1a1a' : '#f5f5f5'
  ctx.fillRect(0, 0, w, h)

  const { tLo: lo, span } = affinity.value
  const labelW = 36
  const bodyW = Math.max(1, w - labelW - PAD)

  cores.value.forEach((row, ri) => {
    const y = PAD + ri * (ROW_H + 2)
    ctx.fillStyle = props.darkMode ? '#888' : '#666'
    ctx.font = '10px monospace'
    ctx.textBaseline = 'middle'
    ctx.fillText(row.label, 2, y + ROW_H / 2)
    for (const seg of row.segments) {
      const x0 = labelW + ((seg.start - lo) / span) * bodyW
      const x1 = labelW + ((seg.end - lo) / span) * bodyW
      ctx.fillStyle = row.color
      ctx.globalAlpha = 0.85
      ctx.fillRect(x0, y + 1, Math.max(2, x1 - x0), ROW_H - 2)
      ctx.globalAlpha = 1
    }
  })
}

function onCanvasClick(e) {
  const canvas = canvasEl.value
  if (!canvas || !cores.value.length) return
  const rect = canvas.getBoundingClientRect()
  const x = e.clientX - rect.left
  const labelW = 36
  const bodyW = Math.max(1, rect.width - labelW - PAD)
  const frac = (x - labelW) / bodyW
  if (frac < 0 || frac > 1) return
  const ns = affinity.value.tLo + frac * affinity.value.span
  emit('jump', ns)
}

let _ro = null
onMounted(() => {
  nextTick(() => paint())
  if (canvasEl.value?.parentElement) {
    _ro = new ResizeObserver(() => paint())
    _ro.observe(canvasEl.value.parentElement)
  }
})
onBeforeUnmount(() => { _ro?.disconnect() })

watch([cores, () => props.viewport, () => props.darkMode], () => nextTick(() => paint()), { deep: true })
</script>

<style scoped>
.core-affinity {
  padding: 8px 12px;
  border-top: 1px solid var(--border);
}
.affinity-header {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 6px;
  font-size: 11px;
}
.affinity-title {
  font-weight: 600;
  color: var(--fg-dim);
}
.affinity-task {
  font-family: monospace;
  color: var(--fg);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.affinity-canvas {
  width: 100%;
  display: block;
  border-radius: 4px;
  cursor: crosshair;
}
.affinity-empty {
  font-size: 11px;
  color: var(--fg-dim);
  padding: 4px 0;
}
</style>
