<template>
  <div
    class="dialog-overlay"
    @click.self="emit('close')"
  >
    <div
      class="analysis-dialog"
      role="dialog"
      aria-modal="true"
      aria-label="Analysis Findings"
    >
      <div class="analysis-header">
        <div class="analysis-title">
          Analysis Findings{{ scopeLabel }}
        </div>
        <button
          class="analysis-close"
          type="button"
          title="Close"
          @click="emit('close')"
        >
          ✕
        </button>
      </div>
      <p class="analysis-note">
        Heuristic summary of load balance, WCET, blocking, thrashing, deadlines, tick health, and sync.
      </p>
      <div class="analysis-body">
        <ul
          v-if="findings.length"
          class="analysis-list"
        >
          <li
            v-for="(f, i) in findings"
            :key="i"
            :class="`sev-${f.severity || 'info'}`"
          >
            <strong>{{ f.title }}</strong> — {{ f.text }}
          </li>
        </ul>
        <div
          v-else
          class="analysis-empty"
        >
          No findings for the current scope
        </div>
      </div>
      <div class="analysis-footer">
        <button
          type="button"
          class="analysis-btn"
          title="Download findings as a plain-text file"
          @click="saveAsText"
        >
          Save as text…
        </button>
        <button
          type="button"
          class="analysis-btn"
          @click="emit('close')"
        >
          Close
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { formatAnalysisFindingsText } from '../utils/workflowAnalysis.js'

const props = defineProps({
  findings: { type: Array, default: () => [] },
  scopeLabel: { type: String, default: '' },
})

const emit = defineEmits(['close'])

function _stamp() {
  const d = new Date()
  const p = n => String(n).padStart(2, '0')
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`
}

function saveAsText() {
  const text = formatAnalysisFindingsText(props.findings, props.scopeLabel)
  const blob = new Blob([text], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `analysis-findings-${_stamp()}.txt`
  a.click()
  URL.revokeObjectURL(url)
}
</script>

<style scoped>
.dialog-overlay {
  position: fixed;
  inset: 0;
  z-index: 1200;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}

.analysis-dialog {
  width: min(720px, calc(100vw - 32px));
  max-height: min(80vh, 640px);
  display: flex;
  flex-direction: column;
  background: var(--panel-bg);
  border: 1px solid var(--border);
  border-radius: 12px;
  box-shadow: 0 16px 40px rgba(0, 0, 0, 0.45);
  overflow: hidden;
  color: var(--fg);
}

.analysis-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--border);
}

.analysis-title {
  font-size: 15px;
  font-weight: 700;
}

.analysis-close {
  border: 1px solid var(--border);
  background: transparent;
  color: var(--fg);
  border-radius: 6px;
  padding: 4px 10px;
  cursor: pointer;
}

.analysis-note {
  margin: 0;
  padding: 8px 14px 0;
  font-size: 12px;
  color: var(--fg-dim);
}

.analysis-body {
  flex: 1 1 auto;
  overflow: auto;
  padding: 8px 14px 12px;
}

.analysis-list {
  margin: 0;
  padding: 0 0 0 18px;
}

.analysis-list li {
  margin: 8px 0;
  line-height: 1.45;
  font-size: 13px;
}

.analysis-list .sev-warning { color: #d68910; }
.analysis-list .sev-error { color: #c0392b; }
.analysis-list .sev-info { color: var(--fg); }

.analysis-empty {
  font-size: 13px;
  color: var(--fg-dim);
  padding: 12px 0;
}

.analysis-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 10px 14px;
  border-top: 1px solid var(--border);
}

.analysis-btn {
  border: 1px solid var(--border);
  background: transparent;
  color: var(--fg);
  border-radius: 6px;
  padding: 6px 14px;
  font-size: 12px;
  cursor: pointer;
}

.analysis-btn:hover {
  background: var(--tb-btn-hover);
}
</style>
