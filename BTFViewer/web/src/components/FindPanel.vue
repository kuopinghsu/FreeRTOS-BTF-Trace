<template>
  <div class="find-panel">
    <div
      class="findbar"
      :class="{ error: !!error }"
    >
      <svg class="findbar-lead" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="M21 21l-4.3-4.3" /></svg>
      <input
        ref="inputRef"
        v-model="localQuery"
        class="findbar-input"
        type="search"
        placeholder="Find task, annotation, migration…"
        :title="modeHelp"
        @input="onQueryChange"
        @keydown.enter.exact.prevent="emit('next')"
        @keydown.enter.shift.prevent="emit('prev')"
      >
      <button
        v-if="localQuery"
        type="button"
        class="findbar-clear"
        title="Clear (Esc)"
        @click="clearQuery"
      >&times;</button>
      <span
        v-if="counterText"
        class="findbar-count"
      >{{ counterText }}</span>
      <button
        type="button"
        class="findbar-step"
        title="Previous match (Shift+F3)"
        :disabled="!hitCount"
        @click="emit('prev')"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true"><path d="M18 15l-6-6-6 6" /></svg>
      </button>
      <button
        type="button"
        class="findbar-step"
        title="Next match (F3)"
        :disabled="!hitCount"
        @click="emit('next')"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true"><path d="M6 9l6 6 6-6" /></svg>
      </button>
    </div>

    <div class="find-mode-row">
      <span class="find-mode-label">Match</span>
      <DomSelect
        v-model="localMode"
        class="find-mode"
        :title="modeHelp"
        :options="findModeOptions"
        @change="onModeChange"
      />
    </div>

    <p
      v-if="error"
      class="find-note error"
    >{{ error }}</p>
    <p
      v-else-if="localQuery && !hitCount"
      class="find-note"
    >No matches for &ldquo;{{ localQuery }}&rdquo;. Try a different Match mode.</p>
    <div
      v-else-if="!localQuery"
      class="find-empty"
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="M21 21l-4.3-4.3" /></svg>
      <p>Search across tasks, annotations and migration events in the active trace.</p>
      <div class="find-examples">
        <button
          v-for="ex in EXAMPLES"
          :key="ex"
          type="button"
          @click="applyExample(ex)"
        >{{ ex }}</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import DomSelect from './DomSelect.vue'
import { FIND_MODE_CHOICES, findModeHelp } from '../utils/findAnalysis.js'

const EXAMPLES = ['IDLE', 'TICK', 'Core_0']

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

const counterText = computed(() => {
  if (props.error || !localQuery.value || !props.hitCount) return ''
  const pos = props.hitIndex >= 0 ? props.hitIndex + 1 : 1
  return `${pos} / ${props.hitCount}`
})

function onQueryChange() {
  emit('update:query', localQuery.value)
  emit('recompute')
}

function onModeChange() {
  emit('update:mode', localMode.value)
  emit('recompute')
}

function clearQuery() {
  localQuery.value = ''
  onQueryChange()
  inputRef.value?.focus()
}

function applyExample(text) {
  localQuery.value = text
  onQueryChange()
  inputRef.value?.focus()
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
  gap: var(--sp-3, 12px);
  padding: var(--sp-3, 12px);
  flex: 1;
  min-height: 0;
  font-family: var(--font-ui, inherit);
}

/* Browser-style search bar: leading glyph, input, clear, inline count, steppers. */
.findbar {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 4px 4px 8px;
  border: 1px solid var(--border);
  border-radius: var(--rp-r-1, 6px);
  background: var(--rp-surface-2, var(--bg));
}
.findbar:focus-within {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--rp-sel-bg, rgba(79,139,255,0.15));
}
.findbar.error {
  border-color: var(--analysis-err, #e07070);
}

.findbar-lead {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
  color: var(--fg-dim);
}

.findbar-input {
  flex: 1;
  min-width: 0;
  border: 0;
  background: transparent;
  color: var(--fg);
  font-family: var(--font-mono, monospace);
  font-size: var(--type-meta, 11px);
  padding: 3px 0;
}
.findbar-input:focus { outline: none; }
.findbar-input::-webkit-search-cancel-button { display: none; }

.findbar-clear {
  border: 0;
  background: transparent;
  color: var(--fg-dim);
  cursor: pointer;
  font-size: 15px;
  line-height: 1;
  padding: 0 4px;
}
.findbar-clear:hover { color: var(--fg); }

.findbar-count {
  font-family: var(--font-mono, monospace);
  font-variant-numeric: tabular-nums;
  font-size: 10px;
  color: var(--fg-dim);
  white-space: nowrap;
  padding: 0 2px;
}

.findbar-step {
  width: 22px;
  height: 22px;
  display: grid;
  place-items: center;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: var(--fg-dim);
  cursor: pointer;
}
.findbar-step svg { width: 12px; height: 12px; }
.findbar-step:hover:not(:disabled) {
  background: var(--rp-surface-3, var(--tb-btn-hover));
  color: var(--fg);
}
.findbar-step:disabled { opacity: 0.35; cursor: default; }

.find-mode-row {
  display: flex;
  align-items: center;
  gap: var(--sp-2, 8px);
}
.find-mode-label {
  font-size: var(--type-meta, 11px);
  color: var(--fg-dim);
  flex-shrink: 0;
}
.find-mode {
  flex: 1;
  padding: 4px 6px;
  border: 1px solid var(--border);
  border-radius: var(--rp-r-1, 6px);
  background: var(--rp-surface-2, var(--bg));
  color: var(--fg);
  font-size: var(--type-body, 12px);
}

.find-note {
  font-size: var(--type-meta, 11px);
  color: var(--fg-dim);
  line-height: 1.4;
}
.find-note.error { color: var(--analysis-err, #e07070); }

.find-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: var(--sp-3, 12px);
  padding: var(--sp-5, 24px) var(--sp-4, 16px);
  color: var(--fg-dim);
}
.find-empty > svg {
  width: 24px;
  height: 24px;
  opacity: 0.6;
}
.find-empty p {
  font-size: var(--type-meta, 11px);
  line-height: 1.45;
}
.find-examples {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  justify-content: center;
}
.find-examples button {
  border: 1px solid var(--border);
  background: var(--rp-surface-2, transparent);
  color: var(--fg-dim);
  font-family: var(--font-mono, monospace);
  font-size: 10px;
  padding: 3px 8px;
  border-radius: 999px;
  cursor: pointer;
}
.find-examples button:hover {
  border-color: var(--rp-accent-line, var(--accent));
  color: var(--accent);
}
</style>
