<template>
  <div
    class="dialog-overlay"
    @click.self="emit('close')"
  >
    <div
      class="np-dialog"
      role="dialog"
      aria-modal="true"
      aria-label="Review AI notebook proposal"
    >
      <div class="np-header">
        <div class="np-title">
          AI proposal — review before it changes the Notebook
        </div>
        <button
          type="button"
          class="np-close"
          @click="emit('close')"
        >
          ✕
        </button>
      </div>

      <div class="np-body">
        <p
          v-if="!validated.ok"
          class="np-empty"
        >
          Nothing in this proposal is applicable to the current investigation.
        </p>

        <section
          v-for="grp in groups"
          :key="grp.id"
          class="np-group"
        >
          <div class="np-group-title">
            {{ grp.label }}
          </div>
          <label
            v-for="op in grp.ops"
            :key="op.index"
            class="np-op"
            :class="{ confirm: op.status === 'needs_confirmation' }"
          >
            <input
              type="checkbox"
              :checked="selected.has(op.index)"
              @change="toggle(op.index)"
            >
            <span class="np-op-body">
              <span class="np-op-line">{{ opSummary(op) }}</span>
              <span
                v-if="op.status === 'needs_confirmation'"
                class="np-op-confirm"
              >
                <input
                  type="checkbox"
                  :checked="confirmed.has(op.index)"
                  @change="toggleConfirm(op.index)"
                >
                Confirm: {{ op.reason }}
              </span>
              <span
                v-else-if="op.reason"
                class="np-op-note"
              >{{ op.reason }}</span>
            </span>
          </label>
        </section>

        <section
          v-if="diff.rejected.length"
          class="np-group rejected"
        >
          <div class="np-group-title">
            Rejected ({{ diff.rejected.length }}) — not shown as actionable
          </div>
          <div
            v-for="op in diff.rejected"
            :key="op.index"
            class="np-op-rejected"
          >
            {{ opSummary(op) }} — {{ op.reason }}
          </div>
        </section>

        <p
          v-if="model.model || model.provider"
          class="np-model"
        >
          Proposed by {{ model.provider || 'AI' }}<template v-if="model.model"> · {{ model.model }}</template>.
          Accepted AI cards are stored with this provenance; API keys and prompts
          are never stored.
        </p>
      </div>

      <div class="np-footer">
        <button
          type="button"
          class="np-btn"
          @click="emit('reject')"
        >
          Reject
        </button>
        <span class="np-spacer" />
        <button
          type="button"
          class="np-btn"
          :disabled="!applicableSelectedCount"
          @click="acceptSelected"
        >
          Accept selected ({{ applicableSelectedCount }})
        </button>
        <button
          type="button"
          class="np-btn primary"
          :disabled="!validated.ok"
          @click="acceptAll"
        >
          Accept all
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import {
  BOOKMARK_TYPE_LABELS,
  NOTEBOOK_STATUS_LABELS,
  loadInvestigation,
} from '../utils/investigationNotebook.js'
import { validateProposal, proposalDiff } from '../utils/investigationAi.js'

const props = defineProps({
  investigation: { type: Object, required: true },
  proposal: { type: Object, required: true },
  allowOtherTrace: { type: Boolean, default: false },
})

const emit = defineEmits(['close', 'reject', 'apply'])

const selected = reactive(new Set())
const confirmed = reactive(new Set())
const _bump = ref(0)
function touch() { _bump.value++ }

const inv = computed(() => loadInvestigation(props.investigation))
const validated = computed(() =>
  validateProposal(props.investigation, props.proposal, { allowOtherTrace: props.allowOtherTrace }),
)
const diff = computed(() => proposalDiff(props.investigation, validated.value))
const model = computed(() => validated.value.model || {})

const groups = computed(() => {
  const s = diff.value.by_section
  return [
    { id: 'hypotheses', label: 'Hypotheses', ops: s.hypotheses },
    { id: 'evidence', label: 'Evidence', ops: s.evidence },
    { id: 'conclusion', label: 'Conclusion', ops: s.conclusion },
    { id: 'status', label: 'Status', ops: s.status },
    { id: 'links', label: 'Links', ops: s.links },
  ].filter((g) => g.ops.length)
})

// Pre-select every immediately-applicable op; leave needs_confirmation unchecked.
watch(validated, (v) => {
  selected.clear()
  confirmed.clear()
  for (const op of v.operations || []) {
    if (op.status === 'ok') selected.add(op.index)
  }
  touch()
}, { immediate: true })

const applicableSelected = computed(() => {
  void _bump.value
  return (validated.value.operations || []).filter((op) => {
    if (!selected.has(op.index)) return false
    if (op.status === 'ok') return true
    if (op.status === 'needs_confirmation') return confirmed.has(op.index)
    return false
  })
})
const applicableSelectedCount = computed(() => applicableSelected.value.length)

function toggle(i) {
  if (selected.has(i)) selected.delete(i)
  else selected.add(i)
  touch()
}
function toggleConfirm(i) {
  if (confirmed.has(i)) confirmed.delete(i)
  else { confirmed.add(i); selected.add(i) }
  touch()
}

function bmTitle(id) {
  const b = inv.value.bookmarks.find((x) => String(x.id) === String(id))
  return b ? b.title : id
}
function opSummary(op) {
  const role = String(op.role || op.type || '')
  if (op.op === 'add') {
    const label = BOOKMARK_TYPE_LABELS[role] || role || 'evidence'
    return `Add ${label}: "${op.title || '(untitled)'}"`
  }
  if (op.op === 'update') {
    if ('conclusion' in (op.changes || {})) return 'Replace the conclusion text'
    return `Edit explanation of "${bmTitle(op.bookmark_id)}"`
  }
  if (op.op === 'link') {
    return `Link "${bmTitle(op.from)}" —${op.relation || 'relates'}→ "${bmTitle(op.to)}"`
  }
  if (op.op === 'change_status') {
    const s = op.status_value || op.status
    return `Set status to ${NOTEBOOK_STATUS_LABELS[s] || s}`
  }
  if (op.op === 'remove') {
    return `Remove "${bmTitle(op.bookmark_id)}"`
  }
  return op.op || 'operation'
}

function acceptSelected() {
  emit('apply', {
    validated: validated.value,
    acceptIndices: [...selected],
    confirmedIndices: [...confirmed],
    acceptAll: false,
  })
}
function acceptAll() {
  emit('apply', {
    validated: validated.value,
    acceptIndices: null,
    confirmedIndices: (validated.value.operations || [])
      .filter((op) => op.status === 'needs_confirmation').map((op) => op.index),
    acceptAll: true,
  })
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
  z-index: 10001;
}
.np-dialog {
  background: var(--panel-bg);
  border: 1px solid var(--app-border-soft, var(--border));
  border-radius: 14px;
  width: min(560px, calc(100vw - 32px));
  max-height: min(84vh, 760px);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: 0 32px 80px -16px rgba(0, 0, 0, 0.5);
}
.np-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 11px 14px;
  border-bottom: 1px solid var(--app-border-soft, var(--border));
  background: color-mix(in srgb, var(--panel-bg) 55%, var(--bg));
}
.np-title { font-weight: 650; font-size: 13px; }
.np-close { background: none; border: none; color: var(--fg-dim); cursor: pointer; font-size: 15px; }
.np-body { padding: 13px 14px; overflow-y: auto; display: flex; flex-direction: column; gap: 12px; }
.np-empty { font-size: 12px; color: var(--fg-dim); }
.np-group { display: flex; flex-direction: column; gap: 6px; }
.np-group-title { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.03em; color: var(--fg-dim); }
.np-group.rejected .np-group-title { color: var(--semantic-warning, #e67e22); }
.np-op {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  padding: 7px 9px;
  border: 1px solid var(--border);
  border-radius: 8px;
  font-size: 12.5px;
  cursor: pointer;
}
.np-op.confirm { border-color: color-mix(in srgb, var(--semantic-warning, #e67e22) 55%, var(--border)); }
.np-op-body { display: flex; flex-direction: column; gap: 3px; }
.np-op-confirm { font-size: 11px; color: var(--semantic-warning, #e67e22); display: flex; align-items: center; gap: 5px; }
.np-op-note { font-size: 11px; color: var(--fg-dim); }
.np-op-rejected { font-size: 11.5px; color: var(--fg-dim); padding: 3px 0; }
.np-model { font-size: 10.5px; color: var(--fg-dim); line-height: 1.5; margin: 0; }
.np-footer {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 11px 14px;
  border-top: 1px solid var(--app-border-soft, var(--border));
  background: color-mix(in srgb, var(--panel-bg) 55%, var(--bg));
}
.np-spacer { flex: 1; }
.np-btn {
  padding: 5px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel-bg);
  color: var(--fg);
  font-size: 12px;
  font-weight: 550;
  cursor: pointer;
}
.np-btn:hover:not(:disabled) { background: var(--tb-btn-hover, var(--bg)); }
.np-btn:disabled { opacity: 0.45; cursor: default; }
.np-btn.primary { background: var(--accent); border-color: var(--accent); color: #fff; font-weight: 650; }
</style>
