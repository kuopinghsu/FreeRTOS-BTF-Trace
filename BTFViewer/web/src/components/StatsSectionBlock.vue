<template>
  <div
    class="stats-section-block"
    :class="{ 'drag-over': dragOver, dragging: dragging }"
    :style="{ order }"
    :data-section-id="sectionId"
    @dragover.prevent="onDragOver"
    @dragenter.prevent="onDragEnter"
    @dragleave="onDragLeave"
    @drop.prevent="onDrop"
  >
    <div class="stats-sep" />
    <slot />
  </div>
</template>

<script setup>
import { ref } from 'vue'

const MIME = 'application/x-btf-stats-section'

const props = defineProps({
  sectionId: { type: String, required: true },
  order: { type: Number, default: 0 },
})

const emit = defineEmits(['reorder'])

const dragOver = ref(false)
const dragging = ref(false)
let dragDepth = 0

function onDragEnter(e) {
  const types = e.dataTransfer?.types ? Array.from(e.dataTransfer.types) : []
  if (!types.includes(MIME) && !types.includes('text/plain')) {
    return
  }
  dragDepth += 1
  dragOver.value = true
}

function onDragOver(e) {
  if (e.dataTransfer) {
    e.dataTransfer.dropEffect = 'move'
  }
  dragOver.value = true
}

function onDragLeave() {
  dragDepth = Math.max(0, dragDepth - 1)
  if (dragDepth === 0) dragOver.value = false
}

function onDrop(e) {
  dragDepth = 0
  dragOver.value = false
  const src = (
    e.dataTransfer?.getData(MIME)
    || e.dataTransfer?.getData('text/plain')
    || ''
  ).trim()
  if (src && src !== props.sectionId) {
    emit('reorder', src, props.sectionId)
  }
}

/** Called by StatsSectionHeader drag handle via provide/parent. */
function setDragging(v) {
  dragging.value = !!v
}

defineExpose({ setDragging, sectionId: props.sectionId })
</script>

<style scoped>
.stats-section-block {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.stats-section-block.drag-over {
  outline: 1px dashed var(--accent, #7ec8e3);
  outline-offset: 2px;
  border-radius: 4px;
}

.stats-section-block.dragging {
  opacity: 0.55;
}

.stats-sep {
  height: 1px;
  background: var(--border, #333);
  margin: 8px 0 6px;
  flex-shrink: 0;
}
</style>
