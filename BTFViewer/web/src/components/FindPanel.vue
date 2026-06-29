<template>
  <div class="find-panel">
    <input
      ref="inputRef"
      v-model="localQuery"
      class="find-input"
      type="search"
      placeholder="Find task, annotation, or migration…"
      @input="onQueryChange"
      @keydown.enter.prevent="emit('next')"
      @keydown.shift.enter.prevent="emit('prev')"
    >
    <select
      v-model="localMode"
      class="find-mode"
      @change="onModeChange"
    >
      <option value="contains">
        Contains
      </option>
      <option value="exact">
        Exact
      </option>
      <option value="regex">
        Regex
      </option>
      <option value="migrations">
        Migrations
      </option>
      <option value="sti">
        STI events
      </option>
      <option value="intervals">
        Intervals
      </option>
      <option value="lifecycle">
        Lifecycle
      </option>
      <option value="pointers">
        Pointers
      </option>
    </select>
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
    <div
      class="find-status"
      :class="{ error: !!error }"
    >
      {{ statusText }}
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'

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

const statusText = computed(() => {
  if (props.error) return props.error
  if (!localQuery.value.trim()) return '0 matches'
  const label = ['migrations', 'sti', 'intervals', 'lifecycle', 'pointers'].includes(localMode.value)
    ? `${localMode.value} matches`
    : 'matches'
  if (props.hitCount === 0) return `0 ${label}`
  if (props.hitIndex >= 0) return `${props.hitCount} ${label} (at ${props.hitIndex + 1})`
  return `${props.hitCount} ${label}`
})

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
.find-status {
  font-size: 11px;
  color: var(--fg-dim);
}
.find-status.error {
  color: #e07070;
}
</style>
