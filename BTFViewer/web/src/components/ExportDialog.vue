<template>
  <div
    class="dialog-overlay"
    @click.self="emit('close')"
  >
    <div
      class="exp-dialog"
      role="dialog"
      aria-modal="true"
      aria-label="Export"
    >
      <div class="exp-header">
        <div class="exp-title">
          Export
        </div>
        <button
          class="exp-close"
          type="button"
          @click="emit('close')"
        >
          ✕
        </button>
      </div>

      <div class="exp-body">
        <ul class="exp-targets">
          <li
            v-for="t in targets"
            :key="t.id"
          >
            <label
              class="exp-target"
              :class="{ disabled: !t.available }"
            >
              <input
                v-model="target"
                type="radio"
                :value="t.id"
                :disabled="!t.available"
              >
              <span class="exp-target-text">
                <span class="exp-target-label">{{ t.label }}</span>
                <span class="exp-target-hint">{{ t.available ? t.hint : t.reason }}</span>
              </span>
            </label>
          </li>
        </ul>

        <!-- Per-target options. All three panels are always rendered and share
             one grid cell, so switching the selection never resizes the dialog
             (mirrors the desktop QStackedWidget). -->
        <div class="exp-opts-stack">
          <div
            class="exp-opts"
            :class="{ 'is-hidden': target !== 'workspace' }"
          >
            <label class="exp-check">
              <input
                v-model="embedTrace"
                type="checkbox"
              >
              Embed the trace file (portable — opens anywhere)
            </label>
            <ul class="exp-summary">
              <li>View state &amp; cursors</li>
              <li>Analysis findings <span v-if="!hasFindings">— none in scope</span></li>
              <li>Trace health status</li>
              <li>Investigation notebook <span v-if="!hasInvestigation">— empty</span></li>
              <li>Rendered statistics HTML report</li>
            </ul>
          </div>

          <div
            class="exp-opts"
            :class="{ 'is-hidden': target !== 'perfetto' }"
          >
            <label class="exp-radio">
              <input
                v-model="perfettoScope"
                type="radio"
                value="full"
              >
              Full loaded trace
            </label>
            <label class="exp-radio">
              <input
                v-model="perfettoScope"
                type="radio"
                value="viewport"
              >
              Current timeline viewport only
            </label>
          </div>

          <div
            class="exp-opts"
            :class="{ 'is-hidden': target !== 'btf-slice' }"
          >
            <p
              v-if="range"
              class="exp-range"
            >
              Writes events in <code>[{{ fmt(range.lo) }}, {{ fmt(range.hi) }})</code>
              (earliest → latest cursor).
            </p>
            <p
              v-else
              class="exp-range muted"
            >
              Place at least two cursors to mark the range.
            </p>
          </div>
        </div>

        <!-- Applies to every target. -->
        <div class="exp-anon">
          <label class="exp-check">
            <input
              v-model="anonymize"
              type="checkbox"
            >
            Anonymize task names (Task-1, Task-2, …)
          </label>
          <p class="exp-anon-hint">
            Every task name in the exported trace, Perfetto file, findings, health
            and notebook is replaced with a stable Task-N alias.
          </p>
        </div>
      </div>

      <div class="exp-footer">
        <button
          type="button"
          class="exp-btn primary"
          :disabled="!canExport"
          @click="run"
        >
          Export
        </button>
        <button
          type="button"
          class="exp-btn"
          @click="emit('close')"
        >
          Cancel
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  targets: { type: Array, required: true },
  defaultTarget: { type: String, default: 'workspace' },
  range: { type: Object, default: null },
  hasFindings: { type: Boolean, default: false },
  hasInvestigation: { type: Boolean, default: false },
  formatNs: { type: Function, default: null },
})

const emit = defineEmits(['close', 'export'])

const target = ref(
  props.targets.find((t) => t.id === props.defaultTarget && t.available)?.id
  || props.targets.find((t) => t.available)?.id
  || props.defaultTarget,
)
const embedTrace = ref(true)
const perfettoScope = ref('full')
const anonymize = ref(false)

const canExport = computed(
  () => !!props.targets.find((t) => t.id === target.value && t.available),
)

function fmt(ns) {
  return props.formatNs ? props.formatNs(ns) : String(Math.trunc(ns))
}

function run() {
  if (!canExport.value) return
  emit('export', {
    target: target.value,
    embedTrace: embedTrace.value,
    perfettoScope: perfettoScope.value,
    anonymize: anonymize.value,
  })
}
</script>

<style scoped>
.dialog-overlay {
  position: fixed;
  inset: 0;
  background: color-mix(in srgb, #000 52%, transparent);
  backdrop-filter: blur(5px) saturate(1.1);
  -webkit-backdrop-filter: blur(5px) saturate(1.1);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10000;
}
.exp-dialog {
  background: var(--panel-bg);
  border: 1px solid var(--app-border-soft, var(--border));
  border-radius: 14px;
  width: min(460px, calc(100vw - 32px));
  overflow: hidden;
  box-shadow: 0 32px 80px -16px rgba(0, 0, 0, 0.5);
  animation: exp-pop 0.18s cubic-bezier(0.32, 0.72, 0, 1);
}
@keyframes exp-pop {
  from { opacity: 0; transform: translateY(10px) scale(0.98); }
  to   { opacity: 1; transform: none; }
}
.exp-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 13px 14px;
  border-bottom: 1px solid var(--app-border-soft, var(--border));
  background: color-mix(in srgb, var(--panel-bg) 55%, var(--bg));
}
.exp-title { font-weight: 650; font-size: 14px; }
.exp-close {
  background: none;
  border: none;
  color: var(--fg-dim);
  cursor: pointer;
  font-size: 16px;
}
.exp-body { padding: 14px; display: flex; flex-direction: column; gap: 12px; }
.exp-targets { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.exp-target {
  display: flex;
  gap: 9px;
  align-items: flex-start;
  padding: 9px 10px;
  border: 1px solid var(--border);
  border-radius: 9px;
  cursor: pointer;
}
.exp-target:hover:not(.disabled) { background: var(--tb-btn-hover, var(--bg)); }
.exp-target.disabled { opacity: 0.5; cursor: default; }
.exp-target input { margin-top: 2px; }
.exp-target-text { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.exp-target-label { font-size: 13px; font-weight: 600; }
.exp-target-hint { font-size: 11px; color: var(--fg-dim); line-height: 1.4; }

/* One shared grid cell: every panel overlaps, so the box is always as tall as
   the tallest panel (the workspace summary) and the dialog never resizes when
   the selection changes. */
.exp-opts-stack {
  display: grid;
}
.exp-opts-stack > .exp-opts {
  grid-area: 1 / 1;
}
.exp-opts-stack > .exp-opts.is-hidden {
  visibility: hidden;
}
.exp-opts {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px;
  border: 1px solid var(--app-border-soft, var(--border));
  border-radius: 9px;
  background: color-mix(in srgb, var(--panel-bg) 40%, var(--bg));
}
.exp-check, .exp-radio { font-size: 12px; display: flex; align-items: center; gap: 7px; }
.exp-summary { margin: 4px 0 0; padding-left: 18px; font-size: 11px; color: var(--fg-dim); line-height: 1.6; }
.exp-anon { display: flex; flex-direction: column; gap: 3px; }
.exp-anon .exp-check { font-weight: 550; }
.exp-anon-hint { margin: 0 0 0 24px; font-size: 11px; color: var(--fg-dim); line-height: 1.45; }
.exp-range { font-size: 12px; margin: 0; }
.exp-range.muted { color: var(--fg-dim); }
.exp-range code {
  font-family: var(--font-mono, monospace);
  background: color-mix(in srgb, var(--fg) 10%, transparent);
  padding: 1px 5px;
  border-radius: 5px;
}
.exp-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 14px;
  border-top: 1px solid var(--app-border-soft, var(--border));
  background: color-mix(in srgb, var(--panel-bg) 55%, var(--bg));
}
.exp-btn {
  padding: 6px 14px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel-bg);
  color: var(--fg);
  font-size: 12px;
  font-weight: 550;
  cursor: pointer;
}
.exp-btn:hover:not(:disabled) { background: var(--tb-btn-hover, var(--bg)); }
.exp-btn:disabled { opacity: 0.45; cursor: default; }
.exp-btn.primary {
  background: var(--accent);
  border-color: var(--accent);
  color: #fff;
  font-weight: 650;
}
.exp-btn.primary:disabled { opacity: 0.5; }
</style>
