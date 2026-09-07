<template>
  <span
    v-if="result"
    class="th-badge-wrap"
  >
    <button
      type="button"
      class="th-badge"
      :class="`th-${result.status}`"
      :title="summary + ' — click for detail'"
      :aria-expanded="open ? 'true' : 'false'"
      @click="open = !open"
    >
      <span
        class="th-dot"
        aria-hidden="true"
      />
      <span class="th-label">{{ label }}</span>
      <span
        v-if="result.issueCount"
        class="th-count"
      >{{ result.issueCount }}</span>
    </button>

    <div
      v-if="open"
      class="th-scrim"
      @click.self="open = false"
    >
      <div
        class="th-pop"
        role="dialog"
        aria-label="Trace health detail"
      >
        <div class="th-pop-head">
          <span class="th-pop-title">Trace Health</span>
          <button
            type="button"
            class="th-pop-close"
            title="Close"
            @click="open = false"
          >✕</button>
        </div>

        <p class="th-pop-status">
          <span :class="`th-status-word th-${result.status}`">{{ label }}</span>
          <span class="th-pop-sub">· {{ result.issueCount }} structural issue(s)</span>
        </p>
        <p class="th-pop-note">
          Structural checks on the parsed event model, independent of AI and of
          <em>Trace Health (TICK)</em>. Passing means the statistics below rest on a
          consistent event stream — not that the system is healthy.
        </p>

        <ul
          v-if="result.checks && result.checks.length"
          class="th-checks"
        >
          <li
            v-for="c in result.checks"
            :key="c.id"
            class="th-check"
          >
            <span
              class="th-check-sev"
              :class="`sev-${c.severity}`"
              :title="c.severity"
              aria-hidden="true"
            />
            <div class="th-check-body">
              <div class="th-check-summary">{{ c.summary }}</div>
              <div
                v-if="rangeText(c.affectedRange)"
                class="th-check-meta"
              >
                Range: {{ rangeText(c.affectedRange) }}
              </div>
              <div
                v-if="c.metricLimitations && c.metricLimitations.length"
                class="th-check-meta"
              >
                Limited: {{ c.metricLimitations.join(', ') }}
              </div>
            </div>
          </li>
        </ul>
        <p
          v-else
          class="th-pop-note th-ok-line"
        >
          No structural issues detected in the analysed range.
        </p>
      </div>
    </div>
  </span>
</template>

<script setup>
import { computed, ref } from 'vue'
import { traceHealthStatusLabel } from '../utils/traceHealth.js'

const props = defineProps({
  result: { type: Object, default: null },
  formatNs: { type: Function, default: null },
})

const open = ref(false)

const label = computed(() => traceHealthStatusLabel(props.result?.status))
const summary = computed(() => {
  const n = Number(props.result?.issueCount || 0)
  return n
    ? `Trace health: ${label.value} · ${n} issue(s)`
    : `Trace health: ${label.value}`
})

function rangeText(range) {
  if (!range) return ''
  const lo = range.lo ?? range.start ?? range[0]
  const hi = range.hi ?? range.end ?? range[1]
  if (lo == null || hi == null) return ''
  const f = props.formatNs || ((v) => String(Math.trunc(v)))
  return `${f(lo)} – ${f(hi)}`
}
</script>

<style scoped>
.th-badge-wrap { display: inline-flex; }
.th-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 2px 8px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--panel-bg);
  color: var(--fg);
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  line-height: 1.6;
  transition: background 0.14s ease, border-color 0.14s ease;
}
.th-badge:hover { background: var(--tb-btn-hover, var(--bg)); }
.th-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--fg-dim);
  flex: none;
}
.th-badge.th-pass .th-dot { background: var(--semantic-improvement, #27ae60); }
.th-badge.th-caution .th-dot { background: var(--semantic-warning, #e67e22); }
.th-badge.th-insufficient .th-dot { background: var(--semantic-error, #e07070); }
.th-badge.th-caution { border-color: color-mix(in srgb, var(--semantic-warning, #e67e22) 45%, var(--border)); }
.th-badge.th-insufficient { border-color: color-mix(in srgb, var(--semantic-error, #e07070) 45%, var(--border)); }
.th-count {
  min-width: 15px;
  padding: 0 4px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--fg) 12%, transparent);
  text-align: center;
  font-size: 10px;
}
.th-badge.th-caution .th-count { background: color-mix(in srgb, var(--semantic-warning, #e67e22) 26%, transparent); }
.th-badge.th-insufficient .th-count { background: color-mix(in srgb, var(--semantic-error, #e07070) 26%, transparent); }

.th-scrim {
  position: fixed;
  inset: 0;
  background: color-mix(in srgb, #000 40%, transparent);
  backdrop-filter: blur(3px);
  -webkit-backdrop-filter: blur(3px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10000;
}
.th-pop {
  background: var(--panel-bg);
  border: 1px solid var(--app-border-soft, var(--border));
  border-radius: 12px;
  width: min(460px, calc(100vw - 32px));
  max-height: min(70vh, 560px);
  overflow-y: auto;
  padding: 0 0 12px;
  box-shadow: 0 32px 80px -16px rgba(0, 0, 0, 0.5);
}
.th-pop-head {
  position: sticky;
  top: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  border-bottom: 1px solid var(--app-border-soft, var(--border));
  background: color-mix(in srgb, var(--panel-bg) 60%, var(--bg));
}
.th-pop-title { font-weight: 650; font-size: 13px; }
.th-pop-close {
  background: none;
  border: none;
  color: var(--fg-dim);
  cursor: pointer;
  font-size: 14px;
}
.th-pop-status { margin: 12px 14px 4px; font-size: 13px; }
.th-status-word { font-weight: 650; }
.th-status-word.th-pass { color: var(--semantic-improvement, #27ae60); }
.th-status-word.th-caution { color: var(--semantic-warning, #e67e22); }
.th-status-word.th-insufficient { color: var(--semantic-error, #e07070); }
.th-pop-sub { color: var(--fg-dim); }
.th-pop-note { margin: 4px 14px 10px; font-size: 11.5px; color: var(--fg-dim); line-height: 1.5; }
.th-ok-line { margin-top: 10px; }

.th-checks { list-style: none; margin: 0; padding: 0 14px; }
.th-check {
  display: flex;
  gap: 9px;
  padding: 9px 0;
  border-top: 1px solid var(--line, var(--border));
}
.th-check-sev {
  width: 8px;
  height: 8px;
  margin-top: 4px;
  border-radius: 50%;
  flex: none;
  background: var(--fg-dim);
}
.th-check-sev.sev-warning { background: var(--semantic-warning, #e67e22); }
.th-check-sev.sev-error { background: var(--semantic-error, #e07070); }
.th-check-sev.sev-info { background: var(--fg-dim); }
.th-check-body { min-width: 0; }
.th-check-summary { font-size: 12px; line-height: 1.45; }
.th-check-meta { margin-top: 2px; font-size: 11px; color: var(--fg-dim); }
</style>
