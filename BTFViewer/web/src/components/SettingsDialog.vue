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
              <span class="settings-unit">pt</span>
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
              <span class="settings-unit">px</span>
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
                v-model="draft.showCpuLoad"
                type="checkbox"
              >
              CPU load graph
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
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { DEFAULT_SETTINGS, normalizeSettings } from '../utils/settingsStore.js'

const props = defineProps({
  modelValue: { type: Object, required: true },
  timeScale:  { type: String, default: 'ns' },
})

const emit = defineEmits(['close', 'save', 'preview'])

const tabs = [
  { id: 'appearance', label: 'Appearance' },
  { id: 'display', label: 'Display' },
  { id: 'layout', label: 'Layout' },
]

const activeTab = ref('appearance')
const draft = reactive(normalizeSettings(props.modelValue))
const deadlinesText = ref(formatDeadlinesText(draft.taskDeadlines))

function formatDeadlinesText(map) {
  if (!map || typeof map !== 'object') return ''
  return Object.entries(map)
    .map(([k, v]) => `${k}=${v}`)
    .join('\n')
}

function parseDeadlinesText(text) {
  const out = {}
  for (const line of String(text || '').split(/\r?\n/)) {
    const t = line.trim()
    if (!t || t.startsWith('#')) continue
    const eq = t.indexOf('=')
    if (eq <= 0) continue
    const key = t.slice(0, eq).trim()
    const val = Number.parseInt(t.slice(eq + 1).trim(), 10)
    if (key && Number.isFinite(val) && val > 0) out[key] = val
  }
  return out
}

watch(() => props.modelValue, (v) => {
  suppressPreview.value = true
  Object.assign(draft, normalizeSettings(v))
  deadlinesText.value = formatDeadlinesText(draft.taskDeadlines)
  nextTick(() => { suppressPreview.value = false })
}, { deep: true })

onMounted(() => {
  nextTick(() => { suppressPreview.value = false })
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
  font-size: var(--ui-font-size, 8px);
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
.settings-row {
  display: grid;
  grid-template-columns: 1fr 110px 36px;
  align-items: center;
  gap: 10px;
  font-size: var(--ui-font-size, 8px);
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
  font-size: var(--ui-font-size, 8px);
}
.settings-input.wide {
  width: 100%;
  max-width: 220px;
  grid-column: 2 / 4;
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
  font-size: var(--ui-font-size, 8px);
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
  font-size: var(--ui-font-size, 8px);
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
