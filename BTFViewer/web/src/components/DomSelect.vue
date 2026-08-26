<template>
  <div
    ref="rootEl"
    class="dom-select"
    :class="[attrs.class, { open, disabled }]"
    v-bind="passthroughAttrs"
  >
    <button
      ref="triggerEl"
      type="button"
      class="dom-select-trigger"
      :disabled="disabled"
      :title="title"
      :aria-label="ariaLabel || undefined"
      :aria-expanded="open ? 'true' : 'false'"
      aria-haspopup="listbox"
      @click="toggle"
      @keydown="onTriggerKeydown"
    >
      <span class="dom-select-label">{{ displayLabel }}</span>
      <svg
        class="dom-select-chevron"
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
    <Teleport to="body">
      <ul
        v-if="open"
        ref="listEl"
        class="dom-select-list"
        role="listbox"
        :aria-label="ariaLabel || title || undefined"
        :style="listStyle"
      >
        <li
          v-for="opt in items"
          :key="String(opt.value)"
          role="option"
          :aria-selected="isSelected(opt) ? 'true' : 'false'"
          :class="{ selected: isSelected(opt), disabled: opt.disabled }"
          :title="opt.title || opt.label"
          @mousedown.prevent="pick(opt)"
        >
          {{ opt.label }}
        </li>
      </ul>
    </Teleport>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref, useAttrs, watch } from 'vue'
import {
  domSelectValueEqual,
  normalizeDomSelectOptions,
  placeDomSelectList,
} from '../utils/domSelect.js'

defineOptions({ inheritAttrs: false })

const props = defineProps({
  modelValue: { type: [String, Number, Boolean], default: '' },
  options: { type: Array, default: () => [] },
  disabled: { type: Boolean, default: false },
  title: { type: String, default: '' },
  ariaLabel: { type: String, default: '' },
  placeholder: { type: String, default: '' },
  maxHeight: { type: Number, default: 280 },
})

const emit = defineEmits(['update:modelValue', 'change'])
const attrs = useAttrs()
const passthroughAttrs = computed(() => {
  const { class: _cls, ...rest } = attrs
  return rest
})

const rootEl = ref(null)
const triggerEl = ref(null)
const listEl = ref(null)
const open = ref(false)
const listStyle = ref({})
let closer = null

const items = computed(() => normalizeDomSelectOptions(props.options))

const displayLabel = computed(() => {
  const hit = items.value.find(o => domSelectValueEqual(o.value, props.modelValue))
  if (hit) return hit.label
  if (props.placeholder) return props.placeholder
  return items.value[0]?.label ?? ''
})

function isSelected(opt) {
  return domSelectValueEqual(opt.value, props.modelValue)
}

function placeMenu() {
  const el = triggerEl.value || rootEl.value
  if (!el) return
  listStyle.value = placeDomSelectList(el.getBoundingClientRect(), {
    maxHeight: props.maxHeight,
    zIndex: 12050,
  })
}

function unbindCloser() {
  if (!closer) return
  document.removeEventListener('mousedown', closer)
  document.removeEventListener('scroll', placeMenu, true)
  window.removeEventListener('resize', placeMenu)
  closer = null
}

function bindCloser() {
  unbindCloser()
  nextTick(() => {
    placeMenu()
    const sel = listEl.value?.querySelector('[aria-selected="true"]')
    sel?.scrollIntoView({ block: 'nearest' })
  })
  closer = (e) => {
    const t = e.target
    if (rootEl.value?.contains(t)) return
    if (listEl.value?.contains(t)) return
    open.value = false
  }
  document.addEventListener('mousedown', closer)
  document.addEventListener('scroll', placeMenu, true)
  window.addEventListener('resize', placeMenu)
}

watch(open, (v) => {
  if (v) bindCloser()
  else unbindCloser()
})

onBeforeUnmount(unbindCloser)

function toggle() {
  if (props.disabled) return
  open.value = !open.value
}

function pick(opt) {
  if (!opt || opt.disabled) return
  if (!domSelectValueEqual(opt.value, props.modelValue)) {
    emit('update:modelValue', opt.value)
    emit('change', opt.value)
  }
  open.value = false
}

function onTriggerKeydown(ev) {
  if (props.disabled) return
  if (ev.key === 'ArrowDown' || ev.key === 'F4' || ev.key === ' ') {
    ev.preventDefault()
    open.value = true
  } else if (ev.key === 'Escape' && open.value) {
    ev.preventDefault()
    open.value = false
  } else if (ev.key === 'Enter' && open.value) {
    ev.preventDefault()
    const sel = items.value.find(o => isSelected(o)) || items.value[0]
    if (sel) pick(sel)
  }
}
</script>

<style scoped>
.dom-select {
  position: relative;
  display: block;
  width: 100%;
  min-width: 0;
}
.dom-select-trigger {
  width: 100%;
  height: 100%;
  box-sizing: border-box;
  margin: 0;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0;
  border: 0;
  border-radius: inherit;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.dom-select.disabled .dom-select-trigger {
  opacity: 0.55;
  cursor: default;
}
.dom-select-label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.dom-select-chevron {
  flex: 0 0 auto;
  opacity: 0.75;
}
.dom-select.open .dom-select-trigger {
  outline: 1px solid var(--accent, #0e639c);
  outline-offset: -1px;
}
</style>

<style>
/* Teleported list — must match page theme and appear in tab capture. */
.dom-select-list {
  margin: 0;
  padding: 4px 0;
  list-style: none;
  overflow: auto;
  background: var(--tb-bg, var(--panel-bg, var(--input-bg, #2a2a2a)));
  color: var(--fg, #ddd);
  border: 1px solid var(--border, #555);
  border-radius: 4px;
  box-shadow: 0 8px 20px rgba(0, 0, 0, 0.35);
  font-size: var(--ui-font-size, 13px);
  z-index: 12050;
}
.dom-select-list li {
  padding: 5px 10px;
  cursor: pointer;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.dom-select-list li:hover:not(.disabled),
.dom-select-list li.selected {
  background: color-mix(in srgb, var(--accent, #0e639c) 22%, transparent);
}
.dom-select-list li.disabled {
  opacity: 0.45;
  cursor: default;
}
</style>
