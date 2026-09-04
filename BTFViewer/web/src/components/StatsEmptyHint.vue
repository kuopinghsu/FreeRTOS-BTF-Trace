<template>
  <div class="stats-empty-hint">
    <span class="stats-empty-msg">{{ message }}</span>
    <span
      v-if="hint"
      class="stats-empty-hint-text"
    >{{ hint }}</span>
    <button
      v-if="action === 'clear_scope'"
      type="button"
      class="stats-empty-action"
      @click="$emit('clear-scope')"
    >
      Turn off Limit
    </button>
    <button
      v-else-if="action === 'clear_filter'"
      type="button"
      class="stats-empty-action"
      @click="$emit('clear-filter')"
    >
      Clear filter
    </button>
  </div>
</template>

<script setup>
defineProps({
  message: { type: String, required: true },
  hint: { type: String, default: null },
  action: {
    type: String,
    default: null,
    validator: (v) => v == null || v === 'clear_scope' || v === 'clear_filter',
  },
})
defineEmits(['clear-scope', 'clear-filter'])
</script>

<style scoped>
.stats-empty-hint {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px 8px;
  color: var(--fg-dim);
  font-size: 0.92em;
  line-height: 1.35;
  padding: 4px 2px 6px;
}

.stats-empty-hint-text {
  opacity: 0.9;
}

.stats-empty-action {
  appearance: none;
  border: 1px solid var(--border, #555);
  background: transparent;
  color: var(--accent, #5B9BD5);
  border-radius: 4px;
  padding: 1px 7px;
  font-size: inherit;
  cursor: pointer;
  line-height: 1.4;
}

.stats-empty-action:hover,
.stats-empty-action:focus-visible {
  background: var(--tb-btn-hover, rgba(255, 255, 255, 0.06));
  outline: none;
}
</style>
