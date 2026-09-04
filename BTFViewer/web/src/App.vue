<template>
  <div
    class="app"
    :class="{ dark: timelineOptions.darkMode, 'drag-over': dragOver, 'focus-mode': focusMode && !!trace }"
    @dragenter.prevent="onDragEnter"
    @dragover.prevent="onDragOver"
    @dragleave.prevent="onDragLeave"
    @drop.prevent="onFileDrop"
  >
    <!-- Toolbar -->
    <Toolbar
      ref="toolbarRef"
      :model-value="timelineOptions"
      :trace-info="traceInfo"
      :task-filter-active="!!timelineOptions.taskFilterKeys?.length"
      :range-enabled="rangeEnabled"
      :zoom-out-enabled="zoomOutEnabled"
      :loading="loading"
      :loading-pct="loadingPct"
      :loading-msg="loadingMsg"
      :time-scale="trace?.timeScale || 'ns'"
      :recording="demoRecording"
      :zoom-preset-value="zoomPresetValue"
      :zoom-preset-options="zoomPresetOptions"
      :limit-on="limitOn"
      :filter-active="!!activeFilterSummaryLabel"
      :filter-label="activeFilterSummaryLabel || ''"
      @update:model-value="onToolbarOptionsUpdate"
      @toggle-limit="onToggleLimit"
      @clear-filters="clearAllActiveFilters"
      @file-error="onFileError"
      @trace-reading="onTraceReading"
      @trace-loaded="onTraceLoaded"
      @traces-loaded="onUserTracesLoaded"
      @load-demo="onLoadDemo"
      @demo-pack="startDemoPack"
      @demo-folder="onDemoFolderNeeded"
      @toggle-record="onToggleRecord"
      @zoom="onZoom"
      @fit="onFit"
      @zoom-preset="onZoomPreset"
      @zoom1to1="onZoom1to1"
      @zoom-range="onZoomRange"
      @show-find="focusFindPanel"
      @expand-all="onExpandAll"
      @collapse-all="onCollapseAll"
      @add-mark="onAddMark"
      @export-svg="onExportSvg"
      @export-perfetto="onExportPerfetto"
      @export-slice="onExportBtfSlice"
      @clear-task-filter="clearHeatmapTaskFilter"
      @show-about="openAboutDialog"
    />

    <div
      v-if="demoRunning"
      class="demo-status-banner"
      role="status"
    >
      <button
        type="button"
        class="demo-nav-btn"
        title="Previous section"
        aria-label="Previous demo section"
        tabindex="-1"
        :disabled="!demoNavReady || !demoNav.canPrev"
        @pointerdown.prevent.stop="onDemoPrev"
      >
        <svg
          viewBox="0 0 16 16"
          width="14"
          height="14"
          fill="currentColor"
          aria-hidden="true"
        >
          <path
            fill-rule="evenodd"
            :d="IC.demoPrev"
          />
        </svg>
      </button>
      <button
        type="button"
        class="demo-nav-btn"
        :class="{ 'is-paused': demoPaused }"
        :title="demoPaused ? 'Resume demo' : 'Pause demo'"
        :aria-label="demoPaused ? 'Resume demo' : 'Pause demo'"
        tabindex="-1"
        :disabled="!demoNavReady"
        @pointerdown.prevent.stop="onDemoPause"
      >
        <svg
          viewBox="0 0 16 16"
          width="14"
          height="14"
          fill="currentColor"
          aria-hidden="true"
        >
          <path
            fill-rule="evenodd"
            :d="demoPaused ? IC.demoPlay : IC.demoPause"
          />
        </svg>
      </button>
      <button
        type="button"
        class="demo-nav-btn"
        title="Next section"
        aria-label="Next demo section"
        tabindex="-1"
        :disabled="!demoNavReady || !demoNav.canNext"
        @pointerdown.prevent.stop="onDemoNext"
      >
        <svg
          viewBox="0 0 16 16"
          width="14"
          height="14"
          fill="currentColor"
          aria-hidden="true"
        >
          <path
            fill-rule="evenodd"
            :d="IC.demoNext"
          />
        </svg>
      </button>
      <span class="demo-status-text">{{ demoStatusText }}</span>
      <label
        v-if="demoVoiceLangs.length > 1"
        class="demo-lang"
      >
        <span class="demo-lang-label">Voice</span>
        <DomSelect
          class="demo-lang-select"
          :model-value="demoVoiceLang"
          aria-label="Demo narration language"
          :options="demoVoiceLangOptions"
          @pointerdown.stop
          @update:model-value="onDemoVoiceLangPick"
        />
      </label>
      <span class="demo-status-hint">{{ demoPaused ? 'Paused · Esc twice to stop' : 'Esc twice to stop' }}</span>
    </div>

    <div
      v-if="demoFolderPrompt"
      class="dialog-overlay"
      @click.self="demoFolderPrompt = null"
    >
      <div
        class="demo-folder-dialog"
        role="dialog"
        aria-modal="true"
        aria-label="Choose demo folder"
      >
        <div class="demo-folder-header">
          <div class="demo-folder-title">
            Open demo pack
          </div>
          <button
            class="demo-folder-close"
            type="button"
            @click="demoFolderPrompt = null"
          >
            ✕
          </button>
        </div>
        <div class="demo-folder-body">
          The browser cannot read sibling files from
          <strong>{{ demoFolderPrompt.xmlName }}</strong> alone.
          Choose the pack folder that contains that XML,
          <code>{{ demoFolderPrompt.traceName || '.btf.gz' }}</code>,
          and <code>voice/</code>
          — then click Open / Select.
          You can also drop that folder onto the viewer.
        </div>
        <div class="demo-folder-footer">
          <button
            type="button"
            class="demo-folder-btn primary"
            @click="onOpenDemoPackFolder"
          >
            Open pack folder
          </button>
          <button
            type="button"
            class="demo-folder-btn"
            @click="demoFolderPrompt = null"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>

    <!-- Unified context strip: trace-quality / evidence inspector / cursor scope
         helper share one bordered zone instead of stacking as loose bars. -->
    <div
      v-if="hasContextStrip"
      class="context-strip"
    >
    <div
      v-if="traceQualityReportData && !traceQualityReportData.ok"
      class="trace-quality-banner ctx-row ctx-row--warn"
      role="status"
    >
      <span>{{ traceQualityReportData.summary }}</span>
      <button
        type="button"
        class="first-run-btn"
        @click="traceQualityDetailsOpen = !traceQualityDetailsOpen"
      >
        Review details
      </button>
      <button
        type="button"
        class="first-run-btn"
        @click="onTraceQualityContinue"
      >
        Continue with limitations
      </button>
      <a
        class="first-run-btn"
        href="WORKFLOWS.md#trace-quality"
        target="_blank"
        rel="noopener"
      >Open capture guidance</a>
    </div>
    <div
      v-if="traceQualityDetailsOpen && traceQualityReportData?.groups?.length"
      class="trace-quality-details ctx-row ctx-row--warn"
      role="region"
      aria-label="Trace quality details"
    >
      <div
        v-for="grp in traceQualityReportData.groups"
        :key="grp.id"
        class="trace-quality-group"
      >
        <strong>{{ grp.title }}</strong>
        <ul>
          <li
            v-for="(line, i) in grp.lines"
            :key="i"
          >{{ line }}</li>
        </ul>
        <div
          v-if="grp.affected?.length"
          class="trace-quality-affected"
        >
          Affects: {{ grp.affected.join(', ') }}
        </div>
      </div>
    </div>

    <div
      v-if="evidenceInspectorText"
      class="evidence-inspector-bar ctx-row ctx-row--info"
      role="status"
      aria-label="Timeline evidence inspector"
    >
      <button
        type="button"
        class="first-run-btn"
        :disabled="!evidenceNav.can_back"
        title="Previous evidence jump"
        @click="stepEvidenceBack"
      >
        Back
      </button>
      <button
        type="button"
        class="first-run-btn"
        :disabled="!evidenceNav.can_forward"
        title="Next evidence jump"
        @click="stepEvidenceForward"
      >
        Forward
      </button>
      <span class="evidence-inspector-text">{{ evidenceInspectorText }}</span>
    </div>

    <div
      v-if="showCursorScopeBanner"
      class="cursor-scope-banner ctx-row ctx-row--info"
      role="status"
    >
      <span>{{ useAsScopePrompt }}</span>
      <button
        type="button"
        class="first-run-btn primary"
        @click="applyCursorsAsScope"
      >
        Enable Limit to C1–Cn
      </button>
      <span
        v-if="multiCursorWarning"
        class="cursor-scope-warn"
      >{{ multiCursorWarning }}</span>
      <button
        type="button"
        class="cursor-scope-close"
        title="Dismiss"
        aria-label="Dismiss cursor scope helper"
        @click="dismissCursorScopeBanner"
      >
        ×
      </button>
    </div>
    </div><!-- /context-strip -->

    <!-- Trace tabs -->
    <div
      v-if="tabs.length"
      class="trace-tabs"
      role="tablist"
      aria-label="Open traces"
    >
      <button
        v-for="tab in tabs"
        :key="tab.id"
        class="trace-tab"
        :class="{ active: tab.id === activeTabId }"
        role="tab"
        type="button"
        :aria-selected="tab.id === activeTabId"
        :title="tab.name"
        @click="activeTabId = tab.id"
      >
        <span class="trace-tab-label">{{ tab.name }}</span>
        <span
          class="trace-tab-close"
          title="Close tab"
          aria-label="Close tab"
          @click.stop="closeTab(tab.id)"
        >×</span>
      </button>
    </div>

    <!-- Main area -->
    <div class="main-area">
      <!-- Loading: a hairline progress bar under the toolbar + a timeline
           skeleton (below) instead of a modal card, so nothing shifts when
           the real timeline mounts. -->
      <div
        v-if="loading"
        class="load-progressbar"
        role="progressbar"
        :aria-valuenow="Math.round(loadingPct)"
        aria-valuemin="0"
        aria-valuemax="100"
        :aria-label="`Loading ${loadingFileName || 'trace'}`"
      >
        <div
          class="load-progressbar-fill"
          :class="{ indeterminate: !loadingPctLabel }"
          :style="{ width: (loadingPctLabel ? loadingPct : 100) + '%' }"
        />
      </div>
      <div
        class="demo-message-overlay"
        aria-live="polite"
      >
        <Transition name="demo-message">
          <div
            v-if="demoMessageText"
            class="demo-message-card"
          >
            {{ demoMessageText }}
          </div>
        </Transition>
      </div>
      <!-- Left activity rail: investigation entry points that have no panel home. -->
      <nav
        v-if="trace"
        class="activity-rail"
        aria-label="Investigation tools"
      >
        <button
          v-if="heatmapEnabled"
          type="button"
          class="rail-btn act-btn"
          data-demo-target="rail_heatmap"
          title="Migration heatmap"
          @click="onOpenHeatmap"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><rect x="3.5" y="3.5" width="7" height="7" rx="1"/><rect x="13.5" y="3.5" width="7" height="7" rx="1"/><rect x="3.5" y="13.5" width="7" height="7" rx="1"/><rect x="13.5" y="13.5" width="7" height="7" rx="1"/></svg>
          <span class="rail-tip act-tip">Migration heatmap</span>
        </button>
        <button
          type="button"
          class="rail-btn act-btn"
          data-demo-target="rail_analysis"
          title="Analysis findings"
          @click="analysisOpen = true"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" aria-hidden="true"><path d="M9 3h6M10 3v5l-5 9.2A2 2 0 0 0 6.8 20h10.4a2 2 0 0 0 1.8-2.8L14 8V3"/></svg>
          <span class="rail-tip act-tip">Analysis findings</span>
        </button>
        <button
          v-if="compareTabs.length >= 2"
          type="button"
          class="rail-btn act-btn"
          data-demo-target="rail_compare"
          title="Compare traces"
          @click="onOpenTraceCompare"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="6" cy="18" r="2.5"/><circle cx="18" cy="6" r="2.5"/><path d="M6 15.5V9a3 3 0 0 1 3-3h4M18 8.5V15a3 3 0 0 1-3 3h-4"/><path d="m11 4 2 2-2 2M13 20l-2-2 2-2"/></svg>
          <span class="rail-tip act-tip">Compare traces</span>
        </button>
        <button
          v-if="traceInfo"
          type="button"
          class="rail-btn act-btn"
          data-demo-target="rail_snapshot"
          title="Snapshot editor"
          @click="onCopyScreenshot"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" aria-hidden="true"><path d="M3 8a2 2 0 0 1 2-2h2.5l1.6-2h5.8L18.5 6H19a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><circle cx="12" cy="12.5" r="3.5"/></svg>
          <span class="rail-tip act-tip">Snapshot editor</span>
        </button>
        <span class="act-spring" aria-hidden="true"></span>
        <button
          type="button"
          class="rail-btn act-btn"
          data-demo-target="rail_help"
          title="Help &amp; keyboard shortcuts"
          @click="openHelpDialog"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M9.6 9.2a2.4 2.4 0 0 1 4.7.6c0 1.6-2.3 2-2.3 3.4"/><path d="M12 17h.01"/></svg>
          <span class="rail-tip act-tip">Help</span>
        </button>
        <button
          type="button"
          class="rail-btn act-btn"
          data-demo-target="rail_settings"
          title="Settings"
          @click="openSettingsDialog"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="3"/><path d="M19.4 13a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 0 1-4 0v-.2a1.7 1.7 0 0 0-1-1.5 1.7 1.7 0 0 0-1.9.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1H3a2 2 0 0 1 0-4h.2a1.7 1.7 0 0 0 1.5-1 1.7 1.7 0 0 0-.3-1.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.9.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 0 1 4 0v.2a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.9-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.9V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 0 1 0 4h-.2a1.7 1.7 0 0 0-1.4 1z"/></svg>
          <span class="rail-tip act-tip">Settings</span>
        </button>
      </nav>

      <div ref="leftPaneRef" class="left-pane">
        <div class="timeline-wrap">
          <!-- First-load skeleton: placeholder lanes so the layout is already
               the right shape when TimelinePanel takes over. -->
          <div
            v-if="loading && !trace"
            class="timeline-skeleton"
            aria-hidden="true"
          >
            <div class="tl-skel-axis" />
            <div
              v-for="n in 9"
              :key="n"
              class="tl-skel-row"
            >
              <div class="tl-skel-label" />
              <div class="tl-skel-track">
                <span
                  v-for="seg in skeletonRow(n)"
                  :key="seg.k"
                  class="tl-skel-seg"
                  :style="{ left: seg.left + '%', width: seg.width + '%' }"
                />
              </div>
            </div>
          </div>
          <TimelinePanel
            ref="timelinePanelRef"
            :trace="trace"
            :options="timelineOptions"
            :cursors="cursors"
            :max-cursors="appSettings.maxCursors"
            :label-width="appSettings.labelWidth"
            :time-decimals="appSettings.timeDecimals"
            :find-hits="findHits"
            :finding-hits="findingHits"
            :find-marker-ns="findMarkerNs"
            :persisted-viewport="timelineViewport"
            @cursors-change="cursors = $event"
            @hover-time-change="cpuLoadHoverTime = $event"
            @viewport-change="onTimelineViewportChange"
            @highlight-change="(k) => timelineOptions.highlightKey = k ?? pinnedHighlightKey"
            @highlight-click="onHighlightClick"
            @segment-click="onSegmentClick"
            @clear-selection="clearCpuLoadSelection"
            @add-bookmark="onAddBookmark"
            @add-annotation="onAddAnnotation"
            @clear-bookmarks="onClearBookmarks"
            @clear-annotations="onClearAnnotations"
            @clear-all-marks="onClearAllMarks"
            @mark-move="onMoveMark"
            @copy-screenshot="onCopyScreenshot"
            @export-svg="onExportSvg"
            @before-cursor-change="pushUndoSnapshot"
            @before-mark-change="pushUndoSnapshot"
            @label-width-change="onLabelWidthChange"
            @explain-region="queryExplainRegionWithAi"
            @ask-ai-event="queryAskAiEvent"
            :ai-enabled="appSettings.aiEnabled !== false"
            :colorblind-safe="appSettings.colorblindSafe"
          />
        </div>

        <div
          v-if="trace && timelineOptions.showCpuLoad"
          class="panel-resizer-h"
          role="separator"
          aria-label="Resize CPU load panel"
          aria-orientation="horizontal"
          @mousedown.prevent="onCpuLoadResizeStart"
        />

        <CpuLoadPanel
          ref="cpuLoadPanelRef"
          v-if="trace && timelineOptions.showCpuLoad"
          :style="{ height: cpuLoadPaneHeight + 'px', flexShrink: 0 }"
          :trace="trace"
          :viewport="timelineViewport"
          :view-mode="timelineOptions.viewMode"
          :orientation="timelineOptions.orientation"
          :dark-mode="timelineOptions.darkMode"
          :selected-task="cpuLoadSelectedTask"
          :all-expanded="cpuLoadExpanded"
          :cursors="cursors"
          :hover-time="cpuLoadHoverTime"
          :marks="marks"
          :cpu-load-row-h="appSettings.cpuLoadRowH"
          :layout-rev="timelineOptions.layoutRev"
          :migrated-only-filter="timelineOptions.migratedOnlyFilter"
          :task-filter-keys="timelineOptions.taskFilterKeys"
          :task-filter-text="timelineOptions.taskFilterText"
          :core-filter-keys="timelineOptions.coreFilterKeys"
          :label-width="appSettings.labelWidth"
          :colorblind-safe="appSettings.colorblindSafe"
          @clear-selection="clearCpuLoadSelection"
          @viewport-change="onCpuLoadViewportChange"
          @toggle-expand-all="onCpuLoadToggleExpandAll"
        />
      </div>

      <div
        v-if="trace"
        class="panel-resizer"
        :class="{ 'is-collapsed': rightPanelCollapsed }"
        role="separator"
        aria-label="Resize side panel — double-click to collapse"
        aria-orientation="vertical"
        title="Drag to resize · double-click to collapse"
        @mousedown.prevent="onRightPanelResizeStart"
        @dblclick="toggleRightPanelCollapsed"
      />

      <!-- Right panel -->
      <div
        v-if="trace"
        class="right-panel"
        :class="{ collapsed: rightPanelCollapsed }"
        :style="{ width: (rightPanelCollapsed ? 44 : rightPanelWidth) + 'px' }"
      >
        <div v-show="!rightPanelCollapsed" class="rp-main">
          <div class="rp-page-header">
            <h2 class="rp-title">{{ rightPanelTitle }}</h2>
          </div>

        <div class="panel-page-wrap">
          <div v-if="rightPanelTab === 'marks'" class="panel-page panel-page-marks">
            <div class="rp-card" :class="{ collapsed: !marksSectionOpen.cursors }">
              <button
                type="button"
                class="rp-card-head"
                :aria-expanded="marksSectionOpen.cursors"
                @click="toggleMarksSection('cursors')"
              >
                <svg class="rp-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg>
                <span class="rp-card-title">Cursors</span>
                <span v-if="placedCursorTimes.length" class="rp-card-count">{{ placedCursorTimes.length }}</span>
              </button>
              <div v-show="marksSectionOpen.cursors" class="rp-card-body">
                <CursorPanel
                  :cursors="cursors"
                  :trace="trace"
                  :time-scale="trace.timeScale"
                  :core-filter-keys="timelineOptions.coreFilterKeys"
                  @delete-cursor="onDeleteCursor"
                  @jump-to-cursor="timelinePanelRef?.jumpToNs($event)"
                  @clear-all="clearCursors"
                  @core-filter-change="onCoreFilterChange"
                />
              </div>
            </div>

            <div class="rp-card" :class="{ collapsed: !marksSectionOpen.range }">
              <button
                type="button"
                class="rp-card-head"
                :aria-expanded="marksSectionOpen.range"
                @click="toggleMarksSection('range')"
              >
                <svg class="rp-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg>
                <span class="rp-card-title">Cursor Range</span>
                <span v-if="cursorRangeStats" class="rp-card-count">A&ndash;B</span>
              </button>
              <div v-show="marksSectionOpen.range" class="rp-card-body">
              <div
                v-if="cursorRangeStats"
                class="cursor-range-body"
              >
                <div class="cursor-range-row">
                  <span class="cursor-range-key">Span</span>
                  <span class="cursor-range-val">{{ cursorRangeStats.span }}</span>
                </div>
                <div class="cursor-range-row">
                  <span class="cursor-range-key">Slices</span>
                  <span class="cursor-range-val">{{ cursorRangeStats.switches }}</span>
                </div>
                <div
                  v-if="cursorRangeStats.topTask"
                  class="cursor-range-row"
                >
                  <span class="cursor-range-key">Top task</span>
                  <span class="cursor-range-val">{{ cursorRangeStats.topTask }} ({{ cursorRangeStats.topPct }}%)</span>
                </div>
                <div
                  v-if="cursorRangeStats.dMin"
                  class="cursor-range-row"
                >
                  <span class="cursor-range-key">Seg min</span>
                  <span class="cursor-range-val">{{ cursorRangeStats.dMin }}</span>
                </div>
                <div
                  v-if="cursorRangeStats.dAvg"
                  class="cursor-range-row"
                >
                  <span class="cursor-range-key">Seg avg</span>
                  <span class="cursor-range-val">{{ cursorRangeStats.dAvg }}</span>
                </div>
                <div
                  v-if="cursorRangeStats.dMax"
                  class="cursor-range-row"
                >
                  <span class="cursor-range-key">Seg max</span>
                  <span class="cursor-range-val">{{ cursorRangeStats.dMax }}</span>
                </div>
              </div>
              <div
                v-else
                class="cursor-range-hint"
              >
                Place 2+ cursors to measure range
              </div>
              </div>
            </div>

            <div class="rp-card" :class="{ collapsed: !marksSectionOpen.marks }">
              <button
                type="button"
                class="rp-card-head"
                :aria-expanded="marksSectionOpen.marks"
                @click="toggleMarksSection('marks')"
              >
                <svg class="rp-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg>
                <span class="rp-card-title">Marks</span>
                <span v-if="marks.length" class="rp-card-count">{{ marks.length }}</span>
              </button>
              <div v-show="marksSectionOpen.marks" class="rp-card-body">
                <MarksPanel
                  ref="marksPanelRef"
                  :marks="marks"
                  :time-scale="trace.timeScale"
                  :time-decimals="appSettings.timeDecimals"
                  @delete-mark="onDeleteMark"
                  @jump-to="onJumpToMark"
                  @update-label="onUpdateMarkLabel"
                  @import-marks="onImportMarks"
                  @clear-bookmarks="onClearBookmarks"
                  @clear-annotations="onClearAnnotations"
                  @export-session="onExportSession"
                  @export-evidence-pack="onExportEvidencePack"
                  @import-session="onImportSession"
                  @select-mark="timelineOptions.selectedMarkId = $event"
                />
              </div>
            </div>
          </div>

          <div v-else-if="rightPanelTab === 'find'" class="panel-page panel-page-find">
            <div class="panel-section flex-fill">
              <FindPanel
                ref="findPanelRef"
                :query="findQuery"
                :mode="findMode"
                :hit-count="findHits.length"
                :hit-index="findHitIdx"
                :error="findError"
                @update:query="onFindQueryChange"
                @update:mode="onFindModeChange"
                @recompute="recomputeFind"
                @next="() => stepFind(true)"
                @prev="() => stepFind(false)"
              />
            </div>
          </div>

          <div
            v-else-if="rightPanelTab === 'legend' && appSettings.showLegend"
            class="panel-page panel-page-legend"
          >
            <div class="panel-section flex-fill">
              <LegendPanel
                :trace="trace"
                :highlight-key="timelineOptions.highlightKey"
                :selected-key="pinnedHighlightKey"
                :task-filter-keys="timelineOptions.taskFilterKeys"
                :task-filter-text="timelineOptions.taskFilterText"
                :migrated-only-filter="timelineOptions.migratedOnlyFilter"
                :heatmap-filter-label="timelineOptions.heatmapFilterLabel"
                :view-mode="timelineOptions.viewMode"
                :core-filter-keys="timelineOptions.coreFilterKeys"
                :dark-mode="timelineOptions.darkMode"
                :colorblind-safe="appSettings.colorblindSafe"
                @highlight-change="(k) => { timelineOptions.highlightKey = k ?? pinnedHighlightKey; scheduleRender() }"
                @highlight-click="onHighlightClick"
                @migrated-filter-change="onMigratedFilterChange"
                @filter-change="onTaskFilterChange"
                @clear-task-filter="clearHeatmapTaskFilter"
                @core-filter-change="onCoreFilterChange"
              />
            </div>
          </div>

          <div
            v-else-if="rightPanelTab !== 'ai' || !aiTabVisible"
            class="panel-page panel-page-stats"
          >
            <div class="panel-section flex-fill">
              <StatisticsPanel
                ref="statsPanelRef"
                :trace="trace"
                :cursors="cursors"
                :tabs="tabs"
                :stats-paused="statsPaused"
                :open-plot="activeTab?.openPlot ?? null"
                :section-heights="statsSectionHeights"
                :scope-to-cursors="activeTab?.scopeToCursors !== false"
                :analysis-settings="appSettings"
                :section-collapsed-state="appSettings.statsSectionCollapsed"
                :section-pins="appSettings.statsPinnedSections || []"
                :section-order="appSettings.statsSectionOrder || []"
                :active-filter-label="activeFilterSummaryLabel"
                :trace-file-name="activeTab?.name || ''"
                :on-clear-filters="clearAllActiveFilters"
                @update:open-plot="onOpenPlotChange"
                @update:section-heights="onSectionHeightsChange"
                @update:scope-to-cursors="onStatsScopeChange"
                @update:section-collapsed-state="onStatsSectionCollapsedChange"
                @update:section-pins="onStatsSectionPinsChange"
                @update:section-order="onStatsSectionOrderChange"
                @highlight-task="onHighlightClick"
                @plot-point-activate="onStatsPlotPointActivate"
                @explore-range="applyExploreRange"
                @segment-jump="onStatsSegmentJump"
                @open-pair-heatmap="onOpenPairHeatmap"
                @open-pair-chord="onOpenPairChord"
                @filter-timeline="onStatsFilterTimeline"
                @open-settings="openSettingsDialog"
                @query-ai="queryAnalysisWithAi"
                @clear-scope="onStatsScopeChange(false)"
                @clear-filter="clearAllActiveFilters"
              />
            </div>
          </div>

          <!-- Outside the v-if chain and only hidden, never destroyed, so the
               conversation survives tab switches and a reply that arrives while
               another tab is open still lands in the log. -->
          <div
            v-if="aiTabVisible"
            v-show="rightPanelTab === 'ai'"
            class="panel-page panel-page-ai"
          >
            <div class="panel-section flex-fill">
              <AiAssistantPanel
                ref="aiPanelRef"
                :analysis-context="aiAnalysisContext"
                :show-clear-filters="!!activeFilterSummaryLabel"
                :on-clear-filters="clearAllActiveFilters"
                :ai-enabled="appSettings.aiEnabled !== false"
                :ai-preset="appSettings.aiPreset"
                :ai-presets="appSettings.aiPresets"
                :response-language="appSettings.aiResponseLanguage"
                :ai-auto-apply="!!appSettings.aiAutoApply"
                :ai-context-mode="appSettings.aiContextMode"
                :ai-redact-task-names="!!appSettings.aiRedactTaskNames"
                :ai-trace-sensitive="!!appSettings.aiTraceSensitive"
                :dark-mode="timelineOptions.darkMode"
                :get-context="buildAiContext"
                :get-loaded-tabs="listAiLoadedTabs"
                :build-compare-context="buildAiCompareContext"
                :execute-tools="onAiExecuteTools"
                :undo-tools="onAiUndoTools"
                :get-gui-state="aiGuiStateForReport"
                @open-settings="openSettingsDialog('ai')"
                @update:response-language="onAiResponseLanguage"
                @jump="onAiJump"
                @range="onAiRange"
                @highlight="onAiHighlight"
                @open-stats="onAiOpenStats"
                @status-message="onAiStatusMessage"
                @session-change="scheduleSessionSave"
              />
            </div>
          </div>
        </div>
        </div><!-- /rp-main -->

        <nav class="icon-rail" role="tablist" aria-label="Right panel navigation">
          <button
            v-if="appSettings.showStats"
            class="rail-btn"
            data-demo-target="stats_tab"
            :class="{ active: rightPanelTab === 'stats' }"
            role="tab"
            :aria-selected="rightPanelTab === 'stats'"
            title="Statistics"
            @click="selectRightPanelTab('stats')"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/></svg>
            <span class="rail-tip">Statistics</span>
          </button>
          <button
            v-if="appSettings.showMarks"
            class="rail-btn"
            :class="{ active: rightPanelTab === 'marks' }"
            role="tab"
            :aria-selected="rightPanelTab === 'marks'"
            title="Marks"
            @click="selectRightPanelTab('marks')"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M6 3h12v18l-6-4-6 4z"/></svg>
            <span class="rail-tip">Marks</span>
          </button>
          <button
            v-if="appSettings.showFind"
            class="rail-btn"
            data-demo-target="find_tab"
            :class="{ active: rightPanelTab === 'find' }"
            role="tab"
            :aria-selected="rightPanelTab === 'find'"
            title="Find"
            @click="selectRightPanelTab('find')"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></svg>
            <span class="rail-tip">Find</span>
          </button>
          <button
            v-if="appSettings.showLegend"
            class="rail-btn"
            :class="{ active: rightPanelTab === 'legend' }"
            role="tab"
            :aria-selected="rightPanelTab === 'legend'"
            title="Legend"
            @click="selectRightPanelTab('legend')"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><circle cx="5" cy="6" r="1.6"/><circle cx="5" cy="12" r="1.6"/><circle cx="5" cy="18" r="1.6"/><path d="M10 6h11M10 12h11M10 18h11"/></svg>
            <span class="rail-tip">Legend</span>
          </button>
          <span v-if="aiTabVisible" class="rail-sep" aria-hidden="true"></span>
          <button
            v-if="aiTabVisible"
            class="rail-btn"
            data-demo-target="ai_tab"
            :class="{ active: rightPanelTab === 'ai' }"
            role="tab"
            :aria-selected="rightPanelTab === 'ai'"
            title="AI Assistant"
            @click="selectRightPanelTab('ai')"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M12 3l1.8 4.9L19 9.6l-4.2 2.4L14 17l-2-3.6L8 17l.2-5-4.2-2.4 5.2-1.7z"/></svg>
            <span class="rail-tip">AI</span>
          </button>
          <button
            type="button"
            class="rail-btn rail-collapse"
            :title="rightPanelCollapsed ? 'Expand panel' : 'Collapse panel'"
            :aria-label="rightPanelCollapsed ? 'Expand panel' : 'Collapse panel'"
            @click="toggleRightPanelCollapsed"
          >
            <svg v-if="rightPanelCollapsed" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M15 3v18"/><path d="m10 15-3-3 3-3"/></svg>
            <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M15 3v18"/><path d="m8 9 3 3-3 3"/></svg>
            <span class="rail-tip">{{ rightPanelCollapsed ? 'Expand panel' : 'Collapse panel' }}</span>
          </button>
        </nav>
      </div>
    </div>

    <!-- Settings dialog -->
    <SettingsDialog
      v-if="settingsOpen"
      :model-value="appSettings"
      :time-scale="trace?.timeScale || 'ns'"
      :initial-tab="settingsInitialTab"
      @close="onSettingsCancel"
      @preview="onSettingsPreview"
      @save="onSettingsSave"
    />

    <!-- Help dialog -->
    <div
      v-if="helpOpen"
      class="dialog-overlay"
      @click.self="helpOpen = false"
    >
      <div
        class="help-dialog"
        role="dialog"
        aria-modal="true"
        aria-label="Help and keyboard shortcuts"
      >
        <div class="help-header">
          <div class="help-title">
            Help & Shortcuts
          </div>
          <button
            class="help-close"
            @click="helpOpen = false"
          >
            ✕
          </button>
        </div>

        <div class="help-body">
          <div class="help-section">
            <div class="help-section-title">
              Keyboard
            </div>
            <div class="help-grid">
              <div class="k">
                ?
              </div><div>Open/close help</div>
              <div class="k">
                Ctrl+,
              </div><div>Open settings</div>
              <div class="k">
                Esc
              </div><div>Close dialog</div>
              <div class="k">
                1
              </div><div>Task view</div>
              <div class="k">
                2
              </div><div>Core view</div>
              <div class="k">
                H
              </div><div>Horizontal layout</div>
              <div class="k">
                V
              </div><div>Vertical layout</div>
              <div class="k">
                C
              </div><div>Place cursor at hover / centre</div>
              <div class="k">
                Shift+C
              </div><div>Clear all cursors</div>
              <div class="k">
                Ctrl+Z
              </div><div>Undo cursor / mark changes</div>
              <div class="k">
                Ctrl+Y
              </div><div>Redo</div>
              <div class="k">
                Ctrl+F
              </div><div>Open Find panel</div>
              <div class="k">
                F3 / Shift+F3
              </div><div>Find next / previous match</div>
              <div class="k">
                Ctrl+R
              </div><div>Fit Cursors — zoom to the C1–Cn Scope</div>
              <div class="k">
                Ctrl+G
              </div><div>Jump to time</div>
              <div class="k">
                Ctrl+Home / End
              </div><div>Jump to trace start / end</div>
              <div class="k">
                Ctrl+Shift+C
              </div><div>Copy viewport to clipboard (no editor)</div>
              <div class="k">
                Ctrl+W
              </div><div>Close active tab</div>
              <div class="k">
                Ctrl+Tab
              </div><div>Next trace tab</div>
              <div class="k">
                Ctrl+Shift+Tab
              </div><div>Previous trace tab</div>
              <div class="k">
                F
              </div><div>Fit Trace — zoom to show the entire trace</div>
              <div class="k">
                G
              </div><div>Toggle grid</div>
              <div class="k">
                I
              </div><div>Show/hide STI channels</div>
              <div class="k">
                D
              </div><div>Toggle dark/light mode</div>
              <div class="k">
                Ctrl+S
              </div><div>Open snapshot editor</div>
              <div class="k">
                Ctrl+Shift+S
              </div><div>Save viewport as SVG</div>
              <div class="k">
                Ctrl+K
              </div><div>Command palette</div>
              <div class="k">
                Ctrl+0
              </div><div>Fit Trace — zoom to show the entire trace</div>
              <div class="k">
                Ctrl+B
              </div><div>Add bookmark at current position</div>
              <div class="k">
                Ctrl+Shift+B
              </div><div>Add annotation at current position</div>
              <div class="k">
                Shift+B
              </div><div>Clear all bookmarks</div>
              <div class="k">
                Shift+A
              </div><div>Clear all annotations</div>
              <div class="k">
                B
              </div><div>Add bookmark at current position</div>
              <div class="k">
                A
              </div><div>Add annotation at current position</div>
              <div class="k">
                S
              </div><div>Open screenshot editor</div>
              <div class="k">
                +
              </div><div>Zoom in</div>
              <div class="k">
                -
              </div><div>Zoom out (until Fit)</div>
              <div class="k">
                Tab
              </div><div>Next segment</div>
              <div class="k">
                Shift+Tab
              </div><div>Previous segment</div>
            </div>
          </div>

          <div class="help-section">
            <div class="help-section-title">
              Mouse / Trackpad
            </div>
            <div class="help-grid">
              <div class="k">
                Wheel
              </div><div>Scroll task rows</div>
              <div class="k">
                Shift + Wheel
              </div><div>Pan timeline left/right</div>
              <div class="k">
                Ctrl/Cmd + Wheel
              </div><div>Zoom at pointer</div>
              <div class="k">
                Middle-drag
              </div><div>Draw a time region and zoom in on release</div>
              <div class="k">
                Ctrl+left-drag
              </div><div>Measure time between two points (double-arrow ruler + Δtime)</div>
              <div class="k">
                Left-drag ruler
              </div><div>Pan timeline</div>
              <div class="k">
                Click timeline
              </div><div>Place/remove cursor (Shift = snap to segment boundary)</div>
              <div class="k">
                Shift+right-click
              </div><div>Clear all cursors</div>
              <div class="k">
                Arrows
              </div><div>Scroll time (time axis) or rows (orthogonal axis)</div>
              <div class="k">
                Shift+arrows
              </div><div>Jump to previous / next segment boundary</div>
              <div class="k">
                Move mouse
              </div><div>Show live hover cursor in timeline and CPU load view</div>
              <div class="k">
                Drag cursor/mark
              </div><div>Move the same cursor, bookmark, or annotation in both views</div>
              <div class="k">
                Right-click timeline
              </div><div>Open context menu</div>
              <div class="k">
                Context menu
              </div><div>Copy screenshot</div>
              <div class="k">
                Double-click ruler
              </div><div>Fit Trace</div>
            </div>
          </div>

          <div class="help-section">
            <div class="help-section-title">
              Selection & CPU Load
            </div>
            <div class="help-grid">
              <div class="k">
                Task bar
              </div><div>Select that task and show its CPU load</div>
              <div class="k">
                Task name
              </div><div>Toggle task selection on/off in both task and core views</div>
              <div class="k">
                Core view label
              </div><div>Click a sub-task name in the left pane to select its merged task</div>
              <div class="k">
                CPU LOAD
              </div><div>Shows global load by default, or task-specific load when a task is selected</div>
              <div class="k">
                Load toggle
              </div><div>Use the toolbar <b>Load</b> button to show/hide the CPU load panel</div>
              <div class="k">
                CPU overlay
              </div><div>Cursors, bookmarks, and annotations appear as vertical lines; hover shows load % on each row</div>
            </div>
          </div>

          <div class="help-section">
            <div class="help-section-title">
              Capture & Export
            </div>
            <div class="help-grid">
              <div class="k">
                S / Ctrl+S
              </div><div>Open snapshot editor from the current timeline view</div>
              <div class="k">
                Save PNG
              </div><div>In the editor: export the annotated snapshot; includes CPU load when Load is on</div>
              <div class="k">
                Export SVG
              </div><div>Exports the current view; includes CPU load when Load is on</div>
              <div class="k">
                Perfetto / Ctrl+Shift+E
              </div><div>Download Chrome Trace JSON for ui.perfetto.dev (full trace or current viewport)</div>
              <div class="k">
                Save BTF
              </div><div>Download the cursor range (C1–Cn) as a .btf slice; needs two or more cursors</div>
              <div class="k">
                File names
              </div><div>Exports use timeline-with-load.* when CPU load is included</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- About dialog -->
    <div
      v-if="aboutOpen"
      class="dialog-overlay"
      @click.self="aboutOpen = false"
    >
      <div
        class="about-dialog"
        role="dialog"
        aria-modal="true"
        aria-label="About RTOS BTF Viewer"
      >
        <div class="about-hero">
          <div
            class="about-icon"
            aria-hidden="true"
            v-html="aboutIconSvg"
          />
          <div class="about-title">RTOS BTF Viewer</div>
          <div class="about-subtitle">AI assistant for RTOS trace analysis — find evidence and explain · v{{ appVersion }}</div>
        </div>

        <div class="about-body">
          <div class="about-section">
            <div class="about-section-title">View Modes</div>
            <div class="about-grid">
              <div class="about-key">Task View</div><div>one row per task</div>
              <div class="about-key">Core View</div><div>expandable rows per CPU core</div>
            </div>
          </div>

          <div class="about-section">
            <div class="about-section-title">Application</div>
            <div class="about-grid">
              <div class="about-key">Product</div><div>RTOS BTF Viewer</div>
              <div class="about-key">Purpose</div><div>AI assistant for RTOS trace analysis: find evidence and explain</div>
              <div class="about-key">Runtime</div><div>Vue 3 · Vite · Canvas-based timeline renderer</div>
              <div class="about-key">Build Date</div><div>{{ buildDate }}</div>
            </div>
          </div>

          <div class="about-section">
            <div class="about-section-title">License</div>
            <div class="about-grid">
              <div class="about-key">License</div><div>MIT License</div>
            </div>
          </div>
        </div>

        <div class="about-footer">
          <button
            class="about-close"
            @click="aboutOpen = false"
          >
            Close
          </button>
        </div>
      </div>
    </div>

    <JumpToTimeDialog
      v-if="jumpDialogOpen && trace"
      :trace="trace"
      @close="jumpDialogOpen = false"
      @jump="onJumpToTime"
      @jump-start="onJumpToTraceStart"
      @jump-end="onJumpToTraceEnd"
    />

    <CorridorInspectorDialog
      v-if="inspectorOpen && trace"
      :trace="trace"
      :cursors="cursors"
      :viewport="timelineViewport"
      :task-filter-active="!!timelineOptions.taskFilterKeys?.length"
      :task-filter-label="timelineOptions.heatmapFilterLabel"
      :task-filter-count="timelineOptions.taskFilterKeys?.length ?? 0"
      :focus-pair="inspectorFocusPair"
      :initial-mode="inspectorMode"
      :ai-enabled="appSettings.aiEnabled !== false"
      @close="onInspectorClose"
      @spotlight="onCorridorSpotlight"
      @jump="onCorridorJump"
      @clear-filter="clearHeatmapTaskFilter"
      @query-ai="queryCorridorWithAi"
      @inspect-task="onInspectorInspectTask"
      @open-load-balance="onInspectorOpenLoadBalance"
    />

    <div
      v-if="paletteOpen"
      class="palette-overlay"
      @click.self="closePalette"
    >
      <div
        class="palette-box"
        role="dialog"
        aria-label="Command palette"
      >
        <input
          ref="paletteInput"
          v-model="paletteQuery"
          class="palette-input"
          placeholder="Jump to Analysis, Statistics, AI…"
          @keydown="onPaletteKeydown"
        >
        <ul class="palette-list">
          <li
            v-for="(a, i) in paletteHits"
            :key="a.id"
            :class="{ on: i === paletteIndex, disabled: !a.available }"
            :title="a.available ? (a.shortcut || undefined) : a.reason"
            @mousedown.prevent="runPaletteAction(a.id)"
          >
            <span class="palette-label">{{ a.label }}</span>
            <span
              v-if="a.shortcut"
              class="palette-shortcut"
            >{{ a.shortcut }}</span>
          </li>
        </ul>
        <p class="palette-hint">Ctrl/Cmd+K · Esc to close</p>
      </div>
    </div>

    <AnalysisFindingsDialog
      v-if="analysisOpen && trace"
      :findings="analysisFindings"
      :scope-label="analysisScopeLabel"
      :analysis-context="findingsAnalysisContext"
      :context-stale="findingsContextStale"
      :show-clear-filters="!!activeFilterSummaryLabel"
      :on-clear-filters="clearAllActiveFilters"
      :ai-enabled="appSettings.aiEnabled !== false"
      :ux-events="analysisUxEvents"
      :time-min="trace.timeMin"
      :time-max="trace.timeMax"
      :quality-warnings="analysisQuality"
      :triage-state="findingsTriageState"
      :current-limit="!!(activeTab?.scopeToCursors !== false && placedCursorTimes.length >= 2)"
      :current-cursor-lo="placedCursorTimes.length >= 2 ? Math.min(...placedCursorTimes) : null"
      :current-cursor-hi="placedCursorTimes.length >= 2 ? Math.max(...placedCursorTimes) : null"
      :can-undo-investigate="!!findingsInvestigateUndo"
      @update:triage-state="onFindingsTriageUpdate"
      @close="analysisOpen = false"
      @query-ai="queryAnalysisWithAi"
      @apply-scope="onApplyFindingScope"
      @investigate="onInvestigateFinding"
      @undo-investigate="onUndoInvestigateFinding"
      @show-evidence="onShowFindingEvidence"
      @add-to-case="onAddFindingToCase"
      @recalculate-context="findingsContextSnapshot = { ...findingsAnalysisContext }"
      @save-recipe="onSaveAnalysisRecipe"
      @save-story="onSaveAnalysisStory"
    />

    <TraceCompareDialog
      v-if="compareOpen && compareTabs.length >= 2"
      :tabs="compareTabs"
      :initial-a="compareInitialA"
      :initial-b="compareInitialB"
      :analysis-context="compareAnalysisContext"
      :ai-enabled="appSettings.aiEnabled !== false"
      :analysis-settings="appSettings"
      @close="compareOpen = false"
      @query-ai="queryCompareWithAi"
      @validate-experiment="queryValidateExperimentWithAi"
      @compared="onTraceCompared"
      @investigate="onCompareInvestigate"
      @save-baseline="onCompareSaveBaseline"
      @score-baseline="onCompareScoreBaseline"
    />

    <!-- Snapshot editor -->
    <SnapshotEditor
      v-if="snapshotEditorOpen"
      :image-url="snapshotImageUrl"
      :download-filename="snapshotDownloadFilename"
      @close="onSnapshotEditorClose"
    />

    <!-- Toast notification -->
    <Transition name="toast">
      <div
        v-if="toastVisible"
        class="toast-notification"
        :class="toastType"
        @click="toastVisible = false"
      >
        {{ toastMsg }}
      </div>
    </Transition>

    <!-- Focus mode: floating way out (Esc also exits). -->
    <button
      v-if="focusMode && trace"
      type="button"
      class="focus-exit"
      title="Exit focus mode (Esc)"
      @click="setFocusMode(false)"
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M9 3H5a2 2 0 0 0-2 2v4M15 3h4a2 2 0 0 1 2 2v4M9 21H5a2 2 0 0 1-2-2v-4M15 21h4a2 2 0 0 0 2-2v-4"/></svg>
      Exit focus
    </button>

    <!-- Status bar -->
    <div class="status-bar">
      <template v-if="loading">
        <span class="status-loading">
          <span class="status-loading-spin" aria-hidden="true" />
          <span class="status-loading-text">
            {{ loadingFileName || 'Loading trace' }} · {{ loadingMsg || 'please wait' }}<template v-if="loadingPctLabel"> · {{ loadingPctLabel }}%</template>
          </span>
        </span>
        <button
          v-if="loadingCancellable"
          type="button"
          class="status-loading-cancel"
          @click="cancelLoading"
        >
          Cancel
        </button>
      </template>
      <template v-else-if="trace">
        <span
          class="status-summary"
          :class="{ error: !!(statusBarFlash && statusBarFlashError) }"
          :title="statusBarFlash || undefined"
        >
          <template v-if="statusBarFlash">{{ statusBarFlash }}</template>
          <template v-else>
            <template v-if="trace.meta?.creator">{{ trace.meta.creator }} · </template>{{ trace.tasks.length }} tasks · {{ trace.segments.length.toLocaleString() }} segments ·
            {{ trace.stiEvents.length.toLocaleString() }} STI events ·
            {{ formatTime(trace.timeMax - trace.timeMin, trace.timeScale, appSettings.timeDecimals) }} total
          </template>
        </span>
        <span
          class="status-inspect"
          :title="taskInspectorText"
        >{{ taskInspectorText }}</span>

        <div
          v-if="activeFilterChips.length"
          class="status-filters"
        >
          <span
            v-for="chip in activeFilterChips"
            :key="chip.key"
            class="status-filter-chip"
          >
            <span
              class="status-filter-chip-label"
              :title="chip.label"
            >{{ chip.label }}</span>
            <button
              type="button"
              class="status-filter-clear"
              title="Clear this filter"
              @click="chip.clear()"
            >×</button>
          </span>
          <button
            v-if="activeFilterChips.length > 1"
            type="button"
            class="status-filter-clear-all"
            title="Clear all active Filters"
            @click="activeFilterChips.forEach(c => c.clear())"
          >
            Clear All
          </button>
        </div>

        <CursorBar
          class="status-cursor-bar"
          :cursors="cursors"
          :time-scale="trace.timeScale"
          :dark-mode="timelineOptions.darkMode"
          :time-decimals="appSettings.timeDecimals"
          @jump-to-cursor="timelinePanelRef?.jumpToNs($event)"
          @delete-cursor="onDeleteCursor"
        />

        <span
          class="status-range"
          :title="statusRangeLine"
        >{{ statusRangeLine }}</span>

        <button
          v-if="findHits.length"
          type="button"
          class="status-find"
          :title="`Find match ${findHitPos} of ${findHits.length} — open the Find panel`"
          @click="focusFindPanel"
        >
          Find {{ findHitPos }} / {{ findHits.length }}
        </button>

        <div class="status-actions">
          <button
            class="status-toggle"
            :class="{ active: timelineOptions.showSti !== false }"
            type="button"
            title="Show or hide STI event markers"
            @click="timelineOptions.showSti = timelineOptions.showSti === false; persistTimelineViewPrefs()"
          >
            STI
          </button>
          <button
            class="status-toggle"
            :class="{ active: timelineOptions.showGrid }"
            type="button"
            title="Show or hide the time grid"
            @click="timelineOptions.showGrid = !timelineOptions.showGrid; persistTimelineViewPrefs()"
          >
            Grid
          </button>
          <span
            class="status-zoom"
            :title="zoomStatus.title"
          >
            <span class="status-zoom-scale">{{ zoomStatus.scale }}</span>
            <span
              v-if="zoomStatus.visible"
              class="status-zoom-visible"
            >{{ zoomStatus.visible }}</span>
          </span>
        </div>
      </template>
      <span
        v-else-if="statusBarFlash"
        class="status-summary"
        :class="{ error: statusBarFlashError }"
        :title="statusBarFlash"
      >{{ statusBarFlash }}</span>
      <span
        v-else
        class="status-hint"
      >
        Open a BTF trace to begin · Press ? for shortcuts
      </span>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted, onBeforeUnmount, nextTick, markRaw } from 'vue'
import { toBlob as domToBlob, toSvg as domToSvg } from 'html-to-image'
import Toolbar          from './components/Toolbar.vue'
import TimelinePanel    from './components/TimelinePanel.vue'
import CpuLoadPanel     from './components/CpuLoadPanel.vue'
import CursorPanel      from './components/CursorPanel.vue'
import CursorBar        from './components/CursorBar.vue'
import LegendPanel      from './components/LegendPanel.vue'
import StatisticsPanel  from './components/StatisticsPanel.vue'
import MarksPanel       from './components/MarksPanel.vue'
import SnapshotEditor   from './components/SnapshotEditor.vue'
import CorridorInspectorDialog from './components/CorridorInspectorDialog.vue'
import AnalysisFindingsDialog from './components/AnalysisFindingsDialog.vue'
import TraceCompareDialog from './components/TraceCompareDialog.vue'
import FindPanel from './components/FindPanel.vue'
import AiAssistantPanel from './components/AiAssistantPanel.vue'
import JumpToTimeDialog from './components/JumpToTimeDialog.vue'
import SettingsDialog from './components/SettingsDialog.vue'
import DomSelect from './components/DomSelect.vue'
import { formatTime }   from './renderer/TimelineRenderer.js'
import { zoomStatusFromViewport } from './utils/timeFormat.js'
import { taskDisplayName, taskMergeKey, setColorblindMode, setDarkMode } from './utils/colors.js'
import { taskPassesRowFilter, rawTaskNameMatchesTextFilter, normalizeTaskFilterText, coreFilterActive, taskRunsOnSelectedCore } from './utils/taskFilter.js'
import {
  AI_TOOL_ADD_ANNOTATION,
  AI_TOOL_ANALYZE_TRACES,
  AI_TOOL_BASELINE_SCORE,
  AI_TOOL_BOOKMARK_FINDING,
  AI_TOOL_CHECK_BUDGET,
  AI_TOOL_CLEAR_MARKS,
  AI_TOOL_COMPARE_PERFORMANCE,
  AI_TOOL_COMPARE_TASKS,
  AI_TOOL_CORRELATE_EVENTS,
  AI_TOOL_DETECT_PRIORITY_INVERSION,
  AI_TOOL_FIND_CRITICAL_PATH,
  AI_TOOL_DETECT_ANOMALIES,
  AI_TOOL_EXPLAIN_FINDING,
  AI_TOOL_FIND_RELATED_FINDINGS,
  AI_TOOL_GENERATE_REPORT,
  AI_TOOL_HIGHLIGHT_TASK,
  AI_TOOL_INVESTIGATE,
  AI_TOOL_INVESTIGATION_REPLAY,
  AI_TOOL_INTERPRET_QUERY,
  AI_TOOL_MANAGE_HYPOTHESES,
  AI_TOOL_PLAN_INVESTIGATION,
  AI_TOOL_SUGGEST_SCOPE,
  AI_TOOL_DETECT_CONTRADICTIONS,
  AI_TOOL_ASSESS_EVIDENCE_SUFFICIENCY,
  AI_TOOL_CLUSTER_FINDINGS,
  AI_TOOL_GENERATE_FINGERPRINT,
  AI_TOOL_FIND_SIMILAR_INVESTIGATIONS,
  AI_TOOL_REGRESSION_LOCALIZE,
  AI_TOOL_BUILD_CAUSAL_CHAIN,
  AI_TOOL_GENERATE_EXPERIMENT_PLAN,
  AI_TOOL_RECORD_EXPERIMENT_OUTCOME,
  AI_TOOL_SCORE_INVESTIGATION,
  AI_TOOL_ANALYZE_TEMPORAL_CAUSALITY,
  AI_TOOL_BUILD_TASK_DEPENDENCY_GRAPH,
  AI_TOOL_DECOMPOSE_RESPONSE_TIME,
  AI_TOOL_RANK_ROOT_CAUSES,
  AI_TOOL_VERIFY_CLAIM,
  AI_TOOL_CHALLENGE_CONCLUSION,
  AI_TOOL_INVESTIGATION_MEMORY,
  AI_TOOL_CLUSTER_INCIDENTS,
  AI_TOOL_CLOSE_INVESTIGATION,
  AI_TOOL_ANALYZE_DISTRIBUTION,
  AI_TOOL_ANALYZE_PERIODICITY,
  AI_TOOL_SUMMARIZE_INVESTIGATION_CONTEXT,
  AI_TOOL_OPEN_CORRIDOR,
  AI_TOOL_OPEN_STATS_SECTION,
  AI_TOOL_OPTIMIZE,
  AI_TOOL_OPTIMIZE_EXPERIMENT,
  AI_TOOL_QUERY_RAW_METRIC,
  AI_TOOL_RECOMMEND_EXPERIMENTS,
  AI_TOOL_REGRESSION_EXPLAIN,
  AI_TOOL_RESET_VIEW,
  AI_TOOL_SEARCH_TIMELINE,
  AI_TOOL_SET_CURSORS,
  AI_TOOL_SET_VIEW_MODE,
  AI_TOOL_TRIGGER_COMPARE,
  AI_TOOL_VALIDATE_EXPERIMENT,
  AI_TOOL_WHAT_IF,
  AI_TOOL_ZOOM_TO_RANGE,
  analyzeTracesSnapshots,
  baselineScoreFinding,
  budgetTaskRowsFromFindings,
  checkBudgetFinding,
  comparePerformanceTabs,
  compareTasksHost,
  correlateTaskEvents,
  detectAnomaliesFinding,
  detectPriorityInversionHost,
  explainFindingTool,
  findCriticalPathTask,
  findRelatedFindingsFinding,
  explainRegressionFromCompare,
  formatBookmarkLabel,
  generateReportFinding,
  investigateFinding,
  investigationReplayFinding,
  interpretQueryTool,
  manageHypothesesTool,
  planInvestigationTool,
  suggestScopeTool,
  detectContradictionsTool,
  assessEvidenceSufficiencyTool,
  clusterFindingsTool,
  generateFingerprintTool,
  findSimilarInvestigationsTool,
  regressionLocalizeTool,
  buildCausalChainTool,
  generateExperimentPlanTool,
  recordExperimentOutcomeTool,
  scoreInvestigationMetricsTool,
  analyzeTemporalCausalityTool,
  buildTaskDependencyGraphTool,
  decomposeResponseTimeTool,
  rankRootCausesTool,
  verifyClaimTool,
  challengeConclusionTool,
  investigationMemoryTool,
  clusterIncidentsTool,
  closeInvestigationTool,
  analyzeDistributionTool,
  analyzePeriodicityTool,
  distributionTraceContext,
  periodicityTraceContext,
  dependencyTraceContext,
  summarizeInvestigationContextTool,
  setExperimentOutcomes,
  experimentOutcomes,
  setInvestigationMemory,
  investigationMemoryStore,
  gatherSimulationInputs,
  optimizeExperimentFinding,
  optimizeFinding,
  queryRawMetric,
  recommendExperimentsFinding,
  resolveCoreKey,
  resolveTaskKey,
  searchTimelineHits,
  toolMutatesGui,
  validateExperimentTool,
  validateToolCall,
  whatIfEstimate,
} from './utils/aiTools.js'
import { detectAnomalies, parseWhatIfChange, snapshotFromSummary, updateBaselineProfile, scoreAgainstBaseline } from './utils/aiInvestigation.js'
import { formatAnalysisStory } from './utils/aiPlanner.js'
import { bestFindingScope, harvestUxEvents, findingOverlayTimes, taskInspectorLine } from './utils/uxExplore.js'
import { mergeIncidentOverlayTimes } from './utils/incidentOverlay.js'
import { resolveFindingEvidence } from './utils/evidenceNav.js'
import {
  formatLoadingMessage,
  formatLoadingPct,
  isLoadingCancellable,
  LOADING_STAGES,
} from './utils/loadingState.js'
import { formatErrorToast, formatParseError } from './utils/errorFormat.js'
import { checkPrerequisite, buildPrerequisiteContext } from './utils/disabledReason.js'
import { experimentPercentsFromCompare, newUserInvestigationTemplate } from './utils/aiCase.js'
import { filterBtfTextToRange, reconstructBtfSlice } from './utils/btfSlice.js'
import {
  DARK_MODE,
  HOVER_HIGHLIGHT,
  ORIENTATION,
  RIGHT_PANEL_MAX_W,
  RIGHT_PANEL_MIN_W,
  RIGHT_PANEL_WIDTH,
  SHOW_CPU_LOAD,
  SHOW_GRID,
  SHOW_STI,
  STI_LOG_SCALE,
  VIEW_MODE,
  COMMAND_PALETTE_ACTIONS,
  COMMAND_PALETTE_META,
  COMMAND_PALETTE_RECENT_MAX,
  commandPaletteRank,
  workspacePresetCollapsed,
} from './config.js'
import { loadSettings, saveSettings, applySettingsToRuntime, resizeTabCursors, normalizeSettings,
  loadAiBaselineProfile, saveAiBaselineProfile,
  loadAiUserInvestigationTemplates, saveAiUserInvestigationTemplates,
} from './utils/settingsStore.js'
import { setTimelineLayout } from './utils/timelineLayout.js'
import { traceIsMultiCore } from './utils/migrationAnalysis.js'
import { collectTraceAnalysisFindings, formatAnalysisFindingsText, FINDING_SECTION_MAP } from './utils/workflowAnalysis.js'
import { getPlacedCursors, getStatsRange } from './utils/statsRange.js'
import { buildAllCompareTables, buildCompareCsv, cursorRangeForCursors, traceSummarySnapshot } from './utils/traceCompare.js'
import {
  cpuLoadPreferredPaneHeight, cpuLoadPaneDefaultH, cpuLoadPaneMaxH,
  CPU_LOAD_PANE_MIN_H,
} from './utils/cpuLoadHelpers.js'
import { selectedTaskFromHighlight } from './utils/highlightLock.js'
import { useTraceTabs } from './composables/useTraceTabs.js'
import { loadSession, saveSession, buildSessionSnapshot, isRestorableViewport, applySavedLayout, applyTabState, mergeLegacyTabFilters } from './utils/sessionStore.js'
import { saveSessionOpfs, loadSessionOpfs } from './utils/sessionOpfs.js'
import { buildEvidencePackZip, downloadBlob } from './utils/evidencePack.js'
import { defaultTriageState, normalizeTriageState } from './utils/findingsTriage.js'
import { putTrace, getTrace, pruneTraces } from './utils/traceCache.js'
import { computeCursorRangeStats, formatStatusRangeLine } from './utils/rangeStats.js'
import { cursorSortedPlaced } from './utils/cursorAnalysis.js'
import { createUndoStack } from './utils/undoStack.js'
import {
  buildPortableSession, parsePortableSession, applyPortableSession, downloadPortableSession,
  sessionCursorsSlotCount,
} from './utils/sessionPortable.js'
import { downloadPerfetto } from './utils/perfettoExport.js'
import { appIconSvgMarkup } from './utils/htmlReport.js'
import {
  defaultSectionCollapsed,
  defaultStatsPresentation,
  defaultStatsSectionOrder,
  mergeSectionCollapsed,
  normalizeStatsPins,
  normalizeStatsSectionOrder,
  commandPaletteStatsSectionActions,
} from './utils/statsPins.js'
import { computeFindHits, stepFindHitIndex } from './utils/findAnalysis.js'
import {
  AI_TEMPLATE_QUESTIONS,
  aiJumpAnnotationNote,
  appendExplainRegionBounds,
  composeAskEventPrompt,
} from './utils/aiClient.js'
import { traceQualityReport, collectTraceQualityWarnings } from './utils/traceQuality.js'
import {
  shouldOfferUseAsScope,
  formatUseAsScopePrompt,
  multiCursorSpanWarning,
} from './utils/cursorScope.js'
import {
  evidenceNavState,
  pushEvidenceEntry,
  stepEvidenceHistory,
  formatEvidenceInspector,
  SHOW_ON_TIMELINE_LABEL,
} from './utils/evidenceHistory.js'
import {
  buildAnalysisContext,
  isContextStale,
} from './utils/analysisContext.js'
import { isBtfOpenName, loadBtfEntriesFromFile } from './utils/btfLoad.js'
import {
  classifyOpenFiles,
  classifyPickedOpen,
  collectDroppedFiles,
  pickDemoPack,
} from './utils/demoPack.js'
import { createDemoRunner, parseCursorTimes } from './utils/demoRunner.js'
import { discoverVoiceLangs, mergeVoiceLangs, pickVoiceLang } from './utils/demoVoice.js'
import { startDemoRecording } from './utils/demoRecorder.js'
import { acquirePointer, dispatchClickAt, moveTo as moveDemoPointer, releasePointer } from './utils/demoPointer.js'
import { buildZoomPresetOptions } from './utils/zoomPresets.js'
import { IC } from './utils/toolbarIcons.js'
import exampleBtfB64   from 'virtual:example-btf'

// ---- State ---------------------------------------------------------------
const appVersion = __APP_VERSION__
const buildDate  = __BUILD_DATE__
const {
  tabs,
  activeTabId,
  activeTab,
  trace,
  cursors,
  marks,
  pinnedHighlightKey,
  highlightSegment,
  timelineViewport,
  cpuLoadExpanded,
  openTab,
  closeTab,
  cycleTraceTab,
  resetTabForLoad,
  getNavCache,
  setNavCache,
} = useTraceTabs()
const timelinePanelRef = ref(null)
const findPanelRef = ref(null)
const toolbarRef = ref(null)
const statsPanelRef = ref(null)
const aiPanelRef = ref(null)
const marksPanelRef = ref(null)
const leftPaneRef = ref(null)
const cpuLoadPanelRef = ref(null)
const loading    = ref(false)
const loadingPct = ref(0)
const loadingMsg = ref('')
const loadingFileName = ref('')
const loadingPhase = ref('parse')
const loadingPctLabel = computed(() => formatLoadingPct(loadingPct.value))
const loadingCancellable = computed(() => loading.value && isLoadingCancellable(loadingPhase.value))

/** Deterministic placeholder segments for one skeleton lane (row index 1..N). */
function skeletonRow(row) {
  let s = row * 2654435761 % 2147483647
  const rnd = () => ((s = (s * 48271) % 2147483647) / 2147483647)
  const out = []
  let x = rnd() * 4
  let k = 0
  while (x < 97) {
    const w = 3 + rnd() * 14
    out.push({ k: k++, left: +x.toFixed(2), width: +Math.min(w, 98 - x).toFixed(2) })
    x += w + 2 + rnd() * 10
  }
  return out
}
const helpOpen   = ref(false)
const aboutOpen  = ref(false)
const aboutIconSvg = appIconSvgMarkup(72)
const settingsOpen = ref(false)
const inspectorOpen = ref(false)
const inspectorMode = ref('heatmap') // 'heatmap' | 'chord'
const inspectorFocusPair = ref(null)
const analysisOpen = ref(false)
const findingsTriageState = ref(defaultTriageState())
const findingsInvestigateUndo = ref(null)
const paletteOpen = ref(false)
const paletteQuery = ref('')
const paletteIndex = ref(0)
const PALETTE_RECENT_KEY = 'btf-palette-recent'
const PALETTE_FREQUENT_KEY = 'btf-palette-frequent'
const paletteRecent = ref(loadPaletteRecent())
const paletteFrequent = ref(loadPaletteFrequent())

function loadPaletteRecent() {
  try {
    const raw = JSON.parse(localStorage.getItem(PALETTE_RECENT_KEY) || '[]')
    if (!Array.isArray(raw)) return []
    const out = []
    for (const x of raw) {
      const s = String(x || '')
      if (s && !out.includes(s)) out.push(s)
      if (out.length >= COMMAND_PALETTE_RECENT_MAX) break
    }
    return out
  } catch {
    return []
  }
}

function loadPaletteFrequent() {
  try {
    const raw = JSON.parse(localStorage.getItem(PALETTE_FREQUENT_KEY) || '{}')
    if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return {}
    const out = {}
    for (const [k, v] of Object.entries(raw)) {
      const n = Number(v)
      if (Number.isFinite(n)) out[String(k)] = n
    }
    return out
  } catch {
    return {}
  }
}

function bumpPaletteUsage(id) {
  const aid = String(id || '')
  if (!aid) return
  const recent = [aid, ...paletteRecent.value.filter(x => x !== aid)]
    .slice(0, COMMAND_PALETTE_RECENT_MAX)
  const frequent = { ...paletteFrequent.value }
  frequent[aid] = (Number(frequent[aid]) || 0) + 1
  paletteRecent.value = recent
  paletteFrequent.value = frequent
  try {
    localStorage.setItem(PALETTE_RECENT_KEY, JSON.stringify(recent))
    localStorage.setItem(PALETTE_FREQUENT_KEY, JSON.stringify(frequent))
  } catch { /* ignore */ }
}

function paletteIsAvailable(aid) {
  const id = String(aid || '')
  if (id.startsWith('stats-section:')) {
    const ctx = buildPrerequisiteContext({
      trace: trace.value,
      compareTabCount: compareTabs.value.length,
      cursorCount: getPlacedCursors(cursors.value).length,
      aiConfigured: appSettings.aiEnabled !== false,
    })
    return checkPrerequisite('trace', ctx, 'Open a trace first')
  }
  const meta = COMMAND_PALETTE_META[aid] || {}
  const ctx = buildPrerequisiteContext({
    trace: trace.value,
    compareTabCount: compareTabs.value.length,
    cursorCount: getPlacedCursors(cursors.value).length,
    aiConfigured: appSettings.aiEnabled !== false,
  })
  return checkPrerequisite(meta.requires, ctx, meta.disabled)
}
const paletteInput = ref(null)
const compareOpen = ref(false)
const compareInitialA = ref(null)
const compareInitialB = ref(null)
const compareTabs = computed(() => tabs.value.filter(t => t?.trace))
/** Viewport/cursors saved when migration inspector opens; restored by Show all tasks. */
let _heatmapRestoreSnapshot = null
const statsPaused = ref(false)
const rightPanelTab = ref('stats')
const aiTabVisible = computed(
  () => appSettings.showAi !== false && appSettings.aiEnabled !== false,
)

/** Collapsible-card open state for the Marks tab (Cursors / Range / Marks). */
const marksSectionOpen = ref({ cursors: true, range: true, marks: true })
function toggleMarksSection(key) {
  marksSectionOpen.value[key] = !marksSectionOpen.value[key]
}

/** Title shown in the redesigned per-panel header row (icon-rail navigation). */
/** Task count shown in the Legend title — reflects the Core Filter when active. */
const legendTaskCount = computed(() => {
  const tasks = trace.value?.tasks || []
  const keys = timelineOptions.coreFilterKeys
  if (!coreFilterActive(keys, trace.value)) return tasks.length
  return tasks.reduce((n, mk) => n + (taskRunsOnSelectedCore(trace.value, mk, keys) ? 1 : 0), 0)
})

const rightPanelTitle = computed(() => {
  switch (rightPanelTab.value) {
    case 'marks': return 'Marks'
    case 'find': return 'Find'
    case 'legend': return `Legend (${legendTaskCount.value})`
    case 'ai': return 'AI Assistant'
    default: return 'Statistics'
  }
})

function firstVisibleRightPanelTab(s = appSettings) {
  if (s.showStats) return 'stats'
  if (s.showMarks) return 'marks'
  if (s.showFind) return 'find'
  if (s.showLegend) return 'legend'
  if (s.showAi !== false && s.aiEnabled !== false) return 'ai'
  return 'stats'
}

function ensureRightPanelTabVisible(s = appSettings) {
  const tab = rightPanelTab.value
  const ok = (tab === 'stats' && s.showStats)
    || (tab === 'marks' && s.showMarks)
    || (tab === 'find' && s.showFind)
    || (tab === 'legend' && s.showLegend)
    || (tab === 'ai' && s.showAi !== false && s.aiEnabled !== false)
  if (!ok) rightPanelTab.value = firstVisibleRightPanelTab(s)
}

const jumpDialogOpen = ref(false)
const dragOver = ref(false)
const statsSectionHeights = ref({})
let _dragDepth = 0

const findQuery = computed({
  get: () => activeTab.value?.findQuery ?? '',
  set: (v) => { if (activeTab.value) activeTab.value.findQuery = v },
})
const findMode = computed({
  get: () => activeTab.value?.findMode ?? 'contains',
  set: (v) => { if (activeTab.value) activeTab.value.findMode = v },
})
const findHits = computed(() => activeTab.value?.findHits ?? [])
const findHitIdx = computed(() => activeTab.value?.findHitIdx ?? -1)
// Mirror FindPanel.vue counterText: unnavigated (idx < 0) shows position 1.
const findHitPos = computed(() => (findHitIdx.value >= 0 ? findHitIdx.value + 1 : 1))
const findMarkerNs = computed(() => activeTab.value?.findMarkerNs ?? null)
const findError = ref('')

const traceQualityText = computed(() => traceQualitySummary(trace.value))

// ---- Snapshot editor -------------------------------------------------------
const snapshotEditorOpen = ref(false)
const snapshotImageUrl   = ref(null)
const snapshotDownloadFilename = ref('annotated-snapshot.png')

const rightPanelWidth = ref(RIGHT_PANEL_WIDTH)
let _rightPanelResize = null

/** Collapse the right panel to just its icon rail (double-click the seam). */
const RP_COLLAPSED_KEY = 'btf-rp-collapsed'
function loadRpCollapsed() {
  try { return localStorage.getItem(RP_COLLAPSED_KEY) === '1' } catch { return false }
}
const rightPanelCollapsed = ref(loadRpCollapsed())
function setRightPanelCollapsed(next) {
  rightPanelCollapsed.value = next
  try { localStorage.setItem(RP_COLLAPSED_KEY, next ? '1' : '0') } catch { /* private mode */ }
  scheduleRender()
}
function toggleRightPanelCollapsed() {
  setRightPanelCollapsed(!rightPanelCollapsed.value)
}
/** Rail click: switch to the tab and, if collapsed, pop the panel back open. */
function selectRightPanelTab(tab) {
  rightPanelTab.value = tab
  if (rightPanelCollapsed.value) setRightPanelCollapsed(false)
}

/** Focus mode: hide every chrome pane but the timeline (+ toolbar / status bar).
 *  Reached from the command palette; Esc or the floating chip leaves it. */
const FOCUS_MODE_KEY = 'btf-focus-mode'
function loadFocusMode() {
  try { return localStorage.getItem(FOCUS_MODE_KEY) === '1' } catch { return false }
}
const focusMode = ref(loadFocusMode())
function setFocusMode(next) {
  focusMode.value = !!next
  try { localStorage.setItem(FOCUS_MODE_KEY, next ? '1' : '0') } catch { /* private mode */ }
  nextTick(scheduleRender)   // right pane appeared/vanished — re-fit the timeline
}
function toggleFocusMode() { setFocusMode(!focusMode.value) }

const appSettings = reactive(applySettingsToRuntime(loadSettings()))

const cpuLoadPaneHeight = ref(cpuLoadPaneDefaultH())
let _cpuLoadResize = null
let _cpuLoadUserSized = false

function autofitCpuLoadPaneHeight() {
  if (_cpuLoadUserSized || !timelineOptions.showCpuLoad) return
  const tr = trace.value
  if (!tr) {
    cpuLoadPaneHeight.value = cpuLoadPaneDefaultH()
    return
  }
  cpuLoadPaneHeight.value = cpuLoadPreferredPaneHeight(
    tr,
    timelineOptions.viewMode,
    cpuLoadSelectedTask.value,
    cpuLoadExpanded.value,
    {
      migratedOnlyFilter: timelineOptions.migratedOnlyFilter,
      taskFilterKeys: timelineOptions.taskFilterKeys,
      taskFilterText: timelineOptions.taskFilterText,
      coreFilterKeys: timelineOptions.coreFilterKeys,
    },
  )
}

const toastMsg     = ref('')
const toastType    = ref('info')
const toastVisible = ref(false)
let   _toastTimer  = null
const statusBarFlash = ref('')
const statusBarFlashError = ref(false)
let   _statusBarFlashTimer = 0

function showToast(msg, type = 'info') {
  const text = typeof msg === 'object' && msg !== null ? formatErrorToast(msg) : String(msg || '')
  toastMsg.value     = text
  toastType.value    = type
  toastVisible.value = true
  clearTimeout(_toastTimer)
  _toastTimer = setTimeout(() => { toastVisible.value = false }, type === 'error' ? 5000 : 3000)
}

function showParseError(err, fileName = '') {
  console.error('BTF parse error:', err)
  showToast(formatParseError(err, fileName), 'error')
}

const traceQualityDetailsOpen = ref(false)
const evidenceHistory = ref({ entries: [], index: -1 })
const evidenceNav = computed(() => evidenceNavState(evidenceHistory.value))
const evidenceInspectorText = computed(() =>
  formatEvidenceInspector(evidenceNavState(evidenceHistory.value).current))

function panelAnalysisContext(panel, panelFilter = '') {
  const tr = trace.value
  if (!tr) return buildAnalysisContext({ panel })
  const scopeOn = activeTab.value?.scopeToCursors !== false
  const range = getStatsRange(cursors.value, scopeOn)
  const scopeLabel = range ? `C1–C${range.nCursors}` : 'Full Trace'
  let scopeDuration = ''
  if (range) {
    scopeDuration = formatTime(
      range.hi - range.lo, tr.timeScale, appSettings.timeDecimals ?? 3)
  }
  const filters = activeFilterSummaryLabel.value ? [activeFilterSummaryLabel.value] : []
  return buildAnalysisContext({
    traceName: activeTab.value?.name || '',
    scopeLabel,
    scopeDuration,
    filterLabels: filters,
    sampleCount: tr.segments?.length ?? 0,
    cursorCount: getPlacedCursors(cursors.value).length,
    limitToCursors: scopeOn && getPlacedCursors(cursors.value).length >= 2,
    panel,
    panelFilter: panelFilter || '',
  })
}

const findingsAnalysisContext = computed(() => panelAnalysisContext('findings'))
const aiAnalysisContext = computed(() =>
  panelAnalysisContext('ai', appSettings.aiContextMode || ''))
const compareAnalysisContext = computed(() => panelAnalysisContext('compare'))

const findingsContextSnapshot = ref(null)
watch(analysisOpen, (open) => {
  if (open) findingsContextSnapshot.value = { ...findingsAnalysisContext.value }
})
const findingsContextStale = computed(() =>
  isContextStale(findingsContextSnapshot.value, findingsAnalysisContext.value))

function recordEvidenceJump(entry) {
  evidenceHistory.value = pushEvidenceEntry(evidenceHistory.value, entry)
}

function stepEvidenceBack() {
  evidenceHistory.value = stepEvidenceHistory(evidenceHistory.value, -1)
  restoreEvidenceJump(evidenceNavState(evidenceHistory.value).current)
}

function stepEvidenceForward() {
  evidenceHistory.value = stepEvidenceHistory(evidenceHistory.value, 1)
  restoreEvidenceJump(evidenceNavState(evidenceHistory.value).current)
}

function restoreEvidenceJump(entry) {
  if (!entry || entry.time == null) return
  timelinePanelRef.value?.jumpToNs(Number(entry.time))
  syncTimelineViewport()
  if (entry.task) onHighlightClick(String(entry.task))
  if (entry.stats_section) {
    rightPanelTab.value = 'stats'
    nextTick(() => {
      statsPanelRef.value?.applyDemoSections?.({
        id: entry.stats_section, expand: true, scroll: entry.stats_section,
      })
    })
  }
}

const traceQualityReportData = computed(() => traceQualityReport(trace.value))

function onTraceQualityContinue() {
  traceQualityDetailsOpen.value = false
}

const placedCursorTimes = computed(() =>
  (cursors.value || []).filter(c => c != null))

const cursorScopeDismissedCount = ref(null)

const useAsScopePrompt = computed(() => {
  if (!trace.value) return ''
  const limited = activeTab.value?.scopeToCursors !== false
  return shouldOfferUseAsScope(placedCursorTimes.value, { limitToCursors: limited })
    ? formatUseAsScopePrompt(placedCursorTimes.value)
    : ''
})

const showCursorScopeBanner = computed(() => {
  if (!useAsScopePrompt.value) return false
  const n = placedCursorTimes.value.length
  const dismissed = cursorScopeDismissedCount.value
  if (dismissed != null && n === dismissed) return false
  return true
})

const multiCursorWarning = computed(() =>
  multiCursorSpanWarning(placedCursorTimes.value))

/**
 * True when any contextual banner (trace-quality, evidence inspector, cursor
 * scope helper) wants to show. Drives the single unified `.context-strip`
 * wrapper so the three read as one zone instead of a stack of loose bars.
 */
const hasContextStrip = computed(() =>
  (!!traceQualityReportData.value && !traceQualityReportData.value.ok) ||
  !!evidenceInspectorText.value ||
  showCursorScopeBanner.value)

watch(
  () => placedCursorTimes.value.length,
  (n) => {
    // Cursor count changed after dismiss (e.g. C1–C2 → C3) — allow helper again.
    if (cursorScopeDismissedCount.value != null && n !== cursorScopeDismissedCount.value) {
      cursorScopeDismissedCount.value = null
    }
  },
)

watch(useAsScopePrompt, (prompt) => {
  if (!prompt) cursorScopeDismissedCount.value = null
})

function applyCursorsAsScope() {
  if (activeTab.value) activeTab.value.scopeToCursors = true
}

function dismissCursorScopeBanner() {
  cursorScopeDismissedCount.value = placedCursorTimes.value.length
}

function clearAllActiveFilters() {
  for (const chip of activeFilterChips.value) chip.clear()
}

function onAiStatusMessage(payload) {
  const text = String(payload?.text || '').trim()
  if (!text) return
  statusBarFlash.value = text
  statusBarFlashError.value = !!payload?.error
  if (_statusBarFlashTimer) clearTimeout(_statusBarFlashTimer)
  _statusBarFlashTimer = setTimeout(() => {
    statusBarFlash.value = ''
    statusBarFlashError.value = false
    _statusBarFlashTimer = 0
  }, 6000)
}

const demoRunning = ref(false)
const demoPaused = ref(false)
const demoRecording = ref(false)
const demoStatusText = ref('')
const demoMessageText = ref('')
const DEMO_MESSAGE_FADE_MS = 250
const demoNav = ref({ index: 0, total: 0, canPrev: false, canNext: false })
const demoNavReady = ref(false)
const demoVoiceLang = ref('en')
const demoVoiceLangs = ref([])
const demoVoiceLangOptions = computed(() =>
  demoVoiceLangs.value.map(lang => ({ value: lang.id, label: lang.label })))
const DEMO_VOICE_LANG_KEY = 'btf-demo-voice-lang'
const demoFolderPrompt = ref(null)
const zoomPresetValue = ref('fit')
const zoomPresetOptions = ref(buildZoomPresetOptions(NaN, 0))
let _demoRunner = null
let _demoEscAt = 0
let _demoRecorder = null
let _demoNavArmTimer = 0

function disarmDemoNav() {
  demoNavReady.value = false
  if (typeof window !== 'undefined' && _demoNavArmTimer) {
    window.clearTimeout(_demoNavArmTimer)
    _demoNavArmTimer = 0
  }
}

function armDemoNav() {
  disarmDemoNav()
  if (typeof window === 'undefined') {
    demoNavReady.value = true
    return
  }
  // The Open / folder-picker click can mouseup on this bar as it appears.
  _demoNavArmTimer = window.setTimeout(() => {
    _demoNavArmTimer = 0
    if (demoRunning.value) demoNavReady.value = true
  }, 800)
}

function demoSleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms))
}

async function demoWaitLoading() {
  for (let i = 0; i < 600; i++) {
    if (!loading.value) return
    await demoSleep(50)
  }
}

function demoSettingsTab(page) {
  const p = String(page || '').toLowerCase()
  if (p.includes('ai')) return 'ai'
  if (p.includes('display')) return 'display'
  if (p.includes('layout')) return 'layout'
  return 'appearance'
}

function demoCloseOverlays() {
  if (jumpDialogOpen.value) jumpDialogOpen.value = false
  if (analysisOpen.value) analysisOpen.value = false
  closeSettingsDialog()
  if (helpOpen.value) helpOpen.value = false
  if (aboutOpen.value) aboutOpen.value = false
}

async function demoSetPanel(name) {
  const key = String(name || 'stats').trim().toLowerCase()
  if (key === 'ai') {
    if (appSettings.showAi === false) {
      appSettings.showAi = true
      saveSettings(appSettings)
    }
    if (appSettings.aiEnabled === false && !demoRunning.value) {
      openSettingsDialog('ai')
      return
    }
    rightPanelTab.value = 'ai'
  } else if (key === 'find' || key === 'search') {
    focusFindPanel()
  } else if (key === 'marks' || key === 'mark') {
    if (!appSettings.showMarks) {
      appSettings.showMarks = true
      saveSettings(appSettings)
    }
    rightPanelTab.value = 'marks'
  } else if (key === 'legend') {
    if (!appSettings.showLegend) {
      appSettings.showLegend = true
      saveSettings(appSettings)
    }
    rightPanelTab.value = 'legend'
  } else {
    if (!appSettings.showStats) {
      appSettings.showStats = true
      saveSettings(appSettings)
    }
    rightPanelTab.value = 'stats'
  }
  await nextTick()
}

async function demoEnsureStatsPanel() {
  await demoSetPanel('stats')
  for (let i = 0; i < 12; i++) {
    if (statsPanelRef.value?.applyDemoSections) return statsPanelRef.value
    await nextTick()
    await demoSleep(40)
  }
  return statsPanelRef.value
}

function demoPointerBox() {
  const root = document.querySelector('.app')
  if (root?.getBoundingClientRect) return root.getBoundingClientRect()
  return {
    left: 0,
    top: 0,
    width: typeof window !== 'undefined' ? window.innerWidth : 1,
    height: typeof window !== 'undefined' ? window.innerHeight : 1,
  }
}

function demoHost() {
  return {
    toast: showToast,
    setStatus: (text) => { demoStatusText.value = text || '' },
    showMessage: async ({ text }) => {
      demoMessageText.value = String(text || '').trim()
      if (!demoMessageText.value) return
      await nextTick()
      await demoSleep(DEMO_MESSAGE_FADE_MS)
    },
    clearMessage: async ({ animate = true } = {}) => {
      if (!demoMessageText.value) return
      demoMessageText.value = ''
      if (!animate) return
      await nextTick()
      await demoSleep(DEMO_MESSAGE_FADE_MS)
    },
    setDemoPaused: (on) => { demoPaused.value = !!on },
    setDemoVoiceLang: (id) => { if (id) demoVoiceLang.value = id },
    setDemoNav: (nav) => {
      demoNav.value = nav && typeof nav === 'object'
        ? {
            index: Number(nav.index) || 0,
            total: Number(nav.total) || 0,
            canPrev: !!nav.canPrev,
            canNext: !!nav.canNext,
          }
        : { index: 0, total: 0, canPrev: false, canNext: false }
    },
    pressEscape: async () => { demoCloseOverlays() },
    pointerBox: demoPointerBox,
    movePointer: async ({ x, y, duration, signal }) => {
      acquirePointer('demo')
      await moveDemoPointer(x, y, duration, signal)
    },
    clickPointer: async ({ x, y }) => {
      acquirePointer('demo')
      await moveDemoPointer(x, y, 0)
      dispatchClickAt(x, y)
    },
    loadTraceFile: async (file) => {
      const entries = await loadBtfEntriesFromFile(file)
      await onTracesLoaded({ entries, sourceName: file.name })
      await demoWaitLoading()
      await nextTick()
      onFit()
    },
    zoomView: async () => {
      // XML <zoom_view/> = Zoom Full View (toolbar Fit / Ctrl+0).
      onFit()
    },
    fit: async () => {
      // XML <fit_view/> = Zoom fit to C1–Cn when those cursors are placed
      // (toolbar Range / Ctrl+R). Toolbar Fit (Ctrl+0) is onFit / fitToTrace.
      const placed = (cursors.value || []).filter(c => c != null)
      if (placed.length >= 2) {
        timelinePanelRef.value?.zoomToCursorRange?.()
        syncTimelineViewport()
        return
      }
      onFit()
    },
    zoom1to1: async () => { onZoom1to1() },
    zoomIn: async () => { onZoom(0.7) },
    zoomOut: async () => {
      const placed = (cursors.value || []).filter(c => c != null).map(Number)
      if (placed.length >= 2) {
        const mid = (Math.min(...placed) + Math.max(...placed)) / 2
        timelinePanelRef.value?.zoomCenter(1.43, mid)
        syncTimelineViewport()
        return
      }
      onZoom(1.43)
    },
    setViewMode: async (mode) => {
      const key = String(mode || 'task').toLowerCase()
      if (key !== 'task' && key !== 'core') return
      timelineOptions.viewMode = key
      persistTimelineViewPrefs()
      scheduleRender()
      autofitCpuLoadPaneHeight()
      await nextTick()
    },
    setCpuLoad: async (on) => {
      timelineOptions.showCpuLoad = !!on
      persistTimelineViewPrefs()
      autofitCpuLoadPaneHeight()
      await nextTick()
    },
    setPanel: demoSetPanel,
    statsSection: async (payload) => {
      const panel = await demoEnsureStatsPanel()
      await panel?.applyDemoSections?.(payload)
    },
    statsReset: async () => {
      const panel = await demoEnsureStatsPanel()
      await panel?.applyDemoSections?.({
        id: '',
        expand: false,
        collapse_others: true,
        scroll: 'top',
      })
    },
    tickDist: async ({ close } = {}) => {
      const panel = await demoEnsureStatsPanel()
      if (close) await panel?.closePlot?.()
      else await panel?.openTickDistPlot?.()
    },
    highlight: async (task) => { onAiHighlight(task) },
    clearHighlight: async () => { onAiHighlight('') },
    tabNav: async (forward) => { cycleHighlightedSegment(forward !== false) },
    jumpWcet: async (task) => {
      onAiHighlight(task)
      const tr = trace.value
      if (!tr) return
      const candidates = [
        ...(tr.tasks || []),
        ...(tr.tasks || []).map(t => taskMergeKey(t)),
      ]
      const resolved = resolveTaskKey(task, candidates)
      if (!resolved) return
      const mk = taskMergeKey(resolved)
      const segs = tr.segByMergeKey?.get(mk) || []
      let best = null
      let maxDur = -1
      for (const seg of segs) {
        const dur = Number(seg.end) - Number(seg.start)
        if (dur >= maxDur) {
          maxDur = dur
          best = seg
        }
      }
      if (!best) return
      highlightSegment.value = best
      timelineOptions.highlightSegment = best
      timelinePanelRef.value?.zoomToTimeRange(
        best.start, best.end, 0.05, { programmatic: true, animate: true },
      )
      timelinePanelRef.value?.scrollToSegmentIfNeeded(best)
      syncTimelineViewport()
    },
    moveView: async ({ time, timeOmitted, unit, task } = {}) => {
      const tr = trace.value
      if (!tr) return
      const scale = tr.timeScale || 'ns'
      const taskRaw = String(task || '').trim()
      let mk = ''
      if (taskRaw) {
        const candidates = [
          ...(tr.tasks || []),
          ...(tr.tasks || []).map(t => taskMergeKey(t)),
        ]
        const resolved = resolveTaskKey(taskRaw, candidates)
        if (resolved) {
          mk = taskMergeKey(resolved)
          if (timelineOptions.viewMode === 'core' && tr.coreTaskOrder) {
            for (const [core, tasks] of tr.coreTaskOrder.entries()) {
              if ((tasks || []).some(t => taskMergeKey(t) === mk)) {
                timelinePanelRef.value?.expandCore?.(core)
                break
              }
            }
          }
        }
      }
      const emptyTime = time == null || String(time).trim() === ''
      let alignLeft = false
      let ns = null
      if (timeOmitted || emptyTime) {
        if (mk) {
          const segs = tr.segByMergeKey?.get(mk) || []
          if (segs.length) {
            ns = Math.min(...segs.map(s => Number(s.start)))
          } else {
            alignLeft = true
          }
        } else {
          alignLeft = true
        }
      } else {
        const parsed = parseCursorTimes(String(time), unit || '', scale)
        ns = parsed.length ? parsed[0] : null
        if (ns == null || !Number.isFinite(ns) || ns <= tr.timeMin) {
          alignLeft = true
          ns = null
        }
      }
      timelinePanelRef.value?.moveView({
        ns,
        alignLeft,
        taskKey: mk || null,
      })
      syncTimelineViewport()
    },
    setCursors: async ({ times, unit, limit, zoom }) => {
      const scale = trace.value?.timeScale || 'ns'
      const parsed = parseCursorTimes(times, unit, scale)
      const max = appSettings.maxCursors || 4
      const next = Array(max).fill(null)
      parsed.slice(0, max).forEach((t, i) => { next[i] = t })
      cursors.value = next
      if (limit != null) onStatsScopeChange(!!limit)
      await nextTick()
      if (zoom && parsed.length >= 2) {
        await timelinePanelRef.value?.zoomToTimeRange(
          parsed[0], parsed[parsed.length - 1], 0.05,
          { programmatic: true, animate: true },
        )
        syncTimelineViewport()
      }
    },
    clearCursors: async () => { clearCursors() },
    clearBookmarks: async () => {
      onClearBookmarks()
      scheduleSessionSave()
      scheduleRender()
    },
    clearAnnotations: async () => {
      onClearAnnotations()
      scheduleSessionSave()
      scheduleRender()
    },
    setLimit: async (on) => { onStatsScopeChange(!!on) },
    zoomRange: async ({ start, end, times, unit }) => {
      const scale = trace.value?.timeScale || 'ns'
      let lo
      let hi
      if (start && end) {
        const t = parseCursorTimes(`${start},${end}`, unit, scale)
        lo = t[0]
        hi = t[1]
      } else {
        const t = parseCursorTimes(times, unit, scale)
        lo = t[0]
        hi = t[t.length - 1]
      }
      if (lo == null || hi == null) return
      timelinePanelRef.value?.zoomToTimeRange(
        lo, hi, 0.05, { programmatic: true, animate: true },
      )
      syncTimelineViewport()
    },
    openAnalysis: async ({ close } = {}) => {
      analysisOpen.value = !close
      await nextTick()
    },
    openHeatmap: async ({ close, mode } = {}) => {
      if (close) {
        inspectorOpen.value = false
        await nextTick()
        return
      }
      inspectorMode.value = mode === 'chord' ? 'chord' : 'heatmap'
      inspectorFocusPair.value = null
      inspectorOpen.value = true
      await nextTick()
    },
    find: async ({ query, next }) => {
      await demoSetPanel('find')
      findQuery.value = query || ''
      await nextTick()
      recomputeFind()
      if (query && next) stepFind(true)
    },
    openSettings: async (spec) => {
      const close = !!(spec && typeof spec === 'object' && spec.close)
      if (close) {
        closeSettingsDialog()
        await nextTick()
        return
      }
      const page = spec && typeof spec === 'object'
        ? (spec.page || spec.name)
        : spec
      openSettingsDialog(demoSettingsTab(page))
      await nextTick()
    },
    closeSettings: async () => {
      closeSettingsDialog()
      await nextTick()
    },
  }
}

function stopDemo() {
  _demoRunner?.abort()
  _demoRunner = null
  demoRunning.value = false
  demoPaused.value = false
  demoStatusText.value = ''
  demoMessageText.value = ''
  demoNav.value = { index: 0, total: 0, canPrev: false, canNext: false }
  demoVoiceLangs.value = []
  disarmDemoNav()
  _demoEscAt = 0
  releasePointer('demo')
}

let _demoSkipAt = 0

function onDemoPrev(e) {
  if (e && e.isTrusted === false) return
  if (e && e.button != null && e.button !== 0) return
  if (!demoRunning.value || !demoNavReady.value || !demoNav.value.canPrev) return
  const now = Date.now()
  if (now - _demoSkipAt < 400) return
  _demoSkipAt = now
  e?.preventDefault?.()
  e?.stopPropagation?.()
  _demoRunner?.skipPrev?.()
}

function onDemoNext(e) {
  if (e && e.isTrusted === false) return
  if (e && e.button != null && e.button !== 0) return
  if (!demoRunning.value || !demoNavReady.value || !demoNav.value.canNext) return
  const now = Date.now()
  if (now - _demoSkipAt < 400) return
  _demoSkipAt = now
  e?.preventDefault?.()
  e?.stopPropagation?.()
  _demoRunner?.skipNext?.()
}

function onDemoPause(e) {
  if (e && e.isTrusted === false) return
  if (e && e.button != null && e.button !== 0) return
  if (!demoRunning.value || !demoNavReady.value) return
  e?.preventDefault?.()
  e?.stopPropagation?.()
  _demoRunner?.togglePause?.()
}

function onDemoVoiceLangPick(id) {
  const v = String(id || '').trim()
  if (!v || !demoRunning.value) return
  demoVoiceLang.value = v
  try { localStorage.setItem(DEMO_VOICE_LANG_KEY, v) } catch { /* ignore */ }
  _demoRunner?.setVoiceLang?.(v)
}

function onDemoFolderNeeded(prompt) {
  demoFolderPrompt.value = {
    xmlName: prompt?.xmlName || 'demo.xml',
    traceName: prompt?.traceName || '',
    startIn: prompt?.startIn || null,
    files: prompt?.files || null,
  }
}

async function onOpenDemoPackFolder() {
  const startIn = demoFolderPrompt.value?.startIn || null
  try {
    const pack = await pickDemoPack({ startIn })
    if (!pack) return
    demoFolderPrompt.value = null
    await startDemoPack(pack)
  } catch (err) {
    showToast(err?.message || 'Failed to open demo pack', 'error')
  }
}

async function startDemoPack(pack) {
  if (!pack) return
  if (!pack.traceFile) {
    showToast('Demo pack has no .btf / .btf.gz trace', 'error')
    return
  }
  stopDemo()
  const langs = mergeVoiceLangs(
    pack.parsed?.languages,
    discoverVoiceLangs(pack.files),
  )
  demoVoiceLangs.value = langs.list
  let preferred = ''
  try { preferred = localStorage.getItem(DEMO_VOICE_LANG_KEY) || '' } catch { /* ignore */ }
  if (!preferred && typeof navigator !== 'undefined') {
    preferred = navigator.language || navigator.userLanguage || ''
  }
  const picked = pickVoiceLang(
    preferred,
    langs.list.map(l => l.id),
    langs.defaultId,
  )
  demoVoiceLang.value = picked
  const runner = createDemoRunner(demoHost(), pack, { aiWaitCapSec: 4, voiceLang: picked })
  _demoRunner = runner
  demoRunning.value = true
  demoPaused.value = false
  armDemoNav()
  try {
    await runner.run()
    if (!runner.aborted) showToast('Demo finished', 'info')
  } catch (err) {
    console.error('Demo XML failed:', err)
    showToast(err?.message || 'Demo failed', 'error')
  } finally {
    if (_demoRunner === runner) {
      _demoRunner = null
      demoRunning.value = false
      demoPaused.value = false
      demoStatusText.value = ''
      demoNav.value = { index: 0, total: 0, canPrev: false, canNext: false }
      disarmDemoNav()
      releasePointer('demo')
    }
  }
}

async function onToggleRecord() {
  if (demoRecording.value) {
    const rec = _demoRecorder
    _demoRecorder = null
    demoRecording.value = false
    try {
      await rec?.stop()
      showToast('Recording saved', 'info')
    } catch (err) {
      showToast(err?.message || 'Failed to save recording', 'error')
    }
    return
  }
  try {
    showToast('Share this tab and enable tab audio so narration is captured', 'info')
    _demoRecorder = await startDemoRecording()
    demoRecording.value = true
    _demoRecorder.stream?.getVideoTracks()?.[0]?.addEventListener('ended', async () => {
      if (!demoRecording.value) return
      const rec = _demoRecorder
      _demoRecorder = null
      demoRecording.value = false
      try {
        await rec?.stop()
        showToast('Recording saved', 'info')
      } catch (err) {
        showToast(err?.message || 'Failed to save recording', 'error')
      }
    })
  } catch (err) {
    if (err?.name === 'NotAllowedError' || err?.name === 'AbortError') return
    showToast(err?.message || 'Screen recording is not available', 'error')
  }
}

const timelineOptions = reactive({
  viewMode:        VIEW_MODE,
  darkMode:        DARK_MODE,
  showGrid:        SHOW_GRID,
  showSti:         SHOW_STI,
  showCpuLoad:     SHOW_CPU_LOAD,
  stiLogScale:     STI_LOG_SCALE,
  orientation:     ORIENTATION,
  highlightKey:    null,
  marks:           [],
  highlightSegment: null,
  highlightInterval: null,
  selectedMarkId:  null,
  migratedOnlyFilter: false,
  taskFilterKeys:     null,
  taskFilterText:     '',
  heatmapFilterLabel: null,
  coreFilterKeys:     null,
  lockedTaskKey:   null,
  showHoverHighlight: HOVER_HIGHLIGHT,
  layoutRev:       0,
})

// Keep colors.js's dark-mode tracking in sync so the colorblind palette can
// swap its black entry for white (pure black is invisible on a dark bg).
watch(() => timelineOptions.darkMode, (v) => setDarkMode(v), { immediate: true })

function tabUndoStack(tab = activeTab.value) {
  if (!tab) return null
  if (!tab._undoStack) tab._undoStack = createUndoStack()
  return tab._undoStack
}

function syncTimelineOptionsFromSettings(s = appSettings) {
  timelineOptions.darkMode = s.darkMode
  timelineOptions.showGrid = s.showGrid
  timelineOptions.showSti = s.showSti
  timelineOptions.showCpuLoad = s.showCpuLoad
  timelineOptions.showHoverHighlight = s.hoverHighlight
  timelineOptions.viewMode = s.viewMode === 'core' ? 'core' : 'task'
  timelineOptions.orientation = s.orientation === 'v' ? 'v' : 'h'
  timelineOptions.stiLogScale = !!s.stiLogScale
  timelineOptions.layoutRev += 1
  ensureRightPanelTabVisible(s)
}

/** Persist toolbar/hotkey view prefs that live in appSettings. */
function persistTimelineViewPrefs() {
  let dirty = false
  if (appSettings.darkMode !== !!timelineOptions.darkMode) {
    appSettings.darkMode = !!timelineOptions.darkMode
    dirty = true
  }
  if (appSettings.showGrid !== !!timelineOptions.showGrid) {
    appSettings.showGrid = !!timelineOptions.showGrid
    dirty = true
  }
  if (appSettings.showSti !== (timelineOptions.showSti !== false)) {
    appSettings.showSti = timelineOptions.showSti !== false
    dirty = true
  }
  if (appSettings.showCpuLoad !== !!timelineOptions.showCpuLoad) {
    appSettings.showCpuLoad = !!timelineOptions.showCpuLoad
    dirty = true
  }
  if (appSettings.hoverHighlight !== !!timelineOptions.showHoverHighlight) {
    appSettings.hoverHighlight = !!timelineOptions.showHoverHighlight
    dirty = true
  }
  const viewMode = timelineOptions.viewMode === 'core' ? 'core' : 'task'
  if (appSettings.viewMode !== viewMode) {
    appSettings.viewMode = viewMode
    dirty = true
  }
  const orientation = timelineOptions.orientation === 'v' ? 'v' : 'h'
  if (appSettings.orientation !== orientation) {
    appSettings.orientation = orientation
    dirty = true
  }
  if (appSettings.stiLogScale !== !!timelineOptions.stiLogScale) {
    appSettings.stiLogScale = !!timelineOptions.stiLogScale
    dirty = true
  }
  if (dirty) saveSettings(appSettings)
}

function onToolbarOptionsUpdate(v) {
  Object.assign(timelineOptions, v || {})
  persistTimelineViewPrefs()
}

/** Show Statistics when opening a new trace (desktop focuses Stats on load only). */
function focusStatisticsPanel(force = false) {
  if (!appSettings.showStats) return
  if (force) rightPanelTab.value = 'stats'
}

function applyAppSettings(next, { silent = false, persist = true } = {}) {
  const runtime = applySettingsToRuntime(next)
  Object.assign(appSettings, runtime)
  // New object/array refs so StatisticsPanel watches apply expand/collapse + pins.
  appSettings.statsSectionCollapsed = mergeSectionCollapsed(runtime.statsSectionCollapsed)
  appSettings.statsPinnedSections = [...(runtime.statsPinnedSections || [])]
  appSettings.statsSectionOrder = [...(runtime.statsSectionOrder || [])]
  setColorblindMode(appSettings.colorblindSafe)
  syncTimelineOptionsFromSettings()
  resizeTabCursors(tabs.value, appSettings.maxCursors)
  if (persist) saveSettings(appSettings)
  scheduleRender()
  autofitCpuLoadPaneHeight()
  if (!silent) showToast('Settings saved', 'info')
}

let settingsRevertSnapshot = null
const settingsInitialTab = ref('appearance')

function openSettingsDialog(tab = 'appearance') {
  helpOpen.value = false
  aboutOpen.value = false
  settingsInitialTab.value = (typeof tab === 'string' && tab) ? tab : 'appearance'
  settingsRevertSnapshot = normalizeSettings(appSettings)
  settingsOpen.value = true
}

function closeSettingsDialog() {
  settingsOpen.value = false
  const snap = settingsRevertSnapshot
  settingsRevertSnapshot = null
  if (!snap) return
  try {
    applyAppSettings(snap, { silent: true, persist: false })
  } catch { /* keep the dialog closed even if revert fails */ }
}

function onSettingsPreview(next) {
  applyAppSettings(next, { silent: true, persist: false })
}

function onSettingsCancel() {
  closeSettingsDialog()
}

function onSettingsSave(next, meta = {}) {
  const resetLayout = !!(meta.resetLayout || next?.resetLayout)
  applyAppSettings(next, { silent: false, persist: true })
  if (resetLayout) {
    const { pins, collapsed } = defaultStatsPresentation(trace.value)
    appSettings.statsPinnedSections = pins
    appSettings.statsSectionOrder = defaultStatsSectionOrder()
    appSettings.statsSectionCollapsed = collapsed
    statsSectionHeights.value = {}
    saveSettings(appSettings)
    scheduleSessionSave()
  }
  settingsRevertSnapshot = null
  settingsOpen.value = false
}
const cpuLoadHoverTime = ref(null)

const cpuLoadSelectedTask = computed(() => selectedTaskFromHighlight({
  pinnedHighlightKey: pinnedHighlightKey.value,
  highlightSegment: highlightSegment.value,
}))

function saveFiltersToActiveTab(tab = activeTab.value) {
  if (!tab) return
  tab.taskFilterText = timelineOptions.taskFilterText || ''
  tab.migratedOnlyFilter = !!timelineOptions.migratedOnlyFilter
  tab.taskFilterKeys = timelineOptions.taskFilterKeys ?? null
  tab.heatmapFilterLabel = timelineOptions.heatmapFilterLabel ?? null
  tab.coreFilterKeys = timelineOptions.coreFilterKeys ?? null
}

function syncFiltersFromTab(tab) {
  timelineOptions.taskFilterText = tab?.taskFilterText ?? ''
  timelineOptions.migratedOnlyFilter = !!tab?.migratedOnlyFilter
  timelineOptions.taskFilterKeys = tab?.taskFilterKeys ?? null
  timelineOptions.heatmapFilterLabel = tab?.heatmapFilterLabel ?? null
  timelineOptions.coreFilterKeys = tab?.coreFilterKeys ?? null
}

/** Saved per-trace state from localStorage (restored when trace opens / session reload). */
let _savedTabStateByTraceName = {}

// ---- Segment navigation cache (built lazily per trace) -------------------
let _navCache = null   // mirrored to active tab via getNavCache/setNavCache

function _sameSegment(a, b) {
  if (!a || !b) return false
  return a.start === b.start && a.end === b.end && a.task === b.task && a.core === b.core
}

function _segmentCmp(a, b) {
  if (a.start !== b.start) return a.start - b.start
  if (a.end !== b.end) return a.end - b.end
  const t = a.task.localeCompare(b.task)
  if (t !== 0) return t
  return a.core.localeCompare(b.core)
}

function _ensureNavCache() {
  if (!trace.value || !activeTab.value) return
  const cached = getNavCache(activeTab.value)
  if (cached?.trace === trace.value) {
    _navCache = cached
    return
  }
  const tickMk = taskMergeKey('TICK')
  const isCoreEntity = (name) => typeof name === 'string' && name.startsWith('Core_')
  _navCache = {
    trace: trace.value,
    segs: [...trace.value.segments]
      .filter(s => !!s.task)
      .filter(s => !isCoreEntity(s.task))
      .filter(s => taskMergeKey(s.task) !== tickMk)
      .sort(_segmentCmp),
  }
  setNavCache(activeTab.value, _navCache)
}

/** Earliest cursor / bookmark / annotation time visible in the current
 * viewport's time range, or null if none are visible there. */
function _earliestMarkerInViewport() {
  const vp = timelinePanelRef.value?.getViewport?.()
  if (!vp) return null
  const lo = Math.min(vp.timeStart, vp.timeEnd)
  const hi = Math.max(vp.timeStart, vp.timeEnd)
  const times = []
  for (const c of cursors.value) {
    if (c != null && c >= lo && c <= hi) times.push(c)
  }
  for (const m of marks.value) {
    if (m.ns >= lo && m.ns <= hi) times.push(m.ns)
  }
  return times.length ? Math.min(...times) : null
}

/** Tab / Shift+Tab: select the next/previous task segment.
 *
 * This only decides the *first stop*: when nothing is selected yet,
 * Tab/Shift+Tab jump to the first segment at or after the earliest cursor /
 * bookmark / annotation visible in the current viewport (in that priority
 * order), or - if none of those are visible - the first segment at or
 * after the viewport's start edge (both keys behave the same here, since
 * there is no current segment to move away from). Once a task is
 * selected, every further Tab/Shift+Tab press keeps cycling to the
 * next/previous task exactly as before (same-task repeats are still
 * skipped).
 */
function cycleHighlightedSegment(forward) {
  if (!trace.value) return
  _ensureNavCache()
  const segs = _navCache?.segs
  if (!segs || segs.length === 0) return

  const cur      = highlightSegment.value
  const isCoreView = timelineOptions.viewMode === 'core'
  const curTaskKey = cur
    ? taskMergeKey(cur.task)
    : (timelineOptions.highlightKey ?? pinnedHighlightKey.value ?? null)

  // Core view scoping (mirrors Desktop's _cycle_highlighted_task): an
  // exact segment's own core wins; else, if a task is only pinned via the
  // legend (no exact segment yet), scope to the first core whose task list
  // still has that task under the active text filter; else fall back to
  // the core at the viewport center.
  const textQ = normalizeTaskFilterText(timelineOptions.taskFilterText)
  let curCore = cur?.core ?? null
  if (curCore == null && isCoreView && curTaskKey != null) {
    for (const c of trace.value.coreNames || []) {
      const tasks = trace.value.coreTaskOrder?.get(c) || []
      if (tasks.some(t => taskMergeKey(t) === curTaskKey
        && rawTaskNameMatchesTextFilter(trace.value, t, textQ))) { curCore = c; break }
    }
  }
  if (curCore == null && isCoreView) {
    curCore = timelinePanelRef.value?.getCoreAtViewportCenter?.() ?? null
  }
  let navSegs = (isCoreView && curCore)
    ? segs.filter(s => s.core === curCore)
    : segs
  // Active filters (search text / migrated-only / heatmap selection) must
  // hide their non-matching segments from Tab/Shift+Tab too, exactly as
  // they hide them from the rendered timeline (Desktop: task_ok() inside
  // _pick_next_task_by_time via _task_merge_key_matches_filter).
  navSegs = navSegs.filter(s => taskPassesRowFilter(
    trace.value, taskMergeKey(s.task),
    timelineOptions.migratedOnlyFilter, timelineOptions.taskFilterKeys,
    timelineOptions.taskFilterText, timelineOptions.coreFilterKeys,
  ))
  // Core view shows one row per core, so also drop segments on hidden cores.
  if (isCoreView && timelineOptions.coreFilterKeys?.length) {
    const coreSet = new Set(timelineOptions.coreFilterKeys)
    navSegs = navSegs.filter(s => coreSet.has(s.core))
  }
  if (!navSegs || navSegs.length === 0) return

  let idx = -1
  if (cur) idx = navSegs.findIndex(s => _sameSegment(s, cur))

  const pickForwardFrom = (startIdx) => {
    let i = startIdx
    for (let step = 0; step < navSegs.length; step++) {
      const seg = navSegs[i]
      if (!curTaskKey || taskMergeKey(seg.task) !== curTaskKey) return seg
      i = (i + 1) % navSegs.length
    }
    return navSegs[startIdx]
  }

  const pickBackwardFrom = (startIdx) => {
    let i = startIdx
    for (let step = 0; step < navSegs.length; step++) {
      const seg = navSegs[i]
      if (!curTaskKey || taskMergeKey(seg.task) !== curTaskKey) return seg
      i = (i - 1 + navSegs.length) % navSegs.length
    }
    return navSegs[startIdx]
  }

  // A task is already selected - either an exact segment, or just pinned
  // via the legend (curTaskKey set but no exact segment picked yet): keep
  // the pre-existing next/previous-task cycling, unchanged.
  let next
  if (curTaskKey != null) {
    const centerNs = timelinePanelRef.value?.getViewportCenter?.() ?? 0
    if (forward) {
      if (idx >= 0) {
        let ni = (idx + 1) % navSegs.length
        next = pickForwardFrom(ni)
      } else {
        const refNs = cur?.start ?? centerNs
        let ni = navSegs.findIndex(s => s.start >= refNs)
        if (ni < 0) ni = 0
        next = pickForwardFrom(ni)
      }
    } else if (idx >= 0) {
      let pi = (idx - 1 + navSegs.length) % navSegs.length
      next = pickBackwardFrom(pi)
    } else {
      const refNs = cur?.start ?? centerNs
      let pi = navSegs.length - 1
      for (let i = navSegs.length - 1; i >= 0; i--) {
        if (navSegs[i].start <= refNs) { pi = i; break }
      }
      next = pickBackwardFrom(pi)
    }
  } else {
    // Nothing selected at all yet: anchor on the earliest visible cursor /
    // bookmark / annotation, falling back to the viewport start edge. Tab
    // and Shift+Tab behave the same here.
    const anchorNs = _earliestMarkerInViewport()
      ?? timelinePanelRef.value?.getViewport?.()?.timeStart ?? 0
    let ni = navSegs.findIndex(s => s.start >= anchorNs)
    if (ni < 0) ni = 0
    next = pickForwardFrom(ni)
  }

  highlightSegment.value = next
  timelineOptions.highlightSegment = next
  timelinePanelRef.value?.scrollToSegmentIfNeeded(next)
}

function onSegmentClick(seg) {
  const cur = highlightSegment.value
  const isSame = cur && cur.start === seg.start && cur.end === seg.end && cur.task === seg.task
  if (isSame) {
    highlightSegment.value = null
    timelineOptions.highlightSegment = null
    timelineOptions.highlightInterval = null
    timelineOptions.highlightKey = null
    timelineOptions.lockedTaskKey = null
    pinnedHighlightKey.value = null
  } else {
    highlightSegment.value = seg
    timelineOptions.highlightSegment = seg
    timelineOptions.highlightInterval = null
    const mk = taskMergeKey(seg.task)
    timelineOptions.highlightKey = mk
    timelineOptions.lockedTaskKey = mk
    pinnedHighlightKey.value = null
  }
  scheduleRender()
  autofitCpuLoadPaneHeight()
}

watch(marks, (m) => {
  timelineOptions.marks = m
}, { deep: true })

watch(activeTabId, (newId, oldId) => {
  let linkedRel = null
  if (oldId != null && appSettings.linkCompareViewports && tabs.value.length >= 2) {
    const leaving = tabs.value.find(t => t.id === oldId)
    const trLeave = leaving?.trace
    const vp = leaving?.timelineViewport
    if (trLeave && vp && Number.isFinite(vp.t0) && Number.isFinite(vp.t1)) {
      const span = Math.max(1, trLeave.timeMax - trLeave.timeMin)
      linkedRel = {
        lo: (vp.t0 - trLeave.timeMin) / span,
        hi: (vp.t1 - trLeave.timeMin) / span,
      }
    }
  }
  if (oldId != null) {
    inspectorOpen.value = false
    inspectorFocusPair.value = null
    analysisOpen.value = false
    findingsTriageState.value = defaultTriageState()
    findingsInvestigateUndo.value = null
    const leaving = tabs.value.find(t => t.id === oldId)
    if (leaving) saveFiltersToActiveTab(leaving)
  }
  const tab = activeTab.value
  const lockKey = selectedTaskFromHighlight(tab)
  timelineOptions.highlightKey = lockKey
  timelineOptions.highlightSegment = tab?.highlightSegment ?? null
  timelineOptions.highlightInterval = null
  timelineOptions.lockedTaskKey = lockKey
  syncFiltersFromTab(tab)
  _navCache = tab ? getNavCache(tab) : null
  nextTick(() => {
    if (linkedRel && tab?.trace) {
      const span = Math.max(1, tab.trace.timeMax - tab.trace.timeMin)
      const lo = tab.trace.timeMin + linkedRel.lo * span
      const hi = tab.trace.timeMin + linkedRel.hi * span
      if (hi > lo) {
        timelinePanelRef.value?.zoomToTimeRange(lo, hi, 0, { programmatic: true })
      }
    } else {
      applyTimelineViewport()
    }
    timelineOptions.layoutRev += 1
    scheduleRender()
    autofitCpuLoadPaneHeight()
  })
  aiPanelRef.value?.refreshCoreAvailability?.()
})

watch(
  () => [
    trace.value,
    timelineOptions.viewMode,
    timelineOptions.showCpuLoad,
    cpuLoadExpanded.value,
    cpuLoadSelectedTask.value,
    highlightSegment.value,
    appSettings.cpuLoadRowH,
    timelineOptions.migratedOnlyFilter,
    timelineOptions.taskFilterKeys,
    timelineOptions.taskFilterText,
    timelineOptions.coreFilterKeys,
  ],
  () => nextTick(() => autofitCpuLoadPaneHeight()),
)

watch(
  () => timelineOptions.viewMode,
  () => {
    timelineOptions.highlightInterval = null
    scheduleRender()
  },
)

watch(
  () => ({
    viewMode: timelineOptions.viewMode,
    orientation: timelineOptions.orientation,
    showGrid: timelineOptions.showGrid,
    showSti: timelineOptions.showSti,
    showCpuLoad: timelineOptions.showCpuLoad,
    darkMode: timelineOptions.darkMode,
    taskFilterText: timelineOptions.taskFilterText,
    taskFilterKeys: timelineOptions.taskFilterKeys,
    heatmapFilterLabel: timelineOptions.heatmapFilterLabel,
    migratedOnlyFilter: timelineOptions.migratedOnlyFilter,
    coreFilterKeys: timelineOptions.coreFilterKeys,
  }),
  scheduleSessionSave,
)

watch(marks, () => {
  if (findQuery.value?.trim()) recomputeFind()
}, { deep: true })

// ---- Trace info for toolbar -----------------------------------------------
const traceInfo = computed(() => {
  if (!trace.value) return ''
  const t = trace.value
  return `${t.meta?.creator || ''} · ${t.tasks.length}T · ${t.segments.length.toLocaleString()} segs`
})

const heatmapEnabled = computed(() => traceIsMultiCore(trace.value))
const rangeEnabled = computed(() => getPlacedCursors(cursors.value).length >= 2)
const limitOn = computed(() =>
  !!(activeTab.value?.scopeToCursors && rangeEnabled.value))
const zoomOutEnabled = computed(() => !!trace.value && zoomPresetValue.value !== 'fit')

const analysisFindings = computed(() => {
  const tr = trace.value
  if (!tr) return []
  const scopeOn = activeTab.value?.scopeToCursors !== false
  const range = getStatsRange(cursors.value, scopeOn)
  return collectTraceAnalysisFindings(
    tr,
    range?.lo ?? null,
    range?.hi ?? null,
    appSettings,
  )
})

const analysisScopeLabel = computed(() => {
  const scopeOn = activeTab.value?.scopeToCursors !== false
  const range = getStatsRange(cursors.value, scopeOn)
  return range ? ` (C1–C${range.nCursors})` : ''
})

const analysisQuality = computed(() => collectTraceQualityWarnings(trace.value))
const findingHits = computed(() => {
  if (!appSettings.showIncidentOverlay) return []
  const fromFindings = findingOverlayTimes(analysisFindings.value || [])
  let ux = []
  if (trace.value) {
    const scopeOn = activeTab.value?.scopeToCursors !== false
    const range = getStatsRange(cursors.value, scopeOn)
    ux = harvestUxEvents(trace.value, range?.lo ?? null, range?.hi ?? null)
  }
  return mergeIncidentOverlayTimes(ux, fromFindings, {
    includeAnomalies: true,
    limit: 120,
  })
})
const taskInspectorText = computed(() => taskInspectorLine(
  selectedTaskFromHighlight({
    highlightSegment: highlightSegment.value,
    pinnedHighlightKey: pinnedHighlightKey.value,
  }) || '',
  analysisQuality.value,
))
const paletteHits = computed(() => {
  const q = String(paletteQuery.value || '').trim()
  const actions = [...COMMAND_PALETTE_ACTIONS]
  // Synthetic Stats section jumps — only when filtering so idle list stays short.
  if (q) actions.push(...commandPaletteStatsSectionActions())
  return commandPaletteRank(
    actions,
    paletteQuery.value,
    paletteRecent.value,
    paletteFrequent.value,
    paletteIsAvailable,
  )
})
watch(paletteQuery, () => { paletteIndex.value = 0 })

const cursorRangeStats = computed(() =>
  computeCursorRangeStats(trace.value, cursors.value, appSettings.timeDecimals))

/** "C1–C3" label for the current cursor-defined Scope (null when Scope is Full Trace). */
const scopeCursorLabel = computed(() => {
  const sorted = cursorSortedPlaced(cursors.value)
  if (sorted.length < 2) return null
  const first = sorted[0].slotIndex + 1
  const last = sorted[sorted.length - 1].slotIndex + 1
  return first === last ? `C${first}` : `C${first}–C${last}`
})

const statusRangeLine = computed(() =>
  formatStatusRangeLine(cursorRangeStats.value, scopeCursorLabel.value))

/** Active analytical Filters shown as removable chips in the status bar (Step-1 item 3). */
const activeFilterChips = computed(() => {
  const chips = []
  if (timelineOptions.taskFilterKeys?.length) {
    chips.push({
      key: 'migration',
      label: `Migration: ${timelineOptions.heatmapFilterLabel || `${timelineOptions.taskFilterKeys.length} tasks`}`,
      clear: clearHeatmapTaskFilter,
    })
  }
  if (timelineOptions.migratedOnlyFilter) {
    chips.push({
      key: 'task',
      label: 'Task: Migrated only',
      clear: () => onMigratedFilterChange(false),
    })
  }
  if (coreFilterActive(timelineOptions.coreFilterKeys, trace.value)) {
    const total = trace.value?.coreNames?.length ?? 0
    chips.push({
      key: 'core',
      label: `Core: ${timelineOptions.coreFilterKeys.length} of ${total}`,
      clear: clearCoreFilter,
    })
  }
  return chips
})

const activeFilterSummaryLabel = computed(() =>
  activeFilterChips.value.length ? activeFilterChips.value.map(c => c.label).join(', ') : null)

const zoomStatus = computed(() => zoomStatusFromViewport(
  timelineViewport.value,
  trace.value?.timeScale || 'ns',
  timelineOptions.orientation || 'h',
))

// ---- File loading (via Web Worker; fallback to main-thread for file:// origins) --
let _parseWorker = null
/** @type {{ text: string, name: string }[]} */
const _pendingTraceLoads = []
/** @type {Promise<void>|null} */
let _drainPromise = null

function onTraceReading({ name }) {
  // Show the loading overlay immediately while FileReader is still reading the file
  if (_parseWorker) { _parseWorker.terminate(); _parseWorker = null }
  loading.value         = true
  loadingPhase.value    = 'read'
  loadingPct.value      = 1
  loadingMsg.value      = LOADING_STAGES.reading
  loadingFileName.value = name || 'trace.btf'
}

/** Clear the load overlay after a read/decompress failure (empty ZIP, etc.). */
function dismissLoadingOverlay() {
  if (_parseWorker) { _parseWorker.terminate(); _parseWorker = null }
  loading.value    = false
  loadingPhase.value = 'parse'
  loadingPct.value = 0
  loadingMsg.value = ''
}

function cancelLoading() {
  if (_parseWorker) {
    _parseWorker.terminate()
    _parseWorker = null
  }
  _pendingTraceLoads.length = 0
  dismissLoadingOverlay()
  showToast('Load cancelled', 'info')
}

function onFileError(message) {
  dismissLoadingOverlay()
  showToast(message, 'error')
}

function finishTraceLoadTab(tab) {
  const lockKey = selectedTaskFromHighlight(tab)
  timelineOptions.highlightKey = lockKey
  timelineOptions.lockedTaskKey = lockKey
  timelineOptions.showCpuLoad = true
  timelineOptions.highlightSegment = tab.highlightSegment ?? null
  loading.value    = false
  loadingPct.value = 0
  loadingMsg.value = ''
}

function paintLoadingProgress(pct, msg) {
  loadingPhase.value = 'parse'
  loadingPct.value = pct
  loadingMsg.value = formatLoadingMessage(msg)
}

async function flushLoadingProgress(pct, msg) {
  paintLoadingProgress(pct, msg)
  await new Promise(resolve => requestAnimationFrame(resolve))
}

async function attachParsedTrace(name, packedOrTrace, {
  savedState = null, fromSession = false, sourceText = null,
} = {}) {
  paintLoadingProgress(100, LOADING_STAGES.opening)
  loadingPhase.value = 'open'
  try {
    const { unpackTrace } = await import('./parser/tracePack.js')
    const trace = packedOrTrace?.segStore ? packedOrTrace : unpackTrace(packedOrTrace)
    const tab = openTab(name || 'trace.btf')
    resizeTabCursors(tabs.value, appSettings.maxCursors)
    resetTabForLoad(tab)
    tab._undoStack = null
    const restored = savedState ?? _savedTabStateByTraceName[name]
    if (restored) applyTabState(tab, restored)
    tab.taskFilterKeys = null
    tab.heatmapFilterLabel = null
    syncFiltersFromTab(tab)
    inspectorOpen.value = false
    inspectorFocusPair.value = null
    _heatmapRestoreSnapshot = null
    timelineOptions.highlightInterval = null

    tab.trace = markRaw(trace)
    if (typeof sourceText === 'string' && sourceText) {
      tab.sourceText = sourceText
    }
    // Fresh open with no saved pins: SMP-aware Core Utilisation presentation.
    // Session restore and user pins from localStorage keep their layout.
    if (!fromSession && !(appSettings.statsPinnedSections || []).length) {
      const { pins, collapsed } = defaultStatsPresentation(trace)
      appSettings.statsPinnedSections = pins
      appSettings.statsSectionCollapsed = collapsed
      saveSettings(appSettings)
    }
    if (trace.meta?._versionWarning) {
      showToast(trace.meta._versionWarning, 'info')
    }
    await nextTick()

    _cpuLoadUserSized = false
    finishTraceLoadTab(tab)
    focusStatisticsPanel(!fromSession)
    await nextTick()
    applyTimelineViewport()
    scheduleRender()
    autofitCpuLoadPaneHeight()

    putTrace(name, packedOrTrace).catch(() => {})
    scheduleSessionSave()

    setTimeout(() => {
      import('./utils/statsWorkerClient.js')
        .then(m => m.registerTraceWithStatsWorker(trace))
        .catch(() => {})
    }, 0)
  } catch (err) {
    loading.value = false
    loadingPct.value = 0
    loadingMsg.value = ''
    throw err
  }
}

async function parseTraceOnMainThread(text, name) {
  const { initWasmAccel } = await import('./renderer/wasmAccel.js')
  await initWasmAccel()
  const { parseBtf } = await import('./parser/btfParser.js')
  const { finalizeAndEnrich } = await import('./parser/tracePack.js')
  const result = finalizeAndEnrich(await parseBtf(text, (pct, msg) => {
    paintLoadingProgress(pct, msg)
  }))
  await attachParsedTrace(name, result, { sourceText: text })
}

async function onUserTracesLoaded(payload) {
  stopDemo()
  await onTracesLoaded(payload)
}

async function onTracesLoaded({ entries, sourceName }) {
  if (!entries?.length) {
    onFileError(
      `Failed to read "${sourceName || 'archive'}": ZIP archive has no .btf member`,
    )
    return
  }
  if (entries.length > 1) {
    showToast(`Opening ${entries.length} traces from ZIP…`, 'info')
  }
  for (const entry of entries) {
    _pendingTraceLoads.push({ text: entry.text, name: entry.name })
  }
  await drainPendingTraceLoads()
}

async function onTraceLoaded({ text, name }) {
  _pendingTraceLoads.push({ text, name })
  await drainPendingTraceLoads()
}

async function drainPendingTraceLoads() {
  if (_drainPromise) return _drainPromise
  _drainPromise = (async () => {
    try {
      while (_pendingTraceLoads.length) {
        const next = _pendingTraceLoads.shift()
        await loadOneTrace(next)
      }
    } finally {
      _drainPromise = null
      // Items may have been queued while we were clearing the promise.
      if (_pendingTraceLoads.length) await drainPendingTraceLoads()
    }
  })()
  return _drainPromise
}

async function loadOneTrace({ text, name }) {
  // Guard against exhausting tab memory on a huge/adversarial file; real
  // traces are typically tens of MB, this leaves generous headroom.
  const MAX_TRACE_FILE_BYTES = 500 * 1024 * 1024
  if (typeof text === 'string' && text.length > MAX_TRACE_FILE_BYTES) {
    showToast(
      `Trace file too large (${(text.length / (1024 * 1024)).toFixed(0)} MB, max ${MAX_TRACE_FILE_BYTES / (1024 * 1024)} MB)`,
      'error',
    )
    return
  }
  // Terminate any in-progress parse
  if (_parseWorker) { _parseWorker.terminate(); _parseWorker = null }

  loading.value         = true
  loadingPhase.value    = 'parse'
  loadingPct.value      = 1
  loadingMsg.value      = LOADING_STAGES.parsing
  loadingFileName.value = name || 'trace.btf'

  // Yield one animation frame so the browser can paint the loading overlay
  // before any heavy synchronous work (or worker creation) begins.
  await new Promise(r => requestAnimationFrame(r))

  // Chrome on file:// blocks Blob-URL workers (null-origin restriction).
  // Detect this by attempting a test createObjectURL worker; if it throws,
  // fall back to parsing synchronously on the main thread.
  let workerOk = true
  try {
    const testBlob = new Blob([''], { type: 'text/javascript' })
    const testUrl  = URL.createObjectURL(testBlob)
    const testW    = new Worker(testUrl)
    testW.terminate()
    URL.revokeObjectURL(testUrl)
  } catch {
    workerOk = false
  }

  if (!workerOk) {
    await new Promise(r => requestAnimationFrame(r))
    try {
      await parseTraceOnMainThread(text, name)
    } catch (err) {
      showParseError(err, name)
      loading.value = false
    }
    return
  }

  const Worker = (await import('./parser/btfWorker.js?worker&inline')).default
  const worker = new Worker()
  _parseWorker = worker

  await new Promise((resolve) => {
    worker.onmessage = ({ data }) => {
      if (data.type === 'progress') {
        loadingPhase.value = 'parse'
        loadingPct.value = data.pct
        loadingMsg.value = formatLoadingMessage(data.msg || '')
      } else if (data.type === 'done') {
        _parseWorker = null
        worker.terminate()
        attachParsedTrace(name, data.packed, { sourceText: text }).then(() => resolve()).catch((err) => {
          showParseError(err, name)
          loading.value = false
          resolve()
        })
      } else if (data.type === 'error') {
        _parseWorker = null
        worker.terminate()
        loadingPct.value = 1
        loadingMsg.value = LOADING_STAGES.parsing
        parseTraceOnMainThread(text, name).then(() => resolve()).catch((err) => {
          showParseError(err, name)
          loading.value = false
          resolve()
        })
      }
    }

    worker.onerror = () => {
      _parseWorker = null
      worker.terminate()
      loadingPct.value = 1
      loadingMsg.value = LOADING_STAGES.parsing
      parseTraceOnMainThread(text, name).then(() => resolve()).catch((err) => {
        showParseError(err, name)
        loading.value = false
        resolve()
      })
    }

    worker.postMessage({ text })
  })
}

// ---- Zoom ----------------------------------------------------------------
function onZoom(factor) {
  if (factor > 1 && !zoomOutEnabled.value) return
  timelinePanelRef.value?.zoomCenter(factor)
  syncTimelineViewport()
}

function onFit() {
  timelinePanelRef.value?.fitToTrace()
  syncTimelineViewport()
}

function closePalette() {
  paletteOpen.value = false
  paletteQuery.value = ''
  paletteIndex.value = 0
}

async function openPalette() {
  paletteOpen.value = true
  paletteQuery.value = ''
  paletteIndex.value = 0
  await nextTick()
  paletteInput.value?.focus?.()
}

function runPaletteAction(id) {
  const aid = String(id || '')
  const [ok, reason] = paletteIsAvailable(aid)
  if (!ok) {
    showToast(reason || 'Unavailable', 'info')
    return
  }
  closePalette()
  bumpPaletteUsage(aid)
  if (aid === 'analysis') analysisOpen.value = true
  else if (aid === 'statistics') rightPanelTab.value = 'stats'
  else if (aid === 'find') rightPanelTab.value = 'find'
  else if (aid === 'marks') rightPanelTab.value = 'marks'
  else if (aid === 'ai') rightPanelTab.value = 'ai'
  else if (aid === 'compare') compareOpen.value = true
  else if (aid === 'heatmap') onOpenHeatmap()
  else if (aid === 'focus') toggleFocusMode()
  else if (aid === 'settings') openSettingsDialog()
  else if (aid === 'limit-scope') onStatsScopeChange(true)
  else if (aid === 'fit') onFit()
  else if (aid === 'inspect-task') {
    showToast(taskInspectorText.value, 'info')
  } else if (String(aid).startsWith('preset-')) {
    applyWorkspacePreset(aid)
  } else if (aid.startsWith('stats-section:')) {
    const sid = aid.slice('stats-section:'.length).trim()
    rightPanelTab.value = 'stats'
    nextTick(() => {
      statsPanelRef.value?.applyDemoSections?.({
        id: sid,
        expand: true,
        scroll: sid,
        collapse_others: false,
      })
    })
  }
}

function applyWorkspacePreset(id) {
  if (id === 'preset-compare') {
    compareOpen.value = true
    return
  }
  rightPanelTab.value = 'stats'
  appSettings.statsSectionCollapsed = workspacePresetCollapsed(
    id, defaultSectionCollapsed())
  saveSettings(appSettings)
}

function onPaletteKeydown(e) {
  const hits = paletteHits.value
  if (e.key === 'Escape') {
    e.preventDefault()
    closePalette()
    return
  }
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    paletteIndex.value = Math.min(hits.length - 1, paletteIndex.value + 1)
    return
  }
  if (e.key === 'ArrowUp') {
    e.preventDefault()
    paletteIndex.value = Math.max(0, paletteIndex.value - 1)
    return
  }
  if (e.key === 'Enter') {
    e.preventDefault()
    const row = hits[paletteIndex.value]
    if (row) runPaletteAction(row.id)
  }
}

function onZoomPreset(value) {
  if (!value || value === 'fit') onFit()
  else timelinePanelRef.value?.zoomToPercent(Number(value))
  syncTimelineViewport()
  refreshZoomPresetUi()
}

function refreshZoomPresetUi() {
  const snap = timelinePanelRef.value?.getZoomPresetSnapshot?.()
  if (!snap) {
    zoomPresetOptions.value = buildZoomPresetOptions(NaN, 0)
    zoomPresetValue.value = 'fit'
    return
  }
  zoomPresetOptions.value = snap.options
  zoomPresetValue.value = snap.value
}

function onZoom1to1() {
  const vp = timelinePanelRef.value?.getViewport?.()
  const lo = trace.value?.timeMin ?? 0
  const hi = trace.value?.timeMax ?? 1
  const wasFit = vp && (vp.timeEnd - vp.timeStart) >= (hi - lo) * 0.92
  timelinePanelRef.value?.zoom1to1(wasFit)
  syncTimelineViewport()
}

function onZoomRange() {
  if (!rangeEnabled.value) {
    showToast('Place at least 2 cursors to zoom to range', 'info')
    return
  }
  const ok = timelinePanelRef.value?.zoomToCursorRange?.()
  if (!ok) showToast('Place at least 2 cursors to zoom to range', 'info')
  else syncTimelineViewport()
}

function onJumpToTraceStart() {
  jumpDialogOpen.value = false
  timelinePanelRef.value?.jumpToTraceStart()
  syncTimelineViewport()
}

function onJumpToTraceEnd() {
  jumpDialogOpen.value = false
  timelinePanelRef.value?.jumpToTraceEnd()
  syncTimelineViewport()
}

function onJumpToTime(ns) {
  jumpDialogOpen.value = false
  timelinePanelRef.value?.jumpToNs(ns)
  syncTimelineViewport()
}

function onStatsPlotPointActivate({ ns, note, segment, interval, priorityRange, syncIssue, tagSample, tagChannel }) {
  const stayOnTab = rightPanelTab.value
  if (syncIssue) {
    pinnedHighlightKey.value = null
    timelineOptions.lockedTaskKey = null
    scheduleRender()
  }
  if (segment) {
    timelineOptions.highlightInterval = null
    highlightSegment.value = segment
    timelineOptions.highlightSegment = segment
    timelineOptions.highlightKey = taskMergeKey(segment.task)
    if (syncIssue) {
      timelinePanelRef.value?.expandCoresForMergeKeys([taskMergeKey(segment.task)])
      timelinePanelRef.value?.zoomToTimeRange(segment.start, segment.end)
      if (ns != null) timelinePanelRef.value?.jumpToNs(ns)
    }
    timelinePanelRef.value?.scrollToSegmentIfNeeded(segment)
  } else if (syncIssue && ns != null && trace.value) {
    timelineOptions.highlightInterval = null
    highlightSegment.value = null
    timelineOptions.highlightSegment = null
    const tr = trace.value
    const pad = Math.max(1000, Math.floor((tr.timeMax - tr.timeMin) / 200))
    timelinePanelRef.value?.zoomToTimeRange(
      Math.max(tr.timeMin, ns - pad),
      Math.min(tr.timeMax, ns + pad),
    )
    timelinePanelRef.value?.jumpToNs(ns)
  } else if (interval) {
    highlightSegment.value = null
    timelineOptions.highlightSegment = null
    timelineOptions.highlightInterval = { ...interval, markNs: ns ?? interval.stopNs }
    timelinePanelRef.value?.zoomToTimeRange(interval.startNs, interval.stopNs)
    timelinePanelRef.value?.scrollToIntervalRow(interval.id)
  } else if (tagSample && ns != null) {
    highlightSegment.value = null
    timelineOptions.highlightSegment = null
    timelineOptions.highlightInterval = null
    const tr = trace.value
    const pad = Math.max(1000, Math.floor((tr.timeMax - tr.timeMin) / 200))
    timelinePanelRef.value?.zoomToTimeRange(
      Math.max(tr.timeMin, ns - pad),
      Math.min(tr.timeMax, ns + pad),
    )
    if (tagChannel) timelinePanelRef.value?.scrollToStiChannel(tagChannel)
    timelinePanelRef.value?.jumpToNs(ns)
  } else if (priorityRange) {
    highlightSegment.value = null
    timelineOptions.highlightSegment = null
    timelineOptions.highlightInterval = null
    pinnedHighlightKey.value = priorityRange.mk
    timelineOptions.highlightKey = priorityRange.mk
    timelineOptions.lockedTaskKey = priorityRange.mk
    timelinePanelRef.value?.expandCoresForMergeKeys([priorityRange.mk])
    scheduleRender()
    nextTick(() => {
      timelinePanelRef.value?.zoomToTimeRange(priorityRange.startNs, priorityRange.stopNs)
      timelinePanelRef.value?.scrollToTask(priorityRange.mk)
      syncTimelineViewport()
      scheduleRender()
    })
  } else if (ns != null) {
    timelineOptions.highlightInterval = null
    timelinePanelRef.value?.jumpToNs(ns)
  }
  if (ns != null) {
    addAnnotationAtNs(ns, note)
  }
  if (rightPanelTab.value !== stayOnTab) {
    rightPanelTab.value = stayOnTab
  }
  syncTimelineViewport()
  scheduleSessionSave()
}

function onStatsSegmentJump(ns, meta = {}) {
  // Matches desktop's _on_segment_jump: scroll the timeline to ns without
  // zooming or adding an annotation (e.g. Task Lifecycle / Core-Pair rows).
  if (ns == null) return
  recordEvidenceJump({
    time: Number(ns),
    task: meta.task || meta.mk || '',
    source_metric: meta.source || SHOW_ON_TIMELINE_LABEL,
    stats_section: meta.section || '',
  })
  timelinePanelRef.value?.jumpToNs(ns)
  syncTimelineViewport()
  scheduleRender()
}

function onOpenPlotChange(v) {
  if (activeTab.value) activeTab.value.openPlot = v
  scheduleSessionSave()
}

function onSectionHeightsChange(v) {
  Object.assign(statsSectionHeights.value, v)
  scheduleSessionSave()
}

function onStatsScopeChange(v) {
  if (activeTab.value) activeTab.value.scopeToCursors = !!v
  scheduleSessionSave()
}

function onToggleLimit() {
  if (!rangeEnabled.value) return
  onStatsScopeChange(!limitOn.value)
}

function onStatsSectionCollapsedChange(v) {
  appSettings.statsSectionCollapsed = mergeSectionCollapsed(v)
  saveSettings(appSettings)
  scheduleSessionSave()
}

function onStatsSectionPinsChange(v) {
  appSettings.statsPinnedSections = normalizeStatsPins(v)
  saveSettings(appSettings)
}

function onStatsSectionOrderChange(v) {
  appSettings.statsSectionOrder = normalizeStatsSectionOrder(v)
  saveSettings(appSettings)
}

function onFindQueryChange(v) {
  findQuery.value = v
}

function onFindModeChange(v) {
  findMode.value = v
}

function recomputeFind() {
  if (!activeTab.value || !trace.value) {
    findError.value = ''
    return
  }
  const { hits, error } = computeFindHits(
    trace.value,
    activeTab.value.findQuery,
    activeTab.value.findMode,
    // Desktop Find searches annotations only (not bookmarks).
    (marks.value || []).filter(m => m.type === 'annotation'),
  )
  activeTab.value.findHits = hits
  activeTab.value.findHitIdx = -1
  activeTab.value.findMarkerNs = null
  findError.value = error || ''
  timelinePanelRef.value?.scheduleRender()
  scheduleSessionSave()
}

function stepFind(forward) {
  if (!activeTab.value?.findHits?.length) {
    recomputeFind()
    if (!activeTab.value?.findHits?.length) return
  }
  const center = timelinePanelRef.value?.getViewportCenter?.() ?? 0
  const idx = stepFindHitIndex(
    activeTab.value.findHits,
    activeTab.value.findHitIdx,
    center,
    forward,
  )
  activeTab.value.findHitIdx = idx
  const ns = activeTab.value.findHits[idx]
  activeTab.value.findMarkerNs = ns
  timelinePanelRef.value?.jumpToNs(ns)
  syncTimelineViewport()
  timelinePanelRef.value?.scheduleRender()
  scheduleSessionSave()
}

function focusFindPanel() {
  if (!appSettings.showFind) {
    appSettings.showFind = true
    saveSettings(appSettings)
  }
  rightPanelTab.value = 'find'
  nextTick(() => findPanelRef.value?.focusInput())
}

async function focusAiAndAsk(templateIdOrPayload) {
  if (appSettings.aiEnabled === false) {
    openSettingsDialog('ai')
    return
  }
  if (appSettings.showAi === false) {
    appSettings.showAi = true
    saveSettings(appSettings)
  }
  rightPanelTab.value = 'ai'
  let templateId = templateIdOrPayload
  let findingId = ''
  let prompt = null
  let level = ''
  let extra = ''
  if (templateIdOrPayload && typeof templateIdOrPayload === 'object') {
    templateId = templateIdOrPayload.template || 'findings'
    findingId = templateIdOrPayload.findingId || ''
    prompt = templateIdOrPayload.prompt || null
    level = String(templateIdOrPayload.level || '').trim()
    extra = String(templateIdOrPayload.extra || '').trim()
  }
  templateId = templateId || 'findings'
  if (!prompt) {
    prompt = AI_TEMPLATE_QUESTIONS.find(t => t.id === templateId)?.prompt
    if (findingId && prompt) {
      prompt = `${prompt}\n\nfinding_id=${findingId}`
    }
    if (level && prompt) {
      prompt = `${prompt}\n\nlevel=${level}`
    }
    if (extra && prompt) {
      prompt = `${prompt}\n\n${extra}`
    }
  }
  if (templateId === 'explain_region' && prompt) {
    prompt = appendExplainRegionBounds(prompt, cursors.value)
  }
  await nextTick()
  if (!aiPanelRef.value) await nextTick()
  if (prompt) {
    if (aiPanelRef.value?.askTemplate) {
      await aiPanelRef.value.askTemplate(templateId, prompt)
    } else {
      await aiPanelRef.value?.ask?.(prompt)
    }
  }
}

const analysisUxEvents = computed(() => {
  const tr = trace.value
  if (!tr) return []
  const range = getStatsRange(cursors.value, activeTab.value?.scopeToCursors !== false)
  return harvestUxEvents(tr, range?.lo ?? null, range?.hi ?? null)
})

function onApplyFindingScope(finding) {
  const tr = trace.value
  if (!tr || !finding) return
  const scope = bestFindingScope(finding, analysisUxEvents.value, tr.timeMin, tr.timeMax)
  if (scope) applyExploreRange(scope)
}

/** Step-1 item 7: plain, non-AI Investigate — scope the finding then jump to its Statistics section. */
async function onInvestigateFinding({ finding, sectionId } = {}) {
  if (!finding || !sectionId) return
  findingsInvestigateUndo.value = {
    cursors: [...(cursors.value || [])],
    scopeToCursors: activeTab.value?.scopeToCursors !== false,
    viewport: timelinePanelRef.value?.getViewport?.() || null,
  }
  onApplyFindingScope(finding)
  // Keep Findings inbox open so Timeline Evidence stays visible (Step 2 #5/#16).
  rightPanelTab.value = 'stats'
  await nextTick()
  statsPanelRef.value?.applyDemoSections?.({ id: sectionId, expand: true, scroll: 'section' })
}

function onUndoInvestigateFinding() {
  const snap = findingsInvestigateUndo.value
  if (!snap) return
  cursors.value = Array.isArray(snap.cursors) ? [...snap.cursors] : cursors.value
  if (activeTab.value) activeTab.value.scopeToCursors = !!snap.scopeToCursors
  onStatsScopeChange(!!snap.scopeToCursors)
  if (snap.viewport) timelinePanelRef.value?.applyViewport?.(snap.viewport)
  findingsInvestigateUndo.value = null
  showToast('Restored Scope from before Investigate', 'info')
  scheduleSessionSave()
}

function onFindingsTriageUpdate(state) {
  findingsTriageState.value = normalizeTriageState(state)
  scheduleSessionSave()
}

function onAddFindingToCase(finding) {
  if (!finding) return
  const ok = aiPanelRef.value?.addFindingToInvestigationCase?.(finding)
  if (ok) {
    showToast('Finding added to AI Case', 'info')
    scheduleSessionSave()
  } else {
    showToast('Could not add finding to Case', 'error')
  }
}

/** Step-2 Show Evidence — Timeline jump without changing Scope or Filters. */
function onShowFindingEvidence(finding) {
  const tr = trace.value
  if (!tr || !finding) return
  const target = resolveFindingEvidence(
    finding, analysisUxEvents.value, tr.timeMin, tr.timeMax)
  if (!target.ok) {
    showToast(target.reason || 'No Timeline Evidence for this finding', 'info')
    return
  }
  const ns = Number(target.ns)
  // Place an Evidence marker in a free cursor slot when possible; never
  // clear existing Scope cursors and never force Limit-to-cursors.
  const max = appSettings.maxCursors || 4
  const next = Array.from({ length: max }, (_, i) => cursors.value[i] ?? null)
  const near = next.some(t => t != null && Math.abs(Number(t) - ns) <= 1)
  if (!near) {
    const slot = next.findIndex(t => t == null)
    if (slot >= 0) {
      next[slot] = ns
      cursors.value = next
    }
  }
  timelinePanelRef.value?.jumpToNs(ns)
  syncTimelineViewport()
  const highlightKey = String(target.mk || target.task || '').trim()
  if (highlightKey) onHighlightClick(highlightKey)
  recordEvidenceJump({
    time: ns,
    task: highlightKey,
    source_metric: String(finding.title || 'Finding'),
    stats_section: (finding.id && FINDING_SECTION_MAP?.[finding.id]) || '',
  })
  const multi = target.multi ? ' (one of several)' : ''
  showToast(
    `Evidence${multi}: ${target.note || 'located'} — Scope/Filters unchanged`,
    'info',
  )
}

function onSaveAnalysisRecipe() {
  const tpl = newUserInvestigationTemplate('Analysis recipe', [
    'investigate', 'correlate', 'generate_report',
  ])
  const items = (loadAiUserInvestigationTemplates() || []).filter(it => it.id !== tpl.id)
  items.push(tpl)
  saveAiUserInvestigationTemplates(items)
  showToast(`Saved recipe “${tpl.label}”.`, 'info')
}

function onSaveAnalysisStory() {
  const text = formatAnalysisStory(analysisFindings.value || [], {
    qualityWarnings: analysisQuality.value,
    scopeTitle: analysisScopeLabel.value,
  })
  const blob = new Blob([text], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'analysis-story.txt'
  a.click()
  URL.revokeObjectURL(url)
}

async function queryAnalysisWithAi(payload = 'findings') {
  // Keep Findings open while AI runs (non-modal tool window).
  await focusAiAndAsk(payload)
}

async function queryExplainRegionWithAi() {
  await focusAiAndAsk('explain_region')
}

async function queryAskAiEvent(event) {
  await focusAiAndAsk({ template: 'ask_event', prompt: composeAskEventPrompt(event) })
}

async function queryCorridorWithAi(payload) {
  const extra = String(payload?.extra || '').trim()
  if (payload?.action === 'compare') {
    const tabsOpen = (tabs.value || []).filter(t => t?.trace)
    if (tabsOpen.length >= 2) {
      await queryCompareWithAi({ idA: tabsOpen[0].id, idB: tabsOpen[1].id })
      return
    }
  }
  await focusAiAndAsk({
    template: 'migrations',
    extra,
  })
}

function onInspectorInspectTask(mk) {
  if (mk) onHighlightClick(mk)
}

async function onInspectorOpenLoadBalance() {
  rightPanelTab.value = 'stats'
  await nextTick()
  statsPanelRef.value?.applyDemoSections?.({
    id: 'cores', expand: true, scroll: 'section', collapse_others: false,
  })
}

async function queryCompareWithAi(payload) {
  const idA = payload?.idA
  const idB = payload?.idB
  compareOpen.value = false
  if (appSettings.aiEnabled === false) {
    openSettingsDialog('ai')
    return
  }
  if (idA == null || idB == null || idA === idB) {
    showToast('Choose two different traces to compare.', 'info')
    return
  }
  if (appSettings.showAi === false) {
    appSettings.showAi = true
    saveSettings(appSettings)
  }
  rightPanelTab.value = 'ai'
  await nextTick()
  if (!aiPanelRef.value) await nextTick()
  await aiPanelRef.value?.askCompare?.(idA, idB, payload?.sectionLabel || '')
}

async function queryValidateExperimentWithAi(payload) {
  const idA = payload?.idA
  const idB = payload?.idB
  compareOpen.value = false
  if (appSettings.aiEnabled === false) {
    openSettingsDialog('ai')
    return
  }
  if (idA == null || idB == null || idA === idB) {
    showToast('Choose two different traces to compare.', 'info')
    return
  }
  if (appSettings.showAi === false) {
    appSettings.showAi = true
    saveSettings(appSettings)
  }
  rightPanelTab.value = 'ai'
  await nextTick()
  if (!aiPanelRef.value) await nextTick()
  await aiPanelRef.value?.askValidateExperiment?.(idA, idB)
}

function buildAiContext() {
  const tr = trace.value
  if (!tr) {
    return {
      findingsText: 'No trace loaded.', scope: '', span: '', cores: '', cursors: [],
      filters: [], selection: null,
    }
  }
  const scopeOn = activeTab.value?.scopeToCursors !== false
  const range = getStatsRange(cursors.value, scopeOn)
  const findings = collectTraceAnalysisFindings(
    tr,
    range?.lo ?? null,
    range?.hi ?? null,
    appSettings,
  )
  const scopeLabel = range ? ` (C1–C${range.nCursors})` : ''
  const span = formatTime(tr.timeMax - tr.timeMin, tr.timeScale, appSettings.timeDecimals)
  return {
    findingsText: formatAnalysisFindingsText(findings, scopeLabel),
    findings,
    scope: range ? `C1–C${range.nCursors}` : 'full trace',
    span,
    cores: tr.coreNames?.length ?? tr.cores?.length ?? 0,
    cursors: (cursors.value || []).filter(c => c != null),
    // Reserved for Step 2 AI context (item 3/4): same Filter/Selection
    // representation shown in the status bar and Legend.
    filters: activeFilterChips.value.map(c => c.label),
    selection: pinnedHighlightKey.value || null,
    timeScale: tr.timeScale || '',
  }
}

function listAiLoadedTabs() {
  return tabs.value
    .filter(t => t?.trace)
    .map(t => ({ id: t.id, name: t.name || `Tab ${t.id}` }))
}

function buildAiCompareContext(idA, idB, section = '') {
  const tabA = tabs.value.find(t => t.id === idA)
  const tabB = tabs.value.find(t => t.id === idB)
  if (!tabA?.trace || !tabB?.trace) {
    throw new Error('Both tabs must have a loaded trace')
  }
  const nameA = tabA.name || 'Trace A'
  const nameB = tabB.name || 'Trace B'
  const scopeEnabled = true
  const tables = buildAllCompareTables(
    tabA.trace, tabB.trace, tabA, tabB, scopeEnabled, appSettings.taskDeadlines)
  try {
    lastAiCompare = compareAiPerformance(idA, idB)
  } catch {
    /* keep prior lastAiCompare */
  }
  let csvText = buildCompareCsv(nameA, nameB, scopeEnabled, tables)
  if (csvText.length > 60000) {
    csvText = `${csvText.slice(0, 60000)}\n… (truncated for AI context)`
  }
  const sec = String(section || '').trim()
  const focusLine = sec && sec.toLowerCase() !== 'summary'
    ? `AI focus: the engineer selected the "${sec}" section — lead your analysis with it.\n`
    : ''
  return {
    findingsText: (
      focusLine +
      `Trace Compare tables (CSV) for ${nameA} vs ${nameB}.\n` +
      'Cursor scope per tab: yes (when 2+ cursors placed).\n\n' +
      csvText
    ),
    scope: `Trace Compare: ${nameA} vs ${nameB}`,
    span: '',
    cores: '',
  }
}

watch(
  () => tabs.value.filter(t => t?.trace).map(t => t.id).join('|'),
  () => {
    aiPanelRef.value?.refreshLoadedTabs?.()
    aiPanelRef.value?.refreshCoreAvailability?.()
  },
)

// The panel stays mounted while hidden, so catch it up on re-entry: a log
// scrolled while display:none keeps its old offset.
watch(rightPanelTab, (tab) => {
  if (tab !== 'ai') return
  nextTick(() => {
    aiPanelRef.value?.refreshLoadedTabs?.()
    aiPanelRef.value?.refreshCoreAvailability?.()
    aiPanelRef.value?.scrollLog?.()
  })
})

function onAiJump(t) {
  if (t == null || !Number.isFinite(Number(t))) return
  const ns = Number(t)
  recordEvidenceJump({
    time: ns,
    source_metric: 'AI evidence',
  })
  timelinePanelRef.value?.jumpToNs(ns)
  syncTimelineViewport()
  if (!trace.value) return
  addAnnotationAtNs(ns, aiJumpAnnotationNote(ns))
  scheduleSessionSave()
}

function onAiOpenStats(sectionId) {
  const sid = String(sectionId || '').trim()
  if (!sid) return
  rightPanelTab.value = 'stats'
  nextTick(() => {
    statsPanelRef.value?.applyDemoSections?.({ id: sid, expand: true, scroll: sid })
  })
}

function onAiRange({ lo, hi } = {}) {
  applyExploreRange({ lo, hi, note: `AI range:${lo}/${hi}`, ns: lo })
}

function applyExploreRange(spec = {}) {
  const lo = Number(spec.lo)
  const hi = Number(spec.hi)
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) return
  const a = Math.min(lo, hi)
  const b = Math.max(lo, hi)
  const max = appSettings.maxCursors || 4
  const next = Array(max).fill(null)
  next[0] = a
  next[1] = Math.max(b, a + 1)
  cursors.value = next
  onStatsScopeChange(true)
  timelinePanelRef.value?.zoomToTimeRange(
    a, next[1], 0.05, { programmatic: true, animate: true },
  )
  if (spec.mk) onHighlightClick(spec.mk)
  if (spec.ns != null && Number.isFinite(Number(spec.ns))) {
    timelinePanelRef.value?.jumpToNs(Number(spec.ns))
  }
  syncTimelineViewport()
  if (spec.section) {
    nextTick(() => {
      statsPanelRef.value?.applyDemoSections?.({
        id: spec.section, expand: true, scroll: spec.section,
      })
    })
  }
  if (spec.note && spec.ns != null) {
    addAnnotationAtNs(Number(spec.ns), spec.note)
  }
  scheduleSessionSave()
}

let _aiGuiUndo = null
let lastAiCompare = null

function captureAiGuiSnapshot() {
  return {
    cursors: [...(cursors.value || [])],
    viewMode: timelineOptions.viewMode,
    orientation: timelineOptions.orientation,
    highlight: pinnedHighlightKey.value,
    viewport: timelinePanelRef.value?.getViewport?.() || null,
    inspectorOpen: inspectorOpen.value,
    marks: (marks.value || []).map(m => ({ ...m })),
    markNextId: activeTab.value?.markNextId,
    scopeToCursors: activeTab.value?.scopeToCursors !== false,
    taskFilterKeys: timelineOptions.taskFilterKeys
      ? [...timelineOptions.taskFilterKeys]
      : null,
    taskFilterText: timelineOptions.taskFilterText || '',
    coreFilterKeys: timelineOptions.coreFilterKeys
      ? [...timelineOptions.coreFilterKeys]
      : null,
    migratedOnlyFilter: !!timelineOptions.migratedOnlyFilter,
    heatmapFilterLabel: timelineOptions.heatmapFilterLabel || null,
  }
}

function restoreAiGuiSnapshot(snap) {
  if (!snap) return
  cursors.value = Array.isArray(snap.cursors) ? [...snap.cursors] : cursors.value
  if (snap.viewMode) timelineOptions.viewMode = snap.viewMode
  if (snap.orientation) timelineOptions.orientation = snap.orientation
  pinnedHighlightKey.value = snap.highlight || null
  timelineOptions.highlightKey = snap.highlight || null
  timelineOptions.lockedTaskKey = snap.highlight || null
  if (snap.viewport) timelinePanelRef.value?.applyViewport?.(snap.viewport)
  if (!snap.inspectorOpen) inspectorOpen.value = false
  if (Array.isArray(snap.marks)) {
    marks.value = snap.marks.map(m => ({ ...m }))
    if (activeTab.value && snap.markNextId != null) {
      activeTab.value.markNextId = snap.markNextId
    }
  }
  if ('scopeToCursors' in snap) {
    if (activeTab.value) activeTab.value.scopeToCursors = !!snap.scopeToCursors
    onStatsScopeChange?.(!!snap.scopeToCursors)
  }
  if ('taskFilterKeys' in snap || 'taskFilterText' in snap
    || 'coreFilterKeys' in snap || 'migratedOnlyFilter' in snap) {
    timelineOptions.taskFilterKeys = Array.isArray(snap.taskFilterKeys)
      ? [...snap.taskFilterKeys]
      : (snap.taskFilterKeys ?? null)
    timelineOptions.taskFilterText = String(snap.taskFilterText || '')
    timelineOptions.coreFilterKeys = Array.isArray(snap.coreFilterKeys)
      ? [...snap.coreFilterKeys]
      : (snap.coreFilterKeys ?? null)
    timelineOptions.migratedOnlyFilter = !!snap.migratedOnlyFilter
    timelineOptions.heatmapFilterLabel = snap.heatmapFilterLabel || null
    if (activeTab.value) {
      activeTab.value.taskFilterKeys = timelineOptions.taskFilterKeys
      activeTab.value.taskFilterText = timelineOptions.taskFilterText
      activeTab.value.coreFilterKeys = timelineOptions.coreFilterKeys
      activeTab.value.migratedOnlyFilter = timelineOptions.migratedOnlyFilter
    }
  }
  persistTimelineViewPrefs()
  syncTimelineViewport()
  scheduleRender()
}

function aiGuiStateForReport() {
  const ctx = buildAiContext()
  const placed = (cursors.value || []).filter(c => c != null)
  return {
    file: activeTab.value?.name || '',
    span: ctx.span || '',
    cores: ctx.cores || '',
    scope: ctx.scope || '',
    findings: ctx.findingsText || '',
    cursors: placed,
    highlight: pinnedHighlightKey.value || '',
    view_mode: timelineOptions.viewMode || 'task',
    orientation: timelineOptions.orientation === 'v' ? 'vertical' : 'horizontal',
    annotations: (marks.value || [])
      .filter(m => m.type === 'annotation')
      .map(m => ({ time: m.ns, note: m.label || '' })),
  }
}

function onAiHighlight(name) {
  const key = String(name || '').trim()
  if (!key) {
    // Mirrors Desktop's set_highlighted_task(None): clears the task-level
    // pin *and* any exact-segment selection in one shot.
    pinnedHighlightKey.value = null
    timelineOptions.highlightKey = null
    timelineOptions.lockedTaskKey = null
    highlightSegment.value = null
    timelineOptions.highlightSegment = null
    scheduleRender()
    return
  }
  const candidates = [
    ...(trace.value?.tasks || []),
    ...(trace.value?.tasks || []).map(t => taskMergeKey(t)),
  ]
  const resolved = resolveTaskKey(key, candidates)
  if (resolved) {
    const mk = taskMergeKey(resolved)
    pinnedHighlightKey.value = mk
    timelineOptions.highlightKey = mk
    timelineOptions.lockedTaskKey = mk
    timelinePanelRef.value?.scrollToTask(mk)
    scheduleRender()
    return
  }
  const core = resolveCoreKey(key, trace.value?.coreNames || [])
  if (!core) return
  timelineOptions.viewMode = 'core'
  persistTimelineViewPrefs()
  pinnedHighlightKey.value = null
  timelineOptions.highlightKey = null
  timelineOptions.lockedTaskKey = null
  nextTick(() => {
    timelinePanelRef.value?.expandCore?.(core)
    timelinePanelRef.value?.scrollToTask(core)
    scheduleRender()
  })
}

function onAiExecuteTools(calls) {
  const mutating = (calls || []).some(c => toolMutatesGui(String(c?.name || '')))
  if (mutating) {
    _aiGuiUndo = captureAiGuiSnapshot()
    pushUndoSnapshot()
  } else {
    _aiGuiUndo = null
  }
  const results = []
  for (const call of calls || []) {
    const name = String(call.name || '')
    const args = call.arguments && typeof call.arguments === 'object' ? call.arguments : {}
    if (call.error) {
      results.push({ ok: false, message: call.error })
      continue
    }
    const checked = validateToolCall(name, args)
    if (checked.error) {
      results.push({ ok: false, message: checked.error })
      continue
    }
    try {
      const out = dispatchAiTool(name, checked.args || {})
      if (out && typeof out === 'object' && 'ok' in out) results.push(out)
      else results.push({ ok: true, message: String(out) })
    } catch (err) {
      results.push({ ok: false, message: err?.message || String(err) })
    }
  }
  return results
}

function dispatchAiTool(name, args) {
  if (!trace.value) throw new Error('No trace loaded')
  if (name === AI_TOOL_SET_CURSORS) {
    const max = appSettings.maxCursors || 4
    const times = (args.timestamps || []).slice(0, max)
    const next = Array(max).fill(null)
    times.forEach((t, i) => { next[i] = Number(t) })
    cursors.value = next
    return `Placed ${times.length} cursor(s)`
  }
  if (name === AI_TOOL_ZOOM_TO_RANGE) {
    timelinePanelRef.value?.zoomToTimeRange(
      args.start_time, args.end_time, 0.05, { programmatic: true, animate: true },
    )
    syncTimelineViewport()
    return 'Zoomed to range'
  }
  if (name === AI_TOOL_HIGHLIGHT_TASK) {
    onAiHighlight(args.task_name_or_id || '')
    return args.task_name_or_id ? `Highlighted ${args.task_name_or_id}` : 'Cleared highlight'
  }
  if (name === AI_TOOL_SET_VIEW_MODE) {
    timelineOptions.viewMode = args.mode
    if (args.orientation === 'horizontal') timelineOptions.orientation = 'h'
    if (args.orientation === 'vertical') timelineOptions.orientation = 'v'
    persistTimelineViewPrefs()
    scheduleRender()
    return `View mode ${args.mode}`
  }
  if (name === AI_TOOL_OPEN_CORRIDOR) {
    const cores = trace.value?.coreNames || []
    const src = resolveCoreKey(args.core_from || '', cores) || (args.core_from || '')
    const dst = resolveCoreKey(args.core_to || '', cores) || (args.core_to || '')
    if (src && dst) onOpenPairHeatmap({ fromCore: src, toCore: dst })
    else onOpenHeatmap()
    return 'Opened corridor inspector'
  }
  if (name === AI_TOOL_OPEN_STATS_SECTION) {
    const section = String(args.section || args.section_id || '').trim()
    onAiOpenStats(section)
    return section ? `Opened Statistics section ${section}` : 'Opened Statistics'
  }
  if (name === AI_TOOL_ADD_ANNOTATION) {
    const ns = Math.trunc(Number(args.time))
    const note = String(args.note || '')
    timelinePanelRef.value?.jumpToNs(ns)
    syncTimelineViewport()
    const existing = (marks.value || []).find(
      m => m.type === 'annotation' && Number(m.ns) === ns && (m.label || '') === note)
    if (existing) return `Annotation already at ${ns}`
    addMarkAtNs(ns, 'annotation', note, { undo: false })
    scheduleSessionSave()
    return `Annotated ${ns}`
  }
  if (name === AI_TOOL_QUERY_RAW_METRIC) {
    const scopeOn = activeTab.value?.scopeToCursors !== false
    const range = getStatsRange(cursors.value, scopeOn)
    return queryRawMetric(trace.value, args.task || '', args.metric || '', {
      lo: range?.lo ?? null,
      hi: range?.hi ?? null,
      findingsText: buildAiContext().findingsText || '',
    })
  }
  if (name === AI_TOOL_CLEAR_MARKS) {
    const what = String(args.what || 'all')
    const cleared = []
    if (['cursors', 'all', 'everything'].includes(what)) {
      clearCursors()
      cleared.push('cursors')
    }
    if (['annotations', 'all', 'everything'].includes(what)) {
      marks.value = (marks.value || []).filter(m => m.type !== 'annotation')
      cleared.push('annotations')
    }
    if (['bookmarks', 'everything'].includes(what)) {
      marks.value = (marks.value || []).filter(m => m.type === 'annotation')
      cleared.push('bookmarks')
    }
    scheduleSessionSave()
    scheduleRender()
    return `Cleared ${cleared.join(', ') || what}`
  }
  if (name === AI_TOOL_RESET_VIEW) {
    timelinePanelRef.value?.fitToTrace()
    syncTimelineViewport()
    onAiHighlight('')
    return 'Reset view to full trace'
  }
  if (name === AI_TOOL_SEARCH_TIMELINE) {
    return searchTimelineHits(
      trace.value,
      args.query || '',
      args.mode || 'contains',
      (marks.value || []).filter(m => m.type === 'annotation'),
    )
  }
  if (name === AI_TOOL_TRIGGER_COMPARE) {
    return triggerAiCompare(args.tab_a || '', args.tab_b || '')
  }
  if (name === AI_TOOL_INVESTIGATE) {
    return investigateFinding(analysisFindings.value || [], args.finding_id || '', {
      depth: args.depth ?? 2,
    })
  }
  if (name === AI_TOOL_DETECT_ANOMALIES) {
    return detectAnomaliesFinding(analysisFindings.value || [], {
      limit: args.limit ?? 10,
    })
  }
  if (name === AI_TOOL_CORRELATE_EVENTS) {
    return correlateTaskEvents(trace.value, args.task || '', {
      aroundTime: args.around_time,
      window: args.window || 0,
      annotations: (marks.value || []).filter(m => m.type === 'annotation'),
    })
  }
  if (name === AI_TOOL_FIND_CRITICAL_PATH) {
    return findCriticalPathTask(trace.value, args.task || '', {
      timestamp: args.timestamp ?? null,
      window: args.window ?? 2000,
      annotations: (marks.value || []).filter(m => m.type === 'annotation'),
    })
  }
  if (name === AI_TOOL_COMPARE_PERFORMANCE) {
    const payload = compareAiPerformance(args.tab_a || '', args.tab_b || '')
    lastAiCompare = payload
    return payload
  }
  if (name === AI_TOOL_DETECT_PRIORITY_INVERSION) {
    const scopeOn = activeTab.value?.scopeToCursors !== false
    const range = getStatsRange(cursors.value, scopeOn)
    return detectPriorityInversionHost(trace.value, analysisFindings.value || [], {
      task: args.task || '',
      window: args.window ?? null,
      lo: range?.lo ?? null,
      hi: range?.hi ?? null,
    })
  }
  if (name === AI_TOOL_FIND_RELATED_FINDINGS) {
    return findRelatedFindingsFinding(analysisFindings.value || [], {
      findingId: args.finding_id || '',
      task: args.task || '',
      metric: args.metric || '',
      window: args.window ?? null,
      limit: args.limit ?? 10,
    })
  }
  if (name === AI_TOOL_COMPARE_TASKS) {
    const scopeOn = activeTab.value?.scopeToCursors !== false
    const range = getStatsRange(cursors.value, scopeOn)
    return compareTasksHost(trace.value, args.task_a || '', args.task_b || '', {
      metrics: args.metrics || null,
      lo: range?.lo ?? null,
      hi: range?.hi ?? null,
      findingsText: buildAiContext().findingsText || '',
    })
  }
  if (name === AI_TOOL_EXPLAIN_FINDING) {
    return explainFindingTool(analysisFindings.value || [], args.finding_id || '', {
      level: args.level || 'technical',
    })
  }
  if (name === AI_TOOL_INTERPRET_QUERY) {
    const times = cursors.value || []
    let lo = null
    let hi = null
    if (times.length >= 2) {
      lo = Math.min(...times)
      hi = Math.max(...times)
    }
    return interpretQueryTool(args.question || '', analysisFindings.value || [], {
      cursorLo: lo,
      cursorHi: hi,
    })
  }
  if (name === AI_TOOL_VALIDATE_EXPERIMENT) {
    let actual = args.actual && typeof args.actual === 'object' ? args.actual : {}
    if (!Object.keys(actual).length) {
      actual = experimentPercentsFromCompare(lastAiCompare)
    }
    return validateExperimentTool(args.expected || {}, actual)
  }
  if (name === AI_TOOL_MANAGE_HYPOTHESES) {
    return manageHypothesesTool(
      analysisFindings.value || [],
      args.hypothesis_id || '',
      args.status || '',
      { reason: args.reason || '', findingId: args.finding_id || '' },
    )
  }
  const findings = analysisFindings.value || []
  if (name === AI_TOOL_PLAN_INVESTIGATION) {
    return planInvestigationTool(findings, {
      question: args.question || '',
      findingId: args.finding_id || '',
    })
  }
  if (name === AI_TOOL_SUGGEST_SCOPE) {
    const times = cursors.value || []
    let lo = null
    let hi = null
    if (times.length >= 2) {
      lo = Math.min(...times)
      hi = Math.max(...times)
    }
    return suggestScopeTool(args.question || '', findings, { cursorLo: lo, cursorHi: hi })
  }
  if (name === AI_TOOL_DETECT_CONTRADICTIONS) {
    return detectContradictionsTool(findings, {
      hypothesis: args.hypothesis || '',
      metrics: args.metrics && typeof args.metrics === 'object' ? args.metrics : {},
    })
  }
  if (name === AI_TOOL_ASSESS_EVIDENCE_SUFFICIENCY) {
    return assessEvidenceSufficiencyTool(findings, { toolsRun: args.tools_run || [] })
  }
  if (name === AI_TOOL_CLUSTER_FINDINGS) return clusterFindingsTool(findings)
  if (name === AI_TOOL_GENERATE_FINGERPRINT) return generateFingerprintTool(findings)
  if (name === AI_TOOL_FIND_SIMILAR_INVESTIGATIONS) {
    let hist = []
    try {
      hist = JSON.parse(localStorage.getItem('btf-experiment-outcomes') || '[]')
    } catch { hist = [] }
    if (Array.isArray(hist)) setExperimentOutcomes(hist)
    return findSimilarInvestigationsTool(findings, {
      history: Array.isArray(hist) ? hist : [],
      limit: args.limit ?? 5,
    })
  }
  if (name === AI_TOOL_REGRESSION_LOCALIZE) {
    const cmp = lastAiCompare || {}
    return regressionLocalizeTool(cmp.candidate || cmp.a || {}, cmp.baseline || cmp.b || {}, {
      findings,
      labelA: args.label_a || 'A',
      labelB: args.label_b || 'B',
    })
  }
  if (name === AI_TOOL_BUILD_CAUSAL_CHAIN) return buildCausalChainTool(findings)
  if (name === AI_TOOL_GENERATE_EXPERIMENT_PLAN) {
    return generateExperimentPlanTool(findings, {
      task: args.task || '',
      limit: args.limit ?? 3,
    })
  }
  if (name === AI_TOOL_RECORD_EXPERIMENT_OUTCOME) {
    const payload = recordExperimentOutcomeTool({
      change: args.change || '',
      predicted: args.predicted || '',
      actual: args.actual || '',
      quality: args.quality || '',
      findings,
    })
    try {
      localStorage.setItem('btf-experiment-outcomes', JSON.stringify(experimentOutcomes()))
    } catch { /* ignore quota */ }
    return payload
  }
  if (name === AI_TOOL_SCORE_INVESTIGATION) {
    return scoreInvestigationMetricsTool(findings, {
      toolsRun: args.tools_run || [],
      elapsedS: args.elapsed_s,
      conclusion: args.conclusion || '',
      confidence: args.confidence || '',
    })
  }
  if (name === AI_TOOL_ANALYZE_TEMPORAL_CAUSALITY) {
    return analyzeTemporalCausalityTool(findings, { task: args.task || '' })
  }
  if (name === AI_TOOL_BUILD_TASK_DEPENDENCY_GRAPH) {
    const times = cursors.value || []
    let lo = null
    let hi = null
    if (times.length >= 2) {
      lo = Math.min(...times)
      hi = Math.max(...times)
    }
    const ctx = dependencyTraceContext(trace.value, lo, hi)
    return buildTaskDependencyGraphTool(findings, {
      task: args.task || '',
      syncHolds: ctx.syncHolds || [],
      preemptions: ctx.preemptions || [],
      migrations: ctx.migrations || [],
      priorityEpisodes: ctx.priorityEpisodes || [],
    })
  }
  if (name === AI_TOOL_DECOMPOSE_RESPONSE_TIME) {
    return decomposeResponseTimeTool(findings, { task: args.task || '' })
  }
  if (name === AI_TOOL_RANK_ROOT_CAUSES) {
    const hyps = Array.isArray(args.hypotheses) ? args.hypotheses : []
    return rankRootCausesTool(findings, { hypotheses: hyps })
  }
  if (name === AI_TOOL_VERIFY_CLAIM) {
    const times = cursors.value || []
    let lo = null
    let hi = null
    if (times.length >= 2) {
      lo = Math.min(...times)
      hi = Math.max(...times)
    }
    return verifyClaimTool(args.claim || '', {
      claimType: args.claim_type || 'causal',
      subject: args.subject || '',
      object: args.object || '',
      evidence: args.evidence || [],
      findings,
      cursorLo: lo,
      cursorHi: hi,
    })
  }
  if (name === AI_TOOL_CHALLENGE_CONCLUSION) {
    return challengeConclusionTool(args.conclusion || '', { findings })
  }
  if (name === AI_TOOL_INVESTIGATION_MEMORY) {
    let hist = []
    try {
      hist = JSON.parse(localStorage.getItem('btf-investigation-memory') || '[]')
    } catch { hist = [] }
    if (Array.isArray(hist)) setInvestigationMemory(hist)
    const payload = investigationMemoryTool(args.action || 'recall', {
      record: args.record && typeof args.record === 'object' ? args.record : null,
      findings,
      limit: args.limit ?? 5,
    })
    try {
      localStorage.setItem('btf-investigation-memory', JSON.stringify(investigationMemoryStore()))
    } catch { /* ignore quota */ }
    return payload
  }
  if (name === AI_TOOL_CLUSTER_INCIDENTS) {
    return clusterIncidentsTool(findings, { windowNs: args.window_ns ?? 1e6 })
  }
  if (name === AI_TOOL_CLOSE_INVESTIGATION) {
    return closeInvestigationTool(args.conclusion || '', {
      findings,
      confidence: args.confidence || '',
    })
  }
  if (name === AI_TOOL_ANALYZE_DISTRIBUTION) {
    const times = cursors.value || []
    let lo = null
    let hi = null
    if (times.length >= 2) {
      lo = Math.min(...times)
      hi = Math.max(...times)
    }
    let values = [...(args.values || [])]
    let metric = args.metric || ''
    let task = args.task || ''
    let source = ''
    let truncated = false
    if (!values.length) {
      const ctx = distributionTraceContext(trace.value, task, metric, lo, hi)
      const harvested = [...(ctx.values || [])]
      if (harvested.length) {
        values = harvested
        metric = ctx.metric || metric
        source = 'btf'
        truncated = Boolean(ctx.truncated)
        if (!task) task = ctx.task || ''
      }
    }
    return analyzeDistributionTool(values, {
      findings,
      metric,
      source,
      task,
      truncated,
    })
  }
  if (name === AI_TOOL_ANALYZE_PERIODICITY) {
    const times = cursors.value || []
    let lo = null
    let hi = null
    if (times.length >= 2) {
      lo = Math.min(...times)
      hi = Math.max(...times)
    }
    const ctx = periodicityTraceContext(trace.value, args.task || '')
    return analyzePeriodicityTool(args.times || [], {
      findings,
      expected: args.expected,
      source: args.source || 'auto',
      durations: args.durations || [],
      tickTimes: ctx.tickTimes || [],
      stiEvents: ctx.stiEvents || [],
      releaseTimes: ctx.releaseTimes || [],
      lo,
      hi,
    })
  }
  if (name === AI_TOOL_SUMMARIZE_INVESTIGATION_CONTEXT) {
    return summarizeInvestigationContextTool(findings, {
      toolsRun: args.tools_run || [],
      conclusion: args.conclusion || '',
    })
  }
  if (name === AI_TOOL_GENERATE_REPORT) {
    return generateReportFinding(analysisFindings.value || [], {
      reportType: args.report_type || 'performance',
      findingId: args.finding_id || '',
    })
  }
  if (name === AI_TOOL_CHECK_BUDGET) {
    return checkBudgetFinding(args.tasks || null, args.budgets || null, {
      findings: analysisFindings.value || [],
    })
  }
  if (name === AI_TOOL_OPTIMIZE) {
    return optimizeFinding(analysisFindings.value || [], {
      limit: args.limit ?? 5,
    })
  }
  if (name === AI_TOOL_REGRESSION_EXPLAIN) {
    return explainAiRegression(args.tab_a || '', args.tab_b || '')
  }
  if (name === AI_TOOL_BOOKMARK_FINDING) {
    const ns = Math.trunc(Number(args.time))
    const note = formatBookmarkLabel(args.kind || 'evidence', args.note || '')
    timelinePanelRef.value?.jumpToNs(ns)
    syncTimelineViewport()
    const existing = (marks.value || []).find(
      m => m.type === 'annotation' && Number(m.ns) === ns && (m.label || '') === note)
    if (existing) return `Annotation already at ${ns}`
    addMarkAtNs(ns, 'annotation', note, { undo: false })
    scheduleSessionSave()
    return `Bookmarked ${ns}: ${note}`
  }
  if (name === AI_TOOL_INVESTIGATION_REPLAY) {
    return investigationReplayFinding(analysisFindings.value || [], args.finding_id || '', {
      conclusion: args.conclusion || '',
      toolsRun: args.tools_run || [],
      evidenceTimes: args.evidence_times || [],
    })
  }
  if (name === AI_TOOL_WHAT_IF) {
    let task = String(args.task || '').trim()
    const change = String(args.change || '')
    if (!task) {
      const parsed = parseWhatIfChange(change)
      task = String(parsed.task || '').trim()
    }
    const scopeOn = activeTab.value?.scopeToCursors !== false
    const range = getStatsRange(cursors.value, scopeOn)
    const simIn = gatherSimulationInputs(trace.value, task, {
      lo: range?.lo ?? null,
      hi: range?.hi ?? null,
      findingsText: buildAiContext().findingsText || '',
    })
    return whatIfEstimate(change, {
      task: simIn.task || task,
      findings: analysisFindings.value || [],
      slices: simIn.slices,
      migrations: simIn.migrations,
      blockingGaps: simIn.blockingGaps,
      coreUtils: simIn.coreUtils,
    })
  }
  if (name === AI_TOOL_OPTIMIZE_EXPERIMENT) {
    let task = String(args.task || '').trim()
    if (!task) {
      const ranked = detectAnomalies(analysisFindings.value || [], { limit: 3 })
      for (const a of ranked.anomalies || []) {
        task = String(a.task || '').trim()
        if (task) break
      }
    }
    const scopeOn = activeTab.value?.scopeToCursors !== false
    const range = getStatsRange(cursors.value, scopeOn)
    const simIn = gatherSimulationInputs(trace.value, task, {
      lo: range?.lo ?? null,
      hi: range?.hi ?? null,
      findingsText: buildAiContext().findingsText || '',
    })
    return optimizeExperimentFinding({
      task: simIn.task || task,
      findings: analysisFindings.value || [],
      slices: simIn.slices,
      migrations: simIn.migrations,
      blockingGaps: simIn.blockingGaps,
      coreUtils: simIn.coreUtils,
      limit: args.limit ?? 5,
    })
  }
  if (name === AI_TOOL_ANALYZE_TRACES) {
    return analyzeAiTraces()
  }
  if (name === AI_TOOL_BASELINE_SCORE) {
    const task = String(args.task || '').trim()
    let profile = args.baseline
    if (!profile || typeof profile !== 'object') profile = loadAiBaselineProfile()
    let snapshot = args.snapshot
    if (!snapshot || typeof snapshot !== 'object') {
      const scopeOn = activeTab.value?.scopeToCursors !== false
      const range = getStatsRange(cursors.value, scopeOn)
      snapshot = buildAiTaskMetricsSnapshot(trace.value, task, {
        lo: range?.lo ?? null,
        hi: range?.hi ?? null,
        findingsText: buildAiContext().findingsText || '',
      })
    }
    return baselineScoreFinding(snapshot, { profile, task })
  }
  if (name === AI_TOOL_RECOMMEND_EXPERIMENTS) {
    return recommendExperimentsFinding(analysisFindings.value || [], {
      findingId: args.finding_id || '',
      task: args.task || '',
      limit: args.limit ?? 5,
    })
  }
  throw new Error(`unknown tool ${name}`)
}

/** Lightweight {task: {wcet_us, blocking_us, migrations}} snapshot for
 * baseline_score, mirroring mainwindow.py _ai_current_task_metrics_snapshot. */
function buildAiTaskMetricsSnapshot(traceObj, taskFilter = '', { lo = null, hi = null, findingsText = '' } = {}) {
  const tasks = {}
  if (!traceObj) return { tasks }
  const taskF = String(taskFilter || '').trim()
  let taskNames = []
  if (taskF) {
    taskNames = [taskF]
  } else {
    const seen = new Set()
    for (const row of budgetTaskRowsFromFindings(analysisFindings.value || [])) {
      const t = String(row.task || '').trim()
      if (t && !seen.has(t)) {
        seen.add(t)
        taskNames.push(t)
      }
    }
  }
  for (const t of taskNames.slice(0, 12)) {
    const metrics = {}
    let label = t
    const execRes = queryRawMetric(traceObj, t, 'execution', { lo, hi, findingsText })
    if (execRes.ok) {
      const d = execRes.data || {}
      if (d.max != null) metrics.wcet_us = Number(d.max) / 1000
      label = String(d.task || label)
    }
    const blockRes = queryRawMetric(traceObj, t, 'blocking', { lo, hi, findingsText })
    if (blockRes.ok) {
      const d = blockRes.data || {}
      if (d.max != null) metrics.blocking_us = Number(d.max) / 1000
    }
    const migRes = queryRawMetric(traceObj, t, 'migrations', { lo, hi, findingsText })
    if (migRes.ok) {
      const d = migRes.data || {}
      if (d.count != null) metrics.migrations = Number(d.count)
    }
    if (Object.keys(metrics).length) tasks[label] = metrics
  }
  return { tasks }
}

/** Merge *traceObj*'s current per-task metrics into the stored baseline. */
function updateAiBaselineFromTrace(traceObj) {
  try {
    const snapshot = buildAiTaskMetricsSnapshot(traceObj)
    if (!Object.keys(snapshot.tasks || {}).length) return
    const profile = updateBaselineProfile(loadAiBaselineProfile(), snapshot)
    saveAiBaselineProfile(profile)
  } catch {
    /* best-effort; never blocks the calling tool */
  }
}

function resolveAiTabRef(ref, defaultIdx) {
  const loaded = tabs.value.filter(t => t?.trace)
  if (loaded.length < 2) throw new Error('Open at least two trace tabs to compare')
  const token = String(ref || '').trim()
  if (!token) {
    return loaded[Math.min(defaultIdx, loaded.length - 1)]
  }
  if (/^\d+$/.test(token)) {
    const n = Number(token)
    // Desktop: 0-based tab-bar index first (must have a loaded trace).
    // Tab ids start at 1 — only used after index lookup fails.
    if (n >= 0 && n < tabs.value.length && tabs.value[n]?.trace) return tabs.value[n]
    if (n >= 0 && n < loaded.length) return loaded[n]
    const byId = loaded.find(t => Number(t.id) === n)
    if (byId) return byId
  }
  const want = token.toLowerCase()
  const exact = loaded.find(t => String(t.name || '').toLowerCase() === want)
  if (exact) return exact
  const part = loaded.find(t => String(t.name || '').toLowerCase().includes(want))
  if (part) return part
  throw new Error(`No loaded tab matching ${JSON.stringify(token)}`)
}

function triggerAiCompare(tabARef, tabBRef) {
  const tabA = resolveAiTabRef(tabARef, 0)
  const tabB = resolveAiTabRef(tabBRef, 1)
  if (tabA.id === tabB.id) throw new Error('tab_a and tab_b must name different traces')
  const ctx = buildAiCompareContext(tabA.id, tabB.id)
  openTraceCompare(tabA.id, tabB.id)
  return {
    ok: true,
    message: ctx.scope || 'Trace Compare',
    data: { csv: ctx.findingsText || '' },
  }
}

function compareAiPerformance(tabARef, tabBRef, { scopeToCursors = true } = {}) {
  const tabA = resolveAiTabRef(tabARef, 0)
  const tabB = resolveAiTabRef(tabBRef, 1)
  if (tabA.id === tabB.id) throw new Error('tab_a and tab_b must name different traces')
  if (!tabA.trace || !tabB.trace) throw new Error('Both tabs must have a loaded trace')
  const ra = scopeToCursors !== false
    ? cursorRangeForCursors(tabA.cursors)
    : { lo: null, hi: null }
  const rb = scopeToCursors !== false
    ? cursorRangeForCursors(tabB.cursors)
    : { lo: null, hi: null }
  const nameA = tabA.name || `Tab ${tabA.id}`
  const nameB = tabB.name || `Tab ${tabB.id}`
  const snapA = traceSummarySnapshot(tabA.trace, ra.lo, ra.hi) || {}
  const snapB = traceSummarySnapshot(tabB.trace, rb.lo, rb.hi) || {}
  updateAiBaselineFromTrace(tabA.trace)
  updateAiBaselineFromTrace(tabB.trace)
  return comparePerformanceTabs(snapA, snapB, { labelA: nameA, labelB: nameB })
}

function explainAiRegression(tabARef, tabBRef) {
  const cmpPayload = compareAiPerformance(tabARef, tabBRef)
  const compare = { ...(cmpPayload.data || {}) }
  if (compare.message == null) compare.message = cmpPayload.message
  if (compare.failed == null && 'failed' in cmpPayload) compare.failed = cmpPayload.failed
  return explainRegressionFromCompare(compare, analysisFindings.value || [])
}

function analyzeAiTraces() {
  const loaded = (tabs.value || []).filter(t => t?.trace)
  if (!loaded.length) throw new Error('No loaded traces')
  const snaps = loaded.map((tab) => {
    const range = cursorRangeForCursors(tab.cursors)
    const name = tab.name || `Tab ${tab.id}`
    updateAiBaselineFromTrace(tab.trace)
    return snapshotFromSummary(
      traceSummarySnapshot(tab.trace, range.lo, range.hi) || {},
      { name },
    )
  })
  return analyzeTracesSnapshots(snaps)
}

function onTraceCompared({ idA, idB, scopeToCursors = true, activateId = null }) {
  try {
    lastAiCompare = compareAiPerformance(idA, idB, {
      scopeToCursors: scopeToCursors !== false,
    })
  } catch {
    /* tabs not ready */
  }
  if (activateId != null && tabs.value.some(t => t.id === activateId)) {
    activeTabId.value = activateId
  }
}

async function onCompareInvestigate({
  activateId = null,
  sectionId = 'response',
  task = '',
  sectionLabel = '',
  tabName = '',
} = {}) {
  if (activateId != null && tabs.value.some(t => t.id === activateId)) {
    activeTabId.value = activateId
  }
  rightPanelTab.value = 'stats'
  const sid = String(sectionId || 'response').trim() || 'response'
  await nextTick()
  statsPanelRef.value?.applyDemoSections?.({ id: sid, expand: true, scroll: sid })
  const taskName = String(task || '').trim()
  if (taskName) {
    await nextTick()
    onAiHighlight(taskName)
  }
  const label = String(sectionLabel || '').trim() || sid
  const name = String(tabName || '').trim()
    || tabs.value.find(t => t.id === activateId)?.name
    || 'trace'
  showToast(`Opened ${label} on ${name}`, 'info')
}

function onCompareSaveBaseline(idA) {
  const tab = tabs.value.find(t => t.id === idA)
  if (tab?.trace) updateAiBaselineFromTrace(tab.trace)
  showToast('Saved Trace A metrics as the regression baseline.', 'info')
}

function onCompareScoreBaseline(idA) {
  const tab = tabs.value.find(t => t.id === idA)
  if (!tab?.trace) return
  const snapshot = buildAiTaskMetricsSnapshot(tab.trace)
  const result = scoreAgainstBaseline(loadAiBaselineProfile(), snapshot)
  showToast(result.message || 'Baseline score', 'info')
}

function openTraceCompare(idA, idB) {
  compareInitialA.value = idA ?? null
  compareInitialB.value = idB ?? null
  compareOpen.value = true
}

function onOpenTraceCompare() {
  openTraceCompare(null, null)
}

function onAiUndoTools() {
  if (_aiGuiUndo) {
    restoreAiGuiSnapshot(_aiGuiUndo)
    _aiGuiUndo = null
  } else {
    onUndo()
  }
}

function onAiResponseLanguage(lang) {
  const next = String(lang || '').trim()
  if (!next || appSettings.aiResponseLanguage === next) return
  appSettings.aiResponseLanguage = next
  saveSettings(appSettings)
}

function onDragEnter(e) {
  if (e.dataTransfer?.types?.includes('Files')) {
    _dragDepth++
    dragOver.value = true
  }
}

function onDragOver(e) {
  if (e.dataTransfer?.types?.includes('Files')) {
    e.dataTransfer.dropEffect = 'copy'
    dragOver.value = true
  }
}

function onDragLeave() {
  _dragDepth = Math.max(0, _dragDepth - 1)
  if (_dragDepth === 0) dragOver.value = false
}

async function onFileDrop(e) {
  _dragDepth = 0
  dragOver.value = false
  let files
  try {
    files = await collectDroppedFiles(e.dataTransfer)
  } catch (err) {
    onFileError(err?.message || 'Failed to read dropped files')
    return
  }
  const kind = classifyOpenFiles(files)
  if (kind === 'demo' || kind === 'xtf') {
    try {
      const picked = await classifyPickedOpen(files)
      if (picked?.kind === 'demo' && picked.pack?.traceFile) {
        await startDemoPack(picked.pack)
        return
      }
      if (picked?.kind === 'demo-folder') {
        onDemoFolderNeeded(picked)
        return
      }
      showToast('Demo pack has no .btf / .btf.gz trace', 'error')
    } catch (err) {
      showToast(err?.message || 'Failed to open demo pack', 'error')
    }
    return
  }
  if (kind === 'btf') {
    stopDemo()
    const btfs = [...files.entries()]
      .filter(([k, f]) => isBtfOpenName(f.name) || isBtfOpenName(k))
      .map(([, f]) => f)
    if (!btfs.length) return
    if (btfs.length === 1) {
      onTraceReading({ name: btfs[0].name })
      try {
        const entries = await loadBtfEntriesFromFile(btfs[0])
        await onTracesLoaded({ entries, sourceName: btfs[0].name })
      } catch (err) {
        onFileError(`Failed to read "${btfs[0].name}"${err?.message ? `: ${err.message}` : ''}`)
      }
      return
    }
    try {
      const all = []
      for (const file of btfs) {
        const entries = await loadBtfEntriesFromFile(file)
        all.push(...entries)
      }
      await onTracesLoaded({ entries: all, sourceName: btfs[0].name })
    } catch (err) {
      onFileError(err?.message || 'Failed to read dropped traces')
    }
    return
  }
  showToast(
    files.size
      ? 'Drop a .btf trace, a demo .xml / .xtf, or a pack folder (xml + .btf.gz + voice)'
      : 'Could not read that drop. Drop the pack folder, .xtf, or the .xml and .btf.gz files together.',
    'error',
  )
}

async function onCopyClipboardDirect() {
  const blob = timelineOptions.showCpuLoad
    ? await captureLeftPaneBlob()
    : await timelinePanelRef.value?.captureScreenshotBlob?.()
  if (!blob) {
    showToast('Unable to capture screenshot.', 'error')
    return
  }
  try {
    await navigator.clipboard.write([
      new ClipboardItem({ [blob.type]: blob }),
    ])
    showToast('Copied to clipboard', 'info')
  } catch {
    if (snapshotImageUrl.value) URL.revokeObjectURL(snapshotImageUrl.value)
    snapshotImageUrl.value = URL.createObjectURL(blob)
    snapshotEditorOpen.value = true
    showToast('Clipboard blocked — use Save/Copy in the editor', 'info')
  }
}

async function onCopyScreenshot() {
  const blob = timelineOptions.showCpuLoad
    ? await captureLeftPaneBlob()
    : await timelinePanelRef.value?.captureScreenshotBlob?.()
  if (!blob) {
    showToast('Unable to capture screenshot.', 'error')
    return
  }
  // Open snapshot editor so user can annotate before copying/saving
  if (snapshotImageUrl.value) URL.revokeObjectURL(snapshotImageUrl.value)
  snapshotDownloadFilename.value = timelineOptions.showCpuLoad
    ? 'timeline-with-load.png'
    : 'timeline-snapshot.png'
  snapshotImageUrl.value   = URL.createObjectURL(blob)
  snapshotEditorOpen.value = true
}

function onSnapshotEditorClose() {
  snapshotEditorOpen.value = false
  if (snapshotImageUrl.value) {
    URL.revokeObjectURL(snapshotImageUrl.value)
    snapshotImageUrl.value = null
  }
}

async function onExportSvg() {
  const blob = timelineOptions.showCpuLoad
    ? await captureLeftPaneSvgBlob()
    : timelinePanelRef.value?.captureAsSvg?.()
  if (!blob) {
    showToast('Unable to generate SVG export.', 'error')
    return
  }
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = timelineOptions.showCpuLoad ? 'timeline-with-load.svg' : 'timeline-export.svg'
  a.click()
  URL.revokeObjectURL(url)
}

function onExportBtfSlice() {
  if (!trace.value) {
    showToast('Open a trace before exporting a BTF slice.', 'error')
    return
  }
  const placed = getPlacedCursors(cursors.value).map(Number).filter(Number.isFinite)
  if (placed.length < 2) {
    showToast('Place at least two cursors (C1–Cn) to export that time range.', 'info')
    return
  }
  const lo = Math.min(...placed)
  const hi = Math.max(...placed)
  if (!(hi > lo)) {
    showToast('Earliest and latest cursors must differ.', 'info')
    return
  }
  let text = ''
  let kept = 0
  const src = activeTab.value?.sourceText
  if (src) {
    try {
      const out = filterBtfTextToRange(src, lo, hi)
      text = out.text
      kept = out.kept
    } catch { /* reconstruct */ }
  }
  if (!String(text).trim()) {
    const out = reconstructBtfSlice(trace.value, lo, hi)
    text = out.text
    kept = out.kept
  }
  const base = (activeTab.value?.name || 'selection').replace(/\.btf(\.gz)?$/i, '')
  const blob = new Blob([text], { type: 'text/plain' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${base}_${lo}-${hi}.btf`
  a.click()
  URL.revokeObjectURL(url)
  showToast(`Saved ${kept} event(s) ${lo}–${hi}`, 'info')
}

function onExportPerfetto() {
  if (!trace.value) {
    showToast('Open a trace before exporting Perfetto.', 'error')
    return
  }
  const useViewport = window.confirm(
    'Export the current timeline viewport?\n\n'
    + 'OK — viewport only\n'
    + 'Cancel — full loaded trace',
  )
  let range = {}
  if (useViewport) {
    const vp = timelineViewport.value
    const lo = Math.floor(Number(vp?.timeStart))
    const hi = Math.ceil(Number(vp?.timeEnd))
    if (!(Number.isFinite(lo) && Number.isFinite(hi) && hi > lo)) {
      showToast('Current viewport is empty; export cancelled.', 'error')
      return
    }
    range = { lo, hi }
  }
  const base = (activeTab.value?.name || 'trace').replace(/\.btf$/i, '')
  try {
    downloadPerfetto(trace.value, `${base}.json`, range)
    showToast(
      useViewport
        ? `Perfetto exported (viewport [${range.lo}, ${range.hi}))`
        : 'Perfetto exported (full trace)',
      'info',
    )
  } catch (err) {
    console.error('Perfetto export failed:', err)
    showToast('Perfetto export failed \u2014 try again, or export a Statistics report instead.', 'error')
  }
}

function captureFilter(node) {
  if (!(node instanceof HTMLElement)) return true
  return !node.classList.contains('context-menu') && !node.classList.contains('sti-tooltip')
}

function loadImageFromBlob(blob) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(blob)
    const img = new Image()
    img.onload = () => {
      URL.revokeObjectURL(url)
      resolve(img)
    }
    img.onerror = () => {
      URL.revokeObjectURL(url)
      reject(new Error('image load failed'))
    }
    img.src = url
  })
}

async function stitchImagesVertical(topImg, bottomImg, targetW = null) {
  const w = targetW ?? Math.max(topImg.naturalWidth, bottomImg.naturalWidth)
  if (w <= 0) return null
  const topH = Math.max(1, Math.round(topImg.naturalHeight * (w / topImg.naturalWidth)))
  const botH = Math.max(1, Math.round(bottomImg.naturalHeight * (w / bottomImg.naturalWidth)))
  const out = document.createElement('canvas')
  out.width = w
  out.height = topH + botH
  const ctx = out.getContext('2d')
  if (!ctx) return null
  ctx.drawImage(topImg, 0, 0, w, topH)
  ctx.drawImage(bottomImg, 0, topH, w, botH)
  return await new Promise((resolve) => out.toBlob(resolve, 'image/png'))
}

async function captureLeftPaneBlob() {
  const leftPane = leftPaneRef.value
  const captureW = leftPane?.clientWidth ?? 0

  const timelineBlob = await timelinePanelRef.value?.captureScreenshotBlob?.()
  if (!timelineBlob) return null

  if (!timelineOptions.showCpuLoad) return timelineBlob

  const cpuEl = cpuLoadPanelRef.value?.panelRef
  if (!cpuEl) return timelineBlob

  const cpuH = cpuEl.clientHeight
  if (captureW <= 0 || cpuH <= 0) return timelineBlob

  try {
    const cpuBlob = await domToBlob(cpuEl, {
      cacheBust: true,
      pixelRatio: 1,
      width: captureW,
      height: cpuH,
      filter: captureFilter,
    })
    if (!cpuBlob) return timelineBlob
    const [topImg, bottomImg] = await Promise.all([
      loadImageFromBlob(timelineBlob),
      loadImageFromBlob(cpuBlob),
    ])
    return await stitchImagesVertical(topImg, bottomImg, captureW)
  } catch {
    return timelineBlob
  }
}

async function captureLeftPaneSvgBlob() {
  const root = leftPaneRef.value
  if (!root) return null

  try {
    const dataUrl = await domToSvg(root, {
      cacheBust: true,
      width: root.clientWidth,
      height: root.clientHeight,
      filter: captureFilter,
    })
    const response = await fetch(dataUrl)
    return await response.blob()
  } catch {
    return timelinePanelRef.value?.captureAsSvg?.() || null
  }
}

function onExpandAll() {
  timelinePanelRef.value?.expandAll()
}

function onCollapseAll() {
  timelinePanelRef.value?.collapseAll()
}

function onCpuLoadToggleExpandAll() {
  cpuLoadExpanded.value = !cpuLoadExpanded.value
  autofitCpuLoadPaneHeight()
}

function onTimelineViewportChange(vp) {
  if (!vp) return
  const { programmatic: _programmatic, ...rest } = vp
  if (activeTab.value) Object.assign(activeTab.value.timelineViewport, rest)
  refreshZoomPresetUi()
}

let _cpuVpApplyRaf = null
let _cpuVpPending = null
function onCpuLoadViewportChange(vp) {
  onTimelineViewportChange(vp)
  _cpuVpPending = vp
  if (_cpuVpApplyRaf) return
  _cpuVpApplyRaf = requestAnimationFrame(() => {
    _cpuVpApplyRaf = null
    const pending = _cpuVpPending
    _cpuVpPending = null
    timelinePanelRef.value?.applyViewport?.(pending)
  })
}

function syncTimelineViewport() {
  const vp = timelinePanelRef.value?.getViewport?.()
  if (vp && activeTab.value) Object.assign(activeTab.value.timelineViewport, vp)
}

function applyTimelineViewport() {
  const tab = activeTab.value
  if (!tab?.trace) return
  const panel = timelinePanelRef.value
  if (!panel) return
  if (isRestorableViewport(tab.timelineViewport, tab.trace)) {
    const ok = panel.applyViewport?.(tab.timelineViewport)
    if (!ok) panel.fitToTrace?.()
  } else {
    panel.applyTraceViewport?.() ?? panel.fitToTrace?.()
  }
  syncTimelineViewport()
}

function clearCursors() {
  timelinePanelRef.value?.clearAllCursorsViaHandler()
}

function onDeleteCursor(idx) {
  pushUndoSnapshot()
  const c = [...cursors.value]
  c[idx] = null
  cursors.value = c
}

function pushUndoSnapshot() {
  if (!activeTab.value) return
  tabUndoStack()?.push({
    cursors: cursors.value,
    marks: marks.value,
    markNextId: activeTab.value.markNextId,
  })
}

function applyUndoSnapshot(snap) {
  if (!snap || !activeTab.value) return
  cursors.value = [...snap.cursors]
  marks.value = JSON.parse(JSON.stringify(snap.marks))
  if (snap.markNextId != null) activeTab.value.markNextId = snap.markNextId
  scheduleSessionSave()
  scheduleRender()
}

function onUndo() {
  const stack = tabUndoStack()
  if (!stack) return
  const snap = stack.undo({
    cursors: cursors.value,
    marks: marks.value,
    markNextId: activeTab.value?.markNextId ?? 1,
  })
  if (snap) applyUndoSnapshot(snap)
}

function onRedo() {
  const stack = tabUndoStack()
  if (!stack) return
  const snap = stack.redo({
    cursors: cursors.value,
    marks: marks.value,
    markNextId: activeTab.value?.markNextId ?? 1,
  })
  if (snap) applyUndoSnapshot(snap)
}

function onLabelWidthChange(w, commit = true) {
  const clamped = Math.max(60, Math.min(600, Math.round(w)))
  appSettings.labelWidth = clamped
  setTimelineLayout({ labelW: clamped })
  scheduleRender()
  if (commit) {
    saveSettings(appSettings)
    timelineOptions.layoutRev += 1
  }
}

function clearCpuLoadSelection() {
  pinnedHighlightKey.value = null
  highlightSegment.value = null
  timelineOptions.highlightKey = null
  timelineOptions.highlightSegment = null
  timelineOptions.highlightInterval = null
  timelineOptions.lockedTaskKey = null
  scheduleRender()
  autofitCpuLoadPaneHeight()
}

function onMigratedFilterChange(enabled) {
  timelineOptions.migratedOnlyFilter = !!enabled
  if (enabled) clearHeatmapTaskFilter()
  else {
    timelineOptions.layoutRev += 1
    scheduleRender()
    autofitCpuLoadPaneHeight()
  }
  saveFiltersToActiveTab()
}

let _filterRenderTimer = null
function onTaskFilterChange(text) {
  timelineOptions.taskFilterText = text || ''
  saveFiltersToActiveTab()
  clearTimeout(_filterRenderTimer)
  _filterRenderTimer = setTimeout(() => {
    timelineOptions.layoutRev += 1
    scheduleRender()
    autofitCpuLoadPaneHeight()
  }, 150)
}

/** Core Filter (Legend "Cores" list, Core View only) — narrows Scope to a subset of cores. */
function onCoreFilterChange(coreNames) {
  const tr = trace.value
  const all = tr?.coreNames || []
  const keys = Array.isArray(coreNames) ? coreNames : []
  // Selecting every core is equivalent to no filter — store null (Step-1 "never silently
  // convert" rule doesn't apply here since this is the Filter's own reset, not a different
  // concept taking it over).
  timelineOptions.coreFilterKeys = (keys.length && keys.length < all.length) ? keys : null
  saveFiltersToActiveTab()
  timelineOptions.layoutRev += 1
  scheduleRender()
  autofitCpuLoadPaneHeight()
}

function clearCoreFilter() {
  timelineOptions.coreFilterKeys = null
  saveFiltersToActiveTab()
  timelineOptions.layoutRev += 1
  scheduleRender()
  autofitCpuLoadPaneHeight()
}

function _captureInspectorRestoreSnapshot() {
  syncTimelineViewport()
  if (activeTab.value) {
    _heatmapRestoreSnapshot = {
      viewport: { ...activeTab.value.timelineViewport },
      cursors: [...cursors.value],
      pinnedHighlightKey: pinnedHighlightKey.value,
      highlightSegment: highlightSegment.value
        ? { ...highlightSegment.value } : null,
      highlightKey: timelineOptions.highlightKey,
      lockedTaskKey: timelineOptions.lockedTaskKey,
      viewMode: timelineOptions.viewMode,
    }
  }
}

function onOpenHeatmap() {
  _captureInspectorRestoreSnapshot()
  inspectorMode.value = 'heatmap'
  inspectorFocusPair.value = null
  inspectorOpen.value = true
}

function onOpenPairHeatmap(focus) {
  inspectorMode.value = 'heatmap'
  inspectorFocusPair.value = focus || null
  inspectorOpen.value = true
}

function onOpenPairChord(focus) {
  inspectorMode.value = 'chord'
  inspectorFocusPair.value = focus || null
  inspectorOpen.value = true
}

function onInspectorClose() {
  inspectorOpen.value = false
  inspectorFocusPair.value = null
}

function clearHeatmapTaskFilter() {
  const hadFilter = !!timelineOptions.taskFilterKeys?.length
  const snap = _heatmapRestoreSnapshot
  statsPaused.value = true

  timelineOptions.taskFilterKeys = null
  timelineOptions.heatmapFilterLabel = null
  pinnedHighlightKey.value = null
  timelineOptions.highlightKey = null
  timelineOptions.highlightSegment = null
  timelineOptions.lockedTaskKey = null
  highlightSegment.value = null

  const restored = !!(snap && activeTab.value)
  if (restored) {
    timelineOptions.viewMode = snap.viewMode
    pinnedHighlightKey.value = snap.pinnedHighlightKey
    highlightSegment.value = snap.highlightSegment
    timelineOptions.highlightKey = snap.highlightKey
    timelineOptions.highlightSegment = snap.highlightSegment
    timelineOptions.lockedTaskKey = snap.lockedTaskKey
    cursors.value = [...snap.cursors]
    nextTick(() => {
      timelinePanelRef.value?.applyViewport?.(snap.viewport)
      syncTimelineViewport()
      scheduleRender()
      requestAnimationFrame(() => {
        statsPaused.value = false
      })
    })
  } else {
    clearCursors()
    scheduleRender()
    requestAnimationFrame(() => {
      statsPaused.value = false
    })
  }

  _heatmapRestoreSnapshot = null

  saveFiltersToActiveTab()
  if (hadFilter || restored) showToast('Showing all tasks', 'info')
}

function onCorridorJump(payload) {
  const c = Array(appSettings.maxCursors).fill(null)
  c[0] = payload.binLo
  c[1] = payload.binHi
  cursors.value = c
  // Evidence loop: Scope stats to the corridor bin and open Core-Pair Summary.
  onStatsScopeChange(true)
  if (payload.enableCpuLoad !== false) timelineOptions.showCpuLoad = true
  nextTick(() => {
    timelinePanelRef.value?.zoomToTimeRange(payload.binLo, payload.binHi, 0.05, { programmatic: true })
    if (payload.lockTaskKey) onHighlightClick(payload.lockTaskKey)
    autofitCpuLoadPaneHeight()
    rightPanelTab.value = 'stats'
    statsPanelRef.value?.applyDemoSections?.({
      id: 'core_pairs', expand: true, scroll: 'core_pairs', collapse_others: false,
    })
  })
  showToast(
    `Jumped to hotspot ${payload.pairLabel || ''}`.trim(),
    'info',
  )
}

function onCorridorSpotlight(payload) {
  timelineOptions.viewMode = 'task'
  timelineOptions.migratedOnlyFilter = false
  timelineOptions.taskFilterKeys = payload.mergeKeys
  timelineOptions.heatmapFilterLabel = payload.pairLabel
  if (payload.enableCpuLoad) timelineOptions.showCpuLoad = true
  saveFiltersToActiveTab()

  const c = Array(appSettings.maxCursors).fill(null)
  c[0] = payload.binLo
  c[1] = payload.binHi
  cursors.value = c
  onStatsScopeChange(true)

  highlightSegment.value = null
  timelineOptions.highlightSegment = null

  const lockKey = payload.lockTaskKey
    || (payload.mergeKeys?.length === 1 ? payload.mergeKeys[0] : null)

  nextTick(() => {
    timelinePanelRef.value?.expandCoresForMergeKeys(payload.mergeKeys)
    timelinePanelRef.value?.zoomToTimeRange(payload.binLo, payload.binHi, 0.05, { programmatic: true })
    if (lockKey) {
      onHighlightClick(lockKey)
    } else {
      pinnedHighlightKey.value = null
      timelineOptions.highlightKey = null
      timelineOptions.lockedTaskKey = null
      scheduleRender()
    }
    autofitCpuLoadPaneHeight()
    rightPanelTab.value = 'stats'
    statsPanelRef.value?.applyDemoSections?.({
      id: 'migrations', expand: true, scroll: 'migrations', collapse_others: false,
    })
  })

  const n = payload.mergeKeys?.length || 0
  showToast(
    `Migration Filter: ${payload.pairLabel} · ${n} task${n === 1 ? '' : 's'}. Toolbar or Legend → Clear to show all.`,
    'info',
  )
}

/** Task × Core Filter Timeline — set filter without changing Scope/cursors. */
function onStatsFilterTimeline(payload) {
  timelineOptions.viewMode = 'task'
  timelineOptions.migratedOnlyFilter = false
  timelineOptions.taskFilterKeys = payload.mergeKeys || null
  timelineOptions.heatmapFilterLabel = payload.pairLabel || null
  saveFiltersToActiveTab()
  const lockKey = payload.mergeKeys?.length === 1 ? payload.mergeKeys[0] : null
  if (lockKey) onHighlightClick(lockKey)
}

function onHighlightClick(key) {
  // Task-name clicks act at task scope, so clear any segment lock first.
  const segmentKey = highlightSegment.value?.task ? taskMergeKey(highlightSegment.value.task) : null
  const effectiveKey = pinnedHighlightKey.value ?? segmentKey
  const nextKey = effectiveKey === key ? null : key

  highlightSegment.value = null
  timelineOptions.highlightSegment = null
  pinnedHighlightKey.value = nextKey
  timelineOptions.highlightKey = nextKey
  timelineOptions.lockedTaskKey = nextKey
  // Scroll & center the task row in the timeline
  if (nextKey) timelinePanelRef.value?.scrollToTask(nextKey)
  scheduleRender()
  autofitCpuLoadPaneHeight()
}

function scheduleRender() {
  timelinePanelRef.value?.scheduleRender()
}

function onRightPanelResizeStart(e) {
  _rightPanelResize = { startX: e.clientX, startW: rightPanelWidth.value }
  document.body.classList.add('col-resizing')
  document.addEventListener('mousemove', onRightPanelResizeMove)
  document.addEventListener('mouseup', onRightPanelResizeEnd)
}

function onRightPanelResizeMove(e) {
  if (!_rightPanelResize) return
  const dx = e.clientX - _rightPanelResize.startX
  const nextW = _rightPanelResize.startW - dx
  rightPanelWidth.value = Math.max(RIGHT_PANEL_MIN_W, Math.min(RIGHT_PANEL_MAX_W, nextW))
  scheduleRender()
}

function onRightPanelResizeEnd() {
  _rightPanelResize = null
  document.body.classList.remove('col-resizing')
  document.removeEventListener('mousemove', onRightPanelResizeMove)
  document.removeEventListener('mouseup', onRightPanelResizeEnd)
  scheduleSessionSave()
}

function onCpuLoadResizeStart(e) {
  _cpuLoadUserSized = true
  _cpuLoadResize = { startY: e.clientY, startH: cpuLoadPaneHeight.value }
  document.body.classList.add('row-resizing')
  document.addEventListener('mousemove', onCpuLoadResizeMove)
  document.addEventListener('mouseup', onCpuLoadResizeEnd)
}

function onCpuLoadResizeMove(e) {
  if (!_cpuLoadResize) return
  const dy = _cpuLoadResize.startY - e.clientY
  cpuLoadPaneHeight.value = Math.max(
    CPU_LOAD_PANE_MIN_H,
    Math.min(cpuLoadPaneMaxH(), _cpuLoadResize.startH + dy),
  )
  scheduleRender()
}

function onCpuLoadResizeEnd() {
  _cpuLoadResize = null
  document.body.classList.remove('row-resizing')
  document.removeEventListener('mousemove', onCpuLoadResizeMove)
  document.removeEventListener('mouseup', onCpuLoadResizeEnd)
  scheduleSessionSave()
}

function isTypingTarget(el) {
  if (!el) return false
  const tag = el.tagName
  return el.isContentEditable || tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT'
}

function openHelpDialog() {
  aboutOpen.value = false
  if (settingsOpen.value) onSettingsCancel()
  helpOpen.value = true
}

function openAboutDialog() {
  helpOpen.value = false
  if (settingsOpen.value) onSettingsCancel()
  aboutOpen.value = true
}

function onGlobalKeydown(e) {
  const palMod = e.ctrlKey || e.metaKey
  if (palMod && e.key.toLowerCase() === 'k') {
    e.preventDefault()
    if (paletteOpen.value) closePalette()
    else openPalette()
    return
  }
  if (paletteOpen.value && e.key === 'Escape') {
    e.preventDefault()
    closePalette()
    return
  }
  if (isTypingTarget(e.target)) return

  if (e.key === 'F3') {
    e.preventDefault()
    stepFind(!e.shiftKey)
    return
  }

  const mod = e.ctrlKey || e.metaKey
  if (mod && e.key.toLowerCase() === 'o') {
    e.preventDefault()
    toolbarRef.value?.triggerOpen?.()
    return
  }
  if (mod && e.key === 'Tab') {
    e.preventDefault()
    cycleTraceTab(!e.shiftKey)
    return
  }

  if (e.key === 'Tab') {
    e.preventDefault()
    cycleHighlightedSegment(!e.shiftKey)
    return
  }

  if (e.key === '?' || (e.key === '/' && e.shiftKey)) {
    e.preventDefault()
    aboutOpen.value = false
    helpOpen.value = !helpOpen.value
    return
  }

  if (e.key === 'Escape') {
    if (demoFolderPrompt.value) {
      demoFolderPrompt.value = null
      e.preventDefault()
      return
    }
    if (focusMode.value && !demoRunning.value) {
      setFocusMode(false)
      e.preventDefault()
      return
    }
    if (demoRunning.value) {
      const now = Date.now()
      if (now - _demoEscAt < 2500) {
        stopDemo()
        showToast('Demo stopped', 'info')
      } else {
        _demoEscAt = now
        showToast('Esc: press again to stop the demo', 'info')
      }
      e.preventDefault()
      return
    }
    if (jumpDialogOpen.value) {
      jumpDialogOpen.value = false
      e.preventDefault()
    } else if (inspectorOpen.value) {
      onInspectorClose()
      e.preventDefault()
    } else if (analysisOpen.value) {
      analysisOpen.value = false
      e.preventDefault()
    } else if (settingsOpen.value) {
      onSettingsCancel()
      e.preventDefault()
    } else if (helpOpen.value) {
      helpOpen.value = false
      e.preventDefault()
    } else if (aboutOpen.value) {
      aboutOpen.value = false
      e.preventDefault()
    } else if (snapshotEditorOpen.value) {
      onSnapshotEditorClose()
      e.preventDefault()
    }
    return
  }

  if (demoRunning.value && (e.key === ' ' || e.code === 'Space')) {
    e.preventDefault()
    if (demoNavReady.value) _demoRunner?.togglePause?.()
    return
  }

  if (helpOpen.value || aboutOpen.value || settingsOpen.value
      || jumpDialogOpen.value || snapshotEditorOpen.value || demoFolderPrompt.value) return

  if (mod && e.key === ',') {
    e.preventDefault()
    openSettingsDialog()
    return
  }
  if (mod && e.key.toLowerCase() === 'z' && !e.shiftKey) {
    e.preventDefault()
    onUndo()
    return
  }
  if (mod && (e.key.toLowerCase() === 'y' || (e.shiftKey && e.key.toLowerCase() === 'z'))) {
    e.preventDefault()
    onRedo()
    return
  }

  if (mod && e.key.toLowerCase() === 'f') {
    e.preventDefault()
    focusFindPanel()
    return
  }
  if (mod && e.key.toLowerCase() === 'r') {
    e.preventDefault()
    onZoomRange()
    return
  }
  if (mod && e.key.toLowerCase() === 'g') {
    e.preventDefault()
    if (trace.value) jumpDialogOpen.value = true
    return
  }
  if (mod && e.key === 'Home') {
    e.preventDefault()
    onJumpToTraceStart()
    return
  }
  if (mod && e.key === 'End') {
    e.preventDefault()
    onJumpToTraceEnd()
    return
  }
  if (mod && e.shiftKey && e.key.toLowerCase() === 'c') {
    e.preventDefault()
    onCopyClipboardDirect()
    return
  }
  if (mod && e.key.toLowerCase() === 'w') {
    e.preventDefault()
    if (activeTabId.value) closeTab(activeTabId.value)
    return
  }
  if (mod && e.shiftKey && e.key.toLowerCase() === 's') {
    e.preventDefault()
    onExportSvg()
    return
  }
  if (mod && e.shiftKey && e.key.toLowerCase() === 'e') {
    e.preventDefault()
    onExportPerfetto()
    return
  }
  if (mod && !e.shiftKey && e.key.toLowerCase() === 's') {
    e.preventDefault()
    onCopyScreenshot()
    return
  }
  if (mod && e.key === '0') {
    e.preventDefault()
    onFit()
    return
  }
  if (mod && (e.key === '+' || e.key === '=')) {
    e.preventDefault()
    onZoom(0.7)
    return
  }
  if (mod && (e.key === '-' || e.key === '_')) {
    e.preventDefault()
    onZoom(1.43)
    return
  }
  if (mod && e.shiftKey && e.key.toLowerCase() === 'b') {
    e.preventDefault()
    onAddAnnotationAtCenter()
    return
  }
  if (mod && !e.shiftKey && e.key.toLowerCase() === 'b') {
    e.preventDefault()
    onAddMark()
    return
  }

  if (trace.value && ['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(e.key)) {
    const horiz = (timelineOptions.orientation || 'h') === 'h'
    const timeKeys = horiz ? ['ArrowLeft', 'ArrowRight'] : ['ArrowUp', 'ArrowDown']
    const rowKeys = horiz ? ['ArrowUp', 'ArrowDown'] : ['ArrowLeft', 'ArrowRight']
    if (e.shiftKey && timeKeys.includes(e.key)) {
      e.preventDefault()
      timelinePanelRef.value?.jumpSegmentBoundary(e.key === timeKeys[1])
      syncTimelineViewport()
      return
    }
    if (timeKeys.includes(e.key)) {
      e.preventDefault()
      timelinePanelRef.value?.scrollTimeAxis(e.key === timeKeys[1] ? 0.2 : -0.2)
      syncTimelineViewport()
      return
    }
    if (rowKeys.includes(e.key)) {
      e.preventDefault()
      timelinePanelRef.value?.scrollRowAxis(e.key === rowKeys[1] ? 0.2 : -0.2)
      return
    }
  }

  const key = e.key.toLowerCase()
  if (key === 'c' && !mod) {
    e.preventDefault()
    if (e.shiftKey) clearCursors()
    else timelinePanelRef.value?.placeCursorAtCenter(e.shiftKey)
    return
  }

  switch (key) {
    case '1':
      timelineOptions.viewMode = 'task'
      persistTimelineViewPrefs()
      e.preventDefault()
      break
    case '2':
      timelineOptions.viewMode = 'core'
      persistTimelineViewPrefs()
      e.preventDefault()
      break
    case 'h':
      if (!mod) {
        timelineOptions.orientation = 'h'
        persistTimelineViewPrefs()
        e.preventDefault()
      }
      break
    case 'v':
      timelineOptions.orientation = 'v'
      persistTimelineViewPrefs()
      e.preventDefault()
      break
    case 'g':
      if (!mod) {
        timelineOptions.showGrid = !timelineOptions.showGrid
        persistTimelineViewPrefs()
        e.preventDefault()
      }
      break
    case 'i':
      timelineOptions.showSti = !timelineOptions.showSti
      persistTimelineViewPrefs()
      e.preventDefault()
      break
    case 'd':
      timelineOptions.darkMode = !timelineOptions.darkMode
      persistTimelineViewPrefs()
      e.preventDefault()
      break
    case 'b':
      if (!mod && !e.shiftKey) {
        onAddMark()
        e.preventDefault()
      } else if (!mod && e.shiftKey) {
        onClearBookmarks()
        e.preventDefault()
      }
      break
    case 'a':
      if (!mod && !e.shiftKey) {
        onAddAnnotationAtCenter()
        e.preventDefault()
      } else if (!mod && e.shiftKey) {
        onClearAnnotations()
        e.preventDefault()
      }
      break
    case 'f':
      if (!mod) {
        onFit()
        e.preventDefault()
      }
      break
    case 's':
      if (!mod) {
        onCopyScreenshot()
        e.preventDefault()
      }
      break
    case '+':
    case '=':
      onZoom(0.7)
      e.preventDefault()
      break
    case '-':
    case '_':
      onZoom(1.43)
      e.preventDefault()
      break
  }
}

// ---- Auto-load embedded example on startup --------------------------------
async function loadExampleBtf() {
  if (typeof DecompressionStream === 'undefined') {
    showToast('Demo trace loading requires gzip decompression support. Open a .btf file directly instead.', 'error')
    return
  }

  loading.value = true
  loadingPhase.value = 'read'
  loadingPct.value = 1
  loadingMsg.value = LOADING_STAGES.demo
  loadingFileName.value = 'example-2cores.btf.gz'
  await new Promise(r => requestAnimationFrame(r))

  // Decode base64 → gzip bytes → UTF-8 text.
  const binStr  = atob(exampleBtfB64)
  const bytes   = new Uint8Array(binStr.length)
  for (let i = 0; i < binStr.length; i++) bytes[i] = binStr.charCodeAt(i)

  const compressed = new Blob([bytes], { type: 'application/gzip' })
  const decompressedStream = compressed.stream().pipeThrough(new DecompressionStream('gzip'))
  const text = await new Response(decompressedStream).text()
  await onTraceLoaded({ text, name: 'example-2cores.btf.gz' })
}

function onLoadDemo() {
  stopDemo()
  loadExampleBtf().catch((err) => {
    console.error('Demo load failed:', err)
    showToast('Failed to load demo trace: ' + (err?.message || String(err)), 'error')
    loading.value = false
  })
}

async function restoreSessionTabs(saved) {
  const names = saved?.openTabNames
  if (!Array.isArray(names) || !names.length) return

  loading.value = true
  loadingPhase.value = 'open'
  loadingMsg.value = LOADING_STAGES.restoring
  try {
    for (const name of names) {
      const packed = await getTrace(name)
      if (!packed) continue
      const state = _savedTabStateByTraceName[name] ?? null
      await attachParsedTrace(name, packed, { savedState: state, fromSession: true })
    }
    const activeName = saved.activeTabName
    if (activeName) {
      const tab = tabs.value.find(t => t.name === activeName)
      if (tab) activeTabId.value = tab.id
    }
  } catch (err) {
    console.warn('Session restore failed:', err)
  } finally {
    loading.value = false
    loadingPct.value = 0
    loadingMsg.value = ''
  }
}

onMounted(async () => {
  applyAppSettings(loadSettings(), { silent: true })
  let saved = loadSession()
  if (!saved?.openTabNames?.length) {
    const fromOpfs = await loadSessionOpfs()
    if (fromOpfs?.openTabNames?.length) saved = fromOpfs
  }
  _savedTabStateByTraceName = mergeLegacyTabFilters(
    saved?.tabStateByTraceName,
    saved?.tabFiltersByTraceName,
  )
  if (saved?.timelineOptions) {
    Object.assign(timelineOptions, saved.timelineOptions)
    syncTimelineOptionsFromSettings()
  }
  applySavedLayout(saved?.layout, {
    rightPanelWidth,
    cpuLoadPaneHeight,
    sectionHeights: statsSectionHeights,
    setCpuLoadUserSized: () => { _cpuLoadUserSized = true },
  }, {
    rightPanelWidth: RIGHT_PANEL_WIDTH,
  })
  rightPanelTab.value = firstVisibleRightPanelTab(appSettings)
  window.addEventListener('keydown', onGlobalKeydown)
  await restoreSessionTabs(saved)
  if (saved?.aiCase) {
    await nextTick()
    aiPanelRef.value?.restoreInvestigation?.(saved.aiCase)
  }
  if (saved?.findingsTriage) {
    findingsTriageState.value = normalizeTriageState(saved.findingsTriage)
  }
  // Auto-load the demo trace only when explicitly requested via ?demo in the URL.
  if (new URLSearchParams(window.location.search).has('demo')) {
    onLoadDemo()
  }
})

onBeforeUnmount(() => {
  if (_statusBarFlashTimer) {
    clearTimeout(_statusBarFlashTimer)
    _statusBarFlashTimer = 0
  }
  if (_parseWorker) {
    _parseWorker.terminate()
    _parseWorker = null
  }
  import('./utils/statsWorkerClient.js').then(m => m.terminateStatsWorker()).catch(() => {})
  onRightPanelResizeEnd()
  onCpuLoadResizeEnd()
  if (_cpuVpApplyRaf) {
    cancelAnimationFrame(_cpuVpApplyRaf)
    _cpuVpApplyRaf = null
  }
  _cpuVpPending = null
  stopDemo()
  if (demoRecording.value) {
    _demoRecorder?.stop?.().catch(() => {})
    _demoRecorder = null
    demoRecording.value = false
  }
  window.removeEventListener('keydown', onGlobalKeydown)
})

// ---- Marks (bookmarks + annotations) -------------------------------------
const MARK_TOGGLE_TOLERANCE_PX = 8   // matches desktop's cursor_drag_threshold

/** Pixel position of *ns* in the current viewport, or null if unknown. */
function _nsToViewportPx(ns) {
  const vp = timelinePanelRef.value?.getViewport?.()
  if (!vp) return null
  const span = vp.timeEnd - vp.timeStart
  if (!(span > 0)) return null
  const horiz = (timelineOptions.orientation || 'h') === 'h'
  const px = horiz ? (vp.canvasW || 1) : (vp.canvasH || 1)
  return (ns - vp.timeStart) * (px / span)
}

/** Remove a bookmark/annotation already near *ns* instead of stacking a
 * duplicate — matches the cursor 'C' toggle (press again to clear).
 * Returns true if an existing mark was removed. */
function _toggleMarkAt(type, ns) {
  const px = _nsToViewportPx(ns)
  if (px == null) return false
  const hit = marks.value.find(m => m.type === type
    && Math.abs((_nsToViewportPx(m.ns) ?? Infinity) - px) <= MARK_TOGGLE_TOLERANCE_PX)
  if (!hit) return false
  pushUndoSnapshot()
  marks.value = marks.value.filter(m => m.id !== hit.id)
  return true
}

function onAddMark() {
  // Priority: mouse hover position → last-moved/placed cursor → viewport center
  if (!trace.value) return
  const hoverNs  = timelinePanelRef.value?.getHoverTime?.() ?? null
  const cursorNs = timelinePanelRef.value?.getLastActiveCursorTime?.() ?? null
  const ns = hoverNs ?? cursorNs ?? (timelinePanelRef.value?.getViewportCenter?.()
    ?? (trace.value.timeMin + (trace.value.timeMax - trace.value.timeMin) / 2))
  if (_toggleMarkAt('bookmark', ns)) return
  addMarkAtNs(ns, 'bookmark')
}

function onAddAnnotationAtCenter() {
  if (!trace.value) return
  const hoverNs  = timelinePanelRef.value?.getHoverTime?.() ?? null
  const cursorNs = timelinePanelRef.value?.getLastActiveCursorTime?.() ?? null
  const ns = hoverNs ?? cursorNs ?? (timelinePanelRef.value?.getViewportCenter?.()
    ?? (trace.value.timeMin + (trace.value.timeMax - trace.value.timeMin) / 2))
  if (_toggleMarkAt('annotation', ns)) return
  addMarkAtNs(ns, 'annotation')
}

function onAddBookmark(ns) {
  // Called from TimelinePanel right-click context menu
  addMarkAtNs(ns, 'bookmark')
}

function onAddAnnotation(ns) {
  addMarkAtNs(ns, 'annotation')
}

function addMarkAtNs(ns, type = 'bookmark', label = '', { undo = true } = {}) {
  if (!trace.value || !activeTab.value) return
  if (undo) pushUndoSnapshot()
  const clamped = Math.max(trace.value.timeMin, Math.min(trace.value.timeMax, ns))
  marks.value.push({
    id: activeTab.value.markNextId++,
    ns: clamped,
    label: label || '',
    type: type === 'annotation' ? 'annotation' : 'bookmark',
  })
  marks.value.sort((a, b) => a.ns - b.ns)
}

function addAnnotationAtNs(ns, note) {
  if (!trace.value || !activeTab.value) return null
  const clamped = Math.max(trace.value.timeMin, Math.min(trace.value.timeMax, ns))
  const label = note || ''
  const existing = marks.value.find(
    m => m.type === 'annotation' && m.ns === clamped && (m.label || '') === label)
  if (existing) return existing.id
  const annId = activeTab.value.markNextId
  addMarkAtNs(clamped, 'annotation', label)
  return annId
}

function onDeleteMark(id) {
  pushUndoSnapshot()
  marks.value = marks.value.filter(m => m.id !== id)
}

function onMoveMark({ id, ns }) {
  if (!trace.value) return
  const m = marks.value.find(mk => mk.id === id)
  if (!m) return
  const clamped = Math.max(trace.value.timeMin, Math.min(trace.value.timeMax, ns))
  m.ns = clamped
  marks.value.sort((a, b) => a.ns - b.ns)
}

function onJumpToMark(ns) {
  timelinePanelRef.value?.jumpToNs(ns)
}

let _sessionSaveTimer = null
function scheduleSessionSave() {
  clearTimeout(_sessionSaveTimer)
  _sessionSaveTimer = setTimeout(() => {
    saveFiltersToActiveTab()
    const loadedNames = tabs.value.filter(t => t.trace).map(t => t.name)
    pruneTraces(loadedNames).catch(() => {})
    const snapshot = buildSessionSnapshot({
      timelineOptions,
      layout: {
        rightPanelWidth: rightPanelWidth.value,
        cpuLoadPaneHeight: cpuLoadPaneHeight.value,
        sectionHeights: { ...statsSectionHeights.value },
      },
      tabs: tabs.value,
      activeTabId: activeTabId.value,
      aiCase: aiPanelRef.value?.investigationSnapshot?.() || null,
      findingsTriage: findingsTriageState.value,
    })
    _savedTabStateByTraceName = snapshot.tabStateByTraceName ?? {}
    saveSession(snapshot)
    saveSessionOpfs(snapshot).catch(() => {})
  }, 400)
}

function onUpdateMarkLabel({ id, label }) {
  const m = marks.value.find(m => m.id === id)
  if (m) m.label = label
}

function onImportMarks(imported) {
  if (!activeTab.value) return
  pushUndoSnapshot()
  for (const { ns, label, type } of imported) {
    marks.value.push({
      id: activeTab.value.markNextId++,
      ns,
      label: label || '',
      type: type === 'annotation' ? 'annotation' : 'bookmark',
    })
  }
  marks.value.sort((a, b) => a.ns - b.ns)
}

function onClearBookmarks() {
  if (!marks.value.some(m => m.type !== 'annotation')) return
  pushUndoSnapshot()
  marks.value = marks.value.filter(m => m.type === 'annotation')
}

function onClearAnnotations() {
  if (!marks.value.some(m => m.type === 'annotation')) return
  pushUndoSnapshot()
  marks.value = marks.value.filter(m => m.type !== 'annotation')
}

function onClearAllMarks() {
  const hasCursors = cursors.value.some(c => c != null)
  const hasMarks = marks.value.length > 0
  if (!hasCursors && !hasMarks) return
  pushUndoSnapshot()
  if (hasCursors) {
    cursors.value = Array(appSettings.maxCursors).fill(null)
  }
  if (hasMarks) marks.value = []
}

function onExportSession() {
  if (!activeTab.value) return
  saveFiltersToActiveTab()
  const payload = buildPortableSession({
    traceName: activeTab.value.name,
    cursors: cursors.value,
    marks: marks.value,
    markNextId: activeTab.value.markNextId,
    timelineViewport: { ...timelineViewport.value },
    timelineOptions,
    tabFilters: activeTab.value,
    findQuery: findQuery.value,
    findMode: findMode.value,
    pinnedHighlightKey: pinnedHighlightKey.value,
    scopeToCursors: activeTab.value.scopeToCursors !== false,
    openPlot: activeTab.value.openPlot ?? null,
    statsSectionCollapsed: appSettings.statsSectionCollapsed ?? null,
  })
  const base = (activeTab.value.name || 'trace').replace(/\.btf$/i, '')
  downloadPortableSession(payload, `${base}-session.json`)
  showToast('Session exported', 'info')
}

async function onExportEvidencePack() {
  if (!activeTab.value || !trace.value) {
    showToast('Open a trace first', 'info')
    return
  }
  saveFiltersToActiveTab()
  const session = buildPortableSession({
    traceName: activeTab.value.name,
    cursors: cursors.value,
    marks: marks.value,
    markNextId: activeTab.value.markNextId,
    timelineViewport: { ...timelineViewport.value },
    timelineOptions,
    tabFilters: activeTab.value,
    findQuery: findQuery.value,
    findMode: findMode.value,
    pinnedHighlightKey: pinnedHighlightKey.value,
    scopeToCursors: activeTab.value.scopeToCursors !== false,
    openPlot: activeTab.value.openPlot ?? null,
    statsSectionCollapsed: appSettings.statsSectionCollapsed ?? null,
  })
  const findingsText = formatAnalysisFindingsText(
    analysisFindings.value || [],
    analysisScopeLabel.value,
  )
  const base = (activeTab.value.name || 'trace').replace(/\.btf(\.gz)?$/i, '')
  const { filename, blob } = buildEvidencePackZip({
    baseName: base,
    findingsText,
    sessionJson: JSON.stringify(session, null, 2),
    notes: `Trace: ${activeTab.value.name}\nScope: ${analysisScopeLabel.value || 'full trace'}\n`
      + 'Re-open the .btf in BTFViewer and Import Session to restore cursors/marks.\n',
  })
  downloadBlob(blob, filename)
  showToast('Evidence pack downloaded', 'info')
}

async function onImportSession(file) {
  if (!activeTab.value) return
  try {
    const text = await file.text()
    const data = parsePortableSession(text)
    if (data.traceName && activeTab.value.name && data.traceName !== activeTab.value.name) {
      showToast(`Session is for "${data.traceName}" (current: ${activeTab.value.name})`, 'info')
    }
    pushUndoSnapshot()
    const needed = sessionCursorsSlotCount(data, appSettings.maxCursors)
    if (needed > appSettings.maxCursors) {
      appSettings.maxCursors = needed
      saveSettings(appSettings)
    }
    applyPortableSession(activeTab.value, data, timelineOptions, trace.value)
    if (data.statsSectionCollapsed !== undefined) {
      appSettings.statsSectionCollapsed = mergeSectionCollapsed(
        activeTab.value.statsSectionCollapsed || data.statsSectionCollapsed)
      saveSettings(appSettings)
    }
    syncFiltersFromTab(activeTab.value)
    resizeTabCursors(tabs.value, appSettings.maxCursors)
    nextTick(() => {
      applyTimelineViewport()
      timelineOptions.layoutRev += 1
      if (findQuery.value) recomputeFind()
      scheduleRender()
      autofitCpuLoadPaneHeight()
    })
    showToast('Session imported', 'info')
  } catch (err) {
    showToast(err?.message || 'Failed to import session', 'error')
  }
}

watch(
  () => ({
    activeTabId: activeTabId.value,
    cursors: cursors.value,
    marks: marks.value,
    viewport: activeTab.value?.timelineViewport,
    findQuery: findQuery.value,
    findMode: findMode.value,
  }),
  scheduleSessionSave,
  { deep: true },
)
</script>

<style>
/* ---- CSS custom properties (dark / light themes) ---- */
:root {
  --bg:            #1E1E1E;
  --panel-bg:      #252526;
  --ruler-bg:      #2D2D2D;
  --tb-bg:         #2D2D2D;
  --tb-btn-hover:  rgba(255,255,255,0.08);
  --tb-btn-active: rgba(79,139,255,0.2);
  --border:        #3C3C3C;
  --fg:            #D4D4D4;
  --fg-dim:        #858585;
  --accent:        #4F8BFF;
  /* Trace Compare A/B identity anchor (Baseline / Candidate). Blue + amber is a
     colour-blind-safe pair; the tables also carry ▲/▼ glyphs so colour is never
     load-bearing. Revisit against Settings → colourblindSafe if the palette shifts. */
  --cmp-a:         #4F8BFF;
  --cmp-b:         #E0A34E;
  --tick-dist-icon:  #FFB74D;
  --tick-dist-fg:    #FFCC80;
  --tick-dist-border: color-mix(in srgb, #FFB74D 55%, #3C3C3C);
  --tick-dist-bg:    color-mix(in srgb, #FFB74D 16%, transparent);
  --sb-thumb:       rgba(160, 160, 160, 0.40);
  --sb-thumb-hover: rgba(160, 160, 160, 0.65);
  --row-even:       #252526;
  --row-odd:        #2D2D2D;
  --row-sti:        #1A1A2E;
  --row-core:       #2A2A3E;
  --row-core-sub-even: #1E1E2C;
  --row-core-sub-odd:  #232330;
  --panel:         #252526;
  --panel-inset:   #1a2230;
  --panel-btn-bg:  #243044;
  --text:          #D4D4D4;
  --muted:         #858585;
  --ai-user-bg:    #1e3348;
  --ai-user-fg:    #e8eef7;
  --ai-asst-bg:    #1a2620;
  --ai-asst-fg:    #d5e4f7;
  --ai-ev-bg:      #1f2430;
  --ai-ev-fg:      #c5d0dc;
  --ai-md-th-bg:   #243044;
  --ai-md-th-fg:   #e8eef6;
  --ai-md-td-bg:   #1a2230;
  --ai-md-td-fg:   #dbe2ea;
  --ai-tool-bg:    #2a2418;
  --ai-tool-fg:    #e6d48a;
  --analysis-ok:   #7dcea0;
  --analysis-warn: #e67e22;
  --analysis-err:  #e74c3c;
  /* Step 3 typography + semantic roles (dark defaults on :root) */
  --type-section: calc(var(--ui-font-size, 13px) * 1.05);
  --type-body: var(--ui-font-size, 13px);
  --type-meta: max(11px, calc(var(--ui-font-size, 13px) * 0.92));
  --type-min: 11px;
  --semantic-error: var(--analysis-err);
  --semantic-warning: var(--analysis-warn);
  --semantic-improvement: var(--analysis-ok);
  --semantic-focus: var(--accent);
  --semantic-selection: color-mix(in srgb, var(--accent) 35%, transparent);
  /* Statistics category badges (dark) — lockstep with config.py palette */
  --badge-overview-bg: #26313B;
  --badge-overview-fg: #C3CED8;
  --badge-overview-border: #4A5966;
  --badge-triage-bg: #3A3020;
  --badge-triage-fg: #E2C27C;
  --badge-triage-border: #675630;
  --badge-timing-bg: #243449;
  --badge-timing-fg: #A9C5E8;
  --badge-timing-border: #47658A;
  --badge-sched-bg: #302C44;
  --badge-sched-fg: #C1B7E3;
  --badge-sched-border: #5D557B;
  --badge-sync-bg: #203A38;
  --badge-sync-fg: #9DD0CA;
  --badge-sync-border: #426C68;
  --badge-detail-bg: #303337;
  --badge-detail-fg: #C0C4C9;
  --badge-detail-border: #565B61;
  /* Statistics Scope chip (dark) — lockstep with config.py stats_meta_chip_colors */
  --badge-scope-fg: #9EC5E8;
  --badge-scope-bg: #283A47;
  --badge-scope-border: #3A6A8A;
  /* Statistics Filtered chip (dark) — lockstep with config.py stats_meta_chip_colors("filtered") */
  --badge-filtered-fg: #E0C070;
  --badge-filtered-bg: #3A3420;
  --badge-filtered-border: #8A7040;

  /* ---- App-wide layout scale: spacing / radius / type faces / surfaces ----
     (introduced with the right-panel redesign, now used by the activity rail,
     context strip, cards and panels alike — hence the --app-* name.) */
  --sp-1: 4px;
  --sp-2: 8px;
  --sp-3: 12px;
  --sp-4: 16px;
  --sp-5: 24px;
  --app-r-1: 6px;
  --app-r-2: 9px;
  --font-ui: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  --font-mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  /* Surfaces derived from the panel tokens, biased toward the accent.
     Redeclared verbatim in the light block below so the color-mix()s
     re-resolve against the light --panel-bg / --bg / --accent. */
  --app-surface:   var(--panel-bg);
  --app-surface-2: color-mix(in srgb, var(--panel-bg) 78%, var(--bg));
  --app-surface-3: color-mix(in srgb, var(--accent) 9%, var(--panel-bg));
  --app-border-soft: color-mix(in srgb, var(--border) 55%, transparent);
  --app-sel-bg:    color-mix(in srgb, var(--accent) 12%, transparent);
  --app-hover-bg:  color-mix(in srgb, var(--accent) 7%, transparent);
  --app-accent-line: color-mix(in srgb, var(--accent) 40%, transparent);
}

.app:not(.dark),
body:has(.app:not(.dark)) {
  --bg:            #FFFFFF;
  --panel-bg:      #F5F5F5;
  /* Re-resolve the accent/panel-derived surfaces against the light palette
     (a bare :root color-mix(var(--panel-bg)…) stays stuck on its dark value). */
  --app-surface:   var(--panel-bg);
  --app-surface-2: color-mix(in srgb, var(--panel-bg) 78%, var(--bg));
  --app-surface-3: color-mix(in srgb, var(--accent) 9%, var(--panel-bg));
  --app-border-soft: color-mix(in srgb, var(--border) 55%, transparent);
  --app-sel-bg:    color-mix(in srgb, var(--accent) 12%, transparent);
  --app-hover-bg:  color-mix(in srgb, var(--accent) 7%, transparent);
  --app-accent-line: color-mix(in srgb, var(--accent) 40%, transparent);
  --ruler-bg:      #EEEEEE;
  --tb-bg:         #F0F0F0;
  --tb-btn-hover:  rgba(0,0,0,0.06);
  --tb-btn-active: rgba(0,80,200,0.15);
  --border:        #DDDDDD;
  --fg:            #1E1E1E;
  --fg-dim:        #666666;
  --accent:        #0066CC;
  --cmp-a:         #1D6FD0;
  --cmp-b:         #C77A12;
  --tick-dist-icon:  #E65100;
  --tick-dist-fg:    #BF360C;
  --tick-dist-border: color-mix(in srgb, #E65100 45%, #DDDDDD);
  --tick-dist-bg:    color-mix(in srgb, #E65100 10%, #FFFFFF);
  --sb-thumb:       rgba(80, 80, 80, 0.38);
  --sb-thumb-hover: rgba(80, 80, 80, 0.62);
  --row-even:       #FFFFFF;
  --row-odd:        #F2F2F2;
  --row-sti:        #EEF3F8;
  --row-core:       #E7ECF3;
  --row-core-sub-even: #F7F9FC;
  --row-core-sub-odd:  #EEF2F7;
  --panel:         #F5F5F5;
  --panel-inset:   #FFFFFF;
  --panel-btn-bg:  #E8E8E8;
  --text:          #1E1E1E;
  --muted:         #666666;
  --ai-user-bg:    #e8f1fa;
  --ai-user-fg:    #1E1E1E;
  --ai-asst-bg:    #e8f6ee;
  --ai-asst-fg:    #1E1E1E;
  --ai-ev-bg:      #eef0f3;
  --ai-ev-fg:      #1E1E1E;
  --ai-md-th-bg:   #E8EEF4;
  --ai-md-th-fg:   #1E1E1E;
  --ai-md-td-bg:   #FFFFFF;
  --ai-md-td-fg:   #1E1E1E;
  --ai-tool-bg:    #fff8e8;
  --ai-tool-fg:    #6b5508;
  --analysis-ok:   #166534;
  --analysis-warn: #9a4d00;
  --analysis-err:  #c0392b;
  /* Statistics category badges (light) — lockstep with config.py palette */
  --badge-overview-bg: #E8EDF2;
  --badge-overview-fg: #536475;
  --badge-overview-border: #B8C4CF;
  --badge-triage-bg: #F7EDD7;
  --badge-triage-fg: #8A641F;
  --badge-triage-border: #DFC68E;
  --badge-timing-bg: #E3EDF9;
  --badge-timing-fg: #426A9E;
  --badge-timing-border: #AFC7E5;
  --badge-sched-bg: #ECE8F7;
  --badge-sched-fg: #665A98;
  --badge-sched-border: #C5BCE0;
  --badge-sync-bg: #E2F1EF;
  --badge-sync-fg: #39746F;
  --badge-sync-border: #ADD2CD;
  --badge-detail-bg: #ECEDEF;
  --badge-detail-fg: #656B72;
  --badge-detail-border: #C8CBD0;
  /* Statistics Scope chip (light) — lockstep with config.py stats_meta_chip_colors */
  --badge-scope-fg: #1A5276;
  --badge-scope-bg: #D6EAF8;
  --badge-scope-border: #85C1E9;
  /* Statistics Filtered chip (light) — lockstep with config.py stats_meta_chip_colors("filtered") */
  --badge-filtered-fg: #7D6608;
  --badge-filtered-bg: #F9E79F;
  --badge-filtered-border: #D4AC0D;
  /* Step 3 typography + semantic roles */
  --type-section: calc(var(--ui-font-size, 13px) * 1.05);
  --type-body: var(--ui-font-size, 13px);
  --type-meta: max(11px, calc(var(--ui-font-size, 13px) * 0.92));
  --type-min: 11px;
  --semantic-error: var(--analysis-err);
  --semantic-warning: var(--analysis-warn);
  --semantic-improvement: var(--analysis-ok);
  --semantic-focus: var(--accent);
  --semantic-selection: color-mix(in srgb, var(--accent) 35%, transparent);
}

* { box-sizing: border-box; margin: 0; padding: 0; }

/* Keyboard focus — keep investigation controls accessible without pointer */
:focus-visible {
  outline: 2px solid var(--semantic-focus, var(--accent));
  outline-offset: 2px;
}

button:focus:not(:focus-visible),
a:focus:not(:focus-visible),
input:focus:not(:focus-visible),
select:focus:not(:focus-visible),
textarea:focus:not(:focus-visible) {
  outline: none;
}

/* ---- Native scrollbar theming (all panels) ---- */
* {
  scrollbar-width: thin;
  scrollbar-color: var(--sb-thumb) transparent;
}
*::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}
*::-webkit-scrollbar-track {
  background: transparent;
}
*::-webkit-scrollbar-thumb {
  background: var(--sb-thumb);
  border-radius: 4px;
}
*::-webkit-scrollbar-thumb:hover {
  background: var(--sb-thumb-hover);
}
*::-webkit-scrollbar-corner {
  background: transparent;
}

body {
  background: var(--bg);
  color: var(--fg);
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  font-size: var(--ui-font-size);
  overflow: hidden;
}

.app {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: var(--bg);
  color: var(--fg);
}

.trace-quality-banner {
  flex: 0 0 auto;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  font-size: 12px;
  background: #5c3d00;
  color: #ffe8a3;
  border-bottom: 1px solid #8a6200;
}

.trace-quality-details {
  padding: 8px 12px 10px;
  font-size: 11px;
  background: rgba(92, 61, 0, 0.25);
  border-bottom: 1px solid #8a6200;
}

.trace-quality-group + .trace-quality-group {
  margin-top: 8px;
}

.trace-quality-affected {
  margin-top: 4px;
  opacity: 0.85;
}

.cursor-scope-banner,
.evidence-inspector-bar {
  flex: 0 0 auto;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  font-size: 12px;
  background: #1a3348;
  color: #cdefff;
  border-bottom: 1px solid #2a5a70;
}

.cursor-scope-close {
  /* Match .trace-tab-close (Web tab close affordance). */
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  appearance: none;
  border: none;
  background: transparent;
  color: #cdefff;
  width: 16px;
  height: 16px;
  border-radius: 3px;
  font-size: 14px;
  line-height: 1;
  padding: 0;
  cursor: pointer;
  opacity: 0.65;
}

.cursor-scope-close:hover {
  opacity: 1;
  background: rgba(127, 127, 127, 0.2);
}

.evidence-inspector-text {
  flex: 1 1 auto;
  min-width: 0;
  font-family: monospace;
  font-size: 11px;
  opacity: 0.95;
}

.cursor-scope-warn {
  font-size: 11px;
  opacity: 0.9;
}

/* ---- Unified context strip ----
   The trace-quality, evidence-inspector and cursor-scope bars share one
   bordered zone with a neutral surface; each keeps its semantic colour as a
   left accent stripe instead of a full-width tint. */
.context-strip {
  flex: 0 0 auto;
  display: flex;
  flex-direction: column;
  /* Reads as an extension of the toolbar zone above it; theme-aware (unlike
     --app-surface-2, which is frozen to its dark value in light mode). */
  background: var(--tb-bg);
  border-bottom: 1px solid var(--border);
}

.context-strip .ctx-row {
  background: transparent;
  border-bottom: 0;
  border-left: 3px solid transparent;
  color: var(--fg);
}

.context-strip .ctx-row + .ctx-row {
  border-top: 1px solid var(--app-border-soft);
}

.context-strip .ctx-row--warn {
  border-left-color: #d8a13a;
}

.context-strip .ctx-row--info {
  border-left-color: var(--accent);
}

.context-strip .trace-quality-details {
  background: transparent;
}

.context-strip .cursor-scope-close,
.context-strip .evidence-inspector-text {
  color: var(--fg-dim);
}

.demo-status-banner {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  font-size: 12px;
  background: #1b3a4a;
  color: #cdefff;
  border-bottom: 1px solid #2a5a70;
}

.demo-nav-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  padding: 0;
  border: 0;
  border-radius: 3px;
  background: transparent;
  color: inherit;
  cursor: pointer;
  flex-shrink: 0;
}

.demo-nav-btn:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.14);
}

.demo-nav-btn:disabled {
  opacity: 0.35;
  cursor: default;
}

.demo-nav-btn.is-paused {
  background: rgba(255, 255, 255, 0.18);
}

.demo-status-text {
  flex: 1;
  min-width: 0;
  margin-left: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.demo-lang {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
  margin-left: 6px;
  font-size: 11px;
  opacity: 0.9;
}

.demo-lang-label {
  opacity: 0.7;
}

.demo-lang-select {
  max-width: 7.5rem;
  height: 22px;
  padding: 0 4px;
  border: 1px solid rgba(255, 255, 255, 0.22);
  border-radius: 3px;
  background: rgba(0, 0, 0, 0.18);
  color: inherit;
  font: inherit;
  font-size: 11px;
}

.demo-lang-select.disabled {
  opacity: 0.45;
}

.demo-status-hint {
  flex-shrink: 0;
  margin-left: 8px;
  font-size: 11px;
  opacity: 0.65;
}

.demo-folder-dialog {
  width: min(440px, 92vw);
  background: var(--panel-bg);
  border: 1px solid var(--app-border-soft, var(--border));
  border-radius: 14px;
  box-shadow:
    0 32px 80px -16px rgba(0, 0, 0, 0.5),
    0 0 0 1px color-mix(in srgb, var(--fg) 6%, transparent);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  animation: dialog-pop 0.18s cubic-bezier(0.32, 0.72, 0, 1);
}

.demo-folder-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  border-bottom: 1px solid var(--border);
}

.demo-folder-title {
  font-weight: 600;
  font-size: 14px;
}

.demo-folder-close {
  background: none;
  border: none;
  color: var(--fg-dim);
  cursor: pointer;
  font-size: 16px;
}

.demo-folder-body {
  padding: 14px;
  font-size: 13px;
  line-height: 1.45;
  color: var(--fg);
}

.demo-folder-body code {
  font-size: 12px;
}

.demo-folder-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 10px 14px;
  border-top: 1px solid var(--border);
}

.demo-folder-btn {
  padding: 5px 12px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--panel-bg);
  color: var(--fg);
  font-size: 12px;
  cursor: pointer;
}

.demo-folder-btn.primary {
  background: var(--accent);
  border-color: var(--accent);
  color: #000;
}

.app.drag-over {
  outline: 2px dashed var(--accent);
  outline-offset: -4px;
}

/* Focus mode — everything but the timeline (+ toolbar / status bar) folds away. */
.app.focus-mode .activity-rail,
.app.focus-mode .trace-tabs,
.app.focus-mode .panel-resizer,
.app.focus-mode .right-panel {
  display: none;
}

.focus-exit {
  position: fixed;
  right: 14px;
  bottom: 34px;
  z-index: 40;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--panel-bg);
  color: var(--fg-dim);
  font: inherit;
  font-size: 12px;
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.28);
  cursor: pointer;
  opacity: 0.85;
}

.focus-exit:hover,
.focus-exit:focus-visible {
  opacity: 1;
  color: var(--fg);
  border-color: var(--accent);
  outline: none;
}

.focus-exit svg {
  width: 14px;
  height: 14px;
}

.trace-tabs {
  display: flex;
  align-items: stretch;
  gap: 2px;
  padding: 0 6px;
  background: var(--tb-bg);
  border-bottom: 1px solid var(--border);
  overflow-x: auto;
  flex-shrink: 0;
}

.trace-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 220px;
  padding: 6px 8px 6px 12px;
  border: none;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--fg-dim);
  cursor: pointer;
  font: inherit;
  font-size: 12px;
}

.trace-tab.active {
  color: var(--fg);
  border-bottom-color: var(--accent);
  background: rgba(127, 127, 127, 0.08);
}

.trace-tab-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.trace-tab-close,
.app-close-x {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  appearance: none;
  box-sizing: border-box;
  border: none;
  background: transparent;
  color: inherit;
  width: 16px;
  height: 16px;
  border-radius: 3px;
  font-family: inherit;
  font-size: 14px;
  font-weight: 400;
  line-height: 1;
  padding: 0;
  cursor: pointer;
  opacity: 0.65;
  flex: 0 0 auto;
}

.trace-tab-close:hover,
.app-close-x:hover {
  opacity: 1;
  background: rgba(127, 127, 127, 0.2);
}

.main-area {
  display: flex;
  flex: 1;
  overflow: hidden;
  min-height: 0;
  position: relative;
}

.left-pane {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}

.timeline-wrap {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.panel-resizer-h {
  height: 8px;
  flex-shrink: 0;
  cursor: row-resize;
  position: relative;
  background: transparent;
}

.panel-resizer-h::before {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  top: 3px;
  height: 2px;
  background: transparent;
  transition: background 0.12s ease;
}

.panel-resizer-h:hover::before {
  background: color-mix(in srgb, var(--accent) 50%, var(--border));
}

body.row-resizing,
body.row-resizing * {
  cursor: row-resize !important;
  user-select: none;
}

/* ---- Inline loading: hairline top bar + timeline skeleton ---- */
.load-progressbar {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 2px;
  z-index: 200;
  background: var(--app-hover-bg);
  overflow: hidden;
}

.load-progressbar-fill {
  height: 100%;
  background: var(--accent);
  transition: width 0.25s ease;
}

.load-progressbar-fill.indeterminate {
  width: 40% !important;
  transition: none;
  animation: load-indeterminate 1.1s ease-in-out infinite;
}

@keyframes load-indeterminate {
  0%   { transform: translateX(-120%); }
  100% { transform: translateX(320%); }
}

.timeline-skeleton {
  position: absolute;
  inset: 0;
  z-index: 5;
  display: flex;
  flex-direction: column;
  padding: 8px 8px 8px 0;
  background: var(--bg);
  overflow: hidden;
}

.tl-skel-axis {
  height: 16px;
  margin: 0 8px 6px 76px;
  border-radius: 3px;
  background: var(--app-surface-2);
}

.tl-skel-row {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 0;
  padding: 3px 8px 3px 12px;
}

.tl-skel-label {
  width: 64px;
  height: 12px;
  flex: none;
  border-radius: 3px;
  background: var(--app-surface-2);
}

.tl-skel-track {
  position: relative;
  flex: 1;
  height: 16px;
  border-radius: 3px;
  background: var(--app-surface-2);
  overflow: hidden;
}

.tl-skel-seg {
  position: absolute;
  top: 2px;
  bottom: 2px;
  border-radius: 2px;
  background: var(--app-surface-3);
}

.timeline-skeleton::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(
    90deg,
    transparent 0%,
    color-mix(in srgb, var(--fg) 6%, transparent) 50%,
    transparent 100%
  );
  transform: translateX(-100%);
  animation: tl-skel-shimmer 1.4s ease-in-out infinite;
}

@keyframes tl-skel-shimmer {
  100% { transform: translateX(100%); }
}

@media (prefers-reduced-motion: reduce) {
  .load-progressbar-fill.indeterminate,
  .timeline-skeleton::after { animation: none; }
}

.demo-message-overlay {
  position: absolute;
  inset: 0;
  z-index: 180;
  display: flex;
  align-items: center;
  justify-content: center;
  pointer-events: none;
  overflow: visible;
  padding: 24px;
  box-sizing: border-box;
}

.demo-message-card {
  background: rgba(20, 28, 38, 0.88);
  color: #e8f4ff;
  border: 1px solid #4a6a8a;
  border-radius: 8px;
  padding: 16px 22px;
  max-width: min(640px, calc(100% - 48px));
  box-sizing: border-box;
  font-size: 14px;
  line-height: 1.45;
  text-align: center;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.45);
}

.demo-message-enter-active,
.demo-message-leave-active {
  transition: opacity 0.25s ease, transform 0.25s ease;
}

.demo-message-enter-from,
.demo-message-leave-to {
  opacity: 0;
  transform: translateY(8px);
}

.app:not(.dark) .demo-message-card {
  background: rgba(245, 245, 245, 0.94);
  color: #1e1e1e;
  border-color: #bbb;
}

.dialog-overlay {
  position: absolute;
  inset: 0;
  z-index: 300;
  display: flex;
  align-items: center;
  justify-content: center;
  background: color-mix(in srgb, #000 52%, transparent);
  backdrop-filter: blur(5px) saturate(1.1);
  -webkit-backdrop-filter: blur(5px) saturate(1.1);
}

@keyframes dialog-pop {
  from { opacity: 0; transform: translateY(10px) scale(0.98); }
  to   { opacity: 1; transform: none; }
}

.help-dialog {
  width: min(760px, 92vw);
  max-height: min(82vh, 760px);
  background: var(--panel-bg);
  border: 1px solid var(--app-border-soft, var(--border));
  border-radius: 14px;
  box-shadow:
    0 32px 80px -16px rgba(0, 0, 0, 0.5),
    0 0 0 1px color-mix(in srgb, var(--fg) 6%, transparent);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  animation: dialog-pop 0.18s cubic-bezier(0.32, 0.72, 0, 1);
}

.about-dialog {
  width: min(520px, 92vw);
  max-height: min(82vh, 720px);
  background: var(--panel-bg);
  border: 1px solid var(--app-border-soft, var(--border));
  border-radius: 14px;
  box-shadow:
    0 32px 80px -16px rgba(0, 0, 0, 0.5),
    0 0 0 1px color-mix(in srgb, var(--fg) 6%, transparent);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  animation: dialog-pop 0.18s cubic-bezier(0.32, 0.72, 0, 1);
}

.about-hero {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 24px 24px 20px;
  border-bottom: 1px solid var(--border);
  background: linear-gradient(180deg, color-mix(in srgb, var(--accent) 16%, var(--panel-bg)), var(--panel-bg));
}

.about-icon {
  width: 72px;
  height: 72px;
  line-height: 0;
  filter: drop-shadow(0 2px 8px rgba(0, 0, 0, 0.28));
}

.about-icon svg {
  display: block;
  width: 72px;
  height: 72px;
}

.about-title {
  font-size: 18px;
  font-weight: 700;
}

.about-subtitle {
  color: var(--fg-dim);
  font-size: 12px;
  text-align: center;
}

.about-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 18px 20px;
  overflow: auto;
}

.about-section {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px;
}

.about-section-title {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--fg-dim);
  margin-bottom: 10px;
}

.about-grid {
  display: grid;
  grid-template-columns: 120px 1fr;
  gap: 8px 12px;
}

.about-key {
  color: var(--accent);
  font-weight: 600;
}

.about-footer {
  display: flex;
  justify-content: flex-end;
  padding: 0 20px 18px;
}

.about-close {
  border: 1px solid transparent;
  background: var(--accent);
  color: white;
  border-radius: 8px;
  min-width: 84px;
  height: 34px;
  padding: 0 16px;
  font-weight: 600;
  cursor: pointer;
}

.about-close:hover {
  filter: brightness(1.08);
}

.help-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  border-bottom: 1px solid var(--border);
}

.help-title {
  font-size: 14px;
  font-weight: 700;
}

.help-close {
  border: 1px solid var(--border);
  background: transparent;
  color: var(--fg);
  border-radius: 6px;
  width: 28px;
  height: 28px;
  cursor: pointer;
}

.help-close:hover {
  background: var(--tb-btn-hover);
}

.help-body {
  padding: 14px;
  overflow: auto;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}

.help-section {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px;
}

.help-section-title {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--fg-dim);
  margin-bottom: 8px;
}

.help-grid {
  display: grid;
  grid-template-columns: 140px 1fr;
  gap: 6px 10px;
  align-items: center;
}

.k {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 11px;
  color: var(--accent);
  background: var(--tb-btn-hover);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 2px 6px;
  justify-self: start;
}

@media (max-width: 960px) {
  .right-panel {
    min-width: 280px;
  }

  .panel-page,
  .stats-scroll,
  .ai-panel {
    overflow-x: auto;
  }
}

@media (max-width: 760px) {
  .help-body {
    grid-template-columns: 1fr;
  }

  .about-grid {
    grid-template-columns: 1fr;
  }

  .right-panel {
    min-width: 220px;
  }

  .main-area {
    min-width: 0;
  }

  .stats-table {
    font-size: var(--type-meta, 11px);
  }
}

.status-loading {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  color: var(--fg-dim);
}

.status-loading-spin {
  width: 11px;
  height: 11px;
  flex: none;
  border-radius: 50%;
  border: 2px solid var(--app-accent-line);
  border-top-color: var(--accent);
  animation: status-loading-spin 0.7s linear infinite;
}

@keyframes status-loading-spin {
  100% { transform: rotate(360deg); }
}

.status-loading-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.status-loading-cancel {
  appearance: none;
  margin-left: 8px;
  flex: none;
  font: inherit;
  font-size: var(--type-meta);
  padding: 1px 10px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: transparent;
  color: var(--fg-dim);
  cursor: pointer;
}

.status-loading-cancel:hover,
.status-loading-cancel:focus-visible {
  background: var(--tb-btn-hover);
  color: var(--fg);
  outline: none;
}

@media (prefers-reduced-motion: reduce) {
  .status-loading-spin { animation-duration: 0s; }
}

.first-run-btn {
  font-size: var(--type-meta);
  padding: 4px 10px;
  border-radius: 4px;
  border: 1px solid var(--border);
  background: var(--panel-btn-bg);
  color: var(--fg);
  cursor: pointer;
}

.first-run-btn.primary {
  border-color: var(--accent);
  background: color-mix(in srgb, var(--accent) 18%, transparent);
}

.num-cell {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.empty {
  color: var(--muted);
  font-size: var(--type-meta);
}

.right-panel {
  display: flex;
  flex-direction: row;
  width: 220px;
  flex-shrink: 0;
  border-left: 1px solid var(--border);
  background: var(--panel-bg);
  overflow: hidden;
}

/* Left column: per-panel header + the active page. */
.rp-main {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
  overflow: hidden;
}

.rp-page-header {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  min-height: 34px;
  padding: 0 var(--sp-3);
  border-bottom: 1px solid var(--app-border-soft);
  background: var(--app-surface-2);
  flex-shrink: 0;
}

.rp-title {
  flex: 1;
  min-width: 0;
  font-family: var(--font-ui);
  font-size: var(--type-section);
  font-weight: 600;
  letter-spacing: 0.01em;
  color: var(--fg);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Right edge: vertical icon rail (replaces the old text tab strip). */
.icon-rail {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  width: 44px;
  flex-shrink: 0;
  padding: var(--sp-2) 0;
  border-left: 1px solid var(--app-border-soft);
  background: var(--app-surface-2);
}

.rail-btn {
  position: relative;
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  border: 0;
  border-radius: var(--app-r-1);
  background: transparent;
  color: var(--fg-dim);
  cursor: pointer;
}

.rail-btn svg {
  width: 18px;
  height: 18px;
}

.rail-btn:hover {
  background: var(--app-surface-3);
  color: var(--fg);
}

.rail-btn.active {
  background: var(--app-sel-bg);
  color: var(--accent);
}

.rail-btn.active::before {
  content: '';
  position: absolute;
  left: -6px;
  top: 7px;
  bottom: 7px;
  width: 2px;
  border-radius: 2px;
  background: var(--accent);
}

.rail-btn .rail-tip {
  position: absolute;
  right: calc(100% + 8px);
  top: 50%;
  transform: translateY(-50%) translateX(4px);
  padding: 3px 8px;
  border-radius: 5px;
  background: var(--fg);
  color: var(--bg);
  font-family: var(--font-ui);
  font-size: 11px;
  font-weight: 500;
  white-space: nowrap;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.12s ease, transform 0.12s ease;
  z-index: 5;
}

.rail-btn:hover .rail-tip,
.rail-btn:focus-visible .rail-tip {
  opacity: 1;
  transform: translateY(-50%) translateX(0);
}

.rail-sep {
  width: 22px;
  height: 1px;
  background: var(--border);
  margin: var(--sp-2) 0;
}

/* Collapse / expand the right panel — pinned to the rail foot with a hairline. */
.rail-collapse {
  margin-top: auto;
}

.rail-collapse::before {
  content: '';
  position: absolute;
  top: -5px;
  left: 6px;
  right: 6px;
  height: 1px;
  background: var(--app-border-soft);
}

@media (prefers-reduced-motion: reduce) {
  .rail-btn .rail-tip { transition: none; }
}

/* Left activity rail — investigation entry points, mirror of the right icon rail. */
.activity-rail {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  width: 44px;
  flex-shrink: 0;
  padding: var(--sp-2) 0;
  border-right: 1px solid var(--border);
  background: var(--app-surface-2);
}

.activity-rail .act-spring {
  flex: 1 1 auto;
}

/* Tip flips to the right edge (the right rail's tip sits on its left). */
.act-btn .act-tip {
  right: auto;
  left: calc(100% + 8px);
  transform: translateY(-50%) translateX(-4px);
}

.act-btn:hover .act-tip,
.act-btn:focus-visible .act-tip {
  transform: translateY(-50%) translateX(0);
}

.panel-page-wrap {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.panel-page {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

/* Marks tab: scrollable stack of collapsible cards. */
.panel-page-marks {
  overflow-y: auto;
  padding: var(--sp-3);
  gap: var(--sp-3);
}

/* ---- Right-panel collapsible section card ---- */
.rp-card {
  border: 1px solid var(--app-border-soft);
  border-radius: var(--app-r-2);
  background: var(--app-surface-2);
  overflow: hidden;
  flex-shrink: 0;
}

.rp-card-head {
  width: 100%;
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  padding: var(--sp-2) var(--sp-3);
  border: 0;
  background: transparent;
  color: var(--fg);
  font-family: var(--font-ui);
  font-size: var(--type-meta, 11px);
  font-weight: 600;
  letter-spacing: 0.01em;
  cursor: pointer;
  text-align: left;
}

.rp-card-head:hover { background: var(--app-hover-bg); }

.rp-chevron {
  width: 13px;
  height: 13px;
  flex-shrink: 0;
  color: var(--fg-dim);
  transition: transform 0.14s ease;
}

.rp-card.collapsed .rp-chevron { transform: rotate(-90deg); }

.rp-card-title { flex: 1; min-width: 0; }

.rp-card-count {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: 10px;
  font-weight: 500;
  color: var(--fg-dim);
  background: var(--app-surface-3);
  padding: 1px 6px;
  border-radius: 999px;
}

.rp-card-body {
  border-top: 1px solid var(--app-border-soft);
}

@media (prefers-reduced-motion: reduce) {
  .rp-chevron { transition: none; }
}

.panel-resizer {
  width: 8px;
  flex-shrink: 0;
  cursor: col-resize;
  position: relative;
  background: transparent;
}

.panel-resizer::before {
  content: '';
  position: absolute;
  top: 0;
  bottom: 0;
  left: 3px;
  width: 2px;
  background: transparent;
  transition: background 0.12s ease;
}

.panel-resizer:hover::before {
  background: color-mix(in srgb, var(--accent) 50%, var(--border));
}

/* Collapsed: keep the seam accent faintly visible so it reads as re-openable. */
.panel-resizer.is-collapsed::before {
  background: color-mix(in srgb, var(--accent) 28%, var(--border));
}
.panel-resizer.is-collapsed:hover::before {
  background: color-mix(in srgb, var(--accent) 60%, var(--border));
}

/* Collapsed right panel is just the rail — drop the now-redundant inner border.
   The width/min-width also override the responsive `.right-panel { min-width }`
   media rules, which would otherwise pin the collapsed panel open. */
.right-panel.collapsed {
  width: 44px;
  min-width: 44px;
}

.right-panel.collapsed .icon-rail {
  border-left: 0;
}

body.col-resizing,
body.col-resizing * {
  cursor: col-resize !important;
  user-select: none;
}

.panel-section {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.panel-section.flex-fill {
  flex: 1;
  overflow: hidden;
}

.panel-header {
  font-family: var(--font-ui);
  font-size: var(--type-meta, 11px);
  font-weight: 600;
  letter-spacing: 0.01em;
  color: var(--fg);
  padding: var(--sp-2) var(--sp-3) var(--sp-1);
  border-bottom: 1px solid var(--app-border-soft);
  flex-shrink: 0;
}

.cursor-range-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 10px;
  font-size: 11px;
  font-family: monospace;
}

.cursor-range-row {
  display: flex;
  justify-content: space-between;
  gap: 6px;
}

.cursor-range-key {
  color: var(--fg-dim);
  flex-shrink: 0;
}

.cursor-range-val {
  color: var(--fg);
  text-align: right;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cursor-range-hint {
  padding: 8px 10px;
  color: var(--fg-dim);
  opacity: 0.65;
  font-size: 10px;
  font-style: italic;
}

.task-count {
  font-weight: normal;
  opacity: 0.7;
}

.status-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 3px 12px;
  font-size: 11px;
  font-family: monospace;
  color: var(--fg-dim);
  background: var(--panel-bg);
  border-top: 1px solid var(--border);
  flex-shrink: 0;
}

.status-summary {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex-shrink: 1;
}

.status-summary.error {
  color: #e07070;
}

.status-inspect {
  flex-shrink: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--fg-dim);
  padding: 0 8px;
}

.status-range {
  flex-shrink: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--fg-dim);
  font-size: 10px;
  max-width: 36%;
}

.status-filters {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 1;
  min-width: 0;
  overflow: hidden;
}

.status-filter-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 1px 6px;
  border-radius: 999px;
  border: 1px solid var(--accent);
  color: var(--fg);
  background: var(--tb-btn-active);
  white-space: nowrap;
  font-size: 10px;
  min-width: 0;
}

.status-filter-chip-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 22vw;
}

.status-filter-clear {
  appearance: none;
  border: none;
  background: transparent;
  color: inherit;
  cursor: pointer;
  font: inherit;
  line-height: 1;
  padding: 0;
  opacity: 0.75;
}

.status-filter-clear:hover {
  opacity: 1;
}

.status-filter-clear-all {
  appearance: none;
  border: 1px solid var(--border);
  background: transparent;
  color: var(--fg-dim);
  border-radius: 999px;
  padding: 1px 8px;
  font-size: 10px;
  cursor: pointer;
}

.status-filter-clear-all:hover {
  color: var(--fg);
  background: var(--tb-btn-hover);
}

.status-cursor-bar {
  margin-left: auto;
  max-width: 55%;
}

.status-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.status-zoom {
  display: flex;
  align-items: baseline;
  flex-shrink: 0;
  white-space: nowrap;
  user-select: text;
}

.status-zoom-scale {
  min-width: 80px;
  padding: 0 2px 0 8px;
  color: var(--fg);
  text-align: right;
}

.status-zoom-visible {
  padding: 0 8px 0 0;
  color: var(--fg-dim);
}

.status-toggle {
  appearance: none;
  border: 1px solid var(--border);
  background: transparent;
  color: var(--fg-dim);
  border-radius: 999px;
  min-width: 46px;
  height: 22px;
  padding: 0 10px;
  font: inherit;
  cursor: pointer;
}

.status-find {
  appearance: none;
  flex-shrink: 0;
  border: 1px solid var(--border);
  background: transparent;
  color: var(--fg-dim);
  border-radius: 999px;
  height: 22px;
  padding: 0 10px;
  font: inherit;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  cursor: pointer;
}

.status-find:hover,
.status-find:focus-visible {
  background: var(--tb-btn-hover);
  color: var(--fg);
  outline: none;
}

.status-toggle:hover,
.status-toggle:focus-visible {
  background: var(--tb-btn-hover);
  color: var(--fg);
  outline: none;
}

.status-toggle.active {
  color: var(--fg);
  border-color: var(--accent);
  background: var(--tb-btn-active);
}

.status-hint {
  opacity: 0.6;
}

/* ---- Toast notification ---- */
.toast-notification {
  position: fixed;
  bottom: 40px;
  left: 50%;
  transform: translateX(-50%);
  padding: 8px 18px;
  border-radius: 6px;
  font-size: 12px;
  z-index: 10000;
  cursor: pointer;
  max-width: 520px;
  text-align: center;
  pointer-events: auto;
  box-shadow: 0 4px 16px rgba(0,0,0,0.4);
}

.toast-notification.info {
  background: var(--panel-bg);
  color: var(--fg);
  border: 1px solid var(--border);
}

.toast-notification.error {
  background: #3a1010;
  color: #ff9090;
  border: 1px solid #7a3333;
}

.app:not(.dark) .toast-notification.info {
  background: #f5f5f5;
  color: #1e1e1e;
  border: 1px solid #ccc;
}

.app:not(.dark) .toast-notification.error {
  background: #fff0f0;
  color: #b00;
  border: 1px solid #e99;
}

.toast-enter-active,
.toast-leave-active {
  transition: opacity 0.2s ease;
}

.toast-enter-from,
.toast-leave-to {
  opacity: 0;
}

.palette-overlay {
  position: fixed;
  inset: 0;
  z-index: 1400;
  background: color-mix(in srgb, #000 48%, transparent);
  backdrop-filter: blur(5px) saturate(1.1);
  -webkit-backdrop-filter: blur(5px) saturate(1.1);
  display: flex;
  justify-content: center;
  padding-top: 12vh;
}
.palette-box {
  width: min(440px, calc(100vw - 32px));
  align-self: flex-start;
  background: var(--panel-bg);
  border: 1px solid var(--app-border-soft, var(--border));
  border-radius: 14px;
  box-shadow:
    0 32px 80px -16px rgba(0, 0, 0, 0.5),
    0 0 0 1px color-mix(in srgb, var(--fg) 6%, transparent);
  padding: 10px;
  animation: dialog-pop 0.16s cubic-bezier(0.32, 0.72, 0, 1);
}
.palette-input {
  width: 100%;
  box-sizing: border-box;
  font: inherit;
  padding: 9px 12px;
  border-radius: 9px;
  border: 1px solid var(--border);
  background: var(--panel-inset);
  color: var(--fg);
  transition: border-color 0.14s ease, box-shadow 0.14s ease;
}
.palette-input:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 24%, transparent);
}
.palette-list {
  list-style: none;
  margin: 8px 0 0;
  padding: 0;
  max-height: 280px;
  overflow: auto;
}
.palette-list li {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 6px;
  cursor: pointer;
}
.palette-list li.disabled {
  color: var(--muted, #8a96a8);
  cursor: default;
  opacity: 0.72;
}
.palette-list li.on,
.palette-list li:hover {
  background: color-mix(in srgb, var(--accent) 20%, transparent);
}
.palette-list li.disabled.on,
.palette-list li.disabled:hover {
  background: color-mix(in srgb, var(--accent) 10%, transparent);
}
.palette-label {
  flex: 1;
  min-width: 0;
}
.palette-shortcut {
  flex: 0 0 auto;
  color: var(--muted, #8a96a8);
  font-size: 11px;
}
.palette-hint {
  margin: 8px 2px 0;
  font-size: 11px;
  color: var(--fg-dim);
}
</style>
