<template>
  <div class="ai-panel">
    <div class="ai-header">
      <span class="ai-title">AI Assistant</span>
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
        @click="send"
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
        title="Configure Ollama"
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

    <p class="ai-hint">
      Uses Analysis Findings for the current Statistics scope. Local or cloud Ollama
      (prefer <code>npm run dev</code> / <code>preview</code> — proxies local Ollama;
      for <code>file://</code> set <code>OLLAMA_ORIGINS</code>).
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
        :title="t.prompt"
        :disabled="busy || !aiEnabled"
        @click="ask(t.prompt)"
      >
        {{ t.label }}
      </button>
    </div>

    <div
      ref="logRef"
      class="ai-log"
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
          v-html="formatMessage(m.content)"
          @click="onMsgClick"
        />
      </div>
    </div>

    <textarea
      v-model="draft"
      class="ai-input"
      rows="3"
      placeholder="Ask about this trace… (Ctrl/Cmd+Enter to send)"
      :disabled="busy || !aiEnabled"
      @keydown.meta.enter.prevent="send"
      @keydown.ctrl.enter.prevent="send"
    />

    <div
      class="ai-status"
      :class="{ error: !!error }"
    >
      {{ statusText }}
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import {
  AI_RESPONSE_LANGUAGES,
  AI_TEMPLATE_QUESTIONS,
  DEFAULT_AI_RESPONSE_LANGUAGE,
  DEFAULT_OLLAMA_MODEL,
  DEFAULT_OLLAMA_URL,
  extractJumpTimes,
  ollamaChat,
} from '../utils/ollamaClient.js'

const props = defineProps({
  aiEnabled: { type: Boolean, default: true },
  ollamaUrl: { type: String, default: DEFAULT_OLLAMA_URL },
  ollamaModel: { type: String, default: DEFAULT_OLLAMA_MODEL },
  ollamaApiKey: { type: String, default: '' },
  responseLanguage: { type: String, default: DEFAULT_AI_RESPONSE_LANGUAGE },
  /** () => Promise|{ findingsText, span, cores, scope } */
  getContext: { type: Function, required: true },
})

const emit = defineEmits(['openSettings', 'jump', 'update:responseLanguage'])

const templates = AI_TEMPLATE_QUESTIONS
const languages = AI_RESPONSE_LANGUAGES
const draft = ref('')
const messages = ref([])
const busy = ref(false)
const error = ref('')
const status = ref('')
const logRef = ref(null)
const langOpen = ref(false)
const langDraft = ref(props.responseLanguage || DEFAULT_AI_RESPONSE_LANGUAGE)
let abortCtrl = null

watch(() => props.responseLanguage, (v) => {
  langDraft.value = v || DEFAULT_AI_RESPONSE_LANGUAGE
})

watch(langOpen, (open) => {
  if (open) langDraft.value = props.responseLanguage || DEFAULT_AI_RESPONSE_LANGUAGE
})

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

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

function formatMessage(text) {
  const esc = escapeHtml(text)
  return esc
    .replace(/jump:([0-9]+(?:\.[0-9]+)?)/g, '<a href="#" data-jump="$1" class="ai-jump">jump:$1</a>')
    .replace(/\n/g, '<br>')
}

function onMsgClick(ev) {
  const a = ev.target?.closest?.('a[data-jump]')
  if (!a) return
  ev.preventDefault()
  const v = Number(a.getAttribute('data-jump'))
  if (Number.isFinite(v)) emit('jump', v)
}

async function scrollLog() {
  await nextTick()
  const el = logRef.value
  if (el) el.scrollTop = el.scrollHeight
}

function clear() {
  if (busy.value) stop()
  messages.value = []
  error.value = ''
  status.value = ''
}

function stop() {
  if (!busy.value || !abortCtrl) return
  status.value = 'Stopping…'
  error.value = ''
  abortCtrl.abort()
}

async function ask(prompt) {
  draft.value = prompt
  await send()
}

async function send() {
  const query = draft.value.trim()
  if (!query || busy.value || !props.aiEnabled) return
  messages.value.push({ role: 'user', content: query })
  draft.value = ''
  busy.value = true
  error.value = ''
  status.value = 'Waiting for Ollama…'
  await scrollLog()

  abortCtrl = new AbortController()
  try {
    const ctx = await Promise.resolve(props.getContext())
    const reply = await ollamaChat({
      query,
      findingsText: ctx?.findingsText || '',
      span: ctx?.span || '',
      cores: ctx?.cores ?? '',
      scope: ctx?.scope || '',
      metrics: ctx?.metrics || null,
      baseUrl: props.ollamaUrl,
      model: props.ollamaModel,
      apiKey: props.ollamaApiKey,
      responseLanguage: props.responseLanguage,
      signal: abortCtrl.signal,
    })
    messages.value.push({ role: 'assistant', content: reply })
    const jumps = extractJumpTimes(reply)
    status.value = jumps.length
      ? `Done. Click jump:${jumps[0]} links to open the timeline.`
      : 'Done.'
  } catch (err) {
    if (err?.name === 'AbortError') {
      status.value = 'Stopped.'
      error.value = ''
    } else {
      const msg = err?.message || String(err)
      messages.value.push({ role: 'assistant', content: `(Error) ${msg}` })
      error.value = msg.split('\n')[0].slice(0, 200)
    }
  } finally {
    busy.value = false
    abortCtrl = null
    await scrollLog()
  }
}

watch(() => props.aiEnabled, (on) => {
  if (!on) status.value = ''
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
}
.ai-header {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
.ai-title { font-weight: 600; font-size: 13px; }
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
.ai-templates {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 140px;
  overflow-y: auto;
  flex-shrink: 0;
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
.ai-empty { color: var(--muted, #8a96a8); }
.ai-msg { margin-bottom: 10px; }
.ai-msg-role {
  font-weight: 600;
  font-size: 11px;
  color: var(--muted, #8a96a8);
  margin-bottom: 2px;
}
.ai-msg.user .ai-msg-body { color: var(--text, #e8eef7); }
.ai-msg.assistant .ai-msg-body { color: var(--text, #d5e4f7); }
.ai-msg-body :deep(.ai-jump) {
  color: var(--accent, #5b9bd5);
  text-decoration: underline;
  cursor: pointer;
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
