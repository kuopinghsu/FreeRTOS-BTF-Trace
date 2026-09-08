<template>
  <div
    class="dialog-overlay"
    @click.self="emit('close')"
  >
    <div
      class="nb-dialog"
      role="dialog"
      aria-modal="true"
      aria-label="Investigation notebook"
    >
      <div class="nb-header">
        <div class="nb-title">
          Investigation Notebook
          <span
            v-if="brokenCount"
            class="nb-broken-flag"
            :title="`${brokenCount} bookmark reference(s) no longer resolve`"
          >⚠ {{ brokenCount }} stale ref</span>
        </div>

        <!-- §7 compact header: durable status · scope · counts -->
        <div class="nb-context">
          <label class="nb-status">
            <span class="nb-status-dot" :class="`s-${header.status}`" />
            <select
              :value="header.status"
              class="nb-status-select"
              title="Durable investigation status"
              @change="changeStatus($event.target.value)"
            >
              <option
                v-for="o in statusOptions"
                :key="o.value"
                :value="o.value"
              >
                {{ o.label }}
              </option>
            </select>
          </label>
          <span
            v-if="header.trace"
            class="nb-context-bit"
          >{{ header.trace }}</span>
          <span class="nb-context-bit">Scope: {{ header.scope }}</span>
          <span class="nb-context-bit">{{ header.evidence_count }} evidence</span>
          <span class="nb-context-bit">{{ header.open_check_count }} open check{{ header.open_check_count === 1 ? '' : 's' }}</span>
          <span
            v-if="header.stale_ref_count"
            class="nb-context-bit warn"
          >{{ header.stale_ref_count }} stale ref{{ header.stale_ref_count === 1 ? '' : 's' }}</span>
          <span
            v-if="header.updated_at"
            class="nb-context-bit"
          >updated {{ header.updated_at }}</span>
        </div>
        <div class="nb-header-actions">
          <button
            type="button"
            class="nb-btn primary"
            :disabled="!findingOptions.length"
            :title="findingOptions.length
              ? 'Seed observations from the current Analysis findings, plus a hypothesis + verification stub'
              : 'No Analysis findings to seed from'"
            @click="emit('scaffold')"
          >
            ✦ Scaffold
          </button>
          <button
            type="button"
            class="nb-btn"
            :disabled="!historyState.can_undo"
            title="Undo (notebook)"
            @click="emit('undo')"
          >
            ↶ Undo
          </button>
          <button
            type="button"
            class="nb-btn"
            :disabled="!historyState.can_redo"
            title="Redo (notebook)"
            @click="emit('redo')"
          >
            ↷ Redo
          </button>
          <button
            type="button"
            class="nb-btn"
            title="Import a saved investigation (.json)"
            @click="fileInput?.click()"
          >
            Import…
          </button>
          <button
            type="button"
            class="nb-btn"
            title="Save this investigation as .json"
            @click="exportJson"
          >
            Export…
          </button>
          <button
            type="button"
            class="nb-btn"
            title="Build a compact AI evidence package from this investigation"
            @click="emitEvidencePackage"
          >
            Evidence pack…
          </button>
          <button
            class="nb-close"
            type="button"
            @click="emit('close')"
          >
            ✕
          </button>
        </div>
        <input
          ref="fileInput"
          type="file"
          accept=".json,application/json"
          hidden
          @change="onImportFile"
        >
      </div>

      <div class="nb-body">
        <label class="nb-field">
          <span class="nb-field-label">Title</span>
          <input
            :value="inv.title"
            class="nb-input"
            type="text"
            placeholder="What is this investigation about?"
            @change="commit(setTitle($event.target.value))"
          >
        </label>

        <!-- Add bookmark -->
        <div class="nb-add">
          <div class="nb-add-row">
            <select
              v-model="draft.type"
              class="nb-input nb-type"
            >
              <option
                v-for="t in bookmarkTypes"
                :key="t"
                :value="t"
              >
                {{ typeLabels[t] }}
              </option>
            </select>
            <input
              v-model="draft.title"
              class="nb-input"
              type="text"
              placeholder="Bookmark title"
              @keydown.enter.prevent="addDraft"
            >
            <button
              type="button"
              class="nb-btn primary"
              :disabled="!draft.title.trim()"
              @click="addDraft"
            >
              Add
            </button>
          </div>
          <textarea
            v-model="draft.note"
            class="nb-input nb-note"
            rows="2"
            placeholder="Note (optional)"
          />
          <div class="nb-add-refs">
            <label
              v-if="cursorRange"
              class="nb-chk"
            >
              <input
                v-model="draft.useRange"
                type="checkbox"
              >
              Attach current cursor range
              ({{ fmt(cursorRange.start) }} – {{ fmt(cursorRange.end) }})
            </label>
            <label
              v-if="findingOptions.length"
              class="nb-chk"
            >
              Link finding
              <select
                v-model="draft.findingRuleId"
                class="nb-input nb-ref-sel"
              >
                <option value="">
                  — none —
                </option>
                <option
                  v-for="f in findingOptions"
                  :key="f.rule_id"
                  :value="f.rule_id"
                >{{ f.label }}</option>
              </select>
            </label>
          </div>
        </div>

        <!-- Bookmark groups -->
        <div
          v-if="isEmpty"
          class="nb-empty nb-empty-actions"
        >
          <button
            type="button"
            class="nb-btn primary"
            :disabled="!findingOptions.length"
            :title="findingOptions.length ? '' : 'No Analysis findings to seed from'"
            @click="emit('scaffold')"
          >
            {{ emptyFromFindings }}
          </button>
          <button
            type="button"
            class="nb-btn"
            @click="startBlank"
          >
            {{ emptyBlank }}
          </button>
        </div>
        <div
          v-else-if="!inv.bookmarks.length"
          class="nb-empty"
        >
          No bookmarks yet. Add an observation, hypothesis, supporting or
          contradicting evidence, a verification step, or a conclusion above.
        </div>
        <div
          v-for="grp in groups"
          v-else
          :key="grp.type"
          class="nb-group"
        >
          <div
            v-if="grp.items.length"
            class="nb-group-title"
          >
            {{ typeLabels[grp.type] }} ({{ grp.items.length }})
          </div>
          <div
            v-for="b in grp.items"
            :key="b.id"
            class="nb-item"
            :class="{ broken: brokenIds.has(b.id) }"
          >
            <div class="nb-item-main">
              <input
                :value="b.title"
                class="nb-input nb-item-title"
                type="text"
                @change="commit(updateBm(b.id, { title: $event.target.value }))"
              >
              <select
                :value="b.type"
                class="nb-input nb-type"
                @change="commit(updateBm(b.id, { type: $event.target.value }))"
              >
                <option
                  v-for="t in bookmarkTypes"
                  :key="t"
                  :value="t"
                >
                  {{ typeLabels[t] }}
                </option>
              </select>
              <button
                type="button"
                class="nb-icon-btn"
                title="Remove bookmark"
                @click="commit(removeBm(b.id))"
              >
                🗑
              </button>
            </div>
            <textarea
              :value="b.note"
              class="nb-input nb-note"
              rows="2"
              placeholder="Note"
              @change="commit(updateBm(b.id, { note: $event.target.value }))"
            />
            <div
              v-if="b.refs && b.refs.length"
              class="nb-refs"
            >
              <button
                v-for="(r, i) in b.refs"
                :key="i"
                type="button"
                class="nb-ref-chip"
                :class="{ broken: isRefBroken(b.id, i) }"
                :title="refTitle(r)"
                @click="onRefClick(r)"
              >
                {{ refChipLabel(r) }}
              </button>
            </div>
          </div>
        </div>

        <!-- Conclusion -->
        <label class="nb-field">
          <span class="nb-field-label">Conclusion</span>
          <textarea
            :value="inv.conclusion"
            class="nb-input nb-note"
            rows="3"
            placeholder="What does the evidence support? Leave blank until it does."
            @change="commit(setConcl($event.target.value))"
          />
        </label>
        <div
          v-for="chain in groundedChains"
          :key="chain.conclusion_id"
          class="nb-chain"
        >
          <strong>{{ chain.title }}</strong> ←
          <span
            v-for="(e, i) in chain.evidence"
            :key="e.id"
          >{{ i ? ' · ' : '' }}{{ typeLabels[e.type] || e.type }}: {{ e.title }}</span>
        </div>

        <!-- Links between bookmarks -->
        <div
          v-if="inv.bookmarks.length >= 2"
          class="nb-field"
        >
          <span class="nb-field-label">Links</span>
          <div class="nb-add-row">
            <select
              v-model="draft.linkFrom"
              class="nb-input nb-link-sel"
            >
              <option value="">
                from…
              </option>
              <option
                v-for="b in inv.bookmarks"
                :key="b.id"
                :value="b.id"
              >
                {{ typeLabels[b.type] }}: {{ b.title }}
              </option>
            </select>
            <select
              v-model="draft.linkRel"
              class="nb-input nb-type"
            >
              <option
                v-for="r in linkRelations"
                :key="r"
                :value="r"
              >
                {{ r }}
              </option>
            </select>
            <select
              v-model="draft.linkTo"
              class="nb-input nb-link-sel"
            >
              <option value="">
                to…
              </option>
              <option
                v-for="b in inv.bookmarks"
                :key="b.id"
                :value="b.id"
              >
                {{ typeLabels[b.type] }}: {{ b.title }}
              </option>
            </select>
            <button
              type="button"
              class="nb-btn"
              :disabled="!draft.linkFrom || !draft.linkTo || draft.linkFrom === draft.linkTo"
              @click="addLink"
            >
              Link
            </button>
          </div>
          <ul
            v-if="inv.links.length"
            class="nb-questions"
          >
            <li
              v-for="(l, i) in inv.links"
              :key="i"
            >
              <span>{{ bmTitle(l.from) }} <em>{{ l.relation }}</em> {{ bmTitle(l.to) }}</span>
              <button
                type="button"
                class="nb-icon-btn"
                title="Remove link"
                @click="commit(unlinkBm(l.from, l.to))"
              >
                ✕
              </button>
            </li>
          </ul>
        </div>

        <!-- Unresolved questions -->
        <div class="nb-field">
          <span class="nb-field-label">Unresolved questions</span>
          <div class="nb-add-row">
            <input
              v-model="draft.question"
              class="nb-input"
              type="text"
              placeholder="Add a question"
              @keydown.enter.prevent="addQuestion"
            >
            <button
              type="button"
              class="nb-btn"
              :disabled="!draft.question.trim()"
              @click="addQuestion"
            >
              Add
            </button>
          </div>
          <ul
            v-if="inv.unresolved_questions.length"
            class="nb-questions"
          >
            <li
              v-for="q in inv.unresolved_questions"
              :key="q"
            >
              <span>{{ q }}</span>
              <button
                type="button"
                class="nb-icon-btn"
                title="Remove question"
                @click="commit(rmQuestion(q))"
              >
                ✕
              </button>
            </li>
          </ul>
        </div>
      </div>

      <div class="nb-footer">
        <span class="nb-count">{{ inv.bookmarks.length }} bookmark(s)</span>
        <button
          type="button"
          class="nb-btn"
          @click="emit('close')"
        >
          Close
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import {
  BOOKMARK_TYPES,
  BOOKMARK_TYPE_LABELS,
  LINK_RELATIONS,
  NB_EMPTY_BLANK,
  NB_EMPTY_FROM_FINDINGS,
  NOTEBOOK_STATUSES,
  NOTEBOOK_STATUS_LABELS,
  addBookmark,
  addUnresolvedQuestion,
  conclusionEvidenceChains,
  detectBrokenReferences,
  dumpInvestigation,
  investigationHeader,
  linkBookmarks,
  loadInvestigation,
  removeBookmark,
  removeUnresolvedQuestion,
  setConclusion,
  setStatus,
  unlinkBookmarks,
  updateBookmark,
} from '../utils/investigationNotebook.js'

const props = defineProps({
  investigation: { type: Object, required: true },
  history: { type: Object, default: () => ({ stack: [], index: -1 }) },
  findings: { type: Array, default: () => [] },
  trace: { type: Object, default: null },
  traceFileName: { type: String, default: '' },
  cursorRange: { type: Object, default: null },
  formatNs: { type: Function, default: null },
})

const emit = defineEmits([
  'close', 'update', 'undo', 'redo', 'jump-range', 'export-evidence-package',
  'scaffold',
])

const fileInput = ref(null)
const bookmarkTypes = BOOKMARK_TYPES
const typeLabels = BOOKMARK_TYPE_LABELS
const linkRelations = LINK_RELATIONS

const draft = reactive({
  type: 'observation',
  title: '',
  note: '',
  question: '',
  useRange: false,
  findingRuleId: '',
  linkFrom: '',
  linkRel: 'relates',
  linkTo: '',
})

const inv = computed(() => loadInvestigation(props.investigation))

const historyState = computed(() => {
  const stack = props.history?.stack || []
  const idx = Number(props.history?.index ?? -1)
  return { can_undo: idx > 0, can_redo: idx >= 0 && idx < stack.length - 1 }
})

const groups = computed(() =>
  bookmarkTypes.map((type) => ({
    type,
    items: inv.value.bookmarks.filter((b) => b.type === type),
  })),
)

const findingOptions = computed(() => {
  const seen = new Set()
  const out = []
  for (const f of props.findings || []) {
    const rid = String(f.rule_id || f.ruleId || f.id || '').trim()
    if (!rid || seen.has(rid)) continue
    seen.add(rid)
    out.push({ rule_id: rid, label: `${f.severity || 'info'} · ${f.title || rid}` })
  }
  return out
})

const broken = computed(() =>
  detectBrokenReferences(props.investigation, {
    trace: props.trace,
    knownRuleIds: findingOptions.value.map((f) => f.rule_id),
  }),
)
const brokenIds = computed(() => new Set(broken.value.issues.map((i) => i.bookmark_id)))
const brokenCount = computed(() => broken.value.issues.length + (broken.value.stale_trace ? 1 : 0))
const groundedChains = computed(() =>
  conclusionEvidenceChains(props.investigation).filter((c) => c.grounded),
)

// §7 — compact header + durable status + empty-state entry points.
const header = computed(() => investigationHeader(props.investigation, { broken: broken.value }))
const statusOptions = NOTEBOOK_STATUSES.map((s) => ({ value: s, label: NOTEBOOK_STATUS_LABELS[s] }))
const isEmpty = computed(() =>
  !inv.value.bookmarks.length
  && !String(inv.value.title || '').trim()
  && !String(inv.value.conclusion || '').trim()
  && !(inv.value.unresolved_questions || []).length,
)
const emptyFromFindings = NB_EMPTY_FROM_FINDINGS
const emptyBlank = NB_EMPTY_BLANK

function changeStatus(next) {
  commit(setStatus(props.investigation, next))
}
function startBlank() {
  // Blank investigation: the editor is already shown — just focus the title.
  const el = document.querySelector('.nb-dialog .nb-field .nb-input')
  if (el) el.focus()
}

function fmt(ns) {
  const f = props.formatNs || ((v) => String(Math.trunc(v)))
  return f(ns)
}

function commit(nextInv) {
  emit('update', nextInv)
}

// --- mutation builders (pure; App owns history) ---
function setTitle(title) {
  return loadInvestigation({ ...inv.value, title: String(title || '').trim() })
}
function updateBm(id, changes) {
  return updateBookmark(props.investigation, id, changes)
}
function removeBm(id) {
  return removeBookmark(props.investigation, id)
}
function setConcl(text) {
  return setConclusion(props.investigation, text)
}
function rmQuestion(q) {
  return removeUnresolvedQuestion(props.investigation, q)
}
function unlinkBm(from, to) {
  return unlinkBookmarks(props.investigation, from, to)
}
function bmTitle(id) {
  const b = inv.value.bookmarks.find((x) => x.id === id)
  return b ? b.title : id
}
function addLink() {
  if (!draft.linkFrom || !draft.linkTo || draft.linkFrom === draft.linkTo) return
  commit(linkBookmarks(props.investigation, draft.linkFrom, draft.linkTo, draft.linkRel))
  draft.linkFrom = ''
  draft.linkTo = ''
}

function addDraft() {
  if (!draft.title.trim()) return
  const refs = []
  if (draft.useRange && props.cursorRange) {
    refs.push({
      kind: 'range',
      range: { start: props.cursorRange.start, end: props.cursorRange.end },
    })
  }
  if (draft.findingRuleId) {
    refs.push({ kind: 'finding', rule_id: draft.findingRuleId })
  }
  commit(addBookmark(props.investigation, {
    type: draft.type,
    title: draft.title.trim(),
    note: draft.note,
    refs,
  }))
  draft.title = ''
  draft.note = ''
  draft.findingRuleId = ''
  draft.useRange = false
}

function addQuestion() {
  if (!draft.question.trim()) return
  commit(addUnresolvedQuestion(props.investigation, draft.question.trim()))
  draft.question = ''
}

function isRefBroken(bid, i) {
  return broken.value.issues.some((x) => x.bookmark_id === bid && x.ref_index === i)
}
function refChipLabel(r) {
  if (r.kind === 'finding') return `finding: ${r.rule_id || r.label || '?'}`
  if (r.kind === 'metric') return `metric: ${r.metric || r.label || '?'}`
  if (r.kind === 'entity') return `entity: ${r.entity || r.label || '?'}`
  if (r.kind === 'range' && r.range) return `range ${fmt(r.range.start)}–${fmt(r.range.end)}`
  if (r.kind === 'evidence') return r.time != null ? `evidence @ ${fmt(r.time)}` : 'evidence'
  return r.kind || 'ref'
}
function refTitle(r) {
  return r.label || refChipLabel(r)
}
function onRefClick(r) {
  if ((r.kind === 'range' || r.kind === 'evidence') && r.range) {
    emit('jump-range', { start: r.range.start, end: r.range.end })
  }
}

function exportJson() {
  const base = (props.traceFileName || 'investigation').replace(/\.btf(\.gz)?$/i, '')
  const blob = new Blob([dumpInvestigation(props.investigation)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${base}-investigation.json`
  a.click()
  URL.revokeObjectURL(url)
}

function emitEvidencePackage() {
  const question = window.prompt(
    'Question the AI evidence package should answer:',
    props.investigation?.title || '',
  )
  if (question == null) return
  emit('export-evidence-package', { question: String(question).trim() })
}

async function onImportFile(ev) {
  const file = ev.target.files?.[0]
  ev.target.value = ''
  if (!file) return
  try {
    const text = await file.text()
    commit(loadInvestigation(text))
  } catch {
    /* ignore malformed file */
  }
}
</script>

<style scoped>
.dialog-overlay {
  position: fixed;
  inset: 0;
  background: color-mix(in srgb, #000 52%, transparent);
  backdrop-filter: blur(5px) saturate(1.1);
  -webkit-backdrop-filter: blur(5px) saturate(1.1);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10000;
}
.nb-dialog {
  background: var(--panel-bg);
  border: 1px solid var(--app-border-soft, var(--border));
  border-radius: 14px;
  width: min(680px, calc(100vw - 32px));
  max-height: min(86vh, 880px);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: 0 32px 80px -16px rgba(0, 0, 0, 0.5);
}
.nb-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 11px 14px;
  border-bottom: 1px solid var(--app-border-soft, var(--border));
  background: color-mix(in srgb, var(--panel-bg) 55%, var(--bg));
  flex-wrap: wrap;
}
.nb-title { font-weight: 650; font-size: 14px; display: flex; align-items: center; gap: 8px; }
.nb-broken-flag {
  font-size: 11px;
  font-weight: 600;
  color: var(--semantic-warning, #e67e22);
}
.nb-header-actions { display: flex; align-items: center; gap: 6px; }
.nb-context {
  flex-basis: 100%;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 10px;
  margin-top: 4px;
  font-size: 11px;
  color: var(--fg-dim);
}
.nb-status { display: inline-flex; align-items: center; gap: 5px; }
.nb-status-dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: var(--fg-dim);
}
.nb-status-dot.s-open { background: #7f8c8d; }
.nb-status-dot.s-needs_evidence { background: var(--semantic-warning, #e67e22); }
.nb-status-dot.s-ready_to_conclude { background: #2e86de; }
.nb-status-dot.s-closed { background: #27ae60; }
.nb-status-select {
  font-size: 11px;
  background: transparent;
  border: 1px solid var(--border, #ccc);
  border-radius: 4px;
  padding: 1px 4px;
  color: inherit;
}
.nb-context-bit { white-space: nowrap; }
.nb-context-bit.warn { color: var(--semantic-warning, #e67e22); font-weight: 600; }
.nb-empty-actions { display: flex; gap: 8px; padding: 10px 0; }
.nb-close {
  background: none;
  border: none;
  color: var(--fg-dim);
  cursor: pointer;
  font-size: 15px;
}
.nb-body {
  padding: 14px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.nb-field { display: flex; flex-direction: column; gap: 5px; }
.nb-field-label { font-size: 12px; font-weight: 600; color: var(--fg-dim); }
.nb-input {
  padding: 6px 9px;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--bg);
  color: var(--fg);
  font-size: 13px;
  font-family: inherit;
}
.nb-input:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 22%, transparent);
}
.nb-note { resize: vertical; font-family: inherit; }
.nb-type { flex: none; min-width: 148px; }

.nb-add {
  border: 1px solid var(--app-border-soft, var(--border));
  border-radius: 10px;
  padding: 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  background: color-mix(in srgb, var(--panel-bg) 40%, var(--bg));
}
.nb-add-row { display: flex; gap: 8px; align-items: center; }
.nb-add-row .nb-input:not(.nb-type) { flex: 1; min-width: 0; }
.nb-add-refs { display: flex; flex-wrap: wrap; gap: 12px; }
.nb-chk { font-size: 11.5px; color: var(--fg-dim); display: flex; align-items: center; gap: 5px; }
.nb-ref-sel { flex: none; max-width: 260px; }
.nb-link-sel { flex: 1; min-width: 0; }

.nb-empty, .nb-group-title { font-size: 12px; color: var(--fg-dim); }
.nb-group { display: flex; flex-direction: column; gap: 8px; }
.nb-group-title { font-weight: 600; margin-top: 2px; }
.nb-item {
  border: 1px solid var(--border);
  border-radius: 9px;
  padding: 9px;
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.nb-item.broken { border-color: color-mix(in srgb, var(--semantic-warning, #e67e22) 55%, var(--border)); }
.nb-item-main { display: flex; gap: 7px; align-items: center; }
.nb-item-title { flex: 1; min-width: 0; }
.nb-icon-btn {
  background: none;
  border: 1px solid transparent;
  border-radius: 6px;
  cursor: pointer;
  color: var(--fg-dim);
  font-size: 13px;
  padding: 3px 6px;
}
.nb-icon-btn:hover { background: var(--tb-btn-hover, var(--bg)); color: var(--fg); }
.nb-refs { display: flex; flex-wrap: wrap; gap: 6px; }
.nb-ref-chip {
  font-size: 11px;
  padding: 2px 7px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: var(--panel-bg);
  color: var(--fg-dim);
  cursor: pointer;
}
.nb-ref-chip.broken {
  border-color: var(--semantic-warning, #e67e22);
  color: var(--semantic-warning, #e67e22);
}
.nb-chain {
  font-size: 11.5px;
  color: var(--fg-dim);
  line-height: 1.5;
  padding: 4px 0;
}
.nb-questions { list-style: none; margin: 4px 0 0; padding: 0; display: flex; flex-direction: column; gap: 4px; }
.nb-questions li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 12px;
}
.nb-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 11px 14px;
  border-top: 1px solid var(--app-border-soft, var(--border));
  background: color-mix(in srgb, var(--panel-bg) 55%, var(--bg));
}
.nb-count { font-size: 11px; color: var(--fg-dim); }
.nb-btn {
  padding: 5px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel-bg);
  color: var(--fg);
  font-size: 12px;
  font-weight: 550;
  cursor: pointer;
}
.nb-btn:hover:not(:disabled) { background: var(--tb-btn-hover, var(--bg)); }
.nb-btn:disabled { opacity: 0.45; cursor: default; }
.nb-btn.primary {
  background: var(--accent);
  border-color: var(--accent);
  color: #fff;
  font-weight: 650;
}
.nb-btn.primary:disabled { opacity: 0.5; }
</style>
