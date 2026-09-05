<template>
  <div v-if="visible" class="stats-ref-scrim" @click.self="close">
    <div class="stats-ref-panel">
      <div class="stats-ref-chrome">
        <button
          type="button"
          class="stats-ref-chrome-btn"
          title="Back"
          :disabled="!canGoBack"
          @click="goBack"
        >
          <svg width="15" height="15" viewBox="0 0 16 16" fill="none"><path d="M10 3L5 8l5 5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </button>
        <button
          type="button"
          class="stats-ref-chrome-btn"
          title="Forward"
          :disabled="!canGoForward"
          @click="goForward"
        >
          <svg width="15" height="15" viewBox="0 0 16 16" fill="none"><path d="M6 3l5 5-5 5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </button>

        <div class="stats-ref-breadcrumb">{{ breadcrumb }}</div>

        <input
          v-model="searchQuery"
          type="search"
          class="stats-ref-search"
          placeholder="Search reference…"
          autocomplete="off"
        >

        <button
          type="button"
          class="stats-ref-chrome-btn"
          title="Open in system browser"
          @click="openInNewTab"
        >
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M6.5 3H3v10h10V9.5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/><path d="M9 3h4v4M13 3L7 9" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </button>
        <button type="button" class="stats-ref-chrome-btn" title="Close" @click="close">
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
        </button>
      </div>

      <div class="stats-ref-body">
        <div class="stats-ref-toc">
          <template v-for="cat in STATS_SECTION_CATEGORIES" :key="cat">
            <div v-if="tocByCategory[cat].length" class="stats-ref-toc-cat">
              {{ STATS_CATEGORY_LABELS[cat] || cat }}
            </div>
            <div
              v-for="row in tocByCategory[cat]"
              :key="row.id"
              class="stats-ref-toc-row"
              :class="{ active: row.id === currentSection }"
              @click="openSection(row.id)"
            >{{ row.title }}</div>
          </template>
        </div>

        <iframe
          ref="frameRef"
          class="stats-ref-frame"
          :srcdoc="docHtml"
          title="Statistics Reference"
          @load="onFrameLoad"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, nextTick } from 'vue'
import {
  STATS_SECTION_CATEGORIES,
  STATS_SECTION_CATEGORY,
  STATS_CATEGORY_LABELS,
  STATS_PINNABLE_SECTIONS,
  STATS_SECTION_TITLES,
} from '../utils/statsPins.js'
// Imported as a raw string (not fetched from a URL): Web ships as ONE
// self-contained HTML file (vite-plugin-singlefile) with no server and no
// guaranteed sibling files at runtime, so the doc content must be inlined
// into the JS bundle and rendered via <iframe srcdoc> — see
// scripts/build_docs_html.py for how this is generated.
import docHtml from '../generated/statistics-en.inline.html?raw'

const visible = ref(false)
const currentSection = ref('')
const searchQuery = ref('')
const frameRef = ref(null)
const frameLoaded = ref(false)
const historyStack = ref([])
const historyIndex = ref(-1)

const canGoBack = computed(() => historyIndex.value > 0)
const canGoForward = computed(() => historyIndex.value < historyStack.value.length - 1)

const breadcrumb = computed(() => {
  const sid = currentSection.value
  if (!sid) return 'Statistics Reference'
  const cat = STATS_SECTION_CATEGORY[sid]
  const catLabel = cat ? STATS_CATEGORY_LABELS[cat] : ''
  const title = STATS_SECTION_TITLES[sid] || sid
  return ['Statistics Reference', catLabel, title].filter(Boolean).join(' › ')
})

const tocByCategory = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  const out = {}
  for (const cat of STATS_SECTION_CATEGORIES) {
    out[cat] = STATS_PINNABLE_SECTIONS
      .filter((sid) => STATS_SECTION_CATEGORY[sid] === cat)
      .map((sid) => ({ id: sid, title: STATS_SECTION_TITLES[sid] || sid }))
      .filter((row) => !q || row.title.toLowerCase().includes(q))
  }
  return out
})

function openSection(sectionId) {
  const sid = String(sectionId || '').trim()
  if (!sid) return
  currentSection.value = sid
  // Truncate any forward history, then push — a normal browser-tab history model.
  historyStack.value = [...historyStack.value.slice(0, historyIndex.value + 1), sid]
  historyIndex.value = historyStack.value.length - 1
  // The panel unmounts its iframe on close (v-if="visible") — a fresh one
  // needs its own load event before hash-navigation works again.
  if (!visible.value) frameLoaded.value = false
  visible.value = true
  nextTick(() => navigateFrame(sid))
}

function navigateFrame(sectionId) {
  const frame = frameRef.value
  if (!frame || !frameLoaded.value) return  // onFrameLoad will catch up once ready
  try {
    frame.contentWindow.location.hash = `statistics-${sectionId}`
  } catch {
    // same-origin srcdoc document — should not normally throw
  }
}

function onFrameLoad() {
  frameLoaded.value = true
  const sid = currentSection.value
  if (sid) navigateFrame(sid)
}

function goBack() {
  if (!canGoBack.value) return
  historyIndex.value -= 1
  const sid = historyStack.value[historyIndex.value]
  currentSection.value = sid
  navigateFrame(sid)
}

function goForward() {
  if (!canGoForward.value) return
  historyIndex.value += 1
  const sid = historyStack.value[historyIndex.value]
  currentSection.value = sid
  navigateFrame(sid)
}

function openInNewTab() {
  // No real URL to hand the new tab (srcdoc content) — package it as a
  // Blob URL instead; the fragment still scrolls on that tab's own load.
  const blob = new Blob([docHtml], { type: 'text/html' })
  const url = URL.createObjectURL(blob)
  const sid = currentSection.value
  window.open(sid ? `${url}#statistics-${sid}` : url, '_blank', 'noopener')
  setTimeout(() => URL.revokeObjectURL(url), 30000)
}

function close() {
  visible.value = false
}

defineExpose({ openSection, close })
</script>

<style scoped>
.stats-ref-scrim {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.38);
  z-index: 400;
  display: flex;
  justify-content: flex-end;
}

.stats-ref-panel {
  width: min(940px, 92vw);
  height: 100%;
  background: var(--panel-bg);
  border-left: 1px solid var(--border);
  box-shadow: -18px 0 44px rgba(0, 0, 0, 0.45);
  display: flex;
  flex-direction: column;
}

.stats-ref-chrome {
  flex: 0 0 auto;
  height: 46px;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 10px;
  border-bottom: 1px solid var(--border);
  background: var(--app-surface-2, var(--panel-bg));
}

.stats-ref-chrome-btn {
  appearance: none;
  border: none;
  background: transparent;
  color: var(--fg-dim);
  width: 26px;
  height: 26px;
  border-radius: 6px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  flex: 0 0 auto;
}

.stats-ref-chrome-btn:hover:not(:disabled) {
  background: var(--app-surface-3, var(--tb-btn-hover));
  color: var(--fg);
}

.stats-ref-chrome-btn:disabled {
  opacity: 0.35;
  cursor: default;
}

.stats-ref-breadcrumb {
  flex: 1 1 auto;
  min-width: 0;
  font-size: 11.5px;
  color: var(--fg-dim);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.stats-ref-search {
  flex: 0 0 auto;
  width: 190px;
  height: 26px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--fg);
  font-family: var(--font-ui);
  font-size: 11.5px;
  padding: 0 10px;
  outline: none;
}

.stats-ref-body {
  flex: 1 1 auto;
  display: flex;
  min-height: 0;
}

.stats-ref-toc {
  width: 236px;
  flex: 0 0 auto;
  border-right: 1px solid var(--border);
  overflow-y: auto;
  padding: 10px 0;
}

.stats-ref-toc-cat {
  padding: 7px 10px;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.07em;
  text-transform: uppercase;
  color: var(--fg-dim);
}

.stats-ref-toc-row {
  padding: 5px 10px 5px 14px;
  border-radius: 5px;
  margin: 0 4px;
  cursor: pointer;
  font-size: 11.5px;
  color: var(--fg-dim);
  line-height: 1.3;
}

.stats-ref-toc-row:hover {
  background: var(--app-surface-3, var(--tb-btn-hover));
  color: var(--fg);
}

.stats-ref-toc-row.active {
  background: rgba(79, 139, 255, 0.14);
  color: var(--fg);
  font-weight: 600;
}

.stats-ref-frame {
  flex: 1 1 auto;
  border: none;
  background: var(--bg);
}
</style>
