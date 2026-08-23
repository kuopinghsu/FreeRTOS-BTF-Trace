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
        <label class="compare-select-label compare-label-baseline">
          Trace A (Baseline):
          <DomSelect
            v-model="tabAId"
            class="compare-select"
            :options="compareTabOptions"
          />
        </label>
        <label class="compare-select-label compare-label-candidate">
          Trace B (Candidate):
          <DomSelect
            v-model="tabBId"
            class="compare-select"
            :options="compareTabOptions"
          />
        </label>
      </div>

      <label class="compare-scope">
        <input
          v-model="scopeToCursors"
          type="checkbox"
        />
        Limit to each tab's cursor range (C1–Cn, when 2+ cursors placed)
      </label>

      <div class="compare-formula">{{ compareFormula }}</div>

      <div
        v-if="compareDecision.visible"
        class="compare-decision"
      >
        <div class="compare-decision-identity">{{ compareDecision.identity }}</div>
        <div class="compare-decision-counts">{{ compareDecision.counts }}</div>
        <div
          class="compare-decision-largest"
          :class="{ clickable: compareDecision.largestClickable }"
          :title="compareDecision.largestClickable
            ? 'Open Statistics for this regression on the Candidate tab'
            : undefined"
          @click="compareDecision.largestClickable && investigateSide('b')"
        >
          {{ compareDecision.largest }}
        </div>
        <div
          v-if="compareDecision.why"
          class="compare-decision-why"
        >
          Why? {{ compareDecision.why }}
        </div>
        <div
          v-if="compareDecision.next"
          class="compare-decision-next"
        >
          {{ compareDecision.next }}
        </div>
        <div
          v-if="compareDecision.sigNote"
          class="compare-decision-sig"
        >
          {{ compareDecision.sigNote }}
        </div>
        <div class="compare-decision-actions">
          <button
            type="button"
            class="compare-inspect-btn"
            title="Open Statistics for the largest regression on this tab (preserves Scope/Filters)"
            @click="investigateSide('a')"
          >
            Investigate on Baseline
          </button>
          <button
            type="button"
            class="compare-inspect-btn"
            title="Open Statistics for the largest regression on this tab (preserves Scope/Filters)"
            @click="investigateSide('b')"
          >
            Investigate on Candidate
          </button>
        </div>
      </div>

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
        <div
          v-if="activePage === 'summary'"
          class="compare-page"
        >
          <div
            v-if="summaryChartModel.length"
            class="compare-chart"
          >
            <div class="compare-chart-head">
              <span class="compare-chart-title">Summary changes</span>
              <span class="compare-chart-legend">Candidate B − Baseline A</span>
            </div>
            <div class="p99-axis">
              <span class="p99-improved">Improved</span>
              <span class="p99-regressed">Regressed</span>
            </div>
            <div
              v-for="row in summaryChartModel"
              :key="row.label"
              class="p99-chart-row"
            >
              <span class="chart-label">{{ row.label }}</span>
              <div class="p99-track">
                <div class="p99-mid" />
                <div
                  class="p99-bar"
                  :class="row.side"
                  :style="row.barStyle"
                />
              </div>
              <span
                class="p99-change"
                :class="row.side"
              >{{ row.change }}</span>
            </div>
          </div>
          <table class="compare-table">
            <thead>
              <tr>
                <th>Metric</th>
                <th>Baseline A</th>
                <th>Candidate B</th>
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
                <td :class="deltaClass(row.label, row.delta)">{{ row.delta }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <table
          v-else-if="activePage === 'top'"
          class="compare-table"
        >
          <thead>
            <tr>
              <th>Task</th>
              <th>CPU A (%)</th>
              <th>CPU B (%)</th>
              <th>Δ (pp)</th>
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
              <td :class="deltaClass(row.name, row.delta, 'cpu')">{{ row.delta }}</td>
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

        <div
          v-else-if="activePage === 'coreUtil'"
          class="compare-page"
        >
          <div
            v-if="coreUtilChartModel.length"
            class="compare-chart"
          >
            <div class="compare-chart-head">
              <span class="compare-chart-title">Core utilisation</span>
              <span class="compare-chart-legend">
                <span class="swatch swatch-a"></span>Baseline A
                <span class="swatch swatch-b"></span>Candidate B
              </span>
            </div>
            <div
              v-for="row in coreUtilChartModel"
              :key="row.label"
              class="util-chart-row"
            >
              <span class="chart-label">{{ row.label }}</span>
              <div class="util-chart-bars">
                <div class="util-track">
                  <div
                    class="util-fill util-fill-a"
                    :style="{ width: row.aPct + '%' }"
                  />
                </div>
                <div class="util-track">
                  <div
                    class="util-fill util-fill-b"
                    :style="{ width: row.bPct + '%' }"
                  />
                </div>
              </div>
              <span class="chart-pct">
                <span class="pct-a">{{ row.a.toFixed(1) }}%</span>
                <span class="pct-b">{{ row.b.toFixed(1) }}%</span>
              </span>
            </div>
          </div>
          <table class="compare-table">
            <thead>
              <tr>
                <th>Core</th>
                <th>Util A (%)</th>
                <th>Util B (%)</th>
                <th>Δ (pp)</th>
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
                <td :class="deltaClass(row.core, row.delta, 'util')">{{ row.delta }}</td>
              </tr>
              <tr v-if="coreUtilRows.length === 0">
                <td colspan="4" class="compare-empty">No core utilisation data</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div
          v-else-if="activePage === 'migrations'"
          class="compare-page"
        >
          <div class="compare-mig-controls">
            <select v-model="migView" class="compare-mig-select">
              <option value="count">Count &amp; rate</option>
              <option value="dwell">Dwell &amp; ping</option>
              <option value="cores">Cores</option>
            </select>
            <select v-model="migFilter" class="compare-mig-select">
              <option value="top">Top 10 changes</option>
              <option value="changed">Changed only</option>
              <option value="regressed">Regressions only</option>
              <option value="all">Show all</option>
            </select>
            <select v-model="migSort" class="compare-mig-select">
              <option value="abs">Sort |Δ|</option>
              <option value="rel">Sort relative</option>
            </select>
            <select v-model="migFamily" class="compare-mig-select">
              <option value="">All families</option>
              <option
                v-for="fam in migFamilies"
                :key="fam"
                :value="fam"
              >
                {{ fam }}
              </option>
            </select>
            <span class="compare-mig-hint">{{ migHint }}</span>
          </div>
          <div
            v-if="migHeatmapModel.length"
            class="compare-chart"
          >
            <div class="compare-chart-head">
              <span class="compare-chart-title">Migration Δ</span>
              <span class="compare-chart-legend">Δ = A − B</span>
            </div>
            <div class="p99-axis">
              <span class="p99-improved">Improved</span>
              <span class="p99-regressed">Regressed</span>
            </div>
            <div
              v-for="row in migHeatmapModel"
              :key="row.label"
              class="p99-chart-row"
            >
              <span class="chart-label">{{ row.label }}</span>
              <div class="p99-track">
                <div class="p99-mid" />
                <div
                  class="p99-bar"
                  :class="row.side"
                  :style="row.barStyle"
                />
              </div>
              <span
                class="p99-change"
                :class="row.side"
              >{{ row.change }}</span>
            </div>
          </div>
          <table class="compare-table">
            <thead>
              <tr>
                <th
                  v-for="h in migHeaders"
                  :key="h"
                >
                  {{ h }}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(row, ri) in migViewRows"
                :key="ri"
              >
                <td
                  v-for="(cell, ci) in row"
                  :key="ci"
                  :class="migCellClass(ci, row)"
                >
                  {{ cell }}
                </td>
              </tr>
              <tr v-if="migViewRows.length === 0">
                <td
                  :colspan="Math.max(migHeaders.length, 1)"
                  class="compare-empty"
                >
                  No migrated tasks in either trace
                </td>
              </tr>
            </tbody>
          </table>
        </div>

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
              <td :class="deltaClass(row.name, row.deltaMax, 'exec max')">{{ row.deltaMax }}</td>
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
              <td :class="deltaClass(row.name, row.delta, 'block')">{{ row.delta }}</td>
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
              <td :class="deltaClass(row.name, row.delta, 'inter')">{{ row.delta }}</td>
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
              <td :class="deltaClass(row.name, row.delta, 'preempt')">{{ row.delta }}</td>
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
              <th>Baseline A</th>
              <th>Candidate B</th>
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
              <td :class="deltaClass(row.label, row.delta)">{{ row.delta }}</td>
            </tr>
            <tr v-if="syncCompareRows.length === 0">
              <td colspan="4" class="compare-empty">No sync instrumentation in either trace</td>
            </tr>
          </tbody>
        </table>

        <div
          v-else-if="activePage === 'response'"
          class="compare-page"
        >
          <div
            v-if="p99ChartModel.length"
            class="compare-chart"
          >
            <div class="compare-chart-head">
              <span class="compare-chart-title">Response P99 change</span>
              <span class="compare-chart-legend">Candidate B − Baseline A</span>
            </div>
            <div class="p99-axis">
              <span class="p99-improved">Improved</span>
              <span class="p99-regressed">Regressed</span>
            </div>
            <div
              v-for="row in p99ChartModel"
              :key="row.label"
              class="p99-chart-row"
            >
              <span class="chart-label">{{ row.label }}</span>
              <div class="p99-track">
                <div class="p99-mid" />
                <div
                  class="p99-bar"
                  :class="row.side"
                  :style="row.barStyle"
                />
              </div>
              <span
                class="p99-change"
                :class="row.side"
              >{{ row.change }}</span>
            </div>
          </div>
          <table class="compare-table">
            <thead>
              <tr>
                <th>Task</th>
                <th>P99 A</th>
                <th>P99 B</th>
                <th>Δ</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in responseCompareRows"
                :key="row.name"
              >
                <td class="task-col">{{ row.name }}</td>
                <td>{{ row.a }}</td>
                <td>{{ row.b }}</td>
                <td :class="deltaClass(row.name, row.delta, 'response')">{{ row.delta }}</td>
              </tr>
              <tr v-if="responseCompareRows.length === 0">
                <td colspan="4" class="compare-empty">No response samples in either trace</td>
              </tr>
            </tbody>
          </table>
        </div>

        <table
          v-else-if="activePage === 'mutex'"
          class="compare-table"
        >
          <thead>
            <tr>
              <th>Task</th>
              <th>Total A</th>
              <th>Total B</th>
              <th>Δ</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in mutexBlockCompareRows"
              :key="row.name"
            >
              <td class="task-col">{{ row.name }}</td>
              <td>{{ row.a }}</td>
              <td>{{ row.b }}</td>
              <td :class="deltaClass(row.name, row.delta, 'mutex')">{{ row.delta }}</td>
            </tr>
            <tr v-if="mutexBlockCompareRows.length === 0">
              <td colspan="4" class="compare-empty">No mutex blocking in either trace</td>
            </tr>
          </tbody>
        </table>

        <table
          v-else-if="activePage === 'trends'"
          class="compare-table"
        >
          <thead>
            <tr>
              <th>Trace</th>
              <th>Tasks</th>
              <th>Migrations</th>
              <th>Load balance</th>
              <th>Tick health</th>
              <th>Span</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in trendRows"
              :key="row.name"
            >
              <td class="task-col">{{ row.name }}</td>
              <td>{{ row.tasks ?? '—' }}</td>
              <td>{{ row.migrations ?? '—' }}</td>
              <td>{{ row.loadBalance == null ? '—' : `${Math.round(row.loadBalance)}%` }}</td>
              <td>{{ row.tickHealth || '—' }}</td>
              <td>{{ row.spanNs ?? '—' }}</td>
            </tr>
            <tr v-if="trendRows.length === 0">
              <td colspan="6" class="compare-empty">Open 2+ traces to trend summaries</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="compare-dialog-footer">
        <div class="compare-footer-left">
        <button
          type="button"
          class="compare-export-btn"
          :title="aiEnabled
            ? 'Score expected vs actual deltas from this Trace Compare'
            : 'Enable AI Assistant in Settings → AI'"
          @click="onValidateExperiment"
        >
          Validate experiment…
        </button>
        <button
          type="button"
          class="compare-export-btn"
          :title="aiEnabled
            ? 'Open the AI Assistant and walk through these Trace Compare tables'
            : 'Enable AI Assistant in Settings → AI'"
          @click="onQueryAi"
        >
          Query with AI…
        </button>
        <button
          type="button"
          class="compare-export-btn"
          title="Store Trace A per-task metrics as the regression baseline"
          @click="onSaveBaseline"
        >
          Save as baseline
        </button>
        <button
          type="button"
          class="compare-export-btn"
          title="Z-score Trace A metrics against the stored baseline"
          @click="onScoreBaseline"
        >
          Score vs baseline
        </button>
        </div>
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
import DomSelect from './DomSelect.vue'
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
  buildResponseCompareRows,
  buildMutexBlockCompareRows,
  buildSharedPatternCompareRows,
  buildAllCompareTables,
  downloadCompareCsv,
  downloadCompareHtml,
  crossTraceTrends,
  traceSummarySnapshot,
  cursorRangeForCursors,
} from '../utils/traceCompare.js'
import {
  compareSummaryStrip,
  compareInvestigateTarget,
  COMPARE_DELTA_FORMULA,
  compareCoreUtilChartRows,
  compareP99DeltaChartRows,
  compareSummaryChangeBarRows,
  compareMigrationHeatmapRows,
  compareRowDeltaStatus,
  filterCompareMigrationRows,
} from '../utils/uxExplore.js'

const props = defineProps({
  tabs: { type: Array, required: true },
  initialA: { type: [Number, String], default: null },
  initialB: { type: [Number, String], default: null },
  aiEnabled: { type: Boolean, default: true },
  analysisSettings: { type: Object, default: () => ({}) },
})

const emit = defineEmits([
  'close', 'query-ai', 'validate-experiment', 'compared', 'investigate',
  'save-baseline', 'score-baseline',
])

const compareTabOptions = computed(() =>
  (props.tabs || []).map(tab => ({ value: tab.id, label: tab.name })))

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
  { id: 'response', label: 'Response' },
  { id: 'mutex', label: 'Mutex' },
  { id: 'trends', label: 'Trends' },
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
const deadlines = computed(() => props.analysisSettings?.taskDeadlines || {})

watch(
  [tabAId, tabBId, scopeToCursors, traceA, traceB],
  () => {
    if (tabAId.value == null || tabBId.value == null || tabAId.value === tabBId.value) return
    if (!traceA.value || !traceB.value) return
    emit('compared', {
      idA: tabAId.value,
      idB: tabBId.value,
      scopeToCursors: !!scopeToCursors.value,
    })
  },
  { immediate: true },
)

const summaryRows = computed(() =>
  buildSummaryCompareRows(traceA.value, traceB.value, tabA.value, tabB.value, scopeToCursors.value, deadlines.value))
const topTaskRows = computed(() =>
  buildTopTasksCompareRows(traceA.value, traceB.value, tabA.value, tabB.value, scopeToCursors.value))
const coreUtilRows = computed(() =>
  buildCoreUtilCompareRows(traceA.value, traceB.value, tabA.value, tabB.value, scopeToCursors.value))
const migrationRows = computed(() =>
  buildMigrationCompareRows(traceA.value, traceB.value, tabA.value, tabB.value, scopeToCursors.value))
const migView = ref('count')
const migFilter = ref('top')
const migSort = ref('abs')
const migFamily = ref('')
const migFiltered = computed(() =>
  filterCompareMigrationRows(
    migrationRows.value, migView.value, migFilter.value, migFamily.value, 10, migSort.value))
const migHeaders = computed(() => migFiltered.value.headers || [])
const migViewRows = computed(() => migFiltered.value.rows || [])
const migFamilies = computed(() => migFiltered.value.families || [])
const migHint = computed(() => `${migFiltered.value.shown || 0} of ${migFiltered.value.total || 0} tasks`)
watch(migFamilies, (fams) => {
  if (migFamily.value && !fams.includes(migFamily.value)) migFamily.value = ''
})
const coreUtilChartModel = computed(() => {
  const rows = compareCoreUtilChartRows({ coreUtil: coreUtilRows.value })
  const maxV = Math.max(1, ...rows.map(r => Math.max(Number(r.a) || 0, Number(r.b) || 0)))
  return rows.map(r => ({
    ...r,
    aPct: Math.max(1, (Number(r.a) || 0) / maxV * 100),
    bPct: Math.max(1, (Number(r.b) || 0) / maxV * 100),
  }))
})
function divergingBarModel(rows, valueKey = 'cand') {
  const maxV = Math.max(1, ...rows.map(r => Math.abs(Number(r[valueKey]) || 0)))
  return rows.map((r) => {
    const cand = Number(r[valueKey]) || 0
    const pct = Math.abs(cand) / maxV * 50
    const improved = cand < 0
    return {
      ...r,
      side: improved ? 'improved' : 'regressed',
      barStyle: improved
        ? { width: `${pct}%`, right: '50%' }
        : { width: `${pct}%`, left: '50%' },
    }
  })
}
const summaryChartModel = computed(() =>
  divergingBarModel(compareSummaryChangeBarRows({ summary: summaryRows.value }, 8)))
const migHeatmapModel = computed(() => {
  const rows = compareMigrationHeatmapRows(migrationRows.value, 12).map((r) => {
    const d = Number(r.delta) || 0
    const change = d === 0 ? '0' : `${d > 0 ? '+' : '−'}${Math.abs(Math.trunc(d))}`
    return { ...r, cand: -d, change }
  })
  return divergingBarModel(rows)
})
function deltaClass(label, delta, metric = '') {
  const status = compareRowDeltaStatus(label, delta, metric)
  if (status === 'Improved') return 'delta-improved'
  if (status === 'Regressed') return 'delta-regressed'
  return ''
}
function migCellClass(ci, row) {
  const classes = []
  if (ci === 0) classes.push('task-col')
  const deltaCol = migView.value === 'cores' ? -1 : 3
  if (ci === deltaCol) {
    const statusCls = deltaClass(row[0], row[ci], 'migrations')
    if (statusCls) classes.push(statusCls)
  }
  return classes
}
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
const responseCompareRows = computed(() =>
  buildResponseCompareRows(traceA.value, traceB.value, tabA.value, tabB.value, scopeToCursors.value, deadlines.value))
const p99ChartModel = computed(() =>
  divergingBarModel(compareP99DeltaChartRows({ response: responseCompareRows.value }, 12)))
const mutexBlockCompareRows = computed(() =>
  buildMutexBlockCompareRows(traceA.value, traceB.value, tabA.value, tabB.value, scopeToCursors.value, deadlines.value))
const trendRows = computed(() => {
  const rows = []
  for (const tab of props.tabs || []) {
    if (!tab?.trace) continue
    const range = scopeToCursors.value ? cursorRangeForCursors(tab.cursors) : { lo: null, hi: null }
    rows.push({
      name: tab.name,
      snap: traceSummarySnapshot(tab.trace, range.lo, range.hi),
    })
  }
  return crossTraceTrends(rows)
})
const sharedPatternRows = computed(() =>
  buildSharedPatternCompareRows(traceA.value, traceB.value, tabA.value, tabB.value, scopeToCursors.value, deadlines.value))

const compareFormula = COMPARE_DELTA_FORMULA

const compareDecision = computed(() => {
  const data = compareSummaryStrip({
    summary: summaryRows.value,
    execution: executionRows.value,
    blocking: blockingRows.value,
    interArrival: interArrivalRows.value,
    response: responseCompareRows.value,
    mutex_block: mutexBlockCompareRows.value,
    shared_patterns: sharedPatternRows.value,
  }, 4, tabA.value?.name ?? '', tabB.value?.name ?? '')
  const notable = data.notable || {}
  const identity = notable.identity || {}
  const idA = identity.a || {}
  const idB = identity.b || {}
  const nameA = tabA.value?.name || 'Baseline'
  const nameB = tabB.value?.name || 'Candidate'
  const cards = notable.cards || {}
  const regs = data.regressions || []
  const nReg = Number(cards.regressions ?? regs.length) || 0
  const nImp = Number(cards.improvements ?? (data.improvements || []).length) || 0
  const nWarn = Number(cards.warnings ?? (data.warnings || []).length) || 0
  const top = regs[0]
  const largest = top
    ? `Largest regression — ${top.label}: ${top.change}`
    : (String(notable.verdict || '').trim() || 'No significant regressions')
  const why = String(data.why || '').trim()
  const next = String(notable.next_investigation || '').trim()
  const omitted = Number(notable.small_omitted_count || 0) || 0
  const sigNote = (Number(cards.significant || 0) || omitted)
    ? 'Showing engineering-significant deltas only (small changes omitted)'
    : ''
  const visible = !!(nReg || nImp || nWarn || top || why || next || notable.verdict)
  const investigate = notable.investigate || compareInvestigateTarget(notable)
  return {
    visible,
    identity:
      `Baseline: ${nameA} · Scope ${idA.span || 'Full Trace'}    |    ` +
      `Candidate: ${nameB} · Scope ${idB.span || 'Full Trace'}`,
    counts:
      `${nReg} REGRESSIONS    ${nImp} IMPROVEMENTS` +
      (nWarn ? `    ${nWarn} WARNING${nWarn === 1 ? '' : 'S'}` : ''),
    largest,
    largestClickable: !!top,
    why,
    next,
    sigNote,
    investigate,
  }
})

function investigateSide(side) {
  const id = side === 'a' ? tabAId.value : tabBId.value
  const tab = side === 'a' ? tabA.value : tabB.value
  const target = compareDecision.value.investigate || compareInvestigateTarget()
  emit('close')
  if (id == null) return
  emit('compared', { idA: tabAId.value, idB: tabBId.value })
  emit('investigate', {
    activateId: id,
    sectionId: target.section_id || target.section || 'response',
    task: target.task || '',
    sectionLabel: target.section_label || '',
    tabName: tab?.name || '',
  })
}

function exportTables() {
  const tables = buildAllCompareTables(
    traceA.value, traceB.value, tabA.value, tabB.value,
    scopeToCursors.value, deadlines.value, 0,
  )
  tables.trends = trendRows.value
  return tables
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

function onValidateExperiment() {
  emit('validate-experiment', { idA: tabAId.value, idB: tabBId.value })
}

function onSaveBaseline() {
  emit('save-baseline', tabAId.value)
}

function onScoreBaseline() {
  emit('score-baseline', tabAId.value)
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

.compare-select-label.compare-label-baseline {
  color: #2a6fb2;
}

.compare-select-label.compare-label-candidate {
  color: #6b4ea8;
}

.compare-formula {
  padding: 4px 14px 0;
  font-size: 11px;
  color: var(--fg-dim);
  flex-shrink: 0;
}

.compare-page {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.compare-chart {
  margin: 8px 0 4px;
  padding: 6px 0 2px;
}

.compare-chart-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 6px;
  font-size: 11px;
}

.compare-chart-title {
  font-weight: 600;
  color: var(--fg);
}

.compare-chart-legend {
  color: var(--fg-dim);
  display: flex;
  align-items: center;
  gap: 6px;
}

.swatch {
  display: inline-block;
  width: 10px;
  height: 8px;
  border-radius: 2px;
}

.swatch-a { background: #2a6fb2; }
.swatch-b { background: #6b4ea8; }

.util-chart-row,
.p99-chart-row {
  display: grid;
  grid-template-columns: 78px 1fr 52px;
  gap: 8px;
  align-items: center;
  margin: 2px 0;
}

.p99-chart-row {
  grid-template-columns: 96px 1fr 88px;
}

.chart-label {
  font-size: 11px;
  color: var(--fg);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.util-chart-bars {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.util-track {
  height: 9px;
  border-radius: 3px;
  background: color-mix(in srgb, var(--fg) 12%, transparent);
  overflow: hidden;
}

.util-fill {
  height: 100%;
  border-radius: 3px;
  min-width: 2px;
}

.util-fill-a { background: #2a6fb2; }
.util-fill-b { background: #6b4ea8; }

.chart-pct {
  display: flex;
  flex-direction: column;
  font-size: 10px;
  line-height: 1.2;
}

.pct-a { color: #2a6fb2; }
.pct-b { color: #6b4ea8; }

.p99-axis {
  display: flex;
  justify-content: space-between;
  font-size: 10px;
  margin: 0 96px 2px 96px;
}

.p99-improved { color: #3cb371; }
.p99-regressed { color: #e07070; }

.p99-track {
  position: relative;
  height: 18px;
  background: color-mix(in srgb, var(--fg) 8%, transparent);
  border-radius: 3px;
}

.p99-mid {
  position: absolute;
  left: 50%;
  top: 0;
  bottom: 0;
  width: 1px;
  background: var(--border);
}

.p99-bar {
  position: absolute;
  top: 3px;
  height: 12px;
  border-radius: 2px;
  min-width: 2px;
}

.p99-bar.improved { background: #3cb371; }
.p99-bar.regressed { background: #e07070; }

.p99-change {
  font-size: 10px;
}

.p99-change.improved { color: #3cb371; }
.p99-change.regressed { color: #e07070; }

.compare-mig-controls {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin: 8px 0 4px;
}

.compare-mig-select {
  padding: 4px 6px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--bg);
  color: var(--fg);
  font-size: 11px;
}

.compare-mig-hint {
  font-size: 11px;
  color: var(--fg-dim);
}

.compare-decision {
  margin: 0 0 8px;
  padding: 8px 10px;
  border-radius: 6px;
  background: rgba(52, 152, 219, 0.10);
  color: var(--fg-dim, #9a9a9a);
  font-size: 12px;
  line-height: 1.45;
}
.compare-decision-identity {
  color: var(--fg-dim, #9a9a9a);
  font-size: 11px;
}
.compare-decision-counts {
  margin-top: 4px;
  color: var(--fg, #cfd8dc);
  font-weight: 600;
}
.compare-decision-largest {
  margin-top: 4px;
  color: var(--fg, #e0e0e0);
}
.compare-decision-largest.clickable {
  cursor: pointer;
  text-decoration: underline;
  text-decoration-color: color-mix(in srgb, var(--fg, #e0e0e0) 35%, transparent);
}
.compare-decision-largest.clickable:hover {
  color: var(--accent, #0e639c);
}
.compare-decision-why {
  margin-top: 2px;
  color: var(--fg-dim, #9a9a9a);
  font-size: 11px;
}
.compare-decision-next {
  margin-top: 2px;
  color: var(--fg-dim, #b0bec5);
  font-size: 11px;
}
.compare-decision-sig {
  margin-top: 2px;
  color: var(--fg-dim, #7a8690);
  font-size: 10px;
}
.compare-decision-actions {
  display: flex;
  gap: 8px;
  margin-top: 6px;
}
.compare-inspect-btn {
  cursor: pointer;
  border: 1px solid var(--border, #444);
  background: var(--bg-elevated, #2a2a2a);
  color: var(--fg, #eee);
  border-radius: 4px;
  padding: 3px 8px;
  font-size: 11px;
}
.compare-inspect-btn:hover {
  border-color: #5dade2;
}
.compare-strip {
  margin: 8px 14px 0;
  padding: 8px 10px;
  border-radius: 6px;
  background: color-mix(in srgb, var(--accent, #3498db) 12%, transparent);
  color: var(--fg-dim);
  font-size: 12px;
  line-height: 1.45;
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

.delta-improved {
  color: #3cb371;
}

.delta-regressed {
  color: #e07070;
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

.compare-footer-left,
.compare-footer-right {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
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
