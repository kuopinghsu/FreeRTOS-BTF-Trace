<template>
  <div class="marks-panel">
    <!-- Marks section -->
    <div class="marks-section">
      <div class="marks-section-header">
        <span>Marks ({{ marks.length }})</span>
        <div class="mark-add-group">
          <button
            class="mark-add-btn"
            title="Add bookmark at viewport centre"
            @click="emit('addBookmark')"
          >
            +B
          </button>
          <button
            class="mark-add-btn"
            title="Add annotation at viewport centre"
            @click="emit('addAnnotation')"
          >
            +A
          </button>
        </div>
      </div>
      <div
        v-if="marks.length > 0"
        class="mark-list"
      >
        <div
          v-for="m in marks"
          :key="m.id"
          class="mark-item"
          :class="{ selected: selectedId === m.id }"
          @click="emit('jumpTo', m.ns); selectedId = m.id"
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
            :value="m.label"
            @change="emit('updateLabel', { id: m.id, label: $event.target.value })"
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
        Right-click timeline to add
      </div>
    </div>

    <!-- Export / Import row -->
    <div class="marks-actions">
      <button
        class="action-btn"
        :disabled="marks.length === 0"
        @click="exportCsv"
      >
        Export CSV
      </button>
      <button
        class="action-btn"
        @click="triggerImport"
      >
        Import CSV
      </button>
      <input
        ref="importInputEl"
        type="file"
        accept=".csv"
        style="display:none"
        @change="onImportFile"
      >
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { formatTime } from '../renderer/TimelineRenderer.js'

const props = defineProps({
  marks: { type: Array, default: () => [] },
  timeScale: { type: String, default: 'ns' },
})

const emit = defineEmits(['addBookmark', 'addAnnotation', 'deleteMark', 'jumpTo', 'updateLabel', 'importMarks'])

const selectedId    = ref(null)
const importInputEl = ref(null)

function markColor(mark) {
  return mark?.type === 'annotation' ? '#FF8C00' : '#FFD700'
}

function fmt(ns) {
  return formatTime(ns, props.timeScale)
}

function exportCsv() {
  if (props.marks.length === 0) return
  const rows = [['type', 'time', 'ns', 'label']]
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

function onImportFile(e) {
  const file = e.target.files[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = (ev) => {
    const text = ev.target.result
    const lines = text.split(/\r?\n/).filter(l => l.trim())
    const imported = []
    // Skip header row (type,time,ns,label)
    const startIdx = lines[0]?.toLowerCase().includes('ns') ? 1 : 0
    for (let i = startIdx; i < lines.length; i++) {
      // Simple CSV parse: split on comma, strip surrounding quotes
      const cols = lines[i].match(/(?:"([^"]*(?:""[^"]*)*)"|([^,]*))/g)
        ?.map(c => c.startsWith('"') ? c.slice(1, -1).replace(/("")/g, '"') : c) ?? []
      // Expected cols: type, time, ns, label
      const type = (cols[0] || '').trim().toLowerCase() === 'annotation' ? 'annotation' : 'bookmark'
      const ns = parseFloat(cols[2])
      if (!isNaN(ns)) {
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
  justify-content: space-between;
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

.mark-add-group {
  display: flex;
  gap: 4px;
}

.mark-add-btn {
  background: var(--tb-btn-active);
  border: 1px solid var(--accent);
  border-radius: 3px;
  color: var(--accent);
  cursor: pointer;
  padding: 0 6px;
  font-size: 14px;
  line-height: 1.2;
}
.mark-add-btn:hover {
  opacity: 0.8;
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
  gap: 4px;
  padding: 6px 8px;
  border-top: 1px solid var(--border);
  flex-shrink: 0;
}

.action-btn {
  flex: 1;
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
