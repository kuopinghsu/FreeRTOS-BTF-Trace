<template>
  <div
    class="stats-panel"
  >
    <!-- Cursor range scope -->
    <div class="stats-scope-row">
      <div class="stats-scope-top">
        <label
          class="stats-scope-check"
          title="Limit statistics to the time window from C1 through the last cursor"
        >
          <input
            v-model="scopeToCursorsModel"
            type="checkbox"
            :disabled="placedCursorCount < 2"
          >
          Limit to C1–Cn
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
          <button
            type="button"
            class="stats-icon-btn"
            :disabled="!sectionOrderIsCustom"
            :title="sectionOrderIsCustom ? 'Reset statistics section order to default' : 'Section order is already the default'"
            aria-label="Reset statistics section order to default"
            @click="resetSectionOrder"
          >
            <svg viewBox="0 0 16 16" width="14" height="14" fill="currentColor" aria-hidden="true">
              <path d="M8 1.25A6.75 6.75 0 1 0 14.75 8h-1.5A5.25 5.25 0 1 1 8 2.75V5.5L12 3 8 .5v.75z" />
            </svg>
          </button>
        </div>
      </div>
      <span class="stats-scope-label">{{ scopeRangeLabel }}</span>
      <span
        v-if="activeFilterLabel"
        class="stats-scope-filtered"
        :title="`Statistics reflect the active Filter: ${activeFilterLabel}`"
      >Filtered: {{ activeFilterLabel }}</span>
    </div>

    <div
      ref="statsBodyRef"
      class="stats-body"
    >
    <!-- Summary and sections (require loaded trace) -->
    <template v-if="trace">
    <div
      class="stats-summary"
      data-demo-target="stats_summary"
    >
      <div class="summary-line">
        Span: {{ spanStr }}{{ scopeSuffixStr }} | Tasks: {{ summaryTaskCount.toLocaleString() }}
      </div>
      <div class="summary-line">
        Segments: {{ summarySegCount.toLocaleString() }} | STI events: {{ summaryStiCount.toLocaleString() }}
      </div>
      <template v-if="schedulingSummary">
        <div class="stats-sep summary-sep" />
        <div class="summary-line">
          Context switches: {{ schedulingSummary.contextSwitches.toLocaleString() }}{{ scopeSuffixStr }}
          <template v-if="schedulingSummary.hasGaps">
            | Core gap avg: {{ schedulingSummary.gapAvg }} | max: {{ schedulingSummary.gapMax }}
          </template>
        </div>
      </template>
    </div>
    <div class="stats-sep" />

    <div class="stats-sections-stack">
    <StatsSectionBlock
      v-if="trace?.coreNames?.length > 0"
      :section-id="'cores'"
      :order="sectionOrderIndex('cores')"
      @reorder="onSectionReorder"
    >
      <!-- Core utilization -->
      <StatsSectionHeader
        :section-id="'cores'"
        :collapsed="coresCollapsed"
        :pinned="isSectionPinned('cores')"
        @toggle="toggleSectionCollapse('cores')"
        @toggle-pin="toggleSectionPin('cores')"
      >
        Core Utilisation (excl. IDLE/TICK){{ scopeSuffixStr }}
      </StatsSectionHeader>
      <template v-if="!coresCollapsed">
        <div
          class="stats-util-scroll"
          :style="utilScrollStyle(coreStats.length, 'cores')"
        >
          <LoadBalanceGauge
            v-if="loadBalanceScore"
            :score="loadBalanceScore.score"
            :gini="loadBalanceScore.gini"
            :stddev="loadBalanceScore.stddev"
            :amber="loadBalanceScore.amber"
            :zone="loadBalanceScore.zone"
          />
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
        <div
          class="stats-section-resizer"
          role="separator"
          aria-label="Resize core utilisation"
          @mousedown="onTableResizeStart('cores', $event, coreStats.length)"
        />
      </template>

    </StatsSectionBlock>
    <StatsSectionBlock
      :section-id="'core_breakdown'"
      :order="sectionOrderIndex('core_breakdown')"
      @reorder="onSectionReorder"
    >
      <!-- Core time breakdown -->
      <StatsSectionHeader
        :section-id="'core_breakdown'"
        :collapsed="coreBreakdownCollapsed"
        :pinned="isSectionPinned('core_breakdown')"
        @toggle="toggleSectionCollapse('core_breakdown')"
        @toggle-pin="toggleSectionPin('core_breakdown')"
      >
        Core Time Breakdown{{ scopeSuffixStr }}
      </StatsSectionHeader>
      <template v-if="!coreBreakdownCollapsed">
        <div
          v-if="coreTimeBreakdown.length === 0"
          class="range-hint"
        >
          No core segments
        </div>
        <div
          v-else
          class="stats-table-block"
        >
          <div class="stats-table-wrap" :style="{ maxHeight: tableHeight('core_breakdown') + 'px' }">
            <table class="stats-table">
              <thead>
                <tr>
                  <th :class="thSortClass('core_breakdown', 'core')" @click="toggleTableSort('core_breakdown', 'core')">Core</th>
                  <th :class="thSortClass('core_breakdown', 'active')" @click="toggleTableSort('core_breakdown', 'active')">Active %</th>
                  <th :class="thSortClass('core_breakdown', 'idle')" @click="toggleTableSort('core_breakdown', 'idle')">Idle %</th>
                  <th :class="thSortClass('core_breakdown', 'tick')" @click="toggleTableSort('core_breakdown', 'tick')">Tick %</th>
                  <th :class="thSortClass('core_breakdown', 'gap')" @click="toggleTableSort('core_breakdown', 'gap')">Gap %</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="row in sortedCoreTimeBreakdown"
                  :key="row.core"
                  class="stats-table-row clickable"
                  :title="`Switch to Core View and expand ${row.core}`"
                  tabindex="0"
                  @click="emit('highlightTask', row.core)"
                  @keydown.enter.prevent="emit('highlightTask', row.core)"
                  @keydown.space.prevent="emit('highlightTask', row.core)"
                >
                  <td class="task-col">{{ row.core }}</td>
                  <td>{{ (100 * row.activeNs / row.spanNs).toFixed(1) }}%</td>
                  <td>{{ (100 * row.idleNs / row.spanNs).toFixed(1) }}%</td>
                  <td>{{ (100 * row.tickNs / row.spanNs).toFixed(1) }}%</td>
                  <td>{{ (100 * row.gapNs / row.spanNs).toFixed(1) }}%</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div
            class="stats-section-resizer"
            role="separator"
            aria-label="Resize core time breakdown table"
            aria-orientation="horizontal"
            @mousedown.prevent="onTableResizeStart('core_breakdown', $event)"
          />
        </div>
      </template>

    </StatsSectionBlock>
    <StatsSectionBlock
      v-if="(trace?.coreNames?.length > 0) || concurrentCoreStats.length"
      :section-id="'concurrency'"
      :order="sectionOrderIndex('concurrency')"
      @reorder="onSectionReorder"
    >
      <!-- Concurrent core active distribution -->
      <StatsSectionHeader
        :section-id="'concurrency'"
        :collapsed="concurrencyCollapsed"
        :pinned="isSectionPinned('concurrency')"
        @toggle="toggleSectionCollapse('concurrency')"
        @toggle-pin="toggleSectionPin('concurrency')"
      >
        Concurrent Core Active Distribution{{ scopeSuffixStr }}
      </StatsSectionHeader>
      <template v-if="!concurrencyCollapsed">
        <div
          v-if="concurrentCoreStats.length === 0"
          class="range-hint"
        >
          No active core intervals
        </div>
        <div
          v-else
          class="stats-table-block"
        >
          <div class="stats-table-wrap" :style="{ maxHeight: tableHeight('concurrency') + 'px' }">
            <table class="stats-table">
              <thead>
                <tr>
                  <th :class="thSortClass('concurrency', 'activeCores')" @click="toggleTableSort('concurrency', 'activeCores')">Active Cores</th>
                  <th :class="thSortClass('concurrency', 'duration')" @click="toggleTableSort('concurrency', 'duration')">Duration</th>
                  <th :class="thSortClass('concurrency', 'pct')" @click="toggleTableSort('concurrency', 'pct')">% of Span</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="row in sortedConcurrentCoreStats"
                  :key="row.activeCores"
                  class="stats-table-row clickable"
                  :title="`Open interval-duration plot for ${row.activeCores} active core(s)`"
                  tabindex="0"
                  @click="openConcurrencyPlot(row.activeCores)"
                  @keydown.enter.prevent="openConcurrencyPlot(row.activeCores)"
                  @keydown.space.prevent="openConcurrencyPlot(row.activeCores)"
                >
                  <td class="task-col">{{ row.activeCores }}</td>
                  <td>{{ row.duration }}</td>
                  <td>{{ row.pctOfSpan.toFixed(1) }}%</td>
                  <td>
                    <div class="prog-bar">
                      <div
                        class="prog-fill"
                        :style="{ width: clampPct(row.pctOfSpan) + '%' }"
                      />
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <div
            class="stats-section-resizer"
            role="separator"
            aria-label="Resize concurrent core active table"
            aria-orientation="horizontal"
            @mousedown.prevent="onTableResizeStart('concurrency', $event)"
          />
        </div>
      </template>

    </StatsSectionBlock>
    <StatsSectionBlock
      v-if="(trace?.coreNames?.length > 0) || switchOverheadStats.length"
      :section-id="'switch_overhead'"
      :order="sectionOrderIndex('switch_overhead')"
      @reorder="onSectionReorder"
    >
      <!-- Kernel switch overhead -->
      <StatsSectionHeader
        :section-id="'switch_overhead'"
        :collapsed="switchOverheadCollapsed"
        :pinned="isSectionPinned('switch_overhead')"
        @toggle="toggleSectionCollapse('switch_overhead')"
        @toggle-pin="toggleSectionPin('switch_overhead')"
      >
        Kernel Switch Overhead{{ scopeSuffixStr }}
      </StatsSectionHeader>
      <template v-if="!switchOverheadCollapsed">
        <div
          v-if="switchOverheadStats.length === 0"
          class="range-hint"
        >
          No context switches
        </div>
        <div
          v-else
          class="stats-table-block"
        >
          <div class="stats-table-wrap" :style="{ maxHeight: tableHeight('switch_overhead') + 'px' }">
            <table class="stats-table">
              <thead>
                <tr>
                  <th :class="thSortClass('switch_overhead', 'core')" @click="toggleTableSort('switch_overhead', 'core')">Core</th>
                  <th :class="thSortClass('switch_overhead', 'switches')" @click="toggleTableSort('switch_overhead', 'switches')">Switches</th>
                  <th :class="thSortClass('switch_overhead', 'min')" @click="toggleTableSort('switch_overhead', 'min')">Min</th>
                  <th :class="thSortClass('switch_overhead', 'avg')" @click="toggleTableSort('switch_overhead', 'avg')">Avg</th>
                  <th :class="thSortClass('switch_overhead', 'max')" @click="toggleTableSort('switch_overhead', 'max')">Max</th>
                  <th :class="thSortClass('switch_overhead', 'total')" @click="toggleTableSort('switch_overhead', 'total')">Total Overhead</th>
                  <th :class="thSortClass('switch_overhead', 'pct')" @click="toggleTableSort('switch_overhead', 'pct')">% of Core</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="row in sortedSwitchOverheadStats"
                  :key="row.core"
                  class="stats-table-row clickable"
                  :title="`Open switch-overhead plot for ${row.core}`"
                  tabindex="0"
                  @click="openSwitchOverheadPlot(row.core)"
                  @keydown.enter.prevent="openSwitchOverheadPlot(row.core)"
                  @keydown.space.prevent="openSwitchOverheadPlot(row.core)"
                >
                  <td class="task-col">{{ row.core }}</td>
                  <td>{{ row.switches }}</td>
                  <td>{{ row.min }}</td>
                  <td>{{ row.avg }}</td>
                  <td>{{ row.max }}</td>
                  <td>{{ row.total }}</td>
                  <td>{{ row.pctOfCore.toFixed(2) }}%</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div
            class="stats-section-resizer"
            role="separator"
            aria-label="Resize kernel switch overhead table"
            aria-orientation="horizontal"
            @mousedown.prevent="onTableResizeStart('switch_overhead', $event)"
          />
        </div>
      </template>

    </StatsSectionBlock>
    <StatsSectionBlock
      :section-id="'tasks'"
      :order="sectionOrderIndex('tasks')"
      @reorder="onSectionReorder"
    >
      <!-- Top tasks -->
      <StatsSectionHeader
        :section-id="'tasks'"
        :collapsed="tasksCollapsed"
        :pinned="isSectionPinned('tasks')"
        @toggle="toggleSectionCollapse('tasks')"
        @toggle-pin="toggleSectionPin('tasks')"
      >
        Top Tasks by CPU (excl. IDLE/TICK){{ scopeSuffixStr }}
      </StatsSectionHeader>
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
          :style="utilScrollStyle(topTasks.length, 'tasks')"
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
        <div
          v-if="topTasks.length > 0"
          class="stats-section-resizer"
          role="separator"
          aria-label="Resize top tasks"
          @mousedown="onTableResizeStart('tasks', $event, topTasks.length)"
        />
      </template>

    </StatsSectionBlock>
    <StatsSectionBlock
      :section-id="'health'"
      :order="sectionOrderIndex('health')"
      @reorder="onSectionReorder"
    >
      <!-- Trace health (TICK) -->
      <StatsSectionHeader
        :section-id="'health'"
        demo-target="stats_health"
        :collapsed="healthCollapsed"
        :pinned="isSectionPinned('health')"
        @toggle="toggleSectionCollapse('health')"
        @toggle-pin="toggleSectionPin('health')"
      >
        Trace Health (TICK){{ scopeSuffixStr }}
      </StatsSectionHeader>
      <template v-if="!healthCollapsed">
        <div
          v-if="!tickHealth.tickCount"
          class="range-hint"
        >
          No STI TICK events
        </div>
        <template v-else>
          <div class="health-banner-row">
            <div
              class="health-banner"
              :class="'health-' + tickHealth.health"
            >
              {{ tickHealth.health.toUpperCase() }}
              · <span
                class="tick-mode-badge"
                :class="tickHealth.isTickless ? 'tick-mode-tickless' : 'tick-mode-tick'"
                :title="tickHealth.isTickless
                  ? `Tickless mode detected (interval CV=${(tickHealth.tickCv * 100).toFixed(1)}%): tick intervals vary because the scheduler suppresses ticks during idle periods.`
                  : `Tick mode detected (interval CV=${(tickHealth.tickCv * 100).toFixed(1)}%): tick intervals are constant.`"
              >{{ tickHealth.isTickless ? 'TICKLESS' : 'TICK' }}</span>
              · {{ tickHealth.tickCount.toLocaleString() }} ticks
              · avg {{ fmtTime(tickHealth.avgPeriod) }}
              · max gap {{ fmtTime(tickHealth.maxGap) }}
            </div>
            <button
              v-if="tickHealth.tickCount >= 2"
              type="button"
              class="tick-dist-btn"
              data-demo-target="stats_tick_dist"
              title="Open tick interval distribution chart"
              @click="openTickDistPlot"
            >
              <svg
                class="tick-dist-icon"
                viewBox="0 0 16 16"
                width="14"
                height="14"
                aria-hidden="true"
              >
                <path
                  fill="currentColor"
                  d="M1.5 12.5h2.5V8H1.5v4.5zm3.5 0H7.5V5H5v7.5zm3.5 0h2.5V2H8.5v10.5zm3.5 0H14v-5h-2.5v5.5z"
                />
              </svg>
              <span>Tick Distribution…</span>
            </button>
          </div>
          <div
            v-if="tickHealth.isTickless"
            class="range-hint"
          >
            Tickless mode: tick intervals vary.
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
            class="stats-table-block"
          >
            <div
              class="stats-table-wrap"
              :style="{ maxHeight: tableHeight('health') + 'px' }"
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
            <div
              class="stats-section-resizer"
              role="separator"
              aria-label="Resize trace health gap table"
              aria-orientation="horizontal"
              @mousedown.prevent="onTableResizeStart('health', $event)"
            />
          </div>
        </template>
      </template>

    </StatsSectionBlock>
    <StatsSectionBlock
      :section-id="'migrations'"
      :order="sectionOrderIndex('migrations')"
      @reorder="onSectionReorder"
    >
      <!-- Core migrations -->
      <StatsSectionHeader
        :section-id="'migrations'"
        :collapsed="migrationCollapsed"
        :pinned="isSectionPinned('migrations')"
        @toggle="toggleSectionCollapse('migrations')"
        @toggle-pin="toggleSectionPin('migrations')"
      >
        Core Migrations{{ scopeSuffixStr }}
      </StatsSectionHeader>
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
                  :class="thSortClass('migrations', 'rate')"
                  @click="toggleTableSort('migrations', 'rate')"
                  title="Migrations per second of on-CPU time (and per on-CPU tick when TICK events exist)"
                >
                  Rate
                </th>
                <th
                  :class="thSortClass('migrations', 'dwell')"
                  @click="toggleTableSort('migrations', 'dwell')"
                  title="Average on-core run time before block, yield, or migration"
                >
                  Dwell
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
                :title="`Click to view migration dwell/rate/gap distribution for ${row.name}`"
                tabindex="0"
                @click="openTaskPlot(row.mk, 'mig_dwell')"
                @keydown.enter.prevent="openTaskPlot(row.mk, 'mig_dwell')"
                @keydown.space.prevent="openTaskPlot(row.mk, 'mig_dwell')"
              >
                <td class="task-col">{{ row.name }}</td>
                <td>{{ row.migrations }}</td>
                <td>{{ row.migrRate }}</td>
                <td>{{ row.avgDwell }}</td>
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

    </StatsSectionBlock>
    <StatsSectionBlock
      :section-id="'core_pairs'"
      :order="sectionOrderIndex('core_pairs')"
      @reorder="onSectionReorder"
    >
      <!-- Core-pair migration summary -->
      <StatsSectionHeader
        :section-id="'core_pairs'"
        :collapsed="corePairsCollapsed"
        :pinned="isSectionPinned('core_pairs')"
        @toggle="toggleSectionCollapse('core_pairs')"
        @toggle-pin="toggleSectionPin('core_pairs')"
      >
        Core-Pair Migration Summary{{ scopeSuffixStr }}
      </StatsSectionHeader>
      <template v-if="!corePairsCollapsed">
        <div
          v-if="corePairRows.length === 0"
          class="range-hint"
        >
          No migrations in scope
        </div>
        <div
          v-else
          class="stats-table-block"
        >
          <div class="stats-table-wrap" :style="{ maxHeight: tableHeight('core_pairs') + 'px' }">
            <table class="stats-table">
              <thead>
                <tr>
                  <th :class="thSortClass('core_pairs', 'from')" @click="toggleTableSort('core_pairs', 'from')">From</th>
                  <th :class="thSortClass('core_pairs', 'to')" @click="toggleTableSort('core_pairs', 'to')">To</th>
                  <th :class="thSortClass('core_pairs', 'count')" @click="toggleTableSort('core_pairs', 'count')">Count</th>
                  <th :class="thSortClass('core_pairs', 'bounces')" @click="toggleTableSort('core_pairs', 'bounces')">Bounces</th>
                  <th :class="thSortClass('core_pairs', 'bouncePct')" @click="toggleTableSort('core_pairs', 'bouncePct')">Bounce %</th>
                  <th :class="thSortClass('core_pairs', 'avgGap')" @click="toggleTableSort('core_pairs', 'avgGap')">Avg Gap</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="row in sortedCorePairRows"
                  :key="`${row.fromCore}-${row.toCore}`"
                  class="stats-table-row clickable"
                  :title="`Click to view Gap/Rate distribution for ${row.fromCore} → ${row.toCore}`"
                  tabindex="0"
                  @click="openPairPlot(row.fromCore, row.toCore)"
                  @keydown.enter.prevent="openPairPlot(row.fromCore, row.toCore)"
                  @keydown.space.prevent="openPairPlot(row.fromCore, row.toCore)"
                >
                  <td class="task-col">{{ row.fromCore }}</td>
                  <td class="task-col">{{ row.toCore }}</td>
                  <td>{{ row.count }}</td>
                  <td>{{ row.bounces }}</td>
                  <td>{{ row.bouncePct.toFixed(1) }}%</td>
                  <td>{{ formatMigGapNs(row.avgGapNs) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div
            class="stats-section-resizer"
            role="separator"
            aria-label="Resize core-pair migration table"
            aria-orientation="horizontal"
            @mousedown.prevent="onTableResizeStart('core_pairs', $event)"
          />
        </div>
      </template>

    </StatsSectionBlock>
    <StatsSectionBlock
      :section-id="'anomalies'"
      :order="sectionOrderIndex('anomalies')"
      @reorder="onSectionReorder"
    >
      <StatsSectionHeader
        :section-id="'anomalies'"
        :collapsed="anomaliesCollapsed"
        :pinned="isSectionPinned('anomalies')"
        @toggle="toggleSectionCollapse('anomalies')"
        @toggle-pin="toggleSectionPin('anomalies')"
      >
        Timeline Anomalies{{ scopeSuffixStr }}
      </StatsSectionHeader>
      <template v-if="!anomaliesCollapsed">
        <div class="stats-tool-row">
          <button
            type="button"
            class="stats-tool-btn"
            :disabled="!aiFeatureEnabled || !anomalyRows.length"
            :title="!aiFeatureEnabled
              ? 'Enable AI Assistant in Settings → AI'
              : !anomalyRows.length
                ? 'No timeline anomalies in this scope'
                : 'Open the AI Assistant and investigate the selected or top anomaly'"
            @click="onInvestigateAnomaly"
          >
            Investigate…
          </button>
        </div>
        <div
          v-if="anomalyRows.length === 0"
          class="range-hint"
        >
          No timeline anomalies in this scope
        </div>
        <div
          v-else
          class="stats-table-block"
        >
          <div
            class="stats-table-wrap"
            :style="{ maxHeight: tableHeight('anomalies') + 'px' }"
          >
            <table class="stats-table">
              <thead>
                <tr>
                  <th :class="thSortClass('anomalies', 'time')" @click="toggleTableSort('anomalies', 'time')">Time</th>
                  <th :class="thSortClass('anomalies', 'kind')" @click="toggleTableSort('anomalies', 'kind')">Kind</th>
                  <th :class="thSortClass('anomalies', 'task')" @click="toggleTableSort('anomalies', 'task')">Task</th>
                  <th :class="thSortClass('anomalies', 'duration')" @click="toggleTableSort('anomalies', 'duration')">Duration</th>
                  <th :class="thSortClass('anomalies', 'why')" @click="toggleTableSort('anomalies', 'why')">Why</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="(row, i) in sortedAnomalyRows"
                  :key="'an-' + i + row.start"
                  class="stats-table-row clickable"
                  :title="'Zoom and place C1–C2 on this episode'"
                  @click="onAnomalyRowClick(row)"
                >
                  <td class="extreme-col">{{ formatTime(row.start, timeScale) }}</td>
                  <td>{{ uxKindLabel(row.kind) }}</td>
                  <td class="task-col">{{ row.task }}</td>
                  <td>{{ formatTime(row.duration, timeScale) }}</td>
                  <td>{{ row.reason }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div
            class="stats-section-resizer"
            role="separator"
            aria-label="Resize anomalies table"
            aria-orientation="horizontal"
            @mousedown.prevent="onTableResizeStart('anomalies', $event)"
          />
        </div>
      </template>
    </StatsSectionBlock>
    <StatsSectionBlock
      :section-id="'worst'"
      :order="sectionOrderIndex('worst')"
      @reorder="onSectionReorder"
    >
      <StatsSectionHeader
        :section-id="'worst'"
        :collapsed="worstCollapsed"
        :pinned="isSectionPinned('worst')"
        @toggle="toggleSectionCollapse('worst')"
        @toggle-pin="toggleSectionPin('worst')"
      >
        Worst Events{{ scopeSuffixStr }}
      </StatsSectionHeader>
      <template v-if="!worstCollapsed">
        <div
          v-if="worstRows.length === 0"
          class="range-hint"
        >
          No episodes in this scope
        </div>
        <div
          v-else
          class="stats-table-block"
        >
          <div
            class="stats-table-wrap"
            :style="{ maxHeight: tableHeight('worst') + 'px' }"
          >
            <table class="stats-table">
              <thead>
                <tr>
                  <th :class="thSortClass('worst', 'time')" @click="toggleTableSort('worst', 'time')">Time</th>
                  <th :class="thSortClass('worst', 'kind')" @click="toggleTableSort('worst', 'kind')">Kind</th>
                  <th :class="thSortClass('worst', 'task')" @click="toggleTableSort('worst', 'task')">Task</th>
                  <th :class="thSortClass('worst', 'duration')" @click="toggleTableSort('worst', 'duration')">Duration</th>
                  <th :class="thSortClass('worst', 'why')" @click="toggleTableSort('worst', 'why')">Why</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="(row, i) in sortedWorstRows"
                  :key="'w-' + i + row.start"
                  class="stats-table-row clickable"
                  :title="'Zoom and place C1–C2 on this episode'"
                  @click="onUxEventClick(row)"
                >
                  <td class="extreme-col">{{ formatTime(row.start, timeScale) }}</td>
                  <td>{{ uxKindLabel(row.kind) }}</td>
                  <td class="task-col">{{ row.task }}</td>
                  <td>{{ formatTime(row.duration, timeScale) }}</td>
                  <td>{{ row.reason || uxKindLabel(row.kind) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div
            class="stats-section-resizer"
            role="separator"
            aria-label="Resize worst-events table"
            aria-orientation="horizontal"
            @mousedown.prevent="onTableResizeStart('worst', $event)"
          />
        </div>
      </template>
    </StatsSectionBlock>
    <StatsSectionBlock
      :section-id="'crit_path'"
      :order="sectionOrderIndex('crit_path')"
      @reorder="onSectionReorder"
    >
      <StatsSectionHeader
        :section-id="'crit_path'"
        :collapsed="critPathCollapsed"
        :pinned="isSectionPinned('crit_path')"
        @toggle="toggleSectionCollapse('crit_path')"
        @toggle-pin="toggleSectionPin('crit_path')"
      >
        Critical Path{{ scopeSuffixStr }}
      </StatsSectionHeader>
      <template v-if="!critPathCollapsed">
        <div
          v-if="critPathRows.length === 0"
          class="range-hint"
        >
          Need at least one on-CPU slice
        </div>
        <div
          v-else
          class="stats-table-block"
        >
          <div
            class="stats-table-wrap"
            :style="{ maxHeight: tableHeight('crit_path') + 'px' }"
          >
            <table class="stats-table">
              <thead>
                <tr>
                  <th :class="thSortClass('crit_path', 'task')" @click="toggleTableSort('crit_path', 'task')">Task</th>
                  <th :class="thSortClass('crit_path', 'duration')" @click="toggleTableSort('crit_path', 'duration')">Duration</th>
                  <th :class="thSortClass('crit_path', 'exec')" @click="toggleTableSort('crit_path', 'exec')">Exec</th>
                  <th :class="thSortClass('crit_path', 'preempt')" @click="toggleTableSort('crit_path', 'preempt')">Preempt</th>
                  <th :class="thSortClass('crit_path', 'wait')" @click="toggleTableSort('crit_path', 'wait')">Wait</th>
                  <th :class="thSortClass('crit_path', 'mig')" @click="toggleTableSort('crit_path', 'mig')">Mig</th>
                  <th :class="thSortClass('crit_path', 'other')" @click="toggleTableSort('crit_path', 'other')">Other</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="(row, i) in sortedCritPathRows"
                  :key="'cp-' + i + row.start"
                  class="stats-table-row clickable"
                >
                  <td
                    class="task-col extreme-col"
                    :title="'Zoom this ready→completion window'"
                    @click="onCritPathCellClick(row)"
                  >{{ row.task }}</td>
                  <td class="extreme-col" @click="onCritPathCellClick(row)">{{ formatTime(row.duration, timeScale) }}</td>
                  <td class="extreme-col" @click="onCritPathCellClick(row, 'exec_ev')">{{ formatTime(row.exec_ns, timeScale) }}</td>
                  <td class="extreme-col" @click="onCritPathCellClick(row, 'preempt_ev')">{{ formatTime(row.preempt_ns, timeScale) }}</td>
                  <td class="extreme-col" @click="onCritPathCellClick(row, 'wait_ev')">{{ formatTime(row.wait_ns, timeScale) }}</td>
                  <td class="extreme-col" @click="onCritPathCellClick(row, 'mig_ev')">{{ formatTime(row.migration_ns, timeScale) }}</td>
                  <td class="extreme-col" @click="onCritPathCellClick(row, 'other_ev')">{{ formatTime(row.other_ns, timeScale) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div
            class="stats-section-resizer"
            role="separator"
            aria-label="Resize critical-path table"
            aria-orientation="horizontal"
            @mousedown.prevent="onTableResizeStart('crit_path', $event)"
          />
        </div>
      </template>
    </StatsSectionBlock>
    <StatsSectionBlock
      :section-id="'patterns'"
      :order="sectionOrderIndex('patterns')"
      @reorder="onSectionReorder"
    >
      <StatsSectionHeader
        :section-id="'patterns'"
        :collapsed="patternsCollapsed"
        :pinned="isSectionPinned('patterns')"
        @toggle="toggleSectionCollapse('patterns')"
        @toggle-pin="toggleSectionPin('patterns')"
      >
        Recurring Patterns{{ scopeSuffixStr }}
      </StatsSectionHeader>
      <template v-if="!patternsCollapsed">
        <div
          v-if="patternRows.length === 0"
          class="range-hint"
        >
          No repeating anomaly kinds in this scope
        </div>
        <div
          v-else
          class="stats-table-block"
        >
          <div
            class="stats-table-wrap"
            :style="{ maxHeight: tableHeight('patterns') + 'px' }"
          >
            <table class="stats-table">
              <thead>
                <tr>
                  <th :class="thSortClass('patterns', 'task')" @click="toggleTableSort('patterns', 'task')">Task</th>
                  <th :class="thSortClass('patterns', 'kind')" @click="toggleTableSort('patterns', 'kind')">Kind</th>
                  <th :class="thSortClass('patterns', 'count')" @click="toggleTableSort('patterns', 'count')">Count</th>
                  <th :class="thSortClass('patterns', 'duration')" @click="toggleTableSort('patterns', 'duration')">Worst</th>
                  <th :class="thSortClass('patterns', 'why')" @click="toggleTableSort('patterns', 'why')">Why</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="(row, i) in sortedPatternRows"
                  :key="'pat-' + i + row.kind"
                  class="stats-table-row clickable"
                  :title="'Jump to the worst instance'"
                  @click="onUxEventClick(row)"
                >
                  <td class="task-col">{{ row.task }}</td>
                  <td>{{ uxKindLabel(row.kind) }}</td>
                  <td>{{ row.count }}</td>
                  <td>{{ formatTime(row.duration, timeScale) }}</td>
                  <td>{{ row.reason }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div
            class="stats-section-resizer"
            role="separator"
            aria-label="Resize recurring-patterns table"
            aria-orientation="horizontal"
            @mousedown.prevent="onTableResizeStart('patterns', $event)"
          />
        </div>
      </template>
    </StatsSectionBlock>
    <StatsSectionBlock
      :section-id="'exec'"
      :order="sectionOrderIndex('exec')"
      @reorder="onSectionReorder"
    >
      <!-- Execution time per slice -->
      <StatsSectionHeader
        :section-id="'exec'"
        :collapsed="execSliceCollapsed"
        :pinned="isSectionPinned('exec')"
        @toggle="toggleSectionCollapse('exec')"
        @toggle-pin="toggleSectionPin('exec')"
      >
        Execution Time Per Slice{{ scopeSuffixStr }}
      </StatsSectionHeader>
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
                  :class="thSortClass('exec', 'jitter')"
                  title="Observed range: maximum minus minimum slice duration"
                  @click="toggleTableSort('exec', 'jitter')"
                >
                  Jitter
                </th>
                <th
                  :class="thSortClass('exec', 'stddev')"
                  title="Population standard deviation of slice durations"
                  @click="toggleTableSort('exec', 'stddev')"
                >
                  σ
                </th>
                <th
                  :class="thSortClass('exec', 'p95')"
                  @click="toggleTableSort('exec', 'p95')"
                >
                  p95
                </th>
                <th
                  :class="thSortClass('exec', 'p99')"
                  @click="toggleTableSort('exec', 'p99')"
                >
                  p99
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
                @click="openTaskPlot(row.mk, 'exec')"
                @keydown.enter.prevent="openTaskPlot(row.mk, 'exec')"
                @keydown.space.prevent="openTaskPlot(row.mk, 'exec')"
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
                <td>{{ row.jitter }}</td>
                <td>{{ row.stddev }}</td>
                <td
                  class="extreme-col"
                  :title="`Jump to the p95 slice for ${row.name}`"
                  @click.stop="jumpToPercentile(row.mk, 'exec', 0.95)"
                >
                  {{ row.p95 }}
                </td>
                <td
                  class="extreme-col"
                  :title="`Jump to the p99 slice for ${row.name}`"
                  @click.stop="jumpToPercentile(row.mk, 'exec', 0.99)"
                >
                  {{ row.p99 }}
                </td>
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

    </StatsSectionBlock>
    <StatsSectionBlock
      :section-id="'block'"
      :order="sectionOrderIndex('block')"
      @reorder="onSectionReorder"
    >
      <!-- Blocking time -->
      <StatsSectionHeader
        :section-id="'block'"
        :collapsed="blockingCollapsed"
        :pinned="isSectionPinned('block')"
        @toggle="toggleSectionCollapse('block')"
        @toggle-pin="toggleSectionPin('block')"
      >
        Blocking Time (off-CPU gap){{ scopeSuffixStr }}
      </StatsSectionHeader>
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
                  :class="thSortClass('block', 'jitter')"
                  title="Observed range: maximum minus minimum off-CPU gap"
                  @click="toggleTableSort('block', 'jitter')"
                >
                  Jitter
                </th>
                <th
                  :class="thSortClass('block', 'stddev')"
                  title="Population standard deviation of off-CPU gaps"
                  @click="toggleTableSort('block', 'stddev')"
                >
                  σ
                </th>
                <th
                  :class="thSortClass('block', 'p95')"
                  @click="toggleTableSort('block', 'p95')"
                >
                  p95
                </th>
                <th
                  :class="thSortClass('block', 'p99')"
                  @click="toggleTableSort('block', 'p99')"
                >
                  p99
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
                @click="openTaskPlot(row.mk, 'block')"
                @keydown.enter.prevent="openTaskPlot(row.mk, 'block')"
                @keydown.space.prevent="openTaskPlot(row.mk, 'block')"
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
                <td>{{ row.jitter }}</td>
                <td>{{ row.stddev }}</td>
                <td
                  class="extreme-col"
                  :title="`Jump to the p95 blocking gap for ${row.name}`"
                  @click.stop="jumpToPercentile(row.mk, 'block', 0.95)"
                >
                  {{ row.p95 }}
                </td>
                <td
                  class="extreme-col"
                  :title="`Jump to the p99 blocking gap for ${row.name}`"
                  @click.stop="jumpToPercentile(row.mk, 'block', 0.99)"
                >
                  {{ row.p99 }}
                </td>
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

    </StatsSectionBlock>
    <StatsSectionBlock
      :section-id="'dispatch'"
      :order="sectionOrderIndex('dispatch')"
      @reorder="onSectionReorder"
    >
      <!-- Dispatch / scheduling latency -->
      <StatsSectionHeader
        :section-id="'dispatch'"
        :collapsed="dispatchCollapsed"
        :pinned="isSectionPinned('dispatch')"
        @toggle="toggleSectionCollapse('dispatch')"
        @toggle-pin="toggleSectionPin('dispatch')"
      >
        Dispatch / Scheduling Latency{{ scopeSuffixStr }}
      </StatsSectionHeader>
      <template v-if="!dispatchCollapsed">
        <div
          v-if="dispatchLatencyStats.length === 0"
          class="range-hint"
        >
          {{ statsRange
            ? 'No dispatch samples in cursor range (needs STI resume Name[id] or task create → first run)'
            : 'No dispatch samples — needs STI task resume Name[id] (vTaskResume) or create→first-run pairs' }}
        </div>
        <div
          v-else
          class="stats-table-block"
        >
          <div
            class="stats-table-wrap"
            :style="{ maxHeight: tableHeight('dispatch') + 'px' }"
          >
            <table class="stats-table">
              <thead>
                <tr>
                  <th
                    :class="thSortClass('dispatch', 'task')"
                    @click="toggleTableSort('dispatch', 'task')"
                  >
                    Task
                  </th>
                  <th
                    :class="thSortClass('dispatch', 'activations')"
                    @click="toggleTableSort('dispatch', 'activations')"
                  >
                    Activations
                  </th>
                  <th
                    :class="thSortClass('dispatch', 'min')"
                    @click="toggleTableSort('dispatch', 'min')"
                  >
                    Min
                  </th>
                  <th
                    :class="thSortClass('dispatch', 'avg')"
                    @click="toggleTableSort('dispatch', 'avg')"
                  >
                    Avg
                  </th>
                  <th
                    :class="thSortClass('dispatch', 'max')"
                    @click="toggleTableSort('dispatch', 'max')"
                  >
                    Max
                  </th>
                  <th
                    :class="thSortClass('dispatch', 'jitter')"
                    title="Observed range: maximum minus minimum dispatch latency"
                    @click="toggleTableSort('dispatch', 'jitter')"
                  >
                    Jitter
                  </th>
                  <th
                    :class="thSortClass('dispatch', 'stddev')"
                    title="Population standard deviation of dispatch latency"
                    @click="toggleTableSort('dispatch', 'stddev')"
                  >
                    σ
                  </th>
                  <th
                    :class="thSortClass('dispatch', 'p95')"
                    @click="toggleTableSort('dispatch', 'p95')"
                  >
                    p95
                  </th>
                  <th
                    :class="thSortClass('dispatch', 'p99')"
                    @click="toggleTableSort('dispatch', 'p99')"
                  >
                    p99
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="row in sortedDispatchLatencyStats"
                  :key="row.mk"
                  class="stats-table-row clickable"
                  :title="`Open dispatch-latency plot for ${row.label}`"
                  tabindex="0"
                  @click="openTaskPlot(row.mk, 'dispatch')"
                  @keydown.enter.prevent="openTaskPlot(row.mk, 'dispatch')"
                  @keydown.space.prevent="openTaskPlot(row.mk, 'dispatch')"
                >
                  <td class="task-col">{{ row.label }}</td>
                  <td>{{ row.activations }}</td>
                  <td
                    class="extreme-col"
                    :title="`Jump to shortest dispatch latency for ${row.label}`"
                    @click.stop="jumpToDispatchExtreme(row, false)"
                  >
                    {{ row.min }}
                  </td>
                  <td>{{ row.avg }}</td>
                  <td
                    class="extreme-col"
                    :title="`Jump to longest dispatch latency for ${row.label}`"
                    @click.stop="jumpToDispatchExtreme(row, true)"
                  >
                    {{ row.max }}
                  </td>
                  <td>{{ row.jitter }}</td>
                  <td>{{ row.stddev }}</td>
                  <td>{{ row.p95 }}</td>
                  <td>{{ row.p99 }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div
            class="stats-section-resizer"
            role="separator"
            aria-label="Resize dispatch latency table"
            aria-orientation="horizontal"
            @mousedown.prevent="onTableResizeStart('dispatch', $event)"
          />
        </div>
      </template>

    </StatsSectionBlock>
    <StatsSectionBlock
      :section-id="'inter'"
      :order="sectionOrderIndex('inter')"
      @reorder="onSectionReorder"
    >
      <!-- Inter-arrival time -->
      <StatsSectionHeader
        :section-id="'inter'"
        :collapsed="interArrivalCollapsed"
        :pinned="isSectionPinned('inter')"
        @toggle="toggleSectionCollapse('inter')"
        @toggle-pin="toggleSectionPin('inter')"
      >
        Inter-Arrival Time{{ scopeSuffixStr }}
      </StatsSectionHeader>
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
                  :class="thSortClass('inter', 'jitter')"
                  title="Observed range: maximum minus minimum inter-arrival time"
                  @click="toggleTableSort('inter', 'jitter')"
                >
                  Jitter
                </th>
                <th
                  :class="thSortClass('inter', 'stddev')"
                  title="Population standard deviation of inter-arrival times"
                  @click="toggleTableSort('inter', 'stddev')"
                >
                  σ
                </th>
                <th
                  :class="thSortClass('inter', 'p95')"
                  @click="toggleTableSort('inter', 'p95')"
                >
                  p95
                </th>
                <th
                  :class="thSortClass('inter', 'p99')"
                  @click="toggleTableSort('inter', 'p99')"
                >
                  p99
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
                @click="openTaskPlot(row.mk, 'inter')"
                @keydown.enter.prevent="openTaskPlot(row.mk, 'inter')"
                @keydown.space.prevent="openTaskPlot(row.mk, 'inter')"
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
                <td>{{ row.jitter }}</td>
                <td>{{ row.stddev }}</td>
                <td
                  class="extreme-col"
                  :title="`Jump to the p95 inter-arrival for ${row.name}`"
                  @click.stop="jumpToPercentile(row.mk, 'inter', 0.95)"
                >
                  {{ row.p95 }}
                </td>
                <td
                  class="extreme-col"
                  :title="`Jump to the p99 inter-arrival for ${row.name}`"
                  @click.stop="jumpToPercentile(row.mk, 'inter', 0.99)"
                >
                  {{ row.p99 }}
                </td>
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

    </StatsSectionBlock>
    <StatsSectionBlock
      :section-id="'period'"
      :order="sectionOrderIndex('period')"
      @reorder="onSectionReorder"
    >
      <StatsSectionHeader
        :section-id="'period'"
        :collapsed="periodCollapsed"
        :pinned="isSectionPinned('period')"
        @toggle="toggleSectionCollapse('period')"
        @toggle-pin="toggleSectionPin('period')"
      >
        Period / Jitter{{ scopeSuffixStr }}
      </StatsSectionHeader>
      <template v-if="!periodCollapsed">
        <div
          v-if="periodRows.length === 0"
          class="range-hint"
        >
          Need at least 3 inter-arrival gaps per task
        </div>
        <div
          v-else
          class="stats-table-block"
        >
          <div
            class="stats-table-wrap"
            :style="{ maxHeight: tableHeight('period') + 'px' }"
          >
            <table class="stats-table">
              <thead>
                <tr>
                  <th :class="thSortClass('period', 'task')" @click="toggleTableSort('period', 'task')">Task</th>
                  <th :class="thSortClass('period', 'n')" @click="toggleTableSort('period', 'n')">N</th>
                  <th :class="thSortClass('period', 'expected')" @click="toggleTableSort('period', 'expected')">Expected</th>
                  <th :class="thSortClass('period', 'min')" @click="toggleTableSort('period', 'min')">Min</th>
                  <th :class="thSortClass('period', 'avg')" @click="toggleTableSort('period', 'avg')">Avg</th>
                  <th :class="thSortClass('period', 'max')" @click="toggleTableSort('period', 'max')">Max</th>
                  <th :class="thSortClass('period', 'p95')" @click="toggleTableSort('period', 'p95')">p95</th>
                  <th :class="thSortClass('period', 'p99')" @click="toggleTableSort('period', 'p99')">p99</th>
                  <th :class="thSortClass('period', 'rms')" @click="toggleTableSort('period', 'rms')">RMS</th>
                  <th :class="thSortClass('period', 'cv')" @click="toggleTableSort('period', 'cv')">CV</th>
                  <th :class="thSortClass('period', 'missed')" @click="toggleTableSort('period', 'missed')">Missed</th>
                  <th :class="thSortClass('period', 'extra')" @click="toggleTableSort('period', 'extra')">Extra</th>
                  <th :class="thSortClass('period', 'burst')" @click="toggleTableSort('period', 'burst')">Burst</th>
                  <th :class="thSortClass('period', 'spark')" title="Inter-arrival over time" @click="toggleTableSort('period', 'spark')">Spark</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="row in sortedPeriodRows"
                  :key="'per-' + row.mk"
                  class="stats-table-row clickable"
                >
                  <td
                    class="task-col extreme-col"
                    :title="'Open inter-arrival plot for ' + row.task"
                    @click="onPeriodCellClick(row, 'plot')"
                  >{{ row.task }}</td>
                  <td>{{ row.n }}</td>
                  <td class="extreme-col" @click="onPeriodCellClick(row, 'p50_ev')">{{ formatTime(row.expected_ns, timeScale) }}</td>
                  <td class="extreme-col" @click="onPeriodCellClick(row, 'min_ev')">{{ formatTime(row.min_ns, timeScale) }}</td>
                  <td class="extreme-col" @click="onPeriodCellClick(row, 'p50_ev')">{{ formatTime(row.avg_ns, timeScale) }}</td>
                  <td class="extreme-col" @click="onPeriodCellClick(row, 'max_ev')">{{ formatTime(row.max_ns, timeScale) }}</td>
                  <td class="extreme-col" @click="onPeriodCellClick(row, 'p95_ev')">{{ formatTime(row.p95_ns, timeScale) }}</td>
                  <td class="extreme-col" @click="onPeriodCellClick(row, 'p99_ev')">{{ formatTime(row.p99_ns, timeScale) }}</td>
                  <td>{{ formatTime(row.rms_ns, timeScale) }}</td>
                  <td>{{ (row.cv * 100).toFixed(1) }}%</td>
                  <td class="extreme-col" @click="onPeriodCellClick(row, 'miss_ev')">{{ row.missed }}</td>
                  <td>{{ row.extra }}</td>
                  <td>{{ row.burst || 0 }}</td>
                  <td class="spark-col">{{ row.spark || '' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div
            class="stats-section-resizer"
            role="separator"
            aria-label="Resize period table"
            aria-orientation="horizontal"
            @mousedown.prevent="onTableResizeStart('period', $event)"
          />
        </div>
      </template>
    </StatsSectionBlock>
    <StatsSectionBlock
      :section-id="'response'"
      :order="sectionOrderIndex('response')"
      @reorder="onSectionReorder"
    >
      <StatsSectionHeader
        :section-id="'response'"
        :collapsed="responseCollapsed"
        :pinned="isSectionPinned('response')"
        @toggle="toggleSectionCollapse('response')"
        @toggle-pin="toggleSectionPin('response')"
      >
        Response Time{{ scopeSuffixStr }}
      </StatsSectionHeader>
      <template v-if="!responseCollapsed">
        <div
          v-if="responseRows.length === 0"
          class="range-hint"
        >
          Need at least one on-CPU slice
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
                  <th :class="thSortClass('response', 'task')" @click="toggleTableSort('response', 'task')">Task</th>
                  <th :class="thSortClass('response', 'n')" @click="toggleTableSort('response', 'n')">N</th>
                  <th :class="thSortClass('response', 'min')" @click="toggleTableSort('response', 'min')">Min</th>
                  <th :class="thSortClass('response', 'avg')" @click="toggleTableSort('response', 'avg')">Avg</th>
                  <th :class="thSortClass('response', 'max')" @click="toggleTableSort('response', 'max')">Max</th>
                  <th :class="thSortClass('response', 'p50')" @click="toggleTableSort('response', 'p50')">p50</th>
                  <th :class="thSortClass('response', 'p90')" @click="toggleTableSort('response', 'p90')">p90</th>
                  <th :class="thSortClass('response', 'p95')" @click="toggleTableSort('response', 'p95')">p95</th>
                  <th :class="thSortClass('response', 'p99')" @click="toggleTableSort('response', 'p99')">p99</th>
                  <th :class="thSortClass('response', 'p999')" @click="toggleTableSort('response', 'p999')">p99.9</th>
                  <th :class="thSortClass('response', 'jitter')" @click="toggleTableSort('response', 'jitter')">Jitter</th>
                  <th :class="thSortClass('response', 'cv')" @click="toggleTableSort('response', 'cv')">CV</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="row in sortedResponseRows"
                  :key="'rt-' + row.mk"
                  class="stats-table-row clickable"
                >
                  <td
                    class="task-col extreme-col"
                    :title="'Open response plot for ' + row.task"
                    @click="onResponseCellClick(row, 'plot')"
                  >{{ row.task }}</td>
                  <td>{{ row.n }}</td>
                  <td class="extreme-col" @click="onResponseCellClick(row, 'min_ev')">{{ formatTime(row.min_ns, timeScale) }}</td>
                  <td>{{ formatTime(row.avg_ns, timeScale) }}</td>
                  <td class="extreme-col" @click="onResponseCellClick(row, 'max_ev')">{{ formatTime(row.max_ns, timeScale) }}</td>
                  <td class="extreme-col" @click="onResponseCellClick(row, 'p50_ev')">{{ formatTime(row.p50_ns, timeScale) }}</td>
                  <td class="extreme-col" @click="onResponseCellClick(row, 'p90_ev')">{{ formatTime(row.p90_ns, timeScale) }}</td>
                  <td class="extreme-col" @click="onResponseCellClick(row, 'p95_ev')">{{ formatTime(row.p95_ns, timeScale) }}</td>
                  <td class="extreme-col" @click="onResponseCellClick(row, 'p99_ev')">{{ formatTime(row.p99_ns, timeScale) }}</td>
                  <td class="extreme-col" @click="onResponseCellClick(row, 'p999_ev')">{{ formatTime(row.p999_ns, timeScale) }}</td>
                  <td class="extreme-col" @click="onResponseCellClick(row, 'worst_ev')">{{ formatTime(row.jitter_ns, timeScale) }}</td>
                  <td>{{ ((row.cv || 0) * 100).toFixed(1) }}%</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div
            class="stats-section-resizer"
            role="separator"
            aria-label="Resize response-time table"
            aria-orientation="horizontal"
            @mousedown.prevent="onTableResizeStart('response', $event)"
          />
        </div>
      </template>
    </StatsSectionBlock>
    <StatsSectionBlock
      :section-id="'jitter'"
      :order="sectionOrderIndex('jitter')"
      @reorder="onSectionReorder"
    >
      <StatsSectionHeader
        :section-id="'jitter'"
        :collapsed="jitterCollapsed"
        :pinned="isSectionPinned('jitter')"
        @toggle="toggleSectionCollapse('jitter')"
        @toggle-pin="toggleSectionPin('jitter')"
      >
        Unified Jitter{{ scopeSuffixStr }}
      </StatsSectionHeader>
      <template v-if="!jitterCollapsed">
        <div
          v-if="jitterRows.length === 0"
          class="range-hint"
        >
          No timing samples in this scope
        </div>
        <div
          v-else
          class="stats-table-block"
        >
          <div
            class="stats-table-wrap"
            :style="{ maxHeight: tableHeight('jitter') + 'px' }"
          >
            <table class="stats-table">
              <thead>
                <tr>
                  <th :class="thSortClass('jitter', 'task')" @click="toggleTableSort('jitter', 'task')">Task</th>
                  <th :class="thSortClass('jitter', 'exec')" @click="toggleTableSort('jitter', 'exec')">Exec</th>
                  <th :class="thSortClass('jitter', 'execCv')" @click="toggleTableSort('jitter', 'execCv')">Exec CV</th>
                  <th :class="thSortClass('jitter', 'block')" @click="toggleTableSort('jitter', 'block')">Block</th>
                  <th :class="thSortClass('jitter', 'blockCv')" @click="toggleTableSort('jitter', 'blockCv')">Block CV</th>
                  <th :class="thSortClass('jitter', 'inter')" @click="toggleTableSort('jitter', 'inter')">Inter</th>
                  <th :class="thSortClass('jitter', 'interCv')" @click="toggleTableSort('jitter', 'interCv')">Inter CV</th>
                  <th :class="thSortClass('jitter', 'response')" @click="toggleTableSort('jitter', 'response')">Response</th>
                  <th :class="thSortClass('jitter', 'responseCv')" @click="toggleTableSort('jitter', 'responseCv')">Resp CV</th>
                  <th :class="thSortClass('jitter', 'dispatch')" @click="toggleTableSort('jitter', 'dispatch')">Dispatch</th>
                  <th :class="thSortClass('jitter', 'dispatchCv')" @click="toggleTableSort('jitter', 'dispatchCv')">Disp CV</th>
                  <th :class="thSortClass('jitter', 'wakeup')" @click="toggleTableSort('jitter', 'wakeup')">Wake</th>
                  <th :class="thSortClass('jitter', 'wakeupCv')" @click="toggleTableSort('jitter', 'wakeupCv')">Wake CV</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="row in sortedJitterRows"
                  :key="'jit-' + row.mk"
                  class="stats-table-row clickable"
                >
                  <td
                    class="task-col extreme-col"
                    :title="'Open execution plot for ' + row.task"
                    @click="onJitterCellClick(row, 'exec')"
                  >{{ row.task }}</td>
                  <td class="extreme-col" @click="onJitterCellClick(row, 'exec')">{{ formatTime(row.exec_jitter_ns, timeScale) }}</td>
                  <td class="extreme-col" @click="onJitterCellClick(row, 'exec')">{{ ((row.exec_cv || 0) * 100).toFixed(1) }}%</td>
                  <td class="extreme-col" @click="onJitterCellClick(row, 'block')">{{ formatTime(row.block_jitter_ns, timeScale) }}</td>
                  <td class="extreme-col" @click="onJitterCellClick(row, 'block')">{{ ((row.block_cv || 0) * 100).toFixed(1) }}%</td>
                  <td class="extreme-col" @click="onJitterCellClick(row, 'inter')">{{ formatTime(row.inter_jitter_ns, timeScale) }}</td>
                  <td class="extreme-col" @click="onJitterCellClick(row, 'inter')">{{ ((row.inter_cv || 0) * 100).toFixed(1) }}%</td>
                  <td class="extreme-col" @click="onJitterCellClick(row, 'response')">{{ formatTime(row.response_jitter_ns, timeScale) }}</td>
                  <td class="extreme-col" @click="onJitterCellClick(row, 'response')">{{ ((row.response_cv || 0) * 100).toFixed(1) }}%</td>
                  <td class="extreme-col" @click="onJitterCellClick(row, 'dispatch')">{{ formatTime(row.dispatch_jitter_ns, timeScale) }}</td>
                  <td class="extreme-col" @click="onJitterCellClick(row, 'dispatch')">{{ ((row.dispatch_cv || 0) * 100).toFixed(1) }}%</td>
                  <td class="extreme-col" @click="onJitterCellClick(row, 'block')">{{ formatTime(row.wakeup_jitter_ns, timeScale) }}</td>
                  <td class="extreme-col" @click="onJitterCellClick(row, 'block')">{{ ((row.wakeup_cv || 0) * 100).toFixed(1) }}%</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div
            class="stats-section-resizer"
            role="separator"
            aria-label="Resize unified-jitter table"
            aria-orientation="horizontal"
            @mousedown.prevent="onTableResizeStart('jitter', $event)"
          />
        </div>
      </template>
    </StatsSectionBlock>
    <StatsSectionBlock
      :section-id="'distrib'"
      :order="sectionOrderIndex('distrib')"
      @reorder="onSectionReorder"
    >
      <StatsSectionHeader
        :section-id="'distrib'"
        :collapsed="distribCollapsed"
        :pinned="isSectionPinned('distrib')"
        @toggle="toggleSectionCollapse('distrib')"
        @toggle-pin="toggleSectionPin('distrib')"
      >
        Distribution Explorer{{ scopeSuffixStr }}
      </StatsSectionHeader>
      <template v-if="!distribCollapsed">
        <div class="distrib-toolbar">
          <div class="distrib-selectors">
            <label>
              Metric
              <DomSelect
                v-model="distribKind"
                :options="distribKindSelectOptions"
              />
            </label>
            <label>
              Task
              <DomSelect
                v-model="distribMk"
                :options="distribTaskOptions"
              />
            </label>
          </div>
          <div class="distrib-actions">
            <button
              type="button"
              class="stats-tool-btn"
              :disabled="!distribMk"
              @click="onOpenDistributionPlot"
            >
              Open histogram
            </button>
            <button
              type="button"
              class="stats-tool-btn"
              :disabled="!aiFeatureEnabled || !distribMk"
              :title="aiFeatureEnabled
                ? 'Open the AI Assistant and explain this distribution'
                : 'Enable AI Assistant in Settings → AI'"
              @click="queryDistributionWithAi('explorer')"
            >
              Query with AI…
            </button>
          </div>
        </div>
        <div class="range-hint">
          {{ distribSummary }}
        </div>
        <div
          v-if="distribHistogramModel"
          class="distrib-hist plot-card plot-card-histogram"
        >
          <div class="plot-histogram-toolbar">
            <label class="plot-scale-label">
              Histogram scale
              <DomSelect
                v-model="distribScaleMode"
                class="plot-scale-select"
                :options="plotScaleOptions"
              />
            </label>
            <span class="plot-histogram-caption">{{ distribHistogramModel.caption }}</span>
          </div>
          <svg
            class="plot-svg distrib-hist-svg"
            :viewBox="`0 0 ${distribHistogramModel.width} ${distribHistogramModel.height}`"
          >
            <rect
              x="0"
              y="0"
              :width="distribHistogramModel.width"
              :height="distribHistogramModel.height"
              fill="var(--bg)"
            />
            <rect
              v-if="distribHistogramModel.sigmaBand"
              :x="distribHistogramModel.sigmaBand.x"
              :y="distribHistogramModel.margin.top"
              :width="distribHistogramModel.sigmaBand.width"
              :height="distribHistogramModel.height - distribHistogramModel.margin.top - distribHistogramModel.margin.bottom"
              fill="#CE93D8"
              fill-opacity="0.14"
            />
            <rect
              v-for="bar in distribHistogramModel.bars"
              :key="`dx-bar-${bar.index}-${bar.kind || 'regular'}`"
              :x="bar.x"
              :y="bar.y"
              :width="bar.width"
              :height="bar.height"
              :fill="distribHistogramModel.color"
              :fill-opacity="bar.kind === 'overflow' || bar.kind === 'underflow' ? 0.55 : 0.82"
            />
            <polyline
              v-if="distribHistogramModel.cdfPoints.length > 1"
              :points="distribHistogramModel.cdfPoints.map(p => `${p.x},${p.y}`).join(' ')"
              fill="none"
              stroke="#90CAF9"
              stroke-width="1.5"
              stroke-linejoin="round"
            />
            <g
              v-for="refLine in distribHistogramModel.referenceLines"
              :key="`dx-ref-${refLine.label}`"
            >
              <line
                :x1="refLine.x"
                :x2="refLine.x"
                :y1="distribHistogramModel.margin.top"
                :y2="distribHistogramModel.height - distribHistogramModel.margin.bottom"
                :stroke="refLine.color"
                stroke-dasharray="5 5"
              />
              <text
                :x="Math.min(refLine.x + 6, distribHistogramModel.width - distribHistogramModel.margin.right - 2)"
                :y="distribHistogramModel.margin.top + 12"
                fill="var(--fg)"
                class="plot-ref-text"
              >
                {{ refLine.label }}
              </text>
            </g>
            <g
              v-for="tick in distribHistogramModel.xTicks"
              :key="`dx-x-${tick.index}`"
            >
              <text
                :x="tick.x"
                :y="distribHistogramModel.height - 10"
                text-anchor="middle"
                fill="var(--fg-dim)"
                class="plot-axis-text"
              >
                {{ tick.label }}
              </text>
            </g>
          </svg>
        </div>
        <div
          v-else
          class="range-hint"
        >
          No histogram samples for this metric × task.
        </div>
      </template>
    </StatsSectionBlock>
    <StatsSectionBlock
      :section-id="'preemption'"
      :order="sectionOrderIndex('preemption')"
      @reorder="onSectionReorder"
    >
      <!-- Preemption Chain Analysis -->
      <StatsSectionHeader
        :section-id="'preemption'"
        :collapsed="preemptionCollapsed"
        :pinned="isSectionPinned('preemption')"
        @toggle="toggleSectionCollapse('preemption')"
        @toggle-pin="toggleSectionPin('preemption')"
      >
        Preemption Chain Analysis{{ scopeSuffixStr }}
      </StatsSectionHeader>
      <template v-if="!preemptionCollapsed">
        <div
          v-if="preemptionComputing"
          class="range-hint"
        >
          Computing preemption chain…
        </div>
        <div
          v-else-if="preemptionRows.length === 0"
          class="range-hint"
        >
          {{ statsRange ? 'No preemption events in cursor range' : 'No preemption events found' }}
        </div>
        <div
          v-else
          class="stats-table-block"
        >
          <div
            v-if="preemptionTruncated"
            class="range-hint"
          >
            Showing top {{ PREEMPTION_CHAIN_MAX_ROWS.toLocaleString() }} pairs by total preemption time.
          </div>
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

    </StatsSectionBlock>
    <StatsSectionBlock
      :section-id="'preempt_matrix'"
      :order="sectionOrderIndex('preempt_matrix')"
      @reorder="onSectionReorder"
    >
      <StatsSectionHeader
        :section-id="'preempt_matrix'"
        :collapsed="preemptMatrixCollapsed"
        :pinned="isSectionPinned('preempt_matrix')"
        @toggle="toggleSectionCollapse('preempt_matrix')"
        @toggle-pin="toggleSectionPin('preempt_matrix')"
      >
        Preemption Matrix{{ scopeSuffixStr }}
      </StatsSectionHeader>
      <template v-if="!preemptMatrixCollapsed">
        <div
          v-if="!preemptRankRows.length"
          class="range-hint"
        >
          No preemption overlaps in this scope
        </div>
        <template v-else>
          <div class="stats-table-block">
            <div class="stats-section-subtitle">Preemptor ranking</div>
            <div
              class="stats-table-wrap"
              :style="{ maxHeight: tableHeight('preempt_matrix') + 'px' }"
            >
              <table class="stats-table">
                <thead>
                  <tr>
                    <th :class="thSortClass('preempt_rank', 'task')" @click="toggleTableSort('preempt_rank', 'task')">Victim</th>
                    <th :class="thSortClass('preempt_rank', 'count')" @click="toggleTableSort('preempt_rank', 'count')">Count</th>
                    <th :class="thSortClass('preempt_rank', 'total')" @click="toggleTableSort('preempt_rank', 'total')">Total</th>
                    <th :class="thSortClass('preempt_rank', 'max')" @click="toggleTableSort('preempt_rank', 'max')">Max</th>
                    <th :class="thSortClass('preempt_rank', 'top')" @click="toggleTableSort('preempt_rank', 'top')">Top preemptors</th>
                    <th :class="thSortClass('preempt_rank', 'story')" @click="toggleTableSort('preempt_rank', 'story')">Story</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="row in sortedPreemptRankRows"
                    :key="'pr-' + row.mk"
                    class="stats-table-row clickable"
                    :title="'Jump to the longest preemption of ' + row.task"
                    @click="onUxEventClick(row.worst)"
                  >
                    <td class="task-col">{{ row.task }}</td>
                    <td>{{ row.count }}</td>
                    <td>{{ formatTime(row.total_ns, timeScale) }}</td>
                    <td>{{ formatTime(row.max_ns, timeScale) }}</td>
                    <td>{{ row.top_label }}</td>
                    <td>{{ row.story }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
          <div
            v-if="preemptMatrixModel.tasks.length"
            class="stats-table-block"
          >
            <div class="stats-section-subtitle">Victim \ Preemptor</div>
            <div
              class="stats-table-wrap"
              :style="{ maxHeight: tableHeight('preempt_matrix') + 'px' }"
            >
            <table class="stats-table">
              <thead>
                <tr>
                  <th :class="thSortClass('preempt_matrix', 'victim')" @click="toggleTableSort('preempt_matrix', 'victim')">Victim \ Preemptor</th>
                  <th
                    v-for="col in preemptMatrixModel.tasks"
                    :key="'pm-h-' + col.mk"
                    :class="thSortClass('preempt_matrix', col.mk)"
                    @click="toggleTableSort('preempt_matrix', col.mk)"
                  >{{ col.task }}</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="victim in sortedPreemptMatrixTasks"
                  :key="'pm-' + victim.mk"
                  class="stats-table-row clickable"
                >
                    <td class="task-col">{{ victim.task }}</td>
                    <td
                      v-for="col in preemptMatrixModel.tasks"
                      :key="'pm-' + victim.mk + col.mk"
                      :class="preemptMatrixModel.cells[victim.mk + '|' + col.mk]?.ns ? 'extreme-col' : ''"
                      @click="onPreemptMatrixCellClick(preemptMatrixModel.cells[victim.mk + '|' + col.mk])"
                    >{{
                      victim.mk === col.mk
                        ? '—'
                        : (preemptMatrixModel.cells[victim.mk + '|' + col.mk]?.ns
                          ? formatTime(preemptMatrixModel.cells[victim.mk + '|' + col.mk].ns, timeScale)
                          : '—')
                    }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div
              class="stats-section-resizer"
              role="separator"
              aria-label="Resize preemption-matrix table"
              aria-orientation="horizontal"
              @mousedown.prevent="onTableResizeStart('preempt_matrix', $event)"
            />
          </div>
        </template>
      </template>
    </StatsSectionBlock>
    <StatsSectionBlock
      v-if="trace?.hasPriorityInstrumentation"
      :section-id="'priority'"
      :order="sectionOrderIndex('priority')"
      @reorder="onSectionReorder"
    >
      <!-- Priority inheritance -->
      <StatsSectionHeader
        :section-id="'priority'"
        :collapsed="priorityCollapsed"
        :pinned="isSectionPinned('priority')"
        @toggle="toggleSectionCollapse('priority')"
        @toggle-pin="toggleSectionPin('priority')"
      >
        Priority Inheritance{{ scopeSuffixStr }}
      </StatsSectionHeader>
      <template v-if="!priorityCollapsed">
        <div
          v-if="priorityStats.length === 0"
          class="range-hint"
        >
          {{ statsRange ? 'No priority boosts in cursor range' : 'No priority boosts in trace' }}
        </div>
        <div
          v-else
          class="stats-table-block"
        >
          <div
            class="stats-table-wrap"
            :style="{ maxHeight: tableHeight('priority') + 'px' }"
          >
            <table class="stats-table">
              <thead>
                <tr>
                  <th
                    :class="thSortClass('priority', 'task')"
                    @click="toggleTableSort('priority', 'task')"
                  >
                    Task
                  </th>
                  <th
                    :class="thSortClass('priority', 'base')"
                    @click="toggleTableSort('priority', 'base')"
                  >
                    Base
                  </th>
                  <th
                    :class="thSortClass('priority', 'peak')"
                    @click="toggleTableSort('priority', 'peak')"
                  >
                    Peak
                  </th>
                  <th
                    :class="thSortClass('priority', 'boosts')"
                    @click="toggleTableSort('priority', 'boosts')"
                  >
                    Boosts
                  </th>
                  <th
                    :class="thSortClass('priority', 'total')"
                    @click="toggleTableSort('priority', 'total')"
                  >
                    Boosted
                  </th>
                  <th
                    :class="thSortClass('priority', 'pattern')"
                    @click="toggleTableSort('priority', 'pattern')"
                  >
                    Pattern
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="row in sortedPriorityStats"
                  :key="row.mk"
                  class="stats-table-row clickable"
                  :class="{ 'priority-inversion-row': row.inversionCount > 0 }"
                  :title="priorityRowTitle(row)"
                  tabindex="0"
                  @click="onPriorityRowClick(row)"
                  @keydown.enter.prevent="onPriorityRowClick(row)"
                  @keydown.space.prevent="onPriorityRowClick(row)"
                >
                  <td class="task-col">{{ row.label }}</td>
                  <td>{{ row.basePri }}</td>
                  <td>{{ row.peakPri }}</td>
                  <td>{{ row.episodeCount }}</td>
                  <td>{{ row.total }}</td>
                  <td>
                    <span
                      class="priority-pattern"
                      :class="{ inversion: row.inversionCount > 0 }"
                    >{{ row.pattern }}</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <div
            class="stats-section-resizer"
            role="separator"
            aria-label="Resize priority inheritance table"
            aria-orientation="horizontal"
            @mousedown.prevent="onTableResizeStart('priority', $event)"
          />
        </div>
      </template>

    </StatsSectionBlock>
    <StatsSectionBlock
      v-if="trace?.hasSyncObjectInstrumentation"
      :section-id="'sync'"
      :order="sectionOrderIndex('sync')"
      @reorder="onSectionReorder"
    >
      <!-- Mutex / Semaphore pairing -->
      <StatsSectionHeader
        :section-id="'sync'"
        :collapsed="syncCollapsed"
        :pinned="isSectionPinned('sync')"
        @toggle="toggleSectionCollapse('sync')"
        @toggle-pin="toggleSectionPin('sync')"
      >
        Mutex / Semaphore{{ scopeSuffixStr }}
      </StatsSectionHeader>
      <template v-if="!syncCollapsed">
        <div
          v-if="syncStats.length === 0"
          class="range-hint"
        >
          {{ statsRange ? 'No mutex/sem activity in cursor range' : 'No mutex/sem STI events in trace' }}
        </div>
        <div
          v-else
          class="stats-table-block"
        >
          <div
            class="stats-table-wrap"
            :style="{ maxHeight: tableHeight('sync') + 'px' }"
          >
            <table class="stats-table">
              <thead>
                <tr>
                  <th
                    :class="thSortClass('sync', 'object')"
                    @click="toggleTableSort('sync', 'object')"
                  >
                    Object
                  </th>
                  <th
                    :class="thSortClass('sync', 'kind')"
                    @click="toggleTableSort('sync', 'kind')"
                  >
                    Kind
                  </th>
                  <th
                    :class="thSortClass('sync', 'holds')"
                    @click="toggleTableSort('sync', 'holds')"
                  >
                    Holds
                  </th>
                  <th
                    :class="thSortClass('sync', 'issues')"
                    @click="toggleTableSort('sync', 'issues')"
                  >
                    Issues
                  </th>
                  <th
                    :class="thSortClass('sync', 'bounces')"
                    @click="toggleTableSort('sync', 'bounces')"
                    title="Number of holds where the mutex lock crossed core boundaries (cache-line bounce)"
                  >
                    Bounces
                  </th>
                  <th
                    :class="thSortClass('sync', 'avg')"
                    @click="toggleTableSort('sync', 'avg')"
                  >
                    Avg hold
                  </th>
                  <th
                    :class="thSortClass('sync', 'status')"
                    @click="toggleTableSort('sync', 'status')"
                  >
                    Status
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="row in sortedSyncStats"
                  :key="row.key"
                  :class="{ 'sync-issue-row': row.status !== 'ok' }"
                >
                  <td class="task-col">{{ row.label }}</td>
                  <td>{{ row.kind }}</td>
                  <td>{{ row.holdCount }}</td>
                  <td>{{ row.issueCount }}</td>
                  <td :class="row.bounceCount > 0 ? 'sev-warning' : ''">
                    {{ row.bounceCount }}
                  </td>
                  <td>{{ row.avgHold }}</td>
                  <td :class="syncStatusClass(row.status)">
                    {{ row.statusLabel }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <div
            class="stats-section-resizer"
            role="separator"
            aria-label="Resize mutex/semaphore summary table"
            aria-orientation="horizontal"
            @mousedown.prevent="onTableResizeStart('sync', $event)"
          />
          <div
            v-if="syncIssueDisplay.note"
            class="range-hint"
          >
            {{ syncIssueDisplay.note }}
          </div>
          <div
            v-if="syncIssueList.length"
            class="stats-table-wrap sync-issues-wrap"
            :style="{ maxHeight: tableHeight('sync_issues') + 'px' }"
          >
            <table class="stats-table sync-issues-table">
              <thead>
                <tr>
                  <th
                    :class="thSortClass('sync_issues', 'object')"
                    @click="toggleTableSort('sync_issues', 'object')"
                  >
                    Object
                  </th>
                  <th
                    :class="thSortClass('sync_issues', 'time')"
                    @click="toggleTableSort('sync_issues', 'time')"
                  >
                    Time
                  </th>
                  <th
                    :class="thSortClass('sync_issues', 'detail')"
                    @click="toggleTableSort('sync_issues', 'detail')"
                  >
                    Detail
                  </th>
                  <th
                    :class="thSortClass('sync_issues', 'issue')"
                    @click="toggleTableSort('sync_issues', 'issue')"
                  >
                    Issue
                  </th>
                  <th
                    :class="thSortClass('sync_issues', 'task')"
                    @click="toggleTableSort('sync_issues', 'task')"
                  >
                    Task
                  </th>
                  <th
                    :class="thSortClass('sync_issues', 'core')"
                    @click="toggleTableSort('sync_issues', 'core')"
                  >
                    Core
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="(iss, idx) in sortedSyncIssueList"
                  :key="`${iss.objKey}-${iss.kind}-${iss.timeNs}-${idx}`"
                  class="clickable-row"
                  tabindex="0"
                  role="button"
                  :title="`Jump, zoom, and annotate at ${fmtTime(iss.timeNs)}`"
                  @click="onSyncIssueClick(iss)"
                  @keydown.enter.prevent="onSyncIssueClick(iss)"
                  @keydown.space.prevent="onSyncIssueClick(iss)"
                >
                  <td>{{ iss.objKey || '—' }}</td>
                  <td>{{ fmtTime(iss.timeNs) }}</td>
                  <td>{{ iss.detail }}</td>
                  <td :class="syncIssueSeverityClass(iss.severity)">
                    {{ iss.kind }}
                  </td>
                  <td>{{ iss.taskLabel || '—' }}</td>
                  <td>{{ iss.core || '' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div
            v-if="syncIssueList.length"
            class="stats-section-resizer"
            role="separator"
            aria-label="Resize mutex/semaphore issues table"
            aria-orientation="horizontal"
            @mousedown.prevent="onTableResizeStart('sync_issues', $event)"
          />
        </div>
      </template>

    </StatsSectionBlock>
    <StatsSectionBlock
      :section-id="'wait_owner'"
      :order="sectionOrderIndex('wait_owner')"
      @reorder="onSectionReorder"
    >
      <StatsSectionHeader
        :section-id="'wait_owner'"
        :collapsed="waitOwnerCollapsed"
        :pinned="isSectionPinned('wait_owner')"
        @toggle="toggleSectionCollapse('wait_owner')"
        @toggle-pin="toggleSectionPin('wait_owner')"
      >
        Waiter × Owner{{ scopeSuffixStr }}
      </StatsSectionHeader>
      <template v-if="!waitOwnerCollapsed">
        <div
          v-if="!waitOwnerModel.tasks.length"
          class="range-hint"
        >
          No mutex handoffs in this scope
        </div>
        <div
          v-else
          class="stats-table-block"
        >
          <div
            class="stats-table-wrap"
            :style="{ maxHeight: tableHeight('wait_owner') + 'px' }"
          >
            <table class="stats-table">
              <thead>
                <tr>
                  <th :class="thSortClass('wait_owner', 'waiter')" @click="toggleTableSort('wait_owner', 'waiter')">Waiter \ Owner</th>
                  <th
                    v-for="owner in waitOwnerModel.tasks"
                    :key="'wo-h-' + owner.mk"
                    :class="thSortClass('wait_owner', owner.mk)"
                    @click="toggleTableSort('wait_owner', owner.mk)"
                  >{{ owner.task }}</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="waiter in sortedWaitOwnerTasks"
                  :key="'wo-' + waiter.mk"
                  class="stats-table-row clickable"
                >
                  <td class="task-col">{{ waiter.task }}</td>
                  <td
                    v-for="owner in waitOwnerModel.tasks"
                    :key="'wo-' + waiter.mk + owner.mk"
                    :class="waitOwnerModel.cells[waiter.mk + '|' + owner.mk]?.ns ? 'extreme-col' : ''"
                    @click="onWaitOwnerCellClick(waitOwnerModel.cells[waiter.mk + '|' + owner.mk])"
                  >{{
                    waiter.mk === owner.mk
                      ? '—'
                      : (waitOwnerModel.cells[waiter.mk + '|' + owner.mk]?.ns
                        ? formatTime(waitOwnerModel.cells[waiter.mk + '|' + owner.mk].ns, timeScale)
                        : '—')
                  }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div
            class="stats-section-resizer"
            role="separator"
            aria-label="Resize waiter-owner table"
            aria-orientation="horizontal"
            @mousedown.prevent="onTableResizeStart('wait_owner', $event)"
          />
        </div>
      </template>
    </StatsSectionBlock>
    <StatsSectionBlock
      :section-id="'mutex_block'"
      :order="sectionOrderIndex('mutex_block')"
      @reorder="onSectionReorder"
    >
      <StatsSectionHeader
        :section-id="'mutex_block'"
        :collapsed="mutexBlockCollapsed"
        :pinned="isSectionPinned('mutex_block')"
        @toggle="toggleSectionCollapse('mutex_block')"
        @toggle-pin="toggleSectionPin('mutex_block')"
      >
        Mutex Blocking{{ scopeSuffixStr }}
      </StatsSectionHeader>
      <template v-if="!mutexBlockCollapsed">
        <div
          v-if="mutexBlockRows.length === 0"
          class="range-hint"
        >
          No mutex waits in this scope
        </div>
        <div
          v-else
          class="stats-table-block"
        >
          <div
            class="stats-table-wrap"
            :style="{ maxHeight: tableHeight('mutex_block') + 'px' }"
          >
            <table class="stats-table">
              <thead>
                <tr>
                  <th :class="thSortClass('mutex_block', 'task')" @click="toggleTableSort('mutex_block', 'task')">Task</th>
                  <th :class="thSortClass('mutex_block', 'object')" @click="toggleTableSort('mutex_block', 'object')">Object</th>
                  <th :class="thSortClass('mutex_block', 'owner')" @click="toggleTableSort('mutex_block', 'owner')">Owner</th>
                  <th :class="thSortClass('mutex_block', 'count')" @click="toggleTableSort('mutex_block', 'count')">Count</th>
                  <th :class="thSortClass('mutex_block', 'total')" @click="toggleTableSort('mutex_block', 'total')">Total</th>
                  <th :class="thSortClass('mutex_block', 'max')" @click="toggleTableSort('mutex_block', 'max')">Max</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="(row, i) in sortedMutexBlockRows"
                  :key="'mb-' + i + row.mk"
                  class="stats-table-row clickable"
                  :title="'Jump to the longest wait'"
                  @click="onMutexBlockClick(row)"
                >
                  <td class="task-col">{{ row.task }}</td>
                  <td>{{ row.object }}</td>
                  <td>{{ row.owner }}</td>
                  <td>{{ row.count }}</td>
                  <td>{{ formatTime(row.total_ns, timeScale) }}</td>
                  <td>{{ formatTime(row.max_ns, timeScale) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div
            class="stats-section-resizer"
            role="separator"
            aria-label="Resize mutex-blocking table"
            aria-orientation="horizontal"
            @mousedown.prevent="onTableResizeStart('mutex_block', $event)"
          />
        </div>
        <div
          v-if="blockerRows.length"
          class="stats-table-block"
        >
          <div class="stats-section-subtitle">Top blocking contributors</div>
          <div class="range-hint">
            Mutex waits, preemption overlap, and leftover idle gaps.
          </div>
          <div
            class="stats-table-wrap"
            :style="{ maxHeight: tableHeight('mutex_block') + 'px' }"
          >
            <table class="stats-table">
              <thead>
                <tr>
                  <th :class="thSortClass('mutex_blockers', 'task')" @click="toggleTableSort('mutex_blockers', 'task')">Task</th>
                  <th :class="thSortClass('mutex_blockers', 'mutex')" @click="toggleTableSort('mutex_blockers', 'mutex')">Mutex</th>
                  <th :class="thSortClass('mutex_blockers', 'preempt')" @click="toggleTableSort('mutex_blockers', 'preempt')">Preempt</th>
                  <th :class="thSortClass('mutex_blockers', 'idle')" @click="toggleTableSort('mutex_blockers', 'idle')">Idle</th>
                  <th :class="thSortClass('mutex_blockers', 'total')" @click="toggleTableSort('mutex_blockers', 'total')">Total</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="row in sortedBlockerRows"
                  :key="'tb-' + row.mk"
                  class="stats-table-row clickable"
                  @click="onUxEventClick({ ...(row.worst || row), mk: row.mk, task: row.task, section: 'mutex_block' })"
                >
                  <td class="task-col">{{ row.task }}</td>
                  <td>{{ formatTime(row.mutex_ns, timeScale) }}</td>
                  <td>{{ formatTime(row.preempt_ns, timeScale) }}</td>
                  <td>{{ formatTime(row.idle_ns, timeScale) }}</td>
                  <td>{{ formatTime(row.total_ns, timeScale) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </template>
    </StatsSectionBlock>
    <StatsSectionBlock
      v-if="trace?.hasSyncObjectInstrumentation"
      :section-id="'queue'"
      :order="sectionOrderIndex('queue')"
      @reorder="onSectionReorder"
    >
      <!-- Queue pairing -->
      <StatsSectionHeader
        :section-id="'queue'"
        :collapsed="queueCollapsed"
        :pinned="isSectionPinned('queue')"
        @toggle="toggleSectionCollapse('queue')"
        @toggle-pin="toggleSectionPin('queue')"
      >
        Queue{{ scopeSuffixStr }}
      </StatsSectionHeader>
      <template v-if="!queueCollapsed">
        <div v-if="queueStats.length === 0" class="range-hint">
          {{ statsRange ? 'No queue activity in cursor range' : 'No queue STI events in trace' }}
        </div>
        <div v-else class="stats-table-block">
          <div class="stats-table-wrap" :style="{ maxHeight: tableHeight('queue') + 'px' }">
            <table class="stats-table">
              <thead>
                <tr>
                  <th :class="thSortClass('queue', 'object')" @click="toggleTableSort('queue', 'object')">Object</th>
                  <th :class="thSortClass('queue', 'kind')" @click="toggleTableSort('queue', 'kind')">Kind</th>
                  <th :class="thSortClass('queue', 'holds')" @click="toggleTableSort('queue', 'holds')">Holds</th>
                  <th :class="thSortClass('queue', 'issues')" @click="toggleTableSort('queue', 'issues')">Issues</th>
                  <th :class="thSortClass('queue', 'bounces')" @click="toggleTableSort('queue', 'bounces')">Bounces</th>
                  <th :class="thSortClass('queue', 'avg')" @click="toggleTableSort('queue', 'avg')">Avg hold</th>
                  <th :class="thSortClass('queue', 'status')" @click="toggleTableSort('queue', 'status')">Status</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in sortedQueueStats" :key="row.key">
                  <td class="task-col">{{ row.label }}</td>
                  <td>{{ row.kind }}</td>
                  <td>{{ row.holdCount }}</td>
                  <td>{{ row.issueCount }}</td>
                  <td :class="row.bounceCount > 0 ? 'sev-warning' : ''">{{ row.bounceCount ?? 0 }}</td>
                  <td>{{ row.avgHold }}</td>
                  <td :class="syncStatusClass(row.status)">{{ row.statusLabel }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div
            class="stats-section-resizer"
            role="separator"
            aria-label="Resize queue table"
            aria-orientation="horizontal"
            @mousedown.prevent="onTableResizeStart('queue', $event)"
          />
        </div>
      </template>

    </StatsSectionBlock>
    <StatsSectionBlock
      :section-id="'lifecycle'"
      :order="sectionOrderIndex('lifecycle')"
      @reorder="onSectionReorder"
    >
      <!-- Task lifecycle -->
      <StatsSectionHeader
        :section-id="'lifecycle'"
        :collapsed="lifecycleCollapsed"
        :pinned="isSectionPinned('lifecycle')"
        @toggle="toggleSectionCollapse('lifecycle')"
        @toggle-pin="toggleSectionPin('lifecycle')"
      >
        Task Lifecycle{{ scopeSuffixStr }}
      </StatsSectionHeader>
      <template v-if="!lifecycleCollapsed">
        <div
          v-if="lifecycleStats.length === 0"
          class="range-hint"
        >
          {{ statsRange
            ? 'No task lifecycle events in cursor range'
            : 'No task create/delete/suspend/resume STI events in trace' }}
        </div>
        <div
          v-else
          class="stats-table-block"
        >
          <div class="stats-table-wrap" :style="{ maxHeight: tableHeight('lifecycle') + 'px' }">
            <table class="stats-table">
              <thead>
                <tr>
                  <th :class="thSortClass('lifecycle', 'task')" @click="toggleTableSort('lifecycle', 'task')">Task</th>
                  <th :class="thSortClass('lifecycle', 'created')" @click="toggleTableSort('lifecycle', 'created')">Created</th>
                  <th :class="thSortClass('lifecycle', 'deleted')" @click="toggleTableSort('lifecycle', 'deleted')">Deleted</th>
                  <th :class="thSortClass('lifecycle', 'suspRes')" @click="toggleTableSort('lifecycle', 'suspRes')">Susp/Res</th>
                  <th :class="thSortClass('lifecycle', 'alive')" @click="toggleTableSort('lifecycle', 'alive')">Alive</th>
                  <th :class="thSortClass('lifecycle', 'events')" @click="toggleTableSort('lifecycle', 'events')">Events</th>
                  <th :class="thSortClass('lifecycle', 'runs')" @click="toggleTableSort('lifecycle', 'runs')">Runs</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="row in sortedLifecycleStats"
                  :key="row.mk"
                  class="stats-table-row clickable"
                  :title="`Click to highlight '${row.label}' in the timeline`"
                  tabindex="0"
                  @click="onLifecycleRowClick(row)"
                  @keydown.enter.prevent="onLifecycleRowClick(row)"
                  @keydown.space.prevent="onLifecycleRowClick(row)"
                >
                  <td class="task-col">{{ row.label }}</td>
                  <td>{{ row.createNs != null ? formatTime(row.createNs, trace.timeScale) : '—' }}</td>
                  <td>{{ row.deleteNs != null ? formatTime(row.deleteNs, trace.timeScale) : '—' }}</td>
                  <td>{{ row.suspendCount }}/{{ row.resumeCount }}</td>
                  <td>{{ formatLifecycleSpan(row.aliveSpanNs, trace.timeScale) }}</td>
                  <td>{{ row.eventCount }}</td>
                  <td>{{ row.runCount }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div
            class="stats-section-resizer"
            role="separator"
            aria-label="Resize task lifecycle table"
            aria-orientation="horizontal"
            @mousedown.prevent="onTableResizeStart('lifecycle', $event)"
          />
        </div>
      </template>

    </StatsSectionBlock>
    <StatsSectionBlock
      :section-id="'affinity'"
      :order="sectionOrderIndex('affinity')"
      @reorder="onSectionReorder"
    >
      <!-- Core affinity -->
      <StatsSectionHeader
        :section-id="'affinity'"
        :collapsed="affinityCollapsed"
        :pinned="isSectionPinned('affinity')"
        @toggle="toggleSectionCollapse('affinity')"
        @toggle-pin="toggleSectionPin('affinity')"
      >
        Core Affinity{{ scopeSuffixStr }}
      </StatsSectionHeader>
      <template v-if="!affinityCollapsed">
        <div
          v-if="coreAffinityRows.length === 0"
          class="range-hint"
        >
          No affinity_set events found
        </div>
        <div
          v-else
          class="stats-table-block"
        >
          <div class="stats-table-wrap" :style="{ maxHeight: tableHeight('affinity') + 'px' }">
            <table class="stats-table">
              <thead>
                <tr>
                  <th :class="thSortClass('affinity', 'task')" @click="toggleTableSort('affinity', 'task')">Task</th>
                  <th :class="thSortClass('affinity', 'mask')" @click="toggleTableSort('affinity', 'mask')">Mask</th>
                  <th :class="thSortClass('affinity', 'observed')" @click="toggleTableSort('affinity', 'observed')">Observed Cores</th>
                  <th :class="thSortClass('affinity', 'violations')" @click="toggleTableSort('affinity', 'violations')">Violations</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="row in sortedAffinityRows"
                  :key="row.mk"
                  class="stats-table-row clickable"
                  :title="`Click to highlight '${row.label}' in the timeline`"
                  tabindex="0"
                  @click="emit('highlightTask', row.mk)"
                  @keydown.enter.prevent="emit('highlightTask', row.mk)"
                  @keydown.space.prevent="emit('highlightTask', row.mk)"
                >
                  <td class="task-col">{{ row.label }}</td>
                  <td>{{ row.maskHex }}</td>
                  <td>{{ row.observedCores }}</td>
                  <td :class="row.violations !== '—' ? 'sev-error' : ''">{{ row.violations }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div
            class="stats-section-resizer"
            role="separator"
            aria-label="Resize core affinity table"
            aria-orientation="horizontal"
            @mousedown.prevent="onTableResizeStart('affinity', $event)"
          />
        </div>
      </template>

    </StatsSectionBlock>
    <StatsSectionBlock
      :section-id="'task_core'"
      :order="sectionOrderIndex('task_core')"
      @reorder="onSectionReorder"
    >
      <StatsSectionHeader
        :section-id="'task_core'"
        :collapsed="taskCoreCollapsed"
        :pinned="isSectionPinned('task_core')"
        @toggle="toggleSectionCollapse('task_core')"
        @toggle-pin="toggleSectionPin('task_core')"
      >
        Task × Core{{ scopeSuffixStr }}
      </StatsSectionHeader>
      <template v-if="!taskCoreCollapsed">
        <div
          v-if="!taskCoreModel.rows.length"
          class="range-hint"
        >
          No on-CPU slices in this scope
        </div>
        <div
          v-else
          class="stats-table-block"
        >
          <div
            class="stats-table-wrap"
            :style="{ maxHeight: tableHeight('task_core') + 'px' }"
          >
            <table class="stats-table">
              <thead>
                <tr>
                  <th :class="thSortClass('task_core', 'task')" @click="toggleTableSort('task_core', 'task')">Task</th>
                  <th
                    v-for="core in taskCoreModel.cores"
                    :key="'tc-h-' + core"
                    :class="thSortClass('task_core', core)"
                    @click="toggleTableSort('task_core', core)"
                  >{{ core }}</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="row in sortedTaskCoreRows"
                  :key="'tc-' + row.mk"
                  class="stats-table-row clickable"
                >
                  <td
                    class="task-col extreme-col"
                    @click="onTaskCoreCellClick(row, null)"
                  >{{ row.task }}</td>
                  <td
                    v-for="core in taskCoreModel.cores"
                    :key="'tc-' + row.mk + core"
                    :class="row.cells[core]?.ns ? 'extreme-col' : ''"
                    :title="row.cells[core]?.ns
                      ? (formatTime(row.cells[core].ns, timeScale) + ' on ' + core)
                      : ''"
                    @click="onTaskCoreCellClick(row, core)"
                  >{{ row.cells[core]?.ns ? row.cells[core].pct_span.toFixed(1) + '%' : '—' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div
            class="stats-section-resizer"
            role="separator"
            aria-label="Resize task-core table"
            aria-orientation="horizontal"
            @mousedown.prevent="onTableResizeStart('task_core', $event)"
          />
        </div>
      </template>
    </StatsSectionBlock>
    <StatsSectionBlock
      :section-id="'core_time'"
      :order="sectionOrderIndex('core_time')"
      @reorder="onSectionReorder"
    >
      <StatsSectionHeader
        :section-id="'core_time'"
        :collapsed="coreTimeCollapsed"
        :pinned="isSectionPinned('core_time')"
        @toggle="toggleSectionCollapse('core_time')"
        @toggle-pin="toggleSectionPin('core_time')"
      >
        Core Utilization Over Time{{ scopeSuffixStr }}
      </StatsSectionHeader>
      <template v-if="!coreTimeCollapsed">
        <div
          v-if="!coreTimeModel.bins.length"
          class="range-hint"
        >
          No on-CPU slices in this scope
        </div>
        <div
          v-else
          class="stats-table-block"
        >
          <div
            class="stats-table-wrap"
            :style="{ maxHeight: tableHeight('core_time') + 'px' }"
          >
            <table class="stats-table">
              <thead>
                <tr>
                  <th :class="thSortClass('core_time', 'time')" @click="toggleTableSort('core_time', 'time')">Time</th>
                  <th
                    v-for="core in coreTimeModel.cores"
                    :key="'ct-h-' + core"
                    :class="thSortClass('core_time', core)"
                    @click="toggleTableSort('core_time', core)"
                  >{{ core }}</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="row in sortedCoreTimeBins"
                  :key="'ct-' + row.index"
                  class="stats-table-row clickable"
                  :title="'Zoom this time bin'"
                  @click="onCoreTimeClick(row)"
                >
                  <td class="extreme-col">{{ formatTime(row.start, timeScale) }}</td>
                  <td
                    v-for="core in coreTimeModel.cores"
                    :key="'ct-' + row.index + core"
                  >{{ row.cells[core] ? row.cells[core].pct.toFixed(1) + '%' : '—' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div
            class="stats-section-resizer"
            role="separator"
            aria-label="Resize core-utilization table"
            aria-orientation="horizontal"
            @mousedown.prevent="onTableResizeStart('core_time', $event)"
          />
        </div>
      </template>
    </StatsSectionBlock>
    <StatsSectionBlock
      :section-id="'deadline'"
      :order="sectionOrderIndex('deadline')"
      @reorder="onSectionReorder"
    >
      <!-- Deadlines / CPU budget -->
      <StatsSectionHeader
        :section-id="'deadline'"
        :collapsed="deadlineCollapsed"
        :pinned="isSectionPinned('deadline')"
        @toggle="toggleSectionCollapse('deadline')"
        @toggle-pin="toggleSectionPin('deadline')"
      >
        Deadlines / CPU budget{{ scopeSuffixStr }}
      </StatsSectionHeader>
      <template v-if="!deadlineCollapsed">
        <div class="deadline-settings-hint">
          <template v-if="!hasDeadlineConfig">Configure deadline / CPU budget thresholds in </template>
          <template v-else>Edit thresholds in </template>
          <button
            type="button"
            class="stats-settings-link"
            title="Open Settings → Display → Analysis thresholds"
            @click="emit('openSettings', 'display')"
          >Settings → Display</button>
          <span> (Analysis thresholds)</span>
        </div>
        <template v-if="hasDeadlineConfig">
          <div v-if="!deadlineViolations.sliceViolations.length && !deadlineViolations.cpuViolations.length" class="range-hint">
            No violations in scope
          </div>
          <div v-if="deadlineViolations.sliceViolations.length" class="stats-table-block">
            <div class="stats-section-subtitle">Slice over deadline</div>
            <table class="stats-table">
              <thead>
                <tr>
                  <th :class="thSortClass('deadline_slice', 'task')" @click="toggleTableSort('deadline_slice', 'task')">Task</th>
                  <th :class="thSortClass('deadline_slice', 'duration')" @click="toggleTableSort('deadline_slice', 'duration')">Duration</th>
                  <th :class="thSortClass('deadline_slice', 'limit')" @click="toggleTableSort('deadline_slice', 'limit')">Limit</th>
                  <th :class="thSortClass('deadline_slice', 'over')" @click="toggleTableSort('deadline_slice', 'over')">Over by</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="(v, i) in sortedDeadlineSliceRows"
                  :key="'d'+i"
                  class="stats-table-row clickable"
                  :title="deadlineSliceRowTitle(v)"
                  tabindex="0"
                  @click="onDeadlineSliceClick(v)"
                  @keydown.enter.prevent="onDeadlineSliceClick(v)"
                  @keydown.space.prevent="onDeadlineSliceClick(v)"
                >
                  <td class="task-col">{{ v.label }}</td>
                  <td>{{ v.duration }}</td>
                  <td>{{ v.limit }}</td>
                  <td class="sev-error">{{ v.overBy }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-if="deadlineViolations.cpuViolations.length" class="stats-table-block">
            <div class="stats-section-subtitle">CPU budget exceeded</div>
            <table class="stats-table">
              <thead>
                <tr>
                  <th :class="thSortClass('deadline_cpu', 'task')" @click="toggleTableSort('deadline_cpu', 'task')">Task</th>
                  <th :class="thSortClass('deadline_cpu', 'cpu')" @click="toggleTableSort('deadline_cpu', 'cpu')">CPU %</th>
                  <th :class="thSortClass('deadline_cpu', 'budget')" @click="toggleTableSort('deadline_cpu', 'budget')">Budget</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="(v, i) in sortedDeadlineCpuRows"
                  :key="'c'+i"
                  class="stats-table-row clickable"
                  :title="`Click to highlight '${v.label}' in the timeline`"
                  tabindex="0"
                  @click="emit('highlightTask', v.mk)"
                  @keydown.enter.prevent="emit('highlightTask', v.mk)"
                  @keydown.space.prevent="emit('highlightTask', v.mk)"
                >
                  <td class="task-col">{{ v.label }}</td>
                  <td class="sev-error">{{ v.pct }}%</td>
                  <td>{{ v.budgetPct }}%</td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>
      </template>

    </StatsSectionBlock>
    <StatsSectionBlock
      :section-id="'task_health'"
      :order="sectionOrderIndex('task_health')"
      @reorder="onSectionReorder"
    >
      <StatsSectionHeader
        :section-id="'task_health'"
        :collapsed="taskHealthCollapsed"
        :pinned="isSectionPinned('task_health')"
        @toggle="toggleSectionCollapse('task_health')"
        @toggle-pin="toggleSectionPin('task_health')"
      >
        Task Health{{ scopeSuffixStr }}
      </StatsSectionHeader>
      <template v-if="!taskHealthCollapsed">
        <div
          v-if="taskHealthRows.length === 0"
          class="range-hint"
        >
          No task slices in this scope
        </div>
        <div
          v-else
          class="stats-table-block"
        >
          <div
            class="stats-table-wrap"
            :style="{ maxHeight: tableHeight('task_health') + 'px' }"
          >
            <table class="stats-table">
              <thead>
                <tr>
                  <th :class="thSortClass('task_health', 'task')" @click="toggleTableSort('task_health', 'task')">Task</th>
                  <th :class="thSortClass('task_health', 'score')" @click="toggleTableSort('task_health', 'score')">Score</th>
                  <th :class="thSortClass('task_health', 'execution')" @click="toggleTableSort('task_health', 'execution')">Exec</th>
                  <th :class="thSortClass('task_health', 'blocking')" @click="toggleTableSort('task_health', 'blocking')">Block</th>
                  <th :class="thSortClass('task_health', 'period')" @click="toggleTableSort('task_health', 'period')">Period</th>
                  <th :class="thSortClass('task_health', 'migration')" @click="toggleTableSort('task_health', 'migration')">Mig</th>
                  <th :class="thSortClass('task_health', 'deadline')" @click="toggleTableSort('task_health', 'deadline')">Deadline</th>
                  <th :class="thSortClass('task_health', 'cpu')" @click="toggleTableSort('task_health', 'cpu')">CPU</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="row in sortedTaskHealthRows"
                  :key="'th-' + row.mk"
                  class="stats-table-row clickable"
                >
                  <td
                    class="task-col extreme-col"
                    @click="onTaskHealthClick(row, null)"
                  >{{ row.task }}</td>
                  <td
                    :class="'health-' + healthTone(row.score)"
                    @click="onTaskHealthClick(row, null)"
                  >{{ row.score }}</td>
                  <td
                    v-for="band in ['execution', 'blocking', 'period', 'migration', 'deadline', 'cpu']"
                    :key="'th-' + row.mk + band"
                    :class="'health-' + (row.bands[band] || 'ok')"
                    class="health-mark"
                    @click="onTaskHealthClick(row, band)"
                  >{{ row.marks[band] }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div
            class="stats-section-resizer"
            role="separator"
            aria-label="Resize task-health table"
            aria-orientation="horizontal"
            @mousedown.prevent="onTableResizeStart('task_health', $event)"
          />
        </div>
      </template>
    </StatsSectionBlock>
    <StatsSectionBlock
      :section-id="'intervals'"
      :order="sectionOrderIndex('intervals')"
      @reorder="onSectionReorder"
    >
      <!-- Interval Analysis -->
      <StatsSectionHeader
        :section-id="'intervals'"
        :collapsed="intervalsCollapsed"
        :pinned="isSectionPinned('intervals')"
        @toggle="toggleSectionCollapse('intervals')"
        @toggle-pin="toggleSectionPin('intervals')"
      >
        Interval Analysis{{ scopeSuffixStr }}
      </StatsSectionHeader>
      <template v-if="!intervalsCollapsed">
        <div
          v-if="intervalStats.length === 0"
          class="range-hint"
        >
          {{ statsRange ? 'No interval data in cursor range' : 'No paired interval_start / interval_stop events in trace' }}
        </div>
        <div
          v-else
          class="stats-table-block"
        >
          <div
            class="stats-table-wrap"
            :style="{ maxHeight: tableHeight('intervals') + 'px' }"
          >
            <table class="stats-table">
              <thead>
                <tr>
                  <th
                    :class="thSortClass('intervals', 'id')"
                    @click="toggleTableSort('intervals', 'id')"
                  >
                    ID
                  </th>
                  <th
                    :class="thSortClass('intervals', 'count')"
                    @click="toggleTableSort('intervals', 'count')"
                  >
                    Count
                  </th>
                  <th
                    :class="thSortClass('intervals', 'min')"
                    @click="toggleTableSort('intervals', 'min')"
                  >
                    Min
                  </th>
                  <th
                    :class="thSortClass('intervals', 'avg')"
                    @click="toggleTableSort('intervals', 'avg')"
                  >
                    Avg
                  </th>
                  <th
                    :class="thSortClass('intervals', 'max')"
                    @click="toggleTableSort('intervals', 'max')"
                  >
                    Max
                  </th>
                  <th
                    :class="thSortClass('intervals', 'p95')"
                    @click="toggleTableSort('intervals', 'p95')"
                  >
                    P95
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="row in sortedIntervalStats"
                  :key="row.id"
                  class="stats-table-row clickable"
                  :title="`Open interval duration plot for ID ${row.id}`"
                  tabindex="0"
                  @click="openIntervalPlot(row.id)"
                  @keydown.enter.prevent="openIntervalPlot(row.id)"
                  @keydown.space.prevent="openIntervalPlot(row.id)"
                >
                  <td class="task-col">{{ row.label }}</td>
                  <td>{{ row.count }}</td>
                  <td>{{ row.min }}</td>
                  <td>{{ row.avg }}</td>
                  <td>{{ row.max }}</td>
                  <td>{{ row.p95 }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div
            class="stats-section-resizer"
            role="separator"
            aria-label="Resize interval analysis table"
            aria-orientation="horizontal"
            @mousedown.prevent="onTableResizeStart('intervals', $event)"
          />
        </div>
      </template>

    </StatsSectionBlock>
    <StatsSectionBlock
      :section-id="'tags'"
      :order="sectionOrderIndex('tags')"
      @reorder="onSectionReorder"
    >
      <!-- Tag Analysis -->
      <StatsSectionHeader
        :section-id="'tags'"
        :collapsed="tagsCollapsed"
        :pinned="isSectionPinned('tags')"
        @toggle="toggleSectionCollapse('tags')"
        @toggle-pin="toggleSectionPin('tags')"
      >
        Tag Analysis{{ scopeSuffixStr }}
      </StatsSectionHeader>
      <template v-if="!tagsCollapsed">
        <div
          v-if="tagStats.length === 0"
          class="range-hint"
        >
          {{ statsRange ? 'No tag samples in cursor range' : 'No tag0_event … tag7_event STI samples in trace' }}
        </div>
        <div
          v-else
          class="stats-table-block"
        >
          <div
            class="stats-table-wrap"
            :style="{ maxHeight: tableHeight('tags') + 'px' }"
          >
            <table class="stats-table">
              <thead>
                <tr>
                  <th
                    :class="thSortClass('tags', 'tag')"
                    @click="toggleTableSort('tags', 'tag')"
                  >
                    Tag
                  </th>
                  <th
                    :class="thSortClass('tags', 'count')"
                    @click="toggleTableSort('tags', 'count')"
                  >
                    Count
                  </th>
                  <th
                    :class="thSortClass('tags', 'min')"
                    @click="toggleTableSort('tags', 'min')"
                  >
                    Min
                  </th>
                  <th
                    :class="thSortClass('tags', 'avg')"
                    @click="toggleTableSort('tags', 'avg')"
                  >
                    Avg
                  </th>
                  <th
                    :class="thSortClass('tags', 'max')"
                    @click="toggleTableSort('tags', 'max')"
                  >
                    Max
                  </th>
                  <th
                    :class="thSortClass('tags', 'p95')"
                    @click="toggleTableSort('tags', 'p95')"
                  >
                    P95
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="row in sortedTagStats"
                  :key="row.channel"
                  class="stats-table-row clickable"
                  :title="`Open tag value plot for ${row.label}`"
                  tabindex="0"
                  @click="openTagPlot(row.channel)"
                  @keydown.enter.prevent="openTagPlot(row.channel)"
                  @keydown.space.prevent="openTagPlot(row.channel)"
                >
                  <td class="task-col">{{ row.label }}</td>
                  <td>{{ row.count }}</td>
                  <td>{{ row.min }}</td>
                  <td>{{ row.avg }}</td>
                  <td>{{ row.max }}</td>
                  <td>{{ row.p95 }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div
            class="stats-section-resizer"
            role="separator"
            aria-label="Resize tag analysis table"
            aria-orientation="horizontal"
            @mousedown.prevent="onTableResizeStart('tags', $event)"
          />
        </div>
      </template>

    </StatsSectionBlock>
    </div>
    </template>
    <div
      v-else
      class="range-hint stats-empty-hint"
      data-demo-target="stats_summary"
    >
      Open a trace file to view statistics.
    </div>
    <div
      ref="statsTailRef"
      class="stats-scroll-tail"
      aria-hidden="true"
    />
    </div>

    <!-- Export (pinned footer, matches desktop stats panel) -->
    <div class="stats-export-row">
      <button
        class="action-btn"
        data-demo-target="stats_export_csv"
        :disabled="!trace"
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
        data-demo-target="stats_export_html"
        :disabled="!trace"
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
    </div>
  </div>

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
        v-if="activePlotTabs"
        class="plot-tab-row"
        role="tablist"
        aria-label="Distribution metric"
      >
        <button
          v-for="tab in activePlotTabs"
          :key="tab.kind"
          type="button"
          class="plot-tab-btn"
          role="tab"
          :class="{ active: openPlotRef.kind === tab.kind }"
          :aria-selected="openPlotRef.kind === tab.kind"
          :title="`Show the ${tab.label} distribution`"
          @click="switchPlotTab(tab.kind)"
        >
          {{ tab.label }}
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
            ref="scatterSvgEl"
            class="plot-svg"
            :viewBox="`0 0 ${scatterModel.width} ${scatterModel.height}`"
            @mousemove="onScatterMouseMove"
            @mouseleave="onScatterMouseLeave"
          >
            <defs>
              <linearGradient
                id="plot-cross-v"
                gradientUnits="userSpaceOnUse"
                :x1="scatterCrosshair?.x ?? 0"
                :y1="scatterModel.margin.top"
                :x2="scatterCrosshair?.x ?? 0"
                :y2="scatterModel.height - scatterModel.margin.bottom"
              >
                <stop offset="0%" stop-color="var(--plot-cross)" stop-opacity="0" />
                <stop offset="50%" stop-color="var(--plot-cross)" stop-opacity="0.85" />
                <stop offset="100%" stop-color="var(--plot-cross)" stop-opacity="0" />
              </linearGradient>
              <linearGradient
                id="plot-cross-h"
                gradientUnits="userSpaceOnUse"
                :x1="scatterModel.margin.left"
                :y1="scatterCrosshair?.y ?? 0"
                :x2="scatterModel.width - scatterModel.margin.right"
                :y2="scatterCrosshair?.y ?? 0"
              >
                <stop offset="0%" stop-color="var(--plot-cross)" stop-opacity="0" />
                <stop offset="50%" stop-color="var(--plot-cross)" stop-opacity="0.85" />
                <stop offset="100%" stop-color="var(--plot-cross)" stop-opacity="0" />
              </linearGradient>
            </defs>
            <rect
              x="0"
              y="0"
              :width="scatterModel.width"
              :height="scatterModel.height"
              fill="var(--bg)"
            />
            <rect
              v-if="scatterModel.sigmaBand"
              :x="scatterModel.margin.left"
              :y="scatterModel.sigmaBand.y"
              :width="scatterModel.width - scatterModel.margin.left - scatterModel.margin.right"
              :height="scatterModel.sigmaBand.height"
              fill="#CE93D8"
              fill-opacity="0.14"
            >
              <title>Average ± one population standard deviation</title>
            </rect>

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

            <g v-if="scatterCrosshair">
              <line
                :x1="scatterCrosshair.x"
                :x2="scatterCrosshair.x"
                :y1="scatterCrosshair.plotTop"
                :y2="scatterCrosshair.plotBottom"
                class="plot-crosshair-line"
                stroke="url(#plot-cross-v)"
              />
              <line
                :x1="scatterCrosshair.plotLeft"
                :x2="scatterCrosshair.plotRight"
                :y1="scatterCrosshair.y"
                :y2="scatterCrosshair.y"
                class="plot-crosshair-line"
                stroke="url(#plot-cross-h)"
              />
              <circle
                :cx="scatterCrosshair.x"
                :cy="scatterCrosshair.y"
                r="4"
                class="plot-crosshair-ring"
              />
            </g>

            <g>
              <circle
                v-for="point in scatterModel.points"
                :key="`scatter-point-${point.index}`"
                :cx="point.x"
                :cy="point.y"
                :r="point.index === selectedPlotPoint ? 5 : 3"
                :fill="point.index === selectedPlotPoint ? '#FFFFFF' : (point.fillColor || scatterModel.color)"
                class="plot-point"
                :style="{ cursor: point.payload ? 'pointer' : 'default' }"
                @click="onPlotPointClick(point)"
              >
                <title>{{ point.label }}</title>
              </circle>
            </g>

            <!-- Tooltip drawn last so it always renders above the scatter dots -->
            <g v-if="scatterCrosshair && scatterCrosshair.tooltip">
              <rect
                :x="scatterCrosshair.tooltip.x"
                :y="scatterCrosshair.tooltip.y"
                :width="scatterCrosshair.tooltip.width"
                :height="scatterCrosshair.tooltip.height"
                rx="4"
                class="plot-crosshair-tip-bg"
              />
              <text
                :x="scatterCrosshair.tooltip.x + 6"
                :y="scatterCrosshair.tooltip.y + 12"
                class="plot-crosshair-tip-text"
              >
                {{ scatterCrosshair.tooltip.line1 }}
              </text>
              <text
                :x="scatterCrosshair.tooltip.x + 6"
                :y="scatterCrosshair.tooltip.y + 24"
                class="plot-crosshair-tip-sub"
              >
                {{ scatterCrosshair.tooltip.line2 }}
              </text>
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
          <template v-else-if="histogramModel">
            <div class="plot-histogram-toolbar">
              <label class="plot-scale-label">
                Histogram scale
                <DomSelect
                  v-model="histogramScaleMode"
                  class="plot-scale-select"
                  :options="histogramScaleOptions"
                />
              </label>
              <span class="plot-histogram-caption">{{ histogramModel.caption }}</span>
            </div>
            <svg
              ref="histogramSvgEl"
              class="plot-svg"
              :viewBox="`0 0 ${histogramModel.width} ${histogramModel.height}`"
              @mousemove="onHistogramMouseMove"
              @mouseleave="onHistogramMouseLeave"
            >
              <rect
                x="0"
                y="0"
                :width="histogramModel.width"
                :height="histogramModel.height"
                fill="var(--bg)"
              />
              <rect
                v-if="histogramModel.sigmaBand"
                :x="histogramModel.sigmaBand.x"
                :y="histogramModel.margin.top"
                :width="histogramModel.sigmaBand.width"
                :height="histogramModel.height - histogramModel.margin.top - histogramModel.margin.bottom"
                fill="#CE93D8"
                fill-opacity="0.14"
              >
                <title>Average ± one population standard deviation</title>
              </rect>

              <line
                v-for="tick in histogramModel.yTicks"
                :key="`hist-grid-${tick.index}`"
                :x1="histogramModel.margin.left"
                :x2="histogramModel.width - histogramModel.margin.right"
                :y1="tick.y"
                :y2="tick.y"
                stroke="var(--border)"
                stroke-dasharray="3 4"
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
              <line
                :x1="histogramModel.width - histogramModel.margin.right"
                :x2="histogramModel.width - histogramModel.margin.right"
                :y1="histogramModel.margin.top"
                :y2="histogramModel.height - histogramModel.margin.bottom"
                stroke="var(--fg-dim)"
                stroke-dasharray="4 3"
              />

              <g
                v-for="tick in histogramModel.yTicks"
                :key="`hist-y-${tick.index}`"
              >
                <text
                  :x="histogramModel.margin.left - 8"
                  :y="tick.y + 4"
                  text-anchor="end"
                  fill="var(--fg-dim)"
                  class="plot-axis-text"
                >
                  {{ tick.label }}
                </text>
              </g>

              <g
                v-for="tick in histogramModel.cdfTicks"
                :key="`hist-cdf-${tick.index}`"
              >
                <text
                  :x="histogramModel.width - histogramModel.margin.right + 6"
                  :y="tick.y + 4"
                  text-anchor="start"
                  fill="var(--fg-dim)"
                  class="plot-axis-text"
                >
                  {{ tick.label }}
                </text>
              </g>

              <rect
                v-for="(bar, barIndex) in histogramModel.bars"
                :key="`hist-bar-${bar.index}-${bar.kind || 'regular'}`"
                :x="bar.x"
                :y="bar.y"
                :width="bar.width"
                :height="bar.height"
                :fill="histogramModel.color"
                :fill-opacity="barIndex === histogramHoverIndex
                  ? 1
                  : (bar.kind === 'overflow' || bar.kind === 'underflow' ? 0.55 : 0.82)"
                :stroke="bar.kind === 'overflow' || bar.kind === 'underflow' ? 'var(--fg-dim)' : 'none'"
                stroke-width="1"
              />

              <polyline
                v-if="histogramModel.cdfPoints.length > 1"
                :points="histogramModel.cdfPoints.map(p => `${p.x},${p.y}`).join(' ')"
                fill="none"
                stroke="#90CAF9"
                stroke-width="1.5"
                stroke-linejoin="round"
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

              <g v-if="histogramHoverTip">
                <rect
                  :x="histogramHoverTip.x"
                  :y="histogramHoverTip.y"
                  :width="histogramHoverTip.width"
                  :height="histogramHoverTip.height"
                  rx="4"
                  class="plot-crosshair-tip-bg"
                />
                <text
                  :x="histogramHoverTip.x + 6"
                  :y="histogramHoverTip.y + 12"
                  class="plot-crosshair-tip-text"
                >
                  {{ histogramHoverTip.line1 }}
                </text>
                <text
                  :x="histogramHoverTip.x + 6"
                  :y="histogramHoverTip.y + 24"
                  class="plot-crosshair-tip-sub"
                >
                  {{ histogramHoverTip.line2 }}
                </text>
              </g>
            </svg>
          </template>
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
        <template v-if="pairPlotFocus">
          <button
            type="button"
            class="action-btn"
            title="Open the Migration Heatmap focused on this core pair"
            @click="openPairHeatmap"
          >
            Open Heatmap
          </button>
          <button
            type="button"
            class="action-btn"
            title="Open the Migration Chord Diagram with this pair highlighted"
            @click="openPairChord"
          >
            Open Chord
          </button>
        </template>
        <span class="plot-footer-spacer" />
        <button
          type="button"
          class="action-btn"
          :disabled="!aiFeatureEnabled"
          :title="aiFeatureEnabled
            ? 'Open the AI Assistant and explain this distribution'
            : 'Enable AI Assistant in Settings → AI'"
          @click="queryDistributionWithAi('plot')"
        >
          Query with AI…
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onBeforeUnmount, nextTick } from 'vue'
import DomSelect from './DomSelect.vue'
import { toBlob as domToBlob, toSvg as domToSvg } from 'html-to-image'
import { formatTime, isStiTagChannel } from '../renderer/TimelineRenderer.js'
import { formatTimeFixed } from '../utils/timeFormat.js'
import { taskDisplayName, parseTaskName, taskMergeKey, isIdleTaskName, taskColor, taskReprGet, taskLabelForMergeKey, coreColor } from '../utils/colors.js'
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
  findPercentileExecSegment,
  findPercentileBlockingSegment,
  findPercentileInterArrivalSegment,
  extremeSegmentNote,
  preemptionChainRows,
  preemptionChainPlotPoints,
  PREEMPTION_CHAIN_MAX_ROWS,
} from '../utils/statsAnalysis.js'
import {
  intervalStatsRows,
  intervalPlotPoints,
  intervalColor,
} from '../utils/intervalAnalysis.js'
import {
  tagStatsRows,
  tagPlotPoints,
  tagIntervalPlotPoints,
  tagColor,
  tagChannelLabel,
  formatTagValue,
  tagSampleDetailRows,
} from '../utils/tagAnalysis.js'
import { priorityStatsRows, priorityEpisodePlotPoints, priorityEpisodeDetailRows, BOOST_BAND_COLOR, INVERSION_BAND_COLOR } from '../utils/priorityAnalysis.js'
import {
  syncObjectStatsRows,
  syncObjectIssueRows,
  syncObjectHoldDetailRows,
  segmentAtCoreTime,
  syncIssueAnnotationNote,
} from '../utils/syncObjectAnalysis.js'
import { buildTaskLifecycleRows, formatLifecycleSpan } from '../utils/lifecycleAnalysis.js'
import { buildCoreAffinityRows } from '../utils/coreAffinityAnalysis.js'
import { formatMigrationGapTime } from '../utils/timeFormat.js'
import { computeDeadlineViolations, deadlineSliceAnnotationNote } from '../utils/deadlineAnalysis.js'
import { intervalInstanceDetailRows } from '../utils/intervalAnalysis.js'
import { migrationRows, buildCorePairRows, buildCoreTimeBreakdown, migrationDwellPlotPoints, migrationRatePlotPoints, migrationGapPlotPoints, pairGapPlotPoints, pairRatePlotPoints, pairPlotKey, pairMigrations, pairBouncePrefer, buildLockBounceNsSet } from '../utils/migrationAnalysis.js'
import { dispatchLatencyRows, switchOverheadRows, concurrentCoreActiveRows, dispatchLatencyPlotPoints, switchOverheadPlotPoints, concurrencyLevelPlotPoints, collectDispatchLatencyByMk } from '../utils/schedulerSmpMetrics.js'
import { coreUtilPctRows } from '../utils/traceCompare.js'
import { renderWorkflowAnalysisHtml, collectTraceAnalysisFindings } from '../utils/workflowAnalysis.js'
import { capStatsTableRows } from '../utils/statsLoad.js'
import {
  STATS_CORES_DEFAULT_VISIBLE_ROWS,
  STATS_DEFAULT_EXPANDED_SECTIONS,
  STATS_LB_GAUGE_H,
  STATS_MAX_VISIBLE_ROWS,
  STATS_TABLE_HEADER_H,
  STATS_TABLE_HSCROLL_H,
  STATS_TABLE_MAX_H,
  STATS_TABLE_MIN_H,
  STATS_TABLE_ROW_H,
  STATS_TABLE_WRAP_BORDER,
  STATS_UTIL_ROW_GAP,
  STATS_UTIL_ROW_H,
} from '../config.js'
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
  INTERVAL_SORT_ACCESSORS,
  TAG_SORT_ACCESSORS,
  PRIORITY_SORT_ACCESSORS,
  SYNC_OBJECT_SORT_ACCESSORS,
  SYNC_ISSUE_SORT_ACCESSORS,
  CORE_BREAKDOWN_SORT_ACCESSORS,
  CONCURRENCY_SORT_ACCESSORS,
  SWITCH_OVERHEAD_SORT_ACCESSORS,
  DISPATCH_SORT_ACCESSORS,
  CORE_PAIR_SORT_ACCESSORS,
  LIFECYCLE_SORT_ACCESSORS,
  AFFINITY_SORT_ACCESSORS,
  DEADLINE_SLICE_SORT_ACCESSORS,
  DEADLINE_CPU_SORT_ACCESSORS,
  ANOMALY_SORT_ACCESSORS,
  CRIT_PATH_SORT_ACCESSORS,
  PATTERN_SORT_ACCESSORS,
  PERIOD_SORT_ACCESSORS,
  RESPONSE_SORT_ACCESSORS,
  JITTER_SORT_ACCESSORS,
  PREEMPT_RANK_SORT_ACCESSORS,
  MUTEX_BLOCK_SORT_ACCESSORS,
  BLOCKER_SORT_ACCESSORS,
  TASK_HEALTH_SORT_ACCESSORS,
  CORE_TIME_BIN_SORT_ACCESSORS,
} from '../utils/statsTableSort.js'
import LoadBalanceGauge from './LoadBalanceGauge.vue'
import StatsSectionHeader from './StatsSectionHeader.vue'
import StatsSectionBlock from './StatsSectionBlock.vue'
import { normalizeStatsPins, normalizeStatsSectionOrder, moveStatsSection, toggleStatsPin, isDefaultStatsSectionOrder, defaultStatsSectionOrder, mergeSectionCollapsed } from '../utils/statsPins.js'
import { buildHistogramModel, histogramBarTooltip } from '../utils/histogramModel.js'
import { plotTabsForKind, resolvePlotTabSwitch } from '../utils/plotTabs.js'
import { classifyLoadBalance, loadBalanceGaugeImgHtml, loadBalanceMetrics } from '../utils/loadBalanceGauge.js'
import { btfHtmlReportDocument, htmlApplyCollapsibleToc, htmlMakeCollapsibleSections, HTML_REPORT_TOC_SCRIPT, HTML_REPORT_INTERACTIVE_SCRIPT } from '../utils/htmlReport.js'
import {
  STATS_DEFAULT_EXPANDED,
  STATS_HTML_EXTRA_CSS,
  STATS_TOC_GROUPS,
  htmlDiagnosticKpiGrid,
  htmlGlossary,
  htmlHealthBars,
  htmlInvestigateAnomalies,
  htmlMatrixHeatmap,
  htmlPercentileBars,
  htmlScopeIdentityCard,
  htmlTagOverview,
  htmlTraceMetadataCard,
} from '../utils/statsHtmlReport.js'
import {
  HEALTH_BAND_SECTION,
  analyzeResponseTimes,
  analyzeTaskPeriods,
  collectWorstEvents,
  coreUtilOverTime,
  criticalPathRows,
  detectTimelineAnomalies,
  distributionExplorer,
  distributionMetricSamples,
  harvestMutexHolds,
  harvestUxEvents,
  healthInputsFromEvents,
  KIND_LABEL,
  mutexBlockingTable,
  pairMutexWaits,
  preemptionMatrix,
  preemptionPairs,
  preemptorRanking,
  recurringPatterns,
  topBlockingContributors,
  taskCoreMatrix,
  taskHealthScores,
  unifiedJitter,
  waiterOwnerMatrix,
} from '../utils/uxExplore.js'

const props = defineProps({
  trace:   { type: Object, default: null },
  cursors: { type: Array, default: () => [] },
  tabs:    { type: Array, default: () => [] },
  statsPaused: { type: Boolean, default: false },
  openPlot: { type: Object, default: null },
  sectionHeights: { type: Object, default: null },
  scopeToCursors: { type: Boolean, default: true },
  analysisSettings: { type: Object, default: () => ({}) },
  sectionCollapsedState: { type: Object, default: null },
  sectionPins: { type: Array, default: () => [] },
  sectionOrder: { type: Array, default: () => [] },
  activeFilterLabel: { type: String, default: null },
})

const emit = defineEmits([
  'highlightTask', 'plotPointActivate', 'segmentJump', 'update:openPlot', 'update:sectionHeights',
  'update:scopeToCursors', 'update:sectionCollapsedState', 'update:sectionPins',
  'update:sectionOrder',
  'openPairHeatmap', 'openPairChord', 'openSettings',
  'exploreRange', 'query-ai',
])

const aiFeatureEnabled = computed(() => props.analysisSettings?.aiEnabled !== false)

function defaultSectionCollapsed(id) {
  return !STATS_DEFAULT_EXPANDED_SECTIONS.includes(id)
}

const coresCollapsed = ref(defaultSectionCollapsed('cores'))
const tasksCollapsed = ref(defaultSectionCollapsed('tasks'))
const healthCollapsed = ref(defaultSectionCollapsed('health'))
const anomaliesCollapsed = ref(defaultSectionCollapsed('anomalies'))
const worstCollapsed = ref(defaultSectionCollapsed('worst'))
const execSliceCollapsed = ref(defaultSectionCollapsed('exec'))
const blockingCollapsed = ref(defaultSectionCollapsed('block'))
const migrationCollapsed = ref(defaultSectionCollapsed('migrations'))
const interArrivalCollapsed = ref(defaultSectionCollapsed('inter'))
const preemptionCollapsed = ref(defaultSectionCollapsed('preemption'))
const priorityCollapsed = ref(defaultSectionCollapsed('priority'))
const syncCollapsed = ref(defaultSectionCollapsed('sync'))
const queueCollapsed = ref(defaultSectionCollapsed('queue'))
const lifecycleCollapsed = ref(defaultSectionCollapsed('lifecycle'))
const deadlineCollapsed = ref(defaultSectionCollapsed('deadline'))
const intervalsCollapsed = ref(defaultSectionCollapsed('intervals'))
const tagsCollapsed = ref(defaultSectionCollapsed('tags'))
const corePairsCollapsed = ref(defaultSectionCollapsed('core_pairs'))
const coreBreakdownCollapsed = ref(defaultSectionCollapsed('core_breakdown'))
const concurrencyCollapsed = ref(defaultSectionCollapsed('concurrency'))
const switchOverheadCollapsed = ref(defaultSectionCollapsed('switch_overhead'))
const dispatchCollapsed = ref(defaultSectionCollapsed('dispatch'))
const affinityCollapsed = ref(defaultSectionCollapsed('affinity'))
const periodCollapsed = ref(defaultSectionCollapsed('period'))
const taskCoreCollapsed = ref(defaultSectionCollapsed('task_core'))
const waitOwnerCollapsed = ref(defaultSectionCollapsed('wait_owner'))
const taskHealthCollapsed = ref(defaultSectionCollapsed('task_health'))
const responseCollapsed = ref(defaultSectionCollapsed('response'))
const critPathCollapsed = ref(defaultSectionCollapsed('crit_path'))
const preemptMatrixCollapsed = ref(defaultSectionCollapsed('preempt_matrix'))
const mutexBlockCollapsed = ref(defaultSectionCollapsed('mutex_block'))
const coreTimeCollapsed = ref(defaultSectionCollapsed('core_time'))
const jitterCollapsed = ref(defaultSectionCollapsed('jitter'))
const distribCollapsed = ref(defaultSectionCollapsed('distrib'))
const patternsCollapsed = ref(defaultSectionCollapsed('patterns'))
const lastAnomaly = ref(null)
const distribKind = ref('exec')
const distribMk = ref('')
const distribScaleMode = ref('auto')
const distribKindOptions = [
  { id: 'exec', label: 'Execution' },
  { id: 'block', label: 'Blocking' },
  { id: 'inter', label: 'Inter-arrival' },
  { id: 'response', label: 'Response' },
  { id: 'dispatch', label: 'Dispatch' },
  { id: 'wakeup', label: 'Wake (stand-in)' },
  { id: 'preempt', label: 'Preemption' },
]
const distribKindSelectOptions = distribKindOptions.map(k => ({ value: k.id, label: k.label }))
const plotScaleOptions = [
  { value: 'auto', label: 'Auto' },
  { value: 'linear', label: 'Linear' },
  { value: 'percentile', label: 'p5–p95' },
  { value: 'log', label: 'Log duration' },
]

function formatMigGapNs(ns) {
  return formatMigrationGapTime(ns, props.trace?.timeScale ?? 'us')
}

const scopeToCursorsModel = computed({
  get: () => props.scopeToCursors,
  set: (v) => emit('update:scopeToCursors', v),
})

const SECTION_COLLAPSE_REFS = {
  cores: coresCollapsed,
  core_breakdown: coreBreakdownCollapsed,
  concurrency: concurrencyCollapsed,
  switch_overhead: switchOverheadCollapsed,
  tasks: tasksCollapsed,
  health: healthCollapsed,
  migrations: migrationCollapsed,
  core_pairs: corePairsCollapsed,
  exec: execSliceCollapsed,
  block: blockingCollapsed,
  dispatch: dispatchCollapsed,
  inter: interArrivalCollapsed,
  preemption: preemptionCollapsed,
  priority: priorityCollapsed,
  sync: syncCollapsed,
  queue: queueCollapsed,
  lifecycle: lifecycleCollapsed,
  affinity: affinityCollapsed,
  task_core: taskCoreCollapsed,
  core_time: coreTimeCollapsed,
  deadline: deadlineCollapsed,
  task_health: taskHealthCollapsed,
  anomalies: anomaliesCollapsed,
  worst: worstCollapsed,
  crit_path: critPathCollapsed,
  patterns: patternsCollapsed,
  response: responseCollapsed,
  period: periodCollapsed,
  jitter: jitterCollapsed,
  distrib: distribCollapsed,
  preempt_matrix: preemptMatrixCollapsed,
  wait_owner: waitOwnerCollapsed,
  mutex_block: mutexBlockCollapsed,
  intervals: intervalsCollapsed,
  tags: tagsCollapsed,
}

const STATS_SECTION_FLAGS = Object.values(SECTION_COLLAPSE_REFS)

const pinnedSet = computed(() => new Set(normalizeStatsPins(props.sectionPins)))

function isSectionPinned(id) {
  return pinnedSet.value.has(id)
}

function toggleSectionPin(id) {
  emit('update:sectionPins', toggleStatsPin(props.sectionPins, id))
  const flag = SECTION_COLLAPSE_REFS[id]
  if (flag) flag.value = false
  emitCollapsedState()
}

const orderedSectionIds = computed(() => normalizeStatsSectionOrder(props.sectionOrder))

const sectionOrderIsCustom = computed(
  () => !isDefaultStatsSectionOrder(props.sectionOrder))

function sectionOrderIndex(id) {
  const idx = orderedSectionIds.value.indexOf(id)
  return idx < 0 ? 999 : idx
}

function onSectionReorder(src, dst) {
  emit('update:sectionOrder', moveStatsSection(props.sectionOrder, src, dst))
}

function resetSectionOrder() {
  if (!sectionOrderIsCustom.value) return
  emit('update:sectionOrder', defaultStatsSectionOrder())
}

function toggleSectionCollapse(id) {
  if (isSectionPinned(id)) return
  const flag = SECTION_COLLAPSE_REFS[id]
  if (flag) flag.value = !flag.value
  emitCollapsedState()
}

function expandAllSections() {
  for (const flag of STATS_SECTION_FLAGS) flag.value = false
  emitCollapsedState()
}

function collapseAllSections() {
  for (const [id, flag] of Object.entries(SECTION_COLLAPSE_REFS)) {
    if (pinnedSet.value.has(id)) continue
    flag.value = true
  }
  emitCollapsedState()
}

const statsBodyRef = ref(null)
const statsTailRef = ref(null)

function sleepMs(ms) {
  return new Promise(resolve => setTimeout(resolve, ms))
}

function updateScrollTailHeight() {
  // Web parity with desktop: keep the tail at 0 during normal browsing so the
  // last section (Tag Analysis) has no blank below it. Grow only while a
  // demo/AI scroll pins a section header near the top of the viewport.
  const body = statsBodyRef.value
  const tail = statsTailRef.value
  if (!body || !tail) return
  const vh = body.clientHeight
  tail.style.height = `${Math.max(0, vh - 48)}px`
}

function clearScrollTailPin() {
  const tail = statsTailRef.value
  if (tail) tail.style.height = '0px'
}

function parseDemoSectionIds(raw) {
  if (Array.isArray(raw)) return raw.map(x => String(x).trim()).filter(Boolean)
  return String(raw || '').replace(/;/g, ',').split(',').map(s => s.trim()).filter(Boolean)
}

async function scrollDemoSectionIntoView(scroll, ids, expand) {
  const body = statsBodyRef.value
  if (!body) return
  const key = String(scroll || '').trim().toLowerCase()
  if (['top', '0', 'start'].includes(key)) {
    clearScrollTailPin()
    body.scrollTop = 0
    return
  }
  if (!expand || !ids.length) return
  let focus = ids[0]
  if (key && !['section', 'focus', '1', 'true', 'yes', ''].includes(key)) {
    if (SECTION_COLLAPSE_REFS[key] || ids.includes(key)) focus = key
  }
  updateScrollTailHeight()
  let elapsed = 0
  for (const mark of [0, 50, 150, 280]) {
    if (mark > elapsed) await sleepMs(mark - elapsed)
    elapsed = mark
    await nextTick()
    const el = body.querySelector(`[data-section-id="${focus}"]`)
    if (!el) continue
    const bodyRect = body.getBoundingClientRect()
    const elRect = el.getBoundingClientRect()
    body.scrollTop += elRect.top - bodyRect.top - 8
  }
}

async function applyDemoSections(payload = {}) {
  const ids = parseDemoSectionIds(payload.id ?? payload.ids ?? payload.section)
  const expand = payload.expand !== false
  const collapseOthers = payload.collapse_others != null
    ? !!payload.collapse_others
    : ids.length > 0
  let scroll = String(payload.scroll || '').trim().toLowerCase()
  if (!scroll && expand && ids.length) scroll = 'section'

  if (collapseOthers) {
    for (const [id, flag] of Object.entries(SECTION_COLLAPSE_REFS)) {
      if (ids.includes(id) || pinnedSet.value.has(id)) continue
      flag.value = true
    }
  }
  for (const id of ids) {
    const flag = SECTION_COLLAPSE_REFS[id]
    if (flag && !pinnedSet.value.has(id)) flag.value = !expand
  }
  await nextTick()
  updateScrollTailHeight()
  await scrollDemoSectionIntoView(scroll, ids, expand)
  return { ids, expand, collapse_others: collapseOthers, scroll }
}

function applyCollapsedState(state) {
  const merged = mergeSectionCollapsed(state)
  for (const [id, flag] of Object.entries(SECTION_COLLAPSE_REFS)) {
    flag.value = !!merged[id]
  }
}

function snapshotCollapsedState() {
  const out = {}
  for (const [id, flag] of Object.entries(SECTION_COLLAPSE_REFS)) {
    out[id] = !!flag.value
  }
  return out
}

function emitCollapsedState() {
  emit('update:sectionCollapsedState', snapshotCollapsedState())
}

watch(() => props.sectionCollapsedState, (state) => {
  applyCollapsedState(state)
}, { deep: true, immediate: true })

watch(pinnedSet, (pins) => {
  for (const id of pins) {
    const flag = SECTION_COLLAPSE_REFS[id]
    if (flag) flag.value = false
  }
}, { immediate: true })

const workerExecRows = ref([])
const workerBlockRows = ref([])
const workerInterRows = ref([])
const workerTaskCpuNs = ref(null)
const preemptionRows = ref([])
const preemptionTruncated = ref(false)
const preemptionComputing = ref(false)
let _statsRefreshTimer = null
let _preemptionGen = 0

function formatStatsRow(row, scale) {
  return {
    ...row,
    minNs: row.min,
    avgNs: row.avg,
    maxNs: row.max,
    jitterNs: row.jitter,
    stddevNs: row.stddev,
    p95Ns: row.p95,
    p99Ns: row.p99,
    min: formatTime(row.min, scale),
    avg: formatTime(row.avg, scale),
    max: formatTime(row.max, scale),
    jitter: formatTime(row.jitter, scale),
    stddev: formatTime(row.stddev, scale),
    p95: formatTime(row.p95, scale),
    p99: formatTime(row.p99, scale),
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

function schedulePreemptionRefresh() {
  if (preemptionCollapsed.value || props.statsPaused) {
    preemptionRows.value = []
    preemptionTruncated.value = false
    preemptionComputing.value = false
    return
  }
  const tr = props.trace
  if (!tr) {
    preemptionRows.value = []
    preemptionTruncated.value = false
    preemptionComputing.value = false
    return
  }
  const gen = ++_preemptionGen
  preemptionComputing.value = true
  const r = statsRange.value
  const lo = r?.lo ?? null
  const hi = r?.hi ?? null
  setTimeout(() => {
    if (gen !== _preemptionGen) return
    const { rows, truncated } = preemptionChainRows(tr, lo, hi)
    preemptionRows.value = rows
    preemptionTruncated.value = truncated
    preemptionComputing.value = false
  }, 0)
}

function scheduleStatsRefresh() {
  if (props.statsPaused) return
  clearTimeout(_statsRefreshTimer)
  _statsRefreshTimer = setTimeout(() => { refreshStatsTables() }, 120)
}

const TABLE_MIN_H = STATS_TABLE_MIN_H
const TABLE_MAX_H = STATS_TABLE_MAX_H

function statsTableViewportHeight(visibleRows = STATS_MAX_VISIBLE_ROWS, reserveHScroll = false) {
  let h = STATS_TABLE_HEADER_H + visibleRows * STATS_TABLE_ROW_H + STATS_TABLE_WRAP_BORDER
  if (reserveHScroll) h += STATS_TABLE_HSCROLL_H
  return h
}

function utilRowsHeight(visibleRows) {
  return visibleRows * STATS_UTIL_ROW_H + Math.max(0, visibleRows - 1) * STATS_UTIL_ROW_GAP + 2
}

function coresUtilViewportHeight(visibleRows, includeGauge) {
  return utilRowsHeight(visibleRows) + (includeGauge ? STATS_LB_GAUGE_H : 0)
}

const STATS_TABLE_DEFAULT_H = statsTableViewportHeight()
const STATS_TABLE_MIG_DEFAULT_H = statsTableViewportHeight(STATS_MAX_VISIBLE_ROWS, true)
const STATS_UTIL_DEFAULT_H = utilRowsHeight(STATS_MAX_VISIBLE_ROWS)
const STATS_CORES_UTIL_DEFAULT_H = coresUtilViewportHeight(
  STATS_CORES_DEFAULT_VISIBLE_ROWS, true)
const STATS_UTIL_MIN_H = utilRowsHeight(1)

const DEFAULT_LOCAL_SECTION_HEIGHTS = {
  tasks: STATS_UTIL_DEFAULT_H,
  migrations: STATS_TABLE_MIG_DEFAULT_H,
  anomalies: STATS_TABLE_DEFAULT_H,
  worst: STATS_TABLE_DEFAULT_H,
  period: STATS_TABLE_DEFAULT_H,
  task_core: STATS_TABLE_DEFAULT_H,
  wait_owner: STATS_TABLE_DEFAULT_H,
  task_health: STATS_TABLE_DEFAULT_H,
  exec: STATS_TABLE_DEFAULT_H,
  block: STATS_TABLE_DEFAULT_H,
  dispatch: STATS_TABLE_DEFAULT_H,
  inter: STATS_TABLE_DEFAULT_H,
  preemption: STATS_TABLE_MIG_DEFAULT_H,
  priority: STATS_TABLE_DEFAULT_H,
  sync: STATS_TABLE_DEFAULT_H,
  sync_issues: STATS_TABLE_MIG_DEFAULT_H,
  queue: STATS_TABLE_DEFAULT_H,
  lifecycle: STATS_TABLE_DEFAULT_H,
  health: STATS_TABLE_DEFAULT_H,
  intervals: STATS_TABLE_DEFAULT_H,
  tags: STATS_TABLE_DEFAULT_H,
  concurrency: STATS_TABLE_DEFAULT_H,
  switch_overhead: STATS_TABLE_DEFAULT_H,
}
const localSectionHeights = ref({ ...DEFAULT_LOCAL_SECTION_HEIGHTS })
watch(() => props.sectionHeights, (v) => {
  const next = { ...DEFAULT_LOCAL_SECTION_HEIGHTS, ...(v || {}) }
  // Older sessions stored cores height as util-rows only (gauges were outside
  // the scroll). Bump those so the default viewport still shows gauges + 2 cores.
  if (next.cores != null && next.cores < STATS_LB_GAUGE_H) {
    next.cores = STATS_CORES_UTIL_DEFAULT_H
  }
  localSectionHeights.value = next
}, { immediate: true, deep: true })
let _tableResize = null
const openPlotRef = computed({
  get: () => props.openPlot,
  set: (v) => emit('update:openPlot', v),
})
const plotContentRef = ref(null)
const scatterSvgEl = ref(null)
const histogramSvgEl = ref(null)
const selectedPlotPoint = ref(-1)
const plotHoverPointIndex = ref(-1)
const histogramHoverIndex = ref(-1)
const histogramScaleMode = ref('auto')

const tableSort = ref({
  migrations: defaultStatsTableSort(),
  exec: defaultStatsTableSort(),
  block: defaultStatsTableSort(),
  dispatch: defaultStatsTableSort(),
  inter: defaultStatsTableSort(),
  health: defaultStatsTableSort(),
  preemption: defaultStatsTableSort(),
  priority: defaultStatsTableSort(),
  sync: defaultStatsTableSort(),
  sync_issues: defaultStatsTableSort(),
  intervals: defaultStatsTableSort(),
  tags: defaultStatsTableSort(),
  core_breakdown: defaultStatsTableSort(),
  concurrency: defaultStatsTableSort(),
  switch_overhead: defaultStatsTableSort(),
  core_pairs: defaultStatsTableSort(),
  queue: defaultStatsTableSort(),
  lifecycle: defaultStatsTableSort(),
  affinity: defaultStatsTableSort(),
  deadline_slice: defaultStatsTableSort(),
  deadline_cpu: defaultStatsTableSort(),
  anomalies: defaultStatsTableSort(),
  worst: defaultStatsTableSort(),
  crit_path: defaultStatsTableSort(),
  patterns: defaultStatsTableSort(),
  period: defaultStatsTableSort(),
  response: defaultStatsTableSort(),
  jitter: defaultStatsTableSort(),
  preempt_rank: defaultStatsTableSort(),
  preempt_matrix: defaultStatsTableSort(),
  wait_owner: defaultStatsTableSort(),
  mutex_block: defaultStatsTableSort(),
  mutex_blockers: defaultStatsTableSort(),
  task_core: defaultStatsTableSort(),
  core_time: defaultStatsTableSort(),
  task_health: defaultStatsTableSort(),
})

function toggleTableSort(tableId, col) {
  tableSort.value[tableId] = nextSortState(tableSort.value[tableId], col)
}

function thSortClass(tableId, col) {
  return sortHeaderClass(tableSort.value[tableId], col)
}

function clampPct(v) { return Math.max(0, Math.min(100, v)).toFixed(1) }

function tableHeight(id) {
  if (localSectionHeights.value[id] != null) return localSectionHeights.value[id]
  // Auto-size small-row sections to exact content height (all wraps use
  // max-height, so this only matters for the initial/default size).
  if (id === 'core_breakdown') {
    return statsTableViewportHeight(Math.min(Math.max(coreTimeBreakdown.value.length, 1), STATS_MAX_VISIBLE_ROWS))
  }
  if (id === 'concurrency') {
    return statsTableViewportHeight(Math.min(Math.max(concurrentCoreStats.value.length, 1), STATS_MAX_VISIBLE_ROWS))
  }
  if (id === 'switch_overhead') {
    return statsTableViewportHeight(Math.min(Math.max(switchOverheadStats.value.length, 1), STATS_MAX_VISIBLE_ROWS))
  }
  if (id === 'core_pairs') {
    return statsTableViewportHeight(Math.min(Math.max(corePairRows.value.length, 1), STATS_MAX_VISIBLE_ROWS))
  }
  if (id === 'affinity') {
    return statsTableViewportHeight(Math.min(Math.max(coreAffinityRows.value.length, 1), STATS_MAX_VISIBLE_ROWS))
  }
  if (id === 'cores') {
    const rows = Math.min(Math.max(coreStats.value.length, 1), STATS_CORES_DEFAULT_VISIBLE_ROWS)
    return coresUtilViewportHeight(rows, !!loadBalanceScore.value)
  }
  return id === 'migrations' ? STATS_TABLE_MIG_DEFAULT_H : STATS_TABLE_DEFAULT_H
}

function utilScrollStyle(rowCount, id = null) {
  let h
  if (id != null && localSectionHeights.value[id] != null) {
    h = localSectionHeights.value[id]
  } else if (id === 'cores') {
    const vis = Math.min(Math.max(rowCount, 1), STATS_CORES_DEFAULT_VISIBLE_ROWS)
    h = coresUtilViewportHeight(vis, !!loadBalanceScore.value)
  } else {
    const maxRows = STATS_MAX_VISIBLE_ROWS
    const vis = Math.min(Math.max(rowCount, 1), maxRows)
    h = utilRowsHeight(vis)
  }
  return { height: `${h}px`, overflowY: 'auto', overflowX: 'hidden', flexShrink: '0' }
}

// Snap a dragged section height to the nearest whole-row increment so the
// last visible row is never partially clipped (which made it look like the
// row height "changes" while resizing).
function quantizeSectionHeight(id, rawH, rowCount = null) {
  if (id === 'cores' || id === 'tasks') {
    const unit = STATS_UTIL_ROW_H + STATS_UTIL_ROW_GAP
    const gaugeH = (id === 'cores' && loadBalanceScore.value) ? STATS_LB_GAUGE_H : 0
    const bodyH = Math.max(0, rawH - gaugeH)
    let minRows = Math.max(1, Math.ceil((STATS_UTIL_MIN_H + STATS_UTIL_ROW_GAP - 2) / unit))
    // Don't force space for more rows than actually exist (e.g. a 2-core
    // trace should be shrinkable down to 2 rows, not stuck at the 5-row min).
    if (rowCount != null) minRows = Math.min(minRows, Math.max(1, rowCount))
    const maxRows = Math.max(minRows, Math.floor((TABLE_MAX_H - gaugeH + STATS_UTIL_ROW_GAP - 2) / unit))
    const rows = Math.min(maxRows, Math.max(minRows, Math.round((bodyH + STATS_UTIL_ROW_GAP - 2) / unit)))
    return gaugeH + rows * STATS_UTIL_ROW_H + (rows - 1) * STATS_UTIL_ROW_GAP + 2
  }
  const base = STATS_TABLE_HEADER_H + STATS_TABLE_WRAP_BORDER
  const minRows = Math.max(1, Math.ceil((TABLE_MIN_H - base) / STATS_TABLE_ROW_H))
  const maxRows = Math.max(minRows, Math.floor((TABLE_MAX_H - base) / STATS_TABLE_ROW_H))
  const rows = Math.min(maxRows, Math.max(minRows, Math.round((rawH - base) / STATS_TABLE_ROW_H)))
  return base + rows * STATS_TABLE_ROW_H
}

function onTableResizeStart(id, e, rowCount = null) {
  _tableResize = { id, startY: e.clientY, startH: tableHeight(id), rowCount }
  document.body.classList.add('row-resizing')
  document.addEventListener('mousemove', onTableResizeMove)
  document.addEventListener('mouseup', onTableResizeEnd)
}

function onTableResizeMove(e) {
  if (!_tableResize) return
  const delta = e.clientY - _tableResize.startY
  localSectionHeights.value[_tableResize.id] = quantizeSectionHeight(_tableResize.id, _tableResize.startH + delta, _tableResize.rowCount)
}

function onTableResizeEnd() {
  _tableResize = null
  document.body.classList.remove('row-resizing')
  document.removeEventListener('mousemove', onTableResizeMove)
  document.removeEventListener('mouseup', onTableResizeEnd)
  emit('update:sectionHeights', { ...localSectionHeights.value })
}

onBeforeUnmount(() => {
  clearTimeout(_statsRefreshTimer)
  _preemptionGen++
  onTableResizeEnd()
})

const placedCursorCount = computed(() => getPlacedCursors(props.cursors).length)

const statsRange = computed(() => getStatsRange(props.cursors, scopeToCursorsModel.value))

const scopeSuffixStr = computed(() => scopeSuffix(statsRange.value))
const timeScale = computed(() => props.trace?.timeScale || 'ns')
const uxEvents = computed(() => {
  const tr = props.trace
  if (!tr) return []
  const r = statsRange.value
  return harvestUxEvents(tr, r?.lo ?? null, r?.hi ?? null)
})
const dispatchSampleMap = computed(() => {
  const tr = props.trace
  if (!tr) return {}
  const r = statsRange.value
  const map = {}
  for (const [mk, data] of collectDispatchLatencyByMk(tr, r?.lo ?? null, r?.hi ?? null)) {
    const samples = (data.samples || []).map(v => Math.trunc(v || 0)).filter(v => v > 0)
    if (samples.length) map[mk] = samples
  }
  return map
})
const mutexWaitRows = computed(() => {
  const tr = props.trace
  if (!tr) return []
  const r = statsRange.value
  return pairMutexWaits(harvestMutexHolds(tr, r?.lo ?? null, r?.hi ?? null))
})
const anomalyRows = computed(() => detectTimelineAnomalies(
  uxEvents.value, 12, mutexWaitRows.value, props.analysisSettings?.taskDeadlines || {},
))
const sortedAnomalyRows = computed(() =>
  sortStatsRows(anomalyRows.value, tableSort.value.anomalies, ANOMALY_SORT_ACCESSORS))
const worstRows = computed(() => collectWorstEvents(uxEvents.value, 12))
const sortedWorstRows = computed(() =>
  sortStatsRows(worstRows.value, tableSort.value.worst, ANOMALY_SORT_ACCESSORS))
const responseModel = computed(() => analyzeResponseTimes(uxEvents.value))
const responseRows = computed(() => responseModel.value.rows || [])
const sortedResponseRows = computed(() =>
  sortStatsRows(responseRows.value, tableSort.value.response, RESPONSE_SORT_ACCESSORS))
const critPathRows = computed(() => criticalPathRows(uxEvents.value, 8))
const sortedCritPathRows = computed(() =>
  sortStatsRows(critPathRows.value, tableSort.value.crit_path, CRIT_PATH_SORT_ACCESSORS))
const preemptPairRows = computed(() => preemptionPairs(uxEvents.value))
const preemptRankRows = computed(() => preemptorRanking(preemptPairRows.value, 16))
const sortedPreemptRankRows = computed(() =>
  sortStatsRows(preemptRankRows.value, tableSort.value.preempt_rank, PREEMPT_RANK_SORT_ACCESSORS))
const preemptMatrixModel = computed(() => preemptionMatrix(preemptPairRows.value, 12))
const sortedPreemptMatrixTasks = computed(() => {
  const tasks = preemptMatrixModel.value.tasks || []
  const cells = preemptMatrixModel.value.cells || {}
  const acc = { victim: t => String(t.task || '').toLowerCase() }
  for (const col of tasks) {
    acc[col.mk] = victim => Number(cells[`${victim.mk}|${col.mk}`]?.ns || 0)
  }
  return sortStatsRows(tasks, tableSort.value.preempt_matrix, acc)
})
const mutexBlockRows = computed(() => mutexBlockingTable(mutexWaitRows.value))
const sortedMutexBlockRows = computed(() =>
  sortStatsRows(mutexBlockRows.value, tableSort.value.mutex_block, MUTEX_BLOCK_SORT_ACCESSORS))
const blockerRows = computed(() => topBlockingContributors(uxEvents.value, mutexWaitRows.value, 12))
const sortedBlockerRows = computed(() =>
  sortStatsRows(blockerRows.value, tableSort.value.mutex_blockers, BLOCKER_SORT_ACCESSORS))
const coreTimeModel = computed(() => {
  const tr = props.trace
  const r = statsRange.value
  return coreUtilOverTime(
    uxEvents.value,
    tr?.coreNames || tr?.core_names || [],
    r?.lo ?? null,
    r?.hi ?? null,
  )
})
const sortedCoreTimeBins = computed(() => {
  const cores = coreTimeModel.value.cores || []
  const acc = { ...CORE_TIME_BIN_SORT_ACCESSORS }
  for (const core of cores) {
    acc[core] = row => Number(row.cells?.[core]?.pct || 0)
  }
  return sortStatsRows(coreTimeModel.value.bins || [], tableSort.value.core_time, acc)
})
const jitterRows = computed(() => unifiedJitter(uxEvents.value, dispatchSampleMap.value))
const sortedJitterRows = computed(() =>
  sortStatsRows(jitterRows.value, tableSort.value.jitter, JITTER_SORT_ACCESSORS))
watch(jitterRows, (rows) => {
  if (distribMk.value || !rows.length) return
  distribMk.value = String(rows[0].mk || '')
}, { immediate: true })
const distribTaskOptions = computed(() => [
  { value: '', label: '(select)' },
  ...jitterRows.value.map(row => ({ value: row.mk, label: row.task })),
])
const patternRows = computed(() => recurringPatterns(anomalyRows.value, 2))
const sortedPatternRows = computed(() =>
  sortStatsRows(patternRows.value, tableSort.value.patterns, PATTERN_SORT_ACCESSORS))

const statsSpanNs = computed(() => {
  const r = statsRange.value
  const tr = props.trace
  if (r) return Math.max(1, r.hi - r.lo)
  if (!tr) return 1
  return Math.max(1, (tr.timeMax ?? tr.time_max ?? 0) - (tr.timeMin ?? tr.time_min ?? 0))
})

const periodRows = computed(() => analyzeTaskPeriods(uxEvents.value, 3))
const sortedPeriodRows = computed(() =>
  sortStatsRows(periodRows.value, tableSort.value.period, PERIOD_SORT_ACCESSORS))

const taskCoreModel = computed(() => {
  const tr = props.trace
  const cores = tr?.coreNames || tr?.core_names || []
  return taskCoreMatrix(uxEvents.value, cores, statsSpanNs.value)
})
const sortedTaskCoreRows = computed(() => {
  const cores = taskCoreModel.value.cores || []
  const acc = { task: r => String(r.task || '').toLowerCase() }
  for (const core of cores) {
    acc[core] = r => Number(r.cells?.[core]?.pct_span || 0)
  }
  return sortStatsRows(taskCoreModel.value.rows || [], tableSort.value.task_core, acc)
})

const waitOwnerModel = computed(() => {
  const tr = props.trace
  if (!tr) return { tasks: [], cells: {} }
  const r = statsRange.value
  return waiterOwnerMatrix(pairMutexWaits(harvestMutexHolds(tr, r?.lo ?? null, r?.hi ?? null)))
})
const sortedWaitOwnerTasks = computed(() => {
  const tasks = waitOwnerModel.value.tasks || []
  const cells = waitOwnerModel.value.cells || {}
  const acc = { waiter: t => String(t.task || '').toLowerCase() }
  for (const owner of tasks) {
    acc[owner.mk] = waiter => Number(cells[`${waiter.mk}|${owner.mk}`]?.ns || 0)
  }
  return sortStatsRows(tasks, tableSort.value.wait_owner, acc)
})

function healthTone(score) {
  if (score >= 80) return 'ok'
  if (score >= 60) return 'warn'
  return 'fail'
}

function onPeriodCellClick(row, key) {
  if (!row) return
  if (key === 'plot') {
    openTaskPlot(row.mk, 'inter')
    return
  }
  onUxEventClick({ ...(row[key] || row.worst_ev), section: 'period', mk: row.mk, task: row.task })
}

function onResponseCellClick(row, key) {
  if (!row) return
  if (key === 'plot') {
    openTaskPlot(row.mk, 'response')
    return
  }
  const ev = row[key] || row.worst_ev || row
  onUxEventClick({ ...ev, section: 'response', mk: row.mk, task: row.task })
}

function onCritPathCellClick(row, key) {
  if (!row) return
  const ev = (key && row[key]) || row
  onUxEventClick({ ...ev, section: 'crit_path', mk: row.mk, task: row.task })
}

function onJitterCellClick(row, kind) {
  if (!row?.mk) return
  openTaskPlot(row.mk, kind || 'exec')
}

function onTaskCoreCellClick(row, core) {
  if (!row) return
  if (!core) {
    emit('highlightTask', row.mk)
    return
  }
  const cell = row.cells?.[core]
  if (!cell?.ns) return
  onUxEventClick({
    kind: 'exec',
    task: row.task,
    mk: row.mk,
    start: cell.start,
    stop: cell.stop,
    duration: cell.ns,
    jump_ns: cell.jump_ns,
    section: 'task_core',
  })
}

function onWaitOwnerCellClick(cell) {
  if (!cell?.ns) return
  onUxEventClick({
    ...cell,
    mk: cell.waiter_mk,
    task: cell.waiter,
    duration: cell.ns,
    section: 'wait_owner',
  })
}

function onPreemptMatrixCellClick(cell) {
  if (!cell?.ns) return
  onUxEventClick({
    ...cell,
    mk: cell.victim_mk || cell.victim,
    task: cell.victim,
    duration: cell.ns,
    section: 'preempt_matrix',
  })
}

function onMutexBlockClick(row) {
  if (!row) return
  const ev = row.worst || row
  onUxEventClick({
    ...ev,
    mk: ev.waiter_mk || row.mk,
    task: ev.waiter || row.task,
    duration: ev.duration || row.max_ns,
    section: 'mutex_block',
  })
}

function onCoreTimeClick(row) {
  if (!row) return
  onUxEventClick({
    ...row,
    task: row.peak_core || 'CPU',
    mk: row.peak_core || '',
    duration: Math.max(1, (row.stop || 0) - (row.start || 0)),
    section: 'core_time',
  })
}

function onTaskHealthClick(row, band) {
  if (!row) return
  if (row.mk) emit('highlightTask', row.mk)
  const sid = band ? (HEALTH_BAND_SECTION[band] || 'task_health') : 'task_health'
  applyDemoSections({ id: sid, expand: true, scroll: sid, collapse_others: false })
}

function uxKindLabel(kind) {
  return KIND_LABEL[kind] || kind
}

function onUxEventClick(ev) {
  if (!ev) return
  const note = `${ev.task || ev.mk} — ${ev.reason || ev.kind || 'episode'}`
  const segs = props.trace?.segByMergeKey?.get(ev.mk) || []
  const jump = ev.jump_ns ?? ev.start
  const seg = segs.find(s => s.start === jump || (s.start <= ev.start && s.end > ev.start))
    || segs[0]
    || null
  emit('plotPointActivate', { ns: jump, note, segment: seg })
  emit('highlightTask', ev.mk)
  emit('exploreRange', {
    lo: ev.start,
    hi: Math.max(ev.stop || ev.start + 1, ev.start + 1),
    mk: ev.mk,
    section: ev.section || ({ exec: 'exec', block: 'block', inter: 'inter', migration: 'migrations' })[ev.kind],
    note,
    ns: jump,
  })
}

function onAnomalyRowClick(row) {
  lastAnomaly.value = row
  onUxEventClick(row)
}

function onInvestigateAnomaly() {
  if (!aiFeatureEnabled.value) return
  const ev = lastAnomaly.value || anomalyRows.value[0]
  if (!ev) return
  const extra = `Investigate this timeline anomaly: kind=${ev.kind || ''} task=${ev.task || ev.mk || ''} jump:${Math.trunc(ev.jump_ns || ev.start || 0)} duration=${Math.trunc(ev.duration || 0)} why=${ev.reason || ''}.`
  emit('query-ai', { template: 'investigate', extra })
}

const distribSummary = computed(() => {
  const mk = distribMk.value
  if (!mk) return 'Select a task to see n / p50 / p99 / sparkline.'
  const model = distributionExplorer(uxEvents.value, distribKind.value, mk, dispatchSampleMap.value)
  if (!model) return 'No samples for this metric × task in scope.'
  const scale = timeScale.value
  return `n=${model.n || 0}  min=${formatTime(model.min_ns, scale)}  p50=${formatTime(model.p50_ns, scale)}  p99=${formatTime(model.p99_ns, scale)}  max=${formatTime(model.max_ns, scale)}  CV=${((model.cv || 0) * 100).toFixed(1)}%  ${model.spark || ''}`
})

const distribHistogramModel = computed(() => {
  const mk = distribMk.value
  if (!mk) return null
  const samples = distributionMetricSamples(
    uxEvents.value, distribKind.value, mk, dispatchSampleMap.value)
  if (!samples.length) return null
  return buildHistogramModel(samples, {
    scaleMode: distribScaleMode.value,
    formatValue: (value) => formatTime(value, timeScale.value),
    valueAsTime: true,
    color: '#5B9BD5',
    showVariability: true,
    height: 200,
  })
})

function onOpenDistributionPlot() {
  const mk = distribMk.value
  if (!mk) return
  const model = distributionExplorer(uxEvents.value, distribKind.value, mk, dispatchSampleMap.value) || {}
  const kind = model.plot_kind || distribKind.value
  if (kind === 'preempt') {
    const rec = preemptorRanking(preemptionPairs(uxEvents.value), 16)
      .find(r => String(r.mk || '') === String(mk))
    const top = (rec?.top || [])[0]
    const label = String(top?.task || top?.mk || '')
    if (!label) return
    openPreemptPlot(mk, label)
    return
  }
  openTaskPlot(mk, kind)
}

function queryDistributionWithAi(source) {
  if (!aiFeatureEnabled.value) return
  const fromPlot = source === 'plot'
  const kind = fromPlot
    ? (openPlotRef.value?.kind || '')
    : distribKind.value
  const mk = fromPlot
    ? (openPlotRef.value?.mk || openPlotRef.value?.pairKey || openPlotRef.value?.core || '')
    : distribMk.value
  if (!fromPlot && !mk) return
  const title = fromPlot
    ? (plotData.value?.title || 'Metrics plot')
    : 'Distribution Explorer'
  const extra = `Explain this statistics distribution: metric=${kind} task=${mk} title=${title}. Use query_raw_metric and search_timeline. Identify the tail, jitter, and the next Statistics page or timeline jump.`
  emit('query-ai', { template: 'investigate', extra })
}

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
  if (n < 2) emit('update:scopeToCursors', false)
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
  const hasGaps = coreGaps.length > 0
  const avg = hasGaps
    ? Math.round(coreGaps.reduce((a, b) => a + b, 0) / coreGaps.length)
    : 0
  return {
    contextSwitches,
    hasGaps,
    gapAvg: hasGaps ? formatTime(avg, scale) : '',
    gapMax: hasGaps ? formatTime(gapMax, scale) : '',
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

// ---- Load Balance Score (Feature 2) ------------------------------------
const loadBalanceScore = computed(() => {
  const cs = coreStats.value
  const lb = loadBalanceMetrics(cs.map(c => c.pct))
  if (!lb) return null
  const score = lb.score
  const gini = lb.gini
  const stddev = lb.stddev
  const zone = classifyLoadBalance(score, stddev)
  return {
    score,
    gini,
    stddev,
    zone,
    amber: zone === 'amber' || zone === 'red',
    red: zone === 'red',
  }
})

// ---- Analysis Findings (Export HTML) -----------------------------------
const analysisFindings = computed(() => {
  const tr = props.trace
  if (!tr) return []
  const r = statsRange.value
  return collectTraceAnalysisFindings(
    tr,
    r?.lo ?? null,
    r?.hi ?? null,
    props.analysisSettings || {},
  )
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

const sortedPreemptionStats = computed(() =>
  sortStatsRows(preemptionRows.value, tableSort.value.preemption, PREEMPTION_SORT_ACCESSORS))

const intervalStats = computed(() => {
  if (intervalsCollapsed.value) return []
  const tr = props.trace
  if (!tr?.intervalIds?.length) return []
  const r = statsRange.value
  const lo = r?.lo ?? null
  const hi = r?.hi ?? null
  return intervalStatsRows(tr, lo, hi)
})

const sortedIntervalStats = computed(() =>
  sortStatsRows(intervalStats.value, tableSort.value.intervals, INTERVAL_SORT_ACCESSORS))

const tagStats = computed(() => {
  if (tagsCollapsed.value) return []
  const tr = props.trace
  if (!tr?.tagChannels?.length) return []
  const r = statsRange.value
  const lo = r?.lo ?? null
  const hi = r?.hi ?? null
  return tagStatsRows(tr, lo, hi)
})

const sortedTagStats = computed(() =>
  sortStatsRows(tagStats.value, tableSort.value.tags, TAG_SORT_ACCESSORS))

const priorityStats = computed(() => {
  if (priorityCollapsed.value) return []
  const tr = props.trace
  if (!tr?.hasPriorityInstrumentation) return []
  const r = statsRange.value
  const lo = r?.lo ?? null
  const hi = r?.hi ?? null
  return priorityStatsRows(tr, lo, hi)
})

const sortedPriorityStats = computed(() =>
  sortStatsRows(priorityStats.value, tableSort.value.priority, PRIORITY_SORT_ACCESSORS))

const syncStats = computed(() => {
  const tr = props.trace
  if (!tr?.hasSyncObjectInstrumentation) return []
  const r = statsRange.value
  return syncObjectStatsRows(tr, r?.lo ?? null, r?.hi ?? null)
})

const syncIssueList = computed(() => {
  const tr = props.trace
  if (!tr?.hasSyncObjectInstrumentation) return []
  const r = statsRange.value
  return syncObjectIssueRows(tr, r?.lo ?? null, r?.hi ?? null)
})

const syncIssueDisplay = computed(() => capStatsTableRows(syncIssueList.value))

const sortedSyncIssueList = computed(() =>
  sortStatsRows(syncIssueDisplay.value.rows, tableSort.value.sync_issues, SYNC_ISSUE_SORT_ACCESSORS))

const sortedSyncStats = computed(() =>
  sortStatsRows(syncStats.value, tableSort.value.sync, SYNC_OBJECT_SORT_ACCESSORS))

const queueStats = computed(() => {
  const tr = props.trace
  if (!tr?.hasSyncObjectInstrumentation) return []
  const r = statsRange.value
  return syncObjectStatsRows(tr, r?.lo ?? null, r?.hi ?? null, { kindFilter: 'queue' })
})

const sortedQueueStats = computed(() =>
  sortStatsRows(queueStats.value, tableSort.value.queue, SYNC_OBJECT_SORT_ACCESSORS))

const lifecycleStats = computed(() => {
  const tr = props.trace
  if (!tr?.stiEvents?.length) return []
  const r = statsRange.value
  return buildTaskLifecycleRows(tr.stiEvents, tr.taskRepr, r?.lo ?? null, r?.hi ?? null, tr.taskCreateTimes, tr.segByMergeKey)
})

const sortedLifecycleStats = computed(() =>
  sortStatsRows(lifecycleStats.value, tableSort.value.lifecycle, LIFECYCLE_SORT_ACCESSORS))

const corePairRows = computed(() => {
  const tr = props.trace
  if (!tr?.migrations?.length) return []
  const r = statsRange.value
  return buildCorePairRows(tr, r?.lo ?? null, r?.hi ?? null)
})

const sortedCorePairRows = computed(() =>
  sortStatsRows(corePairRows.value, tableSort.value.core_pairs, CORE_PAIR_SORT_ACCESSORS))

const coreTimeBreakdown = computed(() => {
  const tr = props.trace
  if (!tr?.coreNames?.length) return []
  const r = statsRange.value
  return buildCoreTimeBreakdown(tr, r?.lo ?? null, r?.hi ?? null)
})

const sortedCoreTimeBreakdown = computed(() =>
  sortStatsRows(coreTimeBreakdown.value, tableSort.value.core_breakdown, CORE_BREAKDOWN_SORT_ACCESSORS))

const concurrentCoreStats = computed(() => {
  const tr = props.trace
  if (!tr) return []
  const r = statsRange.value
  return concurrentCoreActiveRows(tr, r?.lo ?? null, r?.hi ?? null)
})

const sortedConcurrentCoreStats = computed(() =>
  sortStatsRows(concurrentCoreStats.value, tableSort.value.concurrency, CONCURRENCY_SORT_ACCESSORS))

const switchOverheadStats = computed(() => {
  const tr = props.trace
  if (!tr) return []
  const r = statsRange.value
  return switchOverheadRows(tr, r?.lo ?? null, r?.hi ?? null)
})

const sortedSwitchOverheadStats = computed(() =>
  sortStatsRows(switchOverheadStats.value, tableSort.value.switch_overhead, SWITCH_OVERHEAD_SORT_ACCESSORS))

const dispatchLatencyStats = computed(() => {
  const tr = props.trace
  if (!tr) return []
  const r = statsRange.value
  return dispatchLatencyRows(tr, r?.lo ?? null, r?.hi ?? null)
})

const sortedDispatchLatencyStats = computed(() =>
  sortStatsRows(dispatchLatencyStats.value, tableSort.value.dispatch, DISPATCH_SORT_ACCESSORS))

const coreAffinityRows = computed(() => {
  const tr = props.trace
  if (!tr?.stiEvents?.length) return []
  const r = statsRange.value
  return buildCoreAffinityRows(tr, r?.lo ?? null, r?.hi ?? null)
})

const sortedAffinityRows = computed(() =>
  sortStatsRows(coreAffinityRows.value, tableSort.value.affinity, AFFINITY_SORT_ACCESSORS))

const deadlineViolations = computed(() => {
  const tr = props.trace
  if (!tr) return { sliceViolations: [], cpuViolations: [] }
  const r = statsRange.value
  return computeDeadlineViolations(
    tr,
    props.analysisSettings || {},
    r?.lo ?? null,
    r?.hi ?? null,
  )
})

const taskHealthRows = computed(() => {
  const dead = [
    ...deadlineViolations.value.sliceViolations.map(v => v.mk),
    ...deadlineViolations.value.cpuViolations.map(v => v.mk),
  ]
  return taskHealthScores(healthInputsFromEvents(uxEvents.value, statsSpanNs.value, dead))
})
const sortedTaskHealthRows = computed(() =>
  sortStatsRows(taskHealthRows.value, tableSort.value.task_health, TASK_HEALTH_SORT_ACCESSORS))

const sortedDeadlineSliceRows = computed(() =>
  // Cap to the top 20 by duration first (desktop populates sv[:20]), then
  // let header clicks reorder that fixed set — not re-pick from the full list.
  sortStatsRows(
    deadlineViolations.value.sliceViolations.slice(0, 20),
    tableSort.value.deadline_slice,
    DEADLINE_SLICE_SORT_ACCESSORS,
  ))

const sortedDeadlineCpuRows = computed(() =>
  sortStatsRows(
    deadlineViolations.value.cpuViolations,
    tableSort.value.deadline_cpu,
    DEADLINE_CPU_SORT_ACCESSORS,
  ))

function deadlineSliceRowTitle(v) {
  const scale = props.trace?.timeScale || 'ns'
  return `Click to annotate '${v.label}' deadline slice at ${formatTimeFixed(v.startNs, scale)}`
}

const hasDeadlineConfig = computed(() => {
  const s = props.analysisSettings || {}
  const budget = Number(s.cpuBudgetPct)
  const deadlines = s.taskDeadlines || {}
  return (Number.isFinite(budget) && budget > 0) || Object.keys(deadlines).length > 0
})

function syncStatusClass(status) {
  if (status === 'error') return 'sync-status-error'
  if (status === 'warning') return 'sync-status-warning'
  return 'sync-status-ok'
}

function syncIssueSeverityClass(severity) {
  if (severity === 'error') return 'sync-status-error'
  if (severity === 'warning') return 'sync-status-warning'
  return ''
}

function onSyncIssueClick(issue) {
  if (issue?.timeNs == null) return
  const tr = props.trace
  const segment = tr ? segmentAtCoreTime(tr.coreSegs, issue.core, issue.timeNs, tr.coreSegStarts) : null
  emit('plotPointActivate', {
    ns: issue.timeNs,
    note: syncIssueAnnotationNote(issue),
    segment,
    syncIssue: true,
  })
}

function onLifecycleRowClick(row) {
  // Matches desktop's _on_lifecycle_row: jump to the task's creation time,
  // then highlight the task (no annotation is added for this camera-only jump).
  if (row.createNs != null) emit('segmentJump', row.createNs)
  emit('highlightTask', row.mk)
}

function onDeadlineSliceClick(v) {
  if (!v || v.startNs == null) return
  emit('plotPointActivate', {
    ns: v.startNs,
    note: deadlineSliceAnnotationNote(props.trace, v),
    segment: v.segment || null,
  })
}

function priorityRowTitle(row) {
  return `Open boost duration plot for ${row.label}`
}

function onPriorityRowClick(row) {
  openPriorityPlot(row.mk)
  emit('highlightTask', row.mk)
}

function activateExtremeSegment(mk, kind, seg, findMax) {
  if (!seg) return
  const note = extremeSegmentNote(props.trace, mk, kind, seg, findMax)
  emit('plotPointActivate', { ns: seg.start, note, segment: seg })
}

function jumpToPercentile(mk, kind, p) {
  const tr = props.trace
  if (!tr) return
  const r = statsRange.value
  const lo = r?.lo ?? null
  const hi = r?.hi ?? null
  const segs = tr.segByMergeKey?.get(mk) || []
  let seg = null
  if (kind === 'exec') seg = findPercentileExecSegment(segs, p, lo, hi)
  else if (kind === 'block') seg = findPercentileBlockingSegment(segs, p, lo, hi)
  else if (kind === 'inter') seg = findPercentileInterArrivalSegment(segs, p, lo, hi)
  if (!seg) return
  const pct = Math.round(p * 100)
  const name = taskDisplayName(taskReprGet(tr, mk) || mk)
  const note = `${name} p${pct} ${kind}: ${formatTime(seg.end - seg.start, tr.timeScale)} at ${formatTime(seg.start, tr.timeScale)}`
  emit('plotPointActivate', { ns: seg.start, note, segment: seg })
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
  if (seg) activateExtremeSegment(mk, kind, seg, findMax)
}

function jumpToDispatchExtreme(row, findMax) {
  const seg = findMax ? row.maxSeg : row.minSeg
  if (!seg || !props.trace) return
  const latNs = findMax ? row.maxNs : row.minNs
  const tag = findMax ? 'max' : 'min'
  const note = `${row.label} — ${tag} dispatch latency (${formatTime(latNs, props.trace.timeScale)} ready→run)`
  emit('plotPointActivate', { ns: seg.start, note, segment: seg })
}

function _summarizeNumericSamples(samples) {
  if (!samples || samples.length === 0) return null
  const values = [...samples].sort((a, b) => a - b)
  const n = values.length
  const avg = values.reduce((sum, value) => sum + value, 0) / n
  return {
    avg,
    stddev: Math.sqrt(
      values.reduce((sum, value) => sum + ((value - avg) ** 2), 0) / n,
    ),
    p50: values[Math.min(n - 1, Math.floor(n * 0.5))],
    p5: values[Math.min(n - 1, Math.floor(n * 0.05))],
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
  const evs = harvestUxEvents(trace, range?.lo ?? null, range?.hi ?? null)
    .filter(e => e && e.kind === 'exec' && String(e.mk || '') === String(mk))
  const model = analyzeResponseTimes(evs)
  const events = model.events || []
  if (!events.length) return null
  const repr = trace.taskRepr.get(mk) || mk
  const suffix = scopeSuffix(range)
  const points = events.map((ev, index) => ({
    index,
    xNs: ev.start,
    yValue: ev.duration,
    payload: ev,
    label: `${taskDisplayName(repr)}: ${formatTime(ev.duration, trace.timeScale)} ready→complete at ${formatTime(ev.start, trace.timeScale)}`,
  }))
  return {
    kind: 'response',
    mk,
    title: `${taskDisplayName(repr)} - Response Time (heuristic)${suffix}`,
    color: taskColor(mk, repr),
    points,
  }
}

function _buildMigDwellPlot(trace, mk, range) {
  const lo = range?.lo ?? null
  const hi = range?.hi ?? null
  const repr = trace.taskRepr.get(mk) || mk
  const suffix = scopeSuffix(range)
  const name = taskDisplayName(repr)
  const rawPoints = migrationDwellPlotPoints(trace, mk, lo, hi)
  const points = rawPoints.map((pt, index) => ({
    index,
    xNs: pt.xNs,
    yValue: pt.yValue,
    payload: pt.payload,
    label: `${name}: ${formatTime(pt.yValue, trace.timeScale)} dwell on ${pt.payload.core} at ${formatTime(pt.xNs, trace.timeScale)}`,
  }))
  return {
    kind: 'mig_dwell',
    mk,
    title: `${name} — On-Core Dwell Time${suffix}`,
    color: taskColor(mk, repr),
    points,
  }
}

function _buildMigRatePlot(trace, mk, range) {
  const lo = range?.lo ?? null
  const hi = range?.hi ?? null
  const repr = trace.taskRepr.get(mk) || mk
  const suffix = scopeSuffix(range)
  const name = taskDisplayName(repr)
  const rawPoints = migrationRatePlotPoints(trace, mk, lo, hi)
  const points = rawPoints.map((pt, index) => ({
    index,
    xNs: pt.xNs,
    yValue: pt.yValue,
    payload: pt.payload,
    label: `${name}: ${formatTime(pt.yValue, trace.timeScale)} since previous migration at ${formatTime(pt.xNs, trace.timeScale)}`,
  }))
  return {
    kind: 'mig_rate',
    mk,
    title: `${name} — Time Between Migrations${suffix}`,
    color: taskColor(mk, repr),
    points,
  }
}

function _buildMigGapPlot(trace, mk, range) {
  const lo = range?.lo ?? null
  const hi = range?.hi ?? null
  const repr = trace.taskRepr.get(mk) || mk
  const suffix = scopeSuffix(range)
  const name = taskDisplayName(repr)
  const rawPoints = migrationGapPlotPoints(trace, mk, lo, hi)
  const points = rawPoints.map((pt, index) => ({
    index,
    xNs: pt.xNs,
    yValue: pt.yValue,
    payload: pt.payload,
    label: `${name}: ${formatTime(pt.yValue, trace.timeScale)} blocked after ${pt.payload.fromCore}→${pt.payload.toCore} at ${formatTime(pt.xNs, trace.timeScale)}`,
  }))
  return {
    kind: 'mig_gap',
    mk,
    title: `${name} — Post-Migration Gap${suffix}`,
    color: taskColor(mk, repr),
    points,
  }
}

function _pairHeader(trace, fromCore, toCore, range) {
  const lo = range?.lo ?? null
  const hi = range?.hi ?? null
  const migs = pairMigrations(trace, fromCore, toCore, lo, hi)
  if (!migs.length) return null
  const bounceNs = buildLockBounceNsSet(trace)
  const bounces = migs.filter(m => bounceNs.has(m.ns)).length
  const bouncePct = 100 * bounces / migs.length
  const avgGap = Math.floor(migs.reduce((s, m) => s + (m.gapNs || 0), 0) / migs.length)
  return (
    `${fromCore} → ${toCore} · ${migs.length} migr · Bounce ${bouncePct.toFixed(1)}% · ` +
    `Avg Gap ${formatMigrationGapTime(avgGap, trace.timeScale)}`
  )
}

function _buildPairGapPlot(trace, fromCore, toCore, range) {
  const lo = range?.lo ?? null
  const hi = range?.hi ?? null
  const suffix = scopeSuffix(range)
  const hdr = _pairHeader(trace, fromCore, toCore, range)
  if (!hdr) return null
  const rawPoints = pairGapPlotPoints(trace, fromCore, toCore, lo, hi)
  if (!rawPoints.length) return null
  const bounceNs = buildLockBounceNsSet(trace)
  const points = rawPoints.map((pt, index) => {
    const bounce = bounceNs.has(pt.payload.ns) ? ' · bounce' : ''
    return {
      index,
      xNs: pt.xNs,
      yValue: pt.yValue,
      payload: pt.payload,
      fillColor: pt.fillColor,
      label: `${fromCore}→${toCore}: ${formatTime(pt.yValue, trace.timeScale)} blocked after migration at ${formatTime(pt.xNs, trace.timeScale)}${bounce}`,
    }
  })
  return {
    kind: 'pair_gap',
    fromCore,
    toCore,
    pairKey: pairPlotKey(fromCore, toCore),
    title: `${hdr} — Post-Migration Gap${suffix}`,
    color: coreColor(fromCore),
    points,
  }
}

function _buildPairRatePlot(trace, fromCore, toCore, range) {
  const lo = range?.lo ?? null
  const hi = range?.hi ?? null
  const suffix = scopeSuffix(range)
  const hdr = _pairHeader(trace, fromCore, toCore, range)
  if (!hdr) return null
  const rawPoints = pairRatePlotPoints(trace, fromCore, toCore, lo, hi)
  if (!rawPoints.length) return null
  const points = rawPoints.map((pt, index) => ({
    index,
    xNs: pt.xNs,
    yValue: pt.yValue,
    payload: pt.payload,
    fillColor: pt.fillColor,
    label: `${fromCore}→${toCore}: ${formatTime(pt.yValue, trace.timeScale)} since previous pair migration at ${formatTime(pt.xNs, trace.timeScale)}`,
  }))
  return {
    kind: 'pair_rate',
    fromCore,
    toCore,
    pairKey: pairPlotKey(fromCore, toCore),
    title: `${hdr} — Time Between Pair Migrations${suffix}`,
    color: coreColor(fromCore),
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

function _buildTickDistPlot(trace, range) {
  const suffix = scopeSuffix(range)
  let times = trace?.tickStiTimes || []
  if (range) {
    times = times.filter(t => t >= range.lo && t <= range.hi)
  }
  if (times.length < 2) return null
  const points = []
  for (let i = 1; i < times.length; i++) {
    const delta = times[i] - times[i - 1]
    points.push({
      index: i - 1,
      xNs: times[i],
      yValue: delta,
      payload: null,
      label: `Tick #${i}: interval ${formatTime(delta, trace.timeScale)} at ${formatTime(times[i], trace.timeScale)}`,
    })
  }
  return {
    kind: 'tick',
    title: `Tick Interval Distribution${suffix}`,
    color: '#64B5F6',
    points,
  }
}

function _buildDispatchPlot(trace, mk, range) {
  const segs = trace?.segByMergeKey?.get(mk) || []
  if (segs.length === 0) return null
  const repr = trace.taskRepr.get(mk) || mk
  const name = taskDisplayName(repr)
  const suffix = scopeSuffix(range)
  const lo = range?.lo ?? null
  const hi = range?.hi ?? null
  const rawPoints = dispatchLatencyPlotPoints(trace, mk, lo, hi)
  if (!rawPoints.length) return null
  const points = rawPoints.map((pt, index) => ({
    index,
    xNs: pt.xNs,
    yValue: pt.yValue,
    payload: pt.payload,
    label: `${name}: ${formatTime(pt.yValue, trace.timeScale)} dispatch latency at ${formatTime(pt.xNs, trace.timeScale)}`,
  }))
  return {
    kind: 'dispatch',
    mk,
    title: `${name} — Dispatch Latency${suffix}`,
    color: taskColor(mk, repr),
    points,
  }
}

function _buildSwitchOverheadPlot(trace, core, range) {
  const suffix = scopeSuffix(range)
  const lo = range?.lo ?? null
  const hi = range?.hi ?? null
  const rawPoints = switchOverheadPlotPoints(trace, core, lo, hi)
  if (!rawPoints.length) return null
  const points = rawPoints.map((pt, index) => ({
    index,
    xNs: pt.xNs,
    yValue: pt.yValue,
    payload: null,
    label: `${core}: switch overhead ${formatTime(pt.yValue, trace.timeScale)} at ${formatTime(pt.xNs, trace.timeScale)}`,
  }))
  return {
    kind: 'switch_overhead',
    mk: core,
    core,
    title: `${core} — Kernel Switch Overhead${suffix}`,
    color: coreColor(core),
    points,
  }
}

function _buildConcurrencyPlot(trace, activeCores, range) {
  const suffix = scopeSuffix(range)
  const lo = range?.lo ?? null
  const hi = range?.hi ?? null
  const n = Number(activeCores)
  const rawPoints = concurrencyLevelPlotPoints(trace, n, lo, hi)
  if (!rawPoints.length) return null
  const points = rawPoints.map((pt, index) => ({
    index,
    xNs: pt.xNs,
    yValue: pt.yValue,
    payload: null,
    label: `${n} active cores: dwell ${formatTime(pt.yValue, trace.timeScale)} starting ${formatTime(pt.xNs, trace.timeScale)}`,
  }))
  return {
    kind: 'concurrency',
    mk: String(n),
    activeCores: n,
    title: `${n} Active Cores — Interval Duration${suffix}`,
    color: '#64B5F6',
    points,
  }
}

function _buildIntervalPlot(trace, id, range) {
  const suffix = scopeSuffix(range)
  const lo = range?.lo ?? null
  const hi = range?.hi ?? null
  const rawPoints = intervalPlotPoints(trace, id, lo, hi)
  const points = rawPoints.map((pt, index) => ({
    index,
    xNs: pt.xNs,
    yValue: pt.yValue,
    payload: pt.payload,
    label: `Interval ${id}: ${formatTime(pt.yValue, trace.timeScale)} [${formatTime(pt.payload.startNs, trace.timeScale)} – ${formatTime(pt.payload.stopNs, trace.timeScale)}]`,
  }))
  return {
    kind: 'interval',
    intervalId: id,
    title: `Interval ${id} — Duration${suffix}`,
    color: intervalColor(id),
    points,
  }
}

function _buildTagPlot(trace, channel, range) {
  const suffix = scopeSuffix(range)
  const lo = range?.lo ?? null
  const hi = range?.hi ?? null
  const label = tagChannelLabel(channel)
  const rawPoints = tagPlotPoints(trace, channel, lo, hi)
  const points = rawPoints.map((pt, index) => ({
    index,
    xNs: pt.xNs,
    yValue: pt.yValue,
    payload: pt.payload,
    label: `${label}: ${formatTagValue(pt.yValue)} at ${formatTime(pt.xNs, trace.timeScale)}`,
  }))
  return {
    kind: 'tag',
    tagChannel: channel,
    title: `${label} — Value${suffix}`,
    color: tagColor(channel),
    points,
  }
}

function _buildTagIntervalPlot(trace, channel, range) {
  const suffix = scopeSuffix(range)
  const lo = range?.lo ?? null
  const hi = range?.hi ?? null
  const label = tagChannelLabel(channel)
  const rawPoints = tagIntervalPlotPoints(trace, channel, lo, hi)
  const points = rawPoints.map((pt, index) => ({
    index,
    xNs: pt.xNs,
    yValue: pt.yValue,
    payload: pt.payload,
    label: `${label}: ${formatTime(pt.yValue, trace.timeScale)} since previous sample at ${formatTime(pt.xNs, trace.timeScale)}`,
  }))
  return {
    kind: 'tag_interval',
    tagChannel: channel,
    title: `${label} — Interval${suffix}`,
    color: tagColor(channel),
    points,
  }
}

function _buildPriorityPlot(trace, mk, range) {
  const suffix = scopeSuffix(range)
  const lo = range?.lo ?? null
  const hi = range?.hi ?? null
  const label = taskLabelForMergeKey(trace, mk)
  const basePri = trace.taskBasePriority?.get?.(mk)
  const rawPoints = priorityEpisodePlotPoints(trace, mk, lo, hi)
  const scale = trace.timeScale
  const points = rawPoints.map((pt) => ({
    ...pt,
      fillColor: pt.payload?.inversionSuspect ? INVERSION_BAND_COLOR : BOOST_BAND_COLOR,
      label: `${pt.payload.taskLabel}: pri ${pt.payload.basePri}→${pt.payload.peakPri} — ${formatTime(pt.yValue, scale)} [${formatTime(pt.payload.startNs, scale)} – ${formatTime(pt.payload.stopNs, scale)}]${pt.payload.inherited ? ' · inherit' : ''}${pt.payload.inversionSuspect && !pt.payload.inherited ? ' · L/M/H' : ''}`,
  }))
  const peakPri = points.length
    ? Math.max(...points.map(p => p.payload.peakPri))
    : basePri
  return {
    kind: 'priority',
    mk,
    title: `${label} — Priority Boost (base ${basePri}→peak ${peakPri})${suffix}`,
    color: BOOST_BAND_COLOR,
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
  if (open.kind === 'mig_dwell') return _buildMigDwellPlot(props.trace, open.mk, range)
  if (open.kind === 'mig_rate') return _buildMigRatePlot(props.trace, open.mk, range)
  if (open.kind === 'mig_gap') return _buildMigGapPlot(props.trace, open.mk, range)
  if (open.kind === 'pair_gap') {
    return _buildPairGapPlot(props.trace, open.fromCore, open.toCore, range)
  }
  if (open.kind === 'pair_rate') {
    return _buildPairRatePlot(props.trace, open.fromCore, open.toCore, range)
  }
  if (open.kind === 'preempt') {
    return _buildPreemptPlot(props.trace, open.mk, open.preemptor, range)
  }
  if (open.kind === 'interval') {
    return _buildIntervalPlot(props.trace, open.intervalId, range)
  }
  if (open.kind === 'tag') {
    return _buildTagPlot(props.trace, open.tagChannel, range)
  }
  if (open.kind === 'tag_interval') {
    return _buildTagIntervalPlot(props.trace, open.tagChannel, range)
  }
  if (open.kind === 'priority') {
    return _buildPriorityPlot(props.trace, open.mk, range)
  }
  if (open.kind === 'tick') {
    return _buildTickDistPlot(props.trace, range)
  }
  if (open.kind === 'dispatch') {
    return _buildDispatchPlot(props.trace, open.mk, range)
  }
  if (open.kind === 'switch_overhead') {
    return _buildSwitchOverheadPlot(props.trace, open.core || open.mk, range)
  }
  if (open.kind === 'concurrency') {
    return _buildConcurrencyPlot(props.trace, open.activeCores ?? open.mk, range)
  }
  return _buildInterPlot(props.trace, open.mk, range)
})

const histogramScaleOptions = computed(() => [
  { value: 'auto', label: 'Auto' },
  { value: 'linear', label: 'Linear' },
  { value: 'percentile', label: 'p5–p95' },
  {
    value: 'log',
    label: plotData.value?.kind === 'tag' ? 'Log scale' : 'Log duration',
  },
])

const plotScopeInfo = computed(() => {
  if (!openPlotRef.value) return null
  return plotScopeBanner(statsRange.value, props.trace.timeScale, formatTime)
})

const activePlotTabs = computed(() => plotTabsForKind(openPlotRef.value?.kind))

const pairPlotFocus = computed(() => {
  const open = openPlotRef.value
  if (!open || !open.kind?.startsWith('pair_')) return null
  const fromCore = open.fromCore
  const toCore = open.toCore
  if (!fromCore || !toCore) return null
  const range = statsRange.value
  const bounceOnly = pairBouncePrefer(
    props.trace, fromCore, toCore, range?.lo ?? null, range?.hi ?? null)
  return { fromCore, toCore, bounceOnly }
})

function switchPlotTab(kind) {
  const next = resolvePlotTabSwitch(openPlotRef.value, kind)
  if (!next) return
  openPlotRef.value = next
  selectedPlotPoint.value = -1
}

function openTaskPlot(mk, kind) {
  const range = statsRange.value
  let plot
  if (kind === 'exec') plot = _buildExecPlot(props.trace, mk, range)
  else if (kind === 'block') plot = _buildBlockPlot(props.trace, mk, range)
  else if (kind === 'response') plot = _buildResponsePlot(props.trace, mk, range)
  else if (kind === 'mig_dwell') plot = _buildMigDwellPlot(props.trace, mk, range)
  else if (kind === 'mig_rate') plot = _buildMigRatePlot(props.trace, mk, range)
  else if (kind === 'mig_gap') plot = _buildMigGapPlot(props.trace, mk, range)
  else if (kind === 'dispatch') plot = _buildDispatchPlot(props.trace, mk, range)
  else if (kind === 'preempt') {
    const rec = preemptorRanking(preemptionPairs(uxEvents.value), 16)
      .find(r => String(r.mk || '') === String(mk))
    const top = (rec?.top || [])[0]
    const label = String(top?.task || top?.mk || '')
    if (!label) return
    plot = _buildPreemptPlot(props.trace, mk, label, range)
    if (!plot || plot.points.length === 0) return
    openPlotRef.value = { mk, kind: 'preempt', preemptor: label }
    selectedPlotPoint.value = -1
    return
  } else plot = _buildInterPlot(props.trace, mk, range)
  if (!plot || plot.points.length === 0) return
  openPlotRef.value = { mk, kind }
  selectedPlotPoint.value = -1
}

function openSwitchOverheadPlot(core) {
  const range = statsRange.value
  const plot = _buildSwitchOverheadPlot(props.trace, core, range)
  if (!plot || plot.points.length === 0) return
  openPlotRef.value = { mk: core, core, kind: 'switch_overhead' }
  selectedPlotPoint.value = -1
}

function openConcurrencyPlot(activeCores) {
  const range = statsRange.value
  const plot = _buildConcurrencyPlot(props.trace, activeCores, range)
  if (!plot || plot.points.length === 0) return
  openPlotRef.value = { mk: String(activeCores), activeCores, kind: 'concurrency' }
  selectedPlotPoint.value = -1
}

function openPairPlot(fromCore, toCore) {
  const range = statsRange.value
  const plot = _buildPairGapPlot(props.trace, fromCore, toCore, range)
  if (!plot || plot.points.length === 0) return
  openPlotRef.value = { kind: 'pair_gap', fromCore, toCore, pairKey: pairPlotKey(fromCore, toCore) }
  selectedPlotPoint.value = -1
}

function openPairHeatmap() {
  const focus = pairPlotFocus.value
  if (!focus) return
  emit('openPairHeatmap', focus)
}

function openPairChord() {
  const focus = pairPlotFocus.value
  if (!focus) return
  emit('openPairChord', focus)
}

function openPreemptPlot(victimMk, preemptor) {
  const range = statsRange.value
  const plot = _buildPreemptPlot(props.trace, victimMk, preemptor, range)
  if (!plot || plot.points.length === 0) return
  openPlotRef.value = { mk: victimMk, kind: 'preempt', preemptor }
  selectedPlotPoint.value = -1
}

function openIntervalPlot(id) {
  const range = statsRange.value
  const plot = _buildIntervalPlot(props.trace, id, range)
  if (!plot || plot.points.length === 0) return
  openPlotRef.value = { intervalId: id, kind: 'interval' }
  selectedPlotPoint.value = -1
}

function openTagPlot(channel) {
  const range = statsRange.value
  const plot = _buildTagPlot(props.trace, channel, range)
  if (!plot || plot.points.length === 0) return
  openPlotRef.value = { tagChannel: channel, kind: 'tag' }
  selectedPlotPoint.value = -1
}

function openPriorityPlot(mk) {
  const range = statsRange.value
  const plot = _buildPriorityPlot(props.trace, mk, range)
  if (!plot || plot.points.length === 0) return
  openPlotRef.value = { mk, kind: 'priority' }
  selectedPlotPoint.value = -1
}

function openTickDistPlot() {
  const range = statsRange.value
  const plot = _buildTickDistPlot(props.trace, range)
  if (!plot || plot.points.length === 0) return
  openPlotRef.value = { kind: 'tick' }
  selectedPlotPoint.value = -1
}

function closePlot() {
  openPlotRef.value = null
  selectedPlotPoint.value = -1
}

function onPlotPointClick(point) {
  selectedPlotPoint.value = point.index
  const ns = annotationNsForPlotPoint(point)
  const note = point.label || ''
  const kind = openPlotRef.value?.kind
  const segment = (point.payload?.start != null && kind !== 'interval' && kind !== 'priority')
    ? point.payload
    : null
  const interval = (kind === 'interval' && point.payload?.startNs != null) ? point.payload : null
  const tagSample = ((kind === 'tag' || kind === 'tag_interval') && point.payload?.timeNs != null) ? point.payload : null
  const priorityRange = (kind === 'priority' && point.payload?.startNs != null)
    ? { startNs: point.payload.startNs, stopNs: point.payload.stopNs, mk: point.payload.mk }
    : null
  if (ns == null && !segment && !interval && !priorityRange && !tagSample) return
  emit('plotPointActivate', {
    ns,
    note,
    segment,
    interval,
    priorityRange,
    tagSample,
    tagChannel: openPlotRef.value?.tagChannel ?? tagSample?.channel ?? null,
  })
}

function annotationNsForPlotPoint(point) {
  const payload = point.payload
  // Interval plots use stop time on the x-axis — align the annotation with the clicked point.
  if (payload?.startNs != null && payload?.stopNs != null) return point.xNs ?? payload.stopNs
  if (payload?.start != null) return payload.start
  return point.xNs ?? null
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
  const showVariability = ['exec', 'block', 'inter', 'dispatch', 'switch_overhead'].includes(plot.kind)
  const yFormat = plot.kind === 'tag'
    ? (v) => formatTagValue(Math.round(v))
    : (v) => formatTime(Math.round(v), props.trace.timeScale)

  const scaleX = value => margin.left + ((value - x0) / xSpan) * plotW
  const scaleY = value => margin.top + plotH - (value / yMax) * plotH

  const sigmaLo = summary
    ? Math.max(0, summary.avg - summary.stddev)
    : 0
  const sigmaHi = summary
    ? Math.min(yMax, summary.avg + summary.stddev)
    : 0
  const refs = summary ? [
    { label: 'avg', y: scaleY(summary.avg), color: '#CE93D8' },
    { label: 'p5', y: scaleY(summary.p5), color: '#29B6F6' },
    { label: 'p50', y: scaleY(summary.p50), color: '#4CAF50' },
    { label: 'p95', y: scaleY(summary.p95), color: '#FF9800' },
  ] : []

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
      return { index, y: scaleY(value), label: yFormat(Math.round(value)) }
    }),
    sigmaBand: (summary && showVariability) ? {
      y: scaleY(sigmaHi),
      height: Math.max(1, scaleY(sigmaLo) - scaleY(sigmaHi)),
    } : null,
    referenceLines: refs,
    points: plot.points.map((point, index) => ({
      ...point,
      index,
      x: scaleX(point.xNs),
      y: scaleY(point.yValue),
      fillColor: point.fillColor || plot.color,
    })),
  }
})

function _scatterSvgPoint(event) {
  const svg = scatterSvgEl.value
  if (!svg) return null
  const pt = svg.createSVGPoint()
  pt.x = event.clientX
  pt.y = event.clientY
  const ctm = svg.getScreenCTM()
  if (!ctm) return null
  return pt.matrixTransform(ctm.inverse())
}

function _nearestScatterPointIndex(svgX, svgY, model) {
  if (!model?.points?.length) return -1
  const { margin, width, height } = model
  const plotLeft = margin.left
  const plotRight = width - margin.right
  const plotTop = margin.top
  const plotBottom = height - margin.bottom
  if (svgX < plotLeft || svgX > plotRight || svgY < plotTop || svgY > plotBottom) return -1
  let best = -1
  let bestD = Infinity
  for (const pt of model.points) {
    const dx = pt.x - svgX
    const dy = pt.y - svgY
    const d = dx * dx + dy * dy
    if (d < bestD) {
      bestD = d
      best = pt.index
    }
  }
  return best
}

function onScatterMouseMove(event) {
  const model = scatterModel.value
  if (!model) return
  const pt = _scatterSvgPoint(event)
  if (!pt) return
  plotHoverPointIndex.value = _nearestScatterPointIndex(pt.x, pt.y, model)
}

function onScatterMouseLeave() {
  plotHoverPointIndex.value = -1
}

const scatterCrosshair = computed(() => {
  const model = scatterModel.value
  const plot = plotData.value
  const idx = plotHoverPointIndex.value
  if (!model || idx < 0) return null
  const point = model.points.find(p => p.index === idx)
  if (!point) return null
  const plotLeft = model.margin.left
  const plotRight = model.width - model.margin.right
  const plotTop = model.margin.top
  const plotBottom = model.height - model.margin.bottom
  const yFmt = plot?.kind === 'tag'
    ? (v) => formatTagValue(v)
    : (v) => formatTime(v, props.trace.timeScale)
  const line1 = yFmt(point.yValue)
  const line2 = `@ ${formatTime(point.xNs, props.trace.timeScale)}`
  const tipW = Math.max(line1.length, line2.length) * 6.2 + 12
  const tipH = 30
  let tipX = point.x + 10
  let tipY = point.y - tipH / 2
  if (tipX + tipW > model.width - 4) tipX = point.x - tipW - 10
  if (tipY < 4) tipY = 4
  if (tipY + tipH > model.height - 4) tipY = model.height - tipH - 4
  return {
    x: point.x,
    y: point.y,
    plotLeft,
    plotRight,
    plotTop,
    plotBottom,
    tooltip: { x: tipX, y: tipY, width: tipW, height: tipH, line1, line2 },
  }
})

const histogramModel = computed(() => {
  const plot = plotData.value
  if (!plot || plot.points.length === 0) return null
  const values = plot.points.map(point => point.yValue)
  const isTagPlot = plot.kind === 'tag'
  const formatValue = isTagPlot
    ? (value) => formatTagValue(value)
    : (value) => formatTime(value, props.trace.timeScale)
  return buildHistogramModel(values, {
    scaleMode: histogramScaleMode.value,
    formatValue,
    valueAsTime: !isTagPlot,
    color: plot.color,
    showVariability: ['exec', 'block', 'inter', 'dispatch', 'switch_overhead'].includes(plot.kind),
  })
})

function _histogramSvgPoint(event) {
  const svg = histogramSvgEl.value
  if (!svg) return null
  const pt = svg.createSVGPoint()
  pt.x = event.clientX
  pt.y = event.clientY
  const ctm = svg.getScreenCTM()
  if (!ctm) return null
  return pt.matrixTransform(ctm.inverse())
}

function _histogramBarAt(svgX, svgY, model) {
  if (!model?.bars?.length) return -1
  const { margin, width, height, bars } = model
  if (svgX < margin.left || svgX > width - margin.right
      || svgY < margin.top || svgY > height - margin.bottom) return -1
  for (let i = 0; i < bars.length; i++) {
    const bar = bars[i]
    if (svgX >= bar.x && svgX <= bar.x + bar.width) return i
  }
  return -1
}

function onHistogramMouseMove(event) {
  const model = histogramModel.value
  if (!model) return
  const pt = _histogramSvgPoint(event)
  if (!pt) return
  histogramHoverIndex.value = _histogramBarAt(pt.x, pt.y, model)
}

function onHistogramMouseLeave() {
  histogramHoverIndex.value = -1
}

const histogramHoverTip = computed(() => {
  const model = histogramModel.value
  const plot = plotData.value
  const idx = histogramHoverIndex.value
  if (!model || idx < 0) return null
  const bar = model.bars[idx]
  if (!bar) return null
  const formatValue = plot?.kind === 'tag'
    ? (v) => formatTagValue(v)
    : (v) => formatTime(v, props.trace.timeScale)
  const { line1, line2 } = histogramBarTooltip(bar, model.sampleCount, formatValue)
  const tipW = Math.max(line1.length, line2.length) * 6.2 + 12
  const tipH = 30
  const cx = bar.x + bar.width / 2
  let tipX = cx + 10
  let tipY = bar.y - tipH / 2
  if (tipX + tipW > model.width - 4) tipX = cx - tipW - 10
  if (tipY < 4) tipY = 4
  if (tipY + tipH > model.height - 4) tipY = model.height - tipH - 4
  return { x: tipX, y: tipY, width: tipW, height: tipH, line1, line2 }
})

watch(histogramModel, () => {
  histogramHoverIndex.value = -1
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

// Wraps every <section class="report-card ..."> block in <details> so it can be
// collapsed/expanded, and builds a table-of-contents nav linking to each one.
function _makeCollapsibleSections(docHtml) {
  return htmlMakeCollapsibleSections(docHtml, STATS_DEFAULT_EXPANDED, STATS_TOC_GROUPS)
}

const _HTML_EXPORT_UTIL_CSS = `
    .util-list { display: flex; flex-direction: column; gap: 4px; }
    .util-row {
      display: flex;
      align-items: center;
      gap: 8px;
      min-height: 18px;
    }
    .util-label {
      flex: 0 0 128px;
      max-width: 128px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      text-align: left;
      font-size: 13px;
      color: var(--ink);
    }
    .util-bar {
      flex: 1 1 auto;
      height: 8px;
      min-width: 24px;
      border-radius: 4px;
      background: var(--line);
      overflow: hidden;
    }
    .util-bar-fill {
      height: 100%;
      border-radius: 4px;
      background: #5FCF6F;
    }
    .util-row-task .util-bar-fill { background: #5B9BD5; }
    .util-pct {
      flex: 0 0 44px;
      text-align: left;
      font-size: 13px;
    }
    .util-pct-core { color: #77BB77; }
    .util-pct-task { color: #6AAADD; }
`

function _htmlUtilBarRow(label, pct, kind) {
  const pctV = Math.max(0, Math.min(100, Number(pct) || 0))
  const rowCls = kind === 'core' ? 'util-row util-row-core' : 'util-row util-row-task'
  const pctCls = kind === 'core' ? 'util-pct util-pct-core' : 'util-pct util-pct-task'
  return `<div class="${rowCls}"><span class="util-label">${_htmlCell(label)}</span>`
    + `<div class="util-bar"><div class="util-bar-fill" style="width:${pctV.toFixed(1)}%"></div></div>`
    + `<span class="${pctCls}">${pctV.toFixed(1)}%</span></div>`
}

function _htmlUtilSection(title, rows, kind) {
  const body = rows.length
    ? `<div class="util-list">${rows.map(r => _htmlUtilBarRow(r.label, r.pct, kind)).join('')}</div>`
    : '<p class="empty">No data</p>'
  return `<section class="report-card"><h2>${_htmlCell(title)}</h2>${body}</section>`
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
  const { rows: preemptReportRows } = preemptionChainRows(tr, lo, hi)
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
  const lbCsv = loadBalanceScore.value
  if (lbCsv) {
    lines.push(`Load Balance Score,${_csvCell(`${lbCsv.score.toFixed(0)}%`)}`)
    lines.push(`Core Util Std Dev (σ),${_csvCell(`${lbCsv.stddev.toFixed(1)}%`)}`)
    lines.push(`Gini Coefficient (G),${_csvCell(lbCsv.gini.toFixed(4))}`)
  }
  lines.push('Core,CPU %')
  if (coreRows.length > 0) {
    for (const r of coreRows) {
      lines.push(`${_csvCell(r.core)},${_csvCell(`${r.pct}%`)}`)
    }
  } else {
    lines.push('No data,')
  }

  const tick = tickHealthReport(tr, lo, hi)
  lines.push('')
  lines.push(`Trace Health (TICK)${suffix}`)
  if (tick.tickCount) {
    lines.push(`Status,${_csvCell(tick.health.toUpperCase())}`)
    lines.push(`Mode,${_csvCell(tick.isTickless ? 'TICKLESS' : 'TICK')}`)
    lines.push(`Interval CV,${_csvCell((tick.tickCv * 100).toFixed(2) + '%')}`)
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

  const bdRows = buildCoreTimeBreakdown(tr, lo, hi)
  lines.push('')
  lines.push(`Core Time Breakdown${suffix}`)
  lines.push('Core,Active %,Idle %,Tick %,Gap %')
  if (bdRows.length) {
    for (const r of bdRows) {
      const s = Math.max(r.spanNs, 1)
      lines.push([
        _csvCell(r.core),
        _csvCell(`${(100 * r.activeNs / s).toFixed(1)}%`),
        _csvCell(`${(100 * r.idleNs / s).toFixed(1)}%`),
        _csvCell(`${(100 * r.tickNs / s).toFixed(1)}%`),
        _csvCell(`${(100 * r.gapNs / s).toFixed(1)}%`),
      ].join(','))
    }
  } else {
    lines.push('No core data,,,,')
  }
  lines.push('')
  lines.push(`Concurrent Core Active Distribution${suffix}`)
  lines.push('Active Cores,Duration,% of Span')
  const ccCsvRows = concurrentCoreActiveRows(tr, lo, hi)
  if (ccCsvRows.length) {
    for (const r of ccCsvRows) {
      lines.push([
        _csvCell(r.activeCores),
        _csvCell(r.duration),
        _csvCell(`${r.pctOfSpan.toFixed(1)}%`),
      ].join(','))
    }
  } else {
    lines.push('No data,,')
  }

  lines.push('')
  lines.push(`Kernel Switch Overhead${suffix}`)
  lines.push('Core,Switches,Min,Avg,Max,Total Overhead,% of Core')
  const swCsvRows = switchOverheadRows(tr, lo, hi)
  if (swCsvRows.length) {
    for (const r of swCsvRows) {
      lines.push([
        _csvCell(r.core),
        _csvCell(r.switches),
        _csvCell(r.min),
        _csvCell(r.avg),
        _csvCell(r.max),
        _csvCell(r.total),
        _csvCell(`${r.pctOfCore.toFixed(2)}%`),
      ].join(','))
    }
  } else {
    lines.push('No data,,,,,,')
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

  lines.push('')
  lines.push(`Core Migrations${suffix}`)
  lines.push('Task,Migrations,Migr rate,Avg dwell,Core count,Primary core,Primary %,Ping-pong,STI near,Avg gap after,Avg gap other')
  const migReportRows = migrationRows(tr, lo, hi)
  for (const r of migReportRows) {
    lines.push([
      _csvCell(r.name),
      _csvCell(r.migrations),
      _csvCell(r.migrRate),
      _csvCell(r.avgDwell),
      _csvCell(r.coreCount),
      _csvCell(r.primary),
      _csvCell(`${r.primaryPct.toFixed(1)}%`),
      _csvCell(r.pingPong),
      _csvCell(r.stiNear),
      _csvCell(r.gapAfter),
      _csvCell(r.gapOther),
    ].join(','))
  }

  const scale = tr.timeScale
  const pairRows = buildCorePairRows(tr, lo, hi)
  lines.push('')
  lines.push(`Core-Pair Migration Summary${suffix}`)
  lines.push('From,To,Count,Bounces,Bounce %,Avg Gap')
  if (pairRows.length) {
    for (const r of pairRows) {
      lines.push([
        _csvCell(r.fromCore),
        _csvCell(r.toCore),
        _csvCell(r.count),
        _csvCell(r.bounces),
        _csvCell(`${r.bouncePct.toFixed(1)}%`),
        _csvCell(formatMigrationGapTime(r.avgGapNs, scale)),
      ].join(','))
    }
  } else {
    lines.push('No migrations in scope,,,,,')
  }

  const affRows = coreAffinityRows.value
  lines.push('')
  lines.push(`Core Affinity${suffix}`)
  lines.push('Task,Mask,Observed Cores,Violations')
  if (affRows.length) {
    for (const r of affRows) {
      lines.push([_csvCell(r.label), _csvCell(r.maskHex), _csvCell(r.observedCores), _csvCell(r.violations)].join(','))
    }
  } else {
    lines.push('No affinity_set events,,,')
  }

  const tcCsv = taskCoreModel.value
  const tcCores = tcCsv.cores || []
  lines.push('')
  lines.push(`Task × Core${suffix}`)
  lines.push(['Task', ...tcCores].join(','))
  if ((tcCsv.rows || []).length) {
    for (const row of tcCsv.rows) {
      lines.push([
        _csvCell(row.task),
        ...tcCores.map(c => {
          const cell = row.cells?.[c]
          return cell?.ns ? _csvCell(`${cell.pct_span.toFixed(1)}%`) : ''
        }),
      ].join(','))
    }
  } else {
    lines.push(['No on-CPU slices', ...tcCores.map(() => '')].join(','))
  }

  const ctCsv = coreTimeModel.value
  const ctCores = ctCsv.cores || []
  lines.push('')
  lines.push(`Core Utilization Over Time${suffix}`)
  lines.push(['Time', ...ctCores].join(','))
  if ((ctCsv.bins || []).length) {
    for (const row of ctCsv.bins) {
      lines.push([
        _csvCell(formatTime(row.start, scale)),
        ...ctCores.map(c => {
          const cell = row.cells?.[c]
          return cell ? _csvCell(`${cell.pct.toFixed(1)}%`) : ''
        }),
      ].join(','))
    }
  } else {
    lines.push(['No on-CPU slices', ...ctCores.map(() => '')].join(','))
  }

  const lcRows = buildTaskLifecycleRows(tr.stiEvents ?? [], tr.taskRepr, lo, hi, tr.taskCreateTimes, tr.segByMergeKey)
  lines.push('')
  lines.push(`Task Lifecycle${suffix}`)
  lines.push('Task,Created,Deleted,Susp/Res,Alive span,Events,Runs')
  if (lcRows.length) {
    for (const r of lcRows) {
      lines.push([
        _csvCell(r.label),
        r.createNs != null ? _csvCell(formatTime(r.createNs, scale)) : '',
        r.deleteNs != null ? _csvCell(formatTime(r.deleteNs, scale)) : '',
        _csvCell(`${r.suspendCount}/${r.resumeCount}`),
        r.aliveSpanNs ? _csvCell(formatLifecycleSpan(r.aliveSpanNs, scale)) : '',
        _csvCell(r.eventCount),
        _csvCell(r.runCount),
      ].join(','))
    }
  } else {
    lines.push('No lifecycle events,,,,,,')
  }

  if (hasDeadlineConfig.value) {
    const { sliceViolations, cpuViolations } = deadlineViolations.value
    lines.push('')
    lines.push(`Deadlines / CPU budget${suffix}`)
    lines.push('Slice Violations')
    lines.push('Task,Duration,Limit,Over by')
    if (sliceViolations.length) {
      for (const v of sliceViolations) {
        lines.push([
          _csvCell(v.label),
          _csvCell(v.duration),
          _csvCell(v.limit),
          _csvCell(v.overBy),
        ].join(','))
      }
    } else {
      lines.push('No slice violations,,,')
    }
    lines.push('')
    lines.push('CPU Budget Violations')
    lines.push('Task,CPU %,Budget')
    if (cpuViolations.length) {
      for (const v of cpuViolations) {
        lines.push([
          _csvCell(v.label),
          _csvCell(`${v.pct}%`),
          _csvCell(`${v.budgetPct}%`),
        ].join(','))
      }
    } else {
      lines.push('No CPU budget violations,,')
    }
  }

  const thCsv = taskHealthRows.value
  lines.push('')
  lines.push(`Task Health${suffix}`)
  lines.push('Task,Score,Exec,Block,Period,Mig,Deadline,CPU')
  if (thCsv.length) {
    for (const r of thCsv) {
      lines.push([
        _csvCell(r.task),
        _csvCell(r.score),
        _csvCell(r.marks.execution || ''),
        _csvCell(r.marks.blocking || ''),
        _csvCell(r.marks.period || ''),
        _csvCell(r.marks.migration || ''),
        _csvCell(r.marks.deadline || ''),
        _csvCell(r.marks.cpu || ''),
      ].join(','))
    }
  } else {
    lines.push('No task slices,,,,,,,')
  }

  lines.push('')
  lines.push(`Timeline Anomalies${suffix}`)
  lines.push('Time,Kind,Task,Duration,Why')
  if (anomalyRows.value.length) {
    for (const r of anomalyRows.value) {
      lines.push([
        _csvCell(formatTime(r.start, scale)),
        _csvCell(uxKindLabel(r.kind)),
        _csvCell(r.task),
        _csvCell(formatTime(r.duration, scale)),
        _csvCell(r.reason || ''),
      ].join(','))
    }
  } else {
    lines.push('No timeline anomalies in this scope,,,,')
  }

  lines.push('')
  lines.push(`Worst Events${suffix}`)
  lines.push('Time,Kind,Task,Duration,Why')
  if (worstRows.value.length) {
    for (const r of worstRows.value) {
      lines.push([
        _csvCell(formatTime(r.start, scale)),
        _csvCell(uxKindLabel(r.kind)),
        _csvCell(r.task),
        _csvCell(formatTime(r.duration, scale)),
        _csvCell(r.reason || uxKindLabel(r.kind)),
      ].join(','))
    }
  } else {
    lines.push('No episodes in this scope,,,,')
  }

  lines.push('')
  lines.push(`Critical Path${suffix}`)
  lines.push('Task,Duration,Exec,Preempt,Wait,Mig,Other')
  if (critPathRows.value.length) {
    for (const r of critPathRows.value) {
      lines.push([
        _csvCell(r.task),
        _csvCell(formatTime(r.duration, scale)),
        _csvCell(formatTime(r.exec_ns, scale)),
        _csvCell(formatTime(r.preempt_ns, scale)),
        _csvCell(formatTime(r.wait_ns, scale)),
        _csvCell(formatTime(r.migration_ns, scale)),
        _csvCell(formatTime(r.other_ns, scale)),
      ].join(','))
    }
  } else {
    lines.push('Need at least one on-CPU slice,,,,,')
  }

  lines.push('')
  lines.push(`Recurring Patterns${suffix}`)
  lines.push('Task,Kind,Count,Worst,Why')
  if (patternRows.value.length) {
    for (const r of patternRows.value) {
      lines.push([
        _csvCell(r.task),
        _csvCell(uxKindLabel(r.kind)),
        _csvCell(r.count),
        _csvCell(formatTime(r.duration, scale)),
        _csvCell(r.reason || ''),
      ].join(','))
    }
  } else {
    lines.push('No repeating anomaly kinds in this scope,,,,')
  }

  lines.push('')
  lines.push(`Execution Time Per Slice${suffix}`)
  lines.push('Task,Runs,CPU%,Min,Avg,TrimMean(5%),Max,Jitter,StdDev (population),p50,p95')
  for (const r of execReportRows) {
    lines.push([
      _csvCell(r.name),
      _csvCell(r.runs),
      _csvCell(`${r.cpuPct.toFixed(1)}%`),
      _csvCell(r.min),
      _csvCell(r.avg),
      _csvCell(r.trimMean),
      _csvCell(r.max),
      _csvCell(r.jitter),
      _csvCell(r.stddev),
      _csvCell(r.p50),
      _csvCell(r.p95),
    ].join(','))
  }

  lines.push('')
  lines.push(`Blocking Time (off-CPU gap)${suffix}`)
  lines.push('Task,Gaps,Min,Avg,TrimMean(5%),Max,Jitter,StdDev (population),p50,p95')
  for (const r of blockReportRows) {
    lines.push([
      _csvCell(r.name),
      _csvCell(r.runs),
      _csvCell(r.min),
      _csvCell(r.avg),
      _csvCell(r.trimMean),
      _csvCell(r.max),
      _csvCell(r.jitter),
      _csvCell(r.stddev),
      _csvCell(r.p50),
      _csvCell(r.p95),
    ].join(','))
  }

  lines.push('')
  lines.push(`Dispatch / Scheduling Latency${suffix}`)
  lines.push('Task,Activations,Min,Avg,Max,Jitter,StdDev (population),p95,p99')
  const dispCsvRows = dispatchLatencyRows(tr, lo, hi)
  if (dispCsvRows.length) {
    for (const r of dispCsvRows) {
      lines.push([
        _csvCell(r.label),
        _csvCell(r.activations),
        _csvCell(r.min),
        _csvCell(r.avg),
        _csvCell(r.max),
        _csvCell(r.jitter),
        _csvCell(r.stddev),
        _csvCell(r.p95),
        _csvCell(r.p99),
      ].join(','))
    }
  } else {
    lines.push('No data,,,,,,,,')
  }

  lines.push('')
  lines.push(`Inter-Arrival Time${suffix}`)
  lines.push('Task,Runs,Min,Avg,TrimMean(5%),Max,Jitter,StdDev (population),p50,p95')
  for (const r of interReportRows) {
    lines.push([
      _csvCell(r.name),
      _csvCell(r.runs),
      _csvCell(r.min),
      _csvCell(r.avg),
      _csvCell(r.trimMean),
      _csvCell(r.max),
      _csvCell(r.jitter),
      _csvCell(r.stddev),
      _csvCell(r.p50),
      _csvCell(r.p95),
    ].join(','))
  }

  const perCsv = periodRows.value
  lines.push('')
  lines.push(`Period / Jitter${suffix}`)
  lines.push('Task,N,Expected,Min,Avg,Max,p95,p99,RMS,CV,Missed,Extra,Burst,Spark')
  if (perCsv.length) {
    for (const r of perCsv) {
      lines.push([
        _csvCell(r.task),
        _csvCell(r.n),
        _csvCell(formatTime(r.expected_ns, tr.timeScale)),
        _csvCell(formatTime(r.min_ns, tr.timeScale)),
        _csvCell(formatTime(r.avg_ns, tr.timeScale)),
        _csvCell(formatTime(r.max_ns, tr.timeScale)),
        _csvCell(formatTime(r.p95_ns, tr.timeScale)),
        _csvCell(formatTime(r.p99_ns, tr.timeScale)),
        _csvCell(formatTime(r.rms_ns, tr.timeScale)),
        _csvCell(`${(r.cv * 100).toFixed(1)}%`),
        _csvCell(r.missed),
        _csvCell(r.extra),
        _csvCell(r.burst || 0),
        _csvCell(r.spark || ''),
      ].join(','))
    }
  } else {
    lines.push('Need at least 3 inter-arrival gaps per task,,,,,,,,,,,,')
  }

  lines.push('')
  lines.push(`Response Time${suffix}`)
  lines.push('Task,N,Min,Avg,Max,p50,p90,p95,p99,p99.9,Jitter,CV')
  if (responseRows.value.length) {
    for (const r of responseRows.value) {
      lines.push([
        _csvCell(r.task),
        _csvCell(r.n),
        _csvCell(formatTime(r.min_ns, scale)),
        _csvCell(formatTime(r.avg_ns, scale)),
        _csvCell(formatTime(r.max_ns, scale)),
        _csvCell(formatTime(r.p50_ns, scale)),
        _csvCell(formatTime(r.p90_ns, scale)),
        _csvCell(formatTime(r.p95_ns, scale)),
        _csvCell(formatTime(r.p99_ns, scale)),
        _csvCell(formatTime(r.p999_ns, scale)),
        _csvCell(formatTime(r.jitter_ns, scale)),
        _csvCell(`${((r.cv || 0) * 100).toFixed(1)}%`),
      ].join(','))
    }
  } else {
    lines.push('Need at least one on-CPU slice,,,,,,,,,,,')
  }

  lines.push('')
  lines.push(`Unified Jitter${suffix}`)
  lines.push('Task,Exec,Exec CV,Block,Block CV,Inter,Inter CV,Response,Resp CV,Dispatch,Disp CV,Wake,Wake CV')
  if (jitterRows.value.length) {
    for (const r of jitterRows.value) {
      lines.push([
        _csvCell(r.task),
        _csvCell(formatTime(r.exec_jitter_ns, scale)),
        _csvCell(`${((r.exec_cv || 0) * 100).toFixed(1)}%`),
        _csvCell(formatTime(r.block_jitter_ns, scale)),
        _csvCell(`${((r.block_cv || 0) * 100).toFixed(1)}%`),
        _csvCell(formatTime(r.inter_jitter_ns, scale)),
        _csvCell(`${((r.inter_cv || 0) * 100).toFixed(1)}%`),
        _csvCell(formatTime(r.response_jitter_ns, scale)),
        _csvCell(`${((r.response_cv || 0) * 100).toFixed(1)}%`),
        _csvCell(formatTime(r.dispatch_jitter_ns, scale)),
        _csvCell(`${((r.dispatch_cv || 0) * 100).toFixed(1)}%`),
        _csvCell(formatTime(r.wakeup_jitter_ns, scale)),
        _csvCell(`${((r.wakeup_cv || 0) * 100).toFixed(1)}%`),
      ].join(','))
    }
  } else {
    lines.push('No timing samples in this scope,,,,,,,,,,,,')
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
  lines.push(`Preemption Matrix${suffix}`)
  lines.push('Victim,Count,Total,Max,Top preemptors,Story')
  if (preemptRankRows.value.length) {
    for (const r of preemptRankRows.value) {
      lines.push([
        _csvCell(r.task),
        _csvCell(r.count),
        _csvCell(formatTime(r.total_ns, scale)),
        _csvCell(formatTime(r.max_ns, scale)),
        _csvCell(r.top_label || ''),
        _csvCell(r.story || ''),
      ].join(','))
    }
  } else {
    lines.push('No preemption overlaps in this scope,,,,')
  }

  lines.push('')
  lines.push(`Priority Inheritance${suffix}`)
  lines.push('Task,Base,Peak,Boosts,Boosted,Pattern')
  const priorityReportRows = priorityStatsRows(tr, lo, hi)
  if (priorityReportRows.length) {
    for (const row of priorityReportRows) {
      lines.push([
        _csvCell(row.label),
        _csvCell(row.basePri),
        _csvCell(row.peakPri),
        _csvCell(row.episodeCount),
        _csvCell(row.total),
        _csvCell(row.pattern),
      ].join(','))
    }
  } else if (tr?.hasPriorityInstrumentation) {
    lines.push('No priority boosts in scope,,,,,')
  }

  lines.push('')
  lines.push(`Mutex / Semaphore${suffix}`)
  lines.push('Object,Kind,Holds,Issues,Bounces,Avg hold,Status')
  const syncReportRows = syncObjectStatsRows(tr, lo, hi)
  if (syncReportRows.length) {
    for (const row of syncReportRows) {
      lines.push([
        _csvCell(row.label),
        _csvCell(row.kind),
        _csvCell(row.holdCount),
        _csvCell(row.issueCount),
        _csvCell(row.bounceCount ?? 0),
        _csvCell(row.avgHold),
        _csvCell(row.statusLabel),
      ].join(','))
    }
    const bounced = syncReportRows.filter(r => (r.bounceCount || 0) > 0)
    if (bounced.length) {
      lines.push('')
      lines.push(`Core Affinity Violations (lock bounce)${suffix}`)
      lines.push('Object,Bounces,Description')
      for (const row of bounced) {
        const n = row.bounceCount
        lines.push([
          _csvCell(row.label),
          _csvCell(n),
          _csvCell(`${n} hold(s) crossed core boundaries`),
        ].join(','))
      }
    }
  } else if (tr?.hasSyncObjectInstrumentation) {
    lines.push('No mutex/sem activity in scope,,,,,,')
  }

  if (tr?.hasSyncObjectInstrumentation) {
    lines.push('')
    lines.push(`Pairing Issues${suffix}`)
    lines.push('Object,Time,Detail,Issue,Task,Core')
    const issueReportRows = syncObjectIssueRows(tr, lo, hi)
    if (issueReportRows.length) {
      for (const iss of issueReportRows) {
        lines.push([
          _csvCell(iss.objKey || ''),
          _csvCell(formatTime(iss.timeNs, tr.timeScale)),
          _csvCell(iss.detail),
          _csvCell(iss.kind),
          _csvCell(iss.taskLabel || ''),
          _csvCell(iss.core || ''),
        ].join(','))
      }
    } else {
      lines.push('No pairing issues in scope,,,,,')
    }
  }

  const woCsv = waitOwnerModel.value
  const woTasks = woCsv.tasks || []
  lines.push('')
  lines.push(`Waiter × Owner${suffix}`)
  lines.push(['Waiter \\ Owner', ...woTasks.map(t => t.task)].join(','))
  if (woTasks.length) {
    for (const w of woTasks) {
      lines.push([
        _csvCell(w.task),
        ...woTasks.map(o => {
          if (w.mk === o.mk) return ''
          const cell = woCsv.cells[`${w.mk}|${o.mk}`]
          return cell?.ns ? _csvCell(formatTime(cell.ns, tr.timeScale)) : ''
        }),
      ].join(','))
    }
  } else {
    lines.push('No mutex handoffs in this scope')
  }

  lines.push('')
  lines.push(`Mutex Blocking${suffix}`)
  lines.push('Task,Object,Owner,Count,Total,Max')
  if (mutexBlockRows.value.length) {
    for (const r of mutexBlockRows.value) {
      lines.push([
        _csvCell(r.task),
        _csvCell(r.object),
        _csvCell(r.owner),
        _csvCell(r.count),
        _csvCell(formatTime(r.total_ns, scale)),
        _csvCell(formatTime(r.max_ns, scale)),
      ].join(','))
    }
  } else {
    lines.push('No mutex waits in this scope,,,,,')
  }

  const queueReportRows = syncObjectStatsRows(tr, lo, hi, { kindFilter: 'queue' })
  lines.push('')
  lines.push(`Queue${suffix}`)
  lines.push('Object,Kind,Holds,Issues,Bounces,Avg hold,Status')
  if (queueReportRows.length) {
    for (const row of queueReportRows) {
      lines.push([
        _csvCell(row.label),
        _csvCell(row.kind),
        _csvCell(row.holdCount),
        _csvCell(row.issueCount),
        _csvCell(row.bounceCount ?? 0),
        _csvCell(row.avgHold),
        _csvCell(row.statusLabel),
      ].join(','))
    }
  } else if (tr?.hasSyncObjectInstrumentation) {
    lines.push('No queue activity in scope,,,,,,')
  }

  const intervalReportRows = intervalStatsRows(tr, lo, hi)
  lines.push('')
  lines.push(`Interval Analysis${suffix}`)
  lines.push('ID,Label,Count,Min,Avg,Max,p95')
  if (intervalReportRows.length) {
    for (const row of intervalReportRows) {
      lines.push([
        _csvCell(row.id),
        _csvCell(row.label),
        _csvCell(row.count),
        _csvCell(row.min),
        _csvCell(row.avg),
        _csvCell(row.max),
        _csvCell(row.p95),
      ].join(','))
    }
  } else {
    lines.push('No interval data,,,,,,')
  }

  const tagReportRows = tagStatsRows(tr, lo, hi)
  lines.push('')
  lines.push(`Tag Analysis${suffix}`)
  lines.push('Channel,Label,Count,Min,Avg,Max,p95')
  if (tagReportRows.length) {
    for (const row of tagReportRows) {
      lines.push([
        _csvCell(row.channel),
        _csvCell(row.label),
        _csvCell(row.count),
        _csvCell(row.min),
        _csvCell(row.avg),
        _csvCell(row.max),
        _csvCell(row.p95),
      ].join(','))
    }
  } else {
    lines.push('No tag data,,,,,,')
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
  const mean = sum / n
  const trimCount = Math.floor(n * 0.05)
  const trimVals = (trimCount * 2) < n ? sorted.slice(trimCount, n - trimCount) : sorted
  const trimSum = trimVals.reduce((a, b) => a + b, 0)
  const jitter = sorted[n - 1] - sorted[0]
  const stddev = Math.sqrt(
    sorted.reduce((acc, value) => acc + ((value - mean) ** 2), 0) / n,
  )
  return {
    min: formatTime(sorted[0], scale),
    avg: formatTime(Math.round(mean), scale),
    trimMean: formatTime(Math.round(trimSum / trimVals.length), scale),
    max: formatTime(sorted[n - 1], scale),
    jitter: formatTime(jitter, scale),
    stddev: formatTime(Math.round(stddev), scale),
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
      jitter: summary.jitter,
      stddev: summary.stddev,
      p50: summary.p50,
      p95: summary.p95,
    })
  }

  return rows.sort((a, b) => b.cpuPct - a.cpuPct || b.runs - a.runs
    || a.name.localeCompare(b.name))
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
      jitter: summary.jitter,
      stddev: summary.stddev,
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
      jitter: summary.jitter,
      stddev: summary.stddev,
      p50: summary.p50,
      p95: summary.p95,
    })
  }

  return rows.sort((a, b) => b.runs - a.runs || a.name.localeCompare(b.name))
}

function _renderHtmlTableReport(title, rows, includeCpu = false) {
  const head = includeCpu
    ? '<tr><th>Task</th><th>Runs</th><th>CPU%</th><th>Min</th><th>Avg</th><th>TrimMean(5%)</th><th>Max</th><th>Jitter</th><th>σ</th><th>p50</th><th>p95</th></tr>'
    : '<tr><th>Task</th><th>Runs</th><th>Min</th><th>Avg</th><th>TrimMean(5%)</th><th>Max</th><th>Jitter</th><th>σ</th><th>p50</th><th>p95</th></tr>'
  const body = rows.length
    ? rows.map(r => includeCpu
      ? `<tr><td>${_htmlCell(r.name)}</td><td>${_htmlCell(r.runs)}</td><td>${_htmlCell(r.cpuPct.toFixed(1))}%</td><td>${_htmlCell(r.min)}</td><td>${_htmlCell(r.avg)}</td><td>${_htmlCell(r.trimMean)}</td><td>${_htmlCell(r.max)}</td><td>${_htmlCell(r.jitter)}</td><td>${_htmlCell(r.stddev)}</td><td>${_htmlCell(r.p50)}</td><td>${_htmlCell(r.p95)}</td></tr>`
      : `<tr><td>${_htmlCell(r.name)}</td><td>${_htmlCell(r.runs)}</td><td>${_htmlCell(r.min)}</td><td>${_htmlCell(r.avg)}</td><td>${_htmlCell(r.trimMean)}</td><td>${_htmlCell(r.max)}</td><td>${_htmlCell(r.jitter)}</td><td>${_htmlCell(r.stddev)}</td><td>${_htmlCell(r.p50)}</td><td>${_htmlCell(r.p95)}</td></tr>`,
    ).join('')
    : `<tr><td colspan="${includeCpu ? 11 : 10}" class="empty">No data</td></tr>`
  return `<section class="report-card"><h2>${_htmlCell(title)}</h2><table><thead>${head}</thead><tbody>${body}</tbody></table></section>`
}

function _coreUtilRows(tr, range) {
  const rows = coreUtilPctRows(tr, range?.lo ?? null, range?.hi ?? null)
  return rows.map(r => ({ core: r.core, pct: Number(r.pct).toFixed(1) }))
}

function _taskCpuRows(tr, range) {
  if (!tr) return []
  const total = range ? (range.hi - range.lo) : (tr.timeMax - tr.timeMin)
  if (total <= 0) return []
  if (!range && tr.taskCpuNs?.length) {
    return tr.taskCpuNs.slice(0, 10).map(([mk, t]) => ({
      name: taskDisplayName(taskReprGet(tr, mk) || mk),
      pct: (100.0 * t / total).toFixed(1),
    }))
  }
  if (!tr.segByMergeKey) return []
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

function _issueSeverityClass(severity) {
  if (severity === 'error') return 'sev-error'
  if (severity === 'warning') return 'sev-warning'
  return ''
}

function _renderSyncObjectReportHtml(tr, lo, hi, suffix) {
  const syncHtmlRows = syncObjectStatsRows(tr, lo, hi)
  const issues = syncObjectIssueRows(tr, lo, hi)
  const holds = syncObjectHoldDetailRows(tr, lo, hi, 150)
  const summaryBody = syncHtmlRows.length
    ? syncHtmlRows.map(row =>
        `<tr><td>${_htmlCell(row.label)}</td><td>${_htmlCell(row.kind)}</td><td>${row.holdCount}</td><td>${row.issueCount}</td>`
        + `<td class="${row.bounceCount > 0 ? 'sev-warning' : ''}">${row.bounceCount ?? 0}</td>`
        + `<td>${_htmlCell(row.avgHold)}</td><td class="${syncStatusClass(row.status)}">${_htmlCell(row.statusLabel)}</td></tr>`,
      ).join('')
    : '<tr><td colspan="7" class="empty">No mutex/sem activity in scope</td></tr>'
  const issueBody = issues.length
    ? issues.map(iss =>
        `<tr><td>${_htmlCell(iss.objKey || '—')}</td><td>${_htmlCell(formatTime(iss.timeNs, tr.timeScale))}</td><td>${_htmlCell(iss.detail)}</td><td class="${_issueSeverityClass(iss.severity)}">${_htmlCell(iss.kind)}</td><td>${_htmlCell(iss.taskLabel || '—')}</td><td>${_htmlCell(iss.core || '')}</td></tr>`,
      ).join('')
    : '<tr><td colspan="6" class="empty">No pairing issues in scope</td></tr>'
  const holdBody = holds.length
    ? holds.map(h =>
        `<tr><td>${_htmlCell(h.object)}</td><td>${_htmlCell(h.holder)}</td><td>${_htmlCell(h.start)}</td><td>${_htmlCell(h.stop)}</td><td>${_htmlCell(h.duration)}</td><td>${_htmlCell(h.takeCore)}</td><td>${_htmlCell(h.giveCore)}</td></tr>`,
      ).join('')
    : '<tr><td colspan="7" class="empty">No paired holds in scope</td></tr>'
  const holdNote = holds.length >= 150
    ? '<p class="detail-note">Showing longest 150 hold episodes in scope.</p>'
    : ''
  return `<section class="report-card"><h2>Mutex / Semaphore${_htmlCell(suffix)}</h2>
    <table><thead><tr><th>Object</th><th>Kind</th><th>Holds</th><th>Issues</th><th>Bounces</th><th>Avg hold</th><th>Status</th></tr></thead>
    <tbody>${summaryBody}</tbody></table>
    <h3 class="sub">Pairing issues</h3>
    <table><thead><tr><th>Object</th><th>Time</th><th>Detail</th><th>Issue</th><th>Task</th><th>Core</th></tr></thead>
    <tbody>${issueBody}</tbody></table>
    <h3 class="sub">Hold episodes (longest first)</h3>
    ${holdNote}
    <table><thead><tr><th>Object</th><th>Holder</th><th>Take</th><th>Give</th><th>Duration</th><th>Take core</th><th>Give core</th></tr></thead>
    <tbody>${holdBody}</tbody></table></section>`
}

function _renderPriorityReportHtml(tr, lo, hi, suffix) {
  const priorityHtmlRows = priorityStatsRows(tr, lo, hi)
  const episodes = priorityEpisodeDetailRows(tr, lo, hi, 200)
  const summaryBody = priorityHtmlRows.length
    ? priorityHtmlRows.map(row =>
        `<tr><td>${_htmlCell(row.label)}</td><td>${row.basePri}</td><td>${row.peakPri}</td><td>${row.episodeCount}</td><td>${_htmlCell(row.total)}</td><td>${_htmlCell(row.pattern)}</td></tr>`,
      ).join('')
    : '<tr><td colspan="6" class="empty">No priority boosts in scope</td></tr>'
  const epBody = episodes.length
    ? episodes.map(ep =>
        `<tr><td>${_htmlCell(ep.task)}</td><td>${ep.basePri}→${ep.peakPri}</td><td>${_htmlCell(ep.start)}</td><td>${_htmlCell(ep.stop)}</td><td>${_htmlCell(ep.duration)}</td><td>${_htmlCell(ep.pattern)}</td></tr>`,
      ).join('')
    : '<tr><td colspan="6" class="empty">No boost episodes in scope</td></tr>'
  const epNote = episodes.length >= 200
    ? '<p class="detail-note">Showing first 200 boost episodes in scope (by start time).</p>'
    : ''
  return `<section class="report-card"><h2>Priority Inheritance${_htmlCell(suffix)}</h2>
    <table><thead><tr><th>Task</th><th>Base</th><th>Peak</th><th>Boosts</th><th>Boosted</th><th>Pattern</th></tr></thead>
    <tbody>${summaryBody}</tbody></table>
    <h3 class="sub">Boost episodes</h3>
    ${epNote}
    <table><thead><tr><th>Task</th><th>pri</th><th>Start</th><th>End</th><th>Duration</th><th>Pattern</th></tr></thead>
    <tbody>${epBody}</tbody></table></section>`
}

function _renderIntervalReportHtml(tr, lo, hi, suffix) {
  const intervalHtmlRows = intervalStatsRows(tr, lo, hi)
  const instances = intervalInstanceDetailRows(tr, lo, hi, 200)
  const summaryBody = intervalHtmlRows.length
    ? intervalHtmlRows.map(row =>
        `<tr><td>${_htmlCell(row.id)}</td><td>${_htmlCell(row.label)}</td><td>${row.count}</td><td>${_htmlCell(row.min)}</td><td>${_htmlCell(row.avg)}</td><td>${_htmlCell(row.max)}</td><td>${_htmlCell(row.p95)}</td></tr>`,
      ).join('')
    : '<tr><td colspan="7" class="empty">No interval data</td></tr>'
  const instBody = instances.length
    ? instances.map(inst =>
        `<tr><td>${_htmlCell(inst.id)}</td><td>${_htmlCell(inst.taskId || '—')}</td><td>${_htmlCell(inst.start)}</td><td>${_htmlCell(inst.stop)}</td><td>${_htmlCell(inst.duration)}</td><td>${_htmlCell(inst.startCore)}</td><td>${_htmlCell(inst.stopCore)}</td></tr>`,
      ).join('')
    : '<tr><td colspan="7" class="empty">No interval instances in scope</td></tr>'
  const instNote = instances.length >= 200
    ? '<p class="detail-note">Showing longest 200 interval instances in scope.</p>'
    : ''
  return `<section class="report-card"><h2>Interval Analysis${_htmlCell(suffix)}</h2>
    <table><thead><tr><th>ID</th><th>Label</th><th>Count</th><th>Min</th><th>Avg</th><th>Max</th><th>p95</th></tr></thead>
    <tbody>${summaryBody}</tbody></table>
    <h3 class="sub">Interval instances (longest first)</h3>
    ${instNote}
    <table><thead><tr><th>ID</th><th>Task id</th><th>Start</th><th>Stop</th><th>Duration</th><th>Start core</th><th>Stop core</th></tr></thead>
    <tbody>${instBody}</tbody></table></section>`
}

function _renderTagReportHtml(tr, lo, hi, suffix) {
  const tagHtmlRows = tagStatsRows(tr, lo, hi)
  const samples = tagSampleDetailRows(tr, lo, hi, 200)
  const summaryBody = tagHtmlRows.length
    ? tagHtmlRows.map(row =>
        `<tr><td>${_htmlCell(row.channel)}</td><td>${_htmlCell(row.label)}</td><td>${row.count}</td><td>${_htmlCell(row.min)}</td><td>${_htmlCell(row.avg)}</td><td>${_htmlCell(row.max)}</td><td>${_htmlCell(row.p95)}</td></tr>`,
      ).join('')
    : '<tr><td colspan="7" class="empty">No tag data</td></tr>'
  return `<section class="report-card"><h2>Tag Analysis${_htmlCell(suffix)}</h2>
    <table><thead><tr><th>Channel</th><th>Label</th><th>Count</th><th>Min</th><th>Avg</th><th>Max</th><th>p95</th></tr></thead>
    <tbody>${summaryBody}</tbody></table>
    <h3 class="sub">Tag channels over time</h3>
    ${htmlTagOverview(samples, { timeOf: s => s.time })}</section>`
}

function _renderDeadlineReportHtml(suffix) {
  if (!hasDeadlineConfig.value) return ''
  const { sliceViolations, cpuViolations } = deadlineViolations.value
  const svBody = sliceViolations.length
    ? sliceViolations.map(v =>
        `<tr><td>${_htmlCell(v.label)}</td><td>${_htmlCell(v.duration)}</td><td>${_htmlCell(v.limit)}</td>` +
        `<td style="color:#c0392b;font-weight:600">${_htmlCell(v.overBy)}</td></tr>`,
      ).join('')
    : '<tr><td colspan="4" class="empty">No slice violations</td></tr>'
  const cvBody = cpuViolations.length
    ? cpuViolations.map(v =>
        `<tr><td>${_htmlCell(v.label)}</td><td style="color:#c0392b;font-weight:600">${_htmlCell(v.pct)}%</td>` +
        `<td>${_htmlCell(v.budgetPct)}%</td></tr>`,
      ).join('')
    : '<tr><td colspan="3" class="empty">No CPU budget violations</td></tr>'
  return `<section class="report-card"><h2>Deadlines / CPU budget${_htmlCell(suffix)}</h2>
    <h3 class="sub">Slice over deadline</h3>
    <table><thead><tr><th>Task</th><th>Duration</th><th>Limit</th><th>Over by</th></tr></thead>
    <tbody>${svBody}</tbody></table>
    <h3 class="sub">CPU budget exceeded</h3>
    <table><thead><tr><th>Task</th><th>CPU %</th><th>Budget</th></tr></thead>
    <tbody>${cvBody}</tbody></table></section>`
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
  const { rows: preemptHtmlRows } = preemptionChainRows(tr, lo, hi)
  const schedKpi = schedulingSummary.value
  const coreHtml = (() => {
    const section = _htmlUtilSection(
      `Core Utilisation (excl. IDLE/TICK)${suffix}`,
      coreRows.map(r => ({ label: r.core, pct: r.pct })),
      'core',
    )
    const lb = loadBalanceScore.value
    if (!lb) return section
    const gauge = loadBalanceGaugeImgHtml(lb, { width: 300 })
    return section.replace('</h2>', `</h2>${gauge}`)
  })()
  const taskHtml = _htmlUtilSection(
    `Top Tasks by CPU (excl. IDLE/TICK)${suffix}`,
    taskRows.map(r => ({ label: r.name, pct: r.pct })),
    'task',
  )
  const tick = tickHealthReport(tr, lo, hi)
  const tickGapBody = tick.largeGaps.length
    ? tick.largeGaps.map(g => `<tr><td>${_htmlCell(formatTime(g.start, tr.timeScale))}</td><td>${_htmlCell(formatTime(g.end, tr.timeScale))}</td><td>${_htmlCell(formatTime(g.duration, tr.timeScale))}</td><td>${g.missedTicks}</td></tr>`).join('')
    : '<tr><td colspan="4" class="empty">No large gaps</td></tr>'
  const tickHealthHtml = tick.tickCount
    ? `<section class="report-card"><h2>Trace Health (TICK)${_htmlCell(suffix)}</h2><table><tbody>
        <tr><th>Status</th><td>${_htmlCell(tick.health.toUpperCase())}</td></tr>
        <tr><th>Mode</th><td>${tick.isTickless ? 'TICKLESS' : 'TICK'}</td></tr>
        <tr><th>Interval CV</th><td>${(tick.tickCv * 100).toFixed(2)}%</td></tr>
        <tr><th>Ticks</th><td>${tick.tickCount.toLocaleString('en-US')}</td></tr>
        <tr><th>Avg period</th><td>${_htmlCell(formatTime(tick.avgPeriod, tr.timeScale))}</td></tr>
        <tr><th>Max gap</th><td>${_htmlCell(formatTime(tick.maxGap, tr.timeScale))}</td></tr>
        <tr><th>Missed ticks (est.)</th><td>${tick.missedTicksEstimate}</td></tr>
      </tbody></table>
      <h2 style="margin-top:12px;font-size:14px;">Large TICK gaps</h2>
      <table><thead><tr><th>Start</th><th>End</th><th>Gap</th><th>Missed</th></tr></thead><tbody>${tickGapBody}</tbody></table></section>`
    : `<section class="report-card"><h2>Trace Health (TICK)${_htmlCell(suffix)}</h2><p class="empty">No STI TICK events</p></section>`
  const migHtml = `<section class="report-card"><h2>Core Migrations${_htmlCell(suffix)}</h2><table><thead><tr><th>Task</th><th>Migr</th><th>Rate</th><th>Dwell</th><th>Cores</th><th>Primary</th><th>Ping</th><th>STI±</th><th>Gap after</th><th>Gap other</th></tr></thead><tbody>${migReportRows.length
    ? migReportRows.map(r => `<tr><td>${_htmlCell(r.name)}</td><td>${_htmlCell(r.migrations)}</td><td>${_htmlCell(r.migrRate)}</td><td>${_htmlCell(r.avgDwell)}</td><td>${_htmlCell(r.coreCount)}</td><td>${_htmlCell(`${r.primary} (${r.primaryPct.toFixed(0)}%)`)}</td><td>${_htmlCell(r.pingPong)}</td><td>${_htmlCell(r.stiNear)}</td><td>${_htmlCell(r.gapAfter)}</td><td>${_htmlCell(r.gapOther)}</td></tr>`).join('')
    : '<tr><td colspan="10" class="empty">No migrated tasks</td></tr>'
  }</tbody></table></section>`

  const findings = analysisFindings.value || []
  const analysisHtml = renderWorkflowAnalysisHtml(findings, suffix)
  const warnN = findings.filter(f => f.severity === 'warning').length
  const errN = findings.filter(f => f.severity === 'error').length
  const statusKind = errN ? 'error' : (warnN ? 'warn' : 'ok')
  const statusValue = (errN || warnN)
    ? `${errN} error(s), ${warnN} warning(s)`
    : 'No heuristic warnings'
  const pcts = coreRows.map(row => Number(row.pct) || 0)
  const utilLo = pcts.length ? Math.min(...pcts) : 0
  const utilHi = pcts.length ? Math.max(...pcts) : 0
  const lbKpi = loadBalanceScore.value
  const worstRt = [...(responseRows.value || [])].sort((a, b) => (b.p99_ns || 0) - (a.p99_ns || 0))[0]
  const migTotal = migReportRows.reduce((s, row) => s + (Number(row.migrations) || 0), 0)
  const tickLabel = tick.tickCount ? String(tick.health || 'n/a').toUpperCase() : 'No TICK'
  const tickHealthKind = tick.tickCount
    ? (String(tick.health || '').toLowerCase() === 'bad' ? 'error'
      : (tick.health && String(tick.health).toLowerCase() !== 'good' ? 'warn' : 'ok'))
    : 'ok'
  const dlN = hasDeadlineConfig.value
    ? ((deadlineViolations.value.sliceViolations || []).length
      + (deadlineViolations.value.cpuViolations || []).length)
    : 0
  const syncN = (syncIssueList.value || []).length
  const kpis = [
    { label: 'Overall status', value: statusValue, kind: statusKind },
    {
      label: 'Load balance',
      value: lbKpi ? `${lbKpi.score.toFixed(0)}%` : '—',
      hint: lbKpi ? (lbKpi.score >= 85 ? 'Balanced' : 'Uneven') : 'Need 2+ cores',
      kind: lbKpi && (lbKpi.score < 70 || lbKpi.stddev > 30) ? 'warn' : 'ok',
    },
    {
      label: 'Core utilisation range',
      value: `${utilLo.toFixed(1)}–${utilHi.toFixed(1)}%`,
      hint: 'Wall-clock span, one-core = 100%',
    },
    {
      label: 'Worst response P99',
      value: worstRt ? formatTime(worstRt.p99_ns, tr.timeScale) : '—',
      hint: worstRt?.task || '',
    },
    { label: 'Migration activity', value: migTotal.toLocaleString('en-US'), hint: 'Total core hops in scope' },
    { label: 'Tick health', value: tickLabel, kind: tickHealthKind },
    { label: 'Synchronization issues', value: syncN.toLocaleString('en-US'), kind: syncN ? 'warn' : 'ok' },
    { label: 'Deadline misses', value: dlN.toLocaleString('en-US'), kind: dlN ? 'error' : 'ok' },
  ]
  const startS = formatTime(lo ?? tr.timeMin, tr.timeScale)
  const endS = formatTime(hi ?? tr.timeMax, tr.timeScale)
  const sampleNote = execReportRows.length && execReportRows.every(row => row.runs < 8)
    ? 'Few execution samples in this scope; percentiles and comparisons may be unreliable.'
    : ''
  const tab = (props.tabs || []).find(t => t.trace === tr)
  const scopeHtml = htmlScopeIdentityCard({
    filename: tab?.name || 'trace',
    scopeType: r ? `Cursor range C1–C${r.nCursors}` : 'Full trace',
    start: startS,
    end: endS,
    duration: spanStr.value,
    cores: (tr.coreNames || []).length,
    filters: r ? 'Limit to C1–Cn' : 'None',
    timestampMode: 'Trace capture origin (not wall-clock)',
    taskCount: summaryTaskCount.value,
    sampleNote,
  })
  const metaHtml = htmlTraceMetadataCard({
    span: spanStr.value,
    tasks: summaryTaskCount.value,
    segments: summarySegCount.value,
    stiEvents: summaryStiCount.value,
    contextSwitches: schedKpi?.contextSwitches || 0,
    coreGapAvg: schedKpi?.gapAvg || '',
    coreGapMax: schedKpi?.gapMax || '',
    scopeTitle: suffix,
  })
  const glossaryHtml = htmlGlossary({
    rangeNote: r
      ? `<strong>Cursor range:</strong> ${_htmlCell(scopeRangeLabel.value)}. CPU% uses overlapping active time; slice metrics use segments fully inside the range.`
      : '',
  })


  const now = new Date()
  const pad = n => String(n).padStart(2, '0')
  const stamp = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`
  const statsExtraCss = `${STATS_HTML_EXTRA_CSS}\n${_HTML_EXPORT_UTIL_CSS}`.trim()

  const body = `
    ${htmlDiagnosticKpiGrid(kpis)}
    <!--TOC-->
    ${scopeHtml}
    ${analysisHtml}
    ${metaHtml}
    ${coreHtml}
    ${tickHealthHtml}
    ${(() => {
      const bdRows = buildCoreTimeBreakdown(tr, lo, hi)
      const bdBody = bdRows.length
        ? bdRows.map(r => {
            const s = Math.max(r.spanNs, 1)
            return `<tr><td>${_htmlCell(r.core)}</td>` +
              `<td>${(100 * r.activeNs / s).toFixed(1)}%</td>` +
              `<td>${(100 * r.idleNs / s).toFixed(1)}%</td>` +
              `<td>${(100 * r.tickNs / s).toFixed(1)}%</td>` +
              `<td>${(100 * r.gapNs / s).toFixed(1)}%</td></tr>`
          }).join('')
        : '<tr><td colspan="5" class="empty">No core data</td></tr>'
      return `<section class="report-card"><h2>Core Time Breakdown${_htmlCell(suffix)}</h2>` +
        '<table><thead><tr><th>Core</th><th>Active %</th><th>Idle %</th>' +
        '<th>Tick %</th><th>Gap %</th></tr></thead>' +
        `<tbody>${bdBody}</tbody></table></section>`
    })()}
    ${(() => {
      const ccRows = concurrentCoreActiveRows(tr, lo, hi)
      const body = ccRows.length
        ? ccRows.map(r =>
            `<tr><td>${r.activeCores}</td><td>${_htmlCell(r.duration)}</td>` +
            `<td>${r.pctOfSpan.toFixed(1)}%</td></tr>`
          ).join('')
        : '<tr><td colspan="3" class="empty">No data</td></tr>'
      return `<section class="report-card"><h2>Concurrent Core Active Distribution${_htmlCell(suffix)}</h2>` +
        '<table><thead><tr><th>Active Cores</th><th>Duration</th><th>% of Span</th></tr></thead>' +
        `<tbody>${body}</tbody></table></section>`
    })()}
    ${(() => {
      const swRows = switchOverheadRows(tr, lo, hi)
      const body = swRows.length
        ? swRows.map(r =>
            `<tr><td>${_htmlCell(r.core)}</td><td>${r.switches}</td>` +
            `<td>${_htmlCell(r.min)}</td><td>${_htmlCell(r.avg)}</td><td>${_htmlCell(r.max)}</td>` +
            `<td>${_htmlCell(r.total)}</td><td>${r.pctOfCore.toFixed(2)}%</td></tr>`
          ).join('')
        : '<tr><td colspan="7" class="empty">No data</td></tr>'
      return `<section class="report-card"><h2>Kernel Switch Overhead${_htmlCell(suffix)}</h2>` +
        '<table><thead><tr><th>Core</th><th>Switches</th><th>Min</th><th>Avg</th>' +
        '<th>Max</th><th>Total Overhead</th><th>% of Core</th></tr></thead>' +
        `<tbody>${body}</tbody></table></section>`
    })()}
    ${taskHtml}
    ${migHtml}
    ${(() => {
      const pairRows = buildCorePairRows(tr, lo, hi)
      const pairBody = pairRows.length
        ? pairRows.map(r =>
            `<tr><td>${_htmlCell(r.fromCore)}</td><td>${_htmlCell(r.toCore)}</td>` +
            `<td>${r.count}</td><td>${r.bounces}</td><td>${r.bouncePct.toFixed(1)}%</td>` +
            `<td>${_htmlCell(formatMigrationGapTime(r.avgGapNs, tr.timeScale))}</td></tr>`
          ).join('')
        : '<tr><td colspan="6" class="empty">No migrations in scope</td></tr>'
      const pairCores = []
      for (const row of pairRows) {
        if (!pairCores.includes(row.fromCore)) pairCores.push(row.fromCore)
        if (!pairCores.includes(row.toCore)) pairCores.push(row.toCore)
      }
      const pairIdx = Object.fromEntries(pairCores.map((c, i) => [c, i]))
      const pairCells = pairCores.map(() => pairCores.map(() => 0))
      for (const row of pairRows) {
        if (row.fromCore in pairIdx && row.toCore in pairIdx) {
          pairCells[pairIdx[row.fromCore]][pairIdx[row.toCore]] = Number(row.count) || 0
        }
      }
      const pairHeat = pairCores.length
        ? htmlMatrixHeatmap(pairCores, pairCores, pairCells, {
          title: 'Core migration count (source → destination)',
          unit: '',
        })
        : ''
      return `<section class="report-card"><h2>Core-Pair Migration Summary${_htmlCell(suffix)}</h2>` +
        pairHeat +
        '<table><thead><tr><th>From</th><th>To</th><th>Count</th>' +
        '<th>Bounces</th><th>Bounce %</th><th>Avg Gap</th></tr></thead>' +
        `<tbody>${pairBody}</tbody></table></section>`
    })()}
    ${(() => {
      const affRows = coreAffinityRows.value
      const affBody = affRows.length
        ? affRows.map(r => {
            const violStyle = r.violations !== '—' ? ' style="color:#c0392b;font-weight:600"' : ''
            return `<tr><td>${_htmlCell(r.label)}</td><td>${_htmlCell(r.maskHex)}</td>` +
              `<td>${_htmlCell(r.observedCores)}</td><td${violStyle}>${_htmlCell(r.violations)}</td></tr>`
          }).join('')
        : '<tr><td colspan="4" class="empty">No affinity_set events</td></tr>'
      return `<section class="report-card"><h2>Core Affinity${_htmlCell(suffix)}</h2>` +
        '<table><thead><tr><th>Task</th><th>Mask</th><th>Observed Cores</th>' +
        '<th>Violations</th></tr></thead>' +
        `<tbody>${affBody}</tbody></table></section>`
    })()}
    ${(() => {
      const matrix = taskCoreModel.value
      const cores = matrix.cores || []
      const head = '<tr><th>Task</th>' + cores.map(c => `<th>${_htmlCell(c)}</th>`).join('') + '</tr>'
      const body = (matrix.rows || []).length
        ? matrix.rows.map(row =>
            `<tr><td>${_htmlCell(row.task)}</td>` +
            cores.map(c => {
              const cell = row.cells?.[c]
              return `<td>${cell?.ns ? cell.pct_span.toFixed(1) + '%' : '—'}</td>`
            }).join('') + '</tr>'
          ).join('')
        : `<tr><td colspan="${cores.length + 1}" class="empty">No on-CPU slices</td></tr>`
      const heat = htmlMatrixHeatmap(
        (matrix.rows || []).slice(0, 24).map(row => row.task || ''),
        cores,
        (matrix.rows || []).slice(0, 24).map(row => cores.map(c => Number(row.cells?.[c]?.pct_span) || 0)),
        { title: 'Task × Core utilisation (% of span)', unit: '%' },
      )
      return `<section class="report-card"><h2>Task × Core${_htmlCell(suffix)}</h2>` +
        heat +
        `<table><thead>${head}</thead><tbody>${body}</tbody></table></section>`
    })()}
    ${(() => {
      const grid = coreTimeModel.value
      const cores = grid.cores || []
      const head = '<tr><th>Time</th>' + cores.map(c => `<th>${_htmlCell(c)}</th>`).join('') + '</tr>'
      const body = (grid.bins || []).length
        ? grid.bins.map(row =>
            `<tr><td>${_htmlCell(formatTime(row.start, tr.timeScale))}</td>` +
            cores.map(c => {
              const cell = row.cells?.[c]
              return `<td>${cell ? cell.pct.toFixed(1) + '%' : '—'}</td>`
            }).join('') + '</tr>'
          ).join('')
        : `<tr><td colspan="${cores.length + 1}" class="empty">No on-CPU slices</td></tr>`
      const heat = htmlMatrixHeatmap(
        (grid.bins || []).map(row => formatTime(row.start, tr.timeScale)),
        cores,
        (grid.bins || []).map(row => cores.map(c => Number(row.cells?.[c]?.pct) || 0)),
        { title: 'Core utilisation over time', unit: '%' },
      )
      return `<section class="report-card"><h2>Core Utilization Over Time${_htmlCell(suffix)}</h2>` +
        heat +
        `<table><thead>${head}</thead><tbody>${body}</tbody></table></section>`
    })()}
    ${(() => {
      const lcRows = buildTaskLifecycleRows(tr.stiEvents ?? [], tr.taskRepr, lo, hi, tr.taskCreateTimes, tr.segByMergeKey)
      const lcBody = lcRows.length
        ? lcRows.map(r =>
            `<tr><td>${_htmlCell(r.label)}</td>` +
            `<td>${r.createNs != null ? _htmlCell(formatTime(r.createNs, tr.timeScale)) : '—'}</td>` +
            `<td>${r.deleteNs != null ? _htmlCell(formatTime(r.deleteNs, tr.timeScale)) : '—'}</td>` +
            `<td>${r.suspendCount}/${r.resumeCount}</td>` +
            `<td>${r.aliveSpanNs ? _htmlCell(formatLifecycleSpan(r.aliveSpanNs, tr.timeScale)) : '—'}</td>` +
            `<td>${r.eventCount}</td><td>${r.runCount}</td></tr>`
          ).join('')
        : '<tr><td colspan="7" class="empty">No lifecycle events</td></tr>'
      return `<section class="report-card"><h2>Task Lifecycle${_htmlCell(suffix)}</h2>` +
        '<table><thead><tr><th>Task</th><th>Created</th><th>Deleted</th>' +
        '<th>Susp/Res</th><th>Alive span</th><th>Events</th><th>Runs</th></tr></thead>' +
        `<tbody>${lcBody}</tbody></table></section>`
    })()}
    ${_renderDeadlineReportHtml(suffix)}
    ${(() => {
      const rows = taskHealthRows.value
      const body = rows.length
        ? rows.map(r =>
            `<tr><td>${_htmlCell(r.task)}</td><td>${r.score}</td>` +
            ['execution', 'blocking', 'period', 'migration', 'deadline', 'cpu']
              .map(k => `<td>${_htmlCell(r.marks[k] || '')}</td>`).join('') +
            '</tr>'
          ).join('')
        : '<tr><td colspan="8" class="empty">No task slices</td></tr>'
      return `<section class="report-card"><h2>Task Health${_htmlCell(suffix)}</h2>` +
        '<p class="detail-note">Heuristic score from measured statistics, not an AI probability.</p>' +
        htmlHealthBars(rows) +
        '<table><thead><tr><th>Task</th><th>Score</th><th>Exec</th><th>Block</th>' +
        '<th>Period</th><th>Mig</th><th>Deadline</th><th>CPU</th></tr></thead>' +
        `<tbody>${body}</tbody></table></section>`
    })()}
    ${(() => {
      const anBody = anomalyRows.value.length
        ? anomalyRows.value.map(r =>
            `<tr><td>${_htmlCell(formatTime(r.start, tr.timeScale))}</td>` +
            `<td>${_htmlCell(uxKindLabel(r.kind))}</td>` +
            `<td>${_htmlCell(r.task)}</td>` +
            `<td>${_htmlCell(formatTime(r.duration, tr.timeScale))}</td>` +
            `<td>${_htmlCell(r.reason || '')}</td></tr>`
          ).join('')
        : '<tr><td colspan="5" class="empty">No timeline anomalies in this scope</td></tr>'
      const woBody = worstRows.value.length
        ? worstRows.value.map(r =>
            `<tr><td>${_htmlCell(formatTime(r.start, tr.timeScale))}</td>` +
            `<td>${_htmlCell(uxKindLabel(r.kind))}</td>` +
            `<td>${_htmlCell(r.task)}</td>` +
            `<td>${_htmlCell(formatTime(r.duration, tr.timeScale))}</td>` +
            `<td>${_htmlCell(r.reason || uxKindLabel(r.kind))}</td></tr>`
          ).join('')
        : '<tr><td colspan="5" class="empty">No episodes in this scope</td></tr>'
      const patBody = patternRows.value.length
        ? patternRows.value.map(r =>
            `<tr><td>${_htmlCell(r.task)}</td><td>${_htmlCell(uxKindLabel(r.kind))}</td>` +
            `<td>${r.count}</td><td>${_htmlCell(formatTime(r.duration, tr.timeScale))}</td>` +
            `<td>${_htmlCell(r.reason || '')}</td></tr>`
          ).join('')
        : '<tr><td colspan="5" class="empty">No repeating anomaly kinds in this scope</td></tr>'
      const cpBody = critPathRows.value.length
        ? critPathRows.value.map(r =>
            `<tr><td>${_htmlCell(r.task)}</td>` +
            `<td>${_htmlCell(formatTime(r.duration, tr.timeScale))}</td>` +
            `<td>${_htmlCell(formatTime(r.exec_ns, tr.timeScale))}</td>` +
            `<td>${_htmlCell(formatTime(Math.max(0, (r.duration || 0) - (r.exec_ns || 0)), tr.timeScale))}</td>` +
            `<td>${_htmlCell(formatTime(r.preempt_ns, tr.timeScale))}</td>` +
            `<td>${_htmlCell(formatTime(r.wait_ns, tr.timeScale))}</td>` +
            `<td>${_htmlCell(formatTime(r.migration_ns, tr.timeScale))}</td></tr>`
          ).join('')
        : '<tr><td colspan="7" class="empty">Need at least one on-CPU slice</td></tr>'
      return htmlInvestigateAnomalies({
        anomaliesTable: '<table><thead><tr><th>Time</th><th>Kind</th><th>Task</th><th>Duration</th><th>Why</th></tr></thead>'
          + `<tbody>${anBody}</tbody></table>`,
        worstTable: '<table><thead><tr><th>Time</th><th>Kind</th><th>Task</th><th>Duration</th><th>Why</th></tr></thead>'
          + `<tbody>${woBody}</tbody></table>`,
        patternsTable: '<table><thead><tr><th>Task</th><th>Kind</th><th>Count</th><th>Worst</th><th>Why</th></tr></thead>'
          + `<tbody>${patBody}</tbody></table>`,
        critPathTable: '<table><thead><tr><th>Task</th><th>Duration</th><th>Exec</th>'
          + '<th>Off-CPU</th><th>Preempt (overlap)</th><th>Wait (overlap)</th>'
          + '<th>Mig (overlap)</th></tr></thead>'
          + `<tbody>${cpBody}</tbody></table>`,
        critNote: '<p class="detail-note">Duration is the heuristic ready-to-completion window. '
          + 'Exec is own on-CPU time; Off-CPU is Duration − Exec. '
          + 'Preempt, Wait, and Migration overlap (Wait includes preemption gaps) '
          + 'and must not be stacked as a split of Duration.</p>',
        scopeTitle: suffix,
      })
    })()}
    ${_renderHtmlTableReport(`Execution Time Per Slice${suffix}`, execReportRows, true)}
    ${_renderHtmlTableReport(`Off-CPU Time (Blocking Time)${suffix}`, blockReportRows)}
    ${(() => {
      const dispRows = dispatchLatencyRows(tr, lo, hi)
      const body = dispRows.length
        ? dispRows.map(r =>
            `<tr><td>${_htmlCell(r.label)}</td><td>${r.activations}</td>` +
            `<td>${_htmlCell(r.min)}</td><td>${_htmlCell(r.avg)}</td><td>${_htmlCell(r.max)}</td>` +
            `<td>${_htmlCell(r.jitter)}</td><td>${_htmlCell(r.stddev)}</td>` +
            `<td>${_htmlCell(r.p95)}</td><td>${_htmlCell(r.p99)}</td></tr>`
          ).join('')
        : '<tr><td colspan="9" class="empty">No dispatch samples (needs STI resume Name[id] or create→first-run)</td></tr>'
      return `<section class="report-card"><h2>Dispatch / Scheduling Latency${_htmlCell(suffix)}</h2>` +
        '<p class="detail-note">Ready from STI resume / create; sync wakes not attributed.</p>' +
        '<table><thead><tr><th>Task</th><th>Activations</th><th>Min</th><th>Avg</th>' +
        '<th>Max</th><th>Jitter</th><th>σ</th><th>p95</th><th>p99</th></tr></thead>' +
        `<tbody>${body}</tbody></table></section>`
    })()}
    ${_renderHtmlTableReport(`Inter-Arrival Time${suffix}`, interReportRows)}
    ${(() => {
      const rows = periodRows.value
      const body = rows.length
        ? rows.map(r =>
            `<tr><td>${_htmlCell(r.task)}</td><td>${r.n}</td>` +
            `<td>${_htmlCell(formatTime(r.expected_ns, tr.timeScale))}</td>` +
            `<td>${_htmlCell(formatTime(r.min_ns, tr.timeScale))}</td>` +
            `<td>${_htmlCell(formatTime(r.avg_ns, tr.timeScale))}</td>` +
            `<td>${_htmlCell(formatTime(r.max_ns, tr.timeScale))}</td>` +
            `<td>${_htmlCell(formatTime(r.p95_ns, tr.timeScale))}</td>` +
            `<td>${_htmlCell(formatTime(r.p99_ns, tr.timeScale))}</td>` +
            `<td>${_htmlCell(formatTime(r.rms_ns, tr.timeScale))}</td>` +
            `<td>${(r.cv * 100).toFixed(1)}%</td><td>${r.missed}</td><td>${r.extra}</td>` +
            `<td>${r.burst || 0}</td><td>${_htmlCell(r.spark || '')}</td></tr>`
          ).join('')
        : '<tr><td colspan="14" class="empty">Need at least 3 inter-arrival gaps per task</td></tr>'
      return `<section class="report-card"><h2>Period / Jitter${_htmlCell(suffix)}</h2>` +
        '<table><thead><tr><th>Task</th><th>N</th><th>Expected</th><th>Min</th><th>Avg</th>' +
        '<th>Max</th><th>p95</th><th>p99</th><th>RMS</th><th>CV</th><th>Missed</th>' +
        '<th>Extra</th><th>Burst</th><th>Spark</th></tr></thead>' +
        `<tbody>${body}</tbody></table></section>`
    })()}
    ${(() => {
      const rows = responseRows.value
      const body = rows.length
        ? rows.map(r =>
            `<tr><td>${_htmlCell(r.task)}</td><td>${r.n}</td>` +
            `<td>${_htmlCell(formatTime(r.min_ns, tr.timeScale))}</td>` +
            `<td>${_htmlCell(formatTime(r.avg_ns, tr.timeScale))}</td>` +
            `<td>${_htmlCell(formatTime(r.max_ns, tr.timeScale))}</td>` +
            `<td>${_htmlCell(formatTime(r.p50_ns, tr.timeScale))}</td>` +
            `<td>${_htmlCell(formatTime(r.p90_ns, tr.timeScale))}</td>` +
            `<td>${_htmlCell(formatTime(r.p95_ns, tr.timeScale))}</td>` +
            `<td>${_htmlCell(formatTime(r.p99_ns, tr.timeScale))}</td>` +
            `<td>${_htmlCell(formatTime(r.p999_ns, tr.timeScale))}</td>` +
            `<td>${_htmlCell(formatTime(r.jitter_ns, tr.timeScale))}</td>` +
            `<td>${((r.cv || 0) * 100).toFixed(1)}%</td></tr>`
          ).join('')
        : '<tr><td colspan="12" class="empty">Need at least one on-CPU slice</td></tr>'
      return `<section class="report-card"><h2>Response Time${_htmlCell(suffix)}</h2>` +
        '<p class="detail-note">Heuristic ready→completion from adjacent slices, not an explicit BTF release/completion pair.</p>' +
        htmlPercentileBars(rows, { title: 'Response P50–P99' }) +
        '<table><thead><tr><th>Task</th><th>N</th><th>Min</th><th>Avg</th><th>Max</th>' +
        '<th>p50</th><th>p90</th><th>p95</th><th>p99</th><th>p99.9</th><th>Jitter</th><th>CV</th></tr></thead>' +
        `<tbody>${body}</tbody></table></section>`
    })()}
    ${(() => {
      const rows = jitterRows.value
      const body = rows.length
        ? rows.map(r =>
            `<tr><td>${_htmlCell(r.task)}</td>` +
            `<td>${_htmlCell(formatTime(r.exec_jitter_ns, tr.timeScale))}</td>` +
            `<td>${((r.exec_cv || 0) * 100).toFixed(1)}%</td>` +
            `<td>${_htmlCell(formatTime(r.block_jitter_ns, tr.timeScale))}</td>` +
            `<td>${((r.block_cv || 0) * 100).toFixed(1)}%</td>` +
            `<td>${_htmlCell(formatTime(r.inter_jitter_ns, tr.timeScale))}</td>` +
            `<td>${((r.inter_cv || 0) * 100).toFixed(1)}%</td>` +
            `<td>${_htmlCell(formatTime(r.response_jitter_ns, tr.timeScale))}</td>` +
            `<td>${((r.response_cv || 0) * 100).toFixed(1)}%</td>` +
            `<td>${_htmlCell(formatTime(r.dispatch_jitter_ns, tr.timeScale))}</td>` +
            `<td>${((r.dispatch_cv || 0) * 100).toFixed(1)}%</td>` +
            `<td>${_htmlCell(formatTime(r.wakeup_jitter_ns, tr.timeScale))}</td>` +
            `<td>${((r.wakeup_cv || 0) * 100).toFixed(1)}%</td></tr>`
          ).join('')
        : '<tr><td colspan="13" class="empty">No timing samples in this scope</td></tr>'
      return `<section class="report-card"><h2>Unified Jitter${_htmlCell(suffix)}</h2>` +
        '<table><thead><tr><th>Task</th><th>Exec</th><th>Exec CV</th><th>Block</th>' +
        '<th>Block CV</th><th>Inter</th><th>Inter CV</th><th>Response</th>' +
        '<th>Resp CV</th><th>Dispatch</th><th>Disp CV</th><th>Wake</th>' +
        '<th>Wake CV</th></tr></thead>' +
        `<tbody>${body}</tbody></table></section>`
    })()}
    <section class="report-card"><h2>Preemption Chain Analysis${_htmlCell(suffix)}</h2>
    <table><thead><tr><th>Victim</th><th>Preemptor</th><th>Count</th><th>Total</th><th>Avg</th><th>Max</th></tr></thead>
    <tbody>${preemptHtmlRows.length
      ? preemptHtmlRows.map(row =>
          `<tr><td>${_htmlCell(row.victim)}</td><td>${_htmlCell(row.preemptor)}</td><td>${row.count}</td><td>${_htmlCell(row.total)}</td><td>${_htmlCell(row.avg)}</td><td>${_htmlCell(row.max)}</td></tr>`
        ).join('')
      : '<tr><td colspan="6" class="empty">No preemption events found</td></tr>'
    }</tbody></table></section>
    ${(() => {
      const rows = preemptRankRows.value
      const body = rows.length
        ? rows.map(r =>
            `<tr><td>${_htmlCell(r.task)}</td><td>${r.count}</td>` +
            `<td>${_htmlCell(formatTime(r.total_ns, tr.timeScale))}</td>` +
            `<td>${_htmlCell(formatTime(r.max_ns, tr.timeScale))}</td>` +
            `<td>${_htmlCell(r.top_label || '')}</td></tr>`
          ).join('')
        : '<tr><td colspan="5" class="empty">No preemption overlaps in this scope</td></tr>'
      return `<section class="report-card"><h2>Preemption Matrix${_htmlCell(suffix)}</h2>` +
        '<table><thead><tr><th>Victim</th><th>Count</th><th>Total</th>' +
        '<th>Max</th><th>Top preemptors</th></tr></thead>' +
        `<tbody>${body}</tbody></table></section>`
    })()}
    ${tr?.hasPriorityInstrumentation ? _renderPriorityReportHtml(tr, lo, hi, suffix) : ''}
    ${tr?.hasSyncObjectInstrumentation ? _renderSyncObjectReportHtml(tr, lo, hi, suffix) : ''}
    ${(() => {
      const matrix = waitOwnerModel.value
      const tasks = matrix.tasks || []
      if (!tasks.length) {
        return `<section class="report-card"><h2>Waiter × Owner${_htmlCell(suffix)}</h2>` +
          '<p class="empty">No mutex handoffs in this scope</p></section>'
      }
      const head = '<tr><th>Waiter \\ Owner</th>' + tasks.map(t => `<th>${_htmlCell(t.task)}</th>`).join('') + '</tr>'
      const body = tasks.map(w =>
        `<tr><td>${_htmlCell(w.task)}</td>` +
        tasks.map(o => {
          if (w.mk === o.mk) return '<td>—</td>'
          const cell = matrix.cells[`${w.mk}|${o.mk}`]
          return `<td>${cell?.ns ? _htmlCell(formatTime(cell.ns, tr.timeScale)) : '—'}</td>`
        }).join('') + '</tr>'
      ).join('')
      return `<section class="report-card"><h2>Waiter × Owner${_htmlCell(suffix)}</h2>` +
        '<p class="detail-note">Heuristic mutex handoff matrix, not a kernel wait queue.</p>' +
        `<table><thead>${head}</thead><tbody>${body}</tbody></table></section>`
    })()}
    ${(() => {
      const rows = mutexBlockRows.value
      const body = rows.length
        ? rows.map(r =>
            `<tr><td>${_htmlCell(r.task)}</td><td>${_htmlCell(r.object)}</td>` +
            `<td>${_htmlCell(r.owner)}</td><td>${r.count}</td>` +
            `<td>${_htmlCell(formatTime(r.total_ns, tr.timeScale))}</td>` +
            `<td>${_htmlCell(formatTime(r.max_ns, tr.timeScale))}</td></tr>`
          ).join('')
        : '<tr><td colspan="6" class="empty">No mutex waits in this scope</td></tr>'
      return `<section class="report-card"><h2>Mutex Blocking${_htmlCell(suffix)}</h2>` +
        '<table><thead><tr><th>Task</th><th>Object</th><th>Owner</th>' +
        '<th>Count</th><th>Total</th><th>Max</th></tr></thead>' +
        `<tbody>${body}</tbody></table></section>`
    })()}
    ${tr?.hasSyncObjectInstrumentation ? (() => {
      const qRows = syncObjectStatsRows(tr, lo, hi, { kindFilter: 'queue' })
      if (!qRows.length) return ''
      const qBody = qRows.map(r =>
        `<tr><td>${_htmlCell(r.label)}</td><td>${_htmlCell(r.kind)}</td>` +
        `<td>${r.holdCount}</td><td>${r.issueCount}</td>` +
        `<td class="${r.bounceCount > 0 ? 'sev-warning' : ''}">${r.bounceCount ?? 0}</td>` +
        `<td>${_htmlCell(r.avgHold)}</td>` +
        `<td class="${r.status !== 'ok' ? (r.status === 'error' ? 'sev-error' : 'sev-warning') : ''}">${_htmlCell(r.statusLabel)}</td></tr>`
      ).join('')
      return `<section class="report-card"><h2>Queue${_htmlCell(suffix)}</h2>` +
        '<table><thead><tr><th>Object</th><th>Kind</th><th>Holds</th>' +
        '<th>Issues</th><th>Bounces</th><th>Avg hold</th><th>Status</th></tr></thead>' +
        `<tbody>${qBody}</tbody></table></section>`
    })() : ''}
    ${_renderIntervalReportHtml(tr, lo, hi, suffix)}
    ${_renderTagReportHtml(tr, lo, hi, suffix)}
    ${glossaryHtml}
    ${HTML_REPORT_TOC_SCRIPT}
    ${HTML_REPORT_INTERACTIVE_SCRIPT}
`

  const html = btfHtmlReportDocument('Statistics Report', body, {
    subtitle: `Generated: ${stamp}`,
    extraCss: statsExtraCss,
    docTitle: 'BTFViewer — Statistics Report',
    reportClass: 'report-wide',
  })

  const finalHtml = htmlApplyCollapsibleToc(html, STATS_DEFAULT_EXPANDED, STATS_TOC_GROUPS)
  _downloadText(`statistics-${_stamp()}.html`, finalHtml, 'text/html;charset=utf-8')
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
  if (!scopeToCursorsModel.value) {
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
  scheduleStatsRefresh()
}, { immediate: true })

watch(
  [statsRange, execSliceCollapsed, blockingCollapsed, interArrivalCollapsed, scopeToCursorsModel, () => props.statsPaused],
  () => {
    if (props.statsPaused) return
    scheduleStatsRefresh()
  },
  { immediate: true },
)

watch(
  [() => props.trace, statsRange, preemptionCollapsed, () => props.statsPaused],
  () => schedulePreemptionRefresh(),
  { immediate: true },
)

watch(plotData, () => {
  selectedPlotPoint.value = -1
  plotHoverPointIndex.value = -1
  histogramScaleMode.value = 'auto'
})

defineExpose({
  applyDemoSections,
  scrollDemoSectionIntoView,
  expandAllSections,
  collapseAllSections,
  openTickDistPlot,
  closePlot,
})
</script>

<style scoped>
.stats-panel {
  display: flex;
  flex-direction: column;
  padding: 0;
  font-size: 11px;
  font-family: monospace;
  overflow: hidden;
  flex: 1;
  min-height: 0;
  gap: 0;
}

.stats-scope-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin: 0;
  padding: 8px 10px 6px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.stats-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 8px 10px;
}

.stats-scroll-tail {
  flex-shrink: 0;
  pointer-events: none;
  height: 0;
}

.stats-sections-stack {
  display: flex;
  flex-direction: column;
  min-width: 0;
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

.stats-icon-btn:disabled {
  opacity: 0.35;
  cursor: default;
  color: var(--fg-dim, #9e9e9e);
}

.stats-icon-btn:disabled:hover,
.stats-icon-btn:disabled:focus-visible {
  background: transparent;
  color: var(--fg-dim, #9e9e9e);
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

.stats-scope-filtered {
  display: inline-block;
  margin-left: 6px;
  padding: 0 6px;
  border-radius: 999px;
  border: 1px solid var(--accent);
  color: var(--fg);
  font-size: 10px;
  line-height: 1.5;
}

.stats-summary {
  display: flex;
  flex-direction: column;
  gap: 1px;
  color: var(--fg-dim);
  font-size: 10px;
  line-height: 1.25;
}

.summary-line {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.stats-sep {
  height: 1px;
  background: var(--border);
  margin: 6px 0;
  flex-shrink: 0;
}

.stats-summary .summary-sep {
  margin: 3px 0;
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
  white-space: normal;
  overflow-wrap: anywhere;
  word-break: break-word;
  min-width: 0;
}

.deadline-settings-hint {
  color: var(--fg-dim);
  font-size: 10px;
  font-style: italic;
  line-height: 1.4;
  margin: 0 0 4px;
}

.stats-settings-link {
  display: inline;
  margin: 0;
  padding: 0;
  border: none;
  background: none;
  color: #5B9BD5;
  font: inherit;
  font-style: italic;
  font-size: 10px;
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 2px;
}
.stats-settings-link:hover {
  color: #88AAFF;
}

.priority-hint {
  margin: 0 0 6px;
  line-height: 1.35;
}

.priority-hint code {
  font-size: 10px;
}

.priority-pattern {
  font-size: 10px;
  color: var(--fg-dim);
}

.priority-pattern.inversion {
  color: #e74c3c;
  font-weight: 600;
}

.priority-inversion-row .priority-pattern.inversion {
  color: #e74c3c;
}

.sync-status-ok { color: #5FCF6F; }
.sync-status-warning { color: #F39C12; font-weight: 600; }
.sync-status-error { color: #E74C3C; font-weight: 600; }

.health-ok { color: #3cb371; font-weight: 600; }
.health-warn { color: #e0a020; font-weight: 600; }
.health-fail { color: #e07070; font-weight: 600; }
.health-mark { text-align: center; cursor: pointer; }
.stats-table td.sev-error {
  color: #E85D5D;
}
.sync-issue-row td { color: #E8C84A; }
.sync-issues-wrap { margin-top: 6px; }
.sync-issues-table td.sync-status-error,
.sync-issues-table td.sync-status-warning { font-weight: 600; }

.health-banner-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  padding: 4px 0 2px;
}
.health-banner-row .health-banner {
  flex: 1 1 auto;
  min-width: 0;
  padding: 0;
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

.tick-mode-badge {
  display: inline-block;
  font-size: 10px;
  font-weight: 700;
  padding: 1px 4px;
  border-radius: 3px;
  cursor: help;
  letter-spacing: 0.03em;
}
.tick-mode-tick {
  background: color-mix(in srgb, #64B5F6 18%, transparent);
  color: #64B5F6;
  border: 1px solid color-mix(in srgb, #64B5F6 40%, transparent);
}
.tick-mode-tickless {
  background: color-mix(in srgb, #FFB74D 18%, transparent);
  color: #FFB74D;
  border: 1px solid color-mix(in srgb, #FFB74D 40%, transparent);
}
.tick-dist-hint {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
}
.tick-dist-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  background: var(--tick-dist-bg);
  border: 1px solid var(--tick-dist-border);
  border-radius: 4px;
  color: var(--tick-dist-fg);
  cursor: pointer;
  font-size: 11px;
  font-weight: 600;
  padding: 3px 8px;
  flex-shrink: 0;
}
.tick-dist-icon {
  color: var(--tick-dist-icon);
  flex-shrink: 0;
}
.tick-dist-btn:hover,
.tick-dist-btn:focus-visible {
  background: color-mix(in srgb, var(--tick-dist-icon) 22%, transparent);
  border-color: var(--tick-dist-icon);
  color: var(--tick-dist-fg);
  outline: none;
}
.tick-dist-btn:hover .tick-dist-icon,
.tick-dist-btn:focus-visible .tick-dist-icon {
  color: var(--tick-dist-icon);
}

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
  flex: 0 0 128px;
  width: 128px;
  min-width: 48px;
  max-width: 128px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.task-stat-name {
  color: var(--fg);
  flex: 0 0 128px;
  width: 128px;
  min-width: 48px;
  max-width: 128px;
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
  flex: 1 1 0;
  height: 8px;
  border-radius: 4px;
  background: var(--border);
  overflow: hidden;
  min-width: 24px;
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
  min-width: 40px;
  text-align: left;
  flex-shrink: 0;
}

.task-stat-pct {
  color: #6AAADD;
  min-width: 40px;
  text-align: left;
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

/* Row hover for every stats table (clickable and read-only). */
.stats-table tbody tr:hover td {
  background: var(--tb-btn-hover);
}

.stats-table-row.clickable,
.stats-table tbody tr.clickable-row {
  cursor: pointer;
}

.stats-table-row.clickable:focus-visible td,
.stats-table tbody tr.clickable-row:focus-visible td {
  background: var(--tb-btn-hover);
}

.stats-table-row.clickable:focus-visible,
.stats-table tbody tr.clickable-row:focus-visible {
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
  flex-direction: column;
  gap: 4px;
  padding: 6px 10px 8px;
  border-top: 1px solid var(--border);
  flex-shrink: 0;
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

.action-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.stats-tool-row {
  display: flex;
  flex-wrap: nowrap;
  align-items: center;
  gap: 6px;
  padding: 4px 0 8px;
}

.stats-tool-btn {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  padding: 3px 8px;
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 4px;
  color: var(--fg);
  font-size: 11px;
  white-space: nowrap;
  cursor: pointer;
}

.stats-tool-btn:hover:not(:disabled) {
  background: var(--tb-btn-hover);
  color: var(--fg);
}

.stats-tool-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.action-btn .export-icon {
  flex-shrink: 0;
  opacity: 0.9;
}

.action-btn:hover:not(:disabled) {
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

.plot-tab-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 14px 10px;
  border-bottom: 1px solid var(--border);
}

.plot-tab-btn {
  border: 1px solid var(--border);
  border-bottom: 2px solid var(--border);
  background: transparent;
  color: var(--fg);
  border-radius: 6px;
  padding: 4px 12px 3px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

.plot-tab-btn:hover:not(.active) {
  background: var(--tb-btn-hover);
}

.plot-tab-btn.active {
  background: var(--accent, #1976d2);
  border-color: var(--accent, #1976d2);
  border-bottom-color: #0d47a1;
  color: #fff;
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
  flex: 1 1 auto;
  min-height: 0;
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

.plot-card-scatter {
  flex: 1 1 42%;
  min-height: 160px;
}

.plot-card-histogram {
  flex: 1 1 38%;
  min-height: 180px;
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

.plot-histogram-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  padding: 6px 8px 4px;
}

.plot-scale-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--fg-dim);
}

.plot-scale-select {
  font-size: 11px;
  font-family: inherit;
  color: var(--fg);
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 2px 6px;
}

.plot-histogram-caption {
  flex: 1 1 auto;
  min-width: 180px;
  font-size: 10px;
  color: var(--fg-dim);
}

.plot-card-scatter {
  --plot-cross: #ffa03c;
}

.plot-svg {
  display: block;
  width: 100%;
  height: auto;
  cursor: crosshair;
}

.plot-crosshair-line {
  stroke-width: 1;
  pointer-events: none;
}

.plot-crosshair-ring {
  fill: none;
  stroke: var(--plot-cross);
  stroke-width: 1.5;
  pointer-events: none;
}

.plot-crosshair-tip-bg {
  /* Semi-transparent so the chart underneath blends through, matching the desktop app's alpha-blended tooltip. */
  fill: var(--panel-bg);
  fill-opacity: 0.9;
  stroke: var(--border);
  stroke-width: 1;
}

.plot-crosshair-tip-text {
  font-size: 11px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  fill: var(--fg);
}

.plot-crosshair-tip-sub {
  font-size: 10px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  fill: var(--fg-dim);
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

.plot-footer-spacer {
  flex: 1;
}

.distrib-toolbar {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 4px;
  padding: 4px 0 8px;
}

.distrib-selectors {
  display: flex;
  flex-wrap: nowrap;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.distrib-selectors label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  flex: 1 1 0;
  min-width: 0;
}

.distrib-selectors label > :deep(.dom-select) {
  flex: 1 1 auto;
  min-width: 72px;
}

.distrib-actions {
  display: flex;
  flex-wrap: nowrap;
  align-items: center;
  gap: 6px;
}

.distrib-actions .stats-tool-btn {
  flex: 0 0 auto;
  white-space: nowrap;
}

.distrib-hist {
  min-height: 200px;
  margin-top: 4px;
}

.distrib-hist-svg {
  display: block;
  width: 100%;
  min-height: 200px;
}

.spark-col {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  letter-spacing: -0.05em;
  white-space: nowrap;
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
