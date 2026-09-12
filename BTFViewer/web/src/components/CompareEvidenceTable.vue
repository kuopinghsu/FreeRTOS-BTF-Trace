<template>
  <details
    class="compare-evidence"
    open
  >
    <summary>{{ spec.title }}</summary>
    <div class="evidence-controls">
      <input
        v-model="query"
        type="search"
        :aria-label="`Search ${spec.title}`"
        placeholder="Search evidence"
      >
      <select
        v-model.number="limit"
        aria-label="Rows to show"
      >
        <option :value="10">
          Top 10
        </option><option :value="0">
          Show all
        </option>
      </select>
      <button
        type="button"
        @click="download"
      >
        CSV
      </button>
    </div>
    <div class="evidence-scroll">
      <table class="compare-table">
        <thead>
          <tr>
            <th
              v-for="(label, i) in spec.columns"
              :key="label"
              :aria-sort="sort === i ? (descending ? 'descending' : 'ascending') : 'none'"
            >
              <button
                type="button"
                @click="toggle(i)"
              >
                {{ label }} {{ sort === i ? (descending ? '▼' : '▲') : '' }}
              </button>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in visible"
            :key="row[0]"
            tabindex="0"
            :class="{ selected: selected === row[0] }"
            @click="selected = row[0]"
            @keydown.enter="selected = row[0]"
          >
            <td
              v-for="(value, i) in row"
              :key="i"
            >
              {{ cell(value, i) }}
            </td>
          </tr>
          <tr v-if="!visible.length">
            <td :colspan="spec.columns.length">
              No differences to show
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <p>{{ filtered.length }} rows. Timing values: ns. Timing/relative Δ = B − A; migration count Δ = A − B.</p>
  </details>
</template>
<script setup>
import { computed, ref } from 'vue'
import { formatEvidenceCell } from '../utils/compareEvidence.js'
const props = defineProps({ spec: { type: Object, required: true }, rows: { type: Array, default: () => [] } })
const query = ref(''), limit = ref(10), sort = ref(-1), descending = ref(false), selected = ref(null)
const cell = (value, i) => formatEvidenceCell(props.spec.key, value, i)
const filtered = computed(() => {
  const rows = props.rows.filter(row => row.some((v, i) => cell(v, i).toLowerCase().includes(query.value.toLowerCase())))
  if (sort.value >= 0) rows.sort((a, b) => {
    const x = a[sort.value], y = b[sort.value]
    const d = typeof x === 'number' && typeof y === 'number' ? x - y : cell(x, sort.value).localeCompare(cell(y, sort.value))
    return descending.value ? -d : d
  })
  return rows
})
const visible = computed(() => limit.value ? filtered.value.slice(0, limit.value) : filtered.value)
function toggle(i) { descending.value = sort.value === i ? !descending.value : false; sort.value = i }
function download() {
  const quote = v => '"' + String(v).replace(/^[=+@\t\r-]/, "'$&").replaceAll('"', '""') + '"'
  const csv = [props.spec.columns, ...filtered.value.map(r => r.map(cell))].map(r => r.map(quote).join(',')).join('\n')
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
  const a = document.createElement('a'); a.href = url; a.download = props.spec.key + '.csv'; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000)
}
</script>
<style scoped>
.compare-evidence { margin: 12px 0; font-size: 12px; line-height: 1.45; }
summary { font-size: 14px; font-weight: 600; cursor: pointer; }
.evidence-controls { display: flex; gap: 8px; margin: 6px 0; }
input, select, button { color: inherit; background: var(--panel-bg); border: 1px solid var(--border); border-radius: 3px; font: inherit; }
.evidence-scroll { overflow: auto; }
table { width: 100%; border-collapse: collapse; font-size: 12px; }
th, td { padding: 4px 6px; border-bottom: 1px solid var(--border); text-align: right; white-space: nowrap; }
th:first-child, td:first-child { text-align: left; position: sticky; left: 0; background: var(--panel-bg); }
th button { border: 0; cursor: pointer; }
tr:hover td, tr:focus-within td, tr.selected td { background: color-mix(in srgb, var(--fg) 6%, var(--panel-bg)); }
p { color: var(--fg-dim); font-size: 11px; }
@media print { .evidence-controls { display:none; } tr:hover td, tr:focus-within td { background:white; } }
</style>
