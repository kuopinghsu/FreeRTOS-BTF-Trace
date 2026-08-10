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
        title="Stop the current Ollama query"
        :disabled="!busy"
        @click="stop"
      >
        Stop
      </button>
      <button
        type="button"
        class="ai-btn primary ai-ask-btn"
        title="Send the question below (Ctrl/Cmd+Enter)"
        :disabled="busy || !aiEnabled || !draft.trim()"
        @click="send()"
      >
        {{ busy ? 'Waiting…' : 'Ask' }}
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
          <span>Diagram — scroll to pan, pinch to zoom</span>
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
          v-html="mermaidZoom.html"
          @click="onMsgClick"
        />
        <p
          v-if="mermaidZoom.links"
          class="ai-mermaid-zoom-links"
          v-html="mermaidZoom.links"
          @click="onMsgClick"
        />
      </div>
    </div>

    <p class="ai-hint">
      Uses Analysis Findings for the current Statistics scope
      (Trace Compare template uses compare CSV).
      Configure the endpoint in Settings → AI.
      Prefer <code>npm run dev</code> / <code>preview</code> (proxies);
      for <code>file://</code> set <code>OLLAMA_ORIGINS</code>.
    </p>

    <div class="ai-section-label">
      Templates
    </div>
    <div class="ai-templates">
      <button
        v-for="t in templates"
        :key="t.id"
        type="button"
        class="ai-tpl-btn"
        :class="{ gray: t.id === AI_COMPARE_TEMPLATE_ID && !compareEnabled }"
        :title="templateTitle(t)"
        :disabled="busy || !aiEnabled || (t.id === AI_COMPARE_TEMPLATE_ID && !compareEnabled)"
        @click="onTemplate(t)"
      >
        {{ t.label }}
      </button>
    </div>

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
      </div>
      <div
        v-for="(m, i) in messages"
        :key="i"
        class="ai-msg"
        :class="m.role"
      >
        <div class="ai-msg-role">
          {{ m.role === 'user' ? 'You' : 'Assistant' }}
        </div>
        <div
          class="ai-msg-body"
          :class="{ markdown: m.role === 'assistant' }"
          v-html="formatMessage(m.role, m.content)"
          @click="onMsgClick"
        />
        <div
          v-if="m.tools && m.tools.length"
          class="ai-tool-card"
        >
          <p
            v-for="t in m.tools"
            :key="t.id"
          >
            ⚡ {{ toolLabel(t) }}
            <span class="ai-tool-st">({{ t.status || 'pending' }})</span>
          </p>
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
      v-if="toolBarVisible"
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

    <textarea
      v-model="draft"
      class="ai-input"
      rows="3"
      placeholder="Ask about this trace… (Ctrl/Cmd+Enter to send)"
      :disabled="busy || !aiEnabled"
      @keydown.meta.enter.prevent="send()"
      @keydown.ctrl.enter.prevent="send()"
    />

    <div
      class="ai-status"
      :class="{ error: !!error }"
    >
      {{ statusText }}
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
  extractJumpTimes,
  normalizeAiContext,
  resolveAiSettings,
} from '../utils/ollamaClient.js'
import {
  MAX_TOOL_ROUNDS,
  aiViewerTools,
  canonicalAssistantToolMessage,
  parseAiAutoApply,
  parseBtfHighlightHref,
  parseBtfJumpHref,
  summariseToolCall,
  toolResultMessage,
  validateToolCall,
} from '../utils/aiTools.js'
import {
  aiFileStamp,
  formatAiConversationHtml,
  formatAiConversationMarkdown,
  formatAiConversationText,
  formatAiMessageHtml,
} from '../utils/aiMarkdown.js'

const props = defineProps({
  aiEnabled: { type: Boolean, default: true },
  aiPreset: { type: String, default: DEFAULT_AI_PRESET },
  /** { [presetId]: { baseUrl, model, apiKey } } */
  aiPresets: { type: Object, default: () => ({}) },
  responseLanguage: { type: String, default: DEFAULT_AI_RESPONSE_LANGUAGE },
  aiAutoApply: { type: Boolean, default: false },
  /** () => Promise|{ findingsText, span, cores, scope } */
  getContext: { type: Function, required: true },
  /** () => [{ id, name }, ...] loaded BTF tabs */
  getLoadedTabs: { type: Function, default: null },
  /** (idA, idB) => Promise|{ findingsText, span, cores, scope } */
  buildCompareContext: { type: Function, default: null },
  /** (tools) => result[] */
  executeTools: { type: Function, default: null },
  undoTools: { type: Function, default: null },
})

const emit = defineEmits(['openSettings', 'jump', 'highlight', 'update:responseLanguage'])

const templates = AI_TEMPLATE_QUESTIONS
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
  langDraft.value = v || DEFAULT_AI_RESPONSE_LANGUAGE
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

const toolBarVisible = computed(() => !!(pendingBatchId.value || appliedBatchId.value))

function templateTitle(t) {
  if (t.id === AI_COMPARE_TEMPLATE_ID && !compareEnabled.value) {
    return 'Open at least two BTF tabs to use Trace Compare.'
  }
  return t.prompt
}

function applyLanguage() {
  const lang = String(langDraft.value || DEFAULT_AI_RESPONSE_LANGUAGE).trim()
    || DEFAULT_AI_RESPONSE_LANGUAGE
  emit('update:responseLanguage', lang)
  status.value = `Reply language: ${lang}`
  error.value = ''
  langOpen.value = false
}

const statusText = computed(() => {
  if (!props.aiEnabled) return 'AI is disabled in Settings → AI.'
  if (error.value) return error.value
  return status.value
})

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
  mermaidZoom.value = { html, links: links ? links.innerHTML : '' }
}

function onMsgClick(ev) {
  const a = ev.target?.closest?.('a[data-jump], a[href^="btfjump:"], a[data-highlight], a[href^="btfhighlight:"]')
  if (a && !a.classList.contains('ai-mermaid-zoom')) {
    ev.preventDefault()
    const href = a.getAttribute('href') || ''
    const hl = parseBtfHighlightHref(href, a.getAttribute('data-highlight'))
    if (hl) {
      emit('highlight', hl)
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
  writeClipboard(formatAiConversationMarkdown(messages.value))
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
  if (format === 'txt') {
    data = formatAiConversationText(entries)
    mime = 'text/plain;charset=utf-8'
  } else if (format === 'html') {
    data = formatAiConversationHtml(entries)
    mime = 'text/html;charset=utf-8'
  } else {
    data = formatAiConversationMarkdown(entries)
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
  status.value = ''
  mermaidZoom.value = null
}

function stop() {
  if (!busy.value || !abortCtrl) return
  status.value = 'Stopping…'
  error.value = ''
  abortCtrl.abort()
}

async function onTemplate(t) {
  if (t.id === AI_COMPARE_TEMPLATE_ID) {
    await runCompareTemplate(t.prompt)
    return
  }
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
  draft.value = prompt
  await send()
}

async function runCompletion(active) {
  return aiChatCompletion({
    messages: chatMessages,
    tools: aiViewerTools(),
    baseUrl: active.baseUrl,
    model: active.model,
    apiKey: active.apiKey,
    preset: active.preset,
    responseLanguage: props.responseLanguage,
    signal: abortCtrl?.signal,
  })
}

function ingestTurn(turn) {
  const text = String(turn.content || '').trim()
  const calls = Array.isArray(turn.tool_calls) ? turn.tool_calls : []
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
    batchSeq += 1
    const batchId = `b${batchSeq}`
    messages.value.push({
      role: 'assistant',
      content: text,
      tools: toolsNorm,
      batchId,
    })
    return { batchId, text }
  }
  if (text) messages.value.push({ role: 'assistant', content: text })
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
      results = typeof props.executeTools === 'function' ? (props.executeTools(msg.tools) || []) : []
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
  })
  return results
}

async function continueAfterTools() {
  if (toolRound >= MAX_TOOL_ROUNDS) {
    status.value = 'Done (tool round limit).'
    return
  }
  toolRound += 1
  const active = resolveAiSettings({ aiPreset: props.aiPreset, aiPresets: props.aiPresets })
  busy.value = true
  status.value = `Waiting for ${aiPresetInfo(active.preset).label} (${active.model})…`
  abortCtrl = new AbortController()
  try {
    const turn = await runCompletion(active)
    authForced.value = false
    const pending = ingestTurn(turn)
    if (pending && parseAiAutoApply(props.aiAutoApply)) {
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
      error.value = errMsg.split('\n')[0].slice(0, 200)
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
    if (overrideCtx == null) refreshLoadedTabs()
    chatMessages = [
      { role: 'system', content: buildAiSystemPrompt(props.responseLanguage) },
      {
        role: 'user',
        content: buildAiUserMessage(query, {
          findingsText: ctx.findingsText || '',
          metrics: ctx.metrics || null,
          span: ctx.span || '',
          cores: ctx.cores ?? '',
          scope: ctx.scope || '',
        }),
      },
    ]
    const turn = await runCompletion(active)
    authForced.value = false
    const pending = ingestTurn(turn)
    if (pending && parseAiAutoApply(props.aiAutoApply)) {
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
      error.value = msg.split('\n')[0].slice(0, 200)
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

function onDocKeyDown(ev) {
  if (ev.key !== 'Escape') return
  if (mermaidZoom.value) {
    closeMermaidZoom()
    ev.preventDefault()
    return
  }
  closeLogMenu()
}

onMounted(() => {
  document.addEventListener('mousedown', closeLogMenu)
  document.addEventListener('keydown', onDocKeyDown)
})

onBeforeUnmount(() => {
  document.removeEventListener('mousedown', closeLogMenu)
  document.removeEventListener('keydown', onDocKeyDown)
})

defineExpose({ refreshLoadedTabs, ask, clear, saveConversationAs, scrollLog })
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
}
.ai-header {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
.ai-title { font-weight: 600; font-size: 13px; }
.ai-auth-chip {
  margin-left: 4px;
  background: transparent;
  color: var(--muted, #8b98a8);
  border: 1px solid var(--border, #3a4658);
  border-radius: 10px;
  padding: 1px 8px;
  font: inherit;
  font-size: 11px;
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
  font-size: 12px;
  padding: 2px 6px;
}
.ai-link-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.ai-hint {
  margin: 0;
  font-size: 11px;
  color: var(--muted, #8a96a8);
  line-height: 1.35;
}
.ai-hint code {
  font-size: 10px;
  background: rgba(127, 127, 127, 0.15);
  padding: 0 3px;
  border-radius: 3px;
}
.ai-section-label {
  font-weight: 600;
  font-size: 12px;
}
/* Two columns: the labels are short, and a single column pushed the
   conversation log off the bottom of a narrow panel. */
.ai-templates {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 4px;
  max-height: 140px;
  overflow-y: auto;
  flex-shrink: 0;
}
.ai-tpl-btn {
  min-width: 0;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.ai-tpl-btn, .ai-btn {
  font-size: 12px;
  padding: 5px 8px;
  border-radius: 6px;
  border: 1px solid var(--border, #3a4658);
  background: var(--panel-btn-bg, #243044);
  color: var(--text, #e8eef7);
  cursor: pointer;
  text-align: left;
}
.ai-tpl-btn:disabled, .ai-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.ai-tpl-btn.gray:disabled {
  opacity: 0.35;
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
.ai-ask-btn {
  padding: 3px 10px;
  text-align: center;
}
.ai-log {
  flex: 1;
  min-height: 120px;
  overflow: auto;
  border: 1px solid var(--border, #3a4658);
  border-radius: 8px;
  padding: 8px;
  background: var(--panel-inset, #1a2230);
  font-size: 12px;
  line-height: 1.4;
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
  font-size: 12px;
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
  font-size: 10px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  margin-bottom: 4px;
}
.ai-msg.user .ai-msg-role { color: #6ea8e0; }
.ai-msg.assistant .ai-msg-role { color: #6fbf9a; }
.ai-msg-body {
  border-radius: 0 8px 8px 0;
  padding: 8px 10px;
  border: 1px solid #3a4658;
  border-left-width: 3px;
}
.ai-msg.user .ai-msg-body {
  color: #e8eef7;
  background: #1e3348;
  border-left-color: #5b9bd5;
}
.ai-msg.assistant .ai-msg-body {
  color: #d5e4f7;
  background: #1a2620;
  border-left-color: #3d9a72;
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
  background: rgba(0, 0, 0, 0.25);
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
  background: #2a2418;
  color: #e6d48a;
  border-radius: 0 6px 6px 0;
  font-size: 12px;
}
.ai-tool-card p { margin: 2px 0; }
.ai-tool-st { color: #8b98a8; }
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
  border-radius: 4px;
}
.ai-mermaid-zoom-links {
  margin: 10px 0 0;
  font-size: 12px;
}
.ai-mermaid-zoom-links :deep(a) {
  color: #5b9bd5;
}
.ai-input {
  width: 100%;
  box-sizing: border-box;
  resize: vertical;
  min-height: 64px;
  font-size: 12px;
  font-family: inherit;
  border-radius: 6px;
  border: 1px solid var(--border, #3a4658);
  background: var(--panel-inset, #1a2230);
  color: var(--text, #e8eef7);
  padding: 6px 8px;
}
.ai-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.ai-spacer { flex: 1; }
.ai-status {
  font-size: 11px;
  color: var(--muted, #8a96a8);
  min-height: 1.2em;
}
.ai-status.error { color: #e07070; }
</style>
