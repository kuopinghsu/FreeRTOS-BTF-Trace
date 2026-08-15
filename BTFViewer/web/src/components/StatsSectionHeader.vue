<template>
  <div class="stats-section-header-wrap">
  <div
    class="stats-section-title collapsible"
    :class="{ pinned }"
    @click="$emit('toggle')"
  >
    <span
      class="stats-drag-handle"
      draggable="true"
      title="Drag to reorder"
      aria-label="Drag to reorder section"
      @click.stop
      @dragstart.stop="onDragStart"
      @dragend.stop="onDragEnd"
    >⠿</span>
    <svg
      class="chevron"
      :class="{ collapsed }"
      viewBox="0 0 10 10"
      width="10"
      height="10"
      aria-hidden="true"
    >
      <polyline
        points="2,3 5,7 8,3"
        fill="none"
        stroke="currentColor"
        stroke-width="1.5"
        stroke-linecap="round"
        stroke-linejoin="round"
      />
    </svg>
    <span class="stats-section-label"><slot /></span>
    <button
      type="button"
      class="stats-pin-btn"
      :class="{ active: pinned }"
      :title="pinned ? 'Unpin — allow this section to collapse' : 'Pin — keep this section expanded'"
      :aria-pressed="pinned ? 'true' : 'false'"
      @click.stop="$emit('togglePin')"
    >
      <!-- outline thumbtack when unpinned -->
      <svg
        v-if="!pinned"
        class="pin-icon"
        viewBox="0 0 16 16"
        width="14"
        height="14"
        aria-hidden="true"
      >
        <path
          fill="currentColor"
          d="M8 1.25A2.75 2.75 0 0 1 10.75 4c0 .95-.48 1.78-1.2 2.27V13.5L8 11.8 6.45 13.5V6.27A2.75 2.75 0 0 1 5.25 4 2.75 2.75 0 0 1 8 1.25zm0 1.5A1.25 1.25 0 0 0 6.75 4c0 .5.28.93.7 1.15l.3.14v6.1l.25-.27.25.27V5.29l.3-.14c.42-.22.7-.65.7-1.15A1.25 1.25 0 0 0 8 2.75z"
        />
      </svg>
      <!-- filled thumbtack when pinned -->
      <svg
        v-else
        class="pin-icon"
        viewBox="0 0 16 16"
        width="14"
        height="14"
        aria-hidden="true"
      >
        <path
          fill="currentColor"
          d="M8 1.25A2.75 2.75 0 0 1 10.75 4c0 .95-.48 1.78-1.2 2.27V13.5L8 11.8 6.45 13.5V6.27A2.75 2.75 0 0 1 5.25 4 2.75 2.75 0 0 1 8 1.25z"
        />
      </svg>
    </button>
  </div>
  <div
    v-if="!collapsed && helpText"
    class="range-hint"
  >{{ helpText }}</div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { STATS_SECTION_HELP } from '../config.js'

const MIME = 'application/x-btf-stats-section'

const props = defineProps({
  collapsed: { type: Boolean, default: false },
  pinned: { type: Boolean, default: false },
  sectionId: { type: String, default: '' },
})

const helpText = computed(() => STATS_SECTION_HELP[props.sectionId] || '')

const emit = defineEmits(['toggle', 'togglePin', 'dragStart', 'dragEnd'])

function onDragStart(e) {
  const sid = String(props.sectionId || '').trim()
  if (!sid || !e.dataTransfer) return
  e.dataTransfer.effectAllowed = 'move'
  e.dataTransfer.setData(MIME, sid)
  e.dataTransfer.setData('text/plain', sid)
  emit('dragStart', sid)
}

function onDragEnd() {
  emit('dragEnd')
}
</script>

<style scoped>
.stats-section-header-wrap {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.range-hint {
  color: var(--fg-dim, #9e9e9e);
  opacity: 0.6;
  font-size: 10px;
  font-style: italic;
  font-weight: 400;
  text-transform: none;
  letter-spacing: 0;
  white-space: normal;
  overflow-wrap: anywhere;
  word-break: break-word;
  min-width: 0;
  margin: 0 0 6px;
  line-height: 1.35;
}

.stats-section-title {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  box-sizing: border-box;
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--fg-dim, #9e9e9e);
  margin-bottom: 4px;
  min-height: 22px;
}

.stats-section-title.collapsible {
  cursor: pointer;
  user-select: none;
}

.stats-section-title.collapsible:hover {
  color: var(--fg, #e0e0e0);
}

.stats-drag-handle {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 14px;
  color: var(--fg-dim, #9e9e9e);
  cursor: grab;
  opacity: 0.7;
  font-size: 12px;
  line-height: 1;
  user-select: none;
}

.stats-drag-handle:hover {
  opacity: 1;
  color: var(--fg, #e0e0e0);
}

.stats-drag-handle:active {
  cursor: grabbing;
}

.stats-section-label {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chevron {
  flex: 0 0 auto;
  transition: transform 0.15s;
  color: inherit;
}

.chevron.collapsed {
  transform: rotate(-90deg);
}

.stats-pin-btn {
  flex: 0 0 22px;
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  padding: 0;
  border: none;
  border-radius: 3px;
  background: transparent;
  color: var(--fg-dim, #9e9e9e);
  cursor: pointer;
  opacity: 0.75;
}

.stats-pin-btn:hover {
  opacity: 1;
  color: var(--fg, #e0e0e0);
  background: rgba(128, 128, 128, 0.28);
}

.stats-pin-btn.active {
  opacity: 1;
  color: var(--accent, #7ec8e3);
  background: transparent;
}

.stats-section-title.pinned .stats-section-label {
  color: var(--fg, #e0e0e0);
}

.pin-icon {
  display: block;
}
</style>
