<template>
  <div class="cursor-panel" v-if="validCursors.length > 0">
    <div class="cursor-row" v-for="(cur, idx) in cursors" :key="idx">
      <template v-if="cur !== null">
        <span class="cursor-badge" :style="{ background: CURSOR_COLORS[idx] }">C{{ idx + 1 }}</span>
        <span class="cursor-time clickable" title="Jump to cursor" @click="emit('jumpToCursor', cur)">{{ formatTime(cur, timeScale) }}</span>
        <button class="cursor-del" title="Remove cursor" @click="emit('deleteCursor', idx)">×</button>
      </template>
      <span v-else class="cursor-empty">–</span>
    </div>

    <!-- Deltas between adjacent placed cursors -->
    <template v-if="deltas.length > 0">
      <div class="delta-sep" />
      <div class="delta-row" v-for="(d, idx) in deltas" :key="'d' + idx">
        <span class="delta-label">Δ{{ d.from + 1 }}→{{ d.to + 1 }}</span>
        <span class="delta-value">{{ formatTime(d.delta, timeScale) }}</span>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { formatTime } from '../renderer/TimelineRenderer.js'

const CURSOR_COLORS = ['#FF4444', '#44FF88', '#4499FF', '#FFAA22']

const props = defineProps({
  cursors:   { type: Array, required: true },
  timeScale: { type: String, default: 'ns' },
})

const emit = defineEmits(['deleteCursor', 'jumpToCursor'])

const validCursors = computed(() => props.cursors.filter(c => c !== null))

const deltas = computed(() => {
  const placed = []
  props.cursors.forEach((c, i) => { if (c !== null) placed.push({ t: c, idx: i }) })
  const result = []
  for (let i = 1; i < placed.length; i++) {
    result.push({
      from:  placed[i - 1].idx,
      to:    placed[i].idx,
      delta: Math.abs(placed[i].t - placed[i - 1].t),
    })
  }
  return result
})
</script>

<style scoped>
.cursor-panel {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 12px;
  font-size: 11px;
  font-family: monospace;
  min-width: 200px;
}

.cursor-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.cursor-time.clickable {
  cursor: pointer;
  text-decoration: underline dotted;
  opacity: 0.85;
}
.cursor-time.clickable:hover {
  opacity: 1;
  color: var(--accent, #4a9eff);
}

.cursor-del {
  margin-left: auto;
  background: transparent;
  border: none;
  cursor: pointer;
  color: var(--fg-dim);
  font-size: 14px;
  line-height: 1;
  padding: 0 3px;
  border-radius: 3px;
  opacity: 0.6;
}
.cursor-del:hover {
  color: #FF5555;
  opacity: 1;
  background: var(--tb-btn-hover);
}

.cursor-badge {
  color: #000;
  padding: 1px 6px;
  border-radius: 3px;
  font-weight: bold;
  font-size: 10px;
  min-width: 24px;
  text-align: center;
}

.cursor-time {
  color: var(--fg);
}

.cursor-empty {
  color: var(--fg-dim);
  opacity: 0.4;
}

.delta-sep {
  height: 1px;
  background: var(--border);
  margin: 4px 0;
}

.delta-row {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--fg-dim);
}

.delta-label {
  opacity: 0.7;
  min-width: 48px;
}

.delta-value {
  color: var(--fg);
  font-weight: 500;
}
</style>
