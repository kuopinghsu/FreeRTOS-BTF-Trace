<template>
  <div
    v-if="stiEvent"
    class="sti-tooltip"
    :style="{ left: x + 'px', top: y + 'px' }"
  >
    <div class="sti-row"><span class="sti-key">Time</span><span class="sti-val">{{ formatTime(stiEvent.time, timeScale) }}</span></div>
    <div class="sti-row"><span class="sti-key">Channel</span><span class="sti-val">{{ stiEvent.target }}</span></div>
    <div class="sti-row" v-if="stiEvent.event"><span class="sti-key">Event</span><span class="sti-val">{{ stiEvent.event }}</span></div>
    <div class="sti-row" v-if="stiEvent.note"><span class="sti-key">Note</span><span class="sti-val">{{ stiEvent.note }}</span></div>
    <div class="sti-row"><span class="sti-key">Core</span><span class="sti-val">{{ stiEvent.core }}</span></div>
  </div>
</template>

<script setup>
import { formatTime } from '../renderer/TimelineRenderer.js'

defineProps({
  stiEvent:  { type: Object, default: null },
  x:         { type: Number, default: 0 },
  y:         { type: Number, default: 0 },
  timeScale: { type: String, default: 'ns' },
})
</script>

<style scoped>
.sti-tooltip {
  position: absolute;
  z-index: 100;
  pointer-events: none;
  background: var(--panel-bg);
  border: 1px solid var(--accent);
  border-radius: 5px;
  padding: 6px 10px;
  font-family: monospace;
  font-size: 11px;
  white-space: nowrap;
  box-shadow: 0 4px 16px rgba(0,0,0,0.4);
  transform: translate(10px, -50%);
}

.sti-row {
  display: flex;
  gap: 8px;
  line-height: 1.6;
}

.sti-key {
  color: var(--fg-dim);
  min-width: 56px;
}

.sti-val {
  color: var(--fg);
  font-weight: 500;
}
</style>
