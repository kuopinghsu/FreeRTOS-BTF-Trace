<template>
  <DomSelect
    v-bind="$attrs"
    :model-value="prefs.format"
    :options="options"
    :max-height="420"
    :menu-width="440"
    :aria-label="`Tag settings for ${channel}`"
    :title="value ? 'Saved for this trace' : 'Default settings'"
    @click.stop
    @keydown.stop
    @update:model-value="onCommand"
  />
  <Teleport to="body">
    <div
      v-if="renaming"
      class="tag-alias-overlay"
      @click.self="closeRename"
      @keydown.esc.stop.prevent="closeRename"
    >
      <form
        class="tag-alias-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="tag-alias-title"
        @submit.prevent="saveAlias"
        @keydown.esc.stop.prevent="closeRename"
        @keydown.stop
      >
        <h3 id="tag-alias-title">
          Rename tag
        </h3>
        <p>Channel: {{ channel }}</p>
        <label for="tag-alias-input">Display name</label>
        <input
          id="tag-alias-input"
          ref="aliasInput"
          v-model="draftAlias"
          maxlength="80"
          :placeholder="tagChannelLabel(channel)"
          @keydown.tab.shift.prevent="cancelButton?.focus()"
        >
        <p class="tag-alias-help">
          Saved for this trace. Leave blank to restore the original name.
        </p>
        <div class="tag-alias-actions">
          <button type="submit">
            Save
          </button>
          <button
            ref="cancelButton"
            type="button"
            @click="closeRename"
            @keydown.tab.exact.prevent="aliasInput?.focus()"
          >
            Cancel
          </button>
        </div>
      </form>
    </div>
  </Teleport>
</template>
<script setup>
import { computed, nextTick, ref } from 'vue'
import DomSelect from './DomSelect.vue'
import { tagPreferences, tagChannelLabel, TAG_REPRESENTATION_OPTIONS, tagRawUint32, interpretTagValue, formatTagValue } from '../utils/tagAnalysis.js'
defineOptions({ inheritAttrs: false })
const props = defineProps({ channel: { type: String, required: true }, value: { type: [String, Object], default: null }, trace: { type: Object, default: null } })
const emit = defineEmits(['change'])
const prefs = computed(() => tagPreferences(props.value))
const renaming = ref(false)
const draftAlias = ref('')
const aliasInput = ref(null)
const cancelButton = ref(null)
let renameTrigger = null
function closeRename() {
  renaming.value = false
  nextTick(() => renameTrigger?.focus())
}
function saveAlias() {
  emit('change', `alias:${draftAlias.value}`)
  closeRename()
}
function onCommand(command) {
  if (command !== 'rename') { emit('change', command); return }
  renameTrigger = document.activeElement
  draftAlias.value = prefs.value.alias || ''
  renaming.value = true
  nextTick(() => { aliasInput.value?.focus(); aliasInput.value?.select() })
}
const options = computed(() => {
  const sample = props.trace?.tagSamplesByChannel?.get(props.channel)?.[0]
  const raw = sample?.rawValue ?? sample?.rawUint32
  const bits = tagRawUint32(raw)
  const preview = option => bits == null ? option.title : `${option.title} · 0x${bits.toString(16).padStart(8, '0').toUpperCase()} → ${formatTagValue(interpretTagValue(raw, option.value))}`
  return [
    { value: 'rename', label: 'Rename tag…' },
    ...(prefs.value.alias ? [{ value: 'alias:', label: 'Reset tag name' }] : []),
    { value: 'heading-format', label: 'Data format', disabled: true },
    ...TAG_REPRESENTATION_OPTIONS.map(o => ({ ...o, label: o.label, title: preview(o) })),
    { value: 'heading-preview', label: bits == null ? 'No sample available' : preview(TAG_REPRESENTATION_OPTIONS.find(o => o.value === prefs.value.format)), disabled: true },
    { value: 'heading-scale', label: 'Chart scale', disabled: true },
    { value: 'linear', label: `${prefs.value.scale === 'linear' ? '✓ ' : ''}Linear` },
    {
      value: 'log2',
      label: `${prefs.value.scale === 'log2' ? '✓ ' : ''}Log₂ (signed log₂(${prefs.value.format === 'float32' ? '|value|' : '1 + |value|'}))`,
    },
    { value: 'zero', label: `${prefs.value.includeZero ? '✓ ' : ''}Include zero` },
    { value: 'all', label: 'Apply these settings to all tag channels' },
    { value: 'reset', label: 'Reset to default' },
    { value: 'saved', label: props.value ? 'Saved for this trace' : 'Default · UInt32 / Linear / Fit range', disabled: true },
  ]
})
</script>
<style scoped>
:deep(.dom-select-trigger) { border-radius: 999px; min-height: 22px; font-size: 11px; }
.tag-alias-overlay { position: fixed; inset: 0; z-index: 13000; display: grid; place-items: center; background: #0008; }
.tag-alias-dialog { width: min(400px, calc(100vw - 48px)); padding: 20px; border-radius: 12px; border: 1px solid var(--border); background: var(--panel-bg, #252525); color: var(--fg, #eee); box-shadow: 0 12px 40px #0005; }
.tag-alias-dialog h3 { margin: 0 0 12px; }
.tag-alias-dialog label { display: block; margin-bottom: 6px; }
.tag-alias-dialog input { box-sizing: border-box; width: 100%; padding: 8px; border-radius: 6px; border: 1px solid var(--border); background: var(--bg, #181818); color: inherit; }
.tag-alias-help { font-size: 12px; color: var(--fg-dim, #aaa); }
.tag-alias-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
.tag-alias-actions button { padding: 6px 14px; border: 1px solid var(--border); border-radius: 6px; background: var(--bg, #181818); color: inherit; cursor: pointer; }
</style>
