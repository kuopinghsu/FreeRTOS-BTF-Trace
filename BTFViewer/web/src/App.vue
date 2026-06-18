<template>
  <div
    class="app"
    :class="{ dark: timelineOptions.darkMode, 'drag-over': dragOver }"
    @dragenter.prevent="onDragEnter"
    @dragover.prevent="onDragOver"
    @dragleave.prevent="onDragLeave"
    @drop.prevent="onFileDrop"
  >
    <!-- Toolbar -->
    <Toolbar
      :model-value="timelineOptions"
      :trace-info="traceInfo"
      :heatmap-enabled="heatmapEnabled"
      :task-filter-active="!!timelineOptions.taskFilterKeys?.length"
      :loading="loading"
      :loading-pct="loadingPct"
      :loading-msg="loadingMsg"
      :time-scale="trace?.timeScale || 'ns'"
      @update:model-value="v => Object.assign(timelineOptions, v)"
      @file-error="showToast($event, 'error')"
      @trace-reading="onTraceReading"
      @trace-loaded="onTraceLoaded"
      @load-demo="onLoadDemo"
      @zoom="onZoom"
      @fit="onFit"
      @zoom1to1="onZoom1to1"
      @zoom-range="onZoomRange"
      @show-find="focusFindPanel"
      @expand-all="onExpandAll"
      @collapse-all="onCollapseAll"
      @add-mark="onAddMark"
      @copy-screenshot="onCopyScreenshot"
      @export-svg="onExportSvg"
      @show-heatmap="onOpenHeatmap"
      @clear-task-filter="clearHeatmapTaskFilter"
      @show-help="openHelpDialog"
      @show-about="openAboutDialog"
      @show-settings="openSettingsDialog"
    />

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
      <!-- Loading overlay -->
      <div
        v-if="loading"
        class="loading-overlay"
      >
        <div class="loading-card">
          <div class="loading-filename">
            {{ loadingFileName || 'Loading trace…' }}
          </div>
          <div class="loading-msg">
            {{ loadingMsg || 'Please wait…' }}
          </div>
          <div class="loading-bar-track">
            <div
              class="loading-bar-fill"
              :style="{ width: loadingPct + '%' }"
            />
          </div>
          <div class="loading-pct">
            {{ loadingPct }}%
          </div>
        </div>
      </div>
      <div ref="leftPaneRef" class="left-pane">
        <div class="timeline-wrap">
          <TimelinePanel
            ref="timelinePanelRef"
            :trace="trace"
            :options="timelineOptions"
            :cursors="cursors"
            :max-cursors="appSettings.maxCursors"
            :label-width="appSettings.labelWidth"
            :find-hits="findHits"
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
            @mark-move="onMoveMark"
            @copy-screenshot="onCopyScreenshot"
            @export-svg="onExportSvg"
            @before-cursor-change="pushUndoSnapshot"
            @before-mark-change="pushUndoSnapshot"
            @label-width-change="onLabelWidthChange"
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
          @clear-selection="clearCpuLoadSelection"
          @viewport-change="onCpuLoadViewportChange"
        />
      </div>

      <div
        v-if="trace"
        class="panel-resizer"
        role="separator"
        aria-label="Resize side panel"
        aria-orientation="vertical"
        @mousedown.prevent="onRightPanelResizeStart"
      />

      <!-- Right panel -->
      <div
        v-if="trace"
        class="right-panel"
        :style="{ width: rightPanelWidth + 'px' }"
      >
        <div class="panel-page-wrap">
          <div v-if="rightPanelTab === 'marks'" class="panel-page panel-page-marks">
            <div class="panel-section">
              <div class="panel-header">
                Cursors
              </div>
              <CursorPanel
                :cursors="cursors"
                :trace="trace"
                :time-scale="trace.timeScale"
                @delete-cursor="onDeleteCursor"
                @jump-to-cursor="timelinePanelRef?.jumpToNs($event)"
                @clear-all="clearCursors"
              />
            </div>

            <div class="panel-section">
              <div class="panel-header">
                Cursor Range
              </div>
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

            <div
              v-if="appSettings.showMarks"
              class="panel-section"
            >
              <div class="panel-header">
                Marks
              </div>
              <MarksPanel
                :marks="marks"
                :time-scale="trace.timeScale"
                @add-bookmark="onAddMark"
                @add-annotation="onAddAnnotationAtCenter"
                @delete-mark="onDeleteMark"
                @jump-to="onJumpToMark"
                @update-label="onUpdateMarkLabel"
                @import-marks="onImportMarks"
                @clear-marks="onClearMarks"
                @export-session="onExportSession"
                @import-session="onImportSession"
                @select-mark="timelineOptions.selectedMarkId = $event"
              />
            </div>

            <div
              v-if="appSettings.showLegend"
              class="panel-section flex-fill"
            >
              <div class="panel-header">
                Legend
                <span class="task-count">({{ trace.tasks.length }})</span>
              </div>
              <LegendPanel
                :trace="trace"
                :highlight-key="timelineOptions.highlightKey"
                :task-filter-keys="timelineOptions.taskFilterKeys"
                :heatmap-filter-label="timelineOptions.heatmapFilterLabel"
                @highlight-change="(k) => { timelineOptions.highlightKey = k ?? pinnedHighlightKey; scheduleRender() }"
                @highlight-click="onHighlightClick"
                @migrated-filter-change="onMigratedFilterChange"
                @clear-task-filter="clearHeatmapTaskFilter"
              />
            </div>
          </div>

          <div v-else-if="rightPanelTab === 'find'" class="panel-page panel-page-find">
            <div class="panel-section flex-fill">
              <div class="panel-header">
                Find
              </div>
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

          <div v-else class="panel-page panel-page-stats">
            <div class="panel-section flex-fill">
              <div class="panel-header">
                Statistics
              </div>
              <StatisticsPanel
                :trace="trace"
                :cursors="cursors"
                :tabs="tabs"
                :stats-paused="statsPaused"
                :open-plot="activeTab?.openPlot ?? null"
                :section-heights="statsSectionHeights"
                @update:open-plot="onOpenPlotChange"
                @update:section-heights="onSectionHeightsChange"
                @highlight-task="onHighlightClick"
                @plot-point-activate="onStatsPlotPointActivate"
              />
            </div>
          </div>
        </div>

        <div class="panel-tabs" role="tablist" aria-label="Right panel tabs">
          <button
            v-if="appSettings.showStats"
            class="panel-tab"
            :class="{ active: rightPanelTab === 'stats' }"
            role="tab"
            :aria-selected="rightPanelTab === 'stats'"
            @click="rightPanelTab = 'stats'"
          >
            Statistics
          </button>
          <button
            class="panel-tab"
            :class="{ active: rightPanelTab === 'marks' }"
            role="tab"
            :aria-selected="rightPanelTab === 'marks'"
            @click="rightPanelTab = 'marks'"
          >
            Cursor / Bookmark
          </button>
          <button
            class="panel-tab"
            :class="{ active: rightPanelTab === 'find' }"
            role="tab"
            :aria-selected="rightPanelTab === 'find'"
            @click="rightPanelTab = 'find'"
          >
            Find
          </button>
        </div>
      </div>
    </div>

    <!-- Settings dialog -->
    <SettingsDialog
      v-if="settingsOpen"
      :model-value="appSettings"
      :time-scale="trace?.timeScale || 'ns'"
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
              </div><div>Zoom to cursor range</div>
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
              </div><div>Fit timeline to trace</div>
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
              </div><div>Zoom out</div>
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
              </div><div>Fit timeline</div>
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
              </div><div>Use the toolbar or bottom status bar to show/hide the CPU load panel</div>
              <div class="k">
                CPU overlay
              </div><div>Cursors, hover cursor, bookmarks, and annotations are mirrored in CPU load view</div>
            </div>
          </div>

          <div class="help-section">
            <div class="help-section-title">
              Capture & Export
            </div>
            <div class="help-grid">
              <div class="k">
                S
              </div><div>Open snapshot editor from the current timeline view</div>
              <div class="k">
                Save PNG
              </div><div>Exports the annotated snapshot; includes CPU load when Load is on</div>
              <div class="k">
                Export SVG
              </div><div>Exports the current view; includes CPU load when Load is on</div>
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
          <div class="about-icon" aria-hidden="true">
            <span class="bar bar-1" />
            <span class="bar bar-2" />
            <span class="bar bar-3" />
            <span class="bar bar-4" />
            <span class="marker" />
          </div>
          <div class="about-title">RTOS BTF Viewer</div>
          <div class="about-subtitle">RTOS context-switch timeline visualiser · v{{ appVersion }}</div>
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
              <div class="about-key">Purpose</div><div>Interactive viewer for Best Trace Format (.btf) RTOS scheduling traces</div>
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

    <MigrationHeatmapDialog
      v-if="heatmapOpen && trace"
      :trace="trace"
      :cursors="cursors"
      :task-filter-active="!!timelineOptions.taskFilterKeys?.length"
      :task-filter-label="timelineOptions.heatmapFilterLabel"
      :task-filter-count="timelineOptions.taskFilterKeys?.length ?? 0"
      @close="onHeatmapClose"
      @drill-down="onHeatmapDrillDown"
      @clear-filter="clearHeatmapTaskFilter"
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

    <!-- Status bar -->
    <div class="status-bar">
      <template v-if="trace">
        <span class="status-summary">
          {{ trace.tasks.length }} tasks · {{ trace.segments.length.toLocaleString() }} segments ·
          {{ trace.stiEvents.length.toLocaleString() }} STI events ·
          {{ formatTime(trace.timeMax - trace.timeMin, trace.timeScale) }} total
        </span>

        <div class="status-actions">
          <button
            class="status-toggle"
            :class="{ active: timelineOptions.showCpuLoad }"
            type="button"
            @click="timelineOptions.showCpuLoad = !timelineOptions.showCpuLoad"
          >
            Load
          </button>
        </div>
      </template>
      <span
        v-else
        class="status-hint"
      >
        Open a .btf trace file or click Demo to begin · Press ? for shortcuts/help
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
import LegendPanel      from './components/LegendPanel.vue'
import StatisticsPanel  from './components/StatisticsPanel.vue'
import MarksPanel       from './components/MarksPanel.vue'
import SnapshotEditor   from './components/SnapshotEditor.vue'
import MigrationHeatmapDialog from './components/MigrationHeatmapDialog.vue'
import FindPanel from './components/FindPanel.vue'
import JumpToTimeDialog from './components/JumpToTimeDialog.vue'
import SettingsDialog from './components/SettingsDialog.vue'
import { formatTime }   from './renderer/TimelineRenderer.js'
import { taskDisplayName, taskMergeKey, setColorblindMode } from './utils/colors.js'
import { loadSettings, saveSettings, applySettingsToRuntime, resizeTabCursors, normalizeSettings,
} from './utils/settingsStore.js'
import { traceIsMultiCore } from './utils/migrationAnalysis.js'
import {
  cpuLoadPreferredPaneHeight, cpuLoadPaneDefaultH, cpuLoadPaneMaxH,
  CPU_LOAD_PANE_MIN_H,
} from './utils/cpuLoadHelpers.js'
import { useTraceTabs } from './composables/useTraceTabs.js'
import { loadSession, saveSession, buildSessionSnapshot, isRestorableViewport, applySavedLayout } from './utils/sessionStore.js'
import { createUndoStack } from './utils/undoStack.js'
import {
  buildPortableSession, parsePortableSession, applyPortableSession, downloadPortableSession,
  sessionCursorsSlotCount,
} from './utils/sessionPortable.js'
import { computeFindHits, stepFindHitIndex } from './utils/findAnalysis.js'
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
const leftPaneRef = ref(null)
const loading    = ref(false)
const loadingPct = ref(0)
const loadingMsg = ref('')
const loadingFileName = ref('')
const helpOpen   = ref(false)
const aboutOpen  = ref(false)
const settingsOpen = ref(false)
const heatmapOpen = ref(false)
/** Viewport/cursors saved when migration heatmap opens; restored by Show all tasks. */
let _heatmapRestoreSnapshot = null
const statsPaused = ref(false)
const rightPanelTab = ref('stats')
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
const findMarkerNs = computed(() => activeTab.value?.findMarkerNs ?? null)
const findError = ref('')

// ---- Snapshot editor -------------------------------------------------------
const snapshotEditorOpen = ref(false)
const snapshotImageUrl   = ref(null)
const snapshotDownloadFilename = ref('annotated-snapshot.png')

const rightPanelWidth = ref(330)
const RIGHT_PANEL_MIN_W = 180
const RIGHT_PANEL_MAX_W = 520
let _rightPanelResize = null

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
  )
}

const toastMsg     = ref('')
const toastType    = ref('info')
const toastVisible = ref(false)
let   _toastTimer  = null

function showToast(msg, type = 'info') {
  toastMsg.value     = msg
  toastType.value    = type
  toastVisible.value = true
  clearTimeout(_toastTimer)
  _toastTimer = setTimeout(() => { toastVisible.value = false }, type === 'error' ? 5000 : 3000)
}

const timelineOptions = reactive({
  viewMode:        'task',
  darkMode:        true,
  showGrid:        false,
  showSti:         true,
  showCpuLoad:     true,
  stiLogScale:     false,
  orientation:     'h',
  highlightKey:    null,
  marks:           [],
  highlightSegment: null,
  selectedMarkId:  null,
  migratedOnlyFilter: false,
  taskFilterKeys:     null,
  heatmapFilterLabel: null,
  lockedTaskKey:   null,
  showHoverHighlight: true,
  layoutRev:       0,
})

const undoStack = createUndoStack()

function syncTimelineOptionsFromSettings(s = appSettings) {
  timelineOptions.darkMode = s.darkMode
  timelineOptions.showGrid = s.showGrid
  timelineOptions.showSti = s.showSti
  timelineOptions.showCpuLoad = s.showCpuLoad
  timelineOptions.showHoverHighlight = s.hoverHighlight
  timelineOptions.layoutRev += 1
  if (!s.showStats && rightPanelTab.value === 'stats') {
    rightPanelTab.value = 'marks'
  }
}

function applyAppSettings(next, { silent = false, persist = true } = {}) {
  Object.assign(appSettings, applySettingsToRuntime(next))
  setColorblindMode(appSettings.colorblindSafe)
  syncTimelineOptionsFromSettings()
  resizeTabCursors(tabs.value, appSettings.maxCursors)
  if (persist) saveSettings(appSettings)
  scheduleRender()
  autofitCpuLoadPaneHeight()
  if (!silent) showToast('Settings saved', 'info')
}

let settingsRevertSnapshot = null

function openSettingsDialog() {
  helpOpen.value = false
  aboutOpen.value = false
  settingsRevertSnapshot = normalizeSettings(appSettings)
  settingsOpen.value = true
}

function onSettingsPreview(next) {
  applyAppSettings(next, { silent: true, persist: false })
}

function onSettingsCancel() {
  if (settingsRevertSnapshot) {
    applyAppSettings(settingsRevertSnapshot, { silent: true, persist: false })
    settingsRevertSnapshot = null
  }
  settingsOpen.value = false
}

function onSettingsSave(next) {
  applyAppSettings(next, { silent: false, persist: true })
  settingsRevertSnapshot = null
  settingsOpen.value = false
}
const cpuLoadHoverTime = ref(null)

const cpuLoadSelectedTask = computed(() => {
  if (highlightSegment.value?.task) return taskMergeKey(highlightSegment.value.task)
  return pinnedHighlightKey.value
})

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

function cycleHighlightedSegment(forward) {
  if (!trace.value) return
  _ensureNavCache()
  const segs = _navCache?.segs
  if (!segs || segs.length === 0) return

  const cur      = highlightSegment.value
  const centerNs = timelinePanelRef.value?.getViewportCenter?.() ?? 0
  const isCoreView = timelineOptions.viewMode === 'core'
  const centerCore = isCoreView ? (timelinePanelRef.value?.getCoreAtViewportCenter?.() ?? null) : null
  const curCore = cur?.core ?? centerCore
  const navSegs = (isCoreView && curCore)
    ? segs.filter(s => s.core === curCore)
    : segs
  if (!navSegs || navSegs.length === 0) return

  const curTaskKey = cur
    ? taskMergeKey(cur.task)
    : (timelineOptions.highlightKey ?? pinnedHighlightKey.value ?? null)

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

  let next
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
  } else {
    if (idx >= 0) {
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
  } else {
    highlightSegment.value = seg
    timelineOptions.highlightSegment = seg
  }
}

watch(marks, (m) => {
  timelineOptions.marks = m
}, { deep: true })

watch(activeTabId, () => {
  undoStack.clear()
  const tab = activeTab.value
  timelineOptions.highlightKey = tab?.pinnedHighlightKey ?? null
  timelineOptions.highlightSegment = tab?.highlightSegment ?? null
  timelineOptions.lockedTaskKey = tab?.pinnedHighlightKey ?? null
  _navCache = tab ? getNavCache(tab) : null
  nextTick(() => {
    applyTimelineViewport()
    autofitCpuLoadPaneHeight()
  })
})

watch(
  () => [
    trace.value,
    timelineOptions.viewMode,
    timelineOptions.showCpuLoad,
    cpuLoadExpanded.value,
    cpuLoadSelectedTask.value,
    appSettings.cpuLoadRowH,
  ],
  () => nextTick(() => autofitCpuLoadPaneHeight()),
)

watch(
  () => ({
    viewMode: timelineOptions.viewMode,
    orientation: timelineOptions.orientation,
    showGrid: timelineOptions.showGrid,
    showSti: timelineOptions.showSti,
    showCpuLoad: timelineOptions.showCpuLoad,
    darkMode: timelineOptions.darkMode,
    migratedOnlyFilter: timelineOptions.migratedOnlyFilter,
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

const cursorRangeStats = computed(() => {
  const tr = trace.value
  if (!tr) return null

  const placed = cursors.value.filter(c => c !== null)
  if (placed.length < 2) return null

  const sorted = [...placed].sort((a, b) => a - b)
  const lo = sorted[0]
  const hi = sorted[sorted.length - 1]
  const dt = hi - lo
  if (dt <= 0) return null

  const taskAcc = new Map()
  const durations = []
  let switches = 0

  for (const seg of tr.segments) {
    if (seg.end <= lo || seg.start >= hi) continue
    const ov = Math.min(seg.end, hi) - Math.max(seg.start, lo)
    if (ov <= 0) continue
    switches++
    durations.push(seg.end - seg.start)
    const mk = taskMergeKey(seg.task)
    const repr = tr.taskRepr.get(mk) || seg.task
    const disp = taskDisplayName(repr)
    taskAcc.set(disp, (taskAcc.get(disp) || 0) + ov)
  }

  let topTask = null
  let topNs = 0
  for (const [k, v] of taskAcc) {
    if (v > topNs) {
      topNs = v
      topTask = k
    }
  }

  const result = {
    span: formatTime(dt, tr.timeScale),
    switches,
    topTask,
    topPct: topTask ? (100.0 * topNs / dt).toFixed(1) : null,
  }

  if (durations.length > 0) {
    const minD = Math.min(...durations)
    const maxD = Math.max(...durations)
    const avgD = Math.round(durations.reduce((a, b) => a + b, 0) / durations.length)
    result.dMin = formatTime(minD, tr.timeScale)
    result.dAvg = formatTime(avgD, tr.timeScale)
    result.dMax = formatTime(maxD, tr.timeScale)
  }
  return result
})

// ---- File loading (via Web Worker; fallback to main-thread for file:// origins) --
let _parseWorker = null

function onTraceReading({ name }) {
  // Show the loading overlay immediately while FileReader is still reading the file
  if (_parseWorker) { _parseWorker.terminate(); _parseWorker = null }
  loading.value         = true
  loadingPct.value      = 1
  loadingMsg.value      = 'Reading file…'
  loadingFileName.value = name || 'trace.btf'
}

function finishTraceLoadTab(tab) {
  timelineOptions.highlightKey = tab.pinnedHighlightKey ?? null
  timelineOptions.showCpuLoad = true
  timelineOptions.highlightSegment = tab.highlightSegment ?? null
  loading.value    = false
  loadingPct.value = 0
  loadingMsg.value = ''
}

function paintLoadingProgress(pct, msg) {
  loadingPct.value = pct
  loadingMsg.value = msg || ''
}

async function flushLoadingProgress(pct, msg) {
  paintLoadingProgress(pct, msg)
  await new Promise(resolve => requestAnimationFrame(resolve))
}

async function attachParsedTrace(name, packedOrTrace) {
  paintLoadingProgress(100, 'Opening trace…')
  try {
    const { unpackTrace } = await import('./parser/tracePack.js')
    const trace = packedOrTrace?.segStore ? packedOrTrace : unpackTrace(packedOrTrace)
    const tab = openTab(name || 'trace.btf')
    resizeTabCursors(tabs.value, appSettings.maxCursors)
    resetTabForLoad(tab)
    undoStack.clear()
    timelineOptions.taskFilterKeys = null
    timelineOptions.heatmapFilterLabel = null

    tab.trace = markRaw(trace)
    if (trace.meta?._versionWarning) {
      showToast(trace.meta._versionWarning, 'info')
    }
    await nextTick()

    _cpuLoadUserSized = false
    finishTraceLoadTab(tab)
    await nextTick()
    applyTimelineViewport()
    scheduleRender()
    autofitCpuLoadPaneHeight()

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
  const { parseBtf } = await import('./parser/btfParser.js')
  const { finalizeAndEnrich } = await import('./parser/tracePack.js')
  const result = finalizeAndEnrich(await parseBtf(text, (pct, msg) => {
    paintLoadingProgress(pct, msg)
  }))
  await attachParsedTrace(name, result)
}

async function onTraceLoaded({ text, name }) {
  // Terminate any in-progress parse
  if (_parseWorker) { _parseWorker.terminate(); _parseWorker = null }

  loading.value         = true
  loadingPct.value      = 1
  loadingMsg.value      = 'Parsing trace…'
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
      console.error('BTF parse error:', err)
      showToast('Failed to parse BTF file: ' + err.message, 'error')
      loading.value = false
    }
    return
  }

  const Worker = (await import('./parser/btfWorker.js?worker&inline')).default
  const worker = new Worker()
  _parseWorker = worker

  worker.onmessage = ({ data }) => {
    if (data.type === 'progress') {
      loadingPct.value = data.pct
      loadingMsg.value = data.msg || ''
    } else if (data.type === 'done') {
      _parseWorker = null
      worker.terminate()
      attachParsedTrace(name, data.packed).catch((err) => {
        console.error('Failed to open trace:', err)
        showToast('Failed to open trace: ' + (err?.message || String(err)), 'error')
        loading.value = false
      })
    } else if (data.type === 'error') {
      console.error('BTF parse error:', data.message)
      _parseWorker = null
      worker.terminate()
      loadingPct.value = 1
      loadingMsg.value = 'Parsing on main thread…'
      parseTraceOnMainThread(text, name).catch((err) => {
        console.error('BTF main-thread fallback failed:', err)
        showToast('Failed to parse BTF file: ' + (err?.message || data.message), 'error')
        loading.value = false
      })
    }
  }

  worker.onerror = (e) => {
    console.error('Worker error:', e)
    _parseWorker = null
    worker.terminate()
    loadingPct.value = 1
    loadingMsg.value = 'Parsing on main thread…'
    parseTraceOnMainThread(text, name).catch((err) => {
      console.error('BTF main-thread fallback failed:', err)
      showToast('Failed to parse BTF file: ' + (err?.message || e.message), 'error')
      loading.value = false
    })
  }

  worker.postMessage({ text })
}

// ---- Zoom ----------------------------------------------------------------
function onZoom(factor) {
  timelinePanelRef.value?.zoomCenter(factor)
  syncTimelineViewport()
}

function onFit() {
  timelinePanelRef.value?.fitToTrace()
  syncTimelineViewport()
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

function onStatsPlotPointActivate({ ns, note, segment, interval }) {
  if (segment) {
    highlightSegment.value = segment
    timelineOptions.highlightSegment = segment
    timelineOptions.highlightKey = taskMergeKey(segment.task)
    timelinePanelRef.value?.scrollToSegmentIfNeeded(segment)
  } else if (interval) {
    timelinePanelRef.value?.zoomToTimeRange(interval.startNs, interval.stopNs)
  } else if (ns != null) {
    timelinePanelRef.value?.jumpToNs(ns)
  }
  if (ns != null) addAnnotationAtNs(ns, note)
  rightPanelTab.value = 'marks'
  syncTimelineViewport()
  scheduleSessionSave()
}

function onOpenPlotChange(v) {
  if (activeTab.value) activeTab.value.openPlot = v
  scheduleSessionSave()
}

function onSectionHeightsChange(v) {
  Object.assign(statsSectionHeights.value, v)
  scheduleSessionSave()
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
    marks.value,
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
  rightPanelTab.value = 'find'
  nextTick(() => findPanelRef.value?.focusInput())
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
  const file = e.dataTransfer?.files?.[0]
  if (!file) return
  if (!file.name.toLowerCase().endsWith('.btf')) {
    showToast('Only .btf files are supported', 'error')
    return
  }
  onTraceReading({ name: file.name })
  const reader = new FileReader()
  reader.onload = (ev) => onTraceLoaded({ text: ev.target.result, name: file.name })
  reader.onerror = () => showToast(`Failed to read "${file.name}"`, 'error')
  reader.readAsText(file)
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

function captureFilter(node) {
  if (!(node instanceof HTMLElement)) return true
  return !node.classList.contains('context-menu') && !node.classList.contains('sti-tooltip')
}

async function captureLeftPaneBlob() {
  const root = leftPaneRef.value
  if (!root) return null

  try {
    return await domToBlob(root, {
      cacheBust: true,
      pixelRatio: window.devicePixelRatio || 1,
      width: root.clientWidth,
      height: root.clientHeight,
      filter: captureFilter,
    })
  } catch {
    return await timelinePanelRef.value?.captureScreenshotBlob?.()
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
  cpuLoadExpanded.value = true
  autofitCpuLoadPaneHeight()
}

function onCollapseAll() {
  timelinePanelRef.value?.collapseAll()
  cpuLoadExpanded.value = false
  autofitCpuLoadPaneHeight()
}

function onTimelineViewportChange(vp) {
  if (activeTab.value) Object.assign(activeTab.value.timelineViewport, vp)
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
  undoStack.push({
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
  const snap = undoStack.undo({
    cursors: cursors.value,
    marks: marks.value,
    markNextId: activeTab.value?.markNextId ?? 1,
  })
  if (snap) applyUndoSnapshot(snap)
}

function onRedo() {
  const snap = undoStack.redo({
    cursors: cursors.value,
    marks: marks.value,
    markNextId: activeTab.value?.markNextId ?? 1,
  })
  if (snap) applyUndoSnapshot(snap)
}

function onLabelWidthChange(w, commit = true) {
  appSettings.labelWidth = w
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
  timelineOptions.lockedTaskKey = null
  scheduleRender()
}

function onMigratedFilterChange(enabled) {
  timelineOptions.migratedOnlyFilter = !!enabled
  if (enabled) clearHeatmapTaskFilter()
  else scheduleRender()
}

function onOpenHeatmap() {
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
  heatmapOpen.value = true
}

function onHeatmapClose() {
  heatmapOpen.value = false
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

  if (hadFilter || restored) showToast('Showing all tasks', 'info')
}

function onHeatmapDrillDown(payload) {
  timelineOptions.viewMode = 'task'
  timelineOptions.migratedOnlyFilter = false
  timelineOptions.taskFilterKeys = payload.mergeKeys
  timelineOptions.heatmapFilterLabel = payload.pairLabel

  const c = Array(appSettings.maxCursors).fill(null)
  c[0] = payload.binLo
  c[1] = payload.binHi
  cursors.value = c

  highlightSegment.value = null
  timelineOptions.highlightSegment = null

  nextTick(() => {
    timelinePanelRef.value?.expandCoresForMergeKeys(payload.mergeKeys)
    timelinePanelRef.value?.zoomToTimeRange(payload.binLo, payload.binHi)
    if (payload.mergeKeys.length === 1) {
      onHighlightClick(payload.mergeKeys[0])
    } else {
      pinnedHighlightKey.value = null
      timelineOptions.highlightKey = null
      timelineOptions.lockedTaskKey = null
      scheduleRender()
    }
  })

  const n = payload.mergeKeys.length
  showToast(
    `Zoomed to ${payload.pairLabel} · ${n} task${n === 1 ? '' : 's'} with migrations in this bin. Toolbar or Legend → Clear to show all.`,
    'info',
  )
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
  if (isTypingTarget(e.target)) return

  if (e.key === 'F3') {
    e.preventDefault()
    stepFind(!e.shiftKey)
    return
  }

  const mod = e.ctrlKey || e.metaKey
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
    if (jumpDialogOpen.value) {
      jumpDialogOpen.value = false
      e.preventDefault()
    } else if (heatmapOpen.value) {
      onHeatmapClose()
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
    }
    return
  }

  if (helpOpen.value || aboutOpen.value || heatmapOpen.value || settingsOpen.value || jumpDialogOpen.value) return

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
      e.preventDefault()
      break
    case '2':
      timelineOptions.viewMode = 'core'
      e.preventDefault()
      break
    case 'h':
      if (!mod) {
        timelineOptions.orientation = 'h'
        e.preventDefault()
      }
      break
    case 'v':
      timelineOptions.orientation = 'v'
      e.preventDefault()
      break
    case 'g':
      if (!mod) {
        timelineOptions.showGrid = !timelineOptions.showGrid
        e.preventDefault()
      }
      break
    case 'i':
      timelineOptions.showSti = !timelineOptions.showSti
      e.preventDefault()
      break
    case 'd':
      timelineOptions.darkMode = !timelineOptions.darkMode
      e.preventDefault()
      break
    case 'b':
      onAddMark()
      e.preventDefault()
      break
    case 'a':
      onAddAnnotationAtCenter()
      e.preventDefault()
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
  loadingPct.value = 1
  loadingMsg.value = 'Loading demo trace…'
  loadingFileName.value = 'example.btf'
  await new Promise(r => requestAnimationFrame(r))

  // Decode base64 → gzip bytes → UTF-8 text.
  const binStr  = atob(exampleBtfB64)
  const bytes   = new Uint8Array(binStr.length)
  for (let i = 0; i < binStr.length; i++) bytes[i] = binStr.charCodeAt(i)

  const compressed = new Blob([bytes], { type: 'application/gzip' })
  const decompressedStream = compressed.stream().pipeThrough(new DecompressionStream('gzip'))
  const text = await new Response(decompressedStream).text()
  await onTraceLoaded({ text, name: 'example.btf' })
}

function onLoadDemo() {
  loadExampleBtf().catch((err) => {
    console.error('Demo load failed:', err)
    showToast('Failed to load demo trace: ' + (err?.message || String(err)), 'error')
    loading.value = false
  })
}

onMounted(() => {
  applyAppSettings(loadSettings(), { silent: true })
  const saved = loadSession()
  if (saved?.timelineOptions) {
    Object.assign(timelineOptions, saved.timelineOptions)
    syncTimelineOptionsFromSettings()
  }
  applySavedLayout(saved?.layout, {
    rightPanelWidth,
    cpuLoadPaneHeight,
    sectionHeights: statsSectionHeights,
    setCpuLoadUserSized: () => { _cpuLoadUserSized = true },
  })
  rightPanelTab.value = appSettings.showStats ? 'stats' : 'marks'
  window.addEventListener('keydown', onGlobalKeydown)
})

onBeforeUnmount(() => {
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
  window.removeEventListener('keydown', onGlobalKeydown)
})

// ---- Marks (bookmarks + annotations) -------------------------------------
function onAddMark() {
  // Priority: mouse hover position → last-moved/placed cursor → viewport center
  if (!trace.value) return
  const hoverNs  = timelinePanelRef.value?.getHoverTime?.() ?? null
  const cursorNs = timelinePanelRef.value?.getLastActiveCursorTime?.() ?? null
  const ns = hoverNs ?? cursorNs ?? (timelinePanelRef.value?.getViewportCenter?.()
    ?? (trace.value.timeMin + (trace.value.timeMax - trace.value.timeMin) / 2))
  addMarkAtNs(ns, 'bookmark')
}

function onAddAnnotationAtCenter() {
  if (!trace.value) return
  const hoverNs  = timelinePanelRef.value?.getHoverTime?.() ?? null
  const cursorNs = timelinePanelRef.value?.getLastActiveCursorTime?.() ?? null
  const ns = hoverNs ?? cursorNs ?? (timelinePanelRef.value?.getViewportCenter?.()
    ?? (trace.value.timeMin + (trace.value.timeMax - trace.value.timeMin) / 2))
  addMarkAtNs(ns, 'annotation')
}

function onAddBookmark(ns) {
  // Called from TimelinePanel right-click context menu
  addMarkAtNs(ns, 'bookmark')
}

function onAddAnnotation(ns) {
  addMarkAtNs(ns, 'annotation')
}

function addMarkAtNs(ns, type = 'bookmark', label = '') {
  if (!trace.value || !activeTab.value) return
  pushUndoSnapshot()
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
  addMarkAtNs(ns, 'annotation', note)
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
    saveSession(buildSessionSnapshot({
      timelineOptions,
      layout: {
        rightPanelWidth: rightPanelWidth.value,
        cpuLoadPaneHeight: cpuLoadPaneHeight.value,
        sectionHeights: { ...statsSectionHeights.value },
      },
    }))
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

function onClearMarks() {
  pushUndoSnapshot()
  marks.value = []
}

function onExportSession() {
  if (!activeTab.value) return
  const payload = buildPortableSession({
    traceName: activeTab.value.name,
    cursors: cursors.value,
    marks: marks.value,
    markNextId: activeTab.value.markNextId,
    timelineViewport: { ...timelineViewport.value },
    timelineOptions,
    findQuery: findQuery.value,
    findMode: findMode.value,
    pinnedHighlightKey: pinnedHighlightKey.value,
  })
  const base = (activeTab.value.name || 'trace').replace(/\.btf$/i, '')
  downloadPortableSession(payload, `${base}-session.json`)
  showToast('Session exported', 'info')
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
    resizeTabCursors(tabs.value, appSettings.maxCursors)
    nextTick(() => {
      applyTimelineViewport()
      if (findQuery.value) recomputeFind()
      scheduleRender()
    })
    showToast('Session imported', 'info')
  } catch (err) {
    showToast(err?.message || 'Failed to import session', 'error')
  }
}
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
  --sb-thumb:       rgba(160, 160, 160, 0.40);
  --sb-thumb-hover: rgba(160, 160, 160, 0.65);
}

.app:not(.dark) {
  --bg:            #FFFFFF;
  --panel-bg:      #F5F5F5;
  --ruler-bg:      #EEEEEE;
  --tb-bg:         #F0F0F0;
  --tb-btn-hover:  rgba(0,0,0,0.06);
  --tb-btn-active: rgba(0,80,200,0.15);
  --border:        #DDDDDD;
  --fg:            #1E1E1E;
  --fg-dim:        #666666;
  --accent:        #0066CC;
  --sb-thumb:       rgba(80, 80, 80, 0.38);
  --sb-thumb-hover: rgba(80, 80, 80, 0.62);
}

* { box-sizing: border-box; margin: 0; padding: 0; }

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
  font-size: var(--ui-font-size, 13px);
  overflow: hidden;
}

.app {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: var(--bg);
  color: var(--fg);
}
.app.drag-over {
  outline: 2px dashed var(--accent);
  outline-offset: -4px;
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

.trace-tab-close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border-radius: 3px;
  font-size: 14px;
  line-height: 1;
  opacity: 0.65;
}

.trace-tab-close:hover {
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

.loading-overlay {
  position: absolute;
  inset: 0;
  z-index: 200;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.55);
  backdrop-filter: blur(2px);
}

.loading-card {
  background: var(--panel-bg);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 24px 32px;
  min-width: 320px;
  max-width: 480px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.5);
}

.dialog-overlay {
  position: absolute;
  inset: 0;
  z-index: 300;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(2px);
}

.help-dialog {
  width: min(760px, 92vw);
  max-height: min(82vh, 760px);
  background: var(--panel-bg);
  border: 1px solid var(--border);
  border-radius: 10px;
  box-shadow: 0 12px 36px rgba(0, 0, 0, 0.45);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.about-dialog {
  width: min(520px, 92vw);
  max-height: min(82vh, 720px);
  background: var(--panel-bg);
  border: 1px solid var(--border);
  border-radius: 12px;
  box-shadow: 0 12px 36px rgba(0, 0, 0, 0.45);
  display: flex;
  flex-direction: column;
  overflow: hidden;
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
  position: relative;
  width: 72px;
  height: 72px;
  border-radius: 16px;
  background: #1c3a6e;
  box-shadow: inset 0 0 0 1px rgba(255,255,255,0.08);
}

.about-icon .bar {
  position: absolute;
  left: 12px;
  height: 7px;
  border-radius: 999px;
}

.about-icon .bar-1 {
  top: 14px;
  width: 29px;
  background: #5b9bd5;
}

.about-icon .bar-2 {
  top: 26px;
  left: 18px;
  width: 22px;
  background: #7ec8e3;
}

.about-icon .bar-3 {
  top: 38px;
  width: 36px;
  background: #5b9bd5;
}

.about-icon .bar-4 {
  top: 50px;
  left: 22px;
  width: 18px;
  background: #7ec8e3;
}

.about-icon .marker {
  position: absolute;
  top: 10px;
  right: 24px;
  width: 2px;
  height: 46px;
  background: #ffc107;
}

.about-icon .marker::before {
  content: '';
  position: absolute;
  top: 0;
  left: -3px;
  width: 0;
  height: 0;
  border-left: 4px solid transparent;
  border-right: 4px solid transparent;
  border-top: 8px solid #ffc107;
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

@media (max-width: 760px) {
  .help-body {
    grid-template-columns: 1fr;
  }

  .about-grid {
    grid-template-columns: 1fr;
  }
}

.loading-filename {
  font-size: 13px;
  font-weight: 600;
  color: var(--fg);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.loading-msg {
  font-size: 11px;
  color: var(--fg-dim);
  font-family: monospace;
  min-height: 1.4em;
}

.loading-bar-track {
  height: 6px;
  border-radius: 3px;
  background: var(--border);
  overflow: hidden;
}

.loading-bar-fill {
  height: 100%;
  border-radius: 3px;
  background: var(--accent);
  transition: width 0.15s ease;
}

.loading-pct {
  font-size: 11px;
  font-family: monospace;
  color: var(--accent);
  text-align: right;
}

.right-panel {
  display: flex;
  flex-direction: column;
  width: 220px;
  flex-shrink: 0;
  border-left: 1px solid var(--border);
  background: var(--panel-bg);
  overflow: hidden;
}

.panel-tabs {
  display: flex;
  border-top: 1px solid var(--border);
  background: color-mix(in srgb, var(--panel-bg) 86%, var(--tb-bg));
  flex-shrink: 0;
}

.panel-tab {
  flex: 1;
  border: 0;
  border-right: 1px solid var(--border);
  background: transparent;
  color: var(--fg-dim);
  font-size: 11px;
  font-family: monospace;
  font-weight: 500;
  padding: 3px 8px;
  min-height: 24px;
  cursor: pointer;
}

.panel-tab:last-child {
  border-right: 0;
}

.panel-tab:hover {
  background: var(--tb-btn-hover);
  color: var(--fg);
}

.panel-tab.active {
  color: var(--fg);
  background: var(--panel-bg);
  box-shadow: inset 0 2px 0 var(--accent);
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
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--fg-dim);
  padding: 6px 10px 4px;
  border-bottom: 1px solid var(--border);
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
}

.status-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
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
</style>
