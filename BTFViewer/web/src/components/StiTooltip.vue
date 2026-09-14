<template>
  <div
    v-if="stiEvent"
    class="sti-tooltip"
    :style="{ left: x + 'px', top: y + 'px' }"
  >
    <div class="sti-row">
      <span class="sti-key">Time</span><span class="sti-val">{{ formatTime(stiEvent.time, timeScale) }}</span>
    </div>
    <div class="sti-row">
      <span class="sti-key">Channel</span><span class="sti-val">{{ stiEvent.target }}</span>
    </div>
    <div
      v-if="stiEvent.event"
      class="sti-row"
    >
      <span class="sti-key">Event</span><span class="sti-val">{{ stiEvent.event }}</span>
    </div>
    <div
      v-if="stiEvent.note"
      class="sti-row"
    >
      <span class="sti-key">Note</span><span class="sti-val">{{ stiEvent.note }}</span>
    </div>
    <div
      v-if="interpretedValue != null"
      class="sti-row"
    >
      <span class="sti-key">Value</span><span class="sti-val">{{ formatTagValue(interpretedValue) }} ({{ representationLabel }})</span>
    </div>
    <div class="sti-row">
      <span class="sti-key">Core</span><span class="sti-val">{{ stiEvent.core }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { formatTime } from '../renderer/TimelineRenderer.js'
import { formatTagValue, interpretTagValue, isTagChannel, tagRepresentationFor, TAG_REPRESENTATION_OPTIONS } from '../utils/tagAnalysis.js'

const props = defineProps({
  stiEvent:  { type: Object, default: null },
  x:         { type: Number, default: 0 },
  y:         { type: Number, default: 0 },
  timeScale: { type: String, default: 'ns' },
  trace: { type: Object, default: null },
  tagRepresentations: { type: Object, default: () => ({}) },
})

const representation = computed(() => tagRepresentationFor(
  props.stiEvent?.target, props.tagRepresentations, props.trace))
const representationLabel = computed(() =>
  TAG_REPRESENTATION_OPTIONS.find(option => option.value === representation.value)?.label || 'uint32')
const interpretedValue = computed(() => {
  if (!props.stiEvent || !isTagChannel(props.stiEvent.target)) return null
  return interpretTagValue(props.stiEvent.note, representation.value)
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
