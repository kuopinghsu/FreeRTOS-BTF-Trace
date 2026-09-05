<template>
  <div class="stats-section-header-wrap">
  <div
    class="stats-section-title collapsible"
    :class="{ pinned }"
    :data-demo-target="demoTarget || undefined"
    @click="$emit('toggle')"
  >
    <span
      class="stats-drag-handle"
      draggable="true"
      title="Drag to reorder"
      aria-label="Drag to reorder section"
      @click.stop
      @dragstart.stop="onDragStart"
      @dragend.stop="onDragEnd"
    >⠿</span>
    <svg
      class="chevron"
      :class="{ collapsed }"
      viewBox="0 0 10 10"
      width="10"
      height="10"
      aria-hidden="true"
    >
      <polyline
        points="2,3 5,7 8,3"
        fill="none"
        stroke="currentColor"
        stroke-width="1.5"
        stroke-linecap="round"
        stroke-linejoin="round"
      />
    </svg>
    <span class="stats-section-label"><slot /></span>
    <span class="stats-header-meta">
      <span
        v-if="effectiveScopeLabel"
        class="stats-meta-chip scope"
        :title="`Scope limited to ${effectiveScopeLabel}`"
      >{{ effectiveScopeLabel }}</span>
      <span
        v-if="effectiveFilterLabel"
        class="stats-meta-chip filtered"
        :title="`Statistics reflect Filter: ${effectiveFilterLabel}`"
      >Filtered</span>
      <span
        v-if="category"
        class="stats-category-badge"
        :class="categoryClass"
        :title="categoryBadgeTitle"
      >{{ category }}</span>
      <span
        v-if="helpText"
        class="stats-section-help-icon"
        :title="`Open in Statistics Reference — ${helpText}`"
        role="button"
        tabindex="0"
        aria-label="Open Statistics Reference for this section"
        @click.stop="$emit('openReference', sectionId)"
        @keydown.enter.stop="$emit('openReference', sectionId)"
        @keydown.space.stop.prevent="$emit('openReference', sectionId)"
      >ⓘ</span>
      <slot name="actions" />
      <span
        class="stats-pin-slot"
        :style="{ width: `${STATS_PIN_SLOT_W}px`, height: `${STATS_PIN_SLOT_H}px` }"
      >
        <button
          type="button"
          class="stats-pin-btn"
          :class="{ active: pinned }"
          :style="{ width: `${STATS_PIN_SLOT_W}px`, height: `${STATS_PIN_SLOT_H}px` }"
          :title="pinned ? 'Pinned — stays open with Collapse All' : 'Pin open'"
          :aria-label="pinned ? 'Unpin' : 'Pin open'"
          :aria-pressed="pinned ? 'true' : 'false'"
          @click.stop="$emit('togglePin')"
        >
          <!-- outline thumbtack when unpinned -->
          <svg
            v-if="!pinned"
            class="pin-icon"
            viewBox="0 0 16 16"
            :width="STATS_PIN_ICON_PX"
            :height="STATS_PIN_ICON_PX"
            aria-hidden="true"
          >
            <path
              fill="currentColor"
              d="M8 1.25A2.75 2.75 0 0 1 10.75 4c0 .95-.48 1.78-1.2 2.27V13.5L8 11.8 6.45 13.5V6.27A2.75 2.75 0 0 1 5.25 4 2.75 2.75 0 0 1 8 1.25zm0 1.5A1.25 1.25 0 0 0 6.75 4c0 .5.28.93.7 1.15l.3.14v6.1l.25-.27.25.27V5.29l.3-.14c.42-.22.7-.65.7-1.15A1.25 1.25 0 0 0 8 2.75z"
            />
          </svg>
          <!-- filled thumbtack when pinned -->
          <svg
            v-else
            class="pin-icon"
            viewBox="0 0 16 16"
            :width="STATS_PIN_ICON_PX"
            :height="STATS_PIN_ICON_PX"
            aria-hidden="true"
          >
            <path
              fill="currentColor"
              d="M8 1.25A2.75 2.75 0 0 1 10.75 4c0 .95-.48 1.78-1.2 2.27V13.5L8 11.8 6.45 13.5V6.27A2.75 2.75 0 0 1 5.25 4 2.75 2.75 0 0 1 8 1.25z"
            />
          </svg>
        </button>
      </span>
    </span>
  </div>
  </div>
</template>

<script setup>
import { computed, inject, unref } from 'vue'
import { STATS_PIN_ICON_PX, STATS_PIN_SLOT_H, STATS_PIN_SLOT_W, STATS_SECTION_HELP } from '../config.js'
import { statsSectionCategory } from '../utils/statsPins.js'

const MIME = 'application/x-btf-stats-section'

const props = defineProps({
  collapsed: { type: Boolean, default: false },
  pinned: { type: Boolean, default: false },
  sectionId: { type: String, default: '' },
  demoTarget: { type: String, default: '' },
  /** Compact chip when Scope is limited, e.g. "C1–C2". */
  scopeLabel: { type: String, default: null },
  /** Active Filter label; chip shows "Filtered" when set. */
  filterLabel: { type: String, default: null },
})

const injectedScope = inject('statsHeaderScopeLabel', null)
const injectedFilter = inject('statsHeaderFilterLabel', null)

const helpText = computed(() => STATS_SECTION_HELP[props.sectionId] || '')
const category = computed(() => statsSectionCategory(props.sectionId) || '')
const categoryClass = computed(() => {
  const cat = category.value
  return cat ? `cat-${cat.toLowerCase()}` : ''
})
/** Help belongs on the badge (Desktop has no separate ``?`` control). */
const categoryBadgeTitle = computed(() => {
  const cat = category.value
  if (!cat) return ''
  const base = `${cat} — investigation category`
  const help = helpText.value
  return help ? `${base}\n\n${help}` : base
})

const effectiveScopeLabel = computed(() => {
  if (props.scopeLabel != null && props.scopeLabel !== '') return props.scopeLabel
  const inj = injectedScope != null ? unref(injectedScope) : ''
  return inj || ''
})

const effectiveFilterLabel = computed(() => {
  if (props.filterLabel != null && props.filterLabel !== '') return props.filterLabel
  const inj = injectedFilter != null ? unref(injectedFilter) : ''
  return inj || ''
})

const emit = defineEmits(['toggle', 'togglePin', 'dragStart', 'dragEnd', 'openReference'])

function onDragStart(e) {
  const sid = String(props.sectionId || '').trim()
  if (!sid || !e.dataTransfer) return
  e.dataTransfer.effectAllowed = 'move'
  e.dataTransfer.setData(MIME, sid)
  e.dataTransfer.setData('text/plain', sid)
  emit('dragStart', sid)
}

function onDragEnd() {
  emit('dragEnd')
}
</script>

<style scoped>
.stats-section-header-wrap {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.range-hint {
  color: var(--fg-dim, #9e9e9e);
  opacity: 0.85;
  font-size: var(--type-meta, 11px);
  font-style: normal;
  font-weight: 400;
  text-transform: none;
  letter-spacing: 0;
  white-space: nowrap;
  min-width: 0;
  margin: 0 0 4px;
  line-height: 1.35;
}

.stats-section-help {
  display: flex;
  align-items: center;
}

.stats-section-help-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.1em;
  height: 1.1em;
  font-size: var(--type-meta, 11px);
  font-style: normal;
  cursor: pointer;
  color: var(--fg-dim);
  opacity: 0.9;
  border-radius: 50%;
}

.stats-section-help-icon:hover,
.stats-section-help-icon:focus-visible {
  color: var(--accent, #4F8BFF);
  opacity: 1;
  outline: none;
  box-shadow: 0 0 0 3px rgba(79, 139, 255, 0.2);
}

.stats-section-title {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  box-sizing: border-box;
  font-family: var(--font-ui, inherit);
  font-size: var(--type-meta, 11px);
  font-weight: 600;
  letter-spacing: 0.02em;
  color: var(--fg, #e0e0e0);
  margin-bottom: 4px;
  min-height: 24px;
}

.stats-section-title.collapsible {
  cursor: pointer;
  user-select: none;
}

.stats-section-title.collapsible:hover .stats-section-label {
  color: var(--accent, #4F8BFF);
}

.stats-drag-handle {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 14px;
  color: var(--fg-dim, #9e9e9e);
  cursor: grab;
  opacity: 0.7;
  font-size: 12px;
  line-height: 1;
  user-select: none;
}

.stats-drag-handle:hover {
  opacity: 1;
  color: var(--fg, #e0e0e0);
}

.stats-drag-handle:active {
  cursor: grabbing;
}

.stats-section-label {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.stats-header-meta {
  flex: 0 0 auto;
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 2px;
  min-height: 22px;
}

.stats-meta-chip {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.3px;
  text-transform: none;
  border-radius: 8px;
  padding: 2px 6px;
  min-height: 14px;
  line-height: 1.2;
  max-width: 7.5em;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.stats-meta-chip.scope {
  color: var(--badge-scope-fg, #9EC5E8);
  background: var(--badge-scope-bg, #283A47);
  border: 1px solid var(--badge-scope-border, #3A6A8A);
}

.stats-meta-chip.filtered {
  color: var(--badge-filtered-fg, #e0c070);
  background: var(--badge-filtered-bg, rgba(230, 180, 60, 0.16));
  border: 1px solid var(--badge-filtered-border, rgba(212, 172, 13, 0.45));
}

.stats-category-badge {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  font-family: var(--font-ui, inherit);
  font-size: 9.5px;
  font-weight: 700;
  letter-spacing: 0.5px;
  text-transform: uppercase;
  border-radius: 8px;
  padding: 2px 7px;
  min-height: 15px;
  line-height: 1.2;
  /* Soft tinted round-rect — lockstep with Desktop category badges
     (stats_category_badge_stylesheet: border-radius:8px). */
  color: var(--badge-detail-fg, #c0c4c9);
  background: var(--badge-detail-bg, #303337);
  border: 1px solid var(--badge-detail-border, #565b61);
}

.stats-category-badge.cat-overview {
  color: var(--badge-overview-fg);
  background: var(--badge-overview-bg);
  border-color: var(--badge-overview-border);
}

.stats-category-badge.cat-triage {
  color: var(--badge-triage-fg);
  background: var(--badge-triage-bg);
  border-color: var(--badge-triage-border);
}

.stats-category-badge.cat-timing {
  color: var(--badge-timing-fg);
  background: var(--badge-timing-bg);
  border-color: var(--badge-timing-border);
}

.stats-category-badge.cat-sched {
  color: var(--badge-sched-fg);
  background: var(--badge-sched-bg);
  border-color: var(--badge-sched-border);
}

.stats-category-badge.cat-sync {
  color: var(--badge-sync-fg);
  background: var(--badge-sync-bg);
  border-color: var(--badge-sync-border);
}

.stats-category-badge.cat-detail {
  color: var(--badge-detail-fg);
  background: var(--badge-detail-bg);
  border-color: var(--badge-detail-border);
}

.chevron {
  flex: 0 0 auto;
  transition: transform 0.15s;
  color: inherit;
}

.chevron.collapsed {
  transform: rotate(-90deg);
}

/* Narrow vertical bar (Desktop ``stats_section_pin_slot`` parity: 14×22). */
.stats-pin-slot {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

.stats-pin-btn {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
  appearance: none;
  -webkit-appearance: none;
  min-width: 0;
  min-height: 0;
  padding: 0;
  margin: 0;
  border: none;
  border-radius: 3px;
  background: transparent;
  color: var(--fg-dim, #9e9e9e);
  cursor: pointer;
  opacity: 0;
  pointer-events: none;
  overflow: hidden;
}

/* Hover devices: row hover reveals icon only — no fill until pointer is on pin. */
@media (hover: hover) {
  .stats-section-title:hover .stats-pin-btn:not(.active),
  .stats-section-title:focus-within .stats-pin-btn:not(.active) {
    opacity: 0.75;
    pointer-events: auto;
    background: transparent;
  }
}

/* Touch / no-hover: keep outline pin discoverable without hover. */
@media (hover: none) {
  .stats-pin-btn:not(.active) {
    opacity: 0.55;
    pointer-events: auto;
  }
}

.stats-pin-btn:hover,
.stats-pin-btn:focus-visible {
  opacity: 1;
  pointer-events: auto;
  color: var(--fg, #e0e0e0);
  background: rgba(128, 128, 128, 0.28);
  outline: none;
}

.stats-pin-btn.active {
  opacity: 1;
  pointer-events: auto;
  color: var(--fg, #e0e0e0);
  background: transparent;
}

.stats-section-title.pinned .stats-section-label {
  color: var(--fg, #e0e0e0);
}

.pin-icon {
  display: block;
  flex: 0 0 auto;
}
</style>
