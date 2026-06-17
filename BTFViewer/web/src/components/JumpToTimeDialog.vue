<template>
  <div
    class="dialog-overlay"
    @click.self="emit('close')"
  >
    <div
      class="jump-dialog"
      role="dialog"
      aria-modal="true"
      aria-label="Jump to time"
    >
      <div class="jump-header">
        <div class="jump-title">
          Jump to Time
        </div>
        <button
          class="jump-close"
          type="button"
          @click="emit('close')"
        >
          ✕
        </button>
      </div>
      <div class="jump-body">
        <label class="jump-label">
          Time (same format as ruler, e.g. {{ example }})
        </label>
        <input
          ref="inputRef"
          v-model="text"
          class="jump-input"
          type="text"
          @keydown.enter.prevent="onJump"
        >
        <div
          v-if="error"
          class="jump-error"
        >
          {{ error }}
        </div>
        <div class="jump-quick">
          <button
            type="button"
            class="jump-btn"
            @click="emit('jumpStart')"
          >
            Trace start
          </button>
          <button
            type="button"
            class="jump-btn"
            @click="emit('jumpEnd')"
          >
            Trace end
          </button>
        </div>
      </div>
      <div class="jump-footer">
        <button
          type="button"
          class="jump-btn primary"
          @click="onJump"
        >
          Jump
        </button>
        <button
          type="button"
          class="jump-btn"
          @click="emit('close')"
        >
          Cancel
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { formatTime } from '../utils/timeFormat.js'

const props = defineProps({
  trace: { type: Object, required: true },
})

const emit = defineEmits(['close', 'jump', 'jumpStart', 'jumpEnd'])

const text = ref('')
const error = ref('')
const inputRef = ref(null)

const example = computed(() => formatTime(props.trace.timeMin, props.trace.timeScale))

function parseTimeInput(raw) {
  const s = (raw || '').trim()
  if (!s) return null
  const scale = props.trace.timeScale
  const unitMult = { ns: 1, us: 1000, ms: 1_000_000, s: 1_000_000_000 }
  const m = s.match(/^(-?\d+(?:\.\d+)?)\s*(ns|us|µs|μs|ms|s)?$/i)
  if (m) {
    const num = parseFloat(m[1])
    let u = (m[2] || scale || 'ns').toLowerCase().replace(/[µμ]/g, 'u')
    if (u === 'u') u = 'us'
    const mult = unitMult[u] ?? 1
    return Math.round(num * mult)
  }
  const asNum = Number(s)
  if (!Number.isNaN(asNum)) return Math.round(asNum)
  return null
}

function onJump() {
  const ns = parseTimeInput(text.value)
  if (ns == null) {
    error.value = 'Enter a valid time value'
    return
  }
  const lo = props.trace.timeMin
  const hi = props.trace.timeMax
  if (ns < lo || ns > hi) {
    error.value = `Time must be between ${formatTime(lo, props.trace.timeScale)} and ${formatTime(hi, props.trace.timeScale)}`
    return
  }
  emit('jump', ns)
}

onMounted(() => inputRef.value?.focus())
</script>

<style scoped>
.dialog-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10000;
}
.jump-dialog {
  background: var(--panel-bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  min-width: 320px;
  max-width: 420px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.35);
}
.jump-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  border-bottom: 1px solid var(--border);
}
.jump-title { font-weight: 600; font-size: 14px; }
.jump-close {
  background: none;
  border: none;
  color: var(--fg-dim);
  cursor: pointer;
  font-size: 16px;
}
.jump-body { padding: 14px; display: flex; flex-direction: column; gap: 8px; }
.jump-label { font-size: 12px; color: var(--fg-dim); }
.jump-input {
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--bg);
  color: var(--fg);
  font-family: monospace;
  font-size: 13px;
}
.jump-error { font-size: 12px; color: #e07070; }
.jump-quick { display: flex; gap: 8px; }
.jump-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 10px 14px;
  border-top: 1px solid var(--border);
}
.jump-btn {
  padding: 5px 12px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--panel-bg);
  color: var(--fg);
  font-size: 12px;
  cursor: pointer;
}
.jump-btn.primary {
  background: var(--accent);
  border-color: var(--accent);
  color: #000;
}
</style>
