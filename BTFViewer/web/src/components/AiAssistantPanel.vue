<template>
  <div class="ai-panel">
    <div class="ai-header">
      <span class="ai-title">AI Assistant</span>
      <button
        type="button"
        class="ai-auth-chip"
        :title="'Open Settings → AI to sign in or change the API key'"
        @click="emit('openSettings')"
      >
        {{ authChipLabel }}
      </button>
      <button
        type="button"
        class="ai-auth-chip"
        data-testid="ai-privacy-chip"
        :title="privacyChipTitle"
        @click="emit('openSettings')"
      >
        {{ privacyChipLabel }}
      </button>
    </div>
    <div class="ai-header-actions">
      <button
        type="button"
        class="ai-link-btn"
        title="Clear the conversation log"
        @click="clear"
      >
        Clear
      </button>
      <button
        type="button"
        class="ai-link-btn"
        title="Preferred language for assistant replies"
        @click="langOpen = true"
      >
        Language…
      </button>
      <button
        type="button"
        class="ai-link-btn"
        title="Configure the AI preset, endpoint, and model"
        @click="emit('openSettings')"
      >
        Settings…
      </button>
    </div>

    <div
      v-if="langOpen"
      class="ai-lang-backdrop"
      @click.self="langOpen = false"
    >
      <div
        class="ai-lang-dialog"
        role="dialog"
        aria-label="AI response language"
      >
        <h3>AI response language</h3>
        <p>Preferred language for assistant replies:</p>
        <select
          v-model="langDraft"
          class="ai-lang-select"
        >
          <option
            v-for="lang in languages"
            :key="lang"
            :value="lang"
          >
            {{ lang }}
          </option>
        </select>
        <div class="ai-lang-actions">
          <button
            type="button"
            class="ai-link-btn"
            @click="langOpen = false"
          >
            Cancel
          </button>
          <button
            type="button"
            class="ai-btn primary"
            @click="applyLanguage"
          >
            OK
          </button>
        </div>
      </div>
    </div>

    <div
      v-if="comparePickOpen"
      class="ai-lang-backdrop"
      @click.self="comparePickOpen = false"
    >
      <div
        class="ai-lang-dialog"
        role="dialog"
        aria-label="Choose traces to compare"
      >
        <h3>Trace Compare</h3>
        <p>Choose two open traces to compare:</p>
        <label class="ai-pick-label">Trace A</label>
        <select
          v-model="comparePickA"
          class="ai-lang-select"
        >
          <option
            v-for="t in loadedTabs"
            :key="`a-${t.id}`"
            :value="t.id"
          >
            {{ t.name }}
          </option>
        </select>
        <label class="ai-pick-label">Trace B</label>
        <select
          v-model="comparePickB"
          class="ai-lang-select"
        >
          <option
            v-for="t in loadedTabs"
            :key="`b-${t.id}`"
            :value="t.id"
          >
            {{ t.name }}
          </option>
        </select>
        <p
          v-if="comparePickSame"
          class="ai-pick-error"
        >
          Choose two different traces.
        </p>
        <div class="ai-lang-actions">
          <button
            type="button"
            class="ai-link-btn"
            @click="comparePickOpen = false"
          >
            Cancel
          </button>
          <button
            type="button"
            class="ai-btn primary"
            :disabled="!comparePickReady"
            @click="confirmComparePick"
          >
            Compare
          </button>
        </div>
      </div>
    </div>

    <div
      v-if="mermaidZoom"
      class="ai-mermaid-overlay"
      role="dialog"
      aria-label="Diagram"
      @click.self="closeMermaidZoom"
    >
      <div class="ai-mermaid-zoom-dialog">
        <div class="ai-mermaid-zoom-head">
          <span>Scroll to zoom. Click a task/core in the figure or a name below.</span>
          <button
            type="button"
            class="ai-link-btn"
            @click="closeMermaidZoom"
          >
            Close
          </button>
        </div>
        <div
          class="ai-mermaid-zoom-body"
          :style="{ '--mm-scale': mermaidZoom.scale }"
          v-html="mermaidZoom.html"
          @click="onMsgClick"
          @wheel.prevent="onMermaidZoomWheel"
        />
        <p
          v-if="mermaidZoom.links"
          class="ai-mermaid-zoom-links"
          v-html="mermaidZoom.links"
          @click="onMsgClick"
        />
      </div>
    </div>

    <div class="ai-split">
    <div class="ai-split-top">
    <div
      ref="logRef"
      class="ai-log"
      @contextmenu.prevent="onLogContextMenu"
    >
      <div
        v-if="!messages.length"
        class="ai-empty"
      >
        Conversation appears here…
        <span class="ai-empty-hint">
          Uses Analysis Findings for the current Statistics scope.
          Configure the endpoint in Settings → AI.
          Prefer <code>npm run dev</code> / <code>preview</code> (proxies);
          for <code>file://</code> set <code>OLLAMA_ORIGINS</code>.
        </span>
      </div>
      <div
        v-for="(m, i) in messages"
        :key="i"
        class="ai-msg"
        :class="m.role"
      >
        <div class="ai-msg-role">
          {{ aiRoleLabel(m.role, responseLanguage) }}
        </div>
        <div
          class="ai-msg-body"
          :class="{ markdown: m.role === 'assistant' || m.role === 'evidence' }"
          v-html="formatMessage(m.role, m.content)"
          @click="onMsgClick"
        />
        <div
          v-if="m.tools && m.tools.length"
          class="ai-tool-card"
        >
          <template
            v-for="t in m.tools"
            :key="t.id"
          >
            <p>
              ⚡ {{ toolLabel(t) }}
              <span class="ai-tool-st">({{ t.status || 'pending' }})</span>
            </p>
            <p
              v-if="t.status === 'failed' && (t.result || t.error)"
              class="ai-tool-fail"
            >
              {{ t.result || t.error }}
            </p>
          </template>
          <div
            v-if="batchPending(m)"
            class="ai-tool-actions"
          >
            <button
              type="button"
              class="ai-btn primary"
              @click="applyBatch(m.batchId)"
            >
              Apply
            </button>
            <button
              type="button"
              class="ai-link-btn"
              @click="skipBatch(m.batchId)"
            >
              Skip
            </button>
          </div>
          <button
            v-else-if="batchApplied(m)"
            type="button"
            class="ai-link-btn"
            @click="undoBatch(m.batchId)"
          >
            Undo
          </button>
        </div>
      </div>
    </div>

    <div
      v-if="investigationPlan"
      class="ai-plan-status"
      :title="planStatusText"
    >
      {{ planStatusText }}
    </div>

    <div class="ai-modes">
      <button
        v-for="mid in investigationModes"
        :key="mid"
        type="button"
        class="ai-tpl-btn"
        :title="investigationModePrompt(mid)"
        :disabled="busy || !aiEnabled"
        @click="onInvestigationMode(mid)"
      >
        {{ investigationModeLabel(mid) }}
      </button>
    </div>

    <div class="ai-templates">
      <button
        v-for="t in primaryTemplates"
        :key="t.id"
        type="button"
        class="ai-tpl-btn"
        :class="{ gray: templateDisabled(t) }"
        :title="templateTitle(t)"
        :disabled="busy || !aiEnabled || templateDisabled(t)"
        @click="onTemplate(t)"
      >
        {{ t.label }}
      </button>
      <div class="ai-more-wrap">
        <button
          ref="moreBtnEl"
          type="button"
          class="ai-tpl-btn"
          title="Uses Analysis Findings for the current Statistics scope. Configure the endpoint in Settings → AI."
          @click="toggleMore"
        >
          More templates…
        </button>
        <Teleport to="body">
          <div
            v-if="moreOpen"
            ref="moreMenuEl"
            class="ai-more-menu ai-more-menu-wide"
            :style="moreMenuStyle"
          >
            <div
              v-for="group in templateMenuGroups"
              :key="group.label"
              class="ai-more-col"
            >
              <div class="ai-more-heading">
                {{ group.label }}
              </div>
              <button
                v-for="t in group.items"
                :key="t.id"
                type="button"
                class="ai-more-item"
                :class="{ gray: templateDisabled(t) }"
                :title="templateTitle(t)"
                :disabled="busy || !aiEnabled || templateDisabled(t)"
                @click="onTemplate(t); moreOpen = false"
              >
                {{ t.label }}
              </button>
            </div>
            <div class="ai-more-col">
              <div class="ai-more-heading">
                Investigations
              </div>
              <button
                v-for="tpl in investigationTemplates"
                :key="tpl.id"
                type="button"
                class="ai-more-item"
                :title="investigationTemplatePrompt(tpl)"
                :disabled="busy || !aiEnabled"
                @click="onInvestigationTemplate(tpl); moreOpen = false"
              >
                {{ tpl.label }}
              </button>
              <button
                type="button"
                class="ai-more-item"
                title="Save the current investigation steps as a reusable template"
                :disabled="busy"
                @click="onSaveInvestigationTemplate(); moreOpen = false"
              >
                Save as template…
              </button>
              <div class="ai-more-heading">
                Knowledge
              </div>
              <button
                type="button"
                class="ai-more-item"
                title="Store this finding as local historical knowledge"
                :disabled="busy"
                @click="onSaveUserKnowledge(); moreOpen = false"
              >
                Save current finding…
              </button>
            </div>
          </div>
        </Teleport>
      </div>
    </div>

    <div
      v-if="toolBarFallback"
      class="ai-tool-bar"
    >
      <button
        v-if="pendingBatchId"
        type="button"
        class="ai-btn primary"
        title="Run the pending viewer tools from the last reply"
        @click="applyBatch(pendingBatchId)"
      >
        Apply GUI actions
      </button>
      <button
        v-if="pendingBatchId"
        type="button"
        class="ai-link-btn"
        @click="skipBatch(pendingBatchId)"
      >
        Skip
      </button>
      <button
        v-if="appliedBatchId && !pendingBatchId"
        type="button"
        class="ai-link-btn"
        @click="undoBatch(appliedBatchId)"
      >
        Undo last actions
      </button>
    </div>
    </div>

    <div
      class="ai-split-handle"
      title="Drag to resize the input box"
      @mousedown.prevent="onSplitPointerDown"
    />

    <div
      class="ai-split-bottom"
      :style="{ height: `${splitBottom}px` }"
    >
    <div class="ai-composer">
      <textarea
        v-model="draft"
        class="ai-input"
        rows="3"
        placeholder="Ask about this trace… (Ctrl/Cmd+Enter to send)"
        :disabled="busy || !aiEnabled"
        @keydown.meta.enter.prevent="send()"
        @keydown.ctrl.enter.prevent="send()"
      />
      <div class="ai-composer-icons">
        <button
          type="button"
          class="ai-icon-btn primary"
          :title="busy ? 'Stop the current query' : 'Send the question (Ctrl/Cmd+Enter)'"
          :aria-label="busy ? 'Stop' : 'Send'"
          :disabled="!busy && (!aiEnabled || !draft.trim())"
          @click="onComposerAction"
        >
          <svg
            v-if="busy"
            viewBox="0 0 16 16"
            width="14"
            height="14"
            fill="currentColor"
            aria-hidden="true"
          >
            <path d="M5 5h6v6H5z" />
          </svg>
          <svg
            v-else
            viewBox="0 0 16 16"
            width="14"
            height="14"
            fill="currentColor"
            aria-hidden="true"
          >
            <path
              fill-rule="evenodd"
              d="M8 2.5l4.5 5H9.25v6.5h-2.5V7.5H3.5L8 2.5z"
            />
          </svg>
        </button>
      </div>
    </div>
    </div>
    </div>

    <div
      v-if="logMenu.visible"
      class="ai-ctx-menu"
      :style="{ left: `${logMenu.x}px`, top: `${logMenu.y}px` }"
      @mousedown.stop
    >
      <button
        type="button"
        class="ai-ctx-item"
        :disabled="!logMenu.hasSelection"
        @click="copySelection"
      >
        Copy
      </button>
      <button
        type="button"
        class="ai-ctx-item"
        :disabled="!messages.length"
        @click="copyConversation"
      >
        Copy conversation
      </button>
      <div class="ai-ctx-sep" />
      <button
        type="button"
        class="ai-ctx-item"
        :disabled="!messages.length"
        @click="saveConversationAs('md')"
      >
        Save As Markdown…
      </button>
      <button
        type="button"
        class="ai-ctx-item"
        :disabled="!messages.length"
        @click="saveConversationAs('txt')"
      >
        Save As Text…
      </button>
      <button
        type="button"
        class="ai-ctx-item"
        :disabled="!messages.length"
        @click="saveConversationAs('html')"
      >
        Save As HTML…
      </button>
    </div>

    <div
      class="ai-status"
      :class="{ error: !!error }"
    >
      {{ statusText }}
    </div>
    <div
      class="ai-usage-bar"
      :title="usageTip"
    >
      {{ usageText }}
    </div>
    <div
      v-if="showAuthCta"
      class="ai-auth-cta"
    >
      <button
        v-if="showSignInCta"
        type="button"
        class="ai-link-btn"
        @click="onSignInCta"
      >
        {{ signInLabel }}
      </button>
      <button
        type="button"
        class="ai-link-btn"
        @click="emit('openSettings')"
      >
        Settings…
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import {
  AI_COMPARE_TEMPLATE_ID,
  AI_RESPONSE_LANGUAGES,
  AI_SMP_ONLY_TEMPLATE_IDS,
  AI_TEMPLATE_MENU_GROUPS,
  AI_TEMPLATE_PRIMARY_IDS,
  AI_TEMPLATE_QUESTIONS,
  DEFAULT_AI_PRESET,
  DEFAULT_AI_RESPONSE_LANGUAGE,
  aiAuthStatus,
  aiChatCompletion,
  aiPresetInfo,
  aiPresetSignInLabel,
  aiPresetSignInUrl,
  buildAiSystemPrompt,
  buildAiUserMessage,
  cursorRegionBounds,
  extractJumpTimes,
  isLocalAiHost,
  normalizeAiContext,
  resolveAiSettings,
} from '../utils/ollamaClient.js'
import {
  AI_TOOL_EXPORT_INVESTIGATION,
  aiViewerTools,
  buildAiReportCsv,
  buildAiReportHtml,
  canonicalAssistantToolMessage,
  isExportTool,
  isQueryTool,
  maxToolRounds,
  parseAiAutoApply,
  parseBtfHighlightHref,
  parseBtfJumpHref,
  parseBtfRangeHref,
  summariseToolCall,
  toolBatchAutoRuns,
  toolResultMessage,
  validateToolCall,
  btfJumpHref,
} from '../utils/aiTools.js'
import {
  INVESTIGATION_MODE_LABELS,
  INVESTIGATION_MODES,
  accumulateCost,
  buildValidationCatalog,
  builtinInvestigationTemplates,
  chatUsageFromResponse,
  applyCloudPrivacy,
  applyExperimentToHypotheses,
  classifyTracePrivacy,
  compareHypotheses,
  dumpUserHistoricalKnowledge,
  dumpUserInvestigationTemplates,
  emptyCostMeter,
  formatCostMeter,
  formatCostStatus,
  clampAiSplitBottom,
  formatConfidenceEvolution,
  formatPrivacyChip,
  historicalKnowledgeForFinding,
  investigationModePlan,
  interpretInvestigationQuery,
  investigationModePrompt,
  interpretedRunPrompt,
  investigationTemplatePrompt,
  shouldConfirmInterpretedQuery,
  newUserHistoricalEntry,
  newUserInvestigationTemplate,
  parseUserHistoricalKnowledge,
  parseUserInvestigationTemplates,
  toggleInterpretedScope,
  setHypothesisStatus,
  updateCaseFromTool,
  validateAiResponse,
  VALIDATE_EXPERIMENT_PROMPT,
} from '../utils/aiCase.js'
import {
  buildInvestigationPackage,
  completeInvestigationPlan,
  defaultInvestigationPlan,
  EVIDENCE_PANEL_TOOLS,
  extractEvidencePanelPayload,
  formatEvidencePanelMarkdown,
  formatInvestigationPlanStatus,
  isAgentTemplate,
  markPlanStepsFromTools,
  parseBtfExpHref,
  parseBtfHypHref,
  parseBtfScopeHref,
  parseBtfToolHref,
} from '../utils/aiInvestigation.js'
import {
  aiFileStamp,
  aiRoleLabel,
  formatAiConversationHtml,
  formatAiConversationMarkdown,
  formatAiConversationText,
  formatAiMessageHtml,
} from '../utils/aiMarkdown.js'
import {
  loadAiSplitBottom,
  loadAiUserHistoricalKnowledge,
  loadAiUserInvestigationTemplates,
  saveAiSplitBottom,
  saveAiUserHistoricalKnowledge,
  saveAiUserInvestigationTemplates,
} from '../utils/settingsStore.js'

const props = defineProps({
  aiEnabled: { type: Boolean, default: true },
  aiPreset: { type: String, default: DEFAULT_AI_PRESET },
  /** { [presetId]: { baseUrl, model, apiKey } } */
  aiPresets: { type: Object, default: () => ({}) },
  responseLanguage: { type: String, default: DEFAULT_AI_RESPONSE_LANGUAGE },
  aiAutoApply: { type: Boolean, default: false },
  aiRedactTaskNames: { type: Boolean, default: false },
  aiTraceSensitive: { type: Boolean, default: false },
  /** () => Promise|{ findingsText, span, cores, scope } */
  getContext: { type: Function, required: true },
  /** () => [{ id, name }, ...] loaded BTF tabs */
  getLoadedTabs: { type: Function, default: null },
  /** (idA, idB) => Promise|{ findingsText, span, cores, scope } */
  buildCompareContext: { type: Function, default: null },
  /** (tools) => result[] */
  executeTools: { type: Function, default: null },
  undoTools: { type: Function, default: null },
  /** () => { file, span, cores, scope, findings, cursors, highlight, view_mode, orientation, annotations } */
  getGuiState: { type: Function, default: null },
})

const emit = defineEmits([
  'openSettings', 'jump', 'range', 'highlight', 'update:responseLanguage', 'statusMessage',
])

const templates = AI_TEMPLATE_QUESTIONS
const primaryTemplates = computed(() =>
  AI_TEMPLATE_PRIMARY_IDS
    .map(id => templates.find(t => t.id === id))
    .filter(Boolean),
)
const templateMenuGroups = computed(() =>
  AI_TEMPLATE_MENU_GROUPS.map(g => ({
    label: g.label,
    items: g.ids.map(id => templates.find(t => t.id === id)).filter(Boolean),
  })),
)
const investigationModes = INVESTIGATION_MODES
const userInvestigationTemplates = ref(loadAiUserInvestigationTemplates())
const investigationTemplates = computed(() => [
  ...builtinInvestigationTemplates(),
  ...userInvestigationTemplates.value,
])
function investigationModeLabel(mid) {
  return INVESTIGATION_MODE_LABELS[mid] || mid
}
// A language imported from JSON need not be one of the built-in choices.
const languages = computed(() => {
  const cur = String(props.responseLanguage || '').trim()
  if (!cur || AI_RESPONSE_LANGUAGES.includes(cur)) return AI_RESPONSE_LANGUAGES
  return [...AI_RESPONSE_LANGUAGES, cur]
})
const draft = ref('')
const messages = ref([])
const busy = ref(false)
const error = ref('')
const status = ref('')
const logRef = ref(null)
const langOpen = ref(false)
const moreOpen = ref(false)
const moreBtnEl = ref(null)
const moreMenuEl = ref(null)
const moreMenuStyle = ref({})
const langDraft = ref(props.responseLanguage || DEFAULT_AI_RESPONSE_LANGUAGE)
const loadedTabs = ref([])
const logMenu = reactive({ visible: false, x: 0, y: 0, hasSelection: false })
const comparePickOpen = ref(false)
const comparePickA = ref(null)
const comparePickB = ref(null)
const pendingComparePrompt = ref('')
const mermaidZoom = ref(null)
let abortCtrl = null
let chatMessages = []
let toolRound = 0
let batchSeq = 0
let activeTemplateId = ''
let skipInterpretOnce = false
const investigationPlan = ref(null)
let evidencePayload = null
let interpretedQuery = null

const planStatusText = computed(() =>
  formatInvestigationPlanStatus(investigationPlan.value, props.responseLanguage))

function syncEvidenceLogEntry(data, language = props.responseLanguage) {
  const text = formatEvidencePanelMarkdown(data, language)
  if (!text) return
  messages.value = messages.value.filter(m => m.role !== 'evidence')
  messages.value.push({ role: 'evidence', content: text })
  scrollLog()
}

function removeEvidenceLogEntry() {
  const before = messages.value.length
  messages.value = messages.value.filter(m => m.role !== 'evidence')
  if (messages.value.length !== before) scrollLog()
}

function updateEvidenceFromToolResult(name, res) {
  const payload = extractEvidencePanelPayload(name, res)
  if (!payload) return
  const prev = evidencePayload || {}
  const prevCase = prev.investigation_case
  if (prevCase) {
    const caseObj = updateCaseFromTool(prevCase, name, res)
    payload.investigation_case = caseObj
    payload.tool_reasons = caseObj.tool_reasons || []
    payload.confidence_evolution = formatConfidenceEvolution(caseObj.confidence_history)
  }
  if (prev.validation && !payload.validation) payload.validation = prev.validation
  if (prev.cost && !payload.cost) payload.cost = prev.cost
  if (payload.interpreted) interpretedQuery = payload.interpreted
  else if (prev.interpreted && !payload.interpreted) payload.interpreted = prev.interpreted
  if (payload.experiment) {
    const hyps = payload.hypotheses_managed || payload.hypotheses
      || prev.hypotheses_managed || prev.hypotheses || []
    const updated = applyExperimentToHypotheses(hyps, payload.experiment)
    if (updated.length) {
      payload.hypotheses_managed = updated
      payload.hypotheses = updated
    }
  }
  if (payload.finding && typeof payload.finding === 'object') {
    payload.historical_knowledge = historicalKnowledgeForFinding(payload.finding, {
      current: payload.finding,
      userCatalog: loadAiUserHistoricalKnowledge(),
    })
  }
  evidencePayload = payload
  syncEvidenceLogEntry(payload)
}

function pinEvidenceLogEntry() {
  if (evidencePayload) syncEvidenceLogEntry(evidencePayload)
}

function attachResponseValidation(text) {
  const src = String(text || '').trim()
  if (!src) return
  let ctx = {}
  try {
    ctx = normalizeAiContext(props.getContext?.() || {})
  } catch {
    ctx = {}
  }
  const bounds = cursorRegionBounds(ctx.cursors)
  const catalog = buildValidationCatalog({
    findingsText: String(ctx.findings_text || ctx.findingsText || ''),
    evidence: evidencePayload?.evidence,
    cursorLo: bounds ? bounds.lo : null,
    cursorHi: bounds ? bounds.hi : null,
  })
  const report = validateAiResponse(src, catalog)
  evidencePayload = {
    ...(evidencePayload || {}),
    validation: report,
    cost: formatCostMeter(costMeter.value),
  }
}

function setInvestigationPlan(plan) {
  investigationPlan.value = plan || null
}

function advanceInvestigationPlan(toolNames) {
  if (!investigationPlan.value) return
  investigationPlan.value = markPlanStepsFromTools(investigationPlan.value, toolNames)
}

function finishInvestigationPlan() {
  if (!investigationPlan.value) return
  investigationPlan.value = completeInvestigationPlan(investigationPlan.value)
}

function toolLabel(t) {
  return summariseToolCall(t.name, t.arguments || {})
}

function batchPending(m) {
  return m.batchId && (m.tools || []).some(t => (t.status || 'pending') === 'pending')
}

function batchApplied(m) {
  return m.batchId && (m.tools || []).some(t => t.status === 'applied')
}

watch(() => props.responseLanguage, (v) => {
  const lang = v || DEFAULT_AI_RESPONSE_LANGUAGE
  langDraft.value = lang
  if (evidencePayload) syncEvidenceLogEntry(evidencePayload, lang)
})

watch(langOpen, (open) => {
  if (open) langDraft.value = props.responseLanguage || DEFAULT_AI_RESPONSE_LANGUAGE
})

function refreshLoadedTabs() {
  if (!props.getLoadedTabs) {
    loadedTabs.value = []
    return
  }
  try {
    const tabs = props.getLoadedTabs() || []
    loadedTabs.value = Array.isArray(tabs) ? tabs.filter(t => t && t.id != null) : []
  } catch {
    loadedTabs.value = []
  }
}

refreshLoadedTabs()

// Cores in the currently active trace — used to gray out SMP-only templates
// (Migration thrash, Core balance) for a single-core trace. `0` means
// unknown/no trace loaded, treated as "don't disable".
const currentCores = ref(0)

function refreshCoreAvailability() {
  if (typeof props.getContext !== 'function') {
    currentCores.value = 0
    return
  }
  try {
    const ctx = props.getContext()
    if (ctx && typeof ctx.then === 'function') return
    const n = Number(ctx?.cores)
    currentCores.value = Number.isFinite(n) ? n : 0
  } catch {
    currentCores.value = 0
  }
}

refreshCoreAvailability()

const smpEnabled = computed(() => currentCores.value === 0 || currentCores.value >= 2)

const compareEnabled = computed(() => loadedTabs.value.length >= 2)

const comparePickSame = computed(
  () => comparePickA.value != null && comparePickA.value === comparePickB.value,
)

const comparePickReady = computed(
  () => comparePickA.value != null
    && comparePickB.value != null
    && !comparePickSame.value,
)

const pendingBatchId = computed(() => {
  for (let i = messages.value.length - 1; i >= 0; i -= 1) {
    const m = messages.value[i]
    if (m?.tools?.some(t => (t.status || 'pending') === 'pending')) return m.batchId || ''
  }
  return ''
})

const appliedBatchId = computed(() => {
  for (let i = messages.value.length - 1; i >= 0; i -= 1) {
    const m = messages.value[i]
    if (m?.tools?.some(t => t.status === 'applied')) return m.batchId || ''
  }
  return ''
})

const toolBarFallback = computed(() => {
  const hasCards = messages.value.some(m => m.tools && m.tools.length)
  return !!(pendingBatchId.value || appliedBatchId.value) && !hasCards
})

function templateDisabled(t) {
  if (!t) return true
  if (t.id === AI_COMPARE_TEMPLATE_ID && !compareEnabled.value) return true
  if (AI_SMP_ONLY_TEMPLATE_IDS.has(t.id) && !smpEnabled.value) return true
  return false
}

function placeMoreMenu() {
  const btn = moreBtnEl.value
  if (!btn) return
  const r = btn.getBoundingClientRect()
  const gap = 4
  const spaceAbove = r.top
  const spaceBelow = window.innerHeight - r.bottom
  const maxH = Math.max(160, Math.min(560, (spaceAbove >= spaceBelow ? spaceAbove : spaceBelow) - 12))
  const right = Math.max(8, window.innerWidth - r.right)
  if (spaceAbove >= spaceBelow) {
    moreMenuStyle.value = {
      position: 'fixed',
      right: `${right}px`,
      bottom: `${window.innerHeight - r.top + gap}px`,
      maxHeight: `${maxH}px`,
    }
  } else {
    moreMenuStyle.value = {
      position: 'fixed',
      right: `${right}px`,
      top: `${r.bottom + gap}px`,
      maxHeight: `${maxH}px`,
    }
  }
}

function closeMore() {
  moreOpen.value = false
}

function toggleMore() {
  moreOpen.value = !moreOpen.value
  if (moreOpen.value) nextTick(placeMoreMenu)
}

function templateTitle(t) {
  if (t.id === AI_COMPARE_TEMPLATE_ID && !compareEnabled.value) {
    return 'Open at least two BTF tabs to use Trace Compare.'
  }
  if (AI_SMP_ONLY_TEMPLATE_IDS.has(t.id) && !smpEnabled.value) {
    return 'This trace has a single core — not applicable.'
  }
  return t.prompt
}

function applyLanguage() {
  const lang = String(langDraft.value || DEFAULT_AI_RESPONSE_LANGUAGE).trim()
    || DEFAULT_AI_RESPONSE_LANGUAGE
  emit('update:responseLanguage', lang)
  if (evidencePayload) syncEvidenceLogEntry(evidencePayload, lang)
  status.value = `Reply language: ${lang}`
  error.value = ''
  langOpen.value = false
}

const costMeter = ref(emptyCostMeter())
let costStarted = 0
const splitBottom = ref(loadAiSplitBottom())
let splitDrag = null

const statusText = computed(() => {
  return !props.aiEnabled
    ? 'AI is disabled in Settings → AI.'
    : (error.value || status.value)
})
const usageText = computed(() => formatCostStatus(costMeter.value))
const usageTip = computed(() => formatCostMeter(costMeter.value))

function onSplitPointerMove(ev) {
  if (!splitDrag) return
  splitBottom.value = clampAiSplitBottom(splitDrag.startH - (ev.clientY - splitDrag.startY))
}

function endSplitDrag() {
  if (!splitDrag) return
  window.removeEventListener('mousemove', onSplitPointerMove)
  window.removeEventListener('mouseup', endSplitDrag)
  splitDrag = null
  saveAiSplitBottom(splitBottom.value)
}

function onSplitPointerDown(ev) {
  splitDrag = { startY: ev.clientY, startH: splitBottom.value }
  window.addEventListener('mousemove', onSplitPointerMove)
  window.addEventListener('mouseup', endSplitDrag)
}

function setErrorStatus(msg) {
  const short = String(msg || '').split('\n')[0].slice(0, 200)
  error.value = short
  if (short) emit('statusMessage', { text: `AI: ${short}`, error: true })
}

const activeAi = computed(() => resolveAiSettings({
  aiPreset: props.aiPreset,
  aiPresets: props.aiPresets,
}))
const authState = computed(() => aiAuthStatus({
  authMode: activeAi.value.authMode,
  apiKey: activeAi.value.apiKey,
  baseUrl: activeAi.value.baseUrl,
  presetId: activeAi.value.preset,
}))
const authChipLabel = computed(() => (
  `${aiPresetInfo(activeAi.value.preset).label} · ${authState.value.label}`
))
const privacyState = computed(() => classifyTracePrivacy({
  endpointIsLocal: isLocalAiHost(activeAi.value.baseUrl),
  redactTaskNames: !!props.aiRedactTaskNames,
  sensitive: !!props.aiTraceSensitive,
}))
const privacyChipLabel = computed(() => formatPrivacyChip(privacyState.value))
const privacyChipTitle = computed(() => String(privacyState.value.note || ''))
const signInLabel = computed(() => aiPresetSignInLabel(activeAi.value.preset))
const signInUrl = computed(() => (
  aiPresetSignInUrl(activeAi.value.preset, activeAi.value.baseUrl)
))
const authForced = ref(false)
const showAuthCta = computed(() => authState.value.needsAuth || authForced.value)
const showSignInCta = computed(() => (
  authState.value.mode === 'browser' || Boolean(signInUrl.value)
))

function noteAuthError(msg) {
  const low = String(msg || '').toLowerCase()
  if (low.includes('http 401') || low.includes('http 403') || low.includes('api key required')) {
    authForced.value = true
  }
}

function onSignInCta() {
  const url = signInUrl.value
  if (url) {
    window.open(url, '_blank', 'noopener,noreferrer')
    status.value = `Opened ${url}. Paste the key or token in Settings → AI.`
    error.value = ''
  } else {
    status.value = 'This preset has no sign-in page. Paste a token in Settings → AI.'
  }
  emit('openSettings')
}

function formatMessage(role, text) {
  return formatAiMessageHtml(role, text)
}

function closeMermaidZoom() {
  mermaidZoom.value = null
}

function openMermaidZoom(fromEl) {
  const root = fromEl?.closest?.('.ai-mermaid') || fromEl
  const svgWrap = root.querySelector?.('.ai-mermaid-svg')
  const img = root.querySelector?.('.ai-mermaid-img')
  const links = root.querySelector?.('.ai-mermaid-links')
  let html = ''
  if (svgWrap) html = svgWrap.outerHTML
  else if (img) html = `<img src="${img.getAttribute('src') || ''}" alt="mermaid diagram">`
  if (!html) return
  mermaidZoom.value = { html, links: links ? links.innerHTML : '', scale: 1 }
}

function onMermaidZoomWheel(ev) {
  const cur = mermaidZoom.value
  if (!cur) return
  const factor = (ev.deltaY || 0) < 0 ? 1.15 : 1 / 1.15
  const scale = Math.max(0.5, Math.min(6, (Number(cur.scale) || 1) * factor))
  mermaidZoom.value = { ...cur, scale }
}

function onMsgClick(ev) {
  const hypA = ev.target?.closest?.('a[href^="btfhyp:"]')
  if (hypA) {
    ev.preventDefault()
    const parsed = parseBtfHypHref(hypA.getAttribute('href') || '')
    if (parsed.action) onHypothesisAction(parsed.action, parsed.hypId)
    return
  }
  const scopeA = ev.target?.closest?.('a[href^="btfscope:"]')
  if (scopeA) {
    ev.preventDefault()
    const parsed = parseBtfScopeHref(scopeA.getAttribute('href') || '')
    if (parsed.action) onScopeAction(parsed.action, parsed.key)
    return
  }
  const expA = ev.target?.closest?.('a[href^="btfexp:"]')
  if (expA) {
    ev.preventDefault()
    const parsed = parseBtfExpHref(expA.getAttribute('href') || '')
    if (parsed.action) onExperimentAction(parsed.action, parsed.key)
    return
  }
  const toolA = ev.target?.closest?.('a[href^="btftool:"]')
  if (toolA) {
    ev.preventDefault()
    const parsed = parseBtfToolHref(toolA.getAttribute('href') || '')
    if (parsed.action) onToolWhy(parsed.action, parsed.name)
    return
  }
  const a = ev.target?.closest?.('a[data-jump], a[href^="btfjump:"], a[href^="btfrange:"], a[href^="btfhyp:"], a[href^="btfscope:"], a[href^="btfexp:"], a[href^="btftool:"], a[data-highlight], a[href^="btfhighlight:"]')
  if (a && !a.classList.contains('ai-mermaid-zoom')) {
    ev.preventDefault()
    const href = a.getAttribute('href') || ''
    const hl = parseBtfHighlightHref(href, a.getAttribute('data-highlight'))
    if (hl) {
      emit('highlight', hl)
      return
    }
    const range = parseBtfRangeHref(href)
    if (range) {
      emit('range', range)
      return
    }
    const v = parseBtfJumpHref(href, a.getAttribute('data-jump'))
    if (Number.isFinite(v)) emit('jump', v)
    return
  }
  if (ev.target?.closest?.('.ai-mermaid-zoom-dialog')) return
  const zoomHit = ev.target?.closest?.('.ai-mermaid-zoom, .ai-mermaid-svg, .ai-mermaid-img')
  if (!zoomHit) return
  ev.preventDefault()
  openMermaidZoom(zoomHit)
}

function onLogContextMenu(ev) {
  logMenu.hasSelection = !!String(window.getSelection?.() || '').trim()
  logMenu.x = ev.clientX
  logMenu.y = ev.clientY
  logMenu.visible = true
}

function closeLogMenu() {
  logMenu.visible = false
}

function copySelection() {
  const text = String(window.getSelection?.() || '')
  closeLogMenu()
  if (text) writeClipboard(text)
}

function copyConversation() {
  closeLogMenu()
  if (!messages.value.length) return
  writeClipboard(formatAiConversationMarkdown(messages.value, new Date(), props.responseLanguage))
}

async function writeClipboard(text) {
  try {
    await navigator.clipboard.writeText(text)
    status.value = 'Copied to clipboard.'
  } catch {
    status.value = 'Clipboard is not available in this browser.'
  }
}

function saveConversationAs(format) {
  closeLogMenu()
  if (!messages.value.length) return
  const entries = messages.value
  let data
  let mime
  const lang = props.responseLanguage
  if (format === 'txt') {
    data = formatAiConversationText(entries, new Date(), lang)
    mime = 'text/plain;charset=utf-8'
  } else if (format === 'html') {
    data = formatAiConversationHtml(entries, new Date(), lang)
    mime = 'text/html;charset=utf-8'
  } else {
    data = formatAiConversationMarkdown(entries, new Date(), lang)
    mime = 'text/markdown;charset=utf-8'
  }
  const name = `ai-conversation-${aiFileStamp()}.${format}`
  const url = URL.createObjectURL(new Blob([data], { type: mime }))
  const a = document.createElement('a')
  a.href = url
  a.download = name
  a.click()
  URL.revokeObjectURL(url)
  status.value = `Saved conversation to ${name}`
}

function collectConversationToolsRun() {
  const out = []
  for (const m of messages.value) {
    for (const t of (m.tools || [])) {
      if (t && t.status === 'applied' && t.name) out.push(String(t.name))
    }
  }
  return out
}

function collectConversationEvidenceTimes() {
  const out = []
  for (const m of messages.value) {
    if (m.role === 'assistant') out.push(...extractJumpTimes(String(m.content || '')))
  }
  return out
}

function exportInvestigationFile(args, meta) {
  const findingId = String(args.finding_id || '').trim()
  let conclusion = String(args.conclusion || '').trim()
  let toolsRun = Array.isArray(args.tools_run) ? args.tools_run.filter(Boolean).map(String) : []
  let evidenceTimes = Array.isArray(args.evidence_times)
    ? args.evidence_times.filter(t => typeof t === 'number')
    : []
  if (!toolsRun.length) toolsRun = collectConversationToolsRun()
  if (!evidenceTimes.length) evidenceTimes = collectConversationEvidenceTimes()
  if (!conclusion) {
    for (let i = messages.value.length - 1; i >= 0; i -= 1) {
      const m = messages.value[i]
      if (m.role === 'assistant' && String(m.content || '').trim()) {
        conclusion = String(m.content).trim().slice(0, 2000)
        break
      }
    }
  }
  const finding = findingId ? { id: findingId, title: findingId } : null
  const pkg = buildInvestigationPackage({
    traceName: meta.file || '',
    scope: meta.scope || '',
    finding,
    plan: investigationPlan.value,
    toolsRun,
    conclusion,
    evidenceTimes,
    timestamp: new Date().toISOString(),
  })
  const data = JSON.stringify(pkg, null, 2)
  const fname = `ai-investigation-${aiFileStamp()}.json`
  const url = URL.createObjectURL(new Blob([data], { type: 'application/json;charset=utf-8' }))
  const link = document.createElement('a')
  link.href = url
  link.download = fname
  link.click()
  URL.revokeObjectURL(url)
  status.value = `Saved investigation to ${fname}`
  return { ok: true, message: `Saved investigation package to ${fname}`, path: fname }
}

function exportAiReport(toolName, args = {}) {
  let fmt = String(args.format || 'html').trim().toLowerCase()
  if (fmt !== 'csv' && fmt !== 'json') fmt = 'html'
  let gui = {}
  if (typeof props.getGuiState === 'function') {
    try { gui = { ...(props.getGuiState() || {}) } } catch (err) {
      return { ok: false, message: `GUI state error: ${err?.message || err}` }
    }
  }
  let findings = String(gui.findings || '')
  delete gui.findings
  if (!findings && typeof props.getContext === 'function') {
    try {
      const ctx = props.getContext()
      if (ctx && typeof ctx.then !== 'function') {
        findings = String(ctx.findingsText || ctx.findings_text || '')
      }
    } catch { /* ignore */ }
  }
  const meta = {
    file: gui.file || '',
    span: gui.span || '',
    cores: gui.cores || '',
    scope: gui.scope || '',
  }
  delete gui.file
  delete gui.span
  delete gui.cores
  delete gui.scope
  const annotations = Array.isArray(gui.annotations) ? gui.annotations : []
  if (toolName === AI_TOOL_EXPORT_INVESTIGATION || fmt === 'json') {
    return exportInvestigationFile(args, meta)
  }
  const stamp = aiFileStamp()
  let data
  let name
  let mime
  if (fmt === 'csv') {
    data = buildAiReportCsv({
      meta,
      gui,
      findings,
      annotations,
      conversation: formatAiConversationText(messages.value),
    })
    name = `ai-report-${stamp}.csv`
    mime = 'text/csv;charset=utf-8'
  } else {
    data = buildAiReportHtml({
      meta,
      gui,
      findings,
      annotations,
      conversationHtml: formatAiConversationHtmlBody(messages.value),
    })
    name = `ai-report-${stamp}.html`
    mime = 'text/html;charset=utf-8'
  }
  const url = URL.createObjectURL(new Blob([data], { type: mime }))
  const link = document.createElement('a')
  link.href = url
  link.download = name
  link.click()
  URL.revokeObjectURL(url)
  status.value = `Saved report to ${name}`
  return { ok: true, message: `Saved ${fmt} report to ${name}`, path: name }
}

async function scrollLog() {
  await nextTick()
  const el = logRef.value
  if (el) el.scrollTop = el.scrollHeight
}

function clear() {
  if (busy.value) stop()
  messages.value = []
  chatMessages = []
  toolRound = 0
  error.value = ''
  mermaidZoom.value = null
  evidencePayload = null
  interpretedQuery = null
  costMeter.value = emptyCostMeter()
  status.value = ''
}

function stop() {
  if (!busy.value || !abortCtrl) return
  status.value = 'Stopping…'
  error.value = ''
  abortCtrl.abort()
}

function onComposerAction() {
  if (busy.value) stop()
  else send()
}

function recordTurnUsage(turn, calls) {
  const usage = chatUsageFromResponse({ usage: turn?.usage || {} })
  const names = (calls || []).map(c => String(c?.name || ''))
  const elapsed = costStarted ? Math.max(0, (Date.now() - costStarted) / 1000) : 0
  costMeter.value = accumulateCost(costMeter.value, {
    promptTokens: usage.prompt_tokens,
    completionTokens: usage.completion_tokens,
    toolCalls: names.length,
    traceQueries: names.filter(n => isQueryTool(n)).length,
    modelTimeS: elapsed,
  })
}

async function onInvestigationMode(mode) {
  const plan = investigationModePlan(mode)
  const label = investigationModeLabel(plan.mode)
  const prompt = investigationModePrompt(plan.mode)
  const steps = (plan.tools || []).map(s => ({
    id: String(s), label: String(s), status: 'pending',
  }))
  activeTemplateId = plan.template || plan.mode
  if (steps.length) setInvestigationPlan({ goal: label, steps })
  else setInvestigationPlan(null)
  skipInterpretOnce = true
  draft.value = prompt
  await send()
}

function onSaveInvestigationTemplate() {
  let steps = []
  if (investigationPlan.value?.steps) {
    steps = investigationPlan.value.steps.map(s => String(s.id || s)).filter(Boolean)
  }
  if (!steps.length && evidencePayload?.investigation_case?.tools_executed) {
    steps = [...evidencePayload.investigation_case.tools_executed]
  }
  const name = window.prompt('Template name', 'My Investigation')
  if (name == null) return
  const tpl = newUserInvestigationTemplate(name, steps)
  const items = parseUserInvestigationTemplates(
    dumpUserInvestigationTemplates(userInvestigationTemplates.value),
  ).filter(it => it.id !== tpl.id)
  items.push(tpl)
  saveAiUserInvestigationTemplates(items)
  userInvestigationTemplates.value = items
  status.value = `Saved template “${tpl.label}”.`
}

function onHypothesisAction(action, hypId) {
  const act = String(action || '').trim().toLowerCase()
  const hid = String(hypId || '').trim()
  const payload = { ...(evidencePayload || {}) }
  const hyps = [...(payload.hypotheses_managed || payload.hypotheses || [])]
  if (['supported', 'rejected', 'need_evidence', 'possible'].includes(act)) {
    const updated = setHypothesisStatus(hyps, hid, act)
    payload.hypotheses_managed = updated
    payload.hypotheses = updated
    if (payload.investigation_case) {
      payload.investigation_case = { ...payload.investigation_case, hypotheses: updated }
    }
    evidencePayload = payload
    syncEvidenceLogEntry(payload)
    return
  }
  if (act === 'compare') {
    const ranked = compareHypotheses(hyps)
    const leader = ranked.leader || {}
    payload.hypotheses_managed = ranked.ranked || hyps
    payload.conclusion = leader.hypothesis ? `Leader: ${leader.hypothesis}` : 'Compare hypotheses'
    evidencePayload = payload
    syncEvidenceLogEntry(payload)
    return
  }
  if (act === 'test') {
    let name = hid
    for (const h of hyps) {
      if (h && String(h.id || '') === hid) {
        name = String(h.hypothesis || hid)
        break
      }
    }
    const prompt = (
      `Test hypothesis ${JSON.stringify(name)} (id=${hid}). `
      + 'Call investigate then correlate_events, find_critical_path, '
      + 'build_task_dependency_graph, analyze_temporal_causality, '
      + 'rank_root_causes, and challenge_conclusion. '
      + `Then manage_hypotheses(hypothesis_id=${hid}, `
      + 'status=supported|rejected|need_evidence). '
      + 'Finish with a verdict, jump:TIME evidence, and one next check.'
    )
    activeTemplateId = 'investigate'
    skipInterpretOnce = true
    draft.value = prompt
    send()
  }
}

function onScopeAction(action, key) {
  const act = String(action || '').trim().toLowerCase()
  let interpreted = {
    ...(interpretedQuery || evidencePayload?.interpreted || {}),
  }
  if (act === 'toggle') {
    interpreted = toggleInterpretedScope(interpreted, key)
    interpretedQuery = interpreted
    const payload = { ...(evidencePayload || {}), interpreted }
    const scopes = [...(interpreted.scope || [])].map(s => String(s)).filter(Boolean)
    const mode = String(interpreted.mode || interpreted.kind || '')
    payload.subtitle = mode && scopes.length
      ? `${mode}: ${scopes.join(', ')}`
      : (scopes.join(', ') || mode)
    evidencePayload = payload
    syncEvidenceLogEntry(payload)
    return
  }
  if (act === 'edit') {
    const q = String(interpreted.interpreted_question || '').trim()
    const next = window.prompt('Interpreted question:', q)
    if (next != null && String(next).trim()) {
      interpreted.interpreted_question = String(next).trim()
      interpretedQuery = interpreted
      const payload = { ...(evidencePayload || {}), interpreted }
      payload.conclusion = interpreted.interpreted_question
      evidencePayload = payload
      syncEvidenceLogEntry(payload)
    }
    return
  }
  if (act === 'run') {
    activeTemplateId = 'investigate'
    skipInterpretOnce = true
    draft.value = interpretedRunPrompt(interpreted)
    send()
  }
}

function onExperimentAction(action) {
  if (String(action || '').trim().toLowerCase() !== 'save') return
  onSaveUserKnowledge()
}

function onToolWhy(action, name) {
  if (String(action || '').trim().toLowerCase() !== 'why') return
  const want = String(name || '').trim()
  const reasons = evidencePayload?.tool_reasons || []
  const hit = reasons.find(r => r && typeof r === 'object' && String(r.tool || '') === want)
  const why = hit ? String(hit.reason || '') : ''
  status.value = why ? `${want}: ${why}` : `${want}: no recorded reason`
}

function onSaveUserKnowledge() {
  const payload = { ...(evidencePayload || {}) }
  let finding = payload.finding && typeof payload.finding === 'object' ? payload.finding : {}
  if (!finding.title) {
    const items = payload.investigation_case?.suspected_findings || []
    if (items[0] && typeof items[0] === 'object') finding = items[0]
  }
  const hk = payload.historical_knowledge && typeof payload.historical_knowledge === 'object'
    ? payload.historical_knowledge
    : {}
  const extras = {
    issue: String(payload.conclusion || finding.title || ''),
    fix: String(hk.known_fix || ''),
    build: String(hk.last_occurrence || ''),
    task: String(finding.task || hk.task || ''),
    metrics: { ...(hk.current || hk.typical || {}) },
  }
  for (const key of ['migrations', 'migration_rate', 'blocking', 'wcet']) {
    if (finding[key] != null) extras[key] = finding[key]
  }
  const entry = newUserHistoricalEntry(finding, extras)
  const name = window.prompt('Issue label:', entry.issue || 'Saved finding')
  if (name == null) return
  entry.issue = String(name || entry.issue).trim() || entry.issue
  let items = parseUserHistoricalKnowledge(dumpUserHistoricalKnowledge(
    loadAiUserHistoricalKnowledge(),
  ))
  items = items.filter(it => !(it.task === entry.task && it.issue === entry.issue))
  items.push(entry)
  saveAiUserHistoricalKnowledge(items)
  status.value = `Saved knowledge “${entry.issue}”.`
}

async function onInvestigationTemplate(tpl) {
  const prompt = investigationTemplatePrompt(tpl)
  const steps = (tpl.steps || []).map(s => ({
    id: String(s), label: String(s), status: 'pending',
  }))
  activeTemplateId = tpl.id || ''
  if (steps.length) {
    setInvestigationPlan({ goal: String(tpl.label || 'Investigation'), steps })
  } else {
    setInvestigationPlan(null)
  }
  skipInterpretOnce = true
  draft.value = prompt
  await send()
}

async function onTemplate(t) {
  activeTemplateId = t.id || ''
  if (isAgentTemplate(t.id)) {
    setInvestigationPlan(defaultInvestigationPlan(String(t.prompt || '').slice(0, 80)))
  } else {
    setInvestigationPlan(null)
  }
  if (t.id === AI_COMPARE_TEMPLATE_ID) {
    await runCompareTemplate(t.prompt)
    return
  }
  skipInterpretOnce = true
  draft.value = t.prompt
  await send()
}

async function runCompareTemplate(prompt) {
  refreshLoadedTabs()
  const tabs = loadedTabs.value
  if (tabs.length < 2) {
    status.value = 'Open at least two BTF tabs to compare.'
    return
  }
  if (tabs.length === 2) {
    try {
      const ctx = normalizeAiContext(await buildCompareCtx(tabs[0].id, tabs[1].id))
      if (!(ctx.findingsText || '').trim()) {
        status.value = 'Could not build Trace Compare tables.'
        return
      }
      skipInterpretOnce = true
      await send(prompt, ctx)
    } catch (err) {
      status.value = err?.message || String(err)
      error.value = status.value
    }
    return
  }
  pendingComparePrompt.value = prompt
  comparePickA.value = tabs[0].id
  comparePickB.value = tabs[1].id
  comparePickOpen.value = true
}

async function confirmComparePick() {
  const idA = comparePickA.value
  const idB = comparePickB.value
  if (idA == null || idB == null || idA === idB) return
  comparePickOpen.value = false
  const prompt = pendingComparePrompt.value
  pendingComparePrompt.value = ''
  try {
    const ctx = normalizeAiContext(await buildCompareCtx(idA, idB))
    if (!(ctx.findingsText || '').trim()) {
      status.value = 'Could not build Trace Compare tables.'
      return
    }
    skipInterpretOnce = true
    await send(prompt, ctx)
  } catch (err) {
    status.value = err?.message || String(err)
    error.value = status.value
  }
}

async function buildCompareCtx(idA, idB) {
  if (!props.buildCompareContext) {
    throw new Error('Trace Compare is not available.')
  }
  return Promise.resolve(props.buildCompareContext(idA, idB))
}

async function ask(prompt) {
  skipInterpretOnce = true
  draft.value = prompt
  await send()
}

async function askTemplate(templateId, promptOverride = '') {
  const t = templates.find(x => x.id === templateId)
  const prompt = promptOverride || t?.prompt || ''
  if (!prompt) return
  activeTemplateId = templateId || ''
  if (isAgentTemplate(templateId)) {
    setInvestigationPlan(defaultInvestigationPlan(String(prompt).slice(0, 80)))
  } else {
    setInvestigationPlan(null)
  }
  skipInterpretOnce = true
  draft.value = prompt
  await send()
}

async function askCompare(idA, idB) {
  const prompt = templates.find(t => t.id === AI_COMPARE_TEMPLATE_ID)?.prompt
  if (!prompt) return
  if (idA == null || idB == null || idA === idB) {
    status.value = 'Choose two different traces.'
    return
  }
  try {
    const ctx = normalizeAiContext(await buildCompareCtx(idA, idB))
    if (!(ctx.findingsText || '').trim()) {
      status.value = 'Could not build Trace Compare tables.'
      return
    }
    skipInterpretOnce = true
    await send(prompt, ctx)
  } catch (err) {
    status.value = err?.message || String(err)
    error.value = status.value
  }
}

async function askValidateExperiment(idA, idB) {
  if (idA == null || idB == null || idA === idB) {
    status.value = 'Choose two different traces.'
    return
  }
  try {
    const ctx = normalizeAiContext(await buildCompareCtx(idA, idB))
    if (!(ctx.findingsText || '').trim()) {
      status.value = 'Could not build Trace Compare tables.'
      return
    }
    skipInterpretOnce = true
    await send(VALIDATE_EXPERIMENT_PROMPT, ctx)
  } catch (err) {
    status.value = err?.message || String(err)
    error.value = status.value
  }
}

async function runCompletion(active, finalRound = false) {
  let messages = chatMessages
  if (finalRound) {
    // Last allowed round: drop tools so the model must answer in text
    // now, instead of silently hitting the round cap next.
    messages = [...chatMessages, {
      role: 'user',
      content: 'You have reached the tool-call limit for this turn. '
        + 'Do not call any more tools — summarize your findings and '
        + 'give your final answer now in plain text.',
    }]
  }
  costStarted = Date.now()
  return aiChatCompletion({
    messages,
    tools: finalRound ? [] : aiViewerTools(),
    baseUrl: active.baseUrl,
    model: active.model,
    apiKey: active.apiKey,
    preset: active.preset,
    tlsVerify: active.tlsVerify,
    responseLanguage: props.responseLanguage,
    signal: abortCtrl?.signal,
  })
}

function ingestTurn(turn) {
  const text = String(turn.content || '').trim()
  const calls = Array.isArray(turn.tool_calls) ? turn.tool_calls : []
  recordTurnUsage(turn, calls)
  if (calls.length) chatMessages.push(canonicalAssistantToolMessage(text, calls))
  else if (text) chatMessages.push({ role: 'assistant', content: text })

  const toolsNorm = calls.map((c, i) => {
    const name = String(c.name || '')
    const args = c.arguments && typeof c.arguments === 'object' ? c.arguments : {}
    const checked = validateToolCall(name, args)
    return {
      id: String(c.id || `call_${i}`),
      name,
      arguments: checked.args || args,
      error: checked.error || '',
      status: 'pending',
    }
  })
  if (toolsNorm.length) {
    advanceInvestigationPlan(toolsNorm.map(t => t.name))
    batchSeq += 1
    const batchId = `b${batchSeq}`
    messages.value.push({
      role: 'assistant',
      content: text,
      tools: toolsNorm,
      batchId,
    })
    const auto = parseAiAutoApply(props.aiAutoApply) || toolBatchAutoRuns(toolsNorm)
    return { batchId, text, auto }
  }
  if (text) messages.value.push({ role: 'assistant', content: text })
  finishInvestigationPlan()
  attachResponseValidation(text)
  pinEvidenceLogEntry()
  const jumps = extractJumpTimes(text)
  if (jumps.length) {
    const m = /jump:([0-9]+(?:\.[0-9]+)?)/.exec(text || '')
    const label = m ? m[1] : String(jumps[0])
    status.value = `Done. Click jump:${label} to annotate the timeline and jump there.`
  } else {
    status.value = 'Done.'
  }
  return null
}

function findBatch(batchId) {
  return messages.value.find(m => m.batchId === batchId)
}

function commitBatch(batchId, skipped) {
  const msg = findBatch(batchId)
  if (!msg?.tools?.length) return []
  let results = []
  if (skipped) {
    msg.tools.forEach((t) => { t.status = 'skipped' })
    results = msg.tools.map(() => ({ ok: false, message: 'User declined to apply this GUI action.' }))
    status.value = 'Skipped GUI actions.'
  } else {
    try {
      const hostTools = msg.tools.filter(t => !isExportTool(t.name))
      const hostResults = hostTools.length && typeof props.executeTools === 'function'
        ? (props.executeTools(hostTools) || [])
        : []
      let hi = 0
      results = msg.tools.map((t) => {
        if (isExportTool(t.name)) return exportAiReport(t.name, t.arguments || {})
        const res = hostResults[hi] || { ok: false, message: 'missing tool result' }
        hi += 1
        return res
      })
    } catch (err) {
      results = msg.tools.map(() => ({ ok: false, message: err?.message || String(err) }))
    }
    msg.tools.forEach((t, i) => {
      const res = results[i] || {}
      t.status = res.ok === false ? 'failed' : 'applied'
    })
  }
  msg.tools.forEach((t, i) => {
    chatMessages.push(toolResultMessage({
      toolCallId: t.id,
      name: t.name,
      content: results[i] || { ok: false, message: '' },
    }))
    const toolName = String(t.name || '')
    if (EVIDENCE_PANEL_TOOLS.includes(toolName)) {
      updateEvidenceFromToolResult(toolName, results[i] || {})
    }
  })
  return results
}

async function continueAfterTools() {
  if (toolRound >= maxToolRounds(activeTemplateId || '')) {
    status.value = 'Done (tool round limit).'
    return
  }
  toolRound += 1
  const finalRound = toolRound >= maxToolRounds(activeTemplateId || '')
  const active = resolveAiSettings({ aiPreset: props.aiPreset, aiPresets: props.aiPresets })
  busy.value = true
  status.value = `Waiting for ${aiPresetInfo(active.preset).label} (${active.model})…`
  abortCtrl = new AbortController()
  try {
    const turn = await runCompletion(active, finalRound)
    authForced.value = false
    const pending = ingestTurn(turn)
    if (pending && pending.auto) {
      commitBatch(pending.batchId, false)
      await continueAfterTools()
    } else if (pending) {
      status.value = 'Review GUI actions, then Apply or Skip.'
    }
  } catch (err) {
    if (err?.name === 'AbortError') {
      status.value = 'Stopped.'
      error.value = ''
    } else {
      const errMsg = err?.message || String(err)
      messages.value.push({ role: 'assistant', content: `(Error) ${errMsg}` })
      setErrorStatus(errMsg)
      noteAuthError(errMsg)
    }
  } finally {
    busy.value = false
    abortCtrl = null
    await scrollLog()
  }
}

async function applyBatch(batchId) {
  commitBatch(batchId, false)
  await continueAfterTools()
}

async function skipBatch(batchId) {
  commitBatch(batchId, true)
}

async function undoBatch(_batchId) {
  if (typeof props.undoTools === 'function') props.undoTools()
  const msg = findBatch(_batchId)
  if (msg?.tools) msg.tools.forEach((t) => { t.status = 'undone' })
  status.value = 'Reverted last AI GUI actions.'
}

async function send(overrideQuery = null, overrideCtx = null) {
  const query = (overrideQuery != null ? String(overrideQuery) : draft.value).trim()
  if (!query || busy.value || !props.aiEnabled) return
  const skip = skipInterpretOnce
  skipInterpretOnce = false
  if (shouldConfirmInterpretedQuery(query, { alreadyInterpreted: skip })) {
    messages.value.push({ role: 'user', content: query })
    draft.value = ''
    try {
      const raw = overrideCtx != null
        ? overrideCtx
        : await Promise.resolve(props.getContext())
      const ctx = normalizeAiContext(raw)
      const cursors = ctx.cursors || []
      let lo = null
      let hi = null
      if (cursors.length >= 2) {
        lo = Math.min(...cursors.map(Number))
        hi = Math.max(...cursors.map(Number))
      }
      const data = interpretInvestigationQuery(query, {
        findings: ctx.findings || [],
        cursorLo: lo,
        cursorHi: hi,
      })
      updateEvidenceFromToolResult('interpret_query', { ok: true, ...data })
      status.value = 'Confirm investigation scope, then Run investigation.'
    } catch (err) {
      status.value = err?.message || String(err)
    }
    await scrollLog()
    return
  }
  messages.value.push({ role: 'user', content: query })
  draft.value = ''
  busy.value = true
  error.value = ''
  toolRound = 0
  const active = resolveAiSettings({ aiPreset: props.aiPreset, aiPresets: props.aiPresets })
  status.value = `Waiting for ${aiPresetInfo(active.preset).label} (${active.model})…`
  await scrollLog()

  abortCtrl = new AbortController()
  try {
    const raw = overrideCtx != null
      ? overrideCtx
      : await Promise.resolve(props.getContext())
    const ctx = normalizeAiContext(raw)
    const privacy = applyCloudPrivacy(ctx.findingsText || '', query, {
      endpointIsLocal: isLocalAiHost(active.baseUrl),
      redactTaskNames: !!props.aiRedactTaskNames,
      sensitive: !!props.aiTraceSensitive,
    })
    if (privacy.blocked) {
      status.value = privacy.note || 'Cloud AI disabled.'
      messages.value.pop()
      return
    }
    ctx.findingsText = privacy.findings_text || ctx.findingsText || ''
    const sendQuery = privacy.query || query
    if (sendQuery !== query) {
      const last = messages.value[messages.value.length - 1]
      if (last && last.role === 'user') last.content = sendQuery
    }
    if (overrideCtx == null) refreshLoadedTabs()
    chatMessages = [
      { role: 'system', content: buildAiSystemPrompt(props.responseLanguage) },
      {
        role: 'user',
        content: buildAiUserMessage(sendQuery, {
          findingsText: ctx.findingsText || '',
          metrics: ctx.metrics || null,
          span: ctx.span || '',
          cores: ctx.cores ?? '',
          scope: ctx.scope || '',
          cursors: ctx.cursors || [],
        }),
      },
    ]
    const turn = await runCompletion(active)
    authForced.value = false
    const pending = ingestTurn(turn)
    if (pending && pending.auto) {
      commitBatch(pending.batchId, false)
      await continueAfterTools()
    } else if (pending) {
      status.value = 'Review GUI actions, then Apply or Skip.'
    }
  } catch (err) {
    if (err?.name === 'AbortError') {
      status.value = 'Stopped.'
      error.value = ''
    } else {
      const msg = err?.message || String(err)
      messages.value.push({ role: 'assistant', content: `(Error) ${msg}` })
      setErrorStatus(msg)
      noteAuthError(msg)
    }
  } finally {
    busy.value = false
    abortCtrl = null
    refreshLoadedTabs()
    await scrollLog()
  }
}

watch(() => props.aiEnabled, (on) => {
  if (!on) status.value = ''
})

function onDocMouseDown(ev) {
  closeLogMenu()
  if (!moreOpen.value) return
  if (moreBtnEl.value?.contains(ev.target)) return
  if (moreMenuEl.value?.contains(ev.target)) return
  closeMore()
}

function onDocKeyDown(ev) {
  if (ev.key !== 'Escape') return
  if (mermaidZoom.value) {
    closeMermaidZoom()
    ev.preventDefault()
    return
  }
  if (moreOpen.value) {
    closeMore()
    ev.preventDefault()
    return
  }
  closeLogMenu()
}

onMounted(() => {
  document.addEventListener('mousedown', onDocMouseDown)
  document.addEventListener('keydown', onDocKeyDown)
  window.addEventListener('resize', placeMoreMenu)
})

onBeforeUnmount(() => {
  endSplitDrag()
  document.removeEventListener('mousedown', onDocMouseDown)
  document.removeEventListener('keydown', onDocKeyDown)
  window.removeEventListener('resize', placeMoreMenu)
})

defineExpose({
  refreshLoadedTabs,
  refreshCoreAvailability,
  ask,
  askTemplate,
  askCompare,
  askValidateExperiment,
  clear,
  saveConversationAs,
  scrollLog,
})
</script>

<style scoped>
.ai-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
  height: 100%;
  min-height: 0;
  padding: 6px;
  box-sizing: border-box;
  font-size: var(--ui-font-size);
}
.ai-header {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
.ai-title { font-weight: 600; font-size: 1.08em; }
.ai-auth-chip {
  margin-left: 4px;
  background: transparent;
  color: var(--muted, #8b98a8);
  border: 1px solid var(--border, #3a4658);
  border-radius: 10px;
  padding: 1px 8px;
  font: inherit;
  font-size: 0.92em;
  cursor: pointer;
}
.ai-auth-chip:hover {
  color: var(--fg, #dbe2ea);
  border-color: var(--accent, #5b9bd5);
}
.ai-auth-cta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.ai-header-actions {
  display: flex;
  align-items: center;
  gap: 2px;
  flex-wrap: wrap;
  flex-shrink: 0;
}
.ai-lang-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.35);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 80;
}
.ai-lang-dialog {
  background: var(--panel-bg, #1e1e1e);
  color: var(--fg, #ddd);
  border: 1px solid var(--border, #444);
  border-radius: 8px;
  padding: 16px;
  min-width: 280px;
  max-width: 90vw;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
}
.ai-lang-dialog h3 {
  margin: 0 0 8px;
  font-size: 14px;
}
.ai-lang-dialog p {
  margin: 0 0 10px;
  font-size: 12px;
  color: var(--muted, #999);
}
.ai-pick-label {
  display: block;
  font-size: 11px;
  margin: 0 0 4px;
  color: var(--muted, #999);
}
.ai-pick-error {
  margin: 8px 0 0;
  font-size: 12px;
  color: #c0392b;
}
.ai-lang-select {
  width: 100%;
  box-sizing: border-box;
  margin-bottom: 12px;
  padding: 6px 8px;
  border-radius: 4px;
  border: 1px solid var(--border, #555);
  background: var(--input-bg, #2a2a2a);
  color: inherit;
}
.ai-lang-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  align-items: center;
}
.ai-link-btn {
  background: transparent;
  border: none;
  color: var(--accent, #2a6fb2);
  cursor: pointer;
  font: inherit;
  font-size: inherit;
  padding: 2px 6px;
}
.ai-link-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.ai-empty-hint {
  display: block;
  margin-top: 8px;
  font-size: 0.92em;
  color: var(--muted, #8a96a8);
  line-height: 1.35;
}
.ai-empty-hint code {
  font-size: 0.9em;
  background: rgba(127, 127, 127, 0.15);
  padding: 0 3px;
  border-radius: 3px;
}
.ai-section-label {
  font-weight: 600;
  font-size: inherit;
}
.ai-templates,
.ai-modes {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}
.ai-tpl-btn {
  min-width: 0;
  min-height: 28px; /* Desktop `_AI_CHIP_MIN_HEIGHT` */
  padding: 4px 8px;
  line-height: 1.3;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  text-align: left;
  box-sizing: border-box;
}
.ai-more-wrap {
  position: relative;
  flex-shrink: 0;
}
.ai-more-menu {
  z-index: 10100;
  min-width: 168px;
  overflow-y: auto;
  padding: 4px;
  background: var(--panel, #1a2230);
  border: 1px solid var(--border, #3a4658);
  border-radius: 7px;
  box-shadow: 0 8px 28px rgba(0, 0, 0, 0.6);
  display: flex;
  flex-direction: column;
}
.ai-more-menu-wide {
  display: grid;
  grid-template-columns: repeat(2, minmax(168px, 1fr));
  min-width: min(360px, calc(100vw - 16px));
  max-width: min(520px, calc(100vw - 16px));
  gap: 0 8px;
}
.ai-more-col {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.ai-more-heading {
  font-size: 11px;
  font-weight: 600;
  color: var(--muted, #8a96a8);
  padding: 6px 10px 2px;
}
.ai-more-item {
  appearance: none;
  background: none;
  border: none;
  border-radius: 4px;
  color: inherit;
  cursor: pointer;
  font: inherit;
  font-size: inherit;
  text-align: left;
  padding: 5px 10px;
}
.ai-more-item:hover:not(:disabled) {
  background: rgba(91, 155, 213, 0.18);
}
.ai-more-item:disabled,
.ai-more-item.gray {
  color: var(--muted, #8a96a8);
  opacity: 1;
  cursor: not-allowed;
}
.ai-plan-status {
  flex-shrink: 0;
  font-size: 0.85em;
  color: var(--muted, #8a96a8);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  padding: 1px 0;
  line-height: 1.3;
}
.ai-tpl-btn, .ai-btn {
  font: inherit;
  font-size: inherit;
  padding: 5px 8px;
  border-radius: 6px;
  border: 1px solid var(--border, #3a4658);
  background: var(--panel-btn-bg, #243044);
  color: var(--text, #e8eef7);
  cursor: pointer;
  text-align: left;
}
.ai-tpl-btn:disabled, .ai-btn:disabled {
  color: var(--muted, #8a96a8);
  background: var(--panel-inset, #1a2230);
  border-color: var(--border, #3a4658);
  opacity: 1;
  cursor: not-allowed;
}
.ai-tpl-btn.gray:disabled {
  color: var(--muted, #8a96a8);
}
.ai-tpl-btn:hover:not(:disabled), .ai-btn:hover:not(:disabled) {
  border-color: var(--accent, #2a6fb2);
}
.ai-btn.primary {
  background: var(--accent, #2a6fb2);
  border-color: var(--accent, #2a6fb2);
  color: #fff;
  font-weight: 600;
}
.ai-btn.primary:disabled {
  background: #555555;
  border-color: #555555;
  color: #bbbbbb;
}
.ai-log {
  flex: 1;
  min-height: 0;
  overflow: auto;
  border: 1px solid var(--border, #3a4658);
  border-radius: 8px;
  padding: 8px;
  background: var(--panel-inset, #1a2230);
  font-size: inherit;
  line-height: 1.4;
}
.ai-split {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.ai-split-top {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.ai-split-handle {
  flex: 0 0 6px;
  margin: 2px 0;
  cursor: ns-resize;
  background: var(--border, #3a4658);
  border-radius: 3px;
}
.ai-split-handle:hover {
  background: var(--accent, #5b9bd5);
}
.ai-split-bottom {
  flex: 0 0 auto;
  min-height: 64px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.ai-ctx-menu {
  position: fixed;
  z-index: 10100;
  min-width: 168px;
  padding: 4px;
  background: var(--panel, #1a2230);
  border: 1px solid var(--border, #3a4658);
  border-radius: 7px;
  box-shadow: 0 8px 28px rgba(0, 0, 0, 0.6);
  display: flex;
  flex-direction: column;
}
.ai-ctx-item {
  appearance: none;
  background: none;
  border: none;
  border-radius: 4px;
  color: inherit;
  cursor: pointer;
  font: inherit;
  font-size: inherit;
  padding: 5px 10px;
  text-align: left;
}
.ai-ctx-item:hover:not(:disabled) { background: rgba(91, 155, 213, 0.22); }
.ai-ctx-item:disabled { color: var(--muted, #8a96a8); cursor: default; }
.ai-ctx-sep {
  border-top: 1px solid var(--border, #3a4658);
  margin: 4px 2px;
}
.ai-empty { color: var(--muted, #8a96a8); }
.ai-msg { margin: 0 0 12px; }
.ai-msg + .ai-msg {
  padding-top: 12px;
  border-top: 1px solid #2b3442;
}
.ai-msg-role {
  font-weight: 700;
  font-size: 11px;
  margin-bottom: 4px;
}
.ai-msg.user .ai-msg-role { color: #6ea8e0; }
.ai-msg.assistant .ai-msg-role { color: #6fbf9a; }
.ai-msg.evidence .ai-msg-role { color: #8a96a8; }
.ai-msg-body {
  border-radius: 0 8px 8px 0;
  padding: 8px 10px;
  border: 1px solid #3a4658;
  border-left-width: 3px;
}
.ai-msg.user .ai-msg-body {
  color: var(--ai-user-fg, #e8eef7);
  background: var(--ai-user-bg, #1e3348);
  border-left-color: #5b9bd5;
}
.ai-msg.assistant .ai-msg-body {
  color: var(--ai-asst-fg, #d5e4f7);
  background: var(--ai-asst-bg, #1a2620);
  border-left-color: #3d9a72;
}
.ai-msg.evidence .ai-msg-body {
  color: var(--ai-ev-fg, #c5d0dc);
  background: var(--ai-ev-bg, #1f2430);
  border-left-color: #8a96a8;
}
.ai-msg-body.markdown :deep(h1),
.ai-msg-body.markdown :deep(h2),
.ai-msg-body.markdown :deep(h3),
.ai-msg-body.markdown :deep(h4) {
  margin: 8px 0 4px;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.3;
}
.ai-msg-body.markdown :deep(h1) { font-size: 15px; }
.ai-msg-body.markdown :deep(h2) { font-size: 14px; }
.ai-msg-body.markdown :deep(p) { margin: 4px 0; }
.ai-msg-body.markdown :deep(ul),
.ai-msg-body.markdown :deep(ol) {
  margin: 4px 0 4px 1.2em;
  padding: 0;
}
.ai-msg-body.markdown :deep(li) { margin: 2px 0; }
.ai-msg-body.markdown :deep(pre) {
  margin: 6px 0;
  padding: 8px;
  border-radius: 6px;
  border: 1px solid var(--border, #3a4658);
  background: var(--ai-md-td-bg, rgba(0, 0, 0, 0.25));
  overflow-x: auto;
  white-space: pre-wrap;
  font-size: 11px;
}
.ai-msg-body.markdown :deep(code) {
  font-family: ui-monospace, Menlo, Consolas, monospace;
  font-size: 11px;
}
.ai-msg-body.markdown :deep(p code),
.ai-msg-body.markdown :deep(li code) {
  background: rgba(127, 127, 127, 0.18);
  padding: 1px 4px;
  border-radius: 3px;
}
.ai-msg-body.markdown :deep(blockquote) {
  margin: 6px 0;
  padding: 4px 10px;
  border-left: 3px solid var(--accent, #5b9bd5);
  color: var(--muted, #a8b4c4);
}
.ai-msg-body.markdown :deep(hr) {
  border: none;
  border-top: 1px solid var(--border, #3a4658);
  margin: 8px 0;
}
.ai-msg-body.markdown :deep(table.ai-md-table) {
  width: 100%;
  border-collapse: collapse;
  margin: 8px 0;
  font-size: 12px;
  overflow-x: auto;
}
.ai-msg-body.markdown :deep(table.ai-md-table th),
.ai-msg-body.markdown :deep(table.ai-md-table td) {
  border: 1px solid var(--border, #3a4658);
  padding: 4px 8px;
  vertical-align: top;
}
.ai-msg-body.markdown :deep(table.ai-md-table th) {
  background: var(--ai-md-th-bg, #243044);
  color: var(--ai-md-th-fg, #e8eef6);
  font-weight: 600;
}
.ai-msg-body.markdown :deep(table.ai-md-table td) {
  background: var(--ai-md-td-bg, #1a2230);
  color: var(--ai-md-td-fg, #dbe2ea);
}
.ai-msg-body :deep(.ai-jump),
.ai-msg-body.markdown :deep(a) {
  color: var(--accent, #5b9bd5);
  text-decoration: underline;
  cursor: pointer;
}
.ai-tool-card {
  margin-top: 8px;
  padding: 8px 10px;
  border-left: 3px solid #c9a227;
  background: var(--ai-tool-bg, #2a2418);
  color: var(--ai-tool-fg, #e6d48a);
  border-radius: 0 6px 6px 0;
  font-size: 12px;
}
.ai-tool-card p { margin: 2px 0; }
.ai-tool-st { color: #8b98a8; }
.ai-tool-fail {
  margin: 2px 0 6px 1.2em;
  color: #8b98a8;
  font-size: 11px;
}
.ai-tool-actions {
  display: flex;
  gap: 8px;
  margin-top: 6px;
}
.ai-tool-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  flex-shrink: 0;
}
.ai-msg-body :deep(.ai-mermaid) {
  margin: 8px 0;
  overflow-x: auto;
}
.ai-msg-body :deep(.ai-mermaid-zoom) {
  cursor: zoom-in;
  display: inline-block;
  text-decoration: none;
}
.ai-msg-body :deep(.ai-mermaid-svg svg),
.ai-msg-body :deep(.ai-mermaid-img) {
  max-width: 100%;
  height: auto;
  border-radius: 4px;
}
.ai-msg-body :deep(.ai-mermaid-links) {
  margin: 4px 0 0;
  font-size: 11px;
}
.ai-mermaid-overlay {
  position: fixed;
  inset: 0;
  z-index: 80;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: rgba(0, 0, 0, 0.65);
}
.ai-mermaid-zoom-dialog {
  max-width: min(1100px, 96vw);
  max-height: 92vh;
  overflow: auto;
  background: #12161d;
  border: 1px solid #3a4658;
  border-radius: 8px;
  padding: 12px 14px;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.45);
}
.ai-mermaid-zoom-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
  color: #8b98a8;
  font-size: 12px;
}
.ai-mermaid-zoom-body :deep(svg),
.ai-mermaid-zoom-body :deep(img) {
  display: block;
  max-width: none;
  width: min(1000px, 90vw);
  height: auto;
  transform: scale(var(--mm-scale, 1));
  transform-origin: top left;
  border-radius: 4px;
}
.ai-mermaid-zoom-links {
  margin: 10px 0 0;
  font-size: 12px;
}
.ai-mermaid-zoom-links :deep(a) {
  color: #5b9bd5;
}
.ai-composer {
  position: relative;
  flex: 1;
  min-height: 0;
  display: flex;
}
.ai-input {
  width: 100%;
  height: 100%;
  box-sizing: border-box;
  resize: none;
  min-height: 64px;
  flex-shrink: 0;
  font-size: inherit;
  font-family: inherit;
  border-radius: 6px;
  border: 1px solid var(--border, #3a4658);
  background: var(--panel-inset, #1a2230);
  color: var(--text, #e8eef7);
  padding: 6px 44px 6px 8px;
}
.ai-composer-icons {
  position: absolute;
  right: 6px;
  bottom: 6px;
  display: flex;
  align-items: center;
  gap: 4px;
}
.ai-icon-btn {
  width: 28px;
  height: 28px;
  padding: 0;
  border: none;
  border-radius: 14px;
  background: transparent;
  color: var(--muted, #c5cdd8);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}
.ai-icon-btn:hover:not(:disabled) {
  background: var(--tb-btn-hover, #2a3544);
  color: var(--text, #e8eef7);
}
.ai-icon-btn.primary {
  background: #2a6fb2;
  color: #fff;
}
.ai-icon-btn.primary:hover:not(:disabled) {
  background: #1a5a9a;
}
.ai-icon-btn:disabled {
  cursor: default;
  opacity: 0.4;
}
.ai-icon-btn.primary:disabled {
  background: #555555;
  color: #bbbbbb;
  opacity: 1;
}
.ai-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.ai-spacer { flex: 1; }
.ai-status {
  font-size: 0.92em;
  color: var(--muted, #8a96a8);
  min-height: 1.2em;
  flex-shrink: 0;
}
.ai-status.error { color: #e07070; }
.ai-usage-bar {
  flex-shrink: 0;
  font-size: 0.85em;
  color: var(--muted, #8a96a8);
  padding: 2px 0 0;
  border-top: 1px solid var(--border, #3a4658);
  min-height: 1.2em;
}
</style>
