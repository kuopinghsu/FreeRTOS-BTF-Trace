<template>
  <DomSelect
    :model-value="prefs.format"
    :options="options"
    :aria-label="`Tag settings for ${channel}`"
    :title="value ? 'Saved for this trace' : 'Default settings'"
    @click.stop
    @keydown.stop
    @update:model-value="emit('change', $event)"
  />
</template>
<script setup>
import { computed } from 'vue'
import DomSelect from './DomSelect.vue'
import { tagPreferences, TAG_REPRESENTATION_OPTIONS, tagRawUint32, interpretTagValue, formatTagValue } from '../utils/tagAnalysis.js'
const props = defineProps({ channel: { type: String, required: true }, value: { type: [String, Object], default: null }, trace: { type: Object, default: null } })
const emit = defineEmits(['change'])
const prefs = computed(() => tagPreferences(props.value))
const options = computed(() => {
  const sample = props.trace?.tagSamplesByChannel?.get(props.channel)?.[0]
  const raw = sample?.rawValue ?? sample?.rawUint32
  const bits = tagRawUint32(raw)
  const preview = option => bits == null ? option.title : `${option.title} · 0x${bits.toString(16).padStart(8, '0').toUpperCase()} → ${formatTagValue(interpretTagValue(raw, option.value))}`
  return [
    { value: 'heading-format', label: 'Data format', disabled: true },
    ...TAG_REPRESENTATION_OPTIONS.map(o => ({ ...o, label: o.label, title: preview(o) })),
    { value: 'heading-preview', label: bits == null ? 'No sample available' : preview(TAG_REPRESENTATION_OPTIONS.find(o => o.value === prefs.value.format)), disabled: true },
    { value: 'heading-scale', label: 'Chart scale', disabled: true },
    { value: 'linear', label: `${prefs.value.scale === 'linear' ? '✓ ' : ''}Linear` },
    { value: 'log2', label: `${prefs.value.scale === 'log2' ? '✓ ' : ''}Log₂ (signed log₂(1 + |value|))` },
    { value: 'zero', label: `${prefs.value.includeZero ? '✓ ' : ''}Include zero` },
    { value: 'all', label: 'Apply these settings to all tag channels' },
    { value: 'reset', label: 'Reset to default' },
    { value: 'saved', label: props.value ? 'Saved for this trace' : 'Default · UInt32 / Linear / Fit range', disabled: true },
  ]
})
</script>
<style scoped>
:deep(.dom-select-trigger) { border-radius: 999px; min-height: 22px; font-size: 11px; }
</style>
