<template>
  <div
    ref="toolbarEl"
    class="toolbar"
  >
    <!-- Brand / About (web-only) -->
    <button
      class="app-name-btn"
      title="About RTOS BTF Viewer"
      aria-label="About RTOS BTF Viewer"
      @click="emit('showAbout')"
    >
      <svg
        width="16"
        height="16"
        viewBox="0 0 72 72"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden="true"
      >
        <rect
          x="3"
          y="3"
          width="66"
          height="66"
          rx="14"
          fill="#1c3a6e"
        />
        <rect
          x="12"
          y="16"
          width="29"
          height="7"
          rx="3"
          fill="#5b9bd5"
        />
        <rect
          x="18"
          y="28"
          width="22"
          height="7"
          rx="3"
          fill="#7ec8e3"
        />
        <rect
          x="12"
          y="40"
          width="36"
          height="7"
          rx="3"
          fill="#5b9bd5"
        />
        <rect
          x="22"
          y="52"
          width="18"
          height="7"
          rx="3"
          fill="#7ec8e3"
        />
        <rect
          x="40"
          y="12"
          width="3"
          height="46"
          rx="1"
          fill="#ffc107"
        />
        <polygon
          points="41.5,8 38,16 45,16"
          fill="#ffc107"
        />
      </svg>
    </button>

    <div class="tb-sep" />

    <!-- g1: File — Open · Demo · PNG · SVG · Perfetto -->
    <Teleport
      :to="overflowPanelEl ?? 'body'"
      :disabled="!overflow.g1"
    >
      <div
        :ref="el => setGroupRef('g1', el)"
        class="tb-group"
      >
        <label
          v-if="!useFsaOpen"
          class="tb-btn file-btn"
          title="Open BTF trace file (Ctrl+O)"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
            aria-hidden="true"
          >
            <path d="M1 3.5A1.5 1.5 0 0 1 2.5 2h2.764c.958 0 1.76.56 2.311 1.184C7.985 3.648 8.48 4 9 4h4.5A1.5 1.5 0 0 1 15 5.5v7a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 1 12.5v-9z" />
          </svg>
          <span class="tb-label">Open</span>
          <input
            type="file"
            :accept="BTF_FILE_ACCEPT"
            style="display:none"
            @change="onFileChange"
          >
        </label>
        <button
          v-else
          class="tb-btn"
          title="Open BTF trace file (Ctrl+O)"
          @click="onOpenClick"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
            aria-hidden="true"
          >
            <path d="M1 3.5A1.5 1.5 0 0 1 2.5 2h2.764c.958 0 1.76.56 2.311 1.184C7.985 3.648 8.48 4 9 4h4.5A1.5 1.5 0 0 1 15 5.5v7a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 1 12.5v-9z" />
          </svg>
          <span class="tb-label">Open</span>
        </button>
        <button
          class="tb-btn"
          title="Load the bundled demo trace"
          @click="emit('loadDemo')"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
            aria-hidden="true"
          >
            <path d="M3 2.5A1.5 1.5 0 0 1 4.5 1h7A1.5 1.5 0 0 1 13 2.5v11a1.5 1.5 0 0 1-1.5 1.5h-7A1.5 1.5 0 0 1 3 13.5v-11zm3 2.354v6.292L11 8 6 4.854z" />
          </svg>
          <span class="tb-label">Demo</span>
        </button>
        <button
          v-if="traceInfo"
          class="tb-btn"
          title="Open snapshot editor (Ctrl+S)"
          @click="emit('copyScreenshot')"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
            aria-hidden="true"
          >
            <path d="M2 1a1 1 0 0 0-1 1v12a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V4.5L11.5 1H2zm2 1h5v3H4V2zm4 8a1.5 1.5 0 1 1 0-3 1.5 1.5 0 0 1 0 3zM3 10h10v4H3v-4z" />
          </svg>
        </button>
        <button
          v-if="traceInfo"
          class="tb-btn"
          title="Save viewport as SVG (Ctrl+Shift+S)"
          @click="emit('exportSvg')"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
            aria-hidden="true"
          >
            <path d="M7.5 1a.5.5 0 0 1 .5.5v8.793l2.146-2.147a.5.5 0 0 1 .708.708l-3 3a.5.5 0 0 1-.708 0l-3-3a.5.5 0 0 1 .708-.708L7 10.293V1.5a.5.5 0 0 1 .5-.5zM2.5 13a.5.5 0 0 1 .5-.5h10a.5.5 0 0 1 0 1H3a.5.5 0 0 1-.5-.5z" />
          </svg>
        </button>
        <button
          v-if="traceInfo"
          class="tb-btn"
          title="Export Perfetto (Chrome Trace JSON for ui.perfetto.dev)"
          @click="emit('exportPerfetto')"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
            aria-hidden="true"
          >
            <path d="M2.5 2A1.5 1.5 0 0 0 1 3.5v9A1.5 1.5 0 0 0 2.5 14h11a1.5 1.5 0 0 0 1.5-1.5v-9A1.5 1.5 0 0 0 13.5 2h-11zm0 1h11a.5.5 0 0 1 .5.5V5H2V3.5a.5.5 0 0 1 .5-.5zM2 6h12v6.5a.5.5 0 0 1-.5.5h-11a.5.5 0 0 1-.5-.5V6zm2 1.5v1h2v-1H4zm3 0v1h2v-1H7zm3 0v1h2v-1h-2zM4 10v1h5v-1H4z" />
          </svg>
        </button>
        <div class="tb-sep" />
      </div>
    </Teleport>

    <!-- g2: Orientation — Horizontal · Vertical -->
    <Teleport
      :to="overflowPanelEl ?? 'body'"
      :disabled="!overflow.g2"
    >
      <div
        :ref="el => setGroupRef('g2', el)"
        class="tb-group"
      >
        <button
          type="button"
          class="tb-btn"
          :class="{ active: (modelValue.orientation || 'h') === 'h' }"
          title="Horizontal layout — time runs left → right"
          @click="emit('update:modelValue', { ...modelValue, orientation: 'h' })"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
            aria-hidden="true"
          >
            <path d="M1 4h14v2H1zm0 4h14v2H1zm0 4h14v2H1z" />
          </svg>
        </button>
        <button
          type="button"
          class="tb-btn"
          :class="{ active: (modelValue.orientation || 'h') === 'v' }"
          title="Vertical layout — time runs top → bottom"
          @click="emit('update:modelValue', { ...modelValue, orientation: 'v' })"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
            aria-hidden="true"
          >
            <path d="M3 1h2v14H3zm4 0h2v14H7zm4 0h2v14h-2z" />
          </svg>
        </button>
        <div class="tb-sep" />
      </div>
    </Teleport>

    <!-- g3: Zoom — In · Out · 1:1 · Fit · Range · Find -->
    <Teleport
      :to="overflowPanelEl ?? 'body'"
      :disabled="!overflow.g3"
    >
      <div
        :ref="el => setGroupRef('g3', el)"
        class="tb-group"
      >
        <button
          class="tb-btn"
          title="Zoom in (Ctrl++)"
          @click="emit('zoom', 0.7)"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
            aria-hidden="true"
          >
            <path d="M6.5 1a5.5 5.5 0 1 0 3.89 9.4l3.4 3.4.7-.7-3.4-3.4A5.5 5.5 0 0 0 6.5 1zm0 1a4.5 4.5 0 1 1 0 9 4.5 4.5 0 0 1 0-9zM6 5v1.5H4.5v1H6V9h1V7.5h1.5v-1H7V5H6z" />
          </svg>
        </button>
        <button
          class="tb-btn"
          title="Zoom out (Ctrl+-)"
          @click="emit('zoom', 1.43)"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
            aria-hidden="true"
          >
            <path d="M6.5 1a5.5 5.5 0 1 0 3.89 9.4l3.4 3.4.7-.7-3.4-3.4A5.5 5.5 0 0 0 6.5 1zm0 1a4.5 4.5 0 1 1 0 9 4.5 4.5 0 0 1 0-9zM4 6h5v1H4V6z" />
          </svg>
        </button>
        <button
          v-if="traceInfo"
          class="tb-btn tb-btn-text"
          :title="zoom1to1Title"
          @click="emit('zoom1to1')"
        >
          1:1
        </button>
        <button
          class="tb-btn"
          title="Fit entire trace to window (Ctrl+0)"
          @click="emit('fit')"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
            aria-hidden="true"
          >
            <path d="M1.5 1h5v1h-4v4h-1V1.5a.5.5 0 0 1 .5-.5zm13 0a.5.5 0 0 1 .5.5V6h-1V2h-4V1h4.5zM1 10h1v4h4v1H1.5a.5.5 0 0 1-.5-.5V10zm14 0v4.5a.5.5 0 0 1-.5.5H10v-1h4v-4h1z" />
          </svg>
        </button>
        <button
          v-if="traceInfo"
          class="tb-btn"
          :class="{ disabled: !rangeEnabled }"
          :disabled="!rangeEnabled"
          title="Zoom view to fit between cursor C1 and last cursor (Ctrl+R)"
          @click="rangeEnabled && emit('zoomRange')"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
            aria-hidden="true"
          >
            <path d="M3 1h1v14H3zM12 1h1v14h-1zM4 5l3 3-3 3zM12 5l-3 3 3 3z" />
          </svg>
        </button>
        <button
          v-if="traceInfo"
          class="tb-btn"
          title="Find task, annotation, or migration (Ctrl+F)"
          @click="emit('showFind')"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
            aria-hidden="true"
          >
            <path d="M6.5 1a5.5 5.5 0 1 0 3.89 9.4l3.4 3.4.7-.7-3.4-3.4A5.5 5.5 0 0 0 6.5 1zm0 1a4.5 4.5 0 1 1 0 9 4.5 4.5 0 0 1 0-9z" />
          </svg>
        </button>
        <div class="tb-sep" />
      </div>
    </Teleport>

    <!-- g4: View — Task · Core · Expand All · Load · Heatmap · All · Analysis -->
    <Teleport
      :to="overflowPanelEl ?? 'body'"
      :disabled="!overflow.g4"
    >
      <div
        :ref="el => setGroupRef('g4', el)"
        class="tb-group"
      >
        <button
          type="button"
          class="tb-btn tb-btn-labeled"
          :class="{ active: modelValue.viewMode === 'task' }"
          title="Task View — one row per task, merges across cores"
          @click="emit('update:modelValue', { ...modelValue, viewMode: 'task' })"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
            aria-hidden="true"
          >
            <path d="M1 2.5A1.5 1.5 0 0 1 2.5 1h11A1.5 1.5 0 0 1 15 2.5v11a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 1 13.5v-11zM4 5.5h8v1H4v-1zm0 3h8v1H4v-1zm0 3h5v1H4v-1z" />
          </svg>
          <span class="tb-label">Task</span>
        </button>
        <button
          type="button"
          class="tb-btn tb-btn-labeled"
          :class="{ active: modelValue.viewMode === 'core' }"
          title="Core View — one expandable row per CPU core"
          @click="emit('update:modelValue', { ...modelValue, viewMode: 'core' })"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
            aria-hidden="true"
          >
            <path d="M5 1v2H3a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h2v2h1v-2h4v2h1v-2h2a2 2 0 0 0 2-2V5a2 2 0 0 0-2-2h-2V1h-1v2H6V1H5zm-2 4h10v6H3V5zm2 1v4h6V6H5z" />
          </svg>
          <span class="tb-label">Core</span>
        </button>

        <button
          v-if="modelValue.viewMode === 'core'"
          class="tb-btn"
          :class="{ active: coresExpanded }"
          title="Expand / collapse all cores (only in Core View)"
          @click="toggleExpandAll"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
            aria-hidden="true"
          >
            <path d="M8 1l2.5 3h-2v3h-1V4H5.5zM8 15l-2.5-3h2v-3h1V12h2.5zM2 7.5h12v1H2z" />
          </svg>
        </button>

        <button
          type="button"
          class="tb-btn tb-btn-labeled"
          :class="{ active: modelValue.showCpuLoad !== false }"
          title="Show / hide CPU load graph"
          @click="emit('update:modelValue', { ...modelValue, showCpuLoad: modelValue.showCpuLoad === false })"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
            aria-hidden="true"
          >
            <path d="M1 11a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v3H1v-3zm5-4a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v7H6V7zm5-3a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v10h-4V4z" />
          </svg>
          <span class="tb-label">Load</span>
        </button>

        <button
          class="tb-btn"
          :class="{ disabled: !heatmapEnabled }"
          :disabled="!heatmapEnabled"
          title="Migration & Corridor Inspector — topology + timeline (multi-core traces only)"
          @click="heatmapEnabled && emit('showHeatmap')"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
            aria-hidden="true"
          >
            <path d="M1 1h4v4H1V1zm5 0h4v4H6V1zm5 0h4v4h-4V1zM1 6h4v4H1V6zm5 0h4v4H6V6zm5 0h4v4h-4V6zM1 11h4v4H1v-4zm5 0h4v4H6v-4zm5 0h4v4h-4v-4z" />
          </svg>
        </button>

        <button
          v-if="taskFilterActive"
          class="tb-btn active tb-btn-labeled"
          title="Clear heatmap task filter and show all tasks"
          @click="emit('clearTaskFilter')"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            aria-hidden="true"
          >
            <path
              fill="currentColor"
              d="M1 1h4v4H1V1zm5 0h4v4H6V1zm5 0h4v4h-4V1zM1 6h4v4H1V6zm5 0h4v4H6V6zm5 0h4v4h-4V6zM1 11h4v4H1v-4zm5 0h4v4H6v-4zm5 0h4v4h-4v-4z"
            />
            <line
              x1="2"
              y1="14"
              x2="14"
              y2="2"
              class="tb-heatmap-slash-outline"
              stroke-width="3.4"
              stroke-linecap="round"
            />
            <line
              x1="2"
              y1="14"
              x2="14"
              y2="2"
              class="tb-heatmap-slash"
              stroke-width="2"
              stroke-linecap="round"
            />
          </svg>
          <span class="tb-label">All</span>
        </button>

        <button
          class="tb-btn tb-btn-labeled"
          :class="{ disabled: !analysisEnabled }"
          :disabled="!analysisEnabled"
          title="Analysis Findings — heuristic load balance, WCET, blocking, thrashing, deadlines, tick, sync"
          @click="analysisEnabled && emit('showAnalysis')"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
            aria-hidden="true"
          >
            <path d="M2 1.5A.5.5 0 0 1 2.5 1h9A1.5 1.5 0 0 1 13 2.5v11a1.5 1.5 0 0 1-1.5 1.5h-9A.5.5 0 0 1 2 14.5v-13zM3 2v12h8.5a.5.5 0 0 0 .5-.5v-11a.5.5 0 0 0-.5-.5H3zm1.5 2h6v1h-6V4zm0 2.5h6v1h-6v-1zm0 2.5h4v1h-4V9z" />
          </svg>
          <span class="tb-label">Analysis</span>
        </button>
        <div class="tb-sep" />
      </div>
    </Teleport>

    <!-- g5: Log₂ -->
    <Teleport
      :to="overflowPanelEl ?? 'body'"
      :disabled="!overflow.g5"
    >
      <div
        :ref="el => setGroupRef('g5', el)"
        class="tb-group"
      >
        <button
          type="button"
          class="tb-btn tb-btn-text"
          :class="{ active: modelValue.stiLogScale }"
          title="STI waveform y-axis: toggle between linear and log₂ scale (only active when an STI row is expanded)"
          @click="emit('update:modelValue', { ...modelValue, stiLogScale: !modelValue.stiLogScale })"
        >
          Log₂
        </button>
        <div class="tb-sep" />
      </div>
    </Teleport>

    <!-- g6: Theme -->
    <Teleport
      :to="overflowPanelEl ?? 'body'"
      :disabled="!overflow.g6"
    >
      <div
        :ref="el => setGroupRef('g6', el)"
        class="tb-group"
      >
        <button
          type="button"
          class="tb-btn"
          :title="modelValue.darkMode ? 'Switch to light theme' : 'Switch to dark theme'"
          @click="emit('update:modelValue', { ...modelValue, darkMode: !modelValue.darkMode })"
        >
          <svg
            v-if="modelValue.darkMode"
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
            aria-hidden="true"
          >
            <path d="M8 1.5a.5.5 0 0 1 .5.5V3a.5.5 0 0 1-1 0V2a.5.5 0 0 1 .5-.5zM11.9 4.1a.5.5 0 0 1 0 .7l-.7.7a.5.5 0 1 1-.7-.7l.7-.7a.5.5 0 0 1 .7 0zM14 7.5a.5.5 0 0 1 0 1h-1a.5.5 0 0 1 0-1h1zM11.2 11.2a.5.5 0 0 1 .7 0l.7.7a.5.5 0 0 1-.7.7l-.7-.7a.5.5 0 0 1 0-.7zM8 12a.5.5 0 0 1 .5.5V14a.5.5 0 0 1-1 0v-1.5A.5.5 0 0 1 8 12zM4.1 11.2a.5.5 0 0 1 0 .7l-.7.7a.5.5 0 0 1-.7-.7l.7-.7a.5.5 0 0 1 .7 0zM3 7.5a.5.5 0 0 1 0 1H2a.5.5 0 0 1 0-1h1zM4.8 4.1a.5.5 0 0 1-.7 0l-.7-.7a.5.5 0 1 1 .7-.7l.7.7a.5.5 0 0 1 0 .7zM8 5a3 3 0 1 0 0 6 3 3 0 0 0 0-6z" />
          </svg>
          <svg
            v-else
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
            aria-hidden="true"
          >
            <path d="M6 .278a.768.768 0 0 1 .08.858 7.208 7.208 0 0 0-.878 3.46c0 4.021 3.278 7.277 7.318 7.277.527 0 1.04-.055 1.533-.16a.787.787 0 0 1 .81.316.733.733 0 0 1-.031.893A8.349 8.349 0 0 1 8.344 16C3.734 16 0 12.286 0 7.71 0 4.266 2.114 1.312 5.124.06A.752.752 0 0 1 6 .278z" />
          </svg>
        </button>
      </div>
    </Teleport>

    <div
      v-show="anyOverflow"
      class="tb-overflow"
    >
      <button
        ref="overflowBtnEl"
        class="tb-btn tb-overflow-btn"
        :class="{ active: overflowMenuOpen }"
        title="More toolbar options"
        @click="overflowMenuOpen = !overflowMenuOpen"
      >
        ⋯
      </button>
      <div
        v-show="overflowMenuOpen"
        ref="overflowPanelEl"
        class="tb-overflow-panel"
      />
    </div>

    <div class="spacer" />

    <span
      v-if="loading"
      class="loading-badge"
    >
      <span class="loading-badge-text">
        {{ loadingMsg || 'Parsing…' }}
        <span
          v-if="loadingPct > 0"
          class="loading-badge-pct"
        >{{ loadingPct }}%</span>
      </span>
      <span class="loading-badge-bar">
        <span
          class="loading-badge-fill"
          :style="{ width: Math.max(4, loadingPct) + '%' }"
        />
      </span>
    </span>

    <button
      class="tb-btn"
      title="Open Settings (Ctrl+,)"
      @click="emit('showSettings')"
    >
      <svg
        viewBox="0 0 16 16"
        width="16"
        height="16"
        fill="currentColor"
        aria-hidden="true"
      >
        <path d="M8 4.754a3.246 3.246 0 1 0 0 6.492 3.246 3.246 0 0 0 0-6.492zM5.754 8a2.246 2.246 0 1 1 4.492 0 2.246 2.246 0 0 1-4.492 0z" />
        <path d="M9.796 1.343c-.527-1.79-3.065-1.79-3.592 0l-.094.319a.873.873 0 0 1-1.255.52l-.292-.16c-1.64-.892-3.433.902-2.54 2.541l.159.292a.873.873 0 0 1-.52 1.255l-.319.094c-1.79.527-1.79 3.065 0 3.592l.319.094a.873.873 0 0 1 .52 1.255l-.16.292c-.892 1.64.901 3.434 2.541 2.54l.292-.159a.873.873 0 0 1 1.255.52l.094.319c.527 1.79 3.065 1.79 3.592 0l.094-.319a.873.873 0 0 1 1.255-.52l.292.16c1.64.893 3.434-.902 2.54-2.541l-.159-.292a.873.873 0 0 1 .52-1.255l.319-.094c1.79-.527 1.79-3.065 0-3.592l-.319-.094a.873.873 0 0 1-.52-1.255l.16-.292c.893-1.64-.902-3.433-2.541-2.54l-.292.159a.873.873 0 0 1-1.255-.52l-.094-.319z" />
      </svg>
    </button>

    <button
      class="tb-btn"
      title="Help & keyboard shortcuts (?)"
      @click="emit('showHelp')"
    >
      <svg
        viewBox="0 0 16 16"
        width="16"
        height="16"
        fill="currentColor"
        aria-hidden="true"
      >
        <path d="M8 1a7 7 0 1 0 0 14A7 7 0 0 0 8 1zm0 13A6 6 0 1 1 8 2a6 6 0 0 1 0 12zm0-3.1a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5zM8.2 4.2c-1.2 0-2 .8-2.1 1.9h1c.1-.6.5-1 1.1-1 .7 0 1.1.4 1.1 1 0 .4-.2.7-.8 1.1-.8.5-1.3 1-1.3 2v.3h1v-.2c0-.6.3-.9.9-1.3.7-.5 1.2-1 1.2-1.9 0-1.1-.9-1.9-2.1-1.9z" />
      </svg>
    </button>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
import { getTimelineLayout } from '../utils/timelineLayout.js'
import { supportsFileHandles, pickAndReadBtf } from '../utils/fileOpen.js'
import { BTF_FILE_ACCEPT, loadBtfEntriesFromFile } from '../utils/btfLoad.js'

const props = defineProps({
  modelValue:  { type: Object,  required: true },
  traceInfo:   { type: String,  default: '' },
  heatmapEnabled: { type: Boolean, default: false },
  analysisEnabled: { type: Boolean, default: false },
  taskFilterActive: { type: Boolean, default: false },
  rangeEnabled: { type: Boolean, default: false },
  loading:     { type: Boolean, default: false },
  loadingPct:  { type: Number,  default: 0 },
  loadingMsg:  { type: String,  default: '' },
  timeScale:   { type: String, default: 'ns' },
})

const emit = defineEmits([
  'update:modelValue', 'trace-reading', 'trace-loaded', 'traces-loaded', 'loadDemo', 'zoom', 'fit',
  'zoom1to1', 'zoomRange', 'showFind',
  'expandAll', 'collapseAll', 'addMark', 'copyScreenshot', 'exportSvg', 'exportPerfetto',
  'showHelp', 'showAbout', 'showSettings', 'showHeatmap', 'showAnalysis',
  'clearTaskFilter', 'file-error',
])

const useFsaOpen = supportsFileHandles()
const coresExpanded = ref(true)

function toggleExpandAll() {
  coresExpanded.value = !coresExpanded.value
  if (coresExpanded.value) emit('expandAll')
  else emit('collapseAll')
}

const zoom1to1Title = computed(() => {
  const tspx = getTimelineLayout().timescalePerPxDefault
  const u = props.timeScale || 'ns'
  return `Zoom to 1:1 scale (${tspx} ${u}/px)`
})

async function emitLoadedEntries(file) {
  emit('trace-reading', { name: file.name })
  try {
    const entries = await loadBtfEntriesFromFile(file)
    emit('traces-loaded', { entries, sourceName: file.name })
  } catch (err) {
    emit('file-error', `Failed to read "${file.name}"${err?.message ? `: ${err.message}` : ''}`)
  }
}

async function onOpenClick() {
  const file = await pickAndReadBtf()
  if (!file) return
  await emitLoadedEntries(file)
}

async function onFileChange(e) {
  const file = e.target.files[0]
  if (!file) return
  await emitLoadedEntries(file)
  e.target.value = ''
}

// ---- Responsive overflow (groups → ⋯) -------------------------------------
const toolbarEl = ref(null)
const overflowBtnEl = ref(null)
const overflowPanelEl = ref(null)
const overflowMenuOpen = ref(false)

const GROUP_ORDER = ['g1', 'g2', 'g3', 'g4', 'g5', 'g6']
const overflow = reactive(Object.fromEntries(GROUP_ORDER.map(k => [k, false])))
const anyOverflow = computed(() => GROUP_ORDER.some(k => overflow[k]))

const groupEls = {}
function setGroupRef(key, el) {
  if (el) groupEls[key] = el
}

async function recomputeOverflow() {
  const toolbar = toolbarEl.value
  if (!toolbar) return

  let resetAny = false
  for (const k of GROUP_ORDER) {
    if (overflow[k]) { overflow[k] = false; resetAny = true }
  }
  if (resetAny) await nextTick()

  for (let i = GROUP_ORDER.length - 1; i >= 0; i--) {
    if (toolbar.scrollWidth <= toolbar.clientWidth + 1) break
    overflow[GROUP_ORDER[i]] = true
    await nextTick()
  }
}

let recomputeQueued = false
function queueRecompute() {
  if (recomputeQueued) return
  recomputeQueued = true
  requestAnimationFrame(() => {
    recomputeQueued = false
    recomputeOverflow()
  })
}

function onDocumentClick(e) {
  if (!overflowMenuOpen.value) return
  if (overflowBtnEl.value?.contains(e.target)) return
  if (overflowPanelEl.value?.contains(e.target)) return
  overflowMenuOpen.value = false
}

let resizeObserver = null

onMounted(() => {
  queueRecompute()
  resizeObserver = new ResizeObserver(queueRecompute)
  if (toolbarEl.value) resizeObserver.observe(toolbarEl.value)
  document.addEventListener('click', onDocumentClick, true)
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  document.removeEventListener('click', onDocumentClick, true)
})

watch(
  () => [props.modelValue.viewMode, !!props.traceInfo, props.taskFilterActive],
  queueRecompute,
)
</script>

<style scoped>
.toolbar {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 4px 8px;
  background: var(--tb-bg);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  user-select: none;
  container-type: inline-size;
  container-name: toolbar;
}

.tb-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  padding: 4px 7px;
  min-width: 30px;
  min-height: 30px;
  border: 1px solid transparent;
  border-radius: 4px;
  background: transparent;
  color: var(--fg);
  font-size: 12px;
  font-family: inherit;
  cursor: pointer;
  white-space: nowrap;
  flex-shrink: 0;
  transition: background 0.1s;
}
.tb-btn:hover {
  background: var(--tb-btn-hover);
  border-color: var(--border);
}
.tb-btn.active {
  background: var(--tb-btn-active);
  border-color: var(--accent);
  color: var(--accent);
}
.tb-btn.disabled,
.tb-btn:disabled {
  opacity: 0.38;
  cursor: not-allowed;
  pointer-events: none;
}
.tb-btn-text {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  min-width: 34px;
}
.tb-btn-labeled {
  padding-inline: 8px;
}
.tb-label {
  font-size: 12px;
  font-weight: 600;
  line-height: 1;
}
.tb-heatmap-slash-outline {
  stroke: var(--tb-bg, var(--bg));
}
.tb-heatmap-slash {
  stroke: #E24B4A;
}

/* Hybrid: drop short labels when the bar is tight (desktop keeps icon+text for Task/Core/Load/Analysis) */
@container toolbar (max-width: 1100px) {
  .tb-label {
    display: none;
  }
}

.tb-sep {
  width: 1px;
  height: 20px;
  background: var(--border);
  margin: 0 2px;
  flex-shrink: 0;
}
.tb-group {
  display: flex;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
}

.tb-overflow {
  position: relative;
  flex-shrink: 0;
}
.tb-overflow-btn {
  font-weight: 700;
  letter-spacing: 1px;
}
.tb-overflow-panel {
  position: absolute;
  top: calc(100% + 4px);
  right: 0;
  z-index: 50;
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 200px;
  max-height: 70vh;
  overflow-y: auto;
  padding: 6px;
  background: var(--tb-bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
}
.tb-overflow-panel .tb-group {
  flex-wrap: wrap;
}
.tb-overflow-panel .tb-group + .tb-group {
  border-top: 1px solid var(--border);
  padding-top: 4px;
}
.tb-overflow-panel .tb-sep {
  display: none;
}
.tb-overflow-panel .tb-label {
  display: inline;
}

.spacer {
  flex: 1;
}
.loading-badge {
  display: inline-flex;
  flex-direction: column;
  align-items: stretch;
  gap: 2px;
  font-size: 11px;
  background: var(--accent);
  color: #000;
  padding: 3px 8px 4px;
  border-radius: 6px;
  min-width: 110px;
}
.loading-badge-text {
  display: flex;
  justify-content: space-between;
  gap: 6px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.loading-badge-pct {
  opacity: 0.7;
  flex-shrink: 0;
}
.loading-badge-bar {
  height: 3px;
  border-radius: 2px;
  background: rgba(0,0,0,0.2);
  overflow: hidden;
}
.loading-badge-fill {
  display: block;
  height: 100%;
  background: rgba(0,0,0,0.55);
  border-radius: 2px;
  transition: width 0.15s ease;
}
.file-btn {
  cursor: pointer;
}

.app-name-btn {
  background: none;
  border: none;
  color: var(--accent);
  font-size: 13px;
  font-weight: 700;
  font-family: inherit;
  cursor: pointer;
  padding: 4px 6px;
  min-width: 30px;
  min-height: 30px;
  border-radius: 4px;
  white-space: nowrap;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s;
}
.app-name-btn:hover {
  background: var(--tb-btn-hover);
}
</style>
