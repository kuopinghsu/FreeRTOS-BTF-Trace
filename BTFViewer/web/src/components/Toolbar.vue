<template>
  <div
    ref="toolbarEl"
    class="toolbar"
  >
    <!-- App name / About trigger -->
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
        style="display:inline-block;vertical-align:middle"
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

    <Teleport
      :to="overflowPanelEl ?? 'body'"
      :disabled="!overflow.g1"
    >
      <div
        :ref="el => setGroupRef('g1', el)"
        class="tb-group"
      >
        <!-- File open: label+input on file:// (last folder); FSA on http(s)/localhost -->
        <label
          v-if="!useFsaOpen"
          class="tb-btn file-btn"
          title="Open BTF file"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
          >
            <path d="M1 3.5A1.5 1.5 0 0 1 2.5 2h2.764c.958 0 1.76.56 2.311 1.184C7.985 3.648 8.48 4 9 4h4.5A1.5 1.5 0 0 1 15 5.5v7a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 1 12.5v-9z" />
          </svg>
          <input
            type="file"
            :accept="BTF_FILE_ACCEPT"
            style="display:none"
            @change="onFileChange"
          >
        </label>
        <button
          v-else
          class="tb-btn file-btn"
          title="Open BTF file"
          @click="onOpenClick"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
          >
            <path d="M1 3.5A1.5 1.5 0 0 1 2.5 2h2.764c.958 0 1.76.56 2.311 1.184C7.985 3.648 8.48 4 9 4h4.5A1.5 1.5 0 0 1 15 5.5v7a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 1 12.5v-9z" />
          </svg>
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
          >
            <path d="M3 2.5A1.5 1.5 0 0 1 4.5 1h7A1.5 1.5 0 0 1 13 2.5v11a1.5 1.5 0 0 1-1.5 1.5h-7A1.5 1.5 0 0 1 3 13.5v-11zm3 2.354v6.292L11 8 6 4.854z" />
          </svg>
        </button>

        <div class="tb-sep" />
      </div>
    </Teleport>

    <Teleport
      :to="overflowPanelEl ?? 'body'"
      :disabled="!overflow.g2"
    >
      <div
        :ref="el => setGroupRef('g2', el)"
        class="tb-group"
      >
        <!-- View mode -->
        <label
          class="tb-btn"
          :class="{ active: modelValue.viewMode === 'task' }"
          title="Task view"
          @click="emit('update:modelValue', { ...modelValue, viewMode: 'task' })"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
          >
            <path d="M1 2.5A1.5 1.5 0 0 1 2.5 1h11A1.5 1.5 0 0 1 15 2.5v11a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 1 13.5v-11zM4 5.5h8v1H4v-1zm0 3h8v1H4v-1zm0 3h5v1H4v-1z" />
          </svg>
        </label>
        <label
          class="tb-btn"
          :class="{ active: modelValue.viewMode === 'core' }"
          title="Core view"
          @click="emit('update:modelValue', { ...modelValue, viewMode: 'core' })"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
          >
            <path d="M5 1v2H3a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h2v2h1v-2h4v2h1v-2h2a2 2 0 0 0 2-2V5a2 2 0 0 0-2-2h-2V1h-1v2H6V1H5zm-2 4h10v6H3V5zm2 1v4h6V6H5z" />
          </svg>
        </label>

        <!-- Expand / Collapse all cores (core mode only) -->
        <template v-if="modelValue.viewMode === 'core'">
          <div class="tb-sep" />
          <button
            class="tb-btn"
            title="Expand all cores"
            @click="emit('expandAll')"
          >
            <svg
              viewBox="0 0 16 16"
              width="16"
              height="16"
              fill="currentColor"
            >
              <path d="M8 2v5H3v1h5v5h1V8h5V7H9V2H8z" />
            </svg>
          </button>
          <button
            class="tb-btn"
            title="Collapse all cores"
            @click="emit('collapseAll')"
          >
            <svg
              viewBox="0 0 16 16"
              width="16"
              height="16"
              fill="currentColor"
            >
              <path d="M2 7h12v2H2z" />
            </svg>
          </button>
        </template>

        <div class="tb-sep" />
      </div>
    </Teleport>

    <Teleport
      :to="overflowPanelEl ?? 'body'"
      :disabled="!overflow.g3"
    >
      <div
        :ref="el => setGroupRef('g3', el)"
        class="tb-group"
      >
        <label
          class="tb-btn"
          :class="{ active: modelValue.showCpuLoad !== false }"
          title="Show or hide CPU load graph"
          @click="emit('update:modelValue', { ...modelValue, showCpuLoad: modelValue.showCpuLoad === false })"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
          >
            <path d="M1 11a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v3H1v-3zm5-4a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v7H6V7zm5-3a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v10h-4V4z" />
          </svg>
        </label>

        <button
          class="tb-btn"
          :class="{ disabled: !heatmapEnabled }"
          :disabled="!heatmapEnabled"
          title="Migration heatmap — core-pair counts over time (multi-core traces only)"
          @click="heatmapEnabled && emit('showHeatmap')"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
          >
            <path d="M1 1h4v4H1V1zm5 0h4v4H6V1zm5 0h4v4h-4V1zM1 6h4v4H1V6zm5 0h4v4H6V6zm5 0h4v4h-4V6zM1 11h4v4H1v-4zm5 0h4v4H6v-4zm5 0h4v4h-4v-4z" />
          </svg>
        </button>

        <button
          class="tb-btn"
          :class="{ disabled: !heatmapEnabled }"
          :disabled="!heatmapEnabled"
          title="Migration chord diagram — directional core-to-core migration volume (multi-core traces only)"
          @click="heatmapEnabled && emit('showChord')"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
          >
            <circle
              cx="8"
              cy="8"
              r="6.5"
              fill="none"
              stroke="currentColor"
              stroke-width="1.4"
            />
            <path
              d="M2.3 5.6 C 6 8, 10 8, 13.7 5.6"
              fill="none"
              stroke="currentColor"
              stroke-width="1.4"
            />
            <path
              d="M2.3 10.4 C 6 8, 10 8, 13.7 10.4"
              fill="none"
              stroke="currentColor"
              stroke-width="1.4"
            />
          </svg>
        </button>

        <button
          class="tb-btn"
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
          >
            <path d="M2 1.5A.5.5 0 0 1 2.5 1h9A1.5 1.5 0 0 1 13 2.5v11a1.5 1.5 0 0 1-1.5 1.5h-9A.5.5 0 0 1 2 14.5v-13zM3 2v12h8.5a.5.5 0 0 0 .5-.5v-11a.5.5 0 0 0-.5-.5H3zm1.5 2h6v1h-6V4zm0 2.5h6v1h-6v-1zm0 2.5h4v1h-4V9z" />
          </svg>
        </button>

        <button
          v-if="taskFilterActive"
          class="tb-btn active"
          title="Clear heatmap task filter and show all tasks"
          @click="emit('clearTaskFilter')"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
          >
            <path d="M2 3h12v1H2V3zm0 4h12v1H2V7zm0 4h12v1H2v-1zm0 4h8v1H2v-1z" />
          </svg>
        </button>

        <div class="tb-sep" />
      </div>
    </Teleport>

    <Teleport
      :to="overflowPanelEl ?? 'body'"
      :disabled="!overflow.g4"
    >
      <div
        :ref="el => setGroupRef('g4', el)"
        class="tb-group"
      >
        <!-- Zoom controls -->
        <button
          class="tb-btn"
          title="Zoom in (Ctrl+scroll)"
          @click="emit('zoom', 0.7)"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
          >
            <path d="M6.5 1a5.5 5.5 0 1 0 3.89 9.4l3.4 3.4.7-.7-3.4-3.4A5.5 5.5 0 0 0 6.5 1zm0 1a4.5 4.5 0 1 1 0 9 4.5 4.5 0 0 1 0-9zM6 5v1.5H4.5v1H6V9h1V7.5h1.5v-1H7V5H6z" />
          </svg>
        </button>
        <button
          class="tb-btn"
          title="Zoom out (Ctrl+scroll)"
          @click="emit('zoom', 1.43)"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
          >
            <path d="M6.5 1a5.5 5.5 0 1 0 3.89 9.4l3.4 3.4.7-.7-3.4-3.4A5.5 5.5 0 0 0 6.5 1zm0 1a4.5 4.5 0 1 1 0 9 4.5 4.5 0 0 1 0-9zM4 6h5v1H4V6z" />
          </svg>
        </button>
        <button
          class="tb-btn"
          title="Fit to window"
          @click="emit('fit')"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
          >
            <path d="M1.5 1h5v1h-4v4h-1V1.5a.5.5 0 0 1 .5-.5zm13 0a.5.5 0 0 1 .5.5V6h-1V2h-4V1h4.5zM1 10h1v4h4v1H1.5a.5.5 0 0 1-.5-.5V10zm14 0v4.5a.5.5 0 0 1-.5.5H10v-1h4v-4h1z" />
          </svg>
        </button>
        <button
          v-if="traceInfo"
          class="tb-btn"
          :title="zoom1to1Title"
          @click="emit('zoom1to1')"
        >
          1:1
        </button>
        <button
          v-if="traceInfo"
          class="tb-btn"
          title="Zoom to cursor range (Ctrl+R)"
          @click="emit('zoomRange')"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
          >
            <path d="M2 2h4v1H3v3H2V2zm8 0h4v4h-1V3h-3V2zM2 10h1v3h3v1H2v-4zm11 0h1v4h-4v-1h3v-3zM5 5h6v6H5V5zm1 1v4h4V6H6z" />
          </svg>
        </button>
        <button
          v-if="traceInfo"
          class="tb-btn"
          title="Find task or migration (Ctrl+F)"
          @click="emit('showFind')"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
          >
            <path d="M11.742 10.344a6.5 6.5 0 1 0-1.397 1.398h-.001l3.85 3.85a1 1 0 0 0 1.415-1.414l-3.85-3.85zm-5.242 1.1a5.5 5.5 0 1 1 0-11 5.5 5.5 0 0 1 0 11z" />
          </svg>
        </button>

        <div class="tb-sep" />
      </div>
    </Teleport>

    <Teleport
      :to="overflowPanelEl ?? 'body'"
      :disabled="!overflow.g5"
    >
      <div
        :ref="el => setGroupRef('g5', el)"
        class="tb-group"
      >
        <button
          v-if="traceInfo"
          class="tb-btn"
          title="Copy timeline screenshot"
          @click="emit('copyScreenshot')"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
          >
            <path d="M3 3.5A1.5 1.5 0 0 1 4.5 2h7A1.5 1.5 0 0 1 13 3.5V5h1a1 1 0 0 1 1 1v6.5a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 1 12.5V6a1 1 0 0 1 1-1h1V3.5zm1 0V5h8V3.5a.5.5 0 0 0-.5-.5h-7a.5.5 0 0 0-.5.5zM8 7a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5z" />
          </svg>
        </button>

        <button
          v-if="traceInfo"
          class="tb-btn"
          title="Export timeline as SVG"
          @click="emit('exportSvg')"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
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
          >
            <path d="M2.5 2A1.5 1.5 0 0 0 1 3.5v9A1.5 1.5 0 0 0 2.5 14h11a1.5 1.5 0 0 0 1.5-1.5v-9A1.5 1.5 0 0 0 13.5 2h-11zm0 1h11a.5.5 0 0 1 .5.5V5H2V3.5a.5.5 0 0 1 .5-.5zM2 6h12v6.5a.5.5 0 0 1-.5.5h-11a.5.5 0 0 1-.5-.5V6zm2 1.5v1h2v-1H4zm3 0v1h2v-1H7zm3 0v1h2v-1h-2zM4 10v1h5v-1H4z" />
          </svg>
        </button>

        <div class="tb-sep" />
      </div>
    </Teleport>

    <Teleport
      :to="overflowPanelEl ?? 'body'"
      :disabled="!overflow.g6"
    >
      <div
        :ref="el => setGroupRef('g6', el)"
        class="tb-group"
      >
        <!-- Orientation toggle -->
        <label
          class="tb-btn"
          :class="{ active: (modelValue.orientation || 'h') === 'h' }"
          title="Horizontal timeline (time → right)"
          @click="emit('update:modelValue', { ...modelValue, orientation: 'h' })"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
          >
            <path
              d="M1 8h14M11 5l3 3-3 3"
              stroke="currentColor"
              stroke-width="1.5"
              fill="none"
              stroke-linecap="round"
            />
          </svg>
        </label>
        <label
          class="tb-btn"
          :class="{ active: (modelValue.orientation || 'h') === 'v' }"
          title="Vertical timeline (time ↓ down)"
          @click="emit('update:modelValue', { ...modelValue, orientation: 'v' })"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
          >
            <path
              d="M8 1v14M5 11l3 3 3-3"
              stroke="currentColor"
              stroke-width="1.5"
              fill="none"
              stroke-linecap="round"
            />
          </svg>
        </label>

        <div class="tb-sep" />
      </div>
    </Teleport>

    <Teleport
      :to="overflowPanelEl ?? 'body'"
      :disabled="!overflow.g7"
    >
      <div
        :ref="el => setGroupRef('g7', el)"
        class="tb-group"
      >
        <!-- Grid toggle -->
        <label
          class="tb-btn"
          :class="{ active: modelValue.showGrid }"
          title="Toggle grid"
          @click="emit('update:modelValue', { ...modelValue, showGrid: !modelValue.showGrid })"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
          >
            <path d="M1 4h14v1H1zm0 4h14v1H1zm0 4h14v1H1zM4 1v14H5V1zm4 0v14H9V1zm4 0v14h1V1z" />
          </svg>
        </label>

        <label
          class="tb-btn"
          :class="{ active: modelValue.showSti !== false }"
          title="Show or hide STI channels"
          @click="emit('update:modelValue', { ...modelValue, showSti: modelValue.showSti === false })"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
          >
            <path d="M1 8h2l1.5-4L7 12l2-6 1.5 3H15" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </label>

        <label
          class="tb-btn"
          :class="{ active: modelValue.stiLogScale }"
          title="Toggle STI waveform scale: Linear / Log₂"
          @click="emit('update:modelValue', { ...modelValue, stiLogScale: !modelValue.stiLogScale })"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
          >
            <path d="M2 13V3h1.2v8.5H14V13H2zm3.2-2.2c0-2.4 1.5-4.2 3.8-4.2 1.3 0 2.3.5 3 1.4l-.9.7c-.5-.6-1.1-.9-1.9-.9-1.4 0-2.5 1.2-2.5 3s1.1 3 2.5 3c.8 0 1.4-.3 1.9-.9l.9.7c-.7.9-1.7 1.4-3 1.4-2.3 0-3.8-1.8-3.8-4.2z"/>
          </svg>
        </label>

        <!-- Dark mode toggle -->
        <label
          class="tb-btn"
          :class="{ active: modelValue.darkMode }"
          title="Toggle dark/light mode"
          @click="emit('update:modelValue', { ...modelValue, darkMode: !modelValue.darkMode })"
        >
          <svg
            viewBox="0 0 16 16"
            width="16"
            height="16"
            fill="currentColor"
          >
            <path d="M6 .278a.768.768 0 0 1 .08.858 7.208 7.208 0 0 0-.878 3.46c0 4.021 3.278 7.277 7.318 7.277.527 0 1.04-.055 1.533-.16a.787.787 0 0 1 .81.316.733.733 0 0 1-.031.893A8.349 8.349 0 0 1 8.344 16C3.734 16 0 12.286 0 7.71 0 4.266 2.114 1.312 5.124.06A.752.752 0 0 1 6 .278z" />
          </svg>
        </label>
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

    <button
      class="tb-btn"
      title="Settings (Ctrl+,)"
      @click="emit('showSettings')"
    >
      <svg
        viewBox="0 0 16 16"
        width="16"
        height="16"
        fill="currentColor"
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
      >
        <path d="M8 1a7 7 0 1 0 0 14A7 7 0 0 0 8 1zm0 13A6 6 0 1 1 8 2a6 6 0 0 1 0 12zm0-3.1a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5zM8.2 4.2c-1.2 0-2 .8-2.1 1.9h1c.1-.6.5-1 1.1-1 .7 0 1.1.4 1.1 1 0 .4-.2.7-.8 1.1-.8.5-1.3 1-1.3 2v.3h1v-.2c0-.6.3-.9.9-1.3.7-.5 1.2-1 1.2-1.9 0-1.1-.9-1.9-2.1-1.9z" />
      </svg>
    </button>

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
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
import { getTimelineLayout } from '../utils/timelineLayout.js'
import { supportsFileHandles, pickAndReadBtf } from '../utils/fileOpen.js'
import { BTF_FILE_ACCEPT, loadBtfTextFromFile } from '../utils/btfLoad.js'

const props = defineProps({
  modelValue:  { type: Object,  required: true },
  traceInfo:   { type: String,  default: '' },
  heatmapEnabled: { type: Boolean, default: false },
  analysisEnabled: { type: Boolean, default: false },
  taskFilterActive: { type: Boolean, default: false },
  loading:     { type: Boolean, default: false },
  loadingPct:  { type: Number,  default: 0 },
  loadingMsg:  { type: String,  default: '' },
  timeScale:   { type: String, default: 'ns' },
})

const emit = defineEmits([
  'update:modelValue', 'trace-reading', 'trace-loaded', 'loadDemo', 'zoom', 'fit',
  'zoom1to1', 'zoomRange', 'showFind',
  'expandAll', 'collapseAll', 'addMark', 'copyScreenshot', 'exportSvg', 'exportPerfetto',
  'showHelp', 'showAbout', 'showSettings', 'showHeatmap', 'showChord', 'showAnalysis',
  'clearTaskFilter', 'file-error',
])

const useFsaOpen = supportsFileHandles()

const zoom1to1Title = computed(() => {
  const tspx = getTimelineLayout().timescalePerPxDefault
  const u = props.timeScale || 'ns'
  return `Zoom to 1:1 scale (${tspx} ${u}/px)`
})

async function onOpenClick() {
  const file = await pickAndReadBtf()
  if (!file) return
  emit('trace-reading', { name: file.name })
  try {
    const text = await loadBtfTextFromFile(file)
    emit('trace-loaded', { text, name: file.name })
  } catch (err) {
    emit('file-error', `Failed to read "${file.name}"${err?.message ? `: ${err.message}` : ''}`)
  }
}

async function onFileChange(e) {
  const file = e.target.files[0]
  if (!file) return
  emit('trace-reading', { name: file.name })
  try {
    const text = await loadBtfTextFromFile(file)
    emit('trace-loaded', { text, name: file.name })
  } catch (err) {
    emit('file-error', `Failed to read "${file.name}"${err?.message ? `: ${err.message}` : ''}`)
  }
  e.target.value = ''
}

// ---- Responsive overflow menu ---------------------------------------------
// When the window is too narrow to fit every button group, groups are hidden
// from the right (via Teleport into the dropdown panel) until the remaining
// content fits, leaving the "More" (⋯) button on the right to reveal them.
const toolbarEl = ref(null)
const overflowBtnEl = ref(null)
const overflowPanelEl = ref(null)
const overflowMenuOpen = ref(false)

const GROUP_ORDER = ['g1', 'g2', 'g3', 'g4', 'g5', 'g6', 'g7']
const overflow = reactive(Object.fromEntries(GROUP_ORDER.map(k => [k, false])))
const anyOverflow = computed(() => GROUP_ORDER.some(k => overflow[k]))

const groupEls = {}
function setGroupRef(key, el) {
  if (el) groupEls[key] = el
}

async function recomputeOverflow() {
  const toolbar = toolbarEl.value
  if (!toolbar) return

  // Un-hide everything first so group widths reflect their natural (unclipped) size.
  let resetAny = false
  for (const k of GROUP_ORDER) {
    if (overflow[k]) { overflow[k] = false; resetAny = true }
  }
  if (resetAny) await nextTick()

  // Hide groups from the right, one at a time, until the rest fits.
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

// Content that changes which buttons are rendered (and thus toolbar width)
// but isn't itself a resize of the toolbar element.
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
}

.tb-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0;
  padding: 4px 6px;
  min-width: 28px;
  min-height: 28px;
  border: 1px solid transparent;
  border-radius: 4px;
  background: transparent;
  color: var(--fg);
  font-size: 12px;
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
  min-width: 180px;
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
  margin-top: 0;
}
.tb-overflow-panel .tb-sep {
  display: none;
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
  min-width: 28px;
  min-height: 28px;
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
