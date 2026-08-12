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
        Select a finding before Verify or Auto investigate.
      </p>
      <div class="analysis-body">
        <ul
          v-if="findings.length"
          class="analysis-list"
        >
          <li
            v-for="(f, i) in findings"
            :key="i"
            :class="[
              `sev-${f.severity || 'info'}`,
              { selected: selectedId === (f.id || '') && (f.id || '') },
            ]"
            @click="selectedId = f.id || ''"
          >
            <div class="finding-title">{{ f.title }}</div>
            <div class="finding-text">{{ f.text }}</div>
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
        <div class="analysis-footer-ai-label">Ask AI</div>
        <div class="analysis-footer-left">
          <button
            type="button"
            class="analysis-btn primary"
            :title="aiEnabled
              ? 'Open the AI Assistant and investigate the top findings with tools'
              : 'Enable AI Assistant in Settings → AI'"
            @click="emit('query-ai', 'investigate')"
          >
            Investigate…
          </button>
          <button
            type="button"
            class="analysis-btn"
            :title="aiEnabled
              ? 'Open the AI Assistant for evidence-driven root-cause analysis'
              : 'Enable AI Assistant in Settings → AI'"
            @click="emit('query-ai', 'root_cause')"
          >
            Root cause…
          </button>
          <button
            type="button"
            class="analysis-btn"
            :title="aiEnabled
              ? 'Open the AI Assistant and verify the selected finding with evidence'
              : 'Enable AI Assistant in Settings → AI'"
            @click="emit('query-ai', { template: 'verify', findingId: selectedId })"
          >
            Verify with AI…
          </button>
          <button
            type="button"
            class="analysis-btn"
            :title="aiEnabled
              ? 'Run the automatic investigate → correlate → critical-path → what-if/optimize workflow'
              : 'Enable AI Assistant in Settings → AI'"
            @click="emit('query-ai', { template: 'auto_investigate', findingId: selectedId })"
          >
            Auto investigate…
          </button>
          <button
            type="button"
            class="analysis-btn"
            :title="aiEnabled
              ? 'Open the AI Assistant and walk through these Analysis Findings'
              : 'Enable AI Assistant in Settings → AI'"
            @click="emit('query-ai', 'findings')"
          >
            Query with AI…
          </button>
        </div>
        <div class="analysis-footer-right">
          <button
            type="button"
            class="analysis-btn"
            title="Download findings as a plain-text file"
            @click="saveAsText"
          >
            Save as Text…
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
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { formatAnalysisFindingsText } from '../utils/workflowAnalysis.js'

const props = defineProps({
  findings: { type: Array, default: () => [] },
  scopeLabel: { type: String, default: '' },
  aiEnabled: { type: Boolean, default: true },
})

const emit = defineEmits(['close', 'query-ai'])

const selectedId = ref('')

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
  width: min(980px, calc(100vw - 24px));
  max-height: min(84vh, 680px);
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
  padding: 10px 16px 4px;
  font-size: 12px;
  line-height: 1.45;
  color: var(--fg-dim);
}

.analysis-body {
  flex: 1 1 auto;
  overflow: auto;
  padding: 8px 16px 14px;
  min-height: 180px;
}

.analysis-list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.analysis-list li {
  margin: 0 0 8px;
  line-height: 1.45;
  font-size: 13px;
  cursor: pointer;
  border-radius: 6px;
  padding: 10px 12px;
}

.analysis-list li.selected {
  background: var(--tb-btn-hover, rgba(255, 255, 255, 0.08));
  outline: 1px solid rgba(52, 152, 219, 0.45);
}

.finding-title {
  font-weight: 700;
  margin-bottom: 4px;
}

.finding-text {
  opacity: 0.92;
  line-height: 1.45;
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
  flex-direction: column;
  gap: 10px;
  padding: 12px 16px 14px;
  border-top: 1px solid var(--border);
}

.analysis-footer-ai-label {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.4px;
  color: var(--fg-dim);
}

.analysis-footer-left {
  display: flex;
  flex-wrap: nowrap;
  gap: 10px;
  overflow-x: auto;
}

.analysis-footer-right {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  padding-top: 4px;
  border-top: 1px solid var(--border);
}

.analysis-btn {
  border: 1px solid var(--border);
  background: transparent;
  color: var(--fg);
  border-radius: 6px;
  padding: 8px 16px;
  font-size: 12px;
  cursor: pointer;
  min-height: 34px;
  white-space: nowrap;
  flex: 0 0 auto;
}

.analysis-btn:hover {
  background: var(--tb-btn-hover);
}

.analysis-btn.primary {
  background: var(--accent);
  border-color: var(--accent);
  color: #000;
  font-weight: 600;
}

.analysis-btn.primary:hover {
  filter: brightness(1.08);
}
</style>
