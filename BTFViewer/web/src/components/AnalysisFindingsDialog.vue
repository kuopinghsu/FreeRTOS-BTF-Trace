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
          aria-label="Close"
          @click="emit('close')"
        >×</button>
      </div>
      <AnalysisContextStrip
        :context="analysisContext"
        :stale="contextStale"
        :show-clear-filters="showClearFilters"
        :on-clear-filters="onClearFilters"
        @recalculate="emit('recalculate-context')"
      />
      <!-- Desktop parity: note, then queues/filters, then overview box (no height clip). -->
      <p class="analysis-note">
        Heuristic summary of load balance, WCET, blocking, thrashing, deadlines, tick health, and sync.<br>
        Select a finding, then triage or Investigate.
      </p>
      <div class="analysis-queue">
        <button
          v-for="q in queueTabs"
          :key="q.id"
          type="button"
          class="analysis-queue-btn"
          :class="{ active: activeQueue === q.id }"
          @click="activeQueue = q.id"
        >
          {{ q.label }} ({{ counts[q.id] || 0 }})
        </button>
      </div>
      <div class="analysis-filters">
        <label class="analysis-filter-field">
          <span class="analysis-filter-label">Severity</span>
          <DomSelect
            v-model="filterSeverity"
            class="analysis-filter-select"
            aria-label="Severity"
            :options="severityOptions"
          />
        </label>
        <label class="analysis-filter-field">
          <span class="analysis-filter-label">Evidence</span>
          <DomSelect
            v-model="filterEvidence"
            class="analysis-filter-select"
            aria-label="Evidence"
            :options="evidenceOptions"
          />
        </label>
        <label class="analysis-filter-field">
          <span class="analysis-filter-label">Category</span>
          <DomSelect
            v-model="filterCategory"
            class="analysis-filter-select"
            aria-label="Category"
            :options="categoryOptions"
          />
        </label>
        <label class="analysis-filter-field">
          <span class="analysis-filter-label">Sort</span>
          <DomSelect
            v-model="sortBy"
            class="analysis-filter-select analysis-filter-select-sort"
            aria-label="Sort"
            :options="sortOptions"
          />
        </label>
        <label class="analysis-filter-check">
          <input
            v-model="groupIncidents"
            type="checkbox"
          >
          Group incidents
        </label>
      </div>
      <pre
        v-if="dashboard.summary"
        class="analysis-overview"
      >{{ dashboard.summary }}</pre>
      <div class="analysis-body">
        <ul
          v-if="displayRows.length"
          class="analysis-list"
        >
          <template
            v-for="(row, i) in displayRows"
            :key="row.kind === 'header' ? `h-${row.incident_id}` : (row.id || i)"
          >
            <li
              v-if="row.kind === 'header'"
              class="analysis-incident-header"
              :class="{ collapsed: collapsedIncidents[row.incident_id] }"
              @click="toggleIncident(row.incident_id)"
            >
              <span class="incident-toggle">{{ collapsedIncidents[row.incident_id] ? '▸' : '▾' }}</span>
              {{ row.label }}
              <span class="incident-count">{{ row.count }} related</span>
            </li>
            <li
              v-else-if="!row.incident_id || !collapsedIncidents[row.incident_id]"
              :class="[
                `sev-${row.severity || 'info'}`,
                { 'sev-ok': row.id === 'load_balance_ok' },
                { selected: selectedId === (row.id || '') && (row.id || '') },
                { 'in-incident': !!row.incident_id },
              ]"
              @click="selectedId = row.id || ''"
            >
              <div class="finding-title">{{ severityGlyph(row) }}{{ clusterPrefix(row) }}{{ row.observation || row.title }}</div>
              <div
                v-if="row.evidence_strength_label"
                class="finding-strength"
                :title="row.evidence_strength_label"
              >{{ row.evidence_strength_label }}</div>
              <div class="finding-text">{{ row.why_it_matters || row.text }}</div>
              <div
                v-if="row.evidence_text"
                class="finding-evidence"
              ><span class="finding-evidence-label">Evidence</span> {{ row.evidence_text }}</div>
              <div
                v-if="row.check_next"
                class="finding-check-next"
              ><span class="finding-evidence-label">Check next</span> {{ row.check_next }}</div>
              <div
                v-if="dismissReason(row)"
                class="finding-dismiss-reason"
              >Dismissed: {{ dismissReason(row) }}</div>
            </li>
          </template>
        </ul>
        <div
          v-else
          class="analysis-empty"
        >
          No findings in this queue
        </div>
      </div>
      <div class="analysis-triage">
        <button
          type="button"
          class="analysis-btn"
          :disabled="!selectedFinding?.id"
          @click="toggleDone"
        >{{ isDone ? 'Undo' : 'Done' }}</button>
        <button
          type="button"
          class="analysis-btn"
          :disabled="!selectedFinding?.id"
          @click="toggleDismiss"
        >{{ isDismissed ? 'Restore' : 'Dismiss…' }}</button>
        <button
          type="button"
          class="analysis-btn"
          :disabled="!selectedFinding?.id || isInCase"
          @click="addToCase"
        >{{ isInCase ? 'In case' : 'Add to case' }}</button>
      </div>
      <div class="analysis-scope">
        <div class="analysis-scope-text">{{ scopeHint }}</div>
        <pre
          v-if="investigatePending"
          class="analysis-investigate-preview"
        >{{ investigatePreviewText }}</pre>
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
          {{ showOnTimelineLabel }}
        </button>
        <button
          v-if="!investigatePending"
          type="button"
          class="analysis-btn analysis-btn-primary"
          :disabled="!investigateSectionId"
          :title="investigateSectionId
            ? 'Preview Scope and Statistics changes, then Confirm'
            : 'No specific Statistics section is associated with this finding'"
          @click="beginInvestigate"
        >
          Investigate…
        </button>
        <button
          v-if="investigatePending"
          type="button"
          class="analysis-btn analysis-btn-primary"
          @click="confirmInvestigate"
        >
          Confirm Investigate
        </button>
        <button
          v-if="investigatePending"
          type="button"
          class="analysis-btn"
          @click="cancelInvestigate"
        >
          Cancel
        </button>
        <button
          v-if="canUndoInvestigate && !investigatePending"
          type="button"
          class="analysis-btn"
          title="Restore cursors and Limit-to-cursors from before Investigate"
          @click="emit('undo-investigate')"
        >
          Undo Scope
        </button>
      </div>
      <div class="analysis-footer">
        <div class="analysis-footer-row">
          <div class="analysis-menu-wrap">
            <button
              ref="askAiBtn"
              type="button"
              class="analysis-btn"
              :title="aiEnabled
                ? 'Ask AI about findings'
                : 'Enable AI Assistant in Settings → AI'"
              @click.stop="toggleAskAi"
            >
              Ask AI ▾
            </button>
          </div>
          <div class="analysis-menu-wrap">
            <button
              ref="moreBtn"
              type="button"
              class="analysis-btn"
              title="Save recipe, story, or text export"
              @click.stop="toggleMore"
            >
              More ▾
            </button>
          </div>
          <div class="analysis-footer-spacer" />
        </div>
      </div>
    </div>
    <Teleport to="body">
      <div
        v-if="askAiOpen"
        ref="askAiMenuEl"
        class="analysis-popup-menu"
        role="menu"
        :style="askAiMenuStyle"
        @click.stop
      >
        <button type="button" class="analysis-popup-item" role="menuitem" @click="askAi('findings')">Query findings…</button>
        <button type="button" class="analysis-popup-item" role="menuitem" @click="askAi('investigate')">Investigate…</button>
        <button type="button" class="analysis-popup-item" role="menuitem" @click="askAi({ template: 'verify', findingId: selectedId })">Verify…</button>
        <div class="analysis-popup-group">
          <div class="analysis-popup-label">Explain</div>
          <button
            v-for="lv in explainLevels"
            :key="lv.id"
            type="button"
            class="analysis-popup-item"
            role="menuitem"
            @click="explainFinding(lv.id)"
          >{{ lv.label }}</button>
        </div>
        <button type="button" class="analysis-popup-item" role="menuitem" @click="askAi('root_cause')">Root cause…</button>
        <button type="button" class="analysis-popup-item" role="menuitem" @click="askAi({ template: 'auto_investigate', findingId: selectedId })">Auto investigate…</button>
      </div>
      <div
        v-if="moreOpen"
        ref="moreMenuEl"
        class="analysis-popup-menu"
        role="menu"
        :style="moreMenuStyle"
        @click.stop
      >
        <button type="button" class="analysis-popup-item" role="menuitem" @click="moreAction('save-recipe')">Save recipe…</button>
        <button type="button" class="analysis-popup-item" role="menuitem" @click="moreAction('save-story')">Story…</button>
        <button type="button" class="analysis-popup-item" role="menuitem" @click="moreAction('save-text')">Save as text…</button>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { EXPLAIN_LEVELS } from '../utils/aiCase.js'
import { analysisDashboard } from '../utils/aiPlanner.js'
import { bestFindingScope } from '../utils/uxExplore.js'
import { SEMANTIC_GLYPHS } from '../utils/semanticColors.js'
import { formatAnalysisFindingsText, FINDING_SECTION_MAP } from '../utils/workflowAnalysis.js'
import AnalysisContextStrip from './AnalysisContextStrip.vue'
import DomSelect from './DomSelect.vue'
import {
  filterFindingsTriage,
  filterByQueue,
  queueCounts,
  applyTriageAction,
  normalizeTriageState,
  findingQueueStatus,
  findingFilterFacets,
  groupFindingsByIncident,
  formatInvestigatePreview,
  SORT_SEVERITY,
  SORT_KEYS,
  SORT_LABELS,
  QUEUE_OPEN,
  QUEUE_DONE,
  QUEUE_CASE,
  QUEUE_DISMISSED,
} from '../utils/findingsTriage.js'
import { SHOW_ON_TIMELINE_LABEL } from '../utils/evidenceHistory.js'

const props = defineProps({
  findings: { type: Array, default: () => [] },
  scopeLabel: { type: String, default: '' },
  analysisContext: { type: Object, default: null },
  contextStale: { type: Boolean, default: false },
  showClearFilters: { type: Boolean, default: false },
  onClearFilters: { type: Function, default: null },
  aiEnabled: { type: Boolean, default: true },
  uxEvents: { type: Array, default: () => [] },
  timeMin: { type: Number, default: 0 },
  timeMax: { type: Number, default: 0 },
  qualityWarnings: { type: Array, default: () => [] },
  triageState: { type: Object, default: null },
  currentLimit: { type: Boolean, default: false },
  currentCursorLo: { type: Number, default: null },
  currentCursorHi: { type: Number, default: null },
  canUndoInvestigate: { type: Boolean, default: false },
})

const emit = defineEmits([
  'close', 'query-ai', 'apply-scope', 'investigate', 'show-evidence',
  'save-recipe', 'save-story', 'recalculate-context', 'add-to-case',
  'update:triageState', 'undo-investigate',
])

const showOnTimelineLabel = SHOW_ON_TIMELINE_LABEL
const filterSeverity = ref('')
const filterEvidence = ref('')
const filterCategory = ref('')
const sortBy = ref(SORT_SEVERITY)
const groupIncidents = ref(true)
const collapsedIncidents = ref({})
const investigatePending = ref(false)
const severityOptions = [
  { value: '', label: 'All' },
  { value: 'error', label: 'Critical' },
  { value: 'warning', label: 'Warning' },
  { value: 'info', label: 'Info' },
]
const evidenceOptions = [
  { value: '', label: 'All' },
  { value: 'direct', label: 'Direct' },
  { value: 'derived', label: 'Derived' },
  { value: 'estimated', label: 'Estimated' },
]
const sortOptions = SORT_KEYS.map(k => ({ value: k, label: SORT_LABELS[k] || k }))
const activeQueue = ref(QUEUE_OPEN)
const triageState = ref(normalizeTriageState(props.triageState))

watch(() => props.triageState, (v) => {
  triageState.value = normalizeTriageState(v)
})

function commitTriage(next) {
  triageState.value = normalizeTriageState(next)
  emit('update:triageState', triageState.value)
}

const queueTabs = [
  { id: QUEUE_OPEN, label: 'Open' },
  { id: QUEUE_DONE, label: 'Done' },
  { id: QUEUE_CASE, label: 'Case' },
  { id: QUEUE_DISMISSED, label: 'Dismissed' },
]

const facets = computed(() => findingFilterFacets(props.findings))
const categoryOptions = computed(() => [
  { value: '', label: 'All' },
  ...facets.value.categories.map(c => ({
    value: c,
    label: c.charAt(0).toUpperCase() + c.slice(1),
  })),
])

const filteredBase = computed(() => filterFindingsTriage(props.findings, {
  severity: filterSeverity.value,
  evidenceStrength: filterEvidence.value,
  category: filterCategory.value,
  sortBy: sortBy.value,
}))

const counts = computed(() => queueCounts(filteredBase.value, triageState.value))

const displayFindings = computed(() =>
  filterByQueue(filteredBase.value, triageState.value, { queue: activeQueue.value }))

const dashboard = computed(() =>
  analysisDashboard(props.findings, { qualityWarnings: props.qualityWarnings }))

const displayRows = computed(() =>
  groupFindingsByIncident(displayFindings.value, dashboard.value.clusters || [], {
    group: groupIncidents.value,
  }))

const selectedId = ref('')

function clusterPrefix(f) {
  const id = String(f?.id || '')
  const title = String(f?.title || '')
  for (const inc of dashboard.value.clusters || []) {
    if ((inc.finding_ids || []).includes(id) && id) return `[${inc.id}] `
    if ((inc.findings || []).includes(title) && title) return `[${inc.id}] `
  }
  return ''
}

function severityGlyph(f) {
  const sev = String(f?.severity || '').toLowerCase()
  if (sev === 'error') return `${SEMANTIC_GLYPHS.error} `
  if (sev === 'warning' || sev === 'warn') return `${SEMANTIC_GLYPHS.warning} `
  if (f?.id === 'load_balance_ok') return `${SEMANTIC_GLYPHS.improved} `
  return ''
}

function dismissReason(f) {
  const fid = String(f?.id || '').trim()
  if (!fid) return ''
  return triageState.value.dismissed?.[fid] || ''
}

function toggleIncident(cid) {
  const id = String(cid || '')
  if (!id) return
  collapsedIncidents.value = {
    ...collapsedIncidents.value,
    [id]: !collapsedIncidents.value[id],
  }
}

const askAiOpen = ref(false)
const moreOpen = ref(false)
const askAiBtn = ref(null)
const moreBtn = ref(null)
const askAiMenuEl = ref(null)
const moreMenuEl = ref(null)
const askAiMenuStyle = ref({})
const moreMenuStyle = ref({})
const explainLevels = EXPLAIN_LEVELS.map(id => ({
  id,
  label: `${id.charAt(0).toUpperCase()}${id.slice(1)}`,
}))

const selectedFinding = computed(() => {
  const id = selectedId.value
  const items = displayFindings.value
  if (!id) return items[0] || null
  return items.find(f => (f.id || '') === id) || items[0] || null
})

watch(displayFindings, (items) => {
  const id = selectedId.value
  if (id && items.some(f => (f.id || '') === id)) return
  selectedId.value = items[0]?.id || ''
})

const selectedStatus = computed(() =>
  findingQueueStatus(selectedFinding.value?.id || '', triageState.value))
const isDone = computed(() =>
  (triageState.value.reviewed || []).includes(String(selectedFinding.value?.id || '')))
const isDismissed = computed(() => selectedStatus.value === QUEUE_DISMISSED)
const isInCase = computed(() =>
  (triageState.value.case || []).includes(String(selectedFinding.value?.id || '')))

function toggleDone() {
  const f = selectedFinding.value
  if (!f?.id) return
  const act = isDone.value ? 'unreviewed' : 'done'
  commitTriage(applyTriageAction(triageState.value, f.id, act))
}

function toggleDismiss() {
  const f = selectedFinding.value
  if (!f?.id) return
  if (isDismissed.value) {
    commitTriage(applyTriageAction(triageState.value, f.id, 'restore'))
    return
  }
  const reason = window.prompt('Dismiss reason (short):', 'Not relevant')
  if (reason == null) return
  commitTriage(applyTriageAction(triageState.value, f.id, 'dismiss', {
    reason: String(reason).trim() || 'Dismissed',
  }))
}

function addToCase() {
  const f = selectedFinding.value
  if (!f?.id || isInCase.value) return
  commitTriage(applyTriageAction(triageState.value, f.id, 'case'))
  emit('add-to-case', f)
}

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

const investigatePreviewText = computed(() => {
  const f = selectedFinding.value
  if (!f) return ''
  const scope = bestFindingScope(f, props.uxEvents, props.timeMin, props.timeMax)
  const sid = investigateSectionId.value || ''
  return formatInvestigatePreview(f, {
    scope,
    sectionId: sid,
    sectionLabel: sid,
    currentLimit: props.currentLimit,
    currentLo: props.currentCursorLo,
    currentHi: props.currentCursorHi,
  })
})

function beginInvestigate() {
  if (!investigateSectionId.value || !selectedFinding.value) return
  investigatePending.value = true
}

function cancelInvestigate() {
  investigatePending.value = false
}

function confirmInvestigate() {
  const f = selectedFinding.value
  const sectionId = investigateSectionId.value
  if (!f || !sectionId) return
  investigatePending.value = false
  emit('investigate', { finding: f, sectionId })
}

watch(selectedId, () => { investigatePending.value = false })

function investigate() {
  beginInvestigate()
}

function placeMenu(btn, styleRef) {
  if (!btn) return
  const r = btn.getBoundingClientRect()
  const gap = 4
  const spaceAbove = r.top
  const spaceBelow = window.innerHeight - r.bottom
  if (spaceAbove >= spaceBelow) {
    styleRef.value = {
      position: 'fixed',
      left: `${Math.max(8, r.left)}px`,
      bottom: `${window.innerHeight - r.top + gap}px`,
      zIndex: 10100,
    }
  } else {
    styleRef.value = {
      position: 'fixed',
      left: `${Math.max(8, r.left)}px`,
      top: `${r.bottom + gap}px`,
      zIndex: 10100,
    }
  }
}

function toggleAskAi() {
  moreOpen.value = false
  askAiOpen.value = !askAiOpen.value
  if (askAiOpen.value) nextTick(() => placeMenu(askAiBtn.value, askAiMenuStyle))
}

function toggleMore() {
  askAiOpen.value = false
  moreOpen.value = !moreOpen.value
  if (moreOpen.value) nextTick(() => placeMenu(moreBtn.value, moreMenuStyle))
}

function onDocMouseDown(ev) {
  const t = ev.target
  if (askAiOpen.value) {
    if (!askAiBtn.value?.contains(t) && !askAiMenuEl.value?.contains(t)) askAiOpen.value = false
  }
  if (moreOpen.value) {
    if (!moreBtn.value?.contains(t) && !moreMenuEl.value?.contains(t)) moreOpen.value = false
  }
}

function onDocKeyDown(ev) {
  if (ev.key !== 'Escape') return
  if (askAiOpen.value || moreOpen.value) {
    askAiOpen.value = false
    moreOpen.value = false
    ev.preventDefault()
  }
}

onMounted(() => {
  document.addEventListener('mousedown', onDocMouseDown)
  document.addEventListener('keydown', onDocKeyDown)
})

onUnmounted(() => {
  document.removeEventListener('mousedown', onDocMouseDown)
  document.removeEventListener('keydown', onDocKeyDown)
})

function askAi(payload) {
  askAiOpen.value = false
  emit('query-ai', payload)
}

function explainFinding(level) {
  askAiOpen.value = false
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
  const text = formatAnalysisFindingsText(props.findings, props.scopeLabel, {
    triageState: triageState.value,
  })
  const blob = new Blob([text], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `analysis-findings-${_stamp()}.txt`
  a.click()
  URL.revokeObjectURL(url)
}

function moreAction(kind) {
  moreOpen.value = false
  if (kind === 'save-recipe') emit('save-recipe')
  else if (kind === 'save-story') emit('save-story')
  else if (kind === 'save-text') saveAsText()
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
  max-height: min(92vh, 900px);
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

.analysis-dialog :deep(.analysis-context-strip) {
  flex: 0 0 auto;
}

.analysis-title {
  font-size: 15px;
  font-weight: 700;
}

.analysis-close {
  /* Match .trace-tab-close */
  display: inline-flex;
  align-items: center;
  justify-content: center;
  appearance: none;
  border: none;
  background: transparent;
  color: var(--fg);
  width: 16px;
  height: 16px;
  border-radius: 3px;
  font-size: 14px;
  line-height: 1;
  padding: 0;
  cursor: pointer;
  opacity: 0.65;
  flex: 0 0 auto;
}
.analysis-close:hover {
  opacity: 1;
  background: rgba(127, 127, 127, 0.2);
}

.analysis-queue {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 8px 12px 0;
  flex: 0 0 auto;
}

.analysis-queue-btn {
  border: 1px solid var(--border);
  background: transparent;
  color: var(--fg-dim);
  border-radius: 12px;
  padding: 4px 10px;
  font-size: 11px;
  cursor: pointer;
}

.analysis-queue-btn.active {
  color: var(--fg);
  border-color: var(--accent);
  background: color-mix(in srgb, var(--accent) 18%, transparent);
}

.analysis-queue-btn:hover:not(.active) {
  color: var(--fg);
  background: var(--tb-btn-hover);
}

.analysis-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 10px;
  padding: 8px 12px 10px;
  font-size: 11px;
  flex: 0 0 auto;
  align-items: center;
}
.analysis-filter-field {
  display: flex;
  align-items: center;
  gap: 4px;
  color: var(--fg-dim);
}
.analysis-filter-label {
  flex: 0 0 auto;
  color: var(--fg-dim);
  font-size: 11px;
}
/* Match Toolbar DomSelect (tb-zoom-preset): compact 24px chrome. */
.analysis-filter-select {
  width: auto;
  min-width: 88px;
  max-width: 120px;
  height: 24px;
  margin: 0;
  padding: 1px 4px;
  border: 1px solid var(--border);
  border-radius: 3px;
  background: var(--panel-bg, var(--bg));
  color: var(--fg);
  font-size: 11px;
  box-sizing: border-box;
}
.analysis-filters :deep(.dom-select-trigger) {
  min-height: 0;
  height: 100%;
  gap: 4px;
}
.analysis-filters :deep(.dom-select-chevron) {
  width: 10px;
  height: 10px;
}
.analysis-filter-select-sort {
  min-width: 118px;
  max-width: 148px;
}
.analysis-filter-check {
  display: flex;
  align-items: center;
  gap: 4px;
  color: var(--fg-dim);
  font-size: 11px;
  cursor: pointer;
  user-select: none;
}
.finding-strength {
  font-size: 10px;
  opacity: 0.85;
  font-weight: 600;
}
.analysis-incident-header {
  list-style: none;
  margin: 8px 0 4px;
  padding: 6px 10px;
  border-radius: 6px;
  background: color-mix(in srgb, var(--accent) 12%, transparent);
  border: 1px solid color-mix(in srgb, var(--accent) 35%, transparent);
  color: var(--fg);
  font-weight: 600;
  font-size: 12px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
}
.analysis-incident-header .incident-toggle {
  width: 1em;
  opacity: 0.8;
}
.analysis-incident-header .incident-count {
  margin-left: auto;
  font-weight: 500;
  color: var(--fg-dim);
  font-size: 11px;
}
.analysis-list li.in-incident {
  margin-left: 10px;
  border-left: 2px solid color-mix(in srgb, var(--accent) 40%, transparent);
}
.analysis-investigate-preview {
  flex: 1 1 100%;
  margin: 0 0 4px;
  padding: 8px 10px;
  font: inherit;
  font-size: 11px;
  white-space: pre-wrap;
  color: var(--fg);
  border: 1px solid var(--border);
  border-radius: 6px;
  background: color-mix(in srgb, var(--accent) 8%, transparent);
}
.finding-check-next {
  font-size: 11px;
  opacity: 0.9;
  margin-top: 4px;
}
.finding-dismiss-reason {
  margin-top: 4px;
  font-size: 11px;
  color: var(--fg-dim);
  font-style: italic;
}
.analysis-note {
  margin: 0;
  padding: 8px 16px 10px;
  font-size: 12px;
  line-height: 1.4;
  color: var(--fg-dim);
  flex: 0 0 auto;
}

/* Desktop QLabel overview: bordered strip that grows with content (no 28vh clip). */
.analysis-overview {
  margin: 0 16px 8px;
  padding: 8px 10px;
  font: inherit;
  font-size: 12px;
  line-height: 1.4;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--fg);
  border: 1px solid var(--border);
  border-radius: 6px;
  background: color-mix(in srgb, var(--accent) 8%, transparent);
  flex: 0 0 auto;
  overflow: visible;
}

.analysis-body {
  flex: 1 1 auto;
  overflow: auto;
  padding: 8px 16px 14px;
  min-height: 0;
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
  background: color-mix(in srgb, var(--accent) 22%, transparent);
  outline: 1px solid color-mix(in srgb, var(--accent) 45%, transparent);
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
  font-size: var(--type-min, 11px);
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

.analysis-triage {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 0 14px 8px;
  flex: 0 0 auto;
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
  flex: 0 0 auto;
}

.analysis-footer-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.analysis-footer-spacer {
  flex: 1 1 auto;
}

.analysis-menu-wrap {
  position: relative;
  flex: 0 0 auto;
}

.analysis-popup-menu {
  min-width: 180px;
  padding: 4px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--panel-bg);
  color: var(--fg);
  box-shadow: 0 8px 20px rgba(0, 0, 0, 0.35);
  z-index: 12100;
}

.analysis-popup-group {
  border-top: 1px solid var(--border);
  border-bottom: 1px solid var(--border);
  margin: 4px 0;
  padding: 4px 0;
}

.analysis-popup-label {
  padding: 4px 10px;
  font-size: 10px;
  letter-spacing: 0.4px;
  color: var(--fg-dim);
  text-transform: uppercase;
}

.analysis-popup-item {
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

.analysis-popup-item:hover {
  background: var(--tb-btn-hover);
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
