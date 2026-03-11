<template>
  <div class="toolbar">
    <!-- File open -->
    <label class="tb-btn file-btn" title="Open BTF file">
      <svg viewBox="0 0 16 16" width="16" height="16" fill="currentColor">
        <path d="M1 3.5A1.5 1.5 0 0 1 2.5 2h2.764c.958 0 1.76.56 2.311 1.184C7.985 3.648 8.48 4 9 4h4.5A1.5 1.5 0 0 1 15 5.5v7a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 1 12.5v-9z"/>
      </svg>
      Open
      <input type="file" accept=".btf" @change="onFileChange" style="display:none" />
    </label>

    <div class="tb-sep" />

    <!-- View mode -->
    <label class="tb-btn" :class="{ active: modelValue.viewMode === 'task' }"
           title="Task view" @click="emit('update:modelValue', { ...modelValue, viewMode: 'task' })">
      <svg viewBox="0 0 16 16" width="16" height="16" fill="currentColor">
        <path d="M1 2.5A1.5 1.5 0 0 1 2.5 1h11A1.5 1.5 0 0 1 15 2.5v11a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 1 13.5v-11zM4 5.5h8v1H4v-1zm0 3h8v1H4v-1zm0 3h5v1H4v-1z"/>
      </svg>
      Task
    </label>
    <label class="tb-btn" :class="{ active: modelValue.viewMode === 'core' }"
           title="Core view" @click="emit('update:modelValue', { ...modelValue, viewMode: 'core' })">
      <svg viewBox="0 0 16 16" width="16" height="16" fill="currentColor">
        <path d="M5 1v2H3a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h2v2h1v-2h4v2h1v-2h2a2 2 0 0 0 2-2V5a2 2 0 0 0-2-2h-2V1h-1v2H6V1H5zm-2 4h10v6H3V5zm2 1v4h6V6H5z"/>
      </svg>
      Core
    </label>

    <!-- Expand / Collapse all cores (core mode only) -->
    <template v-if="modelValue.viewMode === 'core'">
      <div class="tb-sep" />
      <button class="tb-btn" title="Expand all cores" @click="emit('expandAll')">
        <svg viewBox="0 0 16 16" width="16" height="16" fill="currentColor">
          <path d="M8 2v5H3v1h5v5h1V8h5V7H9V2H8z"/>
        </svg>
        Expand
      </button>
      <button class="tb-btn" title="Collapse all cores" @click="emit('collapseAll')">
        <svg viewBox="0 0 16 16" width="16" height="16" fill="currentColor">
          <path d="M2 7h12v2H2z"/>
        </svg>
        Collapse
      </button>
    </template>

    <div class="tb-sep" />

    <!-- Zoom controls -->
    <button class="tb-btn" title="Zoom in (Ctrl+scroll)" @click="emit('zoom', 0.7)">
      <svg viewBox="0 0 16 16" width="16" height="16" fill="currentColor">
        <path d="M6.5 1a5.5 5.5 0 1 0 3.89 9.4l3.4 3.4.7-.7-3.4-3.4A5.5 5.5 0 0 0 6.5 1zm0 1a4.5 4.5 0 1 1 0 9 4.5 4.5 0 0 1 0-9zM6 5v1.5H4.5v1H6V9h1V7.5h1.5v-1H7V5H6z"/>
      </svg>
    </button>
    <button class="tb-btn" title="Zoom out (Ctrl+scroll)" @click="emit('zoom', 1.43)">
      <svg viewBox="0 0 16 16" width="16" height="16" fill="currentColor">
        <path d="M6.5 1a5.5 5.5 0 1 0 3.89 9.4l3.4 3.4.7-.7-3.4-3.4A5.5 5.5 0 0 0 6.5 1zm0 1a4.5 4.5 0 1 1 0 9 4.5 4.5 0 0 1 0-9zM4 6h5v1H4V6z"/>
      </svg>
    </button>
    <button class="tb-btn" title="Fit to window" @click="emit('fit')">
      <svg viewBox="0 0 16 16" width="16" height="16" fill="currentColor">
        <path d="M1.5 1h5v1h-4v4h-1V1.5a.5.5 0 0 1 .5-.5zm13 0a.5.5 0 0 1 .5.5V6h-1V2h-4V1h4.5zM1 10h1v4h4v1H1.5a.5.5 0 0 1-.5-.5V10zm14 0v4.5a.5.5 0 0 1-.5.5H10v-1h4v-4h1z"/>
      </svg>
    </button>

    <div class="tb-sep" />

    <!-- Clear cursors -->
    <button class="tb-btn" title="Clear all cursors" @click="emit('clearCursors')">
      <svg viewBox="0 0 16 16" width="16" height="16" fill="currentColor">
        <path d="M1 1l5 12 2-4 4 4 1-1-4-4 4-2L1 1z"/>
      </svg>
      Cursors
    </button>

    <div class="tb-sep" />

    <!-- Grid toggle -->
    <label class="tb-btn" :class="{ active: modelValue.showGrid }"
           title="Toggle grid" @click="emit('update:modelValue', { ...modelValue, showGrid: !modelValue.showGrid })">
      <svg viewBox="0 0 16 16" width="16" height="16" fill="currentColor">
        <path d="M1 4h14v1H1zm0 4h14v1H1zm0 4h14v1H1zM4 1v14H5V1zm4 0v14H9V1zm4 0v14h1V1z"/>
      </svg>
    </label>

    <!-- Dark mode toggle -->
    <label class="tb-btn" :class="{ active: modelValue.darkMode }"
           title="Toggle dark/light mode"
           @click="emit('update:modelValue', { ...modelValue, darkMode: !modelValue.darkMode })">
      <svg viewBox="0 0 16 16" width="16" height="16" fill="currentColor">
        <path d="M6 .278a.768.768 0 0 1 .08.858 7.208 7.208 0 0 0-.878 3.46c0 4.021 3.278 7.277 7.318 7.277.527 0 1.04-.055 1.533-.16a.787.787 0 0 1 .81.316.733.733 0 0 1-.031.893A8.349 8.349 0 0 1 8.344 16C3.734 16 0 12.286 0 7.71 0 4.266 2.114 1.312 5.124.06A.752.752 0 0 1 6 .278z"/>
      </svg>
    </label>

    <div class="spacer" />

    <!-- File info -->
    <span v-if="traceInfo" class="trace-info">{{ traceInfo }}</span>
    <span v-if="loading" class="loading-badge">
      Parsing… <span v-if="loadingPct > 0">{{ loadingPct }}%</span>
    </span>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  modelValue:  { type: Object,  required: true },
  traceInfo:   { type: String,  default: '' },
  loading:     { type: Boolean, default: false },
  loadingPct:  { type: Number,  default: 0 },
})

const emit = defineEmits(['update:modelValue', 'trace-loaded', 'zoom', 'fit', 'clearCursors', 'expandAll', 'collapseAll'])

function onFileChange(e) {
  const file = e.target.files[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = (ev) => {
    emit('trace-loaded', { text: ev.target.result, name: file.name })
  }
  reader.onerror = () => {
    alert(`Failed to read "${file.name}": ${reader.error?.message ?? 'unknown error'}`)
  }
  reader.readAsText(file)
  // Reset input so same file can be re-loaded
  e.target.value = ''
}
</script>

<style scoped>
.toolbar {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 4px 8px;
  background: var(--tb-bg);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  user-select: none;
}

.tb-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  border: 1px solid transparent;
  border-radius: 4px;
  background: transparent;
  color: var(--fg);
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.1s;
}
.tb-btn:hover {
  background: var(--tb-btn-hover);
  border-color: var(--border);
}
.tb-btn.active {
  background: var(--tb-btn-active);
  border-color: var(--accent);
  color: var(--accent);
}
.tb-sep {
  width: 1px;
  height: 20px;
  background: var(--border);
  margin: 0 4px;
}
.spacer {
  flex: 1;
}
.trace-info {
  font-size: 11px;
  color: var(--fg-dim);
  font-family: monospace;
}
.loading-badge {
  font-size: 11px;
  background: var(--accent);
  color: #000;
  padding: 2px 8px;
  border-radius: 10px;
}
.file-btn {
  cursor: pointer;
}
</style>
