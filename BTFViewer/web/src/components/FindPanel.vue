<template>
  <div class="find-panel">
    <div
      class="find-status"
      :class="{ error: !!error }"
    >
      {{ statusText }}
    </div>
    <input
      ref="inputRef"
      v-model="localQuery"
      class="find-input"
      type="search"
      placeholder="Find task, annotation, or migration…"
      title="Search the active tab. Enter = next match; Shift+Enter / F3 / Shift+F3 step hits on the timeline."
      @input="onQueryChange"
      @keydown.enter.prevent="emit('next')"
      @keydown.shift.enter.prevent="emit('prev')"
    >
    <DomSelect
      v-model="localMode"
      class="find-mode"
      :title="modeHelp"
      :options="findModeOptions"
      @change="onModeChange"
    />
    <div class="find-btns">
      <button
        type="button"
        class="find-btn"
        title="Find previous (Shift+F3)"
        @click="emit('prev')"
      >
        Previous
      </button>
      <button
        type="button"
        class="find-btn"
        title="Find next (F3)"
        @click="emit('next')"
      >
        Next
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import DomSelect from './DomSelect.vue'
import { FIND_MODE_CHOICES, findModeHelp, formatFindStatus } from '../utils/findAnalysis.js'

const props = defineProps({
  query: { type: String, default: '' },
  mode: { type: String, default: 'contains' },
  hitCount: { type: Number, default: 0 },
  hitIndex: { type: Number, default: -1 },
  error: { type: String, default: '' },
})

const emit = defineEmits(['update:query', 'update:mode', 'recompute', 'next', 'prev'])

const inputRef = ref(null)
const localQuery = ref(props.query)
const localMode = ref(props.mode)

watch(() => props.query, v => { localQuery.value = v })
watch(() => props.mode, v => { localMode.value = v })

const modeHelp = computed(() => findModeHelp(localMode.value))

const findModeOptions = computed(() =>
  FIND_MODE_CHOICES.map(opt => ({ value: opt.key, label: opt.label, title: opt.help })))

const statusText = computed(() => formatFindStatus({
  hitCount: props.hitCount,
  hitIndex: props.hitIndex,
  mode: localMode.value,
  query: localQuery.value,
  error: props.error,
}))

function onQueryChange() {
  emit('update:query', localQuery.value)
  emit('recompute')
}

function onModeChange() {
  emit('update:mode', localMode.value)
  emit('recompute')
}

function focusInput() {
  inputRef.value?.focus()
  inputRef.value?.select()
}

defineExpose({ focusInput })
</script>

<style scoped>
.find-panel {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px;
  flex: 1;
  min-height: 0;
}
.find-status {
  font-size: 11px;
  color: var(--fg-dim);
  align-self: flex-start;
  line-height: 1.35;
}
.find-status.error {
  color: #e07070;
}
.find-input {
  width: 100%;
  padding: 5px 8px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--bg);
  color: var(--fg);
  font-size: 12px;
}
.find-mode {
  width: 100%;
  padding: 4px 6px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--bg);
  color: var(--fg);
  font-size: 12px;
}
.find-btns {
  display: flex;
  gap: 6px;
}
.find-btn {
  flex: 1;
  padding: 4px 8px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--panel-bg);
  color: var(--fg);
  font-size: 12px;
  cursor: pointer;
}
.find-btn:hover {
  background: var(--tb-btn-hover);
}
</style>
