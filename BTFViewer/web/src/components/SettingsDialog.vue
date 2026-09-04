<template>
  <div
    class="settings-overlay"
    :class="{ 'settings-overlay-free': dialogPos }"
    @click.self="onOverlayBackdropClick"
  >
    <div
      ref="dialogEl"
      class="settings-dialog"
      role="dialog"
      aria-modal="true"
      aria-label="Settings"
      :style="dialogStyle"
    >
      <div
        class="settings-header"
        @pointerdown="onHeaderPointerDown"
      >
        <span class="settings-title">Settings</span>
        <button
          type="button"
          class="app-close-x"
          title="Close"
          aria-label="Close settings"
          @pointerdown.stop
          @click="emit('close')"
        >×</button>
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
            <span
              class="settings-nav-ico"
              aria-hidden="true"
              v-html="NAV_ICONS[tab.id]"
            />
            <span class="settings-nav-lbl">{{ tab.label }}</span>
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
              <DomSelect
                v-model="draft.darkMode"
                class="settings-input"
                :options="themeOptions"
              />
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
            <label class="settings-check indent">
              <input
                v-model="draft.showIncidentOverlay"
                type="checkbox"
              >
              Timeline incident markers (findings + anomalies)
            </label>
            <label class="settings-check indent">
              <input
                v-model="draft.linkCompareViewports"
                type="checkbox"
              >
              Link A/B timeline zoom when switching compare tabs
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
              <DomSelect
                v-model="draft.stiLineStyle"
                class="settings-input wide"
                :options="stiLineStyleOptions"
              />
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
            class="settings-page settings-page--ai"
          >
            <h3 class="settings-section">AI connection</h3>
            <div class="settings-form">
              <div class="settings-form-row settings-form-row--check settings-form-row--top">
                <span
                  class="settings-form-label"
                  aria-hidden="true"
                ></span>
                <div class="settings-form-field">
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
                  <p class="settings-help settings-help--tight">
                    When off, the AI tab is hidden.
                  </p>
                </div>
              </div>
              <div class="settings-form-row settings-form-row--check">
                <span
                  class="settings-form-label"
                  aria-hidden="true"
                ></span>
                <label
                  class="settings-check"
                  title="When on, tool calls from the model update the timeline immediately. When off, the chat shows Apply / Skip on each action card."
                >
                  <input
                    v-model="draft.aiAutoApply"
                    type="checkbox"
                  >
                  Auto-apply GUI actions
                </label>
              </div>
              <div class="settings-form-row settings-form-row--top">
                <span class="settings-form-label">Context:</span>
                <div class="settings-form-field">
                  <DomSelect
                    v-model="draft.aiContextMode"
                    class="settings-input settings-input--grow"
                    :title="AI_CONTEXT_MODE_SETTINGS_TOOLTIP"
                    :options="aiContextModeOptions"
                  />
                  <p class="settings-help settings-help--tight settings-help--pre">
                    {{ aiContextSettingsHelp }}
                  </p>
                </div>
              </div>
              <div class="settings-form-row settings-form-row--check">
                <span
                  class="settings-form-label"
                  aria-hidden="true"
                ></span>
                <label
                  class="settings-check"
                  title="When the endpoint is not local, replace task names with Task-N aliases before Findings leave the machine."
                >
                  <input
                    v-model="draft.aiRedactTaskNames"
                    type="checkbox"
                  >
                  Anonymize task names for cloud
                </label>
              </div>
              <div class="settings-form-row settings-form-row--check">
                <span
                  class="settings-form-label"
                  aria-hidden="true"
                ></span>
                <label
                  class="settings-check"
                  title="Disables cloud AI for this machine. Local endpoints still work."
                >
                  <input
                    v-model="draft.aiTraceSensitive"
                    type="checkbox"
                  >
                  Treat this trace as sensitive
                </label>
              </div>

              <div class="settings-form-row">
                <span class="settings-form-label">Preset:</span>
                <DomSelect
                  v-model="aiPreset"
                  class="settings-input settings-input--grow"
                  title="Ollama runs locally; OpenAI and Gemini are cloud APIs; Custom is any other OpenAI-compatible endpoint. Importing a JSON file whose preset name is not in this list adds it. Each preset keeps its own base URL, model, and API key."
                  :options="aiPresetOptions"
                />
              </div>

              <div class="settings-form-row">
                <span class="settings-form-label">Base URL:</span>
                <input
                  v-model="aiBaseUrl"
                  class="settings-input settings-input--grow"
                  type="url"
                  title="OpenAI-compatible API root, e.g. http://localhost:11434/v1 for Ollama."
                  :placeholder="activePresetInfo.baseUrl || 'http://localhost:11434/v1'"
                >
              </div>

              <div class="settings-form-row">
                <span class="settings-form-label">Model:</span>
                <div class="settings-model-wrap settings-model-wrap--grow">
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
                      :placeholder="activePresetInfo.model || DEFAULT_AI_MODEL"
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
              </div>

              <div class="settings-form-row">
                <span class="settings-form-label">Authentication:</span>
                <DomSelect
                  v-model="aiAuthMode"
                  class="settings-input settings-input--grow"
                  title="How this preset authenticates. None for a local server; API key to paste a provider key; Sign in opens the vendor page so you can log in and paste the key or token."
                  :options="aiAuthModeOptions"
                />
              </div>

              <div
                v-if="aiAuthMode !== 'none'"
                class="settings-form-row settings-form-row--top"
              >
                <span class="settings-form-label">{{ aiAuthMode === 'browser' ? 'Token:' : 'API key:' }}</span>
                <div class="settings-ai-auth">
                  <p class="settings-auth-status">
                    {{ authStatusText }}
                  </p>
                  <input
                    v-model="aiApiKey"
                    class="settings-input settings-input--grow"
                    type="password"
                    autocomplete="off"
                    title="API key or access token for this preset (or OPENAI_API_KEY / GEMINI_API_KEY / OLLAMA_API_KEY). Local Ollama needs none. Stored per preset in browser storage."
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
              </div>

              <div class="settings-form-row">
                <span class="settings-form-label">Reply language:</span>
                <DomSelect
                  v-model="draft.aiResponseLanguage"
                  class="settings-input settings-input--grow"
                  title="Language for AI Assistant replies (also available via Language… in the AI panel)."
                  :options="aiLanguageOptions"
                />
              </div>

              <div class="settings-form-row settings-form-row--check">
                <span
                  class="settings-form-label"
                  aria-hidden="true"
                ></span>
                <div class="settings-ai-actions">
                  <button
                    type="button"
                    class="settings-btn secondary"
                    :disabled="aiTesting"
                    title="List models and run a tiny chat probe against this endpoint. Status updates appear below — first model load can take a couple of minutes."
                    @click="onTestAi"
                  >
                    {{ aiTesting ? 'Testing…' : 'Test connection' }}
                  </button>
                  <button
                    type="button"
                    class="settings-btn secondary"
                    title="Load preset, checkbox flags, base URL, model, API key, and auth mode from a JSON file. Unknown preset names are added to the list (see examples/ai/ollama.json, gemini.json, openai.json, deepseek.json, grok.json, presets.json)."
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
              </div>

              <div class="settings-form-row settings-form-row--span">
                <p
                  class="settings-test-status"
                  :class="aiTestClass"
                  role="status"
                  aria-live="polite"
                >
                  {{ aiTestStatus || 'Click Test connection to verify the endpoint and model.' }}
                </p>
              </div>

              <div class="settings-form-row settings-form-row--span">
                <p
                  v-if="isLocalPreset && aiAuthMode === 'none'"
                  class="settings-help"
                >
                  Ollama serves an OpenAI-compatible API at
                  <code>http://localhost:11434/v1</code>. Pull a model first:
                  <code>ollama pull {{ DEFAULT_AI_MODEL }}</code>. Prefer
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
import DomSelect from './DomSelect.vue'
import {
  formatDeadlinesText,
  normalizeSettings,
  parseDeadlinesText,
  shouldReplaceDeadlinesText,
} from '../utils/settingsStore.js'
import {
  defaultSectionCollapsed,
  defaultStatsSectionOrder,
} from '../utils/statsPins.js'
import {
  AI_AUTH_MODE_LABELS,
  AI_PRESETS,
  AI_PRESET_KEY_URLS,
  AI_PRESET_OLLAMA,
  AI_RESPONSE_LANGUAGES,
  BUILTIN_AI_PRESET_IDS,
  DEFAULT_AI_MODEL,
  aiAuthStatus,
  aiListModels,
  aiPresetDisplayLabel,
  aiPresetInfo,
  aiPresetSignInLabel,
  aiPresetSignInUrl,
  aiTestConnection,
  normalizeAiAuthMode,
  normalizeAiPreset,
  parseAiSettingsJson,
  parseExtraAiPresets,
  resolveAiSettings,
  sanitizeAiPresetId,
} from '../utils/aiClient.js'
import {
  AI_CONTEXT_MODE_LABELS,
  AI_CONTEXT_MODES,
  AI_CONTEXT_MODE_SETTINGS_TOOLTIP,
  aiContextModeSettingsOverview,
} from '../utils/aiCase.js'

const props = defineProps({
  modelValue: { type: Object, required: true },
  timeScale:  { type: String, default: 'ns' },
  initialTab: { type: String, default: 'appearance' },
})

const emit = defineEmits(['close', 'save', 'preview'])
let resetLayout = false
const dialogEl = ref(null)
const dialogPos = ref(null)
let _drag = null
let _ignoreOverlayClick = false

function clampDialogPos(x, y) {
  const el = dialogEl.value
  const w = el?.offsetWidth || 0
  const h = el?.offsetHeight || 0
  const pad = 8
  const maxX = Math.max(pad, window.innerWidth - w - pad)
  const maxY = Math.max(pad, window.innerHeight - h - pad)
  return {
    x: Math.min(Math.max(pad, x), maxX),
    y: Math.min(Math.max(pad, y), maxY),
  }
}

const dialogStyle = computed(() => {
  if (!dialogPos.value) return {}
  return {
    position: 'fixed',
    left: `${dialogPos.value.x}px`,
    top: `${dialogPos.value.y}px`,
    margin: '0',
  }
})

function onHeaderPointerDown(ev) {
  if (ev.pointerType === 'mouse' && ev.button !== 0) return
  if (ev.target.closest('button')) return
  const el = dialogEl.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  _drag = { dx: ev.clientX - rect.left, dy: ev.clientY - rect.top, moved: false }
  dialogPos.value = { x: rect.left, y: rect.top }
  window.addEventListener('pointermove', onDialogPointerMove)
  window.addEventListener('pointerup', onDialogPointerUp)
  ev.preventDefault()
}

function onDialogPointerMove(ev) {
  if (!_drag) return
  _drag.moved = true
  dialogPos.value = clampDialogPos(ev.clientX - _drag.dx, ev.clientY - _drag.dy)
}

function onDialogPointerUp() {
  const moved = !!_drag?.moved
  _drag = null
  window.removeEventListener('pointermove', onDialogPointerMove)
  window.removeEventListener('pointerup', onDialogPointerUp)
  if (moved) {
    _ignoreOverlayClick = true
    requestAnimationFrame(() => { _ignoreOverlayClick = false })
  }
}

function onOverlayBackdropClick() {
  if (_ignoreOverlayClick) return
  emit('close')
}

const tabs = [
  { id: 'appearance', label: 'Appearance' },
  { id: 'display', label: 'Display' },
  { id: 'layout', label: 'Layout' },
  { id: 'ai', label: 'AI' },
]

// Bootstrap-icon glyphs (16-viewBox, currentColor). Category set: circle-half
// (Appearance) / display (Display) / columns-gap (Layout) / robot (AI).
// Mirrored verbatim in btf_viewer_pkg/config.py _IC_SET_* — keep in sync.
const svgIco = (d) =>
  `<svg viewBox="0 0 16 16" width="15" height="15" fill="currentColor"><path d="${d}"/></svg>`
const NAV_ICONS = {
  appearance: svgIco('M8 15A7 7 0 1 0 8 1v14zm0 1A8 8 0 1 1 8 0a8 8 0 0 1 0 16z'),
  display: svgIco('M0 4s0-2 2-2h12s2 0 2 2v6s0 2-2 2h-4c0 .667.083 1.167.25 1.5H11a.5.5 0 0 1 0 1H5a.5.5 0 0 1 0-1h.75c.167-.333.25-.833.25-1.5H2s-2 0-2-2V4z'),
  layout: svgIco('M6 1v3H1V1h5zM1 0a1 1 0 0 0-1 1v3a1 1 0 0 0 1 1h5a1 1 0 0 0 1-1V1a1 1 0 0 0-1-1H1zm14 12v3h-5v-3h5zm-5-1a1 1 0 0 0-1 1v3a1 1 0 0 0 1 1h5a1 1 0 0 0 1-1v-3a1 1 0 0 0-1-1h-5zM6 8v7H1V8h5zM1 7a1 1 0 0 0-1 1v7a1 1 0 0 0 1 1h5a1 1 0 0 0 1-1V8a1 1 0 0 0-1-1H1zm14-6v7h-5V1h5zm-5-1a1 1 0 0 0-1 1v7a1 1 0 0 0 1 1h5a1 1 0 0 0 1-1V1a1 1 0 0 0-1-1h-5z'),
  ai: svgIco('M6 12.5a.5.5 0 0 1 .5-.5h3a.5.5 0 0 1 0 1h-3a.5.5 0 0 1-.5-.5ZM3 8.062C3 6.76 4.235 5.765 5.53 5.886a26.58 26.58 0 0 0 4.94 0C11.765 5.765 13 6.76 13 8.062v1.157a.933.933 0 0 1-.765.935c-.845.147-2.34.346-4.235.346-1.895 0-3.39-.2-4.235-.346A.933.933 0 0 1 3 9.219V8.062Zm4.542-.827a.25.25 0 0 0-.217.068l-.92.9a24.767 24.767 0 0 1-1.871-.183.25.25 0 0 0-.068.495c.55.076 1.232.149 2.02.193a.25.25 0 0 0 .189-.071l.754-.736.847 1.71a.25.25 0 0 0 .404.062l.932-.97a25.286 25.286 0 0 0 1.922-.188.25.25 0 0 0-.068-.495c-.538.074-1.207.145-1.976.189a.25.25 0 0 0-.166.076l-.754.785-.842-1.7a.25.25 0 0 0-.182-.135ZM8.5 1.866a1 1 0 1 0-1 0V3h-2A4.5 4.5 0 0 0 1 7.5V8a1 1 0 0 0-1 1v2a1 1 0 0 0 1 1v1a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-1a1 1 0 0 0 1-1V9a1 1 0 0 0-1-1v-.5A4.5 4.5 0 0 0 10.5 3h-2V1.866ZM14 7.5V13a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V7.5A3.5 3.5 0 0 1 5.5 4h5A3.5 3.5 0 0 1 14 7.5Z'),
}
const aiContextModes = AI_CONTEXT_MODES.map((id) => ({
  id,
  label: AI_CONTEXT_MODE_LABELS[id] || id,
}))
const aiContextSettingsHelp = aiContextModeSettingsOverview()

const _tabIds = new Set(tabs.map(t => t.id))
const activeTab = ref(_tabIds.has(props.initialTab) ? props.initialTab : 'appearance')
const draft = reactive(normalizeSettings(props.modelValue))
const deadlinesText = ref(formatDeadlinesText(draft.taskDeadlines))
const aiPresets = computed(() => {
  const extra = parseExtraAiPresets(draft.aiExtraPresets)
  const seen = new Set(AI_PRESETS.map((p) => p.id))
  const rows = [...AI_PRESETS]
  for (const e of extra) {
    const id = sanitizeAiPresetId(e.id)
    if (!id || seen.has(id)) continue
    seen.add(id)
    rows.push({
      id,
      label: e.label || aiPresetDisplayLabel(id),
      baseUrl: '',
      model: '',
    })
  }
  return rows
})
// Each preset keeps its own base URL / model / API key in draft.aiPresets;
// the inputs edit whichever preset is selected.
const aiPreset = computed({
  get: () => normalizeAiPreset(draft.aiPreset),
  set: (v) => { draft.aiPreset = normalizeAiPreset(v) },
})
const activePresetInfo = computed(() => (
  aiPresets.value.find((p) => p.id === aiPreset.value)
  || aiPresetInfo(aiPreset.value, draft.aiExtraPresets)
))
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
    : 'Paste a provider API key, or set OPENAI_API_KEY / GEMINI_API_KEY / OLLAMA_API_KEY.'
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
const themeOptions = [
  { value: true, label: 'Dark' },
  { value: false, label: 'Light' },
]
const stiLineStyleOptions = [
  { value: 'step', label: 'Step (hold value)' },
  { value: 'linear', label: 'Linear (point to point)' },
]
const aiContextModeOptions = computed(() =>
  aiContextModes.map(m => ({ value: m.id, label: m.label })))
const aiPresetOptions = computed(() =>
  aiPresets.value.map(p => ({ value: p.id, label: p.label })))
const aiAuthModeOptions = computed(() =>
  aiAuthModes.map(([id, label]) => ({ value: id, label })))
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
  const maxH = 280
  const gap = 2
  const spaceBelow = window.innerHeight - r.bottom - 8
  const spaceAbove = r.top - 8
  const openUp = spaceBelow < 140 && spaceAbove > spaceBelow
  const height = Math.min(maxH, Math.max(openUp ? spaceAbove : spaceBelow, 100))
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
  const extra = [...parseExtraAiPresets(draft.aiExtraPresets)]
  const seen = new Set(extra.map((e) => e.id))
  for (const row of (patch.extraPresets || [])) {
    const id = sanitizeAiPresetId(row.id)
    if (!id || BUILTIN_AI_PRESET_IDS.has(id) || seen.has(id)) continue
    extra.push({ id, label: row.label || aiPresetDisplayLabel(id) })
    seen.add(id)
  }
  for (const [pid, fields] of Object.entries(patch.presets || {})) {
    const id = sanitizeAiPresetId(pid) || pid
    if (id && !BUILTIN_AI_PRESET_IDS.has(id) && !seen.has(id)) {
      extra.push({ id, label: aiPresetDisplayLabel(id) })
      seen.add(id)
    }
    presets[id] = { ...(presets[id] || {}), ...fields }
  }
  draft.aiExtraPresets = extra
  // Builtins first, then extras in list order, so a multi-preset file reads the same way.
  const catalog = [
    ...AI_PRESETS.map((p) => p.id),
    ...extra.map((e) => e.id),
  ]
  const touched = catalog
    .filter((id) => patch.presets?.[id])
    .map((id) => (
      AI_PRESETS.find((p) => p.id === id)?.label
      || extra.find((e) => e.id === id)?.label
      || aiPresetDisplayLabel(id)
    ))
  draft.aiPresets = presets
  if (patch.responseLanguage) draft.aiResponseLanguage = patch.responseLanguage
  if (patch.aiEnabled != null) draft.aiEnabled = !!patch.aiEnabled
  if (patch.aiAutoApply != null) draft.aiAutoApply = !!patch.aiAutoApply
  if (patch.aiContextMode) draft.aiContextMode = patch.aiContextMode
  if (patch.aiRedactTaskNames != null) draft.aiRedactTaskNames = !!patch.aiRedactTaskNames
  if (patch.aiTraceSensitive != null) draft.aiTraceSensitive = !!patch.aiTraceSensitive
  const preset = normalizeAiPreset(patch.preset || draft.aiPreset)
  draft.aiPreset = preset
  const added = extra
    .filter((e) => (patch.extraPresets || []).some((row) => row.id === e.id))
    .map((e) => e.label)
  const extraNote = added.length ? ` Added ${added.join(', ')} to the preset list.` : ''
  return `Imported ${touched.join(', ') || 'settings'}. `
    + `Selected ${aiPresetInfo(preset, extra).label} — review, then OK to save.`
    + extraNote
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
  onDialogPointerUp()
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
  resetLayout = true
  const next = normalizeSettings(null)
  next.statsPinnedSections = []
  next.statsSectionOrder = defaultStatsSectionOrder()
  next.statsSectionCollapsed = defaultSectionCollapsed()
  Object.assign(draft, next)
  deadlinesText.value = ''
  aiTestStatus.value = ''
  aiTestOk.value = null
  for (const pid of Object.keys(aiModelLists)) aiModelLists[pid] = []
  aiModelMenuOpen.value = false
  clearTimeout(previewTimer)
  emit('preview', normalizeSettings({
    ...draft,
    statsPinnedSections: [],
    statsSectionOrder: defaultStatsSectionOrder(),
    statsSectionCollapsed: defaultSectionCollapsed(),
    taskDeadlines: {},
  }))
}

function onSave() {
  const payload = normalizeSettings({
    ...draft,
    taskDeadlines: parseDeadlinesText(deadlinesText.value),
  })
  if (resetLayout) {
    payload.statsPinnedSections = []
    payload.statsSectionOrder = defaultStatsSectionOrder()
    payload.statsSectionCollapsed = defaultSectionCollapsed()
    payload.resetLayout = true
  }
  emit('save', payload, { resetLayout })
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
      tlsVerify: active.tlsVerify,
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
      tlsVerify: active.tlsVerify,
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

</script>

<style scoped>
.settings-overlay {
  position: fixed;
  inset: 0;
  z-index: 2500;
  background: color-mix(in srgb, #000 48%, transparent);
  backdrop-filter: blur(5px) saturate(1.1);
  -webkit-backdrop-filter: blur(5px) saturate(1.1);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}
.settings-overlay-free {
  display: block;
  padding: 0;
}
.settings-dialog {
  background: var(--bg);
  border: 1px solid var(--app-border-soft, var(--border));
  border-radius: 14px;
  /* Fixed size for every settings group — tab switches must not resize.
     Wide enough for AI controls at 2× the desktop 240px field width. */
  width: min(780px, 94vw);
  height: min(520px, 85vh);
  display: flex;
  flex-direction: column;
  box-shadow:
    0 32px 80px -16px rgba(0, 0, 0, 0.5),
    0 0 0 1px color-mix(in srgb, var(--fg) 6%, transparent);
  overflow: hidden;
  animation: settings-pop 0.18s cubic-bezier(0.32, 0.72, 0, 1);
}
@keyframes settings-pop {
  from { opacity: 0; transform: translateY(10px) scale(0.98); }
  to   { opacity: 1; transform: none; }
}
.settings-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 13px 14px 13px 18px;
  border-bottom: 1px solid var(--app-border-soft, var(--border));
  background: color-mix(in srgb, var(--panel-bg) 60%, var(--bg));
  cursor: grab;
  user-select: none;
}
.settings-header:active {
  cursor: grabbing;
}
.settings-title {
  font-weight: 650;
  font-size: 15px;
  letter-spacing: 0.01em;
}
.settings-body {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
.settings-nav {
  flex: 0 0 148px;
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 12px 10px;
  border-right: 1px solid var(--app-border-soft, var(--border));
  background: color-mix(in srgb, var(--panel-bg) 80%, var(--bg));
}
.settings-nav-btn {
  position: relative;
  display: flex;
  align-items: center;
  gap: 9px;
  border: none;
  background: transparent;
  color: var(--fg-dim);
  text-align: left;
  padding: 8px 10px;
  border-radius: 8px;
  font-size: var(--ui-font-size);
  cursor: pointer;
  transition: background 0.14s ease, color 0.14s ease;
}
.settings-nav-ico {
  display: inline-flex;
  flex: 0 0 auto;
  opacity: 0.75;
}
.settings-nav-lbl { line-height: 1; }
.settings-nav-btn:hover {
  background: var(--tb-btn-hover);
  color: var(--fg);
}
.settings-nav-btn:focus-visible {
  outline: none;
  box-shadow: 0 0 0 2px var(--accent);
}
.settings-nav-btn.active {
  background: color-mix(in srgb, var(--accent) 14%, transparent);
  color: var(--fg);
  font-weight: 600;
}
.settings-nav-btn.active .settings-nav-ico {
  opacity: 1;
  color: var(--accent);
}
.settings-nav-btn.active::before {
  content: "";
  position: absolute;
  left: -10px;
  top: 50%;
  transform: translateY(-50%);
  width: 3px;
  height: 18px;
  border-radius: 0 3px 3px 0;
  background: var(--accent);
}
.settings-content {
  flex: 1;
  overflow: auto;
  padding: 18px 22px 20px;
}
.settings-page {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.settings-page--ai {
  gap: 8px;
  max-width: 100%;
  /* Double the desktop wide-combo (240px); all AI fields share this width. */
  --ai-control-width: 480px;
}
.settings-form {
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: 100%;
}
.settings-form-row {
  display: grid;
  grid-template-columns: 110px var(--ai-control-width, 480px);
  column-gap: 12px;
  align-items: center;
  width: 100%;
  justify-content: start;
}
.settings-form-row--top {
  align-items: start;
}
.settings-form-row--check {
  align-items: center;
  grid-template-columns: 110px var(--ai-control-width, 480px);
}
.settings-form-row--span {
  grid-template-columns: 1fr;
}
.settings-form-label {
  text-align: right;
  color: var(--fg);
  font-size: var(--ui-font-size);
  line-height: 1.3;
  padding-top: 1px;
}
.settings-form-row--top .settings-form-label {
  padding-top: 6px;
}
.settings-form-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  width: 100%;
}
.settings-help--tight {
  margin: 0;
}
.settings-help--pre {
  white-space: pre-line;
}
.settings-model-wrap--grow {
  grid-column: auto;
  box-sizing: border-box;
}
.settings-page--ai .settings-combobox {
  min-width: 0;
  flex: 1 1 auto;
}
.settings-page--ai .settings-combo-input {
  overflow-x: auto;
  text-overflow: clip;
  white-space: nowrap;
}
.settings-page--ai .settings-input.settings-input--grow.dom-select {
  overflow: hidden;
  text-overflow: ellipsis;
}
.settings-section {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 18px 0 8px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--fg-dim);
}
.settings-section::after {
  content: "";
  flex: 1;
  height: 1px;
  background: var(--app-border-soft, var(--border));
}
.settings-section:first-child {
  margin-top: 0;
}
.settings-ai-auth {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 6px;
  width: var(--ai-control-width, 480px);
  max-width: 100%;
  min-width: 0;
  box-sizing: border-box;
}
.settings-auth-status {
  margin: 0;
  font-size: 11px;
  line-height: 1.4;
  color: var(--fg-dim);
  word-break: break-word;
}
.settings-help {
  margin: 4px 0 0;
  font-size: 11px;
  line-height: 1.45;
  color: var(--fg-dim);
  word-break: break-word;
  overflow-wrap: anywhere;
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
  align-items: stretch;
  gap: 6px;
  margin-top: 4px;
  width: 100%;
}
.settings-ai-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
.settings-file-input {
  display: none;
}
.settings-test-status {
  margin: 0;
  min-height: 40px;
  font-size: 11px;
  line-height: 1.45;
  color: var(--fg-dim);
  word-break: break-word;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
  padding: 4px 0;
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
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 4px;
  width: 100%;
}
.settings-row.col .settings-label {
  flex: 0 0 auto;
  line-height: 1.3;
  color: var(--fg-dim);
  font-size: 12px;
  text-align: left;
}
.settings-row.col .settings-input.wide,
.settings-row.col .settings-model-wrap,
.settings-row.col .settings-textarea {
  width: 100%;
  max-width: none;
  grid-column: auto;
  box-sizing: border-box;
}
.settings-textarea {
  width: 100%;
  min-height: 72px;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--bg);
  color: var(--fg);
  font-size: 12px;
  font-family: var(--font-mono, monospace);
  resize: vertical;
  transition: border-color 0.14s ease, box-shadow 0.14s ease;
}
.settings-textarea:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 24%, transparent);
}
.settings-label {
  color: var(--fg);
  /* Right-align like the AI page's .settings-form-label and the desktop
     QFormLayout, so the label hugs its control on every page. */
  text-align: right;
}
.settings-input {
  width: 110px;
  padding: 5px 10px;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--tb-bg);
  color: var(--fg);
  font-size: var(--ui-font-size);
  transition: border-color 0.14s ease, box-shadow 0.14s ease;
}
.settings-input:focus,
.settings-input:focus-within {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 24%, transparent);
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
.settings-row.col .settings-model-wrap {
  max-width: none;
}
/* AI: Preset / Base URL / Auth / Model / Language — one shared width (2× desktop 240). */
.settings-page--ai .settings-input.settings-input--grow,
.settings-page--ai .settings-model-wrap.settings-model-wrap--grow,
.settings-page--ai .settings-ai-auth {
  width: var(--ai-control-width, 480px);
  max-width: 100%;
  min-width: 0;
  box-sizing: border-box;
}
.settings-page--ai .settings-model-wrap.settings-model-wrap--grow {
  grid-column: auto;
}
.settings-page--ai .settings-ai-auth .settings-input.settings-input--grow {
  width: 100%;
  max-width: none;
}
.settings-combobox {
  position: relative;
  display: flex;
  align-items: stretch;
  flex: 1;
  min-width: 0;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--tb-bg);
  transition: border-color 0.14s ease, box-shadow 0.14s ease;
}
.settings-combobox:focus-within,
.settings-combobox.open {
  border-color: var(--accent, #0e639c);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 24%, transparent);
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
  padding: 5px;
  list-style: none;
  overflow: auto;
  background: var(--tb-bg);
  color: var(--fg);
  border: 1px solid var(--app-border-soft, var(--border));
  border-radius: 9px;
  box-shadow: 0 16px 40px -10px rgba(0, 0, 0, 0.4),
              0 0 0 1px color-mix(in srgb, var(--fg) 5%, transparent);
  font-size: var(--ui-font-size);
}
.settings-combo-list li {
  padding: 6px 10px;
  border-radius: 6px;
  cursor: pointer;
  white-space: normal;
  overflow-wrap: anywhere;
  word-break: break-word;
  line-height: 1.35;
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
  border-radius: 7px;
  border: 1px solid var(--border);
  background: var(--tb-bg);
  color: var(--fg);
  cursor: pointer;
  transition: background 0.14s ease, border-color 0.14s ease;
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
  gap: 10px;
  font-size: var(--ui-font-size);
  color: var(--fg);
  cursor: pointer;
}
.settings-check.indent {
  padding-left: 12px;
}
/* Checkbox → toggle switch */
.settings-check input[type="checkbox"] {
  appearance: none;
  -webkit-appearance: none;
  flex: 0 0 auto;
  position: relative;
  width: 34px;
  height: 20px;
  margin: 0;
  border-radius: 999px;
  background: color-mix(in srgb, var(--fg-dim) 45%, transparent);
  border: 1px solid var(--app-border-soft, var(--border));
  cursor: pointer;
  transition: background 0.16s ease, border-color 0.16s ease;
}
.settings-check input[type="checkbox"]::after {
  content: "";
  position: absolute;
  top: 50%;
  left: 2px;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #fff;
  transform: translateY(-50%);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.35);
  transition: transform 0.16s cubic-bezier(0.32, 0.72, 0, 1);
}
.settings-check input[type="checkbox"]:checked {
  background: var(--accent);
  border-color: var(--accent);
}
.settings-check input[type="checkbox"]:checked::after {
  transform: translate(14px, -50%);
}
.settings-check input[type="checkbox"]:focus-visible {
  outline: none;
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 28%, transparent);
}
.settings-footer {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px 14px;
  border-top: 1px solid var(--app-border-soft, var(--border));
  background: color-mix(in srgb, var(--panel-bg) 60%, var(--bg));
}
.settings-footer-spacer {
  flex: 1;
}
.settings-btn {
  border-radius: 8px;
  padding: 7px 18px;
  font-size: var(--ui-font-size);
  font-weight: 550;
  cursor: pointer;
  border: 1px solid var(--border);
  transition: background 0.14s ease, border-color 0.14s ease,
              color 0.14s ease, filter 0.14s ease, transform 0.06s ease;
}
.settings-btn:active {
  transform: translateY(1px);
}
.settings-btn:focus-visible {
  outline: none;
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 28%, transparent);
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
  color: #fff;
  font-weight: 650;
  box-shadow: 0 2px 12px -3px color-mix(in srgb, var(--accent) 65%, transparent);
}
.settings-btn.primary:hover {
  filter: brightness(1.08);
}
</style>
