<template>
  <!-- Floating tool window (Desktop Tool parity): Timeline stays clickable. -->
  <div class="analysis-tool-host">
    <div
      class="analysis-dialog"
      role="dialog"
      aria-modal="false"
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
        Select a finding before Verify, Explain, or Auto investigate.
      </p>
      <pre
        v-if="dashboard.summary"
        class="analysis-overview"
      >{{ dashboard.summary }}</pre>
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
              { 'sev-ok': f.id === 'load_balance_ok' },
              { selected: selectedId === (f.id || '') && (f.id || '') },
            ]"
            @click="selectedId = f.id || ''"
          >
            <div class="finding-title">{{ clusterPrefix(f) }}{{ f.title }}</div>
            <div class="finding-text">{{ f.text }}</div>
            <div
              v-if="f.evidence_text"
              class="finding-evidence"
            ><span class="finding-evidence-label">Evidence</span> {{ f.evidence_text }}</div>
          </li>
        </ul>
        <div
          v-else
          class="analysis-empty"
        >
          No findings for the current scope
        </div>
      </div>
      <div class="analysis-scope">
        <div class="analysis-scope-text">{{ scopeHint }}</div>
        <button
          type="button"
          class="analysis-btn"
          title="Place C1–C2 on the recommended window and zoom the timeline"
          @click="applyScope"
        >
          Apply cursors
        </button>
        <button
          type="button"
          class="analysis-btn"
          :disabled="!selectedFinding"
          title="Jump to Timeline Evidence for the selected finding (does not change Scope or Filters)"
          @click="showEvidence"
        >
          Show Evidence
        </button>
        <button
          type="button"
          class="analysis-btn analysis-btn-primary"
          :disabled="!investigateSectionId"
          :title="investigateSectionId
            ? `Scope the investigation and jump to the relevant Statistics section`
            : 'No specific Statistics section is associated with this finding'"
          @click="investigate"
        >
          Investigate
        </button>
      </div>
      <div class="analysis-footer">
        <div class="analysis-footer-ai-label">Ask AI</div>
        <div class="analysis-footer-left">
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
          <button
            type="button"
            class="analysis-btn"
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
              ? 'Open the AI Assistant and verify the selected finding with evidence'
              : 'Enable AI Assistant in Settings → AI'"
            @click="emit('query-ai', { template: 'verify', findingId: selectedId })"
          >
            Verify with AI…
          </button>
          <div class="analysis-explain-wrap">
            <button
              ref="explainBtn"
              type="button"
              class="analysis-btn"
              :title="aiEnabled
                ? 'Quick / Technical / Deep explanation of the selected finding'
                : 'Enable AI Assistant in Settings → AI'"
              @click.stop="toggleExplain"
            >
              Explain…
            </button>
          </div>
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
              ? 'Run the automatic investigate → correlate → critical-path → what-if/optimize workflow'
              : 'Enable AI Assistant in Settings → AI'"
            @click="emit('query-ai', { template: 'auto_investigate', findingId: selectedId })"
          >
            Auto investigate…
          </button>
          <button
            type="button"
            class="analysis-btn"
            title="Save this finding set as a user investigation template"
            @click="emit('save-recipe')"
          >
            Save recipe…
          </button>
          <button
            type="button"
            class="analysis-btn"
            title="Export an analysis story from the overview and findings"
            @click="emit('save-story')"
          >
            Story…
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
    <Teleport to="body">
      <div
        v-if="explainOpen"
        ref="explainMenuEl"
        class="analysis-explain-menu"
        role="menu"
        :style="explainMenuStyle"
        @click.stop
      >
        <button
          v-for="lv in explainLevels"
          :key="lv.id"
          type="button"
          class="analysis-explain-item"
          role="menuitem"
          @click="explainFinding(lv.id)"
        >
          {{ lv.label }}
        </button>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { EXPLAIN_LEVELS } from '../utils/aiCase.js'
import { analysisDashboard } from '../utils/aiPlanner.js'
import { bestFindingScope } from '../utils/uxExplore.js'
import { formatAnalysisFindingsText, FINDING_SECTION_MAP } from '../utils/workflowAnalysis.js'

const props = defineProps({
  findings: { type: Array, default: () => [] },
  scopeLabel: { type: String, default: '' },
  aiEnabled: { type: Boolean, default: true },
  uxEvents: { type: Array, default: () => [] },
  timeMin: { type: Number, default: 0 },
  timeMax: { type: Number, default: 0 },
  qualityWarnings: { type: Array, default: () => [] },
})

const emit = defineEmits([
  'close', 'query-ai', 'apply-scope', 'investigate', 'show-evidence',
  'save-recipe', 'save-story',
])

const selectedId = ref('')
const dashboard = computed(() =>
  analysisDashboard(props.findings, { qualityWarnings: props.qualityWarnings }))

function clusterPrefix(f) {
  const id = String(f?.id || '')
  const title = String(f?.title || '')
  for (const inc of dashboard.value.clusters || []) {
    if ((inc.finding_ids || []).includes(id) && id) return `[${inc.id}] `
    if ((inc.findings || []).includes(title) && title) return `[${inc.id}] `
  }
  return ''
}
const explainOpen = ref(false)
const explainBtn = ref(null)
const explainMenuEl = ref(null)
const explainMenuStyle = ref({})
const explainLevels = EXPLAIN_LEVELS.map(id => ({
  id,
  label: `${id.charAt(0).toUpperCase()}${id.slice(1)}`,
}))

const selectedFinding = computed(() => {
  const id = selectedId.value
  if (!id) return props.findings[0] || null
  return props.findings.find(f => (f.id || '') === id) || props.findings[0] || null
})

const scopeHint = computed(() => {
  const f = selectedFinding.value
  if (!f) return 'Select a finding to recommend a cursor window.'
  const title = String(f.title || 'Finding').trim()
  const scope = bestFindingScope(f, props.uxEvents, props.timeMin, props.timeMax)
  if (scope?.reason) return `Recommended scope: ${scope.reason}`
  return `Recommended scope: cover ${title} (activation + waits).`
})

function applyScope() {
  const f = selectedFinding.value
  if (f) emit('apply-scope', f)
}

function showEvidence() {
  const f = selectedFinding.value
  if (f) emit('show-evidence', f)
}

const investigateSectionId = computed(() => {
  const f = selectedFinding.value
  return (f && FINDING_SECTION_MAP[f.id || '']) || null
})

function investigate() {
  const f = selectedFinding.value
  const sectionId = investigateSectionId.value
  if (!f || !sectionId) return
  emit('investigate', { finding: f, sectionId })
}

function placeExplainMenu() {
  const btn = explainBtn.value
  if (!btn) return
  const r = btn.getBoundingClientRect()
  const gap = 4
  const spaceAbove = r.top
  const spaceBelow = window.innerHeight - r.bottom
  if (spaceAbove >= spaceBelow) {
    explainMenuStyle.value = {
      position: 'fixed',
      left: `${Math.max(8, r.left)}px`,
      bottom: `${window.innerHeight - r.top + gap}px`,
      zIndex: 10100,
    }
  } else {
    explainMenuStyle.value = {
      position: 'fixed',
      left: `${Math.max(8, r.left)}px`,
      top: `${r.bottom + gap}px`,
      zIndex: 10100,
    }
  }
}

function toggleExplain() {
  explainOpen.value = !explainOpen.value
  if (explainOpen.value) nextTick(placeExplainMenu)
}

function onDocMouseDown(ev) {
  if (!explainOpen.value) return
  const t = ev.target
  if (explainBtn.value?.contains(t)) return
  if (explainMenuEl.value?.contains(t)) return
  explainOpen.value = false
}

function onDocKeyDown(ev) {
  if (ev.key === 'Escape' && explainOpen.value) {
    explainOpen.value = false
    ev.preventDefault()
  }
}

onMounted(() => {
  document.addEventListener('mousedown', onDocMouseDown)
  document.addEventListener('keydown', onDocKeyDown)
  window.addEventListener('resize', placeExplainMenu)
})

onUnmounted(() => {
  document.removeEventListener('mousedown', onDocMouseDown)
  document.removeEventListener('keydown', onDocKeyDown)
  window.removeEventListener('resize', placeExplainMenu)
})

function explainFinding(level) {
  explainOpen.value = false
  emit('query-ai', {
    template: 'explain_finding',
    findingId: selectedId.value || selectedFinding.value?.id || '',
    level,
  })
}

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
/* Non-modal floating tool window — Timeline remains clickable (Desktop Tool parity). */
.analysis-tool-host {
  position: fixed;
  inset: 0;
  z-index: 1200;
  background: transparent;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  pointer-events: none;
}

.analysis-dialog {
  pointer-events: auto;
  width: min(960px, calc(100vw - 24px));
  max-height: min(84vh, 600px);
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
  flex: 0 0 auto;
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

.analysis-overview {
  margin: 0 16px 8px;
  padding: 8px 10px;
  font: inherit;
  font-size: 12px;
  white-space: pre-wrap;
  color: var(--fg);
  border: 1px solid var(--border);
  border-radius: 6px;
  background: rgba(52, 152, 219, 0.08);
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
  line-height: 1.45;
}

.finding-evidence {
  margin-top: 4px;
  font-size: 11px;
  font-family: monospace;
  opacity: 0.85;
}

.finding-evidence-label {
  font-weight: 700;
  text-transform: uppercase;
  font-size: 9px;
  letter-spacing: 0.4px;
  margin-right: 4px;
}

.analysis-list .sev-warning { color: var(--analysis-warn); }
.analysis-list .sev-error { color: var(--analysis-err); }
.analysis-list .sev-info { color: var(--fg); }
.analysis-list .sev-ok { color: var(--analysis-ok); }

.analysis-empty {
  font-size: 13px;
  color: var(--fg-dim);
  padding: 12px 0;
}

.analysis-scope {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  border-top: 1px solid var(--border);
  flex: 0 0 auto;
}

.analysis-scope-text {
  flex: 1 1 100%;
  font-size: 12px;
  color: var(--fg-dim);
  line-height: 1.4;
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
  flex-wrap: wrap;
  gap: 8px;
  overflow-x: auto;
}

.analysis-explain-wrap {
  position: relative;
  flex: 0 0 auto;
}

.analysis-explain-menu {
  min-width: 128px;
  padding: 4px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--panel-bg);
  box-shadow: 0 8px 20px rgba(0, 0, 0, 0.35);
}

.analysis-explain-item {
  display: block;
  width: 100%;
  border: none;
  background: transparent;
  color: var(--fg);
  border-radius: 4px;
  padding: 6px 10px;
  font-size: 12px;
  text-align: left;
  cursor: pointer;
}

.analysis-explain-item:hover {
  background: var(--tb-btn-hover);
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

.analysis-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.analysis-btn-primary {
  border-color: var(--accent);
  color: var(--accent);
  font-weight: 600;
}
</style>
