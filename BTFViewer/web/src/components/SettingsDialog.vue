<template>
  <div
    class="settings-overlay"
    @click.self="emit('close')"
  >
    <div
      class="settings-dialog"
      role="dialog"
      aria-modal="true"
      aria-label="Settings"
    >
      <div class="settings-header">
        <span class="settings-title">Settings</span>
        <button
          type="button"
          class="settings-close"
          aria-label="Close settings"
          @click="emit('close')"
        >
          ✕
        </button>
      </div>

      <div class="settings-body">
        <nav
          class="settings-nav"
          role="tablist"
          aria-label="Settings sections"
        >
          <button
            v-for="tab in tabs"
            :key="tab.id"
            type="button"
            class="settings-nav-btn"
            :class="{ active: activeTab === tab.id }"
            role="tab"
            :aria-selected="activeTab === tab.id"
            @click="activeTab = tab.id"
          >
            {{ tab.label }}
          </button>
        </nav>

        <div class="settings-content">
          <!-- Appearance -->
          <div
            v-show="activeTab === 'appearance'"
            class="settings-page"
          >
            <h3 class="settings-section">Appearance</h3>
            <label class="settings-row">
              <span class="settings-label">Theme</span>
              <select
                v-model="draft.darkMode"
                class="settings-input"
              >
                <option :value="true">Dark</option>
                <option :value="false">Light</option>
              </select>
            </label>
            <label class="settings-check">
              <input
                v-model="draft.colorblindSafe"
                type="checkbox"
              >
              Colorblind-safe colors (Okabe-Ito palette)
            </label>

            <h3 class="settings-section">Font sizes</h3>
            <label class="settings-row">
              <span class="settings-label">Timeline labels</span>
              <input
                v-model.number="draft.labelFontSize"
                class="settings-input"
                type="number"
                min="6"
                max="24"
                step="1"
              >
              <span
                class="settings-unit"
                title="CSS pixels. Desktop Settings use points; defaults look similar."
              >px</span>
            </label>
            <label class="settings-row">
              <span class="settings-label">UI / menus</span>
              <input
                v-model.number="draft.uiFontSize"
                class="settings-input"
                type="number"
                min="8"
                max="18"
                step="1"
              >
              <span
                class="settings-unit"
                title="CSS pixels. Desktop Settings use points; defaults look similar."
              >px</span>
            </label>
          </div>

          <!-- Display -->
          <div
            v-show="activeTab === 'display'"
            class="settings-page"
          >
            <h3 class="settings-section">Panels</h3>
            <label class="settings-check indent">
              <input
                v-model="draft.showLegend"
                type="checkbox"
              >
              Legend panel
            </label>
            <label class="settings-check indent">
              <input
                v-model="draft.showStats"
                type="checkbox"
              >
              Statistics panel
            </label>
            <label class="settings-check indent">
              <input
                v-model="draft.showMarks"
                type="checkbox"
              >
              Marks panel
            </label>
            <label class="settings-check indent">
              <input
                v-model="draft.showFind"
                type="checkbox"
              >
              Find panel
            </label>
            <label class="settings-check indent">
              <input
                v-model="draft.showAi"
                type="checkbox"
              >
              AI Assistant panel
            </label>
            <label class="settings-check indent">
              <input
                v-model="draft.showCpuLoad"
                type="checkbox"
              >
              CPU load graph
            </label>

            <h3 class="settings-section">Timeline overlays</h3>
            <label class="settings-check indent">
              <input
                v-model="draft.showSti"
                type="checkbox"
              >
              STI events
            </label>
            <label class="settings-check indent">
              <input
                v-model="draft.showGrid"
                type="checkbox"
              >
              Grid lines
            </label>
            <label class="settings-check indent">
              <input
                v-model="draft.hoverHighlight"
                type="checkbox"
              >
              Highlight segments on label hover
            </label>

            <h3 class="settings-section">Analysis thresholds</h3>
            <label class="settings-row">
              <span class="settings-label">CPU budget</span>
              <input
                v-model.number="draft.cpuBudgetPct"
                class="settings-input"
                type="number"
                min="0"
                max="100"
                step="0.1"
              >
              <span class="settings-unit">% (0 = off)</span>
            </label>
            <label class="settings-row col">
              <span class="settings-label">Task deadlines (ns)</span>
              <textarea
                v-model="deadlinesText"
                class="settings-textarea"
                rows="4"
                placeholder="TaskName=1000000&#10;Runner1=500000"
              />
            </label>
          </div>

          <!-- Layout -->
          <div
            v-show="activeTab === 'layout'"
            class="settings-page"
          >
            <h3 class="settings-section">Timeline</h3>
            <label class="settings-row">
              <span class="settings-label">Label column</span>
              <input
                v-model.number="draft.labelWidth"
                class="settings-input"
                type="number"
                min="60"
                max="600"
                step="10"
              >
              <span class="settings-unit">px</span>
            </label>
            <label class="settings-row">
              <span class="settings-label">Row height</span>
              <input
                v-model.number="draft.rowHeight"
                class="settings-input"
                type="number"
                min="12"
                max="60"
                step="1"
              >
              <span class="settings-unit">px</span>
            </label>
            <label class="settings-row">
              <span class="settings-label">Row gap</span>
              <input
                v-model.number="draft.rowGap"
                class="settings-input"
                type="number"
                min="0"
                max="20"
                step="1"
              >
              <span class="settings-unit">px</span>
            </label>

            <h3 class="settings-section">STI rows</h3>
            <label class="settings-row">
              <span class="settings-label">Collapsed height</span>
              <input
                v-model.number="draft.stiRowH"
                class="settings-input"
                type="number"
                min="12"
                max="60"
                step="1"
              >
              <span class="settings-unit">px</span>
            </label>
            <label class="settings-row">
              <span class="settings-label">Expanded height</span>
              <input
                v-model.number="draft.stiWaveformH"
                class="settings-input"
                type="number"
                min="40"
                max="300"
                step="4"
              >
              <span class="settings-unit">px</span>
            </label>
            <label class="settings-row">
              <span class="settings-label">Line style</span>
              <select
                v-model="draft.stiLineStyle"
                class="settings-input wide"
              >
                <option value="step">Step (hold value)</option>
                <option value="linear">Linear (point to point)</option>
              </select>
            </label>

            <h3 class="settings-section">Zoom &amp; cursors</h3>
            <label class="settings-row">
              <span class="settings-label">1:1 zoom level</span>
              <input
                v-model.number="draft.timescalePerPxDefault"
                class="settings-input"
                type="number"
                min="0.5"
                max="200"
                step="0.5"
              >
              <span class="settings-unit">{{ zoomUnit }}/px</span>
            </label>
            <label class="settings-row">
              <span class="settings-label">Max cursors</span>
              <input
                v-model.number="draft.maxCursors"
                class="settings-input"
                type="number"
                min="4"
                max="8"
                step="1"
              >
            </label>
            <label class="settings-row">
              <span class="settings-label">Time display precision</span>
              <input
                v-model.number="draft.timeDecimals"
                class="settings-input"
                type="number"
                min="0"
                max="9"
                step="1"
              >
              <span class="settings-unit">digits</span>
            </label>

            <h3 class="settings-section">CPU load graph</h3>
            <label class="settings-row">
              <span class="settings-label">Row height</span>
              <input
                v-model.number="draft.cpuLoadRowH"
                class="settings-input"
                type="number"
                min="16"
                max="120"
                step="2"
              >
              <span class="settings-unit">px</span>
            </label>
          </div>

          <!-- AI -->
          <div
            v-show="activeTab === 'ai'"
            class="settings-page"
          >
            <h3 class="settings-section">AI connection</h3>
            <label
              class="settings-check"
              title="When off, hides the AI tab. When on, the AI panel can send Analysis Findings to the configured endpoint."
            >
              <input
                v-model="draft.aiEnabled"
                type="checkbox"
              >
              Enable AI Assistant
            </label>
            <p class="settings-help">
              When off, the AI tab is hidden.
            </p>
            <label
              class="settings-check"
              title="When on, tool calls from the model update the timeline immediately. When off, the chat shows Apply / Skip on each action card and Apply GUI actions under the log."
            >
              <input
                v-model="draft.aiAutoApply"
                type="checkbox"
              >
              Auto-apply GUI actions
            </label>
            <label class="settings-row col">
              <span class="settings-label">Preset</span>
              <select
                v-model="aiPreset"
                class="settings-input wide"
                title="Ollama runs locally; OpenAI and Gemini are cloud APIs; Custom is any other OpenAI-compatible endpoint. Each preset keeps its own base URL, model, and API key."
              >
                <option
                  v-for="p in aiPresets"
                  :key="p.id"
                  :value="p.id"
                >
                  {{ p.label }}
                </option>
              </select>
            </label>
            <label class="settings-row col">
              <span class="settings-label">Base URL</span>
              <input
                v-model="aiBaseUrl"
                class="settings-input wide"
                type="url"
                title="OpenAI-compatible API root, e.g. http://localhost:11434/v1 for Ollama."
                :placeholder="activePresetInfo.baseUrl || 'http://localhost:11434/v1'"
              >
            </label>
            <label class="settings-row col">
              <span class="settings-label">Model</span>
              <div class="settings-model-wrap">
                <div
                  ref="aiModelComboEl"
                  class="settings-combobox"
                  :class="{ open: aiModelMenuOpen }"
                >
                  <input
                    v-model="aiModel"
                    class="settings-combo-input"
                    type="text"
                    role="combobox"
                    autocomplete="off"
                    :aria-expanded="aiModelMenuOpen ? 'true' : 'false'"
                    aria-controls="ai-model-listbox"
                    aria-autocomplete="list"
                    title="Model id served by that endpoint (e.g. `ollama list` name, gpt-4o-mini, or gemini-flash-lite-latest). Refresh to list models from GET /models, then open the dropdown to pick one."
                    :placeholder="activePresetInfo.model || 'phi4-mini:3.8b'"
                    @keydown="onAiModelKeydown"
                  >
                  <button
                    type="button"
                    class="settings-combo-toggle"
                    tabindex="-1"
                    :title="aiModelOptions.length
                      ? `Show ${aiModelOptions.length} model(s)`
                      : 'Refresh to list models from this endpoint'"
                    aria-label="Show model list"
                    @click="toggleAiModelMenu"
                  >
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      viewBox="0 0 16 16"
                      width="12"
                      height="12"
                      aria-hidden="true"
                    >
                      <path
                        fill="currentColor"
                        d="M4.2 6.2 8 10l3.8-3.8L13 7.4 8 12.4 3 7.4z"
                      />
                    </svg>
                  </button>
                </div>
                <Teleport to="body">
                  <ul
                    v-if="aiModelMenuOpen"
                    id="ai-model-listbox"
                    ref="aiModelListEl"
                    class="settings-combo-list"
                    role="listbox"
                    :style="aiModelListStyle"
                  >
                    <li
                      v-for="m in aiModelOptions"
                      :key="m"
                      role="option"
                      :aria-selected="m === String(aiModel || '').trim() ? 'true' : 'false'"
                      :class="{ selected: m === String(aiModel || '').trim() }"
                      :title="m"
                      @mousedown.prevent="selectAiModel(m)"
                    >
                      {{ m }}
                    </li>
                    <li
                      v-if="!aiModelOptions.length"
                      class="settings-combo-empty"
                      role="presentation"
                    >
                      Refresh to list models
                    </li>
                  </ul>
                </Teleport>
                <button
                  type="button"
                  class="settings-icon-btn"
                  :disabled="aiTesting || aiListing"
                  title="Refresh model list from this endpoint"
                  aria-label="Refresh model list"
                  @click="onRefreshModels"
                >
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    viewBox="0 0 16 16"
                    width="14"
                    height="14"
                    aria-hidden="true"
                  >
                    <path
                      fill="currentColor"
                      d="M8 1.25A6.75 6.75 0 1 0 14.75 8h-1.5A5.25 5.25 0 1 1 8 2.75V5.5L12 3 8 .5v.75z"
                    />
                  </svg>
                </button>
              </div>
            </label>
            <label class="settings-row col">
              <span class="settings-label">Authentication</span>
              <select
                v-model="aiAuthMode"
                class="settings-input wide"
                title="How this preset authenticates. None for a local server; API key to paste a provider key; Sign in opens the vendor page so you can log in and paste the key or token."
              >
                <option
                  v-for="[id, label] in aiAuthModes"
                  :key="id"
                  :value="id"
                >
                  {{ label }}
                </option>
              </select>
            </label>
            <div
              v-if="aiAuthMode !== 'none'"
              class="settings-ai-auth"
            >
              <span class="settings-label">{{ aiAuthMode === 'browser' ? 'Token' : 'API key' }}</span>
              <p class="settings-auth-status">
                {{ authStatusText }}
              </p>
              <input
                v-model="aiApiKey"
                class="settings-input wide"
                type="password"
                autocomplete="off"
                title="API key or access token for this preset (or VITE_OPENAI_API_KEY / VITE_GEMINI_API_KEY / VITE_OLLAMA_API_KEY at build time). Local Ollama needs none. Stored per preset in browser storage."
                :placeholder="aiAuthMode === 'browser'
                  ? 'Paste key or token after signing in'
                  : (isLocalPreset
                    ? 'Optional — local Ollama needs none'
                    : 'Required — provider API key')"
              >
              <div
                v-if="aiAuthMode === 'browser'"
                class="settings-ai-actions"
              >
                <button
                  type="button"
                  class="settings-btn secondary"
                  :title="'Open the provider sign-in or API-key page, then paste the key or token.'"
                  @click="onAiSignIn"
                >
                  {{ signInLabel }}
                </button>
                <button
                  v-if="aiApiKey"
                  type="button"
                  class="settings-btn secondary"
                  title="Clear the saved key or token for this preset."
                  @click="onAiLogout"
                >
                  Log out
                </button>
              </div>
            </div>

            <label class="settings-row col">
              <span class="settings-label">Reply language</span>
              <select
                v-model="draft.aiResponseLanguage"
                class="settings-input wide"
                title="Language for AI Assistant replies (also available via Language… in the AI panel)."
              >
                <option
                  v-for="lang in aiLanguageOptions"
                  :key="lang"
                  :value="lang"
                >
                  {{ lang }}
                </option>
              </select>
            </label>
            <div class="settings-ai-test">
              <div class="settings-ai-actions">
                <button
                  type="button"
                  class="settings-btn secondary"
                  :disabled="aiTesting"
                  title="List models and run a tiny chat probe against this endpoint. Status updates appear below — first model load can take a minute."
                  @click="onTestAi"
                >
                  {{ aiTesting ? 'Testing…' : 'Test connection' }}
                </button>
                <button
                  type="button"
                  class="settings-btn secondary"
                  title="Load preset, base URL, model, and API key from a JSON file (see examples/ai/gemini.json, openai.json, deepseek.json, grok.json)."
                  @click="aiImportInput?.click()"
                >
                  Import…
                </button>
                <input
                  ref="aiImportInput"
                  type="file"
                  accept="application/json,.json"
                  class="settings-file-input"
                  @change="onImportAiSettings"
                >
              </div>
              <p
                class="settings-test-status"
                :class="aiTestClass"
                role="status"
                aria-live="polite"
              >
                {{ aiTestStatus || 'Click Test connection to verify the endpoint and model.' }}
              </p>
            </div>
            <p
              v-if="isLocalPreset && aiAuthMode === 'none'"
              class="settings-help"
            >
              Ollama serves an OpenAI-compatible API at
              <code>http://localhost:11434/v1</code>. Pull a model first:
              <code>ollama pull phi4-mini:3.8b</code>. Prefer
              <code>npm run dev</code> / <code>preview</code> (proxies local Ollama);
              for <code>file://</code> use <code>OLLAMA_ORIGINS="*" ollama serve</code>
              (macOS app: <code>launchctl setenv OLLAMA_ORIGINS "*"</code>, then restart it).
            </p>
            <p
              v-else
              class="settings-help"
            >
              Any OpenAI-compatible endpoint works: set Base URL, model, and
              Authentication (API key or Sign in).
              <a
                v-if="activeKeyUrl"
                :href="activeKeyUrl"
                target="_blank"
                rel="noreferrer"
              >Get a {{ activePresetInfo.label }} key.</a>
              OpenAI and Gemini are proxied under <code>npm run dev</code> /
              <code>preview</code>; other hosts need CORS or the Desktop app.
              Context is Analysis Findings — not the raw BTF.
            </p>
          </div>
        </div>
      </div>

      <div class="settings-footer">
        <button
          type="button"
          class="settings-btn secondary"
          @click="onReset"
        >
          Reset to Defaults
        </button>
        <div class="settings-footer-spacer" />
        <button
          type="button"
          class="settings-btn secondary"
          @click="emit('close')"
        >
          Cancel
        </button>
        <button
          type="button"
          class="settings-btn primary"
          @click="onSave"
        >
          OK
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import {
  DEFAULT_SETTINGS,
  formatDeadlinesText,
  normalizeSettings,
  parseDeadlinesText,
  shouldReplaceDeadlinesText,
} from '../utils/settingsStore.js'
import {
  AI_AUTH_MODE_LABELS,
  AI_PRESETS,
  AI_PRESET_KEY_URLS,
  AI_PRESET_OLLAMA,
  AI_RESPONSE_LANGUAGES,
  aiAuthStatus,
  aiListModels,
  aiPresetInfo,
  aiPresetSignInLabel,
  aiPresetSignInUrl,
  aiTestConnection,
  normalizeAiAuthMode,
  normalizeAiPreset,
  parseAiSettingsJson,
  resolveAiSettings,
} from '../utils/ollamaClient.js'

const props = defineProps({
  modelValue: { type: Object, required: true },
  timeScale:  { type: String, default: 'ns' },
  initialTab: { type: String, default: 'appearance' },
})

const emit = defineEmits(['close', 'save', 'preview'])

const tabs = [
  { id: 'appearance', label: 'Appearance' },
  { id: 'display', label: 'Display' },
  { id: 'layout', label: 'Layout' },
  { id: 'ai', label: 'AI' },
]

const _tabIds = new Set(tabs.map(t => t.id))
const activeTab = ref(_tabIds.has(props.initialTab) ? props.initialTab : 'appearance')
const draft = reactive(normalizeSettings(props.modelValue))
const deadlinesText = ref(formatDeadlinesText(draft.taskDeadlines))
const aiPresets = AI_PRESETS
// Each preset keeps its own base URL / model / API key in draft.aiPresets;
// the inputs edit whichever preset is selected.
const aiPreset = computed({
  get: () => normalizeAiPreset(draft.aiPreset),
  set: (v) => { draft.aiPreset = normalizeAiPreset(v) },
})
const activePresetInfo = computed(() => aiPresetInfo(aiPreset.value))
const isLocalPreset = computed(() => aiPreset.value === AI_PRESET_OLLAMA)
const activeKeyUrl = computed(() => AI_PRESET_KEY_URLS[aiPreset.value] || '')
function presetField(field) {
  return computed({
    get: () => String(draft.aiPresets?.[aiPreset.value]?.[field] ?? ''),
    set: (v) => {
      const cur = draft.aiPresets?.[aiPreset.value] || {}
      draft.aiPresets = { ...draft.aiPresets, [aiPreset.value]: { ...cur, [field]: v } }
    },
  })
}
const aiBaseUrl = presetField('baseUrl')
const aiModel = presetField('model')
const aiApiKey = presetField('apiKey')
const aiAuthModes = AI_AUTH_MODE_LABELS
const aiAuthMode = computed({
  get: () => normalizeAiAuthMode(draft.aiPresets?.[aiPreset.value]?.authMode, {
    presetId: aiPreset.value,
    baseUrl: aiBaseUrl.value || activePresetInfo.value.baseUrl,
  }),
  set: (v) => {
    const cur = draft.aiPresets?.[aiPreset.value] || {}
    draft.aiPresets = {
      ...draft.aiPresets,
      [aiPreset.value]: {
        ...cur,
        authMode: normalizeAiAuthMode(v, { presetId: aiPreset.value }),
      },
    }
  },
})
const signInLabel = computed(() => aiPresetSignInLabel(aiPreset.value))
const authStatusText = computed(() => {
  const st = aiAuthStatus({
    authMode: aiAuthMode.value,
    apiKey: aiApiKey.value,
    baseUrl: aiBaseUrl.value || activePresetInfo.value.baseUrl,
    presetId: aiPreset.value,
  })
  if (aiAuthMode.value === 'none') return 'Local endpoint — no key needed.'
  if (aiAuthMode.value === 'browser') {
    return st.signedIn
      ? 'Signed in — token saved.'
      : 'Not signed in. Open the provider page, then paste the key or token below.'
  }
  return aiApiKey.value
    ? 'Key saved for this preset.'
    : 'Paste a provider API key, or set VITE_OPENAI_API_KEY / VITE_GEMINI_API_KEY at build time.'
})

function onAiSignIn() {
  const url = aiPresetSignInUrl(
    aiPreset.value,
    aiBaseUrl.value || activePresetInfo.value.baseUrl,
  )
  if (!url) {
    aiTestStatus.value = 'This preset has no sign-in page. Paste a token or set Base URL.'
    aiTestOk.value = false
    return
  }
  window.open(url, '_blank', 'noopener,noreferrer')
  aiTestStatus.value = `Opened ${url}. After you sign in, paste the key or token and Test.`
  aiTestOk.value = null
}

function onAiLogout() {
  aiApiKey.value = ''
  aiTestStatus.value = 'Cleared the saved token for this preset.'
  aiTestOk.value = null
}
const aiLanguageOptions = computed(() => {
  const cur = String(draft.aiResponseLanguage || '').trim()
  if (cur && !AI_RESPONSE_LANGUAGES.includes(cur)) {
    return [...AI_RESPONSE_LANGUAGES, cur]
  }
  return AI_RESPONSE_LANGUAGES
})
const aiTesting = ref(false)
const aiListing = ref(false)
const aiTestStatus = ref('')
const aiTestOk = ref(null)
const aiImportInput = ref(null)
const aiModelLists = reactive(
  Object.fromEntries(AI_PRESETS.map(p => [p.id, []])),
)
const aiModelOptions = computed(() => {
  const listed = aiModelLists[aiPreset.value] || []
  const cur = String(aiModel.value || '').trim()
  if (cur && !listed.includes(cur)) return [cur, ...listed]
  return listed
})
const aiModelComboEl = ref(null)
const aiModelListEl = ref(null)
const aiModelMenuOpen = ref(false)
const aiModelListStyle = ref({})
let aiModelMenuCloser = null
let aiAbort = null

function placeAiModelMenu() {
  const el = aiModelComboEl.value
  if (!el) return
  const r = el.getBoundingClientRect()
  const maxH = 220
  const gap = 2
  const spaceBelow = window.innerHeight - r.bottom - 8
  const spaceAbove = r.top - 8
  const openUp = spaceBelow < 120 && spaceAbove > spaceBelow
  const height = Math.min(maxH, Math.max(openUp ? spaceAbove : spaceBelow, 80))
  aiModelListStyle.value = openUp
    ? {
        position: 'fixed',
        left: `${Math.round(r.left)}px`,
        width: `${Math.round(r.width)}px`,
        bottom: `${Math.round(window.innerHeight - r.top + gap)}px`,
        maxHeight: `${Math.round(height)}px`,
        zIndex: 2600,
      }
    : {
        position: 'fixed',
        left: `${Math.round(r.left)}px`,
        width: `${Math.round(r.width)}px`,
        top: `${Math.round(r.bottom + gap)}px`,
        maxHeight: `${Math.round(height)}px`,
        zIndex: 2600,
      }
}

function bindAiModelMenuChrome(open) {
  if (aiModelMenuCloser) {
    document.removeEventListener('mousedown', aiModelMenuCloser)
    document.removeEventListener('scroll', placeAiModelMenu, true)
    window.removeEventListener('resize', placeAiModelMenu)
    aiModelMenuCloser = null
  }
  if (!open) return
  nextTick(() => {
    placeAiModelMenu()
    const sel = aiModelListEl.value?.querySelector('[aria-selected="true"]')
    sel?.scrollIntoView({ block: 'nearest' })
  })
  aiModelMenuCloser = (e) => {
    const t = e.target
    if (aiModelComboEl.value?.contains(t)) return
    if (aiModelListEl.value?.contains(t)) return
    aiModelMenuOpen.value = false
  }
  document.addEventListener('mousedown', aiModelMenuCloser)
  document.addEventListener('scroll', placeAiModelMenu, true)
  window.addEventListener('resize', placeAiModelMenu)
}

watch(aiModelMenuOpen, bindAiModelMenuChrome)
watch(aiPreset, () => { aiModelMenuOpen.value = false })

function toggleAiModelMenu() {
  aiModelMenuOpen.value = !aiModelMenuOpen.value
}

function selectAiModel(name) {
  aiModel.value = String(name || '')
  aiModelMenuOpen.value = false
}

function onAiModelKeydown(ev) {
  if (ev.key === 'ArrowDown' || ev.key === 'F4') {
    ev.preventDefault()
    aiModelMenuOpen.value = true
  } else if (ev.key === 'Escape' && aiModelMenuOpen.value) {
    ev.preventDefault()
    aiModelMenuOpen.value = false
  }
}

/** Apply an imported settings patch to the draft; returns a summary. */
function applyAiSettingsPatch(patch) {
  const presets = { ...draft.aiPresets }
  for (const [pid, fields] of Object.entries(patch.presets || {})) {
    presets[pid] = { ...(presets[pid] || {}), ...fields }
  }
  // Fixed preset order, so a multi-preset file always reads the same way.
  const touched = AI_PRESETS
    .filter((p) => patch.presets?.[p.id])
    .map((p) => p.label)
  draft.aiPresets = presets
  if (patch.responseLanguage) draft.aiResponseLanguage = patch.responseLanguage
  const preset = normalizeAiPreset(patch.preset || draft.aiPreset)
  draft.aiPreset = preset
  return `Imported ${touched.join(', ') || 'settings'}. `
    + `Selected ${aiPresetInfo(preset).label} — review, then OK to save.`
}

async function onImportAiSettings(event) {
  const input = event.target
  const file = input?.files?.[0]
  if (!file) return
  try {
    const patch = parseAiSettingsJson(await file.text())
    aiTestStatus.value = applyAiSettingsPatch(patch)
    aiTestOk.value = true
  } catch (err) {
    aiTestStatus.value = `Cannot import ${file.name}: ${err?.message || err}`
    aiTestOk.value = false
  } finally {
    // Allow re-importing the same file after an edit.
    input.value = ''
  }
}

const aiTestClass = computed(() => {
  if (aiTestOk.value === true) return 'ok'
  if (aiTestOk.value === false) return 'error'
  return ''
})

watch(() => props.modelValue, (v) => {
  suppressPreview.value = true
  Object.assign(draft, normalizeSettings(v))
  // Live preview round-trips parse incomplete lines to {}. Replacing the
  // textarea with that empty result made typing impossible — only sync when
  // the parsed deadlines actually changed (Reset / external load).
  if (shouldReplaceDeadlinesText(deadlinesText.value, draft.taskDeadlines)) {
    deadlinesText.value = formatDeadlinesText(draft.taskDeadlines)
  }
  nextTick(() => { suppressPreview.value = false })
}, { deep: true })

onMounted(() => {
  nextTick(() => { suppressPreview.value = false })
})

onUnmounted(() => {
  aiModelMenuOpen.value = false
  bindAiModelMenuChrome(false)
})

watch(draft, () => {
  if (suppressPreview.value) return
  clearTimeout(previewTimer)
  previewTimer = setTimeout(() => {
    const next = normalizeSettings({ ...draft, taskDeadlines: parseDeadlinesText(deadlinesText.value) })
    emit('preview', next)
  }, 50)
}, { deep: true })

watch(deadlinesText, () => {
  if (suppressPreview.value) return
  clearTimeout(previewTimer)
  previewTimer = setTimeout(() => {
    const next = normalizeSettings({ ...draft, taskDeadlines: parseDeadlinesText(deadlinesText.value) })
    emit('preview', next)
  }, 50)
})

const suppressPreview = ref(true)
let previewTimer = null

const zoomUnit = computed(() => {
  const ts = props.timeScale || 'ns'
  return ts === 'us' ? 'µs' : ts
})

function onReset() {
  Object.assign(draft, { ...DEFAULT_SETTINGS })
  deadlinesText.value = ''
  aiTestStatus.value = ''
  aiTestOk.value = null
  for (const pid of Object.keys(aiModelLists)) aiModelLists[pid] = []
  aiModelMenuOpen.value = false
}

async function onRefreshModels() {
  if (aiTesting.value || aiListing.value) return
  aiListing.value = true
  aiTestOk.value = null
  const active = resolveAiSettings(draft)
  aiTestStatus.value = `Listing models at ${active.baseUrl}…`
  if (aiAbort) aiAbort.abort()
  aiAbort = new AbortController()
  try {
    const names = (await aiListModels(active.baseUrl, {
      apiKey: active.apiKey,
      preset: active.preset,
      signal: aiAbort.signal,
    })).filter(Boolean).sort((a, b) => a.localeCompare(b, undefined, { sensitivity: 'base' }))
    aiModelLists[aiPreset.value] = names
    if (names.length) {
      aiTestOk.value = true
      aiTestStatus.value = `${names.length} model(s) from the endpoint. Open the Model dropdown to pick one.`
      aiModelMenuOpen.value = true
    } else {
      aiTestOk.value = false
      aiTestStatus.value = 'Endpoint listed no models.'
    }
  } catch (err) {
    if (err?.name === 'AbortError') {
      aiTestStatus.value = 'Cancelled'
      aiTestOk.value = null
    } else {
      aiTestOk.value = false
      aiTestStatus.value = err?.message || String(err)
    }
  } finally {
    aiListing.value = false
    aiAbort = null
  }
}

async function onTestAi() {
  if (aiTesting.value || aiListing.value) return
  aiTesting.value = true
  aiTestOk.value = null
  const active = resolveAiSettings(draft)
  aiTestStatus.value = `Starting test for ${active.baseUrl} / ${active.model}…`
  if (aiAbort) aiAbort.abort()
  aiAbort = new AbortController()
  try {
    const msg = await aiTestConnection({
      baseUrl: active.baseUrl,
      model: active.model,
      apiKey: active.apiKey,
      preset: active.preset,
      signal: aiAbort.signal,
      onProgress: (s) => {
        aiTestOk.value = null
        aiTestStatus.value = s
      },
    })
    aiTestOk.value = true
    aiTestStatus.value = msg
  } catch (err) {
    if (err?.name === 'AbortError') {
      aiTestStatus.value = 'Cancelled'
      aiTestOk.value = null
    } else {
      aiTestOk.value = false
      aiTestStatus.value = err?.message || String(err)
    }
  } finally {
    aiTesting.value = false
    aiAbort = null
  }
}

function onSave() {
  emit('save', normalizeSettings({
    ...draft,
    taskDeadlines: parseDeadlinesText(deadlinesText.value),
  }))
}
</script>

<style scoped>
.settings-overlay {
  position: fixed;
  inset: 0;
  z-index: 2500;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}
.settings-dialog {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 10px;
  min-width: min(580px, 92vw);
  max-width: 640px;
  max-height: min(85vh, 520px);
  display: flex;
  flex-direction: column;
  box-shadow: 0 12px 36px rgba(0, 0, 0, 0.45);
}
.settings-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
}
.settings-title {
  font-weight: 600;
  font-size: 15px;
}
.settings-close {
  border: none;
  background: transparent;
  color: var(--fg-dim);
  cursor: pointer;
  font-size: 16px;
  padding: 2px 6px;
  border-radius: 4px;
}
.settings-close:hover {
  background: var(--tb-btn-hover);
  color: var(--fg);
}
.settings-body {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
.settings-nav {
  flex: 0 0 132px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 10px 0;
  border-right: 1px solid var(--border);
  background: color-mix(in srgb, var(--panel-bg) 80%, var(--bg));
}
.settings-nav-btn {
  border: none;
  background: transparent;
  color: var(--fg-dim);
  text-align: left;
  padding: 9px 14px;
  font-size: var(--ui-font-size);
  cursor: pointer;
  border-left: 3px solid transparent;
}
.settings-nav-btn:hover {
  background: var(--tb-btn-hover);
  color: var(--fg);
}
.settings-nav-btn.active {
  background: color-mix(in srgb, var(--accent) 12%, transparent);
  color: var(--fg);
  border-left-color: var(--accent);
  font-weight: 600;
}
.settings-content {
  flex: 1;
  overflow: auto;
  padding: 14px 18px 16px;
}
.settings-page {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.settings-section {
  margin: 10px 0 4px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--fg-dim);
}
.settings-section:first-child {
  margin-top: 0;
}
.settings-ai-auth {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.settings-auth-status {
  margin: 0;
  font-size: 11px;
  line-height: 1.4;
  color: var(--fg-dim);
}
.settings-help {
  margin: 4px 0 0;
  font-size: 11px;
  line-height: 1.4;
  color: var(--fg-dim);
}
.settings-help code {
  font-size: 10px;
  background: rgba(127, 127, 127, 0.15);
  padding: 0 3px;
  border-radius: 3px;
}
.settings-ai-test {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
  margin-top: 4px;
}
.settings-ai-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.settings-file-input {
  display: none;
}
.settings-test-status {
  margin: 0;
  min-height: 2.8em;
  font-size: 11px;
  line-height: 1.4;
  color: var(--fg-dim);
  word-break: break-word;
}
.settings-test-status.ok { color: #1e8449; }
.settings-test-status.error { color: #c0392b; }
.settings-row {
  display: grid;
  grid-template-columns: 1fr 110px 36px;
  align-items: center;
  gap: 10px;
  font-size: var(--ui-font-size);
}
.settings-row.col {
  flex-direction: column;
  align-items: stretch;
}
.settings-textarea {
  width: 100%;
  min-height: 72px;
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--bg);
  color: var(--fg);
  font-size: 12px;
  font-family: monospace;
  resize: vertical;
}
.settings-label {
  color: var(--fg);
}
.settings-input {
  width: 110px;
  padding: 4px 8px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--tb-bg);
  color: var(--fg);
  font-size: var(--ui-font-size);
}
.settings-input.wide {
  width: 100%;
  max-width: 220px;
  grid-column: 2 / 4;
}
.settings-model-wrap {
  display: flex;
  align-items: stretch;
  gap: 6px;
  width: 100%;
  max-width: 280px;
  grid-column: 2 / 4;
}
.settings-combobox {
  position: relative;
  display: flex;
  align-items: stretch;
  flex: 1;
  min-width: 0;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--tb-bg);
}
.settings-combobox.open {
  border-color: var(--accent, #0e639c);
}
.settings-combo-input {
  flex: 1;
  min-width: 0;
  width: 100%;
  padding: 4px 4px 4px 8px;
  border: 0;
  background: transparent;
  color: var(--fg);
  font-size: var(--ui-font-size);
  outline: none;
}
.settings-combo-toggle {
  flex: 0 0 22px;
  width: 22px;
  padding: 0;
  border: 0;
  border-left: 1px solid var(--border);
  background: transparent;
  color: var(--fg);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.settings-combo-toggle:hover {
  background: var(--tb-btn-hover);
}
.settings-combo-list {
  margin: 0;
  padding: 4px 0;
  list-style: none;
  overflow: auto;
  background: var(--tb-bg);
  color: var(--fg);
  border: 1px solid var(--border);
  border-radius: 4px;
  box-shadow: 0 8px 20px rgba(0, 0, 0, 0.35);
  font-size: var(--ui-font-size);
}
.settings-combo-list li {
  padding: 4px 10px;
  cursor: pointer;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.settings-combo-list li:hover,
.settings-combo-list li.selected {
  background: color-mix(in srgb, var(--accent, #0e639c) 22%, transparent);
}
.settings-combo-empty {
  cursor: default;
  color: var(--fg-dim);
}
.settings-icon-btn {
  flex: 0 0 32px;
  width: 32px;
  padding: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  border: 1px solid var(--border);
  background: var(--tb-bg);
  color: var(--fg);
  cursor: pointer;
}
.settings-icon-btn:hover:not(:disabled) {
  background: var(--tb-btn-hover);
}
.settings-icon-btn:disabled {
  opacity: 0.5;
  cursor: default;
}
.settings-unit {
  color: var(--fg-dim);
  font-size: 12px;
  min-width: 36px;
}
.settings-check {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--ui-font-size);
  color: var(--fg);
  cursor: pointer;
}
.settings-check.indent {
  padding-left: 12px;
}
.settings-footer {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px 14px;
  border-top: 1px solid var(--border);
}
.settings-footer-spacer {
  flex: 1;
}
.settings-btn {
  border-radius: 5px;
  padding: 6px 18px;
  font-size: var(--ui-font-size);
  cursor: pointer;
  border: 1px solid var(--border);
}
.settings-btn.secondary {
  background: transparent;
  color: var(--fg-dim);
}
.settings-btn.secondary:hover {
  background: var(--tb-btn-hover);
  color: var(--fg);
}
.settings-btn.primary {
  background: var(--accent);
  border-color: var(--accent);
  color: #000;
  font-weight: 600;
}
.settings-btn.primary:hover {
  filter: brightness(1.08);
}
</style>
