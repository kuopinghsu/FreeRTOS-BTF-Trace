<template>
  <div class="marks-panel">
    <!-- Marks section -->
    <div class="marks-section">
      <div class="marks-section-header">
        <span>Marks ({{ marks.length }})</span>
      </div>
      <div
        v-if="marks.length > 0"
        ref="listEl"
        class="mark-list"
      >
        <div
          v-for="m in marks"
          :key="m.id"
          class="mark-item"
          :class="{ selected: selectedId === m.id }"
          :data-mark-id="m.id"
          tabindex="0"
          @click="emit('jumpTo', m.ns); emit('selectMark', m.id); selectedId = m.id"
          @keydown.delete.stop="emit('deleteMark', m.id)"
        >
          <span
            class="mark-kind"
            :class="m.type === 'annotation' ? 'annotation' : 'bookmark'"
          >
            {{ m.type === 'annotation' ? 'A' : 'B' }}
          </span>
          <span
            class="mark-time"
            :style="{ color: markColor(m) }"
          >{{ fmt(m.ns) }}</span>
          <input
            class="mark-label"
            placeholder="label…"
            :value="editingId === m.id ? editingLabel : m.label"
            @focus="editingId = m.id; editingLabel = m.label"
            @blur="onLabelBlur(m)"
            @input="editingLabel = $event.target.value"
            @keydown.enter.stop="$event.target.blur()"
            @keydown.escape.stop="editingLabel = m.label; $event.target.blur()"
            @click.stop
          >
          <button
            class="mark-btn mark-del"
            title="Delete mark"
            @click.stop="emit('deleteMark', m.id)"
          >
            ×
          </button>
        </div>
      </div>
      <div
        v-else
        class="mark-empty"
      >
        Right-click timeline to add · Double-click or press B / A
      </div>
    </div>

    <!-- Export / Import row -->
    <div class="marks-actions">
      <button
        class="action-btn"
        :disabled="marks.length === 0"
        title="Export Marks (bookmarks + annotations) as CSV"
        @click="exportCsv"
      >
        Export Marks
      </button>
      <button
        class="action-btn"
        title="Import Marks (bookmarks + annotations) from CSV"
        @click="triggerImport"
      >
        Import Marks
      </button>
      <button
        class="action-btn"
        :disabled="!hasBookmarks"
        title="Clear all bookmarks (Shift+B)"
        @click="emit('clearBookmarks')"
      >
        Clear B
      </button>
      <button
        class="action-btn"
        :disabled="!hasAnnotations"
        title="Clear all annotations (Shift+A)"
        @click="emit('clearAnnotations')"
      >
        Clear A
      </button>
      <button
        class="action-btn"
        title="Export portable session (cursors, marks, viewport)"
        @click="emit('exportSession')"
      >
        Session
      </button>
      <button
        class="action-btn"
        title="Import portable session JSON"
        @click="triggerSessionImport"
      >
        Import Session
      </button>
      <input
        ref="importInputEl"
        type="file"
        accept=".csv"
        style="display:none"
        @change="onImportFile"
      >
      <input
        ref="sessionImportEl"
        type="file"
        accept=".json,application/json"
        style="display:none"
        @change="onSessionImportFile"
      >
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, ref } from 'vue'
import { formatTime } from '../renderer/TimelineRenderer.js'

const props = defineProps({
  marks:        { type: Array, default: () => [] },
  timeScale:    { type: String, default: 'ns' },
  timeDecimals: { type: Number, default: 3 },
})

const emit = defineEmits([
  'deleteMark', 'jumpTo', 'updateLabel',
  'importMarks', 'clearBookmarks', 'clearAnnotations', 'selectMark',
  'exportSession', 'importSession',
])

const hasBookmarks = computed(() => props.marks.some(m => m.type !== 'annotation'))
const hasAnnotations = computed(() => props.marks.some(m => m.type === 'annotation'))

const selectedId    = ref(null)
const listEl          = ref(null)
const importInputEl = ref(null)
const sessionImportEl = ref(null)
const MAX_MARKS_CSV_ROWS = 100_000
const editingId     = ref(null)
const editingLabel  = ref('')

function onLabelBlur(mark) {
  if (editingId.value === mark.id) {
    emit('updateLabel', { id: mark.id, label: editingLabel.value })
    editingId.value = null
  }
}

/**
 * Parse a single CSV row, correctly handling quoted fields (including embedded
 * commas and escaped double-quotes "").
 */
function parseCSVRow(line) {
  const fields = []
  let i = 0
  while (i <= line.length) {
    if (i === line.length) { fields.push(''); break }
    if (line[i] === '"') {
      i++ // skip opening quote
      let val = ''
      while (i < line.length) {
        if (line[i] === '"') {
          if (line[i + 1] === '"') { val += '"'; i += 2 } // escaped quote
          else { i++; break }                              // closing quote
        } else {
          val += line[i++]
        }
      }
      fields.push(val)
      if (line[i] === ',') i++ // skip field separator
      else break               // last quoted field – stop without extra empty entry
    } else {
      const end = line.indexOf(',', i)
      if (end === -1) { fields.push(line.slice(i)); break }
      fields.push(line.slice(i, end))
      i = end + 1
    }
  }
  return fields
}

function markColor(mark) {
  return mark?.type === 'annotation' ? '#FF8C00' : '#FFD700'
}

function fmt(ns) {
  return formatTime(ns, props.timeScale, props.timeDecimals)
}

function exportCsv() {
  if (props.marks.length === 0) return
  const rows = [['type', 'time', props.timeScale, 'label']]
  for (const m of props.marks) {
    rows.push([m.type === 'annotation' ? 'annotation' : 'bookmark', fmt(m.ns), m.ns, m.label || ''])
  }
  const csv = rows.map(r => r.map(v => `"${String(v).replace(/"/g, '""')}"`).join(',')).join('\n')
  const blob = new Blob([csv], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'marks.csv'
  a.click()
  URL.revokeObjectURL(url)
}

function triggerImport() {
  importInputEl.value?.click()
}

function triggerSessionImport() {
  sessionImportEl.value?.click()
}

function onSessionImportFile(e) {
  const file = e.target.files[0]
  if (!file) return
  emit('importSession', file)
  e.target.value = ''
}

/** Convert a value from one timescale to another (both in { 'ns','us','ms','s' }). */
function convertTimeScale(value, fromScale, toScale) {
  if (fromScale === toScale) return value
  // Convert to nanoseconds first, then to target
  const toNs = { ns: 1, us: 1e3, ms: 1e6, s: 1e9 }
  const fromNs = toNs[fromScale] ?? 1
  const destNs = toNs[toScale]  ?? 1
  return value * fromNs / destNs
}

function onImportFile(e) {
  const file = e.target.files[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = (ev) => {
    const text = ev.target.result
    const lines = text.split(/\r?\n/).filter(l => l.trim())
    const imported = []
    // Detect header row and read its timescale (3rd column)
    const headerCols = parseCSVRow(lines[0] || '')
    const hasHeader = headerCols[0]?.toLowerCase() === 'type'
    const csvScale = hasHeader ? (headerCols[2]?.toLowerCase() || props.timeScale) : props.timeScale
    const startIdx = hasHeader ? 1 : 0
    const maxRows = Math.min(lines.length, startIdx + MAX_MARKS_CSV_ROWS)
    if (lines.length - startIdx > MAX_MARKS_CSV_ROWS) {
      console.warn(`Marks CSV truncated to ${MAX_MARKS_CSV_ROWS} rows`)
    }
    for (let i = startIdx; i < maxRows; i++) {
      const cols = parseCSVRow(lines[i])
      // Expected cols: type, time, <scale>, label
      const type = (cols[0] || '').trim().toLowerCase() === 'annotation' ? 'annotation' : 'bookmark'
      const raw = parseFloat(cols[2])
      if (!isNaN(raw)) {
        const ns = convertTimeScale(raw, csvScale, props.timeScale)
        imported.push({ ns, label: cols[3] || '', type })
      }
    }
    if (imported.length > 0) {
      emit('importMarks', imported)
    }
  }
  reader.readAsText(file)
  // Reset input so the same file can be re-imported
  e.target.value = ''
}

function focusAnnotation(markId) {
  if (markId == null) return
  selectedId.value = markId
  nextTick(() => {
    const el = listEl.value?.querySelector(`[data-mark-id="${markId}"]`)
    el?.scrollIntoView({ block: 'nearest' })
  })
}

defineExpose({ focusAnnotation })
</script>

<style scoped>
.marks-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  font-size: 11px;
}

.marks-section {
  display: flex;
  flex-direction: column;
  flex: 1;
  overflow: hidden;
}

.marks-section-header {
  display: flex;
  align-items: center;
  padding: 4px 10px;
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--fg-dim);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.mark-list {
  overflow-y: auto;
  flex: 1;
  padding: 4px 0;
}

.mark-item {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  cursor: pointer;
  transition: background 0.08s;
}

.mark-kind {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 9px;
  font-weight: 700;
  color: #000;
  flex-shrink: 0;
}

.mark-kind.bookmark {
  background: #FFD700;
}

.mark-kind.annotation {
  background: #FF8C00;
}
.mark-item:hover {
  background: var(--tb-btn-hover);
}
.mark-item.selected {
  background: var(--tb-btn-active);
}

.mark-time {
  font-family: monospace;
  font-size: 10px;
  min-width: 70px;
  flex-shrink: 0;
}

.mark-label {
  flex: 1;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 3px;
  color: var(--fg);
  font-size: 11px;
  font-family: monospace;
  padding: 1px 4px;
  min-width: 0;
}
.mark-label:hover {
  border-color: var(--border);
}
.mark-label:focus {
  border-color: var(--accent);
  outline: none;
  background: var(--bg);
}

.mark-btn {
  background: transparent;
  border: none;
  cursor: pointer;
  color: var(--fg-dim);
  padding: 1px 4px;
  border-radius: 3px;
  font-size: 12px;
  flex-shrink: 0;
}
.mark-btn:hover {
  background: var(--tb-btn-hover);
  color: var(--fg);
}
.mark-del:hover {
  color: #FF5555;
}

.mark-empty {
  padding: 8px 10px;
  color: var(--fg-dim);
  opacity: 0.6;
  font-size: 10px;
  font-style: italic;
}

.marks-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  padding: 6px 8px;
  border-top: 1px solid var(--border);
  flex-shrink: 0;
}

.action-btn {
  flex: 1 1 calc(33.333% - 4px);
  min-width: 4.5rem;
  padding: 3px 8px;
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 4px;
  color: var(--fg-dim);
  cursor: pointer;
  font-size: 11px;
}
.action-btn:hover {
  background: var(--tb-btn-hover);
  color: var(--fg);
}
</style>
