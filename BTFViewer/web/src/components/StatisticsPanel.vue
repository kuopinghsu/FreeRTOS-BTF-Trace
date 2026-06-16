<template>
  <div class="stats-panel">
    <!-- Cursor range scope -->
    <div class="stats-scope-row">
      <div class="stats-scope-top">
        <label
          class="stats-scope-check"
          :title="'When two or more cursors are placed, restrict all statistics to the time window from C1 through the last cursor.'"
        >
          <input
            v-model="scopeToCursors"
            type="checkbox"
            :disabled="placedCursorCount < 2"
          >
          Limit to cursor range (C1–Cn)
        </label>
        <div class="stats-scope-actions">
          <button
            type="button"
            class="stats-icon-btn"
            title="Expand all statistics sections"
            aria-label="Expand all statistics sections"
            @click="expandAllSections"
          >
            <svg viewBox="0 0 16 16" width="14" height="14" fill="currentColor" aria-hidden="true">
              <path d="M8 2v5H3v1h5v5h1V8h5V7H9V2H8z" />
            </svg>
          </button>
          <button
            type="button"
            class="stats-icon-btn"
            title="Collapse all statistics sections"
            aria-label="Collapse all statistics sections"
            @click="collapseAllSections"
          >
            <svg viewBox="0 0 16 16" width="14" height="14" fill="currentColor" aria-hidden="true">
              <path d="M2 7h12v2H2z" />
            </svg>
          </button>
        </div>
      </div>
      <span class="stats-scope-label">{{ scopeRangeLabel }}</span>
    </div>

    <!-- Summary and sections (require loaded trace) -->
    <template v-if="trace">
    <div class="stats-summary">
      <div class="summary-row">
        <span class="summary-key">Span{{ scopeSuffixStr }}</span>
        <span class="summary-val">{{ spanStr }}</span>
      </div>
      <div class="summary-row">
        <span class="summary-key">Tasks</span>
        <span class="summary-val">{{ summaryTaskCount.toLocaleString() }}</span>
      </div>
      <div class="summary-row">
        <span class="summary-key">Segments</span>
        <span class="summary-val">{{ summarySegCount.toLocaleString() }}</span>
      </div>
      <div class="summary-row">
        <span class="summary-key">STI Events</span>
        <span class="summary-val">{{ summaryStiCount.toLocaleString() }}</span>
      </div>
      <template v-if="schedulingSummary">
        <div class="summary-row">
          <span class="summary-key">Context switches{{ scopeSuffixStr }}</span>
          <span class="summary-val">{{ schedulingSummary.contextSwitches.toLocaleString() }}</span>
        </div>
        <div class="summary-row">
          <span class="summary-key">Core gap avg{{ scopeSuffixStr }}</span>
          <span class="summary-val">{{ schedulingSummary.gapAvg }}</span>
        </div>
        <div class="summary-row">
          <span class="summary-key">Core gap max{{ scopeSuffixStr }}</span>
          <span class="summary-val">{{ schedulingSummary.gapMax }}</span>
        </div>
      </template>
    </div>

    <!-- Core utilization -->
    <template v-if="trace?.coreNames?.length > 0">
      <div class="stats-sep" />
      <div
        class="stats-section-title collapsible"
        @click="coresCollapsed = !coresCollapsed"
      >
        <svg
          class="chevron"
          :class="{ collapsed: coresCollapsed }"
          viewBox="0 0 10 10"
          width="10"
          height="10"
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
        Core Utilisation (excl. IDLE/TICK){{ scopeSuffixStr }}
      </div>
      <template v-if="!coresCollapsed">
        <div
          class="stats-util-scroll"
          :style="utilScrollStyle(coreStats.length)"
        >
          <div
            v-for="cs in coreStats"
            :key="cs.core"
            class="core-stat-row"
          >
            <span class="core-name">{{ cs.core }}</span>
            <div class="prog-bar">
              <div
                class="prog-fill"
                :style="{ width: clampPct(cs.pct) + '%' }"
              />
            </div>
            <span class="core-pct">{{ cs.pct.toFixed(1) }}%</span>
          </div>
        </div>
      </template>
    </template>

    <!-- Top tasks -->
    <div class="stats-sep" />
    <div
      class="stats-section-title collapsible"
      @click="tasksCollapsed = !tasksCollapsed"
    >
      <svg
        class="chevron"
        :class="{ collapsed: tasksCollapsed }"
        viewBox="0 0 10 10"
        width="10"
        height="10"
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
      Top Tasks by CPU (excl. IDLE/TICK){{ scopeSuffixStr }}
    </div>
    <template v-if="!tasksCollapsed">
      <div
        v-if="topTasks.length === 0"
        class="range-hint"
      >
        No user tasks found
      </div>
      <div
        v-else
        class="stats-util-scroll"
        :style="utilScrollStyle(topTasks.length)"
      >
        <div
          v-for="t in topTasks"
          :key="t.mk"
          class="task-stat-row"
        >
          <button
            class="task-stat-name task-link"
            type="button"
            :title="`Highlight ${t.name} in the timeline`"
            @click="emit('highlightTask', t.mk)"
          >
            {{ t.name }}
          </button>
          <div class="prog-bar">
            <div
              class="prog-fill task-fill"
              :style="{ width: clampPct(t.pct) + '%' }"
            />
          </div>
          <span class="task-stat-pct">{{ t.pct.toFixed(1) }}%</span>
        </div>
      </div>
    </template>

    <!-- Trace health (TICK) -->
    <div class="stats-sep" />
    <div
      class="stats-section-title collapsible"
      @click="healthCollapsed = !healthCollapsed"
    >
      <svg
        class="chevron"
        :class="{ collapsed: healthCollapsed }"
        viewBox="0 0 10 10"
        width="10"
        height="10"
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
      Trace Health (TICK){{ scopeSuffixStr }}
    </div>
    <template v-if="!healthCollapsed">
      <div
        v-if="!tickHealth.tickCount"
        class="range-hint"
      >
        No STI TICK events
      </div>
      <template v-else>
        <div
          class="health-banner"
          :class="'health-' + tickHealth.health"
        >
          {{ tickHealth.health.toUpperCase() }}
          · {{ tickHealth.tickCount.toLocaleString() }} ticks
          · avg {{ fmtTime(tickHealth.avgPeriod) }}
          · max gap {{ fmtTime(tickHealth.maxGap) }}
        </div>
        <div
          v-if="tickHealth.largeGaps.length"
          class="range-hint"
        >
          {{ tickHealth.largeGaps.length }} large gap(s)
          · ~{{ tickHealth.missedTicksEstimate }} missed ticks
        </div>
        <div
          v-if="tickHealth.largeGaps.length"
          class="stats-table-wrap"
          style="max-height: 140px"
        >
          <table class="stats-table compact">
            <thead>
              <tr>
                <th
                  :class="thSortClass('health', 'start')"
                  @click="toggleTableSort('health', 'start')"
                >
                  Start
                </th>
                <th
                  :class="thSortClass('health', 'end')"
                  @click="toggleTableSort('health', 'end')"
                >
                  End
                </th>
                <th
                  :class="thSortClass('health', 'gap')"
                  @click="toggleTableSort('health', 'gap')"
                >
                  Gap
                </th>
                <th
                  :class="thSortClass('health', 'missed')"
                  @click="toggleTableSort('health', 'missed')"
                >
                  Missed
                </th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(g, i) in sortedTickHealthGaps"
                :key="i"
              >
                <td>{{ fmtTime(g.start) }}</td>
                <td>{{ fmtTime(g.end) }}</td>
                <td>{{ fmtTime(g.duration) }}</td>
                <td>{{ g.missedTicks }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
    </template>

    <!-- Core migrations -->
    <div class="stats-sep" />
    <div
      class="stats-section-title collapsible"
      @click="migrationCollapsed = !migrationCollapsed"
    >
      <svg
        class="chevron"
        :class="{ collapsed: migrationCollapsed }"
        viewBox="0 0 10 10"
        width="10"
        height="10"
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
      Core Migrations{{ scopeSuffixStr }}
    </div>
    <template v-if="!migrationCollapsed">
      <div
        v-if="migrationStats.length === 0"
        class="range-hint"
      >
        {{ statsRange ? 'No migrated tasks in cursor range' : 'No tasks ran on multiple cores' }}
      </div>
      <div
        v-else
        class="stats-table-block"
      >
        <div
          class="stats-table-wrap"
          :style="{ maxHeight: tableHeight('migrations') + 'px' }"
        >
          <table class="stats-table stats-table-migration">
          <thead>
            <tr>
              <th
                :class="thSortClass('migrations', 'task')"
                @click="toggleTableSort('migrations', 'task')"
              >
                Task
              </th>
              <th
                :class="thSortClass('migrations', 'migr')"
                @click="toggleTableSort('migrations', 'migr')"
              >
                Migr
              </th>
              <th
                :class="thSortClass('migrations', 'cores')"
                @click="toggleTableSort('migrations', 'cores')"
              >
                Cores
              </th>
              <th
                :class="thSortClass('migrations', 'primary')"
                @click="toggleTableSort('migrations', 'primary')"
              >
                Primary
              </th>
              <th
                :class="thSortClass('migrations', 'ping')"
                @click="toggleTableSort('migrations', 'ping')"
              >
                Ping
              </th>
              <th
                :class="thSortClass('migrations', 'sti')"
                @click="toggleTableSort('migrations', 'sti')"
              >
                STI±
              </th>
              <th
                :class="thSortClass('migrations', 'gapAfter')"
                @click="toggleTableSort('migrations', 'gapAfter')"
              >
                Gap after
              </th>
              <th
                :class="thSortClass('migrations', 'gapOther')"
                @click="toggleTableSort('migrations', 'gapOther')"
              >
                Gap other
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in sortedMigrationStats"
              :key="row.mk"
              class="stats-table-row clickable"
              :title="`Highlight ${row.name}`"
              tabindex="0"
              @click="emit('highlightTask', row.mk)"
              @keydown.enter.prevent="emit('highlightTask', row.mk)"
              @keydown.space.prevent="emit('highlightTask', row.mk)"
            >
              <td class="task-col">{{ row.name }}</td>
              <td>{{ row.migrations }}</td>
              <td>{{ row.coreCount }}</td>
              <td>{{ row.primary }} ({{ row.primaryPct.toFixed(0) }}%)</td>
              <td>{{ row.pingPong }}</td>
              <td>{{ row.stiNear }}</td>
              <td>{{ row.gapAfter }}</td>
              <td>{{ row.gapOther }}</td>
            </tr>
          </tbody>
        </table>
        </div>
        <div
          class="stats-section-resizer"
          role="separator"
          aria-label="Resize core migrations table"
          aria-orientation="horizontal"
          @mousedown.prevent="onTableResizeStart('migrations', $event)"
        />
      </div>
    </template>

    <!-- Execution time per slice -->
    <div class="stats-sep" />
    <div
      class="stats-section-title collapsible"
      @click="execSliceCollapsed = !execSliceCollapsed"
    >
      <svg
        class="chevron"
        :class="{ collapsed: execSliceCollapsed }"
        viewBox="0 0 10 10"
        width="10"
        height="10"
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
      Execution Time Per Slice{{ scopeSuffixStr }}
    </div>
    <template v-if="!execSliceCollapsed">
      <div
        v-if="execSliceStats.length === 0"
        class="range-hint"
      >
        {{ statsRange ? 'No slices fully inside cursor range' : 'No user-task slices found' }}
      </div>
      <div
        v-else
        class="stats-table-block"
      >
        <div
          class="stats-table-wrap"
          :style="{ maxHeight: tableHeight('exec') + 'px' }"
        >
        <table class="stats-table">
          <thead>
            <tr>
              <th
                :class="thSortClass('exec', 'task')"
                @click="toggleTableSort('exec', 'task')"
              >
                Task
              </th>
              <th
                :class="thSortClass('exec', 'runs')"
                @click="toggleTableSort('exec', 'runs')"
              >
                Runs
              </th>
              <th
                :class="thSortClass('exec', 'cpu')"
                @click="toggleTableSort('exec', 'cpu')"
              >
                CPU%
              </th>
              <th
                :class="thSortClass('exec', 'min')"
                @click="toggleTableSort('exec', 'min')"
              >
                Min
              </th>
              <th
                :class="thSortClass('exec', 'avg')"
                @click="toggleTableSort('exec', 'avg')"
              >
                Avg
              </th>
              <th
                :class="thSortClass('exec', 'max')"
                @click="toggleTableSort('exec', 'max')"
              >
                Max
              </th>
              <th
                :class="thSortClass('exec', 'p95')"
                @click="toggleTableSort('exec', 'p95')"
              >
                p95
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in sortedExecSliceStats"
              :key="row.mk"
              class="stats-table-row clickable"
              :title="`Open execution-time plot for ${row.name}`"
              tabindex="0"
              @click="openPlot(row.mk, 'exec')"
              @keydown.enter.prevent="openPlot(row.mk, 'exec')"
              @keydown.space.prevent="openPlot(row.mk, 'exec')"
            >
              <td class="task-col">{{ row.name }}</td>
              <td>{{ row.runs }}</td>
              <td>{{ row.cpuPct.toFixed(1) }}%</td>
              <td
                class="extreme-col"
                :title="`Jump to shortest slice for ${row.name}`"
                @click.stop="jumpToSegment(row.mk, 'exec', false)"
              >
                {{ row.min }}
              </td>
              <td>{{ row.avg }}</td>
              <td
                class="extreme-col"
                :title="`Jump to longest slice for ${row.name}`"
                @click.stop="jumpToSegment(row.mk, 'exec', true)"
              >
                {{ row.max }}
              </td>
              <td>{{ row.p95 }}</td>
            </tr>
          </tbody>
        </table>
        </div>
        <div
          class="stats-section-resizer"
          role="separator"
          aria-label="Resize execution time table"
          aria-orientation="horizontal"
          @mousedown.prevent="onTableResizeStart('exec', $event)"
        />
      </div>
    </template>

    <!-- Blocking time -->
    <div class="stats-sep" />
    <div
      class="stats-section-title collapsible"
      @click="blockingCollapsed = !blockingCollapsed"
    >
      <svg
        class="chevron"
        :class="{ collapsed: blockingCollapsed }"
        viewBox="0 0 10 10"
        width="10"
        height="10"
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
      Blocking Time (off-CPU gap){{ scopeSuffixStr }}
    </div>
    <template v-if="!blockingCollapsed">
      <div
        v-if="blockingStats.length === 0"
        class="range-hint"
      >
        {{ statsRange ? 'No off-CPU gaps fully inside cursor range' : 'Need at least 2 activations per task' }}
      </div>
      <div
        v-else
        class="stats-table-block"
      >
        <div
          class="stats-table-wrap"
          :style="{ maxHeight: tableHeight('block') + 'px' }"
        >
        <table class="stats-table">
          <thead>
            <tr>
              <th
                :class="thSortClass('block', 'task')"
                @click="toggleTableSort('block', 'task')"
              >
                Task
              </th>
              <th
                :class="thSortClass('block', 'gaps')"
                @click="toggleTableSort('block', 'gaps')"
              >
                Gaps
              </th>
              <th
                :class="thSortClass('block', 'min')"
                @click="toggleTableSort('block', 'min')"
              >
                Min
              </th>
              <th
                :class="thSortClass('block', 'avg')"
                @click="toggleTableSort('block', 'avg')"
              >
                Avg
              </th>
              <th
                :class="thSortClass('block', 'max')"
                @click="toggleTableSort('block', 'max')"
              >
                Max
              </th>
              <th
                :class="thSortClass('block', 'p95')"
                @click="toggleTableSort('block', 'p95')"
              >
                p95
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in sortedBlockingStats"
              :key="row.mk"
              class="stats-table-row clickable"
              :title="`Open blocking-time plot for ${row.name}`"
              tabindex="0"
              @click="openPlot(row.mk, 'block')"
              @keydown.enter.prevent="openPlot(row.mk, 'block')"
              @keydown.space.prevent="openPlot(row.mk, 'block')"
            >
              <td class="task-col">{{ row.name }}</td>
              <td>{{ row.gaps }}</td>
              <td
                class="extreme-col"
                :title="`Jump to shortest blocking gap for ${row.name}`"
                @click.stop="jumpToSegment(row.mk, 'block', false)"
              >
                {{ row.min }}
              </td>
              <td>{{ row.avg }}</td>
              <td
                class="extreme-col"
                :title="`Jump to longest blocking gap for ${row.name}`"
                @click.stop="jumpToSegment(row.mk, 'block', true)"
              >
                {{ row.max }}
              </td>
              <td>{{ row.p95 }}</td>
            </tr>
          </tbody>
        </table>
        </div>
        <div
          class="stats-section-resizer"
          role="separator"
          aria-label="Resize blocking time table"
          aria-orientation="horizontal"
          @mousedown.prevent="onTableResizeStart('block', $event)"
        />
      </div>
    </template>

    <!-- Inter-arrival time -->
    <div class="stats-sep" />
    <div
      class="stats-section-title collapsible"
      @click="interArrivalCollapsed = !interArrivalCollapsed"
    >
      <svg
        class="chevron"
        :class="{ collapsed: interArrivalCollapsed }"
        viewBox="0 0 10 10"
        width="10"
        height="10"
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
      Inter-Arrival Time{{ scopeSuffixStr }}
    </div>
    <template v-if="!interArrivalCollapsed">
      <div
        v-if="interArrivalStats.length === 0"
        class="range-hint"
      >
        Need at least 2 activations per task
      </div>
      <div
        v-else
        class="stats-table-block"
      >
        <div
          class="stats-table-wrap"
          :style="{ maxHeight: tableHeight('inter') + 'px' }"
        >
        <table class="stats-table">
          <thead>
            <tr>
              <th
                :class="thSortClass('inter', 'task')"
                @click="toggleTableSort('inter', 'task')"
              >
                Task
              </th>
              <th
                :class="thSortClass('inter', 'runs')"
                @click="toggleTableSort('inter', 'runs')"
              >
                Runs
              </th>
              <th
                :class="thSortClass('inter', 'min')"
                @click="toggleTableSort('inter', 'min')"
              >
                Min
              </th>
              <th
                :class="thSortClass('inter', 'avg')"
                @click="toggleTableSort('inter', 'avg')"
              >
                Avg
              </th>
              <th
                :class="thSortClass('inter', 'max')"
                @click="toggleTableSort('inter', 'max')"
              >
                Max
              </th>
              <th
                :class="thSortClass('inter', 'p95')"
                @click="toggleTableSort('inter', 'p95')"
              >
                p95
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in sortedInterArrivalStats"
              :key="row.mk"
              class="stats-table-row clickable"
              :title="`Open inter-arrival plot for ${row.name}`"
              tabindex="0"
              @click="openPlot(row.mk, 'inter')"
              @keydown.enter.prevent="openPlot(row.mk, 'inter')"
              @keydown.space.prevent="openPlot(row.mk, 'inter')"
            >
              <td class="task-col">{{ row.name }}</td>
              <td>{{ row.runs }}</td>
              <td
                class="extreme-col"
                :title="`Jump to shortest inter-arrival for ${row.name}`"
                @click.stop="jumpToSegment(row.mk, 'inter', false)"
              >
                {{ row.min }}
              </td>
              <td>{{ row.avg }}</td>
              <td
                class="extreme-col"
                :title="`Jump to longest inter-arrival for ${row.name}`"
                @click.stop="jumpToSegment(row.mk, 'inter', true)"
              >
                {{ row.max }}
              </td>
              <td>{{ row.p95 }}</td>
            </tr>
          </tbody>
        </table>
        </div>
        <div
          class="stats-section-resizer"
          role="separator"
          aria-label="Resize inter-arrival table"
          aria-orientation="horizontal"
          @mousedown.prevent="onTableResizeStart('inter', $event)"
        />
      </div>
    </template>

    <!-- Preemption Chain Analysis -->
    <div class="stats-sep" />
    <div
      class="stats-section-title collapsible"
      @click="preemptionCollapsed = !preemptionCollapsed"
    >
      <svg
        class="chevron"
        :class="{ collapsed: preemptionCollapsed }"
        viewBox="0 0 10 10"
        width="10"
        height="10"
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
      Preemption Chain Analysis{{ scopeSuffixStr }}
    </div>
    <template v-if="!preemptionCollapsed">
      <div
        v-if="preemptionStats.length === 0"
        class="range-hint"
      >
        {{ statsRange ? 'No preemption events in cursor range' : 'No preemption events found' }}
      </div>
      <div
        v-else
        class="stats-table-block"
      >
        <div
          class="stats-table-wrap"
          :style="{ maxHeight: tableHeight('preemption') + 'px' }"
        >
          <table class="stats-table stats-table-preemption">
            <thead>
              <tr>
                <th
                  :class="thSortClass('preemption', 'victim')"
                  @click="toggleTableSort('preemption', 'victim')"
                >
                  Victim
                </th>
                <th
                  :class="thSortClass('preemption', 'preemptor')"
                  @click="toggleTableSort('preemption', 'preemptor')"
                >
                  Preemptor
                </th>
                <th
                  :class="thSortClass('preemption', 'count')"
                  @click="toggleTableSort('preemption', 'count')"
                >
                  Count
                </th>
                <th
                  :class="thSortClass('preemption', 'total')"
                  @click="toggleTableSort('preemption', 'total')"
                >
                  Total
                </th>
                <th
                  :class="thSortClass('preemption', 'avg')"
                  @click="toggleTableSort('preemption', 'avg')"
                >
                  Avg
                </th>
                <th
                  :class="thSortClass('preemption', 'max')"
                  @click="toggleTableSort('preemption', 'max')"
                >
                  Max
                </th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in sortedPreemptionStats"
                :key="`${row.mk}-${row.preemptor}`"
                class="stats-table-row clickable"
                :title="`Open preemption plot for ${row.victim} ← ${row.preemptor}`"
                tabindex="0"
                @click="openPreemptPlot(row.mk, row.preemptor)"
                @keydown.enter.prevent="openPreemptPlot(row.mk, row.preemptor)"
                @keydown.space.prevent="openPreemptPlot(row.mk, row.preemptor)"
              >
                <td class="task-col">{{ row.victim }}</td>
                <td class="task-col">{{ row.preemptor }}</td>
                <td>{{ row.count }}</td>
                <td>{{ row.total }}</td>
                <td>{{ row.avg }}</td>
                <td>{{ row.max }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div
          class="stats-section-resizer"
          role="separator"
          aria-label="Resize preemption chain table"
          aria-orientation="horizontal"
          @mousedown.prevent="onTableResizeStart('preemption', $event)"
        />
      </div>
    </template>

    <!-- Response Time Analysis -->
    <div class="stats-sep" />
    <div
      class="stats-section-title collapsible"
      @click="responseCollapsed = !responseCollapsed"
    >
      <svg
        class="chevron"
        :class="{ collapsed: responseCollapsed }"
        viewBox="0 0 10 10"
        width="10"
        height="10"
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
      Response Time Analysis{{ scopeSuffixStr }}
    </div>
    <template v-if="!responseCollapsed">
      <div
        v-if="responseTimeStats.length === 0"
        class="range-hint"
      >
        {{ statsRange ? 'No response time data in cursor range' : 'Need at least 2 activations per task' }}
      </div>
      <div
        v-else
        class="stats-table-block"
      >
        <div
          class="stats-table-wrap"
          :style="{ maxHeight: tableHeight('response') + 'px' }"
        >
          <table class="stats-table">
            <thead>
              <tr>
                <th
                  :class="thSortClass('response', 'task')"
                  @click="toggleTableSort('response', 'task')"
                >
                  Task
                </th>
                <th
                  :class="thSortClass('response', 'count')"
                  @click="toggleTableSort('response', 'count')"
                >
                  Events
                </th>
                <th
                  :class="thSortClass('response', 'min')"
                  @click="toggleTableSort('response', 'min')"
                >
                  Min
                </th>
                <th
                  :class="thSortClass('response', 'avg')"
                  @click="toggleTableSort('response', 'avg')"
                >
                  Avg
                </th>
                <th
                  :class="thSortClass('response', 'max')"
                  @click="toggleTableSort('response', 'max')"
                >
                  Max
                </th>
                <th
                  :class="thSortClass('response', 'p95')"
                  @click="toggleTableSort('response', 'p95')"
                >
                  p95
                </th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in sortedResponseTimeStats"
                :key="row.mk"
                class="stats-table-row clickable"
                :title="`Open response-time plot for ${row.name}`"
                tabindex="0"
                @click="openPlot(row.mk, 'response')"
                @keydown.enter.prevent="openPlot(row.mk, 'response')"
                @keydown.space.prevent="openPlot(row.mk, 'response')"
              >
                <td class="task-col">{{ row.name }}</td>
                <td>{{ row.count }}</td>
                <td
                  class="extreme-col"
                  :title="`Jump to shortest response time for ${row.name}`"
                  @click.stop="jumpToResponseSegment(row, false)"
                >
                  {{ row.min }}
                </td>
                <td>{{ row.avg }}</td>
                <td
                  class="extreme-col"
                  :title="`Jump to longest response time for ${row.name}`"
                  @click.stop="jumpToResponseSegment(row, true)"
                >
                  {{ row.max }}
                </td>
                <td>{{ row.p95 }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div
          class="stats-section-resizer"
          role="separator"
          aria-label="Resize response time table"
          aria-orientation="horizontal"
          @mousedown.prevent="onTableResizeStart('response', $event)"
        />
      </div>
    </template>

    <!-- Export -->
    <div class="stats-export-row">
      <button
        class="action-btn"
        title="Export statistics as CSV"
        @click="exportCsv"
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
        class="action-btn"
        title="Export statistics as HTML report"
        @click="exportHtml"
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
      <button
        class="action-btn"
        :disabled="!canCompareTabs"
        title="Compare summary, top tasks, and core migrations between two open trace tabs"
        @click="compareOpen = true"
      >
        Trace Compare…
      </button>
    </div>
    </template>
    <div
      v-else
      class="range-hint stats-empty-hint"
    >
      Open a trace file to view statistics.
    </div>
  </div>

  <TraceCompareDialog
    v-if="compareOpen && canCompareTabs"
    :tabs="loadedTabs"
    @close="compareOpen = false"
  />

  <div
    v-if="openPlotRef"
    class="plot-dialog-overlay"
    @click.self="closePlot"
  >
    <div
      class="plot-dialog"
      role="dialog"
      aria-modal="true"
      :aria-label="plotData?.title || 'Metrics plot'"
    >
      <div class="plot-dialog-header">
        <div class="plot-dialog-title">{{ plotData?.title }}</div>
        <button
          type="button"
          class="plot-close-btn"
          @click="closePlot"
        >
          Close
        </button>
      </div>

      <div
        v-if="plotScopeInfo"
        class="plot-scope-banner"
        :class="plotScopeInfo.scoped ? 'plot-scope-cursor' : 'plot-scope-full'"
      >
        <span class="plot-scope-badge">{{ plotScopeInfo.badge }}</span>
        <span class="plot-scope-detail">{{ plotScopeInfo.detail }}</span>
      </div>

      <div
        ref="plotContentRef"
        class="plot-dialog-body"
      >
        <div class="plot-card plot-card-scatter">
          <div
            v-if="plotData && plotData.points.length === 0"
            class="plot-empty"
          >
            No data in selected range
          </div>
          <svg
            v-else-if="scatterModel"
            class="plot-svg"
            :viewBox="`0 0 ${scatterModel.width} ${scatterModel.height}`"
          >
            <rect
              x="0"
              y="0"
              :width="scatterModel.width"
              :height="scatterModel.height"
              fill="var(--bg)"
            />

            <line
              v-for="grid in scatterModel.yTicks"
              :key="`scatter-grid-${grid.index}`"
              :x1="scatterModel.margin.left"
              :x2="scatterModel.width - scatterModel.margin.right"
              :y1="grid.y"
              :y2="grid.y"
              stroke="var(--border)"
              stroke-dasharray="3 4"
            />

            <line
              :x1="scatterModel.margin.left"
              :x2="scatterModel.margin.left"
              :y1="scatterModel.margin.top"
              :y2="scatterModel.height - scatterModel.margin.bottom"
              stroke="var(--fg-dim)"
            />
            <line
              :x1="scatterModel.margin.left"
              :x2="scatterModel.width - scatterModel.margin.right"
              :y1="scatterModel.height - scatterModel.margin.bottom"
              :y2="scatterModel.height - scatterModel.margin.bottom"
              stroke="var(--fg-dim)"
            />

            <g
              v-for="tick in scatterModel.yTicks"
              :key="`scatter-y-${tick.index}`"
            >
              <text
                :x="scatterModel.margin.left - 8"
                :y="tick.y + 4"
                text-anchor="end"
                fill="var(--fg-dim)"
                class="plot-axis-text"
              >
                {{ tick.label }}
              </text>
            </g>

            <g
              v-for="tick in scatterModel.xTicks"
              :key="`scatter-x-${tick.index}`"
            >
              <text
                :x="tick.x"
                :y="scatterModel.height - 10"
                text-anchor="middle"
                fill="var(--fg-dim)"
                class="plot-axis-text"
              >
                {{ tick.label }}
              </text>
            </g>

            <g
              v-for="refLine in scatterModel.referenceLines"
              :key="`scatter-ref-${refLine.label}`"
            >
              <line
                :x1="scatterModel.margin.left"
                :x2="scatterModel.width - scatterModel.margin.right"
                :y1="refLine.y"
                :y2="refLine.y"
                :stroke="refLine.color"
                stroke-dasharray="5 5"
              />
              <text
                :x="scatterModel.width - scatterModel.margin.right + 6"
                :y="refLine.y + 4"
                fill="var(--fg)"
                class="plot-ref-text"
              >
                {{ refLine.label }}
              </text>
            </g>

            <g>
              <circle
                v-for="point in scatterModel.points"
                :key="`scatter-point-${point.index}`"
                :cx="point.x"
                :cy="point.y"
                :r="point.index === selectedPlotPoint ? 5 : 3"
                :fill="point.index === selectedPlotPoint ? '#FFFFFF' : scatterModel.color"
                class="plot-point"
                :style="{ cursor: point.payload ? 'pointer' : 'default' }"
                @click="onPlotPointClick(point)"
              >
                <title>{{ point.label }}</title>
              </circle>
            </g>
          </svg>
        </div>

        <div class="plot-card plot-card-histogram">
          <div
            v-if="plotData && plotData.points.length === 0"
            class="plot-empty"
          >
            No data in selected range
          </div>
          <svg
            v-else-if="histogramModel"
            class="plot-svg"
            :viewBox="`0 0 ${histogramModel.width} ${histogramModel.height}`"
          >
            <rect
              x="0"
              y="0"
              :width="histogramModel.width"
              :height="histogramModel.height"
              fill="var(--bg)"
            />

            <line
              :x1="histogramModel.margin.left"
              :x2="histogramModel.margin.left"
              :y1="histogramModel.margin.top"
              :y2="histogramModel.height - histogramModel.margin.bottom"
              stroke="var(--fg-dim)"
            />
            <line
              :x1="histogramModel.margin.left"
              :x2="histogramModel.width - histogramModel.margin.right"
              :y1="histogramModel.height - histogramModel.margin.bottom"
              :y2="histogramModel.height - histogramModel.margin.bottom"
              stroke="var(--fg-dim)"
            />

            <rect
              v-for="bar in histogramModel.bars"
              :key="`hist-bar-${bar.index}`"
              :x="bar.x"
              :y="bar.y"
              :width="bar.width"
              :height="bar.height"
              :fill="histogramModel.color"
              fill-opacity="0.82"
            />

            <g
              v-for="refLine in histogramModel.referenceLines"
              :key="`hist-ref-${refLine.label}`"
            >
              <line
                :x1="refLine.x"
                :x2="refLine.x"
                :y1="histogramModel.margin.top"
                :y2="histogramModel.height - histogramModel.margin.bottom"
                :stroke="refLine.color"
                stroke-dasharray="5 5"
              />
              <text
                :x="Math.min(refLine.x + 6, histogramModel.width - histogramModel.margin.right - 2)"
                :y="histogramModel.margin.top + 12"
                fill="var(--fg)"
                class="plot-ref-text"
              >
                {{ refLine.label }}
              </text>
            </g>

            <g
              v-for="tick in histogramModel.xTicks"
              :key="`hist-x-${tick.index}`"
            >
              <text
                :x="tick.x"
                :y="histogramModel.height - 10"
                text-anchor="middle"
                fill="var(--fg-dim)"
                class="plot-axis-text"
              >
                {{ tick.label }}
              </text>
            </g>
          </svg>
        </div>
      </div>

      <div class="plot-dialog-footer">
        <button
          type="button"
          class="action-btn"
          @click="exportPlotPng"
        >
          Export PNG
        </button>
        <button
          type="button"
          class="action-btn"
          @click="exportPlotSvg"
        >
          Export SVG
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import { toBlob as domToBlob, toSvg as domToSvg } from 'html-to-image'
import { formatTime, isStiTagChannel } from '../renderer/TimelineRenderer.js'
import { taskDisplayName, parseTaskName, taskMergeKey, isIdleTaskName, taskColor, taskReprGet } from '../utils/colors.js'
import {
  getPlacedCursors,
  getStatsRange,
  segOverlapNs,
  segFullyInRange,
  segOverlapsRange,
  scopeSuffix,
  plotScopeBanner,
  traceMapGet,
  traceMapEntries,
} from '../utils/statsRange.js'
import {
  blockingTimeSamples,
  blockingTimePlotPoints,
  schedulingStats,
  maxNs,
  minNs,
  findWcetSegment,
  findBcetSegment,
  findExtremeBlockingSegment,
  findExtremeInterArrivalSegment,
  preemptionChainRows,
  preemptionChainPlotPoints,
  responseTimeRows,
  responseTimePlotPoints,
} from '../utils/statsAnalysis.js'
import { migrationRows } from '../utils/migrationAnalysis.js'
import { tickHealthReport } from '../utils/tickHealth.js'
import { requestStatsCompute } from '../utils/statsWorkerClient.js'
import { computeStatsTables, segIndicesMapFromTrace } from '../parser/statsCompute.js'
import {
  defaultStatsTableSort,
  nextSortState,
  sortStatsRows,
  sortHeaderClass,
  MIGRATION_SORT_ACCESSORS,
  EXEC_SORT_ACCESSORS,
  BLOCK_SORT_ACCESSORS,
  INTER_SORT_ACCESSORS,
  HEALTH_GAP_SORT_ACCESSORS,
  PREEMPTION_SORT_ACCESSORS,
  RESPONSE_SORT_ACCESSORS,
} from '../utils/statsTableSort.js'
import TraceCompareDialog from './TraceCompareDialog.vue'

const props = defineProps({
  trace:   { type: Object, default: null },
  cursors: { type: Array, default: () => [] },
  tabs:    { type: Array, default: () => [] },
})

const emit = defineEmits(['highlightTask', 'selectSegment'])

const coresCollapsed = ref(false)
const tasksCollapsed = ref(false)
const healthCollapsed = ref(false)
const execSliceCollapsed = ref(false)
const blockingCollapsed = ref(false)
const migrationCollapsed = ref(false)
const interArrivalCollapsed = ref(false)
const preemptionCollapsed = ref(false)
const responseCollapsed = ref(false)
const scopeToCursors = ref(true)

const STATS_SECTION_FLAGS = [
  coresCollapsed,
  tasksCollapsed,
  healthCollapsed,
  migrationCollapsed,
  execSliceCollapsed,
  blockingCollapsed,
  interArrivalCollapsed,
  preemptionCollapsed,
  responseCollapsed,
]

function expandAllSections() {
  for (const flag of STATS_SECTION_FLAGS) flag.value = false
}

function collapseAllSections() {
  for (const flag of STATS_SECTION_FLAGS) flag.value = true
}

const workerExecRows = ref([])
const workerBlockRows = ref([])
const workerInterRows = ref([])
const workerTaskCpuNs = ref(null)
let _statsRefreshTimer = null

function formatStatsRow(row, scale) {
  return {
    ...row,
    minNs: row.min,
    avgNs: row.avg,
    maxNs: row.max,
    p95Ns: row.p95,
    min: formatTime(row.min, scale),
    avg: formatTime(row.avg, scale),
    max: formatTime(row.max, scale),
    p95: formatTime(row.p95, scale),
  }
}

async function refreshStatsTables() {
  const tr = props.trace
  if (!tr?.segStore) {
    workerExecRows.value = []
    workerBlockRows.value = []
    workerInterRows.value = []
    workerTaskCpuNs.value = null
    return
  }

  const wantExec = !execSliceCollapsed.value
  const wantBlock = !blockingCollapsed.value
  const wantInter = !interArrivalCollapsed.value
  if (!wantExec && !wantBlock && !wantInter) {
    workerExecRows.value = []
    workerBlockRows.value = []
    workerInterRows.value = []
    return
  }

  const r = statsRange.value
  const lo = r?.lo ?? null
  const hi = r?.hi ?? null
  const totalNs = r ? (r.hi - r.lo) : (tr.timeMax - tr.timeMin)
  const scale = tr.timeScale

  let data = await requestStatsCompute({ lo, hi, wantExec, wantBlock, wantInter })

  if (!data) {
    const result = computeStatsTables(tr.segStore, {
      tasks: tr.tasks,
      taskRepr: tr.taskRepr,
      segIndicesByMk: segIndicesMapFromTrace(tr),
      lo,
      hi,
      totalNs,
    })
    data = {
      exec: wantExec ? result.exec : null,
      block: wantBlock ? result.block : null,
      inter: wantInter ? result.inter : null,
      taskCpuNs: result.taskCpuNs,
    }
  }

  if (data.exec) {
    workerExecRows.value = data.exec.map(row => ({
      ...formatStatsRow(row, scale),
      cpuPct: row.cpuPct,
    }))
  } else if (!wantExec) workerExecRows.value = []

  if (data.block) {
    workerBlockRows.value = data.block.map(row => formatStatsRow(row, scale))
  } else if (!wantBlock) workerBlockRows.value = []

  if (data.inter) {
    workerInterRows.value = data.inter.map(row => formatStatsRow(row, scale))
  } else if (!wantInter) workerInterRows.value = []

  if (data.taskCpuNs) workerTaskCpuNs.value = data.taskCpuNs
}

function scheduleStatsRefresh() {
  clearTimeout(_statsRefreshTimer)
  _statsRefreshTimer = setTimeout(() => { refreshStatsTables() }, 120)
}

const TABLE_MIN_H = 80
const TABLE_MAX_H = 480
const STATS_MAX_VISIBLE_ROWS = 8
const STATS_UTIL_ROW_H = 16
const STATS_UTIL_ROW_GAP = 3
// Match .stats-table cell metrics: padding 3+3, border 1, line-height 14.
const STATS_TABLE_ROW_H = 21
const STATS_TABLE_HEADER_H = 22
const STATS_TABLE_HSCROLL_H = 14
const STATS_TABLE_WRAP_BORDER = 2

function statsTableViewportHeight(visibleRows = STATS_MAX_VISIBLE_ROWS, reserveHScroll = false) {
  let h = STATS_TABLE_HEADER_H + visibleRows * STATS_TABLE_ROW_H + STATS_TABLE_WRAP_BORDER
  if (reserveHScroll) h += STATS_TABLE_HSCROLL_H
  return h
}

const STATS_TABLE_DEFAULT_H = statsTableViewportHeight()
const STATS_TABLE_MIG_DEFAULT_H = statsTableViewportHeight(STATS_MAX_VISIBLE_ROWS, true)

const sectionHeights = ref({
  migrations: STATS_TABLE_MIG_DEFAULT_H,
  exec: STATS_TABLE_DEFAULT_H,
  block: STATS_TABLE_DEFAULT_H,
  inter: STATS_TABLE_DEFAULT_H,
  preemption: STATS_TABLE_MIG_DEFAULT_H,
  response: STATS_TABLE_DEFAULT_H,
})
let _tableResize = null
const openPlotRef = ref(null)   // { mk, kind } when plot dialog is open
const plotContentRef = ref(null)
const selectedPlotPoint = ref(-1)
const compareOpen = ref(false)

const tableSort = ref({
  migrations: defaultStatsTableSort(),
  exec: defaultStatsTableSort(),
  block: defaultStatsTableSort(),
  inter: defaultStatsTableSort(),
  health: defaultStatsTableSort(),
  preemption: defaultStatsTableSort(),
  response: defaultStatsTableSort(),
})

function toggleTableSort(tableId, col) {
  tableSort.value[tableId] = nextSortState(tableSort.value[tableId], col)
}

function thSortClass(tableId, col) {
  return sortHeaderClass(tableSort.value[tableId], col)
}

const loadedTabs = computed(() => props.tabs.filter(t => t.trace))
const canCompareTabs = computed(() => loadedTabs.value.length >= 2)

function clampPct(v) { return Math.max(0, Math.min(100, v)).toFixed(1) }

function tableHeight(id) {
  const fallback = id === 'migrations' ? STATS_TABLE_MIG_DEFAULT_H : STATS_TABLE_DEFAULT_H
  return sectionHeights.value[id] ?? fallback
}

function utilScrollStyle(rowCount) {
  const vis = Math.min(Math.max(rowCount, 1), STATS_MAX_VISIBLE_ROWS)
  const h = vis * STATS_UTIL_ROW_H + Math.max(0, vis - 1) * STATS_UTIL_ROW_GAP + 2
  return { height: `${h}px`, overflowY: 'auto', overflowX: 'hidden', flexShrink: '0' }
}

function onTableResizeStart(id, e) {
  _tableResize = { id, startY: e.clientY, startH: tableHeight(id) }
  document.body.classList.add('row-resizing')
  document.addEventListener('mousemove', onTableResizeMove)
  document.addEventListener('mouseup', onTableResizeEnd)
}

function onTableResizeMove(e) {
  if (!_tableResize) return
  const delta = e.clientY - _tableResize.startY
  sectionHeights.value[_tableResize.id] = Math.max(
    TABLE_MIN_H,
    Math.min(TABLE_MAX_H, _tableResize.startH + delta),
  )
}

function onTableResizeEnd() {
  _tableResize = null
  document.body.classList.remove('row-resizing')
  document.removeEventListener('mousemove', onTableResizeMove)
  document.removeEventListener('mouseup', onTableResizeEnd)
}

onBeforeUnmount(() => {
  clearTimeout(_statsRefreshTimer)
  onTableResizeEnd()
})

const placedCursorCount = computed(() => getPlacedCursors(props.cursors).length)

const statsRange = computed(() => getStatsRange(props.cursors, scopeToCursors.value))

const scopeSuffixStr = computed(() => scopeSuffix(statsRange.value))

const tickHealth = computed(() => {
  const r = statsRange.value
  return tickHealthReport(props.trace, r?.lo ?? null, r?.hi ?? null)
})

function fmtTime(ns) {
  return formatTime(ns, props.trace.timeScale)
}

const scopeRangeLabel = computed(() => {
  const r = statsRange.value
  if (!r) {
    return placedCursorCount.value < 2
      ? 'Place 2+ cursors to measure a time window'
      : ''
  }
  const scale = props.trace.timeScale
  return `C1–C${r.nCursors}: ${formatTime(r.lo, scale)} … ${formatTime(r.hi, scale)} (${formatTime(r.hi - r.lo, scale)})`
})

watch(placedCursorCount, (n) => {
  if (n < 2) scopeToCursors.value = false
})

const spanStr = computed(() => {
  const tr = props.trace
  const r = statsRange.value
  const ns = r ? (r.hi - r.lo) : (tr.timeMax - tr.timeMin)
  return formatTime(ns, tr.timeScale)
})

const summaryTaskCount = computed(() => {
  const tr = props.trace
  const r = statsRange.value
  if (!r) return tr.tasks.length
  let n = 0
  for (const segs of tr.segByMergeKey.values()) {
    if (segs.some(s => segOverlapsRange(s, r.lo, r.hi))) n++
  }
  return n
})

const summarySegCount = computed(() => {
  const tr = props.trace
  const r = statsRange.value
  if (!r) return tr.segments.length
  let n = 0
  for (const segs of tr.segByMergeKey.values()) {
    for (const s of segs) {
      if (s.end <= r.lo) continue
      if (s.start > r.hi) break
      if (segOverlapsRange(s, r.lo, r.hi)) n++
    }
  }
  return n
})

const summaryStiCount = computed(() => {
  const tr = props.trace
  const r = statsRange.value
  if (!r) {
    return tr.stiEvents.filter(ev => !isStiTagChannel(ev.target)).length
  }
  return tr.stiEvents.filter(
    ev => !isStiTagChannel(ev.target) && ev.time >= r.lo && ev.time <= r.hi,
  ).length
})

const schedulingSummary = computed(() => {
  const tr = props.trace
  if (!tr) return null
  const r = statsRange.value
  const lo = r?.lo ?? null
  const hi = r?.hi ?? null
  const { contextSwitches, coreGaps, gapMax } = schedulingStats(tr, lo, hi)
  if (contextSwitches <= 0) return null
  const scale = tr.timeScale
  const avg = Math.round(coreGaps.reduce((a, b) => a + b, 0) / coreGaps.length)
  return {
    contextSwitches,
    gapAvg: formatTime(avg, scale),
    gapMax: formatTime(gapMax, scale),
  }
})

// ---- Core utilisation (excl. IDLE/TICK) --------------------------------
const coreStats = computed(() => {
  const tr = props.trace
  if (!tr || !tr.coreNames || tr.coreNames.length === 0) return []
  const r = statsRange.value
  const total = r ? (r.hi - r.lo) : (tr.timeMax - tr.timeMin)
  if (total <= 0) return []
  return tr.coreNames.map(core => {
    const segs = traceMapGet(tr.coreSegs, core) || []
    let active = 0
    for (const s of segs) {
      const { name } = parseTaskName(s.task)
      if (name === 'TICK' || isIdleTaskName(name)) continue
      active += r ? segOverlapNs(s, r.lo, r.hi) : (s.end - s.start)
    }
    return { core, pct: 100.0 * active / total }
  })
})

// ---- Top 10 tasks by CPU -----------------------------------------------
const topTasks = computed(() => {
  const tr = props.trace
  if (!tr) return []
  const r = statsRange.value
  const total = r ? (r.hi - r.lo) : (tr.timeMax - tr.timeMin)
  if (total <= 0) return []
  const source = (r && workerTaskCpuNs.value) ? workerTaskCpuNs.value : (tr.taskCpuNs || [])
  return source.slice(0, 10).map(([mk, t]) => ({
    mk,
    name: taskDisplayName(taskReprGet(tr, mk) || mk),
    pct: 100.0 * t / total,
  }))
})

function _summarizeSamples(samples, scale) {
  if (!samples || samples.length === 0) return null
  const sorted = [...samples].sort((a, b) => a - b)
  const n = sorted.length
  const sum = sorted.reduce((a, b) => a + b, 0)
  const p95Idx = Math.min(n - 1, Math.ceil(n * 0.95) - 1)
  return {
    min: formatTime(sorted[0], scale),
    avg: formatTime(Math.round(sum / n), scale),
    max: formatTime(sorted[n - 1], scale),
    p95: formatTime(sorted[p95Idx], scale),
  }
}

const execSliceStats = computed(() => workerExecRows.value)

const blockingStats = computed(() => workerBlockRows.value)

const migrationStats = computed(() => {
  if (migrationCollapsed.value) return []
  const tr = props.trace
  if (!tr) return []
  const r = statsRange.value
  const lo = r?.lo ?? null
  const hi = r?.hi ?? null
  return migrationRows(tr, lo, hi)
})

const sortedMigrationStats = computed(() =>
  sortStatsRows(migrationStats.value, tableSort.value.migrations, MIGRATION_SORT_ACCESSORS))

const sortedExecSliceStats = computed(() =>
  sortStatsRows(execSliceStats.value, tableSort.value.exec, EXEC_SORT_ACCESSORS))

const sortedBlockingStats = computed(() =>
  sortStatsRows(blockingStats.value, tableSort.value.block, BLOCK_SORT_ACCESSORS))

const interArrivalStats = computed(() => workerInterRows.value)

const sortedInterArrivalStats = computed(() =>
  sortStatsRows(interArrivalStats.value, tableSort.value.inter, INTER_SORT_ACCESSORS))

const sortedTickHealthGaps = computed(() =>
  sortStatsRows(
    tickHealth.value.largeGaps.slice(0, 8),
    tableSort.value.health,
    HEALTH_GAP_SORT_ACCESSORS,
  ))

const preemptionStats = computed(() => {
  if (preemptionCollapsed.value) return []
  const tr = props.trace
  if (!tr) return []
  const r = statsRange.value
  const lo = r?.lo ?? null
  const hi = r?.hi ?? null
  return preemptionChainRows(tr, lo, hi)
})

const sortedPreemptionStats = computed(() =>
  sortStatsRows(preemptionStats.value, tableSort.value.preemption, PREEMPTION_SORT_ACCESSORS))

const responseTimeStats = computed(() => {
  if (responseCollapsed.value) return []
  const tr = props.trace
  if (!tr) return []
  const r = statsRange.value
  const lo = r?.lo ?? null
  const hi = r?.hi ?? null
  return responseTimeRows(tr, lo, hi)
})

const sortedResponseTimeStats = computed(() =>
  sortStatsRows(responseTimeStats.value, tableSort.value.response, RESPONSE_SORT_ACCESSORS))

function jumpToResponseSegment(row, findMax) {
  const seg = findMax ? row.worstSeg : row.bestSeg
  if (seg) emit('selectSegment', seg)
}

function jumpToSegment(mk, kind, findMax) {
  const tr = props.trace
  if (!tr) return
  const r = statsRange.value
  const lo = r?.lo ?? null
  const hi = r?.hi ?? null
  const segs = tr.segByMergeKey?.get(mk) || []
  let seg = null
  if (kind === 'exec') {
    seg = findMax ? findWcetSegment(segs, lo, hi) : findBcetSegment(segs, lo, hi)
  } else if (kind === 'block') {
    seg = findExtremeBlockingSegment(segs, lo, hi, findMax)
  } else if (kind === 'inter') {
    seg = findExtremeInterArrivalSegment(segs, lo, hi, findMax)
  }
  if (seg) emit('selectSegment', seg)
}

function _summarizeNumericSamples(samples) {
  if (!samples || samples.length === 0) return null
  const values = [...samples].sort((a, b) => a - b)
  const n = values.length
  return {
    avg: values.reduce((sum, value) => sum + value, 0) / n,
    p50: values[Math.min(n - 1, Math.floor(n * 0.5))],
    p95: values[Math.min(n - 1, Math.floor(n * 0.95))],
  }
}

function _downloadBlob(filename, blob) {
  if (!blob) return
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

function _downloadDataUrl(filename, dataUrl) {
  if (!dataUrl) return
  const anchor = document.createElement('a')
  anchor.href = dataUrl
  anchor.download = filename
  anchor.click()
}

function _safeFileName(title) {
  return title.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'metrics-plot'
}

function _buildExecPlot(trace, mk, range) {
  let segs = trace?.segByMergeKey?.get(mk) || []
  if (segs.length === 0) return null
  const repr = trace.taskRepr.get(mk) || mk
  const suffix = scopeSuffix(range)
  if (range) {
    segs = segs.filter(s => segFullyInRange(s, range.lo, range.hi))
  }
  const points = segs
    .filter(seg => seg.end > seg.start)
    .map((seg, index) => ({
      index,
      xNs: seg.start,
      yValue: seg.end - seg.start,
      payload: seg,
      label: `${taskDisplayName(repr)}: ${formatTime(seg.end - seg.start, trace.timeScale)} at ${formatTime(seg.start, trace.timeScale)}`,
    }))
  return {
    kind: 'exec',
    mk,
    title: `${taskDisplayName(repr)} - Execution Time${suffix}`,
    color: taskColor(mk, repr),
    points,
  }
}

function _buildInterPlot(trace, mk, range) {
  const segs = trace?.segByMergeKey?.get(mk) || []
  if (segs.length < 2) return null
  const repr = trace.taskRepr.get(mk) || mk
  const suffix = scopeSuffix(range)
  const sorted = [...segs].sort((a, b) => a.start - b.start)
  const points = []
  for (let i = 1; i < sorted.length; i++) {
    if (range && (sorted[i].start < range.lo || sorted[i].start > range.hi)) continue
    const delta = sorted[i].start - sorted[i - 1].start
    if (delta <= 0) continue
    points.push({
      index: points.length,
      xNs: sorted[i].start,
      yValue: delta,
      payload: sorted[i],
      label: `${taskDisplayName(repr)}: ${formatTime(delta, trace.timeScale)} from ${formatTime(sorted[i - 1].start, trace.timeScale)}`,
    })
  }
  return {
    kind: 'inter',
    mk,
    title: `${taskDisplayName(repr)} - Inter-Arrival Time${suffix}`,
    color: taskColor(mk, repr),
    points,
  }
}

function _buildBlockPlot(trace, mk, range) {
  const segs = trace?.segByMergeKey?.get(mk) || []
  if (segs.length < 2) return null
  const repr = trace.taskRepr.get(mk) || mk
  const suffix = scopeSuffix(range)
  const lo = range?.lo ?? null
  const hi = range?.hi ?? null
  const rawPoints = blockingTimePlotPoints(segs, lo, hi)
  const points = rawPoints.map((pt, index) => ({
    index,
    xNs: pt.xNs,
    yValue: pt.yValue,
    payload: pt.payload,
    label: `${taskDisplayName(repr)}: ${formatTime(pt.yValue, trace.timeScale)} blocked before ${formatTime(pt.xNs, trace.timeScale)}`,
  }))
  return {
    kind: 'block',
    mk,
    title: `${taskDisplayName(repr)} - Blocking Time${suffix}`,
    color: taskColor(mk, repr),
    points,
  }
}

function _buildResponsePlot(trace, mk, range) {
  const segs = trace?.segByMergeKey?.get(mk) || []
  if (segs.length < 2) return null
  const repr = trace.taskRepr.get(mk) || mk
  const suffix = scopeSuffix(range)
  const lo = range?.lo ?? null
  const hi = range?.hi ?? null
  const rawPoints = responseTimePlotPoints(segs, lo, hi)
  const points = rawPoints.map((pt, index) => ({
    index,
    xNs: pt.xNs,
    yValue: pt.yValue,
    payload: pt.payload,
    label: `${taskDisplayName(repr)}: ${formatTime(pt.yValue, trace.timeScale)} response at ${formatTime(pt.xNs, trace.timeScale)}`,
  }))
  return {
    kind: 'response',
    mk,
    title: `${taskDisplayName(repr)} - Response Time${suffix}`,
    color: taskColor(mk, repr),
    points,
  }
}

function _buildPreemptPlot(trace, victimMk, preemptor, range) {
  const repr = trace?.taskRepr?.get(victimMk) || victimMk
  const suffix = scopeSuffix(range)
  const lo = range?.lo ?? null
  const hi = range?.hi ?? null
  const rawPoints = preemptionChainPlotPoints(trace, victimMk, preemptor, lo, hi)
  const points = rawPoints.map((pt, index) => ({
    index,
    xNs: pt.xNs,
    yValue: pt.yValue,
    payload: pt.payload,
    label: `${taskDisplayName(repr)} ← ${preemptor}: ${formatTime(pt.yValue, trace.timeScale)} at ${formatTime(pt.xNs, trace.timeScale)}`,
  }))
  return {
    kind: 'preempt',
    mk: victimMk,
    preemptor,
    title: `${taskDisplayName(repr)} ← preempted by ${preemptor}${suffix}`,
    color: taskColor(victimMk, repr),
    points,
  }
}

const plotData = computed(() => {
  const open = openPlotRef.value
  if (!open) return null
  const range = statsRange.value
  if (open.kind === 'exec') return _buildExecPlot(props.trace, open.mk, range)
  if (open.kind === 'block') return _buildBlockPlot(props.trace, open.mk, range)
  if (open.kind === 'response') return _buildResponsePlot(props.trace, open.mk, range)
  if (open.kind === 'preempt') {
    return _buildPreemptPlot(props.trace, open.mk, open.preemptor, range)
  }
  return _buildInterPlot(props.trace, open.mk, range)
})

const plotScopeInfo = computed(() => {
  if (!openPlotRef.value) return null
  return plotScopeBanner(statsRange.value, props.trace.timeScale, formatTime)
})

function openPlot(mk, kind) {
  const range = statsRange.value
  let plot
  if (kind === 'exec') plot = _buildExecPlot(props.trace, mk, range)
  else if (kind === 'block') plot = _buildBlockPlot(props.trace, mk, range)
  else if (kind === 'response') plot = _buildResponsePlot(props.trace, mk, range)
  else plot = _buildInterPlot(props.trace, mk, range)
  if (!plot || plot.points.length === 0) return
  openPlotRef.value = { mk, kind }
  selectedPlotPoint.value = -1
}

function openPreemptPlot(victimMk, preemptor) {
  const range = statsRange.value
  const plot = _buildPreemptPlot(props.trace, victimMk, preemptor, range)
  if (!plot || plot.points.length === 0) return
  openPlotRef.value = { mk: victimMk, kind: 'preempt', preemptor }
  selectedPlotPoint.value = -1
}

function closePlot() {
  openPlotRef.value = null
  selectedPlotPoint.value = -1
}

function onPlotPointClick(point) {
  selectedPlotPoint.value = point.index
  if (point.payload) emit('selectSegment', point.payload)
}

const scatterModel = computed(() => {
  const plot = plotData.value
  if (!plot || plot.points.length === 0) return null
  const width = 820
  const height = 320
  const margin = { left: 72, right: 42, top: 16, bottom: 34 }
  const xs = plot.points.map(point => point.xNs)
  const ys = plot.points.map(point => point.yValue)
  const x0 = Math.min(...xs)
  const x1 = Math.max(...xs)
  const yMax = Math.max(1, ...ys)
  const xSpan = Math.max(1, x1 - x0)
  const plotW = width - margin.left - margin.right
  const plotH = height - margin.top - margin.bottom
  const summary = _summarizeNumericSamples(ys)

  const scaleX = value => margin.left + ((value - x0) / xSpan) * plotW
  const scaleY = value => margin.top + plotH - (value / yMax) * plotH

  return {
    width,
    height,
    margin,
    color: plot.color,
    xTicks: [0, 0.5, 1].map((ratio, index) => {
      const value = Math.round(x0 + xSpan * ratio)
      return { index, x: scaleX(value), label: formatTime(value, props.trace.timeScale) }
    }),
    yTicks: Array.from({ length: 5 }, (_, index) => {
      const value = yMax * (1 - index / 4)
      return { index, y: scaleY(value), label: formatTime(Math.round(value), props.trace.timeScale) }
    }),
    referenceLines: summary ? [
      { label: 'avg', y: scaleY(summary.avg), color: '#CE93D8' },
      { label: 'p50', y: scaleY(summary.p50), color: '#4CAF50' },
      { label: 'p95', y: scaleY(summary.p95), color: '#FF9800' },
    ] : [],
    points: plot.points.map(point => ({
      ...point,
      x: scaleX(point.xNs),
      y: scaleY(point.yValue),
    })),
  }
})

const histogramModel = computed(() => {
  const plot = plotData.value
  if (!plot || plot.points.length === 0) return null
  const width = 820
  const height = 220
  const margin = { left: 72, right: 24, top: 16, bottom: 34 }
  const values = plot.points.map(point => point.yValue).sort((a, b) => a - b)
  const v0 = values[0]
  const v1 = values[values.length - 1]
  const vSpan = Math.max(1, v1 - v0)
  const plotW = width - margin.left - margin.right
  const plotH = height - margin.top - margin.bottom
  const binCount = 50
  const counts = Array.from({ length: binCount }, () => 0)
  const step = vSpan / binCount
  for (const value of values) {
    const rawIndex = step > 0 ? Math.floor((value - v0) / step) : 0
    counts[Math.min(binCount - 1, Math.max(0, rawIndex))] += 1
  }
  const maxCount = Math.max(1, ...counts)
  const summary = _summarizeNumericSamples(values)
  const scaleX = value => margin.left + ((value - v0) / vSpan) * plotW

  return {
    width,
    height,
    margin,
    color: plot.color,
    bars: counts.map((count, index) => {
      const barWidth = Math.max(1, plotW / binCount - 1)
      const barHeight = count > 0 ? (count / maxCount) * plotH : 0
      return {
        index,
        x: margin.left + (index * plotW) / binCount,
        y: margin.top + plotH - barHeight,
        width: barWidth,
        height: barHeight,
      }
    }),
    xTicks: [0, 0.5, 1].map((ratio, index) => {
      const value = Math.round(v0 + vSpan * ratio)
      return { index, x: scaleX(value), label: formatTime(value, props.trace.timeScale) }
    }),
    referenceLines: summary ? [
      { label: 'avg', x: scaleX(summary.avg), color: '#CE93D8' },
      { label: 'p50', x: scaleX(summary.p50), color: '#4CAF50' },
      { label: 'p95', x: scaleX(summary.p95), color: '#FF9800' },
    ] : [],
  }
})

async function exportPlotPng() {
  if (!plotContentRef.value || !plotData.value) return
  const blob = await domToBlob(plotContentRef.value, {
    cacheBust: true,
    pixelRatio: window.devicePixelRatio || 1,
  })
  _downloadBlob(`${_safeFileName(plotData.value.title)}.png`, blob)
}

async function exportPlotSvg() {
  if (!plotContentRef.value || !plotData.value) return
  const dataUrl = await domToSvg(plotContentRef.value, { cacheBust: true })
  _downloadDataUrl(`${_safeFileName(plotData.value.title)}.svg`, dataUrl)
}

function _htmlCell(v) {
  return String(v ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function _csvCell(v) {
  const s = String(v ?? '').replace(/[µμ]s/g, 'us')
  if (/[",\n]/.test(s)) return `"${s.replace(/"/g, '""')}"`
  return s
}

function _downloadText(filename, text, mime) {
  const blob = new Blob([text], { type: mime })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

function _stamp() {
  const d = new Date()
  const pad = n => String(n).padStart(2, '0')
  return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`
}

function exportCsv() {
  const tr = props.trace
  const r = statsRange.value
  const suffix = scopeSuffixStr.value
  const execReportRows = _execSliceRowsForReport(tr, r)
  const interReportRows = _interArrivalRowsForReport(tr, r)
  const blockReportRows = _blockingRowsForReport(tr, r)
  const coreRows = _coreUtilRows(tr, r)
  const taskRows = _taskCpuRows(tr, r)
  const lo = r?.lo ?? null
  const hi = r?.hi ?? null
  const preemptReportRows = preemptionChainRows(tr, lo, hi)
  const respReportRows = responseTimeRows(tr, lo, hi)
  const { contextSwitches, coreGaps } = schedulingStats(tr, lo, hi)
  const lines = []

  lines.push('Summary')
  lines.push('Metric,Value')
  lines.push(`Span${suffix},${_csvCell(spanStr.value)}`)
  if (suffix) {
    lines.push(`Cursor range,${_csvCell(scopeRangeLabel.value)}`)
  }
  lines.push(`Tasks,${_csvCell(summaryTaskCount.value)}`)
  lines.push(`Segments,${_csvCell(summarySegCount.value)}`)
  lines.push(`STI Events,${_csvCell(summaryStiCount.value)}`)
  lines.push(`Context switches${suffix},${_csvCell(contextSwitches)}`)
  if (coreGaps.length > 0) {
    const gapAvg = Math.round(coreGaps.reduce((a, b) => a + b, 0) / coreGaps.length)
    lines.push(`Core gap avg${suffix},${_csvCell(formatTime(gapAvg, tr.timeScale))}`)
    lines.push(`Core gap max${suffix},${_csvCell(formatTime(maxNs(coreGaps), tr.timeScale))}`)
  }

  if (rangeStats.value && !r) {
    lines.push('')
    lines.push('Cursor Range')
    lines.push('Metric,Value')
    lines.push(`Span,${_csvCell(rangeStats.value.span)}`)
    lines.push(`Slices,${_csvCell(rangeStats.value.switches)}`)
    if (rangeStats.value.topTask) lines.push(`Top task,${_csvCell(`${rangeStats.value.topTask} (${rangeStats.value.topPct}%)`)}`)
    if (rangeStats.value.dMin) lines.push(`Seg min,${_csvCell(rangeStats.value.dMin)}`)
    if (rangeStats.value.dAvg) lines.push(`Seg avg,${_csvCell(rangeStats.value.dAvg)}`)
    if (rangeStats.value.dMax) lines.push(`Seg max,${_csvCell(rangeStats.value.dMax)}`)
  }

  lines.push('')
  lines.push(`Core Utilisation (excl. IDLE/TICK)${suffix}`)
  lines.push('Core,CPU %')
  if (coreRows.length > 0) {
    for (const r of coreRows) {
      lines.push(`${_csvCell(r.core)},${_csvCell(`${r.pct}%`)}`)
    }
  } else {
    lines.push('No data,')
  }

  lines.push('')
  lines.push(`Top Tasks by CPU (excl. IDLE/TICK)${suffix}`)
  lines.push('Task,CPU %')
  if (taskRows.length > 0) {
    for (const r of taskRows) {
      lines.push(`${_csvCell(r.name)},${_csvCell(`${r.pct}%`)}`)
    }
  } else {
    lines.push('No data,')
  }

  const tick = tickHealthReport(tr, lo, hi)
  lines.push('')
  lines.push(`Trace Health (TICK)${suffix}`)
  if (tick.tickCount) {
    lines.push(`Status,${_csvCell(tick.health.toUpperCase())}`)
    lines.push(`Ticks,${_csvCell(tick.tickCount)}`)
    lines.push(`Avg period,${_csvCell(formatTime(tick.avgPeriod, tr.timeScale))}`)
    lines.push(`Max gap,${_csvCell(formatTime(tick.maxGap, tr.timeScale))}`)
    lines.push(`Missed ticks (est.),${_csvCell(tick.missedTicksEstimate)}`)
    lines.push('')
    lines.push('Large TICK gaps')
    lines.push('Start,End,Gap,Missed')
    if (tick.largeGaps.length) {
      for (const g of tick.largeGaps) {
        lines.push([
          _csvCell(formatTime(g.start, tr.timeScale)),
          _csvCell(formatTime(g.end, tr.timeScale)),
          _csvCell(formatTime(g.duration, tr.timeScale)),
          _csvCell(g.missedTicks),
        ].join(','))
      }
    } else {
      lines.push('No large gaps,,,')
    }
  } else {
    lines.push('No STI TICK events,')
  }

  lines.push('')
  lines.push(`Core Migrations${suffix}`)
  lines.push('Task,Migrations,Core count,Primary core,Primary %,Ping-pong,STI near,Gap after avg,Gap other avg')
  const migReportRows = migrationRows(tr, lo, hi)
  for (const r of migReportRows) {
    lines.push([
      _csvCell(r.name),
      _csvCell(r.migrations),
      _csvCell(r.coreCount),
      _csvCell(r.primary),
      _csvCell(`${r.primaryPct.toFixed(1)}%`),
      _csvCell(r.pingPong),
      _csvCell(r.stiNear),
      _csvCell(r.gapAfter),
      _csvCell(r.gapOther),
    ].join(','))
  }

  lines.push('')
  lines.push(`Execution Time Per Slice${suffix}`)
  lines.push('Task,Runs,CPU%,Min,Avg,TrimMean(5%),Max,p50,p95')
  for (const r of execReportRows) {
    lines.push([
      _csvCell(r.name),
      _csvCell(r.runs),
      _csvCell(`${r.cpuPct.toFixed(1)}%`),
      _csvCell(r.min),
      _csvCell(r.avg),
      _csvCell(r.trimMean),
      _csvCell(r.max),
      _csvCell(r.p50),
      _csvCell(r.p95),
    ].join(','))
  }

  lines.push('')
  lines.push(`Blocking Time (off-CPU gap)${suffix}`)
  lines.push('Task,Gaps,Min,Avg,TrimMean(5%),Max,p50,p95')
  for (const r of blockReportRows) {
    lines.push([
      _csvCell(r.name),
      _csvCell(r.runs),
      _csvCell(r.min),
      _csvCell(r.avg),
      _csvCell(r.trimMean),
      _csvCell(r.max),
      _csvCell(r.p50),
      _csvCell(r.p95),
    ].join(','))
  }

  lines.push('')
  lines.push(`Inter-Arrival Time${suffix}`)
  lines.push('Task,Runs,Min,Avg,TrimMean(5%),Max,p50,p95')
  for (const r of interReportRows) {
    lines.push([
      _csvCell(r.name),
      _csvCell(r.runs),
      _csvCell(r.min),
      _csvCell(r.avg),
      _csvCell(r.trimMean),
      _csvCell(r.max),
      _csvCell(r.p50),
      _csvCell(r.p95),
    ].join(','))
  }

  lines.push('')
  lines.push(`Preemption Chain Analysis${suffix}`)
  lines.push('Victim,Preemptor,Count,Total,Avg,Max')
  if (preemptReportRows.length) {
    for (const row of preemptReportRows) {
      lines.push([
        _csvCell(row.victim),
        _csvCell(row.preemptor),
        _csvCell(row.count),
        _csvCell(row.total),
        _csvCell(row.avg),
        _csvCell(row.max),
      ].join(','))
    }
  } else {
    lines.push('No preemption events found,,,,,')
  }

  lines.push('')
  lines.push(`Response Time Analysis${suffix}`)
  lines.push('Task,Events,Min,Avg,Max,p95')
  if (respReportRows.length) {
    for (const row of respReportRows) {
      lines.push([
        _csvCell(row.name),
        _csvCell(row.count),
        _csvCell(row.min),
        _csvCell(row.avg),
        _csvCell(row.max),
        _csvCell(row.p95),
      ].join(','))
    }
  } else {
    lines.push('No data,,,,,')
  }

  _downloadText(`statistics-${_stamp()}.csv`, `\uFEFF${lines.join('\n')}`, 'text/csv;charset=utf-8')
}

function _summarizeSamplesReport(samples, scale) {
  if (!samples || samples.length === 0) return null
  const sorted = [...samples].sort((a, b) => a - b)
  const n = sorted.length
  const p50Idx = Math.min(n - 1, Math.ceil(n * 0.50) - 1)
  const p95Idx = Math.min(n - 1, Math.ceil(n * 0.95) - 1)
  const sum = sorted.reduce((a, b) => a + b, 0)
  const trimCount = Math.floor(n * 0.05)
  const trimVals = (trimCount * 2) < n ? sorted.slice(trimCount, n - trimCount) : sorted
  const trimSum = trimVals.reduce((a, b) => a + b, 0)
  return {
    min: formatTime(sorted[0], scale),
    avg: formatTime(Math.round(sum / n), scale),
    trimMean: formatTime(Math.round(trimSum / trimVals.length), scale),
    max: formatTime(sorted[n - 1], scale),
    p50: formatTime(sorted[p50Idx], scale),
    p95: formatTime(sorted[p95Idx], scale),
  }
}

function _execSliceRowsForReport(tr, range) {
  if (!tr || !tr.segByMergeKey) return []
  const scale = tr.timeScale
  const total = range ? (range.hi - range.lo) : (tr.timeMax - tr.timeMin)
  const rows = []

  for (const [mk, segs] of tr.segByMergeKey) {
    if (!segs || segs.length === 0) continue
    const repr = tr.taskRepr.get(mk) || mk
    const { name } = parseTaskName(repr)
    if (isIdleTaskName(name) || name === 'TICK') continue

    const samples = []
    for (const s of segs) {
      const d = s.end - s.start
      if (d <= 0) continue
      if (range && !segFullyInRange(s, range.lo, range.hi)) continue
      samples.push(d)
    }
    const summary = _summarizeSamplesReport(samples, scale)
    if (!summary) continue
    const taskTotal = samples.reduce((a, b) => a + b, 0)

    rows.push({
      mk,
      name: taskDisplayName(repr),
      runs: samples.length,
      cpuPct: total > 0 ? (100.0 * taskTotal / total) : 0,
      min: summary.min,
      avg: summary.avg,
      trimMean: summary.trimMean,
      max: summary.max,
      p50: summary.p50,
      p95: summary.p95,
    })
  }

  return rows.sort((a, b) => b.runs - a.runs || a.name.localeCompare(b.name))
}

function _interArrivalRowsForReport(tr, range) {
  if (!tr || !tr.segByMergeKey) return []
  const scale = tr.timeScale
  const rows = []

  for (const [mk, segs] of tr.segByMergeKey) {
    if (!segs || segs.length < 2) continue
    const repr = tr.taskRepr.get(mk) || mk
    const { name } = parseTaskName(repr)
    if (isIdleTaskName(name) || name === 'TICK') continue

    const starts = [...segs].map(s => s.start).sort((a, b) => a - b)
    const samples = []
    for (let i = 1; i < starts.length; i++) {
      if (range && (starts[i] < range.lo || starts[i] > range.hi)) continue
      const d = starts[i] - starts[i - 1]
      if (d > 0) samples.push(d)
    }
    const summary = _summarizeSamplesReport(samples, scale)
    if (!summary) continue

    const runs = range
      ? segs.filter(s => s.start >= range.lo && s.start <= range.hi).length
      : starts.length

    rows.push({
      mk,
      name: taskDisplayName(repr),
      runs,
      min: summary.min,
      avg: summary.avg,
      trimMean: summary.trimMean,
      max: summary.max,
      p50: summary.p50,
      p95: summary.p95,
    })
  }

  return rows.sort((a, b) => b.runs - a.runs || a.name.localeCompare(b.name))
}

function _blockingRowsForReport(tr, range) {
  if (!tr || !tr.segByMergeKey) return []
  const scale = tr.timeScale
  const lo = range?.lo ?? null
  const hi = range?.hi ?? null
  const rows = []

  for (const [mk, segs] of tr.segByMergeKey) {
    if (!segs || segs.length < 2) continue
    const repr = tr.taskRepr.get(mk) || mk
    const { name } = parseTaskName(repr)
    if (isIdleTaskName(name) || name === 'TICK') continue
    const samples = blockingTimeSamples(segs, lo, hi)
    const summary = _summarizeSamplesReport(samples, scale)
    if (!summary) continue
    rows.push({
      mk,
      name: taskDisplayName(repr),
      runs: samples.length,
      min: summary.min,
      avg: summary.avg,
      trimMean: summary.trimMean,
      max: summary.max,
      p50: summary.p50,
      p95: summary.p95,
    })
  }

  return rows.sort((a, b) => b.runs - a.runs || a.name.localeCompare(b.name))
}

function _renderHtmlTable(title, rows, includeCpu = false) {
  const head = includeCpu
    ? '<tr><th>Task</th><th>Runs</th><th>CPU%</th><th>Min</th><th>Avg</th><th>Max</th><th>p95</th></tr>'
    : '<tr><th>Task</th><th>Runs</th><th>Min</th><th>Avg</th><th>Max</th><th>p95</th></tr>'
  const body = rows.length
    ? rows.map(r => includeCpu
      ? `<tr><td>${_htmlCell(r.name)}</td><td>${_htmlCell(r.runs)}</td><td>${_htmlCell(r.cpuPct.toFixed(1))}%</td><td>${_htmlCell(r.min)}</td><td>${_htmlCell(r.avg)}</td><td>${_htmlCell(r.max)}</td><td>${_htmlCell(r.p95)}</td></tr>`
      : `<tr><td>${_htmlCell(r.name)}</td><td>${_htmlCell(r.runs)}</td><td>${_htmlCell(r.min)}</td><td>${_htmlCell(r.avg)}</td><td>${_htmlCell(r.max)}</td><td>${_htmlCell(r.p95)}</td></tr>`,
    ).join('')
    : `<tr><td colspan="${includeCpu ? 7 : 6}" class="empty">No data</td></tr>`
  return `<section class="report-card"><h2>${_htmlCell(title)}</h2><table><thead>${head}</thead><tbody>${body}</tbody></table></section>`
}

function _renderHtmlTableReport(title, rows, includeCpu = false) {
  const head = includeCpu
    ? '<tr><th>Task</th><th>Runs</th><th>CPU%</th><th>Min</th><th>Avg</th><th>TrimMean(5%)</th><th>Max</th><th>p50</th><th>p95</th></tr>'
    : '<tr><th>Task</th><th>Runs</th><th>Min</th><th>Avg</th><th>TrimMean(5%)</th><th>Max</th><th>p50</th><th>p95</th></tr>'
  const body = rows.length
    ? rows.map(r => includeCpu
      ? `<tr><td>${_htmlCell(r.name)}</td><td>${_htmlCell(r.runs)}</td><td>${_htmlCell(r.cpuPct.toFixed(1))}%</td><td>${_htmlCell(r.min)}</td><td>${_htmlCell(r.avg)}</td><td>${_htmlCell(r.trimMean)}</td><td>${_htmlCell(r.max)}</td><td>${_htmlCell(r.p50)}</td><td>${_htmlCell(r.p95)}</td></tr>`
      : `<tr><td>${_htmlCell(r.name)}</td><td>${_htmlCell(r.runs)}</td><td>${_htmlCell(r.min)}</td><td>${_htmlCell(r.avg)}</td><td>${_htmlCell(r.trimMean)}</td><td>${_htmlCell(r.max)}</td><td>${_htmlCell(r.p50)}</td><td>${_htmlCell(r.p95)}</td></tr>`,
    ).join('')
    : `<tr><td colspan="${includeCpu ? 9 : 8}" class="empty">No data</td></tr>`
  return `<section class="report-card"><h2>${_htmlCell(title)}</h2><table><thead>${head}</thead><tbody>${body}</tbody></table></section>`
}

function _coreUtilRows(tr, range) {
  if (!tr || !tr.coreNames || tr.coreNames.length === 0) return []
  const total = range ? (range.hi - range.lo) : (tr.timeMax - tr.timeMin)
  if (total <= 0) return []
  return tr.coreNames.map(core => {
    const segs = traceMapGet(tr.coreSegs, core) || []
    let active = 0
    for (const s of segs) {
      const { name } = parseTaskName(s.task)
      if (name === 'TICK' || isIdleTaskName(name)) continue
      active += range ? segOverlapNs(s, range.lo, range.hi) : (s.end - s.start)
    }
    return {
      core,
      pct: (100.0 * active / total).toFixed(1),
    }
  })
}

function _taskCpuRows(tr, range) {
  if (!tr || !tr.segByMergeKey) return []
  const total = range ? (range.hi - range.lo) : (tr.timeMax - tr.timeMin)
  if (total <= 0) return []
  const accum = new Map()
  for (const [mk, segs] of traceMapEntries(tr.segByMergeKey)) {
    const repr = taskReprGet(tr, mk) || mk
    const { name } = parseTaskName(repr)
    if (isIdleTaskName(name) || name === 'TICK') continue
    let t = 0
    for (const s of segs) {
      t += range ? segOverlapNs(s, range.lo, range.hi) : (s.end - s.start)
    }
    if (t > 0) accum.set(mk, t)
  }
  return [...accum.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10)
    .map(([mk, t]) => ({
      name: taskDisplayName(taskReprGet(tr, mk) || mk),
      pct: (100.0 * t / total).toFixed(1),
    }))
}

function exportHtml() {
  const tr = props.trace
  const r = statsRange.value
  const suffix = scopeSuffixStr.value
  const execReportRows = _execSliceRowsForReport(tr, r)
  const interReportRows = _interArrivalRowsForReport(tr, r)
  const blockReportRows = _blockingRowsForReport(tr, r)
  const coreRows = _coreUtilRows(tr, r)
  const taskRows = _taskCpuRows(tr, r)
  const lo = r?.lo ?? null
  const hi = r?.hi ?? null
  const migReportRows = migrationRows(tr, lo, hi)
  const preemptHtmlRows = preemptionChainRows(tr, lo, hi)
  const respHtmlRows = responseTimeRows(tr, lo, hi)
  const { contextSwitches, coreGaps } = schedulingStats(tr, lo, hi)
  const schedKpi = schedulingSummary.value
  const range = !r ? rangeStats.value : null
  const rangeHtml = range
    ? `<section class="report-card"><h2>Cursor Range</h2><table><tbody>
        <tr><th>Span</th><td>${_htmlCell(range.span)}</td></tr>
        <tr><th>Slices</th><td>${_htmlCell(range.switches)}</td></tr>
        ${range.topTask ? `<tr><th>Top task</th><td>${_htmlCell(`${range.topTask} (${range.topPct}%)`)}</td></tr>` : ''}
        ${range.dMin ? `<tr><th>Seg min</th><td>${_htmlCell(range.dMin)}</td></tr>` : ''}
        ${range.dAvg ? `<tr><th>Seg avg</th><td>${_htmlCell(range.dAvg)}</td></tr>` : ''}
        ${range.dMax ? `<tr><th>Seg max</th><td>${_htmlCell(range.dMax)}</td></tr>` : ''}
      </tbody></table></section>`
    : ''
  const scopeNote = r
    ? `<li><strong>Cursor range:</strong> ${_htmlCell(scopeRangeLabel.value)}. CPU% uses overlapping active time; slice metrics use segments fully inside the range.</li>`
    : ''
  const coreHtml = `<section class="report-card"><h2>Core Utilisation (excl. IDLE/TICK)${_htmlCell(suffix)}</h2><table><thead><tr><th>Core</th><th>CPU %</th></tr></thead><tbody>${coreRows.length
    ? coreRows.map(r => `<tr><td>${_htmlCell(r.core)}</td><td>${_htmlCell(r.pct)}%</td></tr>`).join('')
    : '<tr><td colspan="2" class="empty">No data</td></tr>'
  }</tbody></table></section>`
  const taskHtml = `<section class="report-card"><h2>Top Tasks by CPU (excl. IDLE/TICK)${_htmlCell(suffix)}</h2><table><thead><tr><th>Task</th><th>CPU %</th></tr></thead><tbody>${taskRows.length
    ? taskRows.map(r => `<tr><td>${_htmlCell(r.name)}</td><td>${_htmlCell(r.pct)}%</td></tr>`).join('')
    : '<tr><td colspan="2" class="empty">No data</td></tr>'
  }</tbody></table></section>`
  const tick = tickHealthReport(tr, lo, hi)
  const tickGapBody = tick.largeGaps.length
    ? tick.largeGaps.map(g => `<tr><td>${_htmlCell(formatTime(g.start, tr.timeScale))}</td><td>${_htmlCell(formatTime(g.end, tr.timeScale))}</td><td>${_htmlCell(formatTime(g.duration, tr.timeScale))}</td><td>${g.missedTicks}</td></tr>`).join('')
    : '<tr><td colspan="4" class="empty">No large gaps</td></tr>'
  const tickHealthHtml = tick.tickCount
    ? `<section class="report-card"><h2>Trace Health (TICK)${_htmlCell(suffix)}</h2><table><tbody>
        <tr><th>Status</th><td>${_htmlCell(tick.health.toUpperCase())}</td></tr>
        <tr><th>Ticks</th><td>${tick.tickCount.toLocaleString()}</td></tr>
        <tr><th>Avg period</th><td>${_htmlCell(formatTime(tick.avgPeriod, tr.timeScale))}</td></tr>
        <tr><th>Max gap</th><td>${_htmlCell(formatTime(tick.maxGap, tr.timeScale))}</td></tr>
        <tr><th>Missed ticks (est.)</th><td>${tick.missedTicksEstimate}</td></tr>
      </tbody></table>
      <h2 style="margin-top:12px;font-size:14px;">Large TICK gaps</h2>
      <table><thead><tr><th>Start</th><th>End</th><th>Gap</th><th>Missed</th></tr></thead><tbody>${tickGapBody}</tbody></table></section>`
    : `<section class="report-card"><h2>Trace Health (TICK)${_htmlCell(suffix)}</h2><p class="empty">No STI TICK events</p></section>`
  const migHtml = `<section class="report-card"><h2>Core Migrations${_htmlCell(suffix)}</h2><table><thead><tr><th>Task</th><th>Migr</th><th>Cores</th><th>Primary</th><th>Ping</th><th>STI±</th><th>Gap after</th><th>Gap other</th></tr></thead><tbody>${migReportRows.length
    ? migReportRows.map(r => `<tr><td>${_htmlCell(r.name)}</td><td>${_htmlCell(r.migrations)}</td><td>${_htmlCell(r.coreCount)}</td><td>${_htmlCell(`${r.primary} (${r.primaryPct.toFixed(0)}%)`)}</td><td>${_htmlCell(r.pingPong)}</td><td>${_htmlCell(r.stiNear)}</td><td>${_htmlCell(r.gapAfter)}</td><td>${_htmlCell(r.gapOther)}</td></tr>`).join('')
    : '<tr><td colspan="8" class="empty">No migrated tasks</td></tr>'
  }</tbody></table></section>`

  const html = `<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>BTF Statistics Report</title>
  <style>
    :root {
      --bg: #e9edf3;
      --paper: #ffffff;
      --ink: #182230;
      --muted: #5f6f82;
      --line: #d9e0ea;
      --line-strong: #c8d2e0;
      --header: #16324f;
      --accent: #2a6fb2;
      --stripe: #f7f9fc;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      padding: 28px;
      font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
      color: var(--ink);
      background: radial-gradient(circle at top right, #f6f8fb 0%, var(--bg) 52%, #dde4ee 100%);
    }
    .report { max-width: 1160px; margin: 0 auto; }
    .report-head {
      background: linear-gradient(135deg, var(--header) 0%, #21496f 100%);
      color: #f3f7fd;
      border-radius: 14px;
      padding: 20px 24px;
      box-shadow: 0 10px 28px rgba(17, 44, 69, 0.24);
      margin-bottom: 18px;
    }
    h1 { margin: 0; font-size: 28px; letter-spacing: 0.2px; }
    .sub { margin-top: 6px; color: #cfe1f7; font-size: 13px; }
    .kpi-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
      gap: 10px;
      margin-bottom: 16px;
    }
    .kpi {
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 12px 14px;
      box-shadow: 0 2px 8px rgba(30, 60, 90, 0.06);
    }
    .kpi .k { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.6px; }
    .kpi .v { margin-top: 4px; font-size: 20px; font-weight: 700; color: #0f2b47; }
    .report-card {
      margin: 14px 0;
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 12px 14px 14px;
      box-shadow: 0 2px 10px rgba(30, 60, 90, 0.06);
    }
    h2 { margin: 0 0 10px 0; color: #123355; font-size: 17px; }
    .notes { border-left: 4px solid var(--accent); }
    .notes ul { margin: 8px 0 0 18px; padding: 0; }
    .notes li { margin: 6px 0; line-height: 1.45; }
    table { border-collapse: separate; border-spacing: 0; width: 100%; }
    th, td { border-bottom: 1px solid var(--line); padding: 8px 10px; font-size: 13px; text-align: right; }
    th:first-child, td:first-child { text-align: left; }
    thead th {
      background: #f1f5fb;
      color: #284563;
      font-weight: 600;
      border-top: 1px solid var(--line-strong);
      border-bottom: 1px solid var(--line-strong);
    }
    tbody tr:nth-child(even) td { background: var(--stripe); }
    .empty { text-align: center !important; color: var(--muted); }
    .report-foot { margin-top: 14px; color: var(--muted); font-size: 12px; text-align: right; }
  </style>
</head>
<body>
  <div class="report">
    <header class="report-head">
      <h1>BTF Statistics Report</h1>
      <div class="sub">Generated: ${_htmlCell(new Date().toLocaleString())}</div>
    </header>
    <section class="kpi-grid">
      <article class="kpi"><div class="k">Span${_htmlCell(suffix)}</div><div class="v">${_htmlCell(spanStr.value)}</div></article>
      <article class="kpi"><div class="k">Tasks</div><div class="v">${_htmlCell(summaryTaskCount.value.toLocaleString())}</div></article>
      <article class="kpi"><div class="k">Segments</div><div class="v">${_htmlCell(summarySegCount.value.toLocaleString())}</div></article>
      <article class="kpi"><div class="k">STI Events</div><div class="v">${_htmlCell(summaryStiCount.value.toLocaleString())}</div></article>
      ${schedKpi ? `<article class="kpi"><div class="k">Context switches${_htmlCell(suffix)}</div><div class="v">${_htmlCell(schedKpi.contextSwitches.toLocaleString())}</div></article>` : ''}
      ${schedKpi?.gapAvg ? `<article class="kpi"><div class="k">Core gap avg${_htmlCell(suffix)}</div><div class="v">${_htmlCell(schedKpi.gapAvg)}</div></article>` : ''}
      ${schedKpi?.gapMax ? `<article class="kpi"><div class="k">Core gap max${_htmlCell(suffix)}</div><div class="v">${_htmlCell(schedKpi.gapMax)}</div></article>` : ''}
    </section>
    <section class="report-card notes">
    <h2>Statistics Notes</h2>
    <ul>
      ${scopeNote}
      <li><strong>Execution Time Per Slice:</strong> Duration of each continuous task run between two context switches. Lower and tighter values indicate more predictable execution.</li>
      <li><strong>Inter-Arrival Time:</strong> Time between consecutive activations of the same task (slice start to next slice start). It reflects activation cadence and jitter.</li>
      <li><strong>Blocking Time:</strong> Off-CPU gap between the end of one slice and the start of the next for the same task.</li>
      <li><strong>Preemption Chain Analysis:</strong> For each blocking gap of a victim task, identifies which task ran on the same core during that gap. High counts or long totals point to recurring preemption bottlenecks.</li>
      <li><strong>Response Time Analysis:</strong> Time from the end of a task slice to the start of its next slice (= off-CPU blocking gap). Max and p95 values indicate worst-case scheduling latency for that task.</li>
      <li><strong>Context switches:</strong> Count of segment boundaries on all cores whose start time falls inside the statistics scope.</li>
      <li><strong>Min (Minimum):</strong> The fastest execution time recorded. It represents the best-case scenario under zero system load.</li>
      <li><strong>Max (Maximum):</strong> The slowest execution time recorded. It identifies worst-case bottlenecks, spikes, or resource contention.</li>
      <li><strong>Average (Mean):</strong> Total execution time divided by the number of slices. It shows general performance but is heavily skewed by extreme outliers.</li>
      <li><strong>TrimMean(5%):</strong> Average after removing the fastest 5% and slowest 5% slices. It reflects typical performance while reducing outlier impact.</li>
      <li><strong>P50 (Median):</strong> The midpoint latency where half of slices are faster and half are slower. It captures typical-case behaviour.</li>
      <li><strong>P95 (95th Percentile):</strong> The threshold under which 95% of all slices execute. It is the best metric for user experience because it ignores rare anomalies while capturing real-world slowdowns.</li>
    </ul>
    </section>
    ${rangeHtml}
    ${coreHtml}
    ${taskHtml}
    ${tickHealthHtml}
    ${migHtml}
    ${_renderHtmlTableReport(`Execution Time Per Slice${suffix}`, execReportRows, true)}
    ${_renderHtmlTableReport(`Blocking Time (off-CPU gap)${suffix}`, blockReportRows)}
    ${_renderHtmlTableReport(`Inter-Arrival Time${suffix}`, interReportRows)}
    <section class="report-card"><h2>Preemption Chain Analysis${_htmlCell(suffix)}</h2>
    <table><thead><tr><th>Victim</th><th>Preemptor</th><th>Count</th><th>Total</th><th>Avg</th><th>Max</th></tr></thead>
    <tbody>${preemptHtmlRows.length
      ? preemptHtmlRows.map(row =>
          `<tr><td>${_htmlCell(row.victim)}</td><td>${_htmlCell(row.preemptor)}</td><td>${row.count}</td><td>${_htmlCell(row.total)}</td><td>${_htmlCell(row.avg)}</td><td>${_htmlCell(row.max)}</td></tr>`
        ).join('')
      : '<tr><td colspan="6" class="empty">No preemption events found</td></tr>'
    }</tbody></table></section>
    <section class="report-card"><h2>Response Time Analysis${_htmlCell(suffix)}</h2>
    <table><thead><tr><th>Task</th><th>Events</th><th>Min</th><th>Avg</th><th>Max</th><th>p95</th></tr></thead>
    <tbody>${respHtmlRows.length
      ? respHtmlRows.map(row =>
          `<tr><td>${_htmlCell(row.name)}</td><td>${row.count}</td><td>${_htmlCell(row.min)}</td><td>${_htmlCell(row.avg)}</td><td>${_htmlCell(row.max)}</td><td>${_htmlCell(row.p95)}</td></tr>`
        ).join('')
      : '<tr><td colspan="6" class="empty">No data</td></tr>'
    }</tbody></table></section>
    <div class="report-foot">Generated by BTF Viewer</div>
  </div>
</body>
</html>`

  _downloadText(`statistics-${_stamp()}.html`, html, 'text/html;charset=utf-8')
}

// ---- Range statistics (from 2+ cursor positions) -----------------------
// Computed via a debounced watcher so cursor placement never blocks the UI.
const rangeStats = ref(null)
let _rangeTimer = null

function _computeRangeStats(cursors) {
  const placed = cursors.filter(c => c !== null)
  if (placed.length < 2) return null
  const sorted = [...placed].sort((a, b) => a - b)
  const lo = sorted[0]
  const hi = sorted[sorted.length - 1]
  const dt = hi - lo
  if (dt <= 0) return null

  const scale = props.trace.timeScale
  const taskAcc = new Map()
  const durations = []
  let switches = 0

  for (const seg of props.trace.segments) {
    if (seg.end <= lo || seg.start >= hi) continue
    const ov = Math.min(seg.end, hi) - Math.max(seg.start, lo)
    if (ov <= 0) continue
    switches++
    durations.push(seg.end - seg.start)
    const mk = taskMergeKey(seg.task)
    const repr = props.trace.taskRepr.get(mk) || seg.task
    const disp = taskDisplayName(repr)
    taskAcc.set(disp, (taskAcc.get(disp) || 0) + ov)
  }

  let topTask = null, topNs = 0
  for (const [k, v] of taskAcc) {
    if (v > topNs) { topNs = v; topTask = k }
  }

  const result = {
    span:     formatTime(dt, scale),
    switches,
    topTask,
    topPct:   topTask ? (100.0 * topNs / dt).toFixed(1) : null,
  }

  if (durations.length > 0) {
    const minD = minNs(durations)
    const maxD = maxNs(durations)
    const avgD = Math.round(durations.reduce((a, b) => a + b, 0) / durations.length)
    result.dMin = formatTime(minD, scale)
    result.dMax = formatTime(maxD, scale)
    result.dAvg = formatTime(avgD, scale)
  }
  return result
}

watch(() => props.cursors, (cursors) => {
  clearTimeout(_rangeTimer)
  if (!scopeToCursors.value) {
    rangeStats.value = null
    return
  }
  const placed = cursors.filter(c => c !== null)
  if (placed.length < 2) {
    rangeStats.value = null
    return
  }
  // Defer heavy segment scan so cursor placement feels instant
  _rangeTimer = setTimeout(() => {
    rangeStats.value = _computeRangeStats(cursors)
  }, 200)
}, { deep: true })

watch(() => props.trace, () => {
  closePlot()
  scheduleStatsRefresh()
}, { immediate: true })

watch(
  [statsRange, execSliceCollapsed, blockingCollapsed, interArrivalCollapsed, scopeToCursors],
  scheduleStatsRefresh,
  { immediate: true },
)

watch(plotData, () => {
  selectedPlotPoint.value = -1
})
</script>

<style scoped>
.stats-panel {
  display: flex;
  flex-direction: column;
  padding: 8px 10px;
  font-size: 11px;
  font-family: monospace;
  overflow-y: auto;
  flex: 1;
  min-height: 0;
  gap: 0;
}

.stats-scope-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 8px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--border);
}

.stats-scope-top {
  display: flex;
  align-items: center;
  gap: 8px;
}

.stats-scope-actions {
  display: flex;
  gap: 2px;
  margin-left: auto;
  flex-shrink: 0;
}

.stats-icon-btn {
  appearance: none;
  border: none;
  background: transparent;
  color: var(--fg-dim);
  padding: 2px 4px;
  border-radius: 3px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.stats-icon-btn:hover,
.stats-icon-btn:focus-visible {
  background: var(--tb-btn-hover);
  color: var(--fg);
  outline: none;
}

.stats-scope-check {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--fg);
  font-size: 10px;
  cursor: pointer;
  user-select: none;
}

.stats-scope-check input:disabled {
  cursor: not-allowed;
  opacity: 0.45;
}

.stats-scope-label {
  color: var(--fg-dim);
  font-size: 10px;
  line-height: 1.35;
  word-break: break-word;
}

.stats-summary {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.summary-row {
  display: flex;
  justify-content: space-between;
  gap: 4px;
}

.summary-key {
  color: var(--fg-dim);
  flex-shrink: 0;
}

.summary-val {
  color: var(--fg);
  text-align: right;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.stats-sep {
  height: 1px;
  background: var(--border);
  margin: 6px 0;
  flex-shrink: 0;
}

.stats-section-title {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--fg-dim);
  margin-bottom: 4px;
}

.stats-section-title.collapsible {
  cursor: pointer;
  user-select: none;
}

.stats-section-title.collapsible:hover {
  color: var(--fg);
}

.chevron {
  flex-shrink: 0;
  transition: transform 0.15s;
  color: var(--fg-dim);
}

.chevron.collapsed {
  transform: rotate(-90deg);
}

.range-hint {
  color: var(--fg-dim);
  opacity: 0.6;
  font-size: 10px;
  font-style: italic;
}

.health-banner {
  font-size: 11px;
  padding: 4px 0 2px;
  font-weight: 500;
}
.health-banner.health-good { color: #5FCF6F; }
.health-banner.health-warning { color: #E8C84A; }
.health-banner.health-critical { color: #E85D5D; }
.health-banner.health-unknown { color: var(--fg-dim); }

.stats-util-scroll {
  display: flex;
  flex-direction: column;
  gap: 3px;
  flex-shrink: 0;
  width: 100%;
  box-sizing: border-box;
}

.core-stat-row,
.task-stat-row {
  display: flex;
  align-items: center;
  gap: 5px;
  height: 16px;
  min-height: 16px;
  max-height: 16px;
  margin-bottom: 0;
  flex-shrink: 0;
}

.core-name {
  color: var(--fg-dim);
  min-width: 56px;
  flex-shrink: 0;
}

.task-stat-name {
  color: var(--fg);
  min-width: 0;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.task-link {
  appearance: none;
  background: transparent;
  border: none;
  cursor: pointer;
  font: inherit;
  padding: 0;
  text-align: left;
}

.task-link:hover,
.task-link:focus-visible {
  color: var(--accent);
  outline: none;
}

.prog-bar {
  flex: 1;
  height: 8px;
  border-radius: 4px;
  background: var(--border);
  overflow: hidden;
  flex-shrink: 0;
  min-width: 30px;
}

.prog-fill {
  height: 100%;
  background: #5FCF6F;
  border-radius: 4px;
  transition: width 0.2s;
}

.prog-fill.task-fill {
  background: #5B9BD5;
}

.core-pct {
  color: #77BB77;
  min-width: 38px;
  text-align: right;
  flex-shrink: 0;
}

.task-stat-pct {
  color: #6AAADD;
  min-width: 38px;
  text-align: right;
  flex-shrink: 0;
}

.stats-table-block {
  display: flex;
  flex-direction: column;
}

.stats-table-wrap {
  border: 1px solid var(--border);
  border-radius: 6px;
  overflow: auto;
}

.stats-section-resizer {
  height: 6px;
  flex-shrink: 0;
  cursor: row-resize;
  position: relative;
  margin-top: 2px;
}

.stats-section-resizer::before {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  top: 2px;
  height: 2px;
  background: transparent;
  transition: background 0.12s ease;
}

.stats-section-resizer:hover::before {
  background: color-mix(in srgb, var(--accent) 50%, var(--border));
}

.stats-table-migration {
  min-width: 520px;
}

.stats-table-preemption {
  min-width: 380px;
}

.stats-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 10px;
}

.stats-table th,
.stats-table td {
  padding: 3px 5px;
  border-bottom: 1px solid var(--border);
  text-align: right;
  white-space: nowrap;
  line-height: 14px;
  box-sizing: border-box;
}

.stats-table th {
  position: sticky;
  top: 0;
  background: var(--panel-bg);
  color: var(--fg-dim);
  font-weight: 600;
  z-index: 1;
}

.stats-table th.sortable {
  cursor: pointer;
  user-select: none;
}

.stats-table th.sortable:hover {
  color: var(--fg);
}

.stats-table th.sort-asc::after,
.stats-table th.sort-desc::after {
  font-size: 8px;
  opacity: 0.85;
}

.stats-table th.sort-asc::after {
  content: ' ▲';
}

.stats-table th.sort-desc::after {
  content: ' ▼';
}

.stats-table th:first-child,
.stats-table td.task-col {
  text-align: left;
}

.stats-table td.task-col {
  max-width: 140px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.stats-table tr:last-child td {
  border-bottom: none;
}

.stats-table-row.clickable {
  cursor: pointer;
}

.stats-table-row.clickable:hover td,
.stats-table-row.clickable:focus-visible td {
  background: var(--tb-btn-hover);
}

.stats-table-row.clickable:focus-visible {
  outline: none;
}

.stats-table td.extreme-col,
.stats-table td.wcet-col {
  color: var(--accent);
  cursor: pointer;
  text-decoration: underline;
  text-decoration-style: dotted;
  text-underline-offset: 2px;
}

.stats-table td.extreme-col:hover,
.stats-table td.wcet-col:hover {
  color: var(--fg);
}

.stats-export-row {
  display: flex;
  gap: 4px;
  padding: 6px 8px;
  border-top: 1px solid var(--border);
}

.action-btn {
  flex: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  padding: 3px 8px;
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 4px;
  color: var(--fg-dim);
  font-size: 11px;
  cursor: pointer;
}

.action-btn .export-icon {
  flex-shrink: 0;
  opacity: 0.9;
}

.action-btn:hover {
  background: var(--tb-btn-hover);
  color: var(--fg);
}

.plot-dialog-overlay {
  position: fixed;
  inset: 0;
  z-index: 500;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.52);
  backdrop-filter: blur(2px);
}

.plot-dialog {
  width: min(900px, calc(100vw - 32px));
  max-height: min(86vh, 760px);
  display: flex;
  flex-direction: column;
  background: var(--panel-bg);
  border: 1px solid var(--border);
  border-radius: 12px;
  box-shadow: 0 16px 40px rgba(0, 0, 0, 0.45);
  overflow: hidden;
}

.plot-dialog-header,
.plot-dialog-footer {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 14px;
}

.plot-dialog-header {
  justify-content: space-between;
  border-bottom: 1px solid var(--border);
}

.plot-dialog-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--fg);
}

.plot-close-btn {
  border: 1px solid var(--border);
  background: transparent;
  color: var(--fg);
  border-radius: 6px;
  padding: 6px 10px;
  cursor: pointer;
}

.plot-close-btn:hover {
  background: var(--tb-btn-hover);
}

.plot-scope-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  font-size: 11px;
  line-height: 1.35;
}

.plot-scope-cursor {
  background: color-mix(in srgb, #ff9800 18%, var(--panel-bg));
  border-bottom: 1px solid color-mix(in srgb, #ff9800 45%, var(--border));
  border-left: 4px solid #ff9800;
}

.plot-scope-full {
  background: color-mix(in srgb, var(--fg-dim) 10%, var(--panel-bg));
  border-bottom: 1px solid var(--border);
  border-left: 4px solid var(--fg-dim);
}

.plot-scope-badge {
  flex-shrink: 0;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  font-size: 10px;
  padding: 3px 8px;
  border-radius: 4px;
}

.plot-scope-cursor .plot-scope-badge {
  background: #ff9800;
  color: #1a1200;
}

.plot-scope-full .plot-scope-badge {
  background: var(--border);
  color: var(--fg);
}

.plot-scope-detail {
  color: var(--fg);
}

.plot-scope-full .plot-scope-detail {
  color: var(--fg-dim);
}

.plot-dialog-body {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px 14px;
  overflow: auto;
}

.plot-card {
  border: 1px solid var(--border);
  border-radius: 10px;
  background: color-mix(in srgb, var(--panel-bg) 70%, var(--bg));
  overflow: hidden;
}

.plot-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 160px;
  padding: 24px 16px;
  color: var(--fg-dim);
  font-size: 12px;
  font-style: italic;
  text-align: center;
}

.plot-card-histogram .plot-empty {
  min-height: 120px;
}

.plot-svg {
  display: block;
  width: 100%;
  height: auto;
}

.plot-point:hover {
  filter: brightness(1.18);
}

.plot-axis-text,
.plot-ref-text {
  font-size: 11px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}

.plot-dialog-footer {
  justify-content: flex-end;
  border-top: 1px solid var(--border);
}

@media (max-width: 720px) {
  .plot-dialog {
    width: calc(100vw - 16px);
    max-height: calc(100vh - 16px);
  }

  .plot-dialog-header,
  .plot-dialog-footer,
  .plot-dialog-body {
    padding: 10px;
  }
}
</style>
