<template>
  <div
    class="compare-dialog-overlay"
    @click.self="emit('close')"
  >
    <div
      class="compare-dialog"
      role="dialog"
      aria-modal="true"
      aria-label="Trace compare"
    >
      <div class="compare-dialog-header">
        <div class="compare-dialog-title">Trace Compare</div>
        <button
          type="button"
          class="compare-close-btn"
          @click="emit('close')"
        >
          Close
        </button>
      </div>

      <div class="compare-select-row">
        <label class="compare-select-label">
          Trace A:
          <select
            v-model="tabAId"
            class="compare-select"
          >
            <option
              v-for="tab in tabs"
              :key="tab.id"
              :value="tab.id"
            >
              {{ tab.name }}
            </option>
          </select>
        </label>
        <label class="compare-select-label">
          Trace B:
          <select
            v-model="tabBId"
            class="compare-select"
          >
            <option
              v-for="tab in tabs"
              :key="tab.id"
              :value="tab.id"
            >
              {{ tab.name }}
            </option>
          </select>
        </label>
      </div>

      <label class="compare-scope">
        <input
          v-model="scopeToCursors"
          type="checkbox"
        />
        Limit to each tab's cursor range (C1–Cn, when 2+ cursors placed)
      </label>

      <div class="compare-tabs" role="tablist">
        <button
          v-for="tab in pageTabs"
          :key="tab.id"
          type="button"
          class="compare-tab"
          :class="{ active: activePage === tab.id }"
          role="tab"
          :aria-selected="activePage === tab.id"
          @click="activePage = tab.id"
        >
          {{ tab.label }}
        </button>
      </div>

      <div class="compare-table-wrap">
        <table
          v-if="activePage === 'summary'"
          class="compare-table"
        >
          <thead>
            <tr>
              <th>Metric</th>
              <th>Trace A</th>
              <th>Trace B</th>
              <th>Δ</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in summaryRows"
              :key="row.label"
            >
              <td class="task-col">{{ row.label }}</td>
              <td>{{ row.a }}</td>
              <td>{{ row.b }}</td>
              <td>{{ row.delta }}</td>
            </tr>
          </tbody>
        </table>

        <table
          v-else-if="activePage === 'top'"
          class="compare-table"
        >
          <thead>
            <tr>
              <th>Task</th>
              <th>CPU% A</th>
              <th>CPU% B</th>
              <th>Δ</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in topTaskRows"
              :key="row.name"
            >
              <td class="task-col">{{ row.name }}</td>
              <td>{{ row.cpuA }}</td>
              <td>{{ row.cpuB }}</td>
              <td>{{ row.delta }}</td>
            </tr>
            <tr v-if="topTaskRows.length === 0">
              <td
                colspan="4"
                class="compare-empty"
              >
                No user tasks in either trace
              </td>
            </tr>
          </tbody>
        </table>

        <table
          v-else-if="activePage === 'coreUtil'"
          class="compare-table"
        >
          <thead>
            <tr>
              <th>Core</th>
              <th>Util% A</th>
              <th>Util% B</th>
              <th>Δ</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in coreUtilRows"
              :key="row.core"
            >
              <td class="task-col">{{ row.core }}</td>
              <td>{{ row.utilA }}</td>
              <td>{{ row.utilB }}</td>
              <td>{{ row.delta }}</td>
            </tr>
            <tr v-if="coreUtilRows.length === 0">
              <td colspan="4" class="compare-empty">No core utilisation data</td>
            </tr>
          </tbody>
        </table>

        <table
          v-else-if="activePage === 'migrations'"
          class="compare-table"
        >
          <thead>
            <tr>
              <th>Task</th>
              <th>Migr A</th>
              <th>Migr B</th>
              <th>Δ</th>
              <th>Rate A</th>
              <th>Rate B</th>
              <th>Rate Δ</th>
              <th>Dwell A</th>
              <th>Dwell B</th>
              <th>Dwell Δ</th>
              <th>Ping A</th>
              <th>Ping B</th>
              <th>Cores A</th>
              <th>Cores B</th>
              <th>Primary A</th>
              <th>Primary B</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in migrationRows"
              :key="row.mk"
            >
              <td class="task-col">{{ row.name }}</td>
              <td>{{ row.migrationsA }}</td>
              <td>{{ row.migrationsB }}</td>
              <td>{{ row.delta }}</td>
              <td>{{ row.rateA }}</td>
              <td>{{ row.rateB }}</td>
              <td>{{ row.rateDelta }}</td>
              <td>{{ row.dwellA }}</td>
              <td>{{ row.dwellB }}</td>
              <td>{{ row.dwellDelta }}</td>
              <td>{{ row.pingA }}</td>
              <td>{{ row.pingB }}</td>
              <td>{{ row.coresA }}</td>
              <td>{{ row.coresB }}</td>
              <td>{{ row.primaryA }}</td>
              <td>{{ row.primaryB }}</td>
            </tr>
            <tr v-if="migrationRows.length === 0">
              <td
                colspan="16"
                class="compare-empty"
              >
                No migrated tasks in either trace
              </td>
            </tr>
          </tbody>
        </table>

        <table
          v-else-if="activePage === 'execution'"
          class="compare-table"
        >
          <thead>
            <tr>
              <th>Task</th>
              <th>Runs A</th>
              <th>Runs B</th>
              <th>Avg A</th>
              <th>Avg B</th>
              <th>Max A</th>
              <th>Max B</th>
              <th>Δ max</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in executionRows"
              :key="row.name"
            >
              <td class="task-col">{{ row.name }}</td>
              <td>{{ row.runsA }}</td>
              <td>{{ row.runsB }}</td>
              <td>{{ row.avgA }}</td>
              <td>{{ row.avgB }}</td>
              <td>{{ row.maxA }}</td>
              <td>{{ row.maxB }}</td>
              <td>{{ row.deltaMax }}</td>
            </tr>
            <tr v-if="executionRows.length === 0">
              <td colspan="8" class="compare-empty">No execution samples in either trace</td>
            </tr>
          </tbody>
        </table>

        <table
          v-else-if="activePage === 'blocking'"
          class="compare-table"
        >
          <thead>
            <tr>
              <th>Task</th>
              <th>Gaps A</th>
              <th>Gaps B</th>
              <th>Avg A</th>
              <th>Avg B</th>
              <th>Max A</th>
              <th>Max B</th>
              <th>Δ avg</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in blockingRows"
              :key="row.name"
            >
              <td class="task-col">{{ row.name }}</td>
              <td>{{ row.gapsA }}</td>
              <td>{{ row.gapsB }}</td>
              <td>{{ row.avgA }}</td>
              <td>{{ row.avgB }}</td>
              <td>{{ row.maxA }}</td>
              <td>{{ row.maxB }}</td>
              <td>{{ row.delta }}</td>
            </tr>
            <tr v-if="blockingRows.length === 0">
              <td colspan="8" class="compare-empty">No blocking samples in either trace</td>
            </tr>
          </tbody>
        </table>

        <table
          v-else-if="activePage === 'interArrival'"
          class="compare-table"
        >
          <thead>
            <tr>
              <th>Task</th>
              <th>Runs A</th>
              <th>Runs B</th>
              <th>Avg A</th>
              <th>Avg B</th>
              <th>Max A</th>
              <th>Max B</th>
              <th>Δ avg</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in interArrivalRows"
              :key="row.name"
            >
              <td class="task-col">{{ row.name }}</td>
              <td>{{ row.runsA }}</td>
              <td>{{ row.runsB }}</td>
              <td>{{ row.avgA }}</td>
              <td>{{ row.avgB }}</td>
              <td>{{ row.maxA }}</td>
              <td>{{ row.maxB }}</td>
              <td>{{ row.delta }}</td>
            </tr>
            <tr v-if="interArrivalRows.length === 0">
              <td colspan="8" class="compare-empty">No inter-arrival samples in either trace</td>
            </tr>
          </tbody>
        </table>

        <table
          v-else-if="activePage === 'preemption'"
          class="compare-table"
        >
          <thead>
            <tr>
              <th>Victim</th>
              <th>Count A</th>
              <th>Count B</th>
              <th>Δ</th>
              <th>Total A</th>
              <th>Total B</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in preemptionCompareRows"
              :key="row.name"
            >
              <td class="task-col">{{ row.name }}</td>
              <td>{{ row.countA }}</td>
              <td>{{ row.countB }}</td>
              <td>{{ row.delta }}</td>
              <td>{{ row.totalA }}</td>
              <td>{{ row.totalB }}</td>
            </tr>
            <tr v-if="preemptionCompareRows.length === 0">
              <td colspan="6" class="compare-empty">No preemption chains in either trace</td>
            </tr>
          </tbody>
        </table>

        <table
          v-else-if="activePage === 'sync'"
          class="compare-table"
        >
          <thead>
            <tr>
              <th>Metric</th>
              <th>Trace A</th>
              <th>Trace B</th>
              <th>Δ</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in syncCompareRows"
              :key="row.label"
            >
              <td class="task-col">{{ row.label }}</td>
              <td>{{ row.a }}</td>
              <td>{{ row.b }}</td>
              <td>{{ row.delta }}</td>
            </tr>
            <tr v-if="syncCompareRows.length === 0">
              <td colspan="4" class="compare-empty">No sync instrumentation in either trace</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="compare-dialog-footer">
        <button
          type="button"
          class="compare-ai-btn"
          :title="aiEnabled
            ? 'Open the AI Assistant and walk through these Trace Compare tables'
            : 'Enable AI Assistant in Settings → AI'"
          @click="onQueryAi"
        >
          Query with AI…
        </button>
        <div class="compare-footer-right">
        <button
          type="button"
          class="compare-export-btn"
          title="Export compare tables as CSV"
          @click="onExportCsv"
        >
          <svg
            class="export-icon"
            viewBox="0 0 16 16"
            width="14"
            height="14"
            fill="currentColor"
            aria-hidden="true"
          >
            <path d="M2 1h12a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H2a1 1 0 0 1-1-1V2a1 1 0 0 1 1-1zm0 1v12h12V2H2zm2 2h8v1H4V4zm0 2h8v1H4V6zm0 2h5v1H4V8z" />
          </svg>
          Export CSV
        </button>
        <button
          type="button"
          class="compare-export-btn"
          title="Export compare report as HTML"
          @click="onExportHtml"
        >
          <svg
            class="export-icon"
            viewBox="0 0 16 16"
            width="14"
            height="14"
            fill="none"
            stroke="currentColor"
            stroke-width="1.2"
            aria-hidden="true"
          >
            <rect
              x="2.5"
              y="2"
              width="11"
              height="12"
              rx="1"
            />
            <path
              d="M5.5 6.5 3.5 8.5l2 2M10.5 6.5l2 2-2 2"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
          </svg>
          Export HTML
        </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import {
  buildSummaryCompareRows,
  buildTopTasksCompareRows,
  buildCoreUtilCompareRows,
  buildMigrationCompareRows,
  buildExecutionCompareRows,
  buildBlockingCompareRows,
  buildInterArrivalCompareRows,
  buildPreemptionCompareRows,
  buildSyncCompareRows,
  downloadCompareCsv,
  downloadCompareHtml,
} from '../utils/traceCompare.js'

const props = defineProps({
  tabs: { type: Array, required: true },
  initialA: { type: [Number, String], default: null },
  initialB: { type: [Number, String], default: null },
  aiEnabled: { type: Boolean, default: true },
})

const emit = defineEmits(['close', 'query-ai'])

function pickTabId(preferred, fallbackIndex) {
  const list = props.tabs || []
  if (preferred != null && list.some(t => t.id === preferred)) return preferred
  return list[Math.min(fallbackIndex, Math.max(0, list.length - 1))]?.id ?? null
}

const pageTabs = [
  { id: 'summary', label: 'Summary' },
  { id: 'top', label: 'Top Tasks' },
  { id: 'coreUtil', label: 'Core Util' },
  { id: 'migrations', label: 'Core Migrations' },
  { id: 'execution', label: 'Execution' },
  { id: 'blocking', label: 'Blocking' },
  { id: 'interArrival', label: 'Inter-Arrival' },
  { id: 'preemption', label: 'Preemption' },
  { id: 'sync', label: 'Sync' },
]

const activePage = ref('summary')
const scopeToCursors = ref(true)
const tabAId = ref(pickTabId(props.initialA, 0))
const tabBId = ref(pickTabId(props.initialB, 1))

watch(
  () => props.tabs,
  (next) => {
    if (!next.some(t => t.id === tabAId.value)) tabAId.value = next[0]?.id ?? null
    if (!next.some(t => t.id === tabBId.value)) {
      tabBId.value = next[Math.min(1, next.length - 1)]?.id ?? null
    }
  },
  { deep: true },
)

const tabA = computed(() => props.tabs.find(t => t.id === tabAId.value) ?? null)
const tabB = computed(() => props.tabs.find(t => t.id === tabBId.value) ?? null)
const traceA = computed(() => tabA.value?.trace ?? null)
const traceB = computed(() => tabB.value?.trace ?? null)

const summaryRows = computed(() =>
  buildSummaryCompareRows(traceA.value, traceB.value, tabA.value, tabB.value, scopeToCursors.value))
const topTaskRows = computed(() =>
  buildTopTasksCompareRows(traceA.value, traceB.value, tabA.value, tabB.value, scopeToCursors.value))
const coreUtilRows = computed(() =>
  buildCoreUtilCompareRows(traceA.value, traceB.value, tabA.value, tabB.value, scopeToCursors.value))
const migrationRows = computed(() =>
  buildMigrationCompareRows(traceA.value, traceB.value, tabA.value, tabB.value, scopeToCursors.value))
const executionRows = computed(() =>
  buildExecutionCompareRows(traceA.value, traceB.value, tabA.value, tabB.value, scopeToCursors.value))
const blockingRows = computed(() =>
  buildBlockingCompareRows(traceA.value, traceB.value, tabA.value, tabB.value, scopeToCursors.value))
const interArrivalRows = computed(() =>
  buildInterArrivalCompareRows(traceA.value, traceB.value, tabA.value, tabB.value, scopeToCursors.value))
const preemptionCompareRows = computed(() =>
  buildPreemptionCompareRows(traceA.value, traceB.value, tabA.value, tabB.value, scopeToCursors.value))
const syncCompareRows = computed(() =>
  buildSyncCompareRows(traceA.value, traceB.value, tabA.value, tabB.value, scopeToCursors.value))

function exportTables() {
  return {
    summary: summaryRows.value,
    top: topTaskRows.value,
    coreUtil: coreUtilRows.value,
    migrations: migrationRows.value,
    execution: executionRows.value,
    blocking: blockingRows.value,
    interArrival: interArrivalRows.value,
    preemption: preemptionCompareRows.value,
    sync: syncCompareRows.value,
  }
}

function onExportCsv() {
  downloadCompareCsv(
    tabA.value?.name ?? 'Trace A',
    tabB.value?.name ?? 'Trace B',
    scopeToCursors.value,
    exportTables(),
  )
}

function onExportHtml() {
  downloadCompareHtml(
    tabA.value?.name ?? 'Trace A',
    tabB.value?.name ?? 'Trace B',
    scopeToCursors.value,
    exportTables(),
  )
}

function onQueryAi() {
  emit('query-ai', { idA: tabAId.value, idB: tabBId.value })
}
</script>

<style scoped>
.compare-dialog-overlay {
  position: fixed;
  inset: 0;
  z-index: 500;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(2px);
}

.compare-dialog {
  width: min(1080px, 98vw);
  height: min(88vh, 640px);
  background: var(--panel-bg);
  border: 1px solid var(--border);
  border-radius: 10px;
  box-shadow: 0 12px 36px rgba(0, 0, 0, 0.45);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.compare-dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.compare-dialog-title {
  font-size: 13px;
  font-weight: 700;
}

.compare-close-btn {
  appearance: none;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: transparent;
  color: var(--fg-dim);
  font-size: 11px;
  padding: 4px 10px;
  cursor: pointer;
}

.compare-close-btn:hover {
  background: var(--tb-btn-hover);
  color: var(--fg);
}

.compare-scope {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px 0;
  font-size: 12px;
  color: var(--fg-dim);
  cursor: pointer;
  flex-shrink: 0;
}

.compare-select-row {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.compare-select-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
  color: var(--fg-dim);
  flex: 1;
  min-width: 200px;
}

.compare-select {
  flex: 1;
  min-width: 0;
  padding: 4px 6px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--bg);
  color: var(--fg);
  font-size: 11px;
}

.compare-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 2px;
  padding: 8px 14px 0;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.compare-tab {
  appearance: none;
  border: none;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--fg-dim);
  font-size: 11px;
  font-weight: 600;
  padding: 6px 12px;
  cursor: pointer;
  margin-bottom: -1px;
}

.compare-tab:hover {
  color: var(--fg);
  background: var(--tb-btn-hover);
}

.compare-tab.active {
  color: var(--accent);
  border-bottom-color: var(--accent);
}

.compare-table-wrap {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
  padding: 0 14px 14px;
}

.compare-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 11px;
  margin-top: 10px;
}

.compare-table th,
.compare-table td {
  padding: 4px 6px;
  border-bottom: 1px solid var(--border);
  text-align: right;
  white-space: nowrap;
}

.compare-table th:first-child,
.compare-table td.task-col {
  text-align: left;
}

.compare-table th {
  position: sticky;
  top: 0;
  background: var(--panel-bg);
  color: var(--fg-dim);
  font-weight: 600;
  z-index: 1;
}

.compare-empty {
  text-align: center !important;
  color: var(--fg-dim);
  padding: 16px 6px !important;
}

.compare-dialog-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-top: 1px solid var(--border);
  flex-shrink: 0;
}

.compare-footer-right {
  display: flex;
  gap: 8px;
}

.compare-ai-btn {
  appearance: none;
  border: 1px solid var(--accent, #4a90d9);
  border-radius: 4px;
  background: var(--accent, #4a90d9);
  color: #000;
  font-size: 11px;
  font-weight: 600;
  padding: 5px 10px;
  cursor: pointer;
}

.compare-ai-btn:hover {
  filter: brightness(1.08);
}

.compare-export-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  appearance: none;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: transparent;
  color: var(--fg-dim);
  font-size: 11px;
  padding: 5px 10px;
  cursor: pointer;
}

.compare-export-btn:hover {
  background: var(--tb-btn-hover);
  color: var(--fg);
}

.export-icon {
  flex-shrink: 0;
  opacity: 0.9;
}
</style>
