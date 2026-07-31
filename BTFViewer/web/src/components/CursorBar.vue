<template>
  <div
    v-if="model.pills.length"
    class="cursor-bar"
  >
    <div
      v-for="(pill, idx) in model.pills"
      :key="pill.slotIndex"
      class="cursor-pill-wrap"
    >
      <button
        type="button"
        class="cursor-pill-badge"
        :style="pillStyle(pill.slotIndex)"
        :title="pill.tooltip"
        @click="emit('jumpToCursor', pill.ns)"
      >
        {{ pill.label }}
      </button>
      <button
        type="button"
        class="cursor-pill-del"
        :style="pillStyle(pill.slotIndex)"
        title="Delete cursor"
        @click="emit('deleteCursor', pill.slotIndex)"
      >
        ×
      </button>
      <span
        v-if="idx < model.pills.length - 1"
        class="cursor-pill-gap"
      />
    </div>
    <span
      v-if="model.deltas.length"
      class="cursor-deltas"
    >
      <span
        v-for="d in model.deltas"
        :key="d.index"
        class="cursor-delta"
      >{{ d.text }}</span>
    </span>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { CURSOR_COLORS } from '../utils/cursorColors.js'
import { cursorBarModel } from '../utils/cursorAnalysis.js'

const props = defineProps({
  cursors:      { type: Array, required: true },
  timeScale:    { type: String, default: 'ns' },
  darkMode:     { type: Boolean, default: true },
  timeDecimals: { type: Number, default: 3 },
})

const emit = defineEmits(['jumpToCursor', 'deleteCursor'])

const model = computed(() => cursorBarModel(props.cursors, props.timeScale, props.timeDecimals))

function pillStyle(slotIndex) {
  const color = CURSOR_COLORS[slotIndex % CURSOR_COLORS.length]
  return {
    '--pill-color': color,
    '--pill-bg': props.darkMode ? '#2A2A2A' : '#F0F0F0',
    '--pill-hover': props.darkMode ? '#3A3A3A' : '#E0E0E0',
    '--pill-del-hover': props.darkMode ? '#5A1A1A' : '#FAEAEA',
  }
}
</script>

<style scoped>
.cursor-bar {
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
  overflow-x: auto;
  overflow-y: hidden;
  flex-shrink: 1;
}

.cursor-pill-wrap {
  display: inline-flex;
  align-items: stretch;
  flex-shrink: 0;
}

.cursor-pill-badge,
.cursor-pill-del {
  appearance: none;
  border: 1px solid var(--pill-color);
  background: var(--pill-bg);
  color: var(--pill-color);
  font: inherit;
  font-size: 11px;
  line-height: 1.2;
  cursor: pointer;
  padding: 1px 7px;
}

.cursor-pill-badge {
  border-right: none;
  border-radius: 3px 0 0 3px;
  white-space: nowrap;
}

.cursor-pill-badge:hover {
  background: var(--pill-hover);
}

.cursor-pill-del {
  border-radius: 0 3px 3px 0;
  padding: 1px 4px;
  min-width: 18px;
}

.cursor-pill-del:hover {
  background: var(--pill-del-hover);
  color: #FF4444;
  border-color: #FF4444;
}

.cursor-pill-gap {
  display: inline-block;
  width: 4px;
  flex-shrink: 0;
}

.cursor-deltas {
  display: inline-flex;
  align-items: center;
  gap: 12px;
  padding: 0 4px;
  color: var(--fg);
  white-space: nowrap;
  flex-shrink: 0;
}

.cursor-delta {
  font-size: 11px;
}
</style>
