<template>
  <div class="se-overlay" ref="overlayEl" @click.self="handleClose">
    <div class="se-win" ref="winEl" tabindex="-1" :style="winStyle" @keydown.tab="trapFocus">
      <!-- ── Toolbar (history + zoom + shortcuts) ─────────────── -->
      <div class="se-toolbar" role="toolbar" aria-label="Editor options" @mousedown="onWinDragStart">

        <!-- Default style for the next shape (per-shape editing is in the inspector) -->
        <div class="se-style">
          <button
            class="se-style-swatch"
            :style="{ background: color }"
            :title="`Default colour — ${color}`"
            aria-label="Default colour"
            :aria-expanded="colorPanelOpen"
            @click.stop="colorPanelOpen = !colorPanelOpen"
          />
          <div v-if="colorPanelOpen" class="se-color-panel" @click.stop>
            <div
              v-for="c in PRESET_COLORS" :key="c"
              class="se-color-dot"
              :class="{ active: color === c }"
              :style="{ background: c }"
              :title="c"
              @click="pickColor(c)"
            />
            <label class="se-color-custom" title="Custom colour">
              <span v-html="ICON_PALETTE" />
              <input type="color" :value="color" class="se-color-custom-input"
                     @input="e => pickColor(e.target.value)" />
            </label>
            <button
              v-if="hasEyeDropper"
              class="se-color-eyedrop"
              title="Pick a colour from the image"
              aria-label="Pick a colour from the image"
              @click="eyeDrop(pickColor)"
            >
              <svg viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor"
                   stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
                <path d="M10.5 2.5a2 2 0 0 1 3 3L7 12l-3 1 1-3z" />
              </svg>
            </button>
            <div v-if="recentColors.length" class="se-color-recent">
              <div
                v-for="c in recentColors" :key="'tr' + c"
                class="se-color-dot"
                :class="{ active: color === c }"
                :style="{ background: c }"
                :title="c"
                @click="pickColor(c)"
              />
            </div>
          </div>

          <span class="se-style-div" />
          <button class="se-tbtn se-zoom-btn" aria-label="Thinner stroke"
                  :disabled="lineWidth <= 1" @click="lineWidth = Math.max(1, lineWidth - 1)">&minus;</button>
          <span class="se-style-val" title="Default stroke width">{{ lineWidth }}</span>
          <button class="se-tbtn se-zoom-btn" aria-label="Thicker stroke"
                  :disabled="lineWidth >= 20" @click="lineWidth = Math.min(20, lineWidth + 1)">+</button>
          <span class="se-style-div" />
          <button class="se-tbtn se-style-dash" :class="{ on: dashChecked }"
                  :aria-pressed="dashChecked" title="Dashed by default"
                  @click="dashChecked = !dashChecked">Dash</button>
        </div>

        <!-- Undo / redo -->
        <div class="se-zoom">
          <button
            class="se-tbtn icon-btn"
            :disabled="!canUndo && !textEdit.active"
            title="Undo (Ctrl+Z)"
            aria-label="Undo"
            @click="undo"
            v-html="ICON_UNDO"
          />
          <button
            class="se-tbtn icon-btn"
            :disabled="!canRedo"
            title="Redo (Ctrl+Shift+Z)"
            aria-label="Redo"
            @click="redo"
            v-html="ICON_REDO"
          />
        </div>

        <!-- Zoom / pan -->
        <div class="se-zoom" title="Zoom — Ctrl+scroll to zoom, Space-drag to pan">
          <button class="se-tbtn icon-btn" :disabled="isFit"
                  @click="zoomBy(1 / 1.25)" title="Zoom out" aria-label="Zoom out">
            <svg viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor"
                 stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <circle cx="7" cy="7" r="4.3" /><path d="M10.2 10.2 14 14M5 7h4" />
            </svg>
          </button>
          <button class="se-tbtn se-zoom-val" title="Reset to 100%"
                  @click="zoomActual">{{ zoomPct }}%</button>
          <button class="se-tbtn icon-btn" :disabled="zoom >= maxZoom - 1e-4"
                  @click="zoomBy(1.25)" title="Zoom in" aria-label="Zoom in">
            <svg viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor"
                 stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <circle cx="7" cy="7" r="4.3" /><path d="M10.2 10.2 14 14M5 7h4M7 5v4" />
            </svg>
          </button>
          <button class="se-tbtn" :disabled="isFit" @click="zoomFit">Fit</button>
        </div>

        <div class="se-spacer" />

        <!-- Shortcuts hint -->
        <button class="se-hint" title="Keyboard shortcuts" @click="shortcutsOpen = true">
          <svg viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor"
               stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <rect x="1.5" y="4" width="13" height="8" rx="1.5" />
            <path d="M4 7h.01M6.5 7h.01M9 7h.01M11.5 7h.01M4.5 9.5h7" />
          </svg>
          Press <kbd>?</kbd> for shortcuts
        </button>
      </div>

      <!-- ── Status toast ────────────────────────────────────────────── -->
      <Transition name="se-toast">
        <div v-if="statusVisible" class="se-status" :class="statusType">{{ statusMsg }}</div>
      </Transition>

      <!-- ── Tool rail ─────────────────────────────────────────────────── -->
      <div class="se-rail" role="toolbar" aria-label="Annotation tools" aria-orientation="vertical">
        <template v-for="(t, i) in TOOLS" :key="t.id">
          <div v-if="RAIL_SEPS.includes(i)" class="se-rail-sep" />
          <button
            class="se-rail-btn"
            :class="{ active: tool === t.id }"
            :title="t.label"
            :aria-label="t.label"
            :aria-pressed="tool === t.id"
            @click="setTool(t.id)"
            v-html="t.icon"
          />
        </template>
      </div>

      <!-- ── Canvas ────────────────────────────────────────────────────── -->
      <div class="se-body" ref="bodyEl" :class="{ 'se-panning': spaceDown }" @wheel="onWheel">

        <!-- Applied-crop chip -->
        <div v-if="crop" class="se-crop-chip">
          <svg viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor"
               stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M4.5 1.5v9.6a.9.9 0 0 0 .9.9H15M1 4.5h9.6a.9.9 0 0 1 .9.9V15" />
          </svg>
          <span>Cropped {{ Math.round(crop.w) }} &times; {{ Math.round(crop.h) }}</span>
          <button title="Remove crop (restore full image)" aria-label="Remove crop"
                  @click="clearCrop">&times;</button>
        </div>

        <div class="se-canvas-wrap" :style="wrapStyle">
          <canvas
            ref="canvasEl"
            :width="imgNW"
            :height="imgNH"
            :style="canvasStyle"
            @mousedown.prevent="onMouseDown"
            @mousemove="onMouseMove"
            @mouseup="onMouseUp"
            @mouseleave="onMouseLeave"
            @dblclick.prevent="onDoubleClick"
            @contextmenu.prevent="onContextMenu"
          />

          <!-- Floating text editor overlay -->
          <textarea
            v-if="textEdit.active"
            ref="textareaEl"
            class="se-text-input"
            :style="textInputStyle"
            v-model="textEdit.value"
            rows="1"
            @keydown.enter.exact.prevent="commitText"
            @keydown.esc.stop.prevent="cancelText"
            @blur="commitText"
          />

          <!-- Floating selection inspector -->
          <div
            v-if="inspectorVisible"
            class="se-inspector"
            :class="{ below: !inspectorAbove }"
            :style="inspectorStyle"
            @mousedown.stop
            @dblclick.stop
            @contextmenu.stop.prevent
          >
            <div class="se-insp-head">
              <span class="se-insp-title">{{ inspectorTitle }}</span>
              <span class="se-insp-dims">{{ inspectorDims }}</span>
              <button class="se-insp-x se-insp-trash" title="Delete shape (Del)"
                      aria-label="Delete shape" @click="deleteSelected" v-html="ICON_TRASH" />
            </div>

            <div v-if="selectedShape.type !== 'blur'" class="se-insp-row">
              <span class="se-insp-lbl">Color</span>
              <div class="se-insp-colors">
                <button
                  v-for="c in INSPECTOR_COLORS" :key="c"
                  class="se-insp-dot"
                  :class="{ active: selectedShape.color === c }"
                  :style="{ background: c }"
                  :title="c"
                  :aria-label="`Colour ${c}`"
                  @click="setShapeProp('color', c)"
                />
                <label class="se-insp-custom" title="Custom colour…">
                  <input type="color" :value="selectedShape.color"
                         @input="e => setShapeProp('color', e.target.value)" />
                </label>
                <button
                  v-if="hasEyeDropper"
                  class="se-insp-eyedrop"
                  title="Pick a colour from the image"
                  aria-label="Pick a colour from the image"
                  @click="eyeDrop(hex => setShapeProp('color', hex))"
                >
                  <svg viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor"
                       stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M10.5 2.5a2 2 0 0 1 3 3L7 12l-3 1 1-3z" />
                  </svg>
                </button>
                <input class="se-insp-hex" type="text" spellcheck="false"
                       :value="selectedShape.color" aria-label="Hex colour"
                       @change="e => applyHex(e.target.value)" />
              </div>
              <div v-if="recentColors.length" class="se-insp-recent">
                <button
                  v-for="c in recentColors" :key="'r' + c"
                  class="se-insp-dot"
                  :class="{ active: selectedShape.color === c }"
                  :style="{ background: c }"
                  :title="`Recent — ${c}`"
                  :aria-label="`Recent colour ${c}`"
                  @click="setShapeProp('color', c)"
                />
              </div>
            </div>

            <div v-if="STROKE_TYPES.has(selectedShape.type)" class="se-insp-row">
              <span class="se-insp-lbl">Stroke</span>
              <input class="se-range" type="range" min="1" max="20" step="1"
                     :value="selectedShape.width"
                     @input="e => setShapeProp('width', +e.target.value)" />
              <span class="se-insp-val">{{ selectedShape.width }}</span>
            </div>

            <div v-if="DASHABLE.has(selectedShape.type)" class="se-insp-row">
              <span class="se-insp-lbl">Dash</span>
              <div class="se-insp-seg">
                <button :class="{ on: !selectedShape.dashed }" @click="setShapeProp('dashed', false)">Solid</button>
                <button :class="{ on: !!selectedShape.dashed }" @click="setShapeProp('dashed', true)">Dashed</button>
              </div>
            </div>

            <div v-if="selectedShape.type === 'blur'" class="se-insp-row">
              <span class="se-insp-lbl">Strength</span>
              <input class="se-range" type="range" min="1" max="10" step="1"
                     :value="selectedShape.strength || 4"
                     @input="e => setShapeProp('strength', +e.target.value)" />
              <span class="se-insp-val">{{ selectedShape.strength || 4 }}</span>
            </div>

            <div v-if="selectedShape.type !== 'blur'" class="se-insp-row">
              <span class="se-insp-lbl">Opacity</span>
              <input class="se-range" type="range" min="10" max="100" step="5"
                     :value="Math.round((selectedShape.opacity ?? 1) * 100)"
                     @input="e => setShapeProp('opacity', +e.target.value / 100)" />
              <span class="se-insp-val">{{ Math.round((selectedShape.opacity ?? 1) * 100) }}%</span>
            </div>

            <template v-if="DASHABLE.has(selectedShape.type)">
              <div class="se-insp-row">
                <span class="se-insp-lbl">Label</span>
                <input class="se-insp-text" type="text" :value="selectedShape.label || ''"
                       placeholder="—"
                       @input="e => setShapeProp('label', e.target.value)" />
              </div>
              <div v-if="selectedShape.label" class="se-insp-row">
                <span class="se-insp-lbl">Font</span>
                <input class="se-range" type="range" min="10" max="72" step="2"
                       :value="selectedShape.labelFontSize || fontSize"
                       @input="e => setLabelFont(+e.target.value)" />
                <span class="se-insp-val">{{ selectedShape.labelFontSize || fontSize }}</span>
              </div>
            </template>

            <template v-if="selectedShape.type === 'text'">
              <div class="se-insp-row">
                <span class="se-insp-lbl">Text</span>
                <input class="se-insp-text" type="text" :value="selectedShape.text"
                       @input="e => setShapeProp('text', e.target.value)" />
              </div>
              <div class="se-insp-row">
                <span class="se-insp-lbl">Font</span>
                <input class="se-range" type="range" min="10" max="72" step="2"
                       :value="selectedShape.fontSize"
                       @input="e => setLabelFont(+e.target.value)" />
                <span class="se-insp-val">{{ selectedShape.fontSize }}</span>
              </div>
            </template>

            <div class="se-insp-row">
              <span class="se-insp-lbl">Arrange</span>
              <div class="se-insp-zrow">
                <button title="Send to back" @click="zSelected('back')">⤓</button>
                <button title="Send backward" @click="zSelected('backward')">‹</button>
                <button title="Bring forward" @click="zSelected('forward')">›</button>
                <button title="Bring to front" @click="zSelected('front')">⤒</button>
                <button title="Duplicate (Ctrl+D)" @click="duplicateSelected">Dup</button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- ── Footer actions ─────────────────────────────────────────────── -->
      <div class="se-footer">
        <button
          class="se-btn primary"
          title="Copy annotated image to clipboard"
          @click="copyToClipboard"
        >
          <span v-html="ICON_COPY" />
          Copy to Clipboard
        </button>
        <button
          class="se-btn secondary"
          title="Save annotated image as PNG"
          @click="saveAsPng"
        >
          <span v-html="ICON_SAVE" />
          Save PNG…
        </button>
        <div class="se-spacer" />
        <button class="se-btn secondary" title="Close editor" @click="handleClose">
          Close
        </button>
      </div>

      <!-- ── Keyboard shortcuts overlay ────────────────────────────────── -->
      <Transition name="se-toast">
        <div v-if="shortcutsOpen" class="se-sc-backdrop" @click.self="shortcutsOpen = false">
          <div class="se-sc-card" role="dialog" aria-label="Keyboard shortcuts">
            <div class="se-sc-head">
              <span>Keyboard shortcuts</span>
              <button class="se-insp-x" aria-label="Close" @click="shortcutsOpen = false" v-html="ICON_CLEAR" />
            </div>
            <div class="se-sc-grid">
              <div v-for="row in SHORTCUTS" :key="row[1]" class="se-sc-row">
                <kbd>{{ row[0] }}</kbd><span>{{ row[1] }}</span>
              </div>
            </div>
            <button class="se-sc-clear" :disabled="!shapes.length" @click="clearAll(); shortcutsOpen = false">
              Clear all annotations
            </button>
          </div>
        </div>
      </Transition>
    </div>

  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import {
  SNAP_TOOL_ICONS,
  ICON_UNDO,
  ICON_REDO,
  ICON_CLEAR,
  ICON_TRASH,
  ICON_COPY,
  ICON_SAVE,
  ICON_PALETTE,
} from '../utils/snapshotEditorIcons.js'

const props = defineProps({
  imageUrl: { type: String, required: true },
  downloadFilename: { type: String, default: 'annotated-snapshot.png' },
})

const emit = defineEmits(['close'])

// ── Tool definitions ──────────────────────────────────────────────────────────

const TOOLS = [
  { id: 'select', label: 'Select / move (V)', icon: SNAP_TOOL_ICONS.select },
  { id: 'arrow', label: 'Arrow (A)', icon: SNAP_TOOL_ICONS.arrow },
  { id: 'dblarrow', label: 'Double Arrow (D)', icon: SNAP_TOOL_ICONS.dblarrow },
  { id: 'line', label: 'Line (L)', icon: SNAP_TOOL_ICONS.line },
  { id: 'rect', label: 'Rectangle — Shift: square (R)', icon: SNAP_TOOL_ICONS.rect },
  { id: 'circle', label: 'Circle / Ellipse — Shift: circle (O)', icon: SNAP_TOOL_ICONS.circle },
  { id: 'text', label: 'Add Text — click to place (T)', icon: SNAP_TOOL_ICONS.text },
  { id: 'highlight', label: 'Highlighter (H)', icon: SNAP_TOOL_ICONS.highlight },
  { id: 'badge', label: 'Numbered step badge — click to place (S)', icon: SNAP_TOOL_ICONS.badge },
  { id: 'blur', label: 'Blur / redact — drag a region (B)', icon: SNAP_TOOL_ICONS.blur },
  { id: 'crop', label: 'Crop — drag to trim the export (C)', icon: SNAP_TOOL_ICONS.crop },
]
// One separator after Select; the drawing tools form a single group.
const RAIL_SEPS = [1]

const TOOL_CURSORS = {
  select: 'default',
  arrow: 'crosshair',
  dblarrow: 'crosshair',
  line:  'crosshair',
  rect:  'crosshair',
  circle:'crosshair',
  text:  'text',
  highlight: 'crosshair',
  badge: 'copy',
  blur:  'crosshair',
  crop:  'crosshair',
}

const LINE_TOOL_TYPES = new Set(['line', 'arrow', 'dblarrow', 'dash', 'highlight'])
// Types with box geometry (x, y, w, h) — resize handles, box hit-testing.
const BOX_TOOL_TYPES  = new Set(['rect', 'circle', 'blur'])
// Which inspector rows apply to which shape type.
const STROKE_TYPES = new Set(['rect', 'circle', 'line', 'arrow', 'dblarrow', 'dash', 'highlight'])
const DASHABLE     = new Set(['rect', 'circle', 'line', 'arrow', 'dblarrow', 'dash'])

// ── Reactive state ────────────────────────────────────────────────────────────

const tool      = ref('select')
const color     = ref('#ff4444')
const lineWidth = ref(3)
const fontSize  = ref(20)
const dashChecked = ref(false)

const colorPanelOpen = ref(false)
const shortcutsOpen  = ref(false)

const SHORTCUTS = [
  ['V', 'Select / move'],
  ['A / D', 'Arrow / double arrow'],
  ['L', 'Line'],
  ['R / O', 'Rectangle / ellipse'],
  ['T', 'Text'],
  ['H', 'Highlighter'],
  ['S', 'Numbered badge'],
  ['B', 'Blur / redact'],
  ['C', 'Crop'],
  ['1 – 9, 0', 'Set stroke width'],
  ['Ctrl+Z', 'Undo'],
  ['Ctrl+Shift+Z', 'Redo'],
  ['Ctrl+D', 'Duplicate selection'],
  ['Delete', 'Delete selection'],
  ['Arrows', 'Nudge selection (Shift = ×10)'],
  ['[ / ]', 'Send back / bring forward'],
  ['Ctrl+scroll', 'Zoom to cursor'],
  ['Space + drag', 'Pan'],
  ['Esc', 'Deselect, back to Select'],
  ['?', 'This panel'],
]
const PRESET_COLORS = [
  '#ff4444', '#ff8800', '#ffdd00', '#44cc44', '#00bbff', '#4466ff', '#9944ff', '#ff44aa',
  '#ffffff', '#cccccc', '#888888', '#444444', '#000000',
  '#cc0000', '#cc5500', '#aa9900', '#007700', '#005588', '#002299', '#550099',
]
function pickColor(hex) {
  color.value = hex
  pushRecentColor(hex)
  colorPanelOpen.value = false
  scheduleRedraw()
}
function closeColorPanel() {
  colorPanelOpen.value = false
}

// ── Colour system (Phase 5): recent colours + eyedropper ─────────────────────
const recentColors = ref([])
function pushRecentColor(hex) {
  if (!hex) return
  const h = String(hex).toLowerCase()
  const next = [h, ...recentColors.value.filter(c => c !== h)]
  recentColors.value = next.slice(0, 6)
}

const hasEyeDropper = typeof window !== 'undefined' && typeof window.EyeDropper === 'function'
async function eyeDrop(apply) {
  if (!hasEyeDropper) return
  try {
    const { sRGBHex } = await new window.EyeDropper().open()
    apply(sRGBHex)
    pushRecentColor(sRGBHex)
  } catch { /* user pressed Esc */ }
}
const shapes    = ref([])
const drawing   = ref(null)
const selectedIdx = ref(-1)

// ── Undo / redo history ───────────────────────────────────────────────────────
// Snapshot-based: each entry is a deep-cloned copy of the shapes array. Simple
// and robust for this plain-object model; moves, resizes and property edits are
// all undoable steps.
const HISTORY_LIMIT = 100
const history   = ref([])
const histIndex = ref(-1)
let _histTimer  = null
let _gestureDirty = false   // a drag/resize mutated a shape this gesture

const canUndo = computed(() => histIndex.value > 0)
const canRedo = computed(() => histIndex.value < history.value.length - 1)

// A history entry is a full snapshot: the shapes plus the applied crop, so
// undo/redo covers crop changes too.
function snapshotState() {
  return {
    shapes: shapes.value.map(cloneShape),
    crop: crop.value ? { ...crop.value } : null,
  }
}

function pushHistory() {
  if (histIndex.value < history.value.length - 1) {
    history.value.splice(histIndex.value + 1)
  }
  history.value.push(snapshotState())
  if (history.value.length > HISTORY_LIMIT) history.value.shift()
  histIndex.value = history.value.length - 1
}

// Coalesce rapid mutations (arrow-key nudges, colour-picker drags) into one entry.
function scheduleHistory(delay = 350) {
  clearTimeout(_histTimer)
  _histTimer = setTimeout(() => { _histTimer = null; pushHistory() }, delay)
}

function flushHistory() {
  if (_histTimer) { clearTimeout(_histTimer); _histTimer = null; pushHistory() }
}

function restoreHistory(idx) {
  if (idx < 0 || idx >= history.value.length) return
  histIndex.value = idx
  const snap = history.value[idx]
  shapes.value = snap.shapes.map(cloneShape)
  crop.value = snap.crop ? { ...snap.crop } : null
  if (selectedIdx.value >= shapes.value.length) selectedIdx.value = -1
  scheduleRedraw()
}

// ── Selection inspector (Phase 2) ────────────────────────────────────────────
// A floating properties panel that tracks the selection — replaces the old
// right-click context menu. The top toolbar now only sets next-shape defaults.
const INSPECTOR_COLORS = PRESET_COLORS.slice(0, 10)
const SHAPE_LABELS = {
  arrow: 'Arrow', dblarrow: 'Double arrow', line: 'Line', dash: 'Line',
  rect: 'Rectangle', circle: 'Ellipse', text: 'Text',
  highlight: 'Highlighter', badge: 'Number', blur: 'Blur',
}

const selectedShape = computed(() =>
  selectedIdx.value >= 0 && selectedIdx.value < shapes.value.length
    ? shapes.value[selectedIdx.value]
    : null
)

const inspectorVisible = computed(() =>
  !!selectedShape.value &&
  !drawing.value &&
  dragMode.value === 'none' &&
  !(textEdit.active && textEdit.shapeIdx === selectedIdx.value)
)

const inspectorTitle = computed(() =>
  selectedShape.value ? (SHAPE_LABELS[selectedShape.value.type] || 'Shape') : ''
)

const inspectorDims = computed(() => {
  const s = selectedShape.value
  if (!s) return ''
  if (s.type === 'text') return `${s.fontSize} pt`
  if (s.type === 'badge') return `#${s.n}`
  const b = shapeBounds(s)
  if (LINE_TOOL_TYPES.has(s.type)) return `${Math.round(Math.hypot(b.w, b.h))} px`
  return `${Math.round(b.w)} × ${Math.round(b.h)}`
})

const inspectorAbove = computed(() => {
  const s = selectedShape.value
  return s ? (shapeBounds(s).y * dScale.value) > 168 : true
})

const inspectorStyle = computed(() => {
  const s = selectedShape.value
  if (!s) return { display: 'none' }
  const k     = dScale.value
  const b     = shapeBounds(s)
  const wrapW = imgNW.value * k
  const wrapH = imgNH.value * k
  const left  = b.x * k
  const top   = b.y * k
  const w     = b.w * k
  const h     = b.h * k
  const INSP_W = 250
  let px = left + w / 2 - INSP_W / 2
  px = Math.max(4, Math.min(px, Math.max(4, wrapW - INSP_W - 4)))
  const style = { left: `${Math.round(px)}px`, width: `${INSP_W}px` }
  if (inspectorAbove.value) style.bottom = `${Math.round(wrapH - top + 12)}px`
  else                      style.top    = `${Math.round(top + h + 12)}px`
  return style
})

function setShapeProp(key, val) {
  const s = selectedShape.value
  if (!s) return
  if (key === 'label' && !val) {
    delete s.label
    delete s.labelFontSize
  } else {
    s[key] = val
    if (key === 'label' && val && !s.labelFontSize) s.labelFontSize = fontSize.value
  }
  if (key === 'color') pushRecentColor(val)
  scheduleHistory()
  scheduleRedraw()
}

// Accept "#rrggbb", "rrggbb", "#rgb" — normalise and apply to the selection.
function applyHex(raw) {
  let h = String(raw).trim().replace(/^#/, '').toLowerCase()
  if (/^[0-9a-f]{3}$/.test(h)) h = h.split('').map(c => c + c).join('')
  if (!/^[0-9a-f]{6}$/.test(h)) return
  setShapeProp('color', '#' + h)
}

// Focus trap — keep Tab within the editor window while it is open.
function trapFocus(e) {
  const root = winEl.value
  if (!root) return
  const f = [...root.querySelectorAll(
    'button:not([disabled]), input:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
  )].filter(el => el.offsetParent !== null)
  if (!f.length) return
  const first = f[0]
  const last  = f[f.length - 1]
  if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus() }
  else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() }
}

function setLabelFont(val) {
  const s = selectedShape.value
  if (!s) return
  if (s.type === 'text') s.fontSize = val
  else s.labelFontSize = val
  scheduleHistory()
  scheduleRedraw()
}

function duplicateSelected() {
  if (selectedIdx.value < 0) return
  const ni = duplicateShape(selectedIdx.value)
  moveShape(ni, 12, 12)
  selectedIdx.value = ni
  syncDashFromShape(ni)
  pushHistory()
  scheduleRedraw()
}

// dir: 'back' | 'backward' | 'forward' | 'front' — array order is z-order
function zSelected(dir) {
  const i = selectedIdx.value
  const n = shapes.value.length
  if (i < 0 || n < 2) return
  const arr = shapes.value
  const [sh] = arr.splice(i, 1)
  const ni = dir === 'back'     ? 0
           : dir === 'front'    ? n - 1
           : dir === 'backward' ? Math.max(0, i - 1)
           :                      Math.min(n - 1, i + 1)
  arr.splice(ni, 0, sh)
  selectedIdx.value = ni
  pushHistory()
  scheduleRedraw()
}

const imgNW  = ref(1)
const imgNH  = ref(1)
const imgEl  = ref(null)

// ── Zoom & pan (Phase 3) ─────────────────────────────────────────────────────
// dScale = fitScale (fit-to-window, ≤ 1) × zoom (user multiplier, 1 = fit).
// Pan is plain scrollLeft/scrollTop on the .se-body scroll container.
const DSCALE_MAX = 8
const fitScale = ref(1)
const zoom     = ref(1)
const dScale   = computed(() =>
  Math.min(DSCALE_MAX, Math.max(0.02, fitScale.value * zoom.value))
)
const zoomPct  = computed(() => Math.round(dScale.value * 100))
const maxZoom  = computed(() => Math.max(1, DSCALE_MAX / fitScale.value))
const isFit    = computed(() => Math.abs(zoom.value - 1) < 1e-4)
const spaceDown = ref(false)

let _panning  = false
let _panStart = null

function setZoom(z) {
  zoom.value = Math.min(maxZoom.value, Math.max(1, z))
}
function zoomBy(f) { setZoom(zoom.value * f) }
function zoomFit() { setZoom(1); resetPan() }
function zoomActual() { setZoom(1 / fitScale.value) }

function resetPan() {
  if (bodyEl.value) { bodyEl.value.scrollLeft = 0; bodyEl.value.scrollTop = 0 }
}

// Ctrl/Cmd + wheel — zoom toward the cursor, keeping that point anchored.
function onWheel(e) {
  if (!(e.ctrlKey || e.metaKey)) return
  e.preventDefault()
  const body = bodyEl.value
  if (!body) return
  const r  = body.getBoundingClientRect()
  const cx = e.clientX - r.left
  const cy = e.clientY - r.top
  const px = body.scrollLeft + cx
  const py = body.scrollTop  + cy
  const before = dScale.value
  zoomBy(e.deltaY < 0 ? 1.15 : 1 / 1.15)
  nextTick(() => {
    const ratio = dScale.value / before
    body.scrollLeft = px * ratio - cx
    body.scrollTop  = py * ratio - cy
  })
}

function startPan(e) {
  _panning = true
  _panStart = {
    x: e.clientX, y: e.clientY,
    sl: bodyEl.value?.scrollLeft || 0,
    st: bodyEl.value?.scrollTop  || 0,
  }
  window.addEventListener('mousemove', onPanMove)
  window.addEventListener('mouseup', endPan)
}
function onPanMove(e) {
  if (!_panning || !bodyEl.value) return
  bodyEl.value.scrollLeft = _panStart.sl - (e.clientX - _panStart.x)
  bodyEl.value.scrollTop  = _panStart.st - (e.clientY - _panStart.y)
}
function endPan() {
  _panning = false
  window.removeEventListener('mousemove', onPanMove)
  window.removeEventListener('mouseup', endPan)
}

// ── Movable editor window — drag by the toolbar background ────────────────────
const winOffset = reactive({ x: 0, y: 0 })
let _winDrag = null

const winStyle = computed(() => ({
  transform: `translate(${Math.round(winOffset.x)}px, ${Math.round(winOffset.y)}px)`,
}))

function onWinDragStart(e) {
  if (e.button !== 0) return
  // Only the bare toolbar is a drag handle — not its buttons / groups.
  if (e.target.closest('button, input, label, .se-zoom, .se-hint, .se-style')) return
  _winDrag = { mx: e.clientX, my: e.clientY, x: winOffset.x, y: winOffset.y }
  window.addEventListener('mousemove', onWinDragMove)
  window.addEventListener('mouseup', onWinDragEnd)
  e.preventDefault()
}
function onWinDragMove(e) {
  if (!_winDrag) return
  const maxX = Math.max(0, window.innerWidth  / 2 - 80)
  const maxY = Math.max(0, window.innerHeight / 2 - 60)
  winOffset.x = Math.max(-maxX, Math.min(maxX, _winDrag.x + (e.clientX - _winDrag.mx)))
  winOffset.y = Math.max(-maxY, Math.min(maxY, _winDrag.y + (e.clientY - _winDrag.my)))
}
function onWinDragEnd() {
  _winDrag = null
  window.removeEventListener('mousemove', onWinDragMove)
  window.removeEventListener('mouseup', onWinDragEnd)
}

// ── Phase 4 tools: badge / blur / crop ───────────────────────────────────────
const crop = ref(null)          // { x, y, w, h } in image px, or null
let _exporting = false          // suppress overlay + selection during export
const _blurCanvas = document.createElement('canvas')

function nextBadgeNumber() {
  return 1 + shapes.value.reduce((m, s) => s.type === 'badge' ? Math.max(m, s.n) : m, 0)
}

function setCrop(box) {
  const x = Math.max(0, Math.min(box.x, imgNW.value))
  const y = Math.max(0, Math.min(box.y, imgNH.value))
  crop.value = {
    x, y,
    w: Math.min(imgNW.value - x, box.w),
    h: Math.min(imgNH.value - y, box.h),
  }
  pushHistory()
  scheduleRedraw()
}

function clearCrop() {
  if (!crop.value) return
  crop.value = null
  pushHistory()
  scheduleRedraw()
}

const overlayEl  = ref(null)
const winEl      = ref(null)
const bodyEl     = ref(null)
const canvasEl   = ref(null)
const textareaEl = ref(null)

const textEdit = reactive({
  active:   false,
  canvasX:  0,
  canvasY:  0,
  value:    '',
  shapeIdx: -1,
  angle:    0,
})

const DRAG_THRESHOLD = 4

let _mouseDown   = false
let _startPos    = null
let _pendingDrag = null // { idx, startX, startY, startPos }
let _dragIdx     = -1
let _dragPrev    = null
let _dragHandle  = null
let _dragAnchor  = null
let _rafId       = null
let _statusTimer = null

const hoverIdx = ref(-1)
const hoverHandleId = ref('')
const dragMode = ref('none') // none | move | handle

const statusMsg     = ref('')
const statusType    = ref('info')
const statusVisible = ref(false)

function showStatus(msg, type = 'info') {
  statusMsg.value     = msg
  statusType.value    = type
  statusVisible.value = true
  clearTimeout(_statusTimer)
  _statusTimer = setTimeout(() => { statusVisible.value = false }, type === 'error' ? 4000 : 2500)
}

// ── Computed styles ───────────────────────────────────────────────────────────

const canvasStyle = computed(() => ({
  display: 'block',
  width:   `${Math.round(imgNW.value * dScale.value)}px`,
  height:  `${Math.round(imgNH.value * dScale.value)}px`,
  cursor:  spaceDown.value
             ? 'grab'
             : tool.value === 'text'
             ? 'text'
             : dragMode.value === 'handle'
               ? cursorForHandle(hoverHandleId.value || _dragHandle)
               : hoverHandleId.value
                 ? cursorForHandle(hoverHandleId.value)
                 : (_dragIdx >= 0 || hoverIdx.value >= 0)
                   ? 'move'
             : (TOOL_CURSORS[tool.value] || 'crosshair'),
}))

const wrapStyle = computed(() => ({
  position: 'relative',
  flexShrink: '0',
  width:  `${Math.round(imgNW.value * dScale.value)}px`,
  height: `${Math.round(imgNH.value * dScale.value)}px`,
}))

const textInputStyle = computed(() => {
  const s  = dScale.value
  const editingShape = textEdit.shapeIdx >= 0 ? shapes.value[textEdit.shapeIdx] : null
  const isShapeLabel = editingShape && editingShape.type !== 'text'
  let fs = fontSize.value
  let col = color.value
  if (editingShape) {
    if (editingShape.type === 'text') {
      fs = editingShape.fontSize
      col = editingShape.color
    } else {
      const anchor = shapeLabelAnchor(editingShape)
      fs = anchor.fontSize
      col = anchor.color
    }
  }
  const style = {
    position:    'absolute',
    left:        `${Math.round(textEdit.canvasX * s)}px`,
    top:         `${Math.round(textEdit.canvasY * s)}px`,
    fontSize:    `${fs * s}px`,
    lineHeight:  '1.2',
    color:       col,
    fontFamily:  'sans-serif',
    fontWeight:  'bold',
    background:  'transparent',
    border:      '1px dashed rgba(255,255,255,0.55)',
    outline:     'none',
    resize:      'none',
    padding:     '0 2px',
    margin:      '0',
    minWidth:    '60px',
    maxWidth:    isShapeLabel ? 'none' : `${Math.max(60, (imgNW.value - textEdit.canvasX) * s)}px`,
    overflow:    'hidden',
    whiteSpace:  'nowrap',
    boxSizing:   'border-box',
    zIndex:      '1',
    textAlign:   isShapeLabel ? 'center' : 'left',
  }
  if (isShapeLabel) {
    style.transform = `translate(-50%, -50%) rotate(${textEdit.angle}rad)`
    style.transformOrigin = 'center center'
  }
  return style
})

// ── Lifecycle ─────────────────────────────────────────────────────────────────

onMounted(() => {
  const image  = new Image()
  image.onload = () => {
    imgEl.value  = image
    imgNW.value  = image.naturalWidth
    imgNH.value  = image.naturalHeight
    nextTick(() => {
      computeScale()
      nextTick(() => redraw())
    })
  }
  image.onerror = () => console.error('[SnapshotEditor] failed to load image')
  image.src = props.imageUrl

  document.addEventListener('keydown', onDocKeyDown, true)
  document.addEventListener('keyup', onDocKeyUp, true)
  document.addEventListener('keypress', onDocKeyPress, true)
  document.addEventListener('click', closeColorPanel)
  window.addEventListener('resize', computeScale)

  pushHistory()   // empty baseline so the first edit is undoable
  nextTick(() => winEl.value?.focus())   // a11y: move focus into the modal
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', onDocKeyDown, true)
  document.removeEventListener('keyup', onDocKeyUp, true)
  document.removeEventListener('keypress', onDocKeyPress, true)
  document.removeEventListener('click', closeColorPanel)
  window.removeEventListener('resize', computeScale)
  if (_rafId) cancelAnimationFrame(_rafId)
  clearTimeout(_histTimer)
  endPan()
  onWinDragEnd()
})

function isTypingTarget() {
  const ae = document.activeElement
  return textEdit.active ||
    !!(ae && (ae.tagName === 'INPUT' || ae.tagName === 'TEXTAREA' || ae.isContentEditable))
}

function onDocKeyUp(e) {
  if (e.key === ' ') { spaceDown.value = false; endPan() }
  // Don't let a "?" release reach a main-window help handler either.
  if (e.key === '?' && !isTypingTarget()) e.stopImmediatePropagation()
}

// Some apps trigger help on the "?" character (keypress) rather than keydown.
function onDocKeyPress(e) {
  if (e.key === '?' && !isTypingTarget()) {
    e.preventDefault()
    e.stopImmediatePropagation()
  }
}

function computeScale() {
  if (!bodyEl.value || !imgNW.value || !imgNH.value) return
  const r     = bodyEl.value.getBoundingClientRect()
  const availW = Math.max(1, r.width  - 48)
  const availH = Math.max(1, r.height - 48)
  fitScale.value = Math.min(1, availW / imgNW.value, availH / imgNH.value)
  if (zoom.value > maxZoom.value) zoom.value = maxZoom.value
}

// Single-key tool shortcuts (shown in each button's tooltip).
const TOOL_KEYS = {
  v: 'select',
  a: 'arrow', d: 'dblarrow', l: 'line', r: 'rect', o: 'circle', t: 'text',
  h: 'highlight', s: 'badge', b: 'blur', c: 'crop',
}

function onDocKeyDown(e) {
  // Esc — peel back one layer at a time; never closes the editor itself.
  if (e.key === 'Escape') {
    e.preventDefault()
    e.stopPropagation()
    if (shortcutsOpen.value) { shortcutsOpen.value = false; return }
    if (colorPanelOpen.value) { colorPanelOpen.value = false; return }
    if (textEdit.active) { cancelText(); return }
    if (selectedIdx.value >= 0) { selectedIdx.value = -1; scheduleRedraw(); return }
    if (crop.value) { clearCrop(); return }
    if (tool.value !== 'select') { setTool('select'); return }
    return
  }

  // Never steal keys while the user is typing in the text editor or a menu field.
  const ae = document.activeElement
  if (ae && (ae.tagName === 'INPUT' || ae.tagName === 'TEXTAREA' || ae.isContentEditable)) return
  if (textEdit.active) return

  // The editor is a modal — no key below here should reach the window behind it
  // (otherwise e.g. "?" would also pop the main-window shortcuts help).
  e.stopPropagation()

  // ? — toggle the keyboard-shortcuts panel.
  if (e.key === '?') {
    e.preventDefault()
    e.stopImmediatePropagation()
    shortcutsOpen.value = !shortcutsOpen.value
    return
  }
  if (shortcutsOpen.value) return

  // Space — hold to pan. Skip when a button is focused (space would click it).
  if (e.key === ' ' && !e.repeat) {
    if (ae && ae.tagName === 'BUTTON') return
    e.preventDefault()
    spaceDown.value = true
    return
  }

  const mod = e.ctrlKey || e.metaKey

  // Undo / redo — Ctrl/Cmd+Z, Ctrl/Cmd+Shift+Z, Ctrl+Y
  if (mod && (e.key === 'z' || e.key === 'Z')) {
    e.preventDefault(); e.stopPropagation()
    e.shiftKey ? redo() : undo()
    return
  }
  if (mod && (e.key === 'y' || e.key === 'Y')) {
    e.preventDefault(); e.stopPropagation()
    redo()
    return
  }

  // Ctrl/Cmd+D — duplicate the selection, offset slightly
  if (mod && (e.key === 'd' || e.key === 'D')) {
    e.preventDefault(); e.stopPropagation()
    duplicateSelected()
    return
  }

  if (mod) return   // leave every other Ctrl/Cmd combo to the browser / app

  // Delete / Backspace — remove the selection, or the crop when nothing is selected
  if (e.key === 'Delete' || e.key === 'Backspace') {
    if (selectedIdx.value >= 0) {
      e.preventDefault(); e.stopPropagation()
      deleteSelected()
      return
    }
    if (crop.value) {
      e.preventDefault(); e.stopPropagation()
      clearCrop()
      return
    }
  }

  // Arrow keys — nudge the selection (Shift = ×10)
  if (selectedIdx.value >= 0 && e.key.startsWith('Arrow')) {
    e.preventDefault(); e.stopPropagation()
    const step = e.shiftKey ? 10 : 1
    const dx = e.key === 'ArrowLeft' ? -step : e.key === 'ArrowRight' ? step : 0
    const dy = e.key === 'ArrowUp'   ? -step : e.key === 'ArrowDown'  ? step : 0
    if (dx || dy) { moveShape(selectedIdx.value, dx, dy); scheduleRedraw(); scheduleHistory() }
    return
  }

  // [ / ] — z-order of the selection
  if ((e.key === '[' || e.key === ']') && selectedIdx.value >= 0) {
    e.preventDefault(); e.stopPropagation()
    zSelected(e.key === '[' ? 'backward' : 'forward')
    return
  }

  // 1–9, 0 — set the default stroke width (0 = 10)
  if (/^[0-9]$/.test(e.key)) {
    e.stopPropagation()
    lineWidth.value = e.key === '0' ? 10 : Number(e.key)
    if (selectedIdx.value >= 0 && STROKE_TYPES.has(selectedShape.value?.type)) {
      setShapeProp('width', lineWidth.value)
    }
    return
  }

  // Single-key tool switch
  const t = TOOL_KEYS[e.key.toLowerCase()]
  if (t && !e.altKey && !e.shiftKey) {
    e.stopPropagation()
    setTool(t)
  }
}

function deleteSelected() {
  const i = selectedIdx.value
  if (i < 0 || i >= shapes.value.length) return
  shapes.value.splice(i, 1)
  selectedIdx.value = -1
  pushHistory()
  scheduleRedraw()
}

// ── Tool selection ────────────────────────────────────────────────────────────

function setTool(t) {
  cancelText()
  tool.value = t
}

// The toolbar "Dash" toggle is now a stable default — it no longer follows the
// selection (that would make the control jump around as you click shapes).
function syncDashFromShape(_idx) { /* intentionally a no-op */ }

function handleClose() {
  commitText()
  emit('close')
}

// ── Canvas coordinate conversion ──────────────────────────────────────────────

function getPos(e) {
  const rect = canvasEl.value.getBoundingClientRect()
  return {
    x: (e.clientX - rect.left) * (imgNW.value / rect.width),
    y: (e.clientY - rect.top)  * (imgNH.value / rect.height),
  }
}

// ── Mouse events ──────────────────────────────────────────────────────────────

function onMouseDown(e) {
  if (e.button !== 0) return
  if (spaceDown.value) { e.preventDefault(); startPan(e); return }
  const pos = getPos(e)

  if (tool.value === 'text') {
    commitText()
    const hit = hitTest(pos.x, pos.y)
    if (hit >= 0 && shapes.value[hit].type === 'text') {
      selectedIdx.value = hit
      scheduleRedraw()
      return
    }
    textEdit.shapeIdx = -1
    textEdit.canvasX = pos.x
    textEdit.canvasY = pos.y
    textEdit.value   = ''
    textEdit.active  = true
    nextTick(() => textareaEl.value?.focus())
    return
  }

  // Numbered step badge — click to drop the next number.
  if (tool.value === 'badge') {
    shapes.value.push({
      type: 'badge', color: color.value,
      x: pos.x, y: pos.y, n: nextBadgeNumber(), r: 15,
    })
    selectedIdx.value = shapes.value.length - 1
    pushHistory()
    scheduleRedraw()
    return
  }

  // Crop always drags a fresh frame — never grabs a shape underneath.
  if (tool.value === 'crop') {
    selectedIdx.value = -1
    _mouseDown = true
    _startPos  = pos
    drawing.value = buildShape('crop', pos, pos, e.shiftKey)
    return
  }

  const handleHit = hitControlPoint(pos.x, pos.y)
  if (handleHit && selectedIdx.value >= 0) {
    _dragIdx    = selectedIdx.value
    _dragHandle = handleHit
    _dragAnchor = getHandleAnchor(shapes.value[_dragIdx], handleHit)
    dragMode.value = 'handle'
    return
  }

  // Hit-test: select and drag an existing shape rather than drawing a new one
  const hit = hitTest(pos.x, pos.y)
  if (hit >= 0) {
    if (e.ctrlKey || e.metaKey) {
      const newIdx = duplicateShape(hit)
      selectedIdx.value = newIdx
      syncDashFromShape(newIdx)
      _dragIdx  = newIdx
      _dragPrev = pos
      _dragHandle = null
      _dragAnchor = null
      dragMode.value = 'move'
      _gestureDirty = true
      hoverHandleId.value = ''
      scheduleRedraw()
      return
    }
    selectedIdx.value = hit
    syncDashFromShape(hit)
    _pendingDrag = { idx: hit, startX: pos.x, startY: pos.y, startPos: pos }
    _dragHandle = null
    _dragAnchor = null
    hoverHandleId.value = ''
    scheduleRedraw()
    return
  }

  // Select tool never draws — an empty-space click just clears the selection.
  if (tool.value === 'select') {
    selectedIdx.value = -1
    hoverHandleId.value = ''
    scheduleRedraw()
    return
  }

  selectedIdx.value = -1
  hoverHandleId.value = ''
  _mouseDown = true
  _startPos  = pos
  drawing.value = buildShape(tool.value, pos, pos, e.shiftKey)
}

function onMouseMove(e) {
  const pos = getPos(e)

  if (_pendingDrag && dragMode.value === 'none') {
    const dx = pos.x - _pendingDrag.startX
    const dy = pos.y - _pendingDrag.startY
    if (Math.hypot(dx, dy) >= DRAG_THRESHOLD) {
      _dragIdx = _pendingDrag.idx
      _dragPrev = _pendingDrag.startPos
      dragMode.value = 'move'
      _pendingDrag = null
    }
  }

  if (dragMode.value === 'handle' && _dragIdx >= 0 && _dragHandle) {
    updateShapeByHandle(_dragIdx, _dragHandle, pos, e.shiftKey)
    _gestureDirty = true
    scheduleRedraw()
    return
  }

  if (dragMode.value === 'move' && _dragIdx >= 0 && _dragPrev) {
    moveShape(_dragIdx, pos.x - _dragPrev.x, pos.y - _dragPrev.y)
    _dragPrev = pos
    _gestureDirty = true
    scheduleRedraw()
    return
  }

  if (_mouseDown && _startPos) {
    drawing.value = buildShape(tool.value, _startPos, pos, e.shiftKey)
    scheduleRedraw()
    return
  }

  // Hover: update cursor hint for draggable shapes / control points
  if (tool.value !== 'text') {
    const handleHit = hitControlPoint(pos.x, pos.y)
    hoverHandleId.value = handleHit || ''
    hoverIdx.value = handleHit ? -1 : hitTest(pos.x, pos.y)
  }
}

function onMouseUp(e) {
  _pendingDrag = null
  if (dragMode.value !== 'none') {
    _dragIdx  = -1
    _dragPrev = null
    _dragHandle = null
    _dragAnchor = null
    dragMode.value = 'none'
    if (_gestureDirty) { _gestureDirty = false; pushHistory() }
    scheduleRedraw()
    return
  }
  if (!_mouseDown) return
  _mouseDown = false
  if (drawing.value && _startPos) {
    const pos   = getPos(e)
    const shape = buildShape(tool.value, _startPos, pos, e.shiftKey)
    if (tool.value === 'crop') {
      if (!isTrivial(shape)) setCrop(shape)
    } else if (!isTrivial(shape)) {
      shapes.value.push(shape)
      // Select the shape we just drew so it can be moved / restyled / deleted
      // straight away, without a separate click to find it again.
      selectedIdx.value = shapes.value.length - 1
      syncDashFromShape(selectedIdx.value)
      pushHistory()
    }
    drawing.value = null
  }
  _startPos = null
  scheduleRedraw()
}

function onMouseLeave() {
  hoverIdx.value = -1
  hoverHandleId.value = ''
  _pendingDrag = null
  if (dragMode.value !== 'none') {
    _dragIdx  = -1
    _dragPrev = null
    _dragHandle = null
    _dragAnchor = null
    dragMode.value = 'none'
    if (_gestureDirty) { _gestureDirty = false; pushHistory() }
    scheduleRedraw()
    return
  }
  if (_mouseDown) {
    _mouseDown    = false
    drawing.value = null
    _startPos     = null
    scheduleRedraw()
  }
}

function onDoubleClick(e) {
  _pendingDrag = null
  _mouseDown = false
  drawing.value = null
  _startPos = null
  if (dragMode.value !== 'none') {
    _dragIdx = -1
    _dragPrev = null
    _dragHandle = null
    _dragAnchor = null
    dragMode.value = 'none'
  }

  const pos = getPos(e)
  const hit = hitTest(pos.x, pos.y)
  if (hit < 0) return
  // Badge / blur / highlighter carry no editable text.
  if (['badge', 'blur', 'highlight'].includes(shapes.value[hit].type)) {
    selectedIdx.value = hit
    scheduleRedraw()
    return
  }
  beginEditShapeText(hit)
}

// ── Hit-testing & shape movement ─────────────────────────────────────────────

function ptToSegDist(px, py, x1, y1, x2, y2) {
  const dx = x2 - x1, dy = y2 - y1
  const lenSq = dx * dx + dy * dy
  if (lenSq < 1e-6) return Math.hypot(px - x1, py - y1)
  const t = Math.max(0, Math.min(1, ((px - x1) * dx + (py - y1) * dy) / lenSq))
  return Math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))
}

function hitTest(x, y) {
  const thr = 10
  for (let i = shapes.value.length - 1; i >= 0; i--) {
    const s = shapes.value[i]
    if (s.type === 'text') {
      const w = s.fontSize * 0.65 * s.text.length
      if (x >= s.x - thr && x <= s.x + w + thr &&
          y >= s.y - thr && y <= s.y + s.fontSize + thr) return i
    } else if (s.type === 'badge') {
      if (Math.hypot(x - s.x, y - s.y) <= (s.r || 15) + thr) return i
    } else if (BOX_TOOL_TYPES.has(s.type)) {
      if (x >= s.x - thr && x <= s.x + s.w + thr &&
          y >= s.y - thr && y <= s.y + s.h + thr) return i
    } else {
      // Match the *rendered* thickness — the highlighter draws far wider than
      // its stored width, so its hit zone has to follow.
      const w = Number(s.width) || 3
      const half = s.type === 'highlight' ? Math.max(w * 3, 10) / 2 : w
      if (ptToSegDist(x, y, s.x1, s.y1, s.x2, s.y2) < thr + half) return i
    }
  }
  return -1
}

function moveShape(idx, dx, dy) {
  const s = shapes.value[idx]
  if (s.type === 'text' || s.type === 'badge' || BOX_TOOL_TYPES.has(s.type)) {
    s.x += dx; s.y += dy
  } else {
    s.x1 += dx; s.y1 += dy
    s.x2 += dx; s.y2 += dy
  }
}

function cloneShape(shape) {
  const op = (shape.opacity != null && shape.opacity < 1) ? { opacity: shape.opacity } : {}
  if (shape.type === 'text') {
    return {
      type: shape.type,
      color: shape.color,
      fontSize: shape.fontSize,
      x: shape.x,
      y: shape.y,
      text: shape.text,
      ...op,
    }
  }
  if (shape.type === 'badge') {
    return {
      type: 'badge',
      color: shape.color,
      x: shape.x,
      y: shape.y,
      n: shape.n,
      r: shape.r,
      ...op,
    }
  }
  if (BOX_TOOL_TYPES.has(shape.type)) {
    return {
      type: shape.type,
      color: shape.color,
      width: shape.width,
      x: shape.x,
      y: shape.y,
      w: shape.w,
      h: shape.h,
      ...(shape.label ? { label: shape.label } : {}),
      ...(shape.labelFontSize ? { labelFontSize: shape.labelFontSize } : {}),
      ...(shape.dashed ? { dashed: true } : {}),
      ...(shape.strength ? { strength: shape.strength } : {}),
      ...op,
    }
  }
  return {
    type: shape.type,
    color: shape.color,
    width: shape.width,
    x1: shape.x1,
    y1: shape.y1,
    x2: shape.x2,
    y2: shape.y2,
    ...op,
    ...(shape.label ? { label: shape.label } : {}),
    ...(shape.labelFontSize ? { labelFontSize: shape.labelFontSize } : {}),
    ...(shape.dashed ? { dashed: true } : {}),
  }
}

function duplicateShape(idx) {
  shapes.value.push(cloneShape(shapes.value[idx]))
  return shapes.value.length - 1
}

function getControlPoints(shape) {
  if (!shape) return []
  if (LINE_TOOL_TYPES.has(shape.type)) {
    return [
      { id: 'start', x: shape.x1, y: shape.y1 },
      { id: 'end', x: shape.x2, y: shape.y2 },
    ]
  }
  if (BOX_TOOL_TYPES.has(shape.type)) {
    return [
      { id: 'nw', x: shape.x,           y: shape.y },
      { id: 'n',  x: shape.x + shape.w / 2, y: shape.y },
      { id: 'ne', x: shape.x + shape.w, y: shape.y },
      { id: 'e',  x: shape.x + shape.w, y: shape.y + shape.h / 2 },
      { id: 'se', x: shape.x + shape.w, y: shape.y + shape.h },
      { id: 's',  x: shape.x + shape.w / 2, y: shape.y + shape.h },
      { id: 'sw', x: shape.x,           y: shape.y + shape.h },
      { id: 'w',  x: shape.x,           y: shape.y + shape.h / 2 },
    ]
  }
  return []
}

function hitControlPoint(x, y) {
  if (selectedIdx.value < 0 || selectedIdx.value >= shapes.value.length) return null
  const points = getControlPoints(shapes.value[selectedIdx.value])
  if (!points.length) return null
  const thr = Math.max(8, 10 / dScale.value)
  for (const p of points) {
    if (Math.hypot(x - p.x, y - p.y) <= thr) return p.id
  }
  return null
}

function getHandleAnchor(shape, handleId) {
  if (!shape) return null
  if (BOX_TOOL_TYPES.has(shape.type)) {
    if (handleId === 'nw') return { x: shape.x + shape.w, y: shape.y + shape.h }
    if (handleId === 'n')  return { x: shape.x + shape.w / 2, y: shape.y + shape.h }
    if (handleId === 'ne') return { x: shape.x, y: shape.y + shape.h }
    if (handleId === 'e')  return { x: shape.x, y: shape.y + shape.h / 2 }
    if (handleId === 'se') return { x: shape.x, y: shape.y }
    if (handleId === 's')  return { x: shape.x + shape.w / 2, y: shape.y }
    if (handleId === 'sw') return { x: shape.x + shape.w, y: shape.y }
    if (handleId === 'w')  return { x: shape.x + shape.w, y: shape.y + shape.h / 2 }
  }
  return null
}

function updateShapeByHandle(idx, handleId, pos, forceSnap = false) {
  const s = shapes.value[idx]
  if (!s) return
  if (LINE_TOOL_TYPES.has(s.type)) {
    if (handleId === 'start') {
      const end = snapLineEnd(s.x2, s.y2, pos.x, pos.y, forceSnap)
      s.x1 = end.x
      s.y1 = end.y
    } else if (handleId === 'end') {
      const end = snapLineEnd(s.x1, s.y1, pos.x, pos.y, forceSnap)
      s.x2 = end.x
      s.y2 = end.y
    }
    return
  }

  if ((BOX_TOOL_TYPES.has(s.type)) && handleId === 'n') {
    const bottom = s.y + s.h
    const top = pos.y
    s.y = Math.min(top, bottom)
    s.h = Math.abs(bottom - top)
    return
  }

  if ((BOX_TOOL_TYPES.has(s.type)) && handleId === 's') {
    const top = s.y
    const bottom = pos.y
    s.y = Math.min(top, bottom)
    s.h = Math.abs(bottom - top)
    return
  }

  if ((BOX_TOOL_TYPES.has(s.type)) && handleId === 'w') {
    const right = s.x + s.w
    const left = pos.x
    s.x = Math.min(left, right)
    s.w = Math.abs(right - left)
    return
  }

  if ((BOX_TOOL_TYPES.has(s.type)) && handleId === 'e') {
    const left = s.x
    const right = pos.x
    s.x = Math.min(left, right)
    s.w = Math.abs(right - left)
    return
  }

  if ((BOX_TOOL_TYPES.has(s.type)) && _dragAnchor) {
    let x1 = pos.x
    let y1 = pos.y
    const x2 = _dragAnchor.x
    const y2 = _dragAnchor.y

    if (forceSnap) {
      const dx = x1 - x2
      const dy = y1 - y2
      const size = Math.min(Math.abs(dx), Math.abs(dy))
      x1 = x2 + (dx < 0 ? -size : size)
      y1 = y2 + (dy < 0 ? -size : size)
    }
    s.x = Math.min(x1, x2)
    s.y = Math.min(y1, y2)
    s.w = Math.abs(x1 - x2)
    s.h = Math.abs(y1 - y2)
  }
}

function cursorForHandle(handleId) {
  if (handleId === 'nw' || handleId === 'se') return 'nwse-resize'
  if (handleId === 'ne' || handleId === 'sw') return 'nesw-resize'
  if (handleId === 'n' || handleId === 's') return 'ns-resize'
  if (handleId === 'e' || handleId === 'w') return 'ew-resize'
  return 'crosshair'
}

// ── Right-click ───────────────────────────────────────────────────────────────
// Selects the shape under the cursor; the floating inspector then does the rest.
function onContextMenu(e) {
  const pos = getPos(e)
  const hit = hitTest(pos.x, pos.y)
  if (hit < 0) return
  selectedIdx.value = hit
  syncDashFromShape(hit)
  scheduleRedraw()
}

function isTrivial(shape) {
  if ('x1' in shape) return Math.hypot(shape.x2 - shape.x1, shape.y2 - shape.y1) < 3
  if ('w'  in shape) return shape.w < 3 && shape.h < 3
  return false
}

function constrainBox(p1, p2) {
  const dx = p2.x - p1.x
  const dy = p2.y - p1.y
  const size = Math.min(Math.abs(dx), Math.abs(dy))
  return {
    x: p1.x + (dx < 0 ? -size : 0),
    y: p1.y + (dy < 0 ? -size : 0),
    w: size,
    h: size,
  }
}

// Snap angles: 0°, ±45°, ±90°, ±135°, 180°
const _SNAP_ANGLES = [0, 45, 90, 135, 180, -135, -90, -45].map(d => d * Math.PI / 180)
const _SNAP_THRESH = 2 * Math.PI / 180

// force=true (Shift held): always snap to nearest axis
// force=false: snap only when within 2° threshold
function snapLineEnd(x1, y1, x2, y2, force = false) {
  const dx   = x2 - x1
  const dy   = y2 - y1
  const dist = Math.hypot(dx, dy)
  if (dist < 2) return { x: x2, y: y2 }
  const angle = Math.atan2(dy, dx)   // atan2 range: [-π, π]
  let best = null
  let bestDiff = force ? Infinity : _SNAP_THRESH
  for (const snap of _SNAP_ANGLES) {
    let diff = angle - snap
    if (diff >  Math.PI) diff -= 2 * Math.PI  // normalise to [-π, π]
    if (diff < -Math.PI) diff += 2 * Math.PI
    const abs = Math.abs(diff)
    if (abs < bestDiff) { bestDiff = abs; best = snap }
  }
  return best !== null
    ? { x: x1 + dist * Math.cos(best), y: y1 + dist * Math.sin(best) }
    : { x: x2, y: y2 }
}

function buildShape(type, p1, p2, forceSnap = false) {
  const base = {
    type,
    color: color.value,
    width: lineWidth.value,
    ...(type !== 'text' && dashChecked.value ? { dashed: true } : {}),
  }
  if (type === 'rect' || type === 'circle' || type === 'blur' || type === 'crop') {
    const box = forceSnap ? constrainBox(p1, p2) : {
      x: Math.min(p1.x, p2.x),
      y: Math.min(p1.y, p2.y),
      w: Math.abs(p2.x - p1.x),
      h: Math.abs(p2.y - p1.y),
    }
    const s = { ...base, ...box }
    if (type === 'blur') s.strength = 4
    return s
  }
  // Line-based tools: apply angle snapping to the endpoint
  const end = LINE_TOOL_TYPES.has(type)
    ? snapLineEnd(p1.x, p1.y, p2.x, p2.y, forceSnap)
    : { x: p2.x, y: p2.y }
  return { ...base, x1: p1.x, y1: p1.y, x2: end.x, y2: end.y }
}

// ── Shape labels ──────────────────────────────────────────────────────────────

function labelAngleForLine(x1, y1, x2, y2) {
  let angle = Math.atan2(y2 - y1, x2 - x1)
  if (angle > Math.PI / 2) angle -= Math.PI
  else if (angle < -Math.PI / 2) angle += Math.PI
  return angle
}

function shapeLabelAnchor(shape) {
  if (shape.type === 'text') {
    return {
      x: shape.x,
      y: shape.y,
      angle: 0,
      fontSize: shape.fontSize,
      color: shape.color,
    }
  }
  const fs = shape.labelFontSize ?? fontSize.value
  if (LINE_TOOL_TYPES.has(shape.type)) {
    return {
      x: (shape.x1 + shape.x2) / 2,
      y: (shape.y1 + shape.y2) / 2,
      angle: labelAngleForLine(shape.x1, shape.y1, shape.x2, shape.y2),
      fontSize: fs,
      color: shape.color,
    }
  }
  if (BOX_TOOL_TYPES.has(shape.type)) {
    return {
      x: shape.x + shape.w / 2,
      y: shape.y + shape.h / 2,
      angle: 0,
      fontSize: fs,
      color: shape.color,
    }
  }
  return { x: 0, y: 0, angle: 0, fontSize: fs, color: shape.color }
}

function isEditingShapeLabel(shape) {
  return textEdit.active && textEdit.shapeIdx >= 0
    && shapes.value[textEdit.shapeIdx] === shape
    && shapes.value[textEdit.shapeIdx].type !== 'text'
}

function effectiveLineLabel(shape) {
  if (!LINE_TOOL_TYPES.has(shape.type)) return ''
  if (isEditingShapeLabel(shape) && textEdit.value.trim()) {
    return textEdit.value.trim()
  }
  return shape.label || ''
}

function lineLabelGapHalf(shape) {
  const label = effectiveLineLabel(shape)
  if (!label) return 0
  const fs = shape.labelFontSize ?? fontSize.value
  return Math.max(label.length * fs * 0.65, fs) / 2 + 6
}

function strokeSegment(ctx, x1, y1, x2, y2) {
  ctx.beginPath()
  ctx.moveTo(x1, y1)
  ctx.lineTo(x2, y2)
  ctx.stroke()
}

function strokeLineWithLabelGap(ctx, x1, y1, x2, y2, gapHalf) {
  if (gapHalf <= 0) {
    strokeSegment(ctx, x1, y1, x2, y2)
    return
  }
  const dx = x2 - x1
  const dy = y2 - y1
  const len = Math.hypot(dx, dy)
  if (len < 1) return
  if (gapHalf * 2.2 >= len) {
    strokeSegment(ctx, x1, y1, x2, y2)
    return
  }
  const ux = dx / len
  const uy = dy / len
  const mx = (x1 + x2) / 2
  const my = (y1 + y2) / 2
  strokeSegment(ctx, x1, y1, mx - ux * gapHalf, my - uy * gapHalf)
  strokeSegment(ctx, mx + ux * gapHalf, my + uy * gapHalf, x2, y2)
}

function paintAttachedLabel(ctx, shape, overrideColor = null) {
  const label = shape.label
  if (!label || shape.type === 'text') return
  const anchor = shapeLabelAnchor(shape)
  const col = overrideColor ?? anchor.color
  ctx.save()
  ctx.translate(anchor.x, anchor.y)
  if (anchor.angle) ctx.rotate(anchor.angle)
  ctx.font = `bold ${anchor.fontSize}px sans-serif`
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  if (overrideColor !== null) {
    ctx.strokeStyle = col
    ctx.lineWidth = 4
    ctx.lineJoin = 'round'
    ctx.strokeText(label, 0, 0)
  } else {
    ctx.fillStyle = col
    ctx.shadowColor = 'rgba(0,0,0,0.85)'
    ctx.shadowBlur = 4
    ctx.shadowOffsetX = 1
    ctx.shadowOffsetY = 1
    ctx.fillText(label, 0, 0)
  }
  ctx.restore()
}

// ── Text editing ──────────────────────────────────────────────────────────────

function beginEditShapeText(idx) {
  const s = shapes.value[idx]
  if (!s) return
  if (textEdit.active && textEdit.shapeIdx !== idx) commitText()
  selectedIdx.value = idx
  textEdit.shapeIdx = idx
  if (s.type === 'text') {
    textEdit.canvasX = s.x
    textEdit.canvasY = s.y
    textEdit.angle = 0
    textEdit.value = s.text
  } else {
    const anchor = shapeLabelAnchor(s)
    textEdit.canvasX = anchor.x
    textEdit.canvasY = anchor.y
    textEdit.angle = anchor.angle
    textEdit.value = s.label || ''
  }
  textEdit.active = true
  nextTick(() => {
    const el = textareaEl.value
    if (!el) return
    el.focus()
    el.select()
  })
}

function commitText() {
  if (!textEdit.active) return
  const text = textEdit.value.trim()
  let mutated = false
  if (textEdit.shapeIdx >= 0) {
    const s = shapes.value[textEdit.shapeIdx]
    if (s?.type === 'text') {
      if (text) {
        if (s.text !== text) { s.text = text; mutated = true }
      } else {
        shapes.value.splice(textEdit.shapeIdx, 1)
        if (selectedIdx.value === textEdit.shapeIdx) selectedIdx.value = -1
        else if (selectedIdx.value > textEdit.shapeIdx) selectedIdx.value -= 1
        mutated = true
      }
    } else if (s) {
      if (text) {
        if (s.label !== text) { s.label = text; mutated = true }
        if (!s.labelFontSize) s.labelFontSize = fontSize.value
      } else if (s.label !== undefined) {
        delete s.label
        delete s.labelFontSize
        mutated = true
      }
    }
  } else if (text) {
    shapes.value.push({
      type:     'text',
      color:    color.value,
      fontSize: fontSize.value,
      x:        textEdit.canvasX,
      y:        textEdit.canvasY,
      text,
    })
    mutated = true
  }
  textEdit.shapeIdx = -1
  textEdit.angle = 0
  textEdit.active = false
  textEdit.value  = ''
  if (mutated) pushHistory()
  scheduleRedraw()
}

function cancelText() {
  textEdit.shapeIdx = -1
  textEdit.angle = 0
  textEdit.active = false
  textEdit.value  = ''
}

// ── Undo / Clear ──────────────────────────────────────────────────────────────

function undo() {
  if (textEdit.active) { cancelText(); return }
  flushHistory()
  if (canUndo.value) restoreHistory(histIndex.value - 1)
}

function redo() {
  if (textEdit.active) return
  flushHistory()
  if (canRedo.value) restoreHistory(histIndex.value + 1)
}

function clearAll() {
  cancelText()
  if (!shapes.value.length) return
  shapes.value = []
  selectedIdx.value = -1
  pushHistory()
  scheduleRedraw()
}

// ── Rendering ─────────────────────────────────────────────────────────────────

function scheduleRedraw() {
  if (_rafId) return
  _rafId = requestAnimationFrame(() => {
    _rafId = null
    redraw()
  })
}

function redraw() {
  const canvas = canvasEl.value
  if (!canvas || !imgEl.value) return
  const ctx = canvas.getContext('2d')
  ctx.clearRect(0, 0, imgNW.value, imgNH.value)
  ctx.drawImage(imgEl.value, 0, 0)
  const skipTextEdit = textEdit.active && textEdit.shapeIdx >= 0
    && shapes.value[textEdit.shapeIdx]?.type === 'text'
    ? shapes.value[textEdit.shapeIdx]
    : null
  // White outline pass — always drawn first so color sits on top.
  // Highlighter / badge / blur render their own contrast, so they skip it.
  for (const shape of shapes.value) {
    if (shape === skipTextEdit) continue
    if (NO_OUTLINE_TYPES.has(shape.type)) continue
    paint(ctx, shape, '#ffffff', 2)
    if (shape.label && !isEditingShapeLabel(shape)) {
      paintAttachedLabel(ctx, shape, '#ffffff')
    }
  }
  if (drawing.value && !NO_OUTLINE_TYPES.has(drawing.value.type)) {
    paint(ctx, drawing.value, '#ffffff', 2)
  }
  for (const shape of shapes.value) {
    if (shape === skipTextEdit) continue
    paint(ctx, shape)
    if (shape.label && !isEditingShapeLabel(shape)) {
      paintAttachedLabel(ctx, shape)
    }
  }
  if (drawing.value) paint(ctx, drawing.value)
  if (crop.value && !_exporting) paintCropOverlay(ctx, crop.value)
  const sel = selectedIdx.value
  if (sel >= 0 && sel < shapes.value.length && !drawing.value && !_exporting
      && (!textEdit.active || textEdit.shapeIdx !== sel)) {
    paintSelection(ctx, shapes.value[sel])
  }
}

const NO_OUTLINE_TYPES = new Set(['highlight', 'badge', 'blur', 'crop'])

function paintCropOverlay(ctx, c) {
  const W = imgNW.value, H = imgNH.value
  ctx.save()
  ctx.fillStyle = 'rgba(0, 0, 0, 0.5)'
  ctx.fillRect(0, 0, W, Math.max(0, c.y))
  ctx.fillRect(0, c.y + c.h, W, Math.max(0, H - c.y - c.h))
  ctx.fillRect(0, c.y, Math.max(0, c.x), c.h)
  ctx.fillRect(c.x + c.w, c.y, Math.max(0, W - c.x - c.w), c.h)
  ctx.strokeStyle = 'rgba(255, 255, 255, 0.92)'
  ctx.lineWidth = Math.max(1, 1.5 / dScale.value)
  ctx.setLineDash([6 / dScale.value, 4 / dScale.value])
  ctx.strokeRect(c.x, c.y, c.w, c.h)
  ctx.restore()
}

function shapeBounds(shape) {
  if (BOX_TOOL_TYPES.has(shape.type)) {
    return { x: shape.x, y: shape.y, w: shape.w, h: shape.h }
  }
  if (shape.type === 'badge') {
    const r = shape.r || 15
    return { x: shape.x - r, y: shape.y - r, w: 2 * r, h: 2 * r }
  }
  if (shape.type === 'text') {
    const w = shape.fontSize * 0.65 * shape.text.length
    return { x: shape.x, y: shape.y, w, h: shape.fontSize }
  }
  return {
    x: Math.min(shape.x1, shape.x2),
    y: Math.min(shape.y1, shape.y2),
    w: Math.abs(shape.x2 - shape.x1),
    h: Math.abs(shape.y2 - shape.y1),
  }
}

function paintSelection(ctx, shape) {
  const b = shapeBounds(shape)
  // Pad thin line-type selections so the marquee is actually visible.
  const pad = LINE_TOOL_TYPES.has(shape.type)
    ? Math.max(Number(shape.width) || 3, 6) + 4
    : 0
  ctx.save()
  ctx.setLineDash([5 / dScale.value, 4 / dScale.value])
  ctx.lineWidth = Math.max(1, 1.5 / dScale.value)
  ctx.strokeStyle = 'rgba(80, 190, 255, 0.95)'
  ctx.strokeRect(b.x - pad, b.y - pad, Math.max(1, b.w) + pad * 2, Math.max(1, b.h) + pad * 2)
  ctx.setLineDash([])

  const points = getControlPoints(shape)
  if (points.length) {
    const r = Math.max(4, 6 / dScale.value)
    for (const p of points) {
      ctx.beginPath()
      ctx.arc(p.x, p.y, r, 0, 2 * Math.PI)
      ctx.fillStyle = '#ffffff'
      ctx.fill()
      ctx.lineWidth = Math.max(1.2, 1.8 / dScale.value)
      ctx.strokeStyle = '#2c8cff'
      ctx.stroke()
    }
  }
  ctx.restore()
}

function fillArrowHead(ctx, tipX, tipY, angle, hl, ha, strokeOutline = false) {
  ctx.setLineDash([])
  ctx.beginPath()
  ctx.moveTo(tipX, tipY)
  ctx.lineTo(tipX - hl * Math.cos(angle - ha), tipY - hl * Math.sin(angle - ha))
  ctx.lineTo(tipX - hl * Math.cos(angle + ha), tipY - hl * Math.sin(angle + ha))
  ctx.closePath()
  ctx.fill()
  if (strokeOutline) ctx.stroke()
}

function shapeIsDashed(shape) {
  return !!shape.dashed || shape.type === 'dash'
}

function applyShapeDash(ctx, shape) {
  if (shapeIsDashed(shape)) {
    ctx.setLineDash([shape.width * 4, shape.width * 3])
  } else {
    ctx.setLineDash([])
  }
}

function paint(ctx, shape, overrideColor = null, extraWidth = 0) {
  const eff = overrideColor ?? shape.color
  ctx.save()
  if (shape.opacity != null && shape.opacity < 1) ctx.globalAlpha = shape.opacity
  ctx.strokeStyle = eff
  ctx.fillStyle   = eff
  ctx.lineWidth   = shape.width + extraWidth
  ctx.lineCap     = 'round'
  ctx.lineJoin    = 'round'
  ctx.setLineDash([])

  const { type } = shape

  if (type === 'line' || type === 'dash') {
    applyShapeDash(ctx, shape)
    strokeLineWithLabelGap(
      ctx, shape.x1, shape.y1, shape.x2, shape.y2, lineLabelGapHalf(shape))

  } else if (type === 'arrow') {
    const dx    = shape.x2 - shape.x1
    const dy    = shape.y2 - shape.y1
    const dist  = Math.hypot(dx, dy)
    if (dist < 2) { ctx.restore(); return }
    const angle = Math.atan2(dy, dx)
    const hl    = Math.max(shape.width * 5, 14)
    const ha    = Math.PI / 7
    const tailX = shape.x2 - hl * 0.6 * Math.cos(angle)
    const tailY = shape.y2 - hl * 0.6 * Math.sin(angle)
    applyShapeDash(ctx, shape)
    strokeLineWithLabelGap(ctx, shape.x1, shape.y1, tailX, tailY, lineLabelGapHalf(shape))
    ctx.setLineDash([])
    const outline = overrideColor !== null
    fillArrowHead(ctx, shape.x2, shape.y2, angle, hl, ha, outline)

  } else if (type === 'dblarrow') {
    const dx    = shape.x2 - shape.x1
    const dy    = shape.y2 - shape.y1
    const dist  = Math.hypot(dx, dy)
    if (dist < 2) { ctx.restore(); return }
    const angle = Math.atan2(dy, dx)
    const hl    = Math.max(shape.width * 5, 14)
    const ha    = Math.PI / 7
    const inset = hl * 0.6
    const sx = shape.x1 + inset * Math.cos(angle)
    const sy = shape.y1 + inset * Math.sin(angle)
    const ex = shape.x2 - inset * Math.cos(angle)
    const ey = shape.y2 - inset * Math.sin(angle)
    applyShapeDash(ctx, shape)
    strokeLineWithLabelGap(ctx, sx, sy, ex, ey, lineLabelGapHalf(shape))
    ctx.setLineDash([])
    const outline = overrideColor !== null
    fillArrowHead(ctx, shape.x2, shape.y2, angle, hl, ha, outline)
    fillArrowHead(ctx, shape.x1, shape.y1, angle + Math.PI, hl, ha, outline)

  } else if (type === 'rect') {
    applyShapeDash(ctx, shape)
    ctx.strokeRect(shape.x, shape.y, shape.w, shape.h)

  } else if (type === 'circle') {
    applyShapeDash(ctx, shape)
    if (shape.w < 1 && shape.h < 1) { ctx.restore(); return }
    if (shape.w < 1) {
      ctx.beginPath()
      ctx.moveTo(shape.x, shape.y)
      ctx.lineTo(shape.x, shape.y + shape.h)
      ctx.stroke()
      ctx.restore()
      return
    }
    if (shape.h < 1) {
      ctx.beginPath()
      ctx.moveTo(shape.x, shape.y)
      ctx.lineTo(shape.x + shape.w, shape.y)
      ctx.stroke()
      ctx.restore()
      return
    }
    ctx.beginPath()
    ctx.ellipse(
      shape.x + shape.w / 2,
      shape.y + shape.h / 2,
      Math.max(1, shape.w / 2),
      Math.max(1, shape.h / 2),
      0, 0, 2 * Math.PI
    )
    ctx.stroke()

  } else if (type === 'text') {
    ctx.font         = `bold ${shape.fontSize}px sans-serif`
    ctx.textBaseline = 'top'
    if (overrideColor !== null) {
      // Outline pass: stroke text so letters get a white halo
      ctx.strokeStyle = overrideColor
      ctx.lineWidth   = 4  // 2px halo on each side of the glyph
      ctx.lineJoin    = 'round'
      ctx.strokeText(shape.text, shape.x, shape.y)
    } else {
      ctx.shadowColor   = 'rgba(0,0,0,0.85)'
      ctx.shadowBlur    = 4
      ctx.shadowOffsetX = 1
      ctx.shadowOffsetY = 1
      ctx.fillText(shape.text, shape.x, shape.y)
    }

  } else if (type === 'highlight') {
    if (overrideColor !== null) { ctx.restore(); return }
    ctx.globalAlpha = 0.3 * (shape.opacity ?? 1)
    ctx.lineWidth   = Math.max(shape.width * 3, 10)
    ctx.lineCap     = 'round'
    strokeSegment(ctx, shape.x1, shape.y1, shape.x2, shape.y2)

  } else if (type === 'badge') {
    if (overrideColor !== null) { ctx.restore(); return }
    const r = shape.r || 15
    ctx.beginPath()
    ctx.arc(shape.x, shape.y, r, 0, 2 * Math.PI)
    ctx.fillStyle = shape.color
    ctx.shadowColor = 'rgba(0,0,0,0.45)'
    ctx.shadowBlur  = 4
    ctx.shadowOffsetY = 1
    ctx.fill()
    ctx.shadowColor = 'transparent'
    ctx.lineWidth   = Math.max(2, r * 0.16)
    ctx.strokeStyle = '#ffffff'
    ctx.stroke()
    ctx.fillStyle    = '#ffffff'
    ctx.font         = `bold ${Math.round(r * 1.15)}px sans-serif`
    ctx.textAlign    = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText(String(shape.n), shape.x, shape.y + r * 0.04)

  } else if (type === 'blur') {
    if (overrideColor !== null) { ctx.restore(); return }
    drawBlurRegion(ctx, shape)

  } else if (type === 'crop') {
    // Drag preview only — the applied crop is drawn by paintCropOverlay().
    ctx.strokeStyle = 'rgba(255,255,255,0.92)'
    ctx.lineWidth   = Math.max(1, 1.5 / dScale.value)
    ctx.setLineDash([6 / dScale.value, 4 / dScale.value])
    ctx.strokeRect(shape.x, shape.y, shape.w, shape.h)
  }

  ctx.restore()
}

// Pixelate the source-image pixels inside a blur region (redacts the base image).
function drawBlurRegion(ctx, shape) {
  if (!imgEl.value) return
  const x = Math.round(shape.x)
  const y = Math.round(shape.y)
  const w = Math.max(1, Math.round(shape.w))
  const h = Math.max(1, Math.round(shape.h))
  const strength = Math.min(10, Math.max(1, shape.strength || 4))
  const block = Math.max(3, Math.round(Math.min(w, h) / (15 - strength)))
  const sw = Math.max(1, Math.round(w / block))
  const sh = Math.max(1, Math.round(h / block))

  const sx  = Math.max(0, x)
  const sy  = Math.max(0, y)
  const sxw = Math.min(imgNW.value, x + w) - sx
  const syh = Math.min(imgNH.value, y + h) - sy
  if (sxw <= 0 || syh <= 0) return

  const tmp  = _blurCanvas
  tmp.width  = sw
  tmp.height = sh
  const tctx = tmp.getContext('2d')
  tctx.imageSmoothingEnabled = false
  tctx.clearRect(0, 0, sw, sh)
  tctx.drawImage(imgEl.value, sx, sy, sxw, syh, 0, 0, sw, sh)

  ctx.save()
  ctx.imageSmoothingEnabled = false
  ctx.beginPath()
  ctx.rect(x, y, w, h)
  ctx.clip()
  ctx.drawImage(tmp, 0, 0, sw, sh, x, y, w, h)
  ctx.restore()
}

// ── Export ────────────────────────────────────────────────────────────────────

// Re-render without the selection / crop overlay, then hand back the canvas to
// export — the full canvas, or just the crop region when one is set.
function exportCanvas() {
  _exporting = true
  redraw()
  _exporting = false
  const src = canvasEl.value
  if (!src || !crop.value) return src
  const c = crop.value
  const out = document.createElement('canvas')
  out.width  = Math.max(1, Math.round(c.w))
  out.height = Math.max(1, Math.round(c.h))
  out.getContext('2d').drawImage(src, c.x, c.y, c.w, c.h, 0, 0, out.width, out.height)
  return out
}

async function copyToClipboard() {
  commitText()
  await nextTick()
  const canvas = exportCanvas()
  if (!canvas) return
  canvas.toBlob(async (blob) => {
    scheduleRedraw()   // restore the on-screen overlay
    if (!blob) { showStatus('Failed to capture image.', 'error'); return }
    if (typeof ClipboardItem !== 'undefined' && navigator.clipboard?.write && window.isSecureContext) {
      try {
        await navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })])
        showStatus('Copied to clipboard!')
        return
      } catch { /* fall through */ }
    }
    triggerDownload(blob)
    showStatus('Clipboard unavailable — saved as PNG.')
  }, 'image/png')
}

function saveAsPng() {
  commitText()
  nextTick(() => {
    const canvas = exportCanvas()
    if (!canvas) return
    canvas.toBlob((blob) => {
      scheduleRedraw()
      if (blob) { triggerDownload(blob); showStatus(`Saved as ${props.downloadFilename}`) }
    }, 'image/png')
  })
}

function triggerDownload(blob) {
  const url  = URL.createObjectURL(blob)
  const a    = document.createElement('a')
  a.href     = url
  a.download = props.downloadFilename
  a.click()
  URL.revokeObjectURL(url)
}
</script>

<style scoped>
/* ── Overlay ───────────────────────────────────────────────────────────────── */
.se-overlay {
  position: fixed;
  inset: 0;
  background: color-mix(in srgb, #000 62%, transparent);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10000;
  backdrop-filter: blur(6px) saturate(1.1);
  -webkit-backdrop-filter: blur(6px) saturate(1.1);

  /* Component-scoped tokens — resolve against the app theme, with a
     self-contained dark fallback so the editor also stands alone. */
  --se-surface:     var(--panel-bg, #1a1a2e);
  --se-surface-2:   var(--bg, #13132a);
  --se-border:      var(--border, #3a3a60);
  --se-border-soft: color-mix(in srgb, var(--border, #3a3a60) 55%, transparent);
  --se-fg:          var(--fg, #e6e6f2);
  --se-fg-dim:      var(--fg-dim, #8a8ab0);
  --se-accent:      var(--accent, #4f8bff);
  /* Radii track the shared modern-dialog family (SettingsDialog = 14). */
  --se-radius:      14px;
  --se-radius-sm:   9px;
  --se-radius-xs:   6px;
  --se-ring:        0 0 0 3px color-mix(in srgb, var(--accent, #4f8bff) 30%, transparent);
}

/* ── Window ────────────────────────────────────────────────────────────────── */
.se-win {
  position: relative;
  display: grid;
  grid-template-columns: auto 1fr;
  grid-template-rows: auto 1fr auto;
  grid-template-areas:
    "toolbar toolbar"
    "rail    canvas"
    "footer  footer";
  background: var(--se-surface);
  border: 1px solid var(--se-border-soft);
  border-radius: var(--se-radius);
  box-shadow:
    0 32px 80px -12px rgba(0, 0, 0, 0.6),
    0 0 0 1px color-mix(in srgb, #fff 5%, transparent),
    inset 0 1px 0 color-mix(in srgb, #fff 6%, transparent);
  max-width: 97vw;
  max-height: 95vh;
  overflow: hidden;
  user-select: none;
  animation: se-pop 0.18s cubic-bezier(0.32, 0.72, 0, 1);
}
.se-toolbar { grid-area: toolbar; }
.se-rail    { grid-area: rail; }
.se-body    { grid-area: canvas; min-width: 0; }
.se-footer  { grid-area: footer; }

@keyframes se-pop {
  from { opacity: 0; transform: translateY(8px) scale(0.985); }
  to   { opacity: 1; transform: none; }
}

/* ── Toolbar ───────────────────────────────────────────────────────────────── */
.se-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
  padding: 8px 10px;
  background: linear-gradient(180deg, var(--se-surface), var(--se-surface-2));
  border-bottom: 1px solid var(--se-border-soft);
  flex-shrink: 0;
  cursor: move;          /* the toolbar background is the window drag handle */
}
.se-toolbar button,
.se-toolbar input,
.se-toolbar .se-zoom,
.se-toolbar .se-hint { cursor: default; }
.se-toolbar button:not(:disabled),
.se-toolbar .se-hint { cursor: pointer; }

/* ── Tool rail ─────────────────────────────────────────────────────────────── */
.se-rail {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
  padding: 8px 6px;
  background: var(--se-surface-2);
  border-right: 1px solid var(--se-border-soft);
  overflow-y: auto;
}

.se-rail-btn {
  width: 34px;
  height: 32px;
  display: grid;
  place-items: center;
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--se-radius-xs);
  color: var(--se-fg-dim);
  cursor: pointer;
  transition: background 0.14s ease, color 0.14s ease, box-shadow 0.14s ease;
}
.se-rail-btn :deep(svg) { width: 16px; height: 16px; display: block; }
.se-rail-btn:hover {
  background: color-mix(in srgb, var(--se-fg) 10%, transparent);
  color: var(--se-fg);
}
.se-rail-btn.active {
  background: var(--se-accent);
  color: #fff;
  box-shadow: 0 2px 10px -3px color-mix(in srgb, var(--se-accent) 75%, transparent);
}
.se-rail-btn:focus-visible {
  outline: none;
  box-shadow: var(--se-ring);
}

.se-rail-sep {
  width: 20px;
  height: 1px;
  background: var(--se-border-soft);
  margin: 4px 0;
}

/* ── Zoom control group ────────────────────────────────────────────────────── */
.se-zoom {
  display: flex;
  gap: 2px;
  padding: 3px;
  background: var(--se-surface-2);
  border: 1px solid var(--se-border-soft);
  border-radius: var(--se-radius-sm);
}
.se-zoom .se-tbtn { height: 28px; }
.se-zoom-btn {
  min-width: 26px;
  padding: 0 6px;
  font-size: 15px;
}
.se-zoom-val {
  min-width: 48px;
  font-size: 11px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

/* ── Default-style group ───────────────────────────────────────────────────── */
.se-style {
  position: relative;
  z-index: 20;
  display: flex;
  align-items: center;
  gap: 3px;
  padding: 3px 5px;
  background: var(--se-surface-2);
  border: 1px solid var(--se-border-soft);
  border-radius: var(--se-radius-sm);
}
.se-style .se-tbtn { height: 28px; }
.se-style-swatch {
  width: 22px;
  height: 22px;
  padding: 0;
  border: 2px solid color-mix(in srgb, #fff 30%, transparent);
  border-radius: var(--se-radius-xs);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, #000 25%, transparent);
  cursor: pointer;
}
.se-style-div {
  width: 1px;
  height: 18px;
  background: var(--se-border-soft);
  margin: 0 3px;
}
.se-style-val {
  min-width: 20px;
  text-align: center;
  font-size: 11px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--se-fg);
}
.se-style-dash {
  height: 24px;
  padding: 0 9px;
  font-size: 11px;
  font-weight: 500;
  border-radius: var(--se-radius-xs);
}
.se-style-dash.on {
  background: var(--se-accent);
  color: #fff;
}
/* The default-colour popup drops from the toolbar swatch. */
.se-style .se-color-panel { top: calc(100% + 8px); left: 0; }

/* ── Toolbar button ────────────────────────────────────────────────────────── */
.se-tbtn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  height: 32px;
  padding: 0 10px;
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--se-radius-xs);
  color: var(--se-fg-dim);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
  line-height: 1;
  transition: background 0.14s ease, border-color 0.14s ease,
              color 0.14s ease, transform 0.06s ease, box-shadow 0.14s ease;
  box-sizing: border-box;
}


.se-tbtn.icon-btn {
  padding: 0 7px;
}

.se-tbtn :deep(svg) {
  width: 16px;
  height: 16px;
  display: block;
}

.se-tbtn:hover:not(:disabled) {
  background: color-mix(in srgb, var(--se-fg) 10%, transparent);
  color: var(--se-fg);
}

.se-tbtn:active:not(:disabled) {
  transform: translateY(1px);
}

.se-tbtn.active {
  background: var(--se-accent);
  border-color: transparent;
  color: #fff;
  box-shadow: 0 2px 10px -3px color-mix(in srgb, var(--se-accent) 75%, transparent);
}

.se-tbtn:focus-visible {
  outline: none;
  box-shadow: var(--se-ring);
}

.se-tbtn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

/* ── Footer action bar ─────────────────────────────────────────────────────── */
.se-footer {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px 12px;
  background: linear-gradient(0deg, var(--se-surface), var(--se-surface-2));
  border-top: 1px solid var(--se-border-soft);
  flex-shrink: 0;
}

.se-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 34px;
  padding: 0 18px;
  border-radius: var(--se-radius-xs);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  line-height: 1;
  border: 1px solid transparent;
  transition: background 0.14s ease, border-color 0.14s ease,
              color 0.14s ease, filter 0.14s ease, transform 0.06s ease;
  box-sizing: border-box;
}

.se-btn :deep(svg) { width: 15px; height: 15px; display: block; }

.se-btn:active { transform: translateY(1px); }

.se-btn:focus-visible {
  outline: none;
  box-shadow: var(--se-ring);
}

.se-btn.primary {
  background: var(--se-accent);
  color: #fff;
  box-shadow: 0 2px 12px -3px color-mix(in srgb, var(--se-accent) 65%, transparent);
}

.se-btn.primary:hover { filter: brightness(1.08); }

.se-btn.secondary {
  background: transparent;
  color: var(--se-fg-dim);
  border-color: var(--se-border);
}

.se-btn.secondary:hover {
  background: color-mix(in srgb, var(--se-fg) 10%, transparent);
  color: var(--se-fg);
}

.se-spacer {
  flex: 1;
}

/* ── Shortcuts hint chip ───────────────────────────────────────────────────── */
.se-hint {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 30px;
  padding: 0 12px;
  background: transparent;
  border: 1px solid var(--se-border-soft);
  border-radius: 999px;
  color: var(--se-fg-dim);
  font-size: 11px;
  font-weight: 500;
  cursor: pointer;
  transition: color 0.14s ease, border-color 0.14s ease;
}
.se-hint:hover { color: var(--se-fg); border-color: var(--se-border); }
.se-hint kbd {
  font-family: ui-monospace, "SF Mono", Menlo, monospace;
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 4px;
  border: 1px solid var(--se-border-soft);
  background: var(--se-surface-2);
}

.se-color-panel {
  position: absolute;
  top: calc(100% + 8px);
  left: 0;
  z-index: 200;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 10px;
  background: var(--se-surface);
  border: 1px solid var(--se-border-soft);
  border-radius: var(--se-radius-sm);
  width: 178px;
  box-shadow: 0 16px 40px -8px rgba(0, 0, 0, 0.55),
              0 0 0 1px color-mix(in srgb, #fff 5%, transparent);
  animation: se-pop 0.14s ease;
}

/* ── Applied-crop chip ─────────────────────────────────────────────────────── */
.se-crop-chip {
  position: absolute;
  top: 12px;
  left: 12px;
  z-index: 7;
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 5px 6px 5px 10px;
  background: color-mix(in srgb, var(--se-surface) 92%, transparent);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  border: 1px solid var(--se-border);
  border-radius: 999px;
  color: var(--se-fg-dim);
  font-size: 11px;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
  box-shadow: 0 8px 22px -10px rgba(0, 0, 0, 0.55);
}
.se-crop-chip button {
  width: 18px;
  height: 18px;
  display: grid;
  place-items: center;
  padding: 0;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: var(--se-fg-dim);
  font-size: 13px;
  line-height: 1;
  cursor: pointer;
}
.se-crop-chip button:hover {
  background: color-mix(in srgb, #e5484d 20%, transparent);
  color: #ff8a8a;
}

.se-color-dot {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  border: 2px solid transparent;
  cursor: pointer;
  flex-shrink: 0;
  box-sizing: border-box;
  transition: border-color 0.1s, transform 0.1s;
}

.se-color-dot:hover {
  border-color: #ccc;
  transform: scale(1.18);
}

.se-color-dot.active {
  border-color: #fff;
  outline: 2px solid var(--se-accent);
  outline-offset: 1px;
  transform: scale(1.1);
}

.se-color-custom {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  border: 2px solid #555;
  background: conic-gradient(red, yellow, lime, cyan, blue, magenta, red);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
  color: white;
  flex-shrink: 0;
}

.se-color-custom-input {
  position: absolute;
  inset: 0;
  opacity: 0;
  cursor: pointer;
  width: 100%;
  height: 100%;
}

.se-color-eyedrop {
  width: 22px;
  height: 22px;
  display: grid;
  place-items: center;
  padding: 0;
  border: 1px solid var(--se-border-soft);
  border-radius: 50%;
  background: var(--se-surface-2);
  color: var(--se-fg-dim);
  cursor: pointer;
  flex-shrink: 0;
}
.se-color-eyedrop:hover { color: var(--se-fg); border-color: var(--se-border); }

.se-color-recent {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  width: 100%;
  padding-top: 8px;
  margin-top: 2px;
  border-top: 1px solid var(--se-border-soft);
}

.se-range {
  width: 92px;
  height: 4px;
  cursor: pointer;
  accent-color: var(--se-accent);
  margin: 0;
}

/* ── Canvas body ───────────────────────────────────────────────────────────── */
.se-body {
  position: relative;
  flex: 1;
  overflow: auto;
  display: flex;
  /* `safe` keeps the canvas reachable when it is zoomed larger than the
     viewport — plain `center` would clip the top / left and block scrolling. */
  align-items: safe center;
  justify-content: safe center;
  padding: 28px;
  min-height: 0;
  background: color-mix(in srgb, var(--se-surface-2) 82%, #000);
  /* Checkerboard so transparency is visible */
  --se-check: color-mix(in srgb, var(--se-fg) 6%, transparent);
  background-image:
    linear-gradient(45deg, var(--se-check) 25%, transparent 25%),
    linear-gradient(-45deg, var(--se-check) 25%, transparent 25%),
    linear-gradient(45deg, transparent 75%, var(--se-check) 75%),
    linear-gradient(-45deg, transparent 75%, var(--se-check) 75%);
  background-size: 22px 22px;
  background-position: 0 0, 0 11px, 11px -11px, -11px 0;
}

.se-body.se-panning,
.se-body.se-panning .se-canvas-wrap canvas { cursor: grab; }

/* ── Canvas wrap ───────────────────────────────────────────────────────────── */
.se-canvas-wrap {
  border-radius: 4px;
  box-shadow:
    0 18px 48px -12px rgba(0, 0, 0, 0.62),
    0 0 0 1px color-mix(in srgb, #fff 10%, transparent);
}

.se-canvas-wrap canvas {
  display: block;
  border-radius: 4px;
}

/* ── Floating text input ───────────────────────────────────────────────────── */
.se-text-input {
  position: absolute;
  background: transparent;
  /* Accent dashes read on both light and dark screenshots. */
  border: 1px dashed var(--se-accent);
  border-radius: 2px;
  outline: none;
  resize: none;
  overflow: hidden;
  font-family: sans-serif;
  font-weight: bold;
  min-width: 60px;
  min-height: 1.3em;
  z-index: 1;
  white-space: nowrap;
  box-sizing: border-box;
}

/* ── Status toast ───────────────────────────────────────────────────────────── */
.se-status {
  position: absolute;
  /* Sit above the footer action bar. */
  bottom: 74px;
  left: 50%;
  transform: translateX(-50%);
  background: color-mix(in srgb, var(--se-surface) 88%, transparent);
  backdrop-filter: blur(12px) saturate(1.2);
  -webkit-backdrop-filter: blur(12px) saturate(1.2);
  border: 1px solid color-mix(in srgb, var(--se-accent) 45%, transparent);
  border-radius: 999px;
  color: color-mix(in srgb, var(--se-accent) 85%, var(--se-fg));
  font-size: 13px;
  font-weight: 500;
  padding: 8px 20px;
  pointer-events: none;
  white-space: nowrap;
  z-index: 200;
  box-shadow: 0 12px 32px -8px rgba(0, 0, 0, 0.5);
}

.se-status.success {
  border-color: color-mix(in srgb, #3fb950 55%, transparent);
  color: #5ddc8f;
}

.se-status.error {
  border-color: color-mix(in srgb, #e5484d 55%, transparent);
  color: #ff8a8a;
}

.se-toast-enter-active,
.se-toast-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.se-toast-enter-from,
.se-toast-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(8px);
}


/* ── Floating selection inspector ─────────────────────────────────────────── */
.se-inspector {
  position: absolute;
  z-index: 6;
  display: flex;
  flex-direction: column;
  gap: 7px;
  padding: 10px;
  background: color-mix(in srgb, var(--se-surface) 96%, transparent);
  backdrop-filter: blur(14px) saturate(1.2);
  -webkit-backdrop-filter: blur(14px) saturate(1.2);
  border: 1px solid var(--se-border);
  border-radius: var(--se-radius-sm);
  box-shadow: 0 18px 44px -14px rgba(0, 0, 0, 0.6),
              0 0 0 1px color-mix(in srgb, #fff 5%, transparent);
  user-select: none;
  animation: se-pop 0.13s ease;
}

.se-insp-head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.se-insp-title { font-size: 12px; font-weight: 600; color: var(--se-fg); }

.se-insp-dims {
  font-size: 11px;
  color: var(--se-fg-dim);
  font-variant-numeric: tabular-nums;
}

.se-insp-x {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  padding: 0;
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--se-radius-xs);
  color: var(--se-fg-dim);
  cursor: pointer;
  transition: background 0.12s ease, color 0.12s ease;
}
.se-insp-x:hover {
  background: color-mix(in srgb, #e5484d 18%, transparent);
  color: #ff8a8a;
}
.se-insp-x :deep(svg) { width: 13px; height: 13px; display: block; }

.se-insp-row {
  display: grid;
  grid-template-columns: 44px 1fr auto;
  align-items: center;
  gap: 8px;
}

.se-insp-lbl {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.03em;
  text-transform: uppercase;
  color: var(--se-fg-dim);
  white-space: nowrap;
}

.se-insp-val {
  font-size: 11px;
  color: var(--se-fg-dim);
  font-variant-numeric: tabular-nums;
  min-width: 16px;
  text-align: right;
}

.se-inspector .se-range { width: 100%; }

.se-insp-colors {
  grid-column: 2 / -1;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
}

.se-insp-dot {
  width: 16px;
  height: 16px;
  padding: 0;
  border-radius: 50%;
  border: 2px solid transparent;
  cursor: pointer;
  box-sizing: border-box;
  box-shadow: inset 0 0 0 1px color-mix(in srgb, #000 25%, transparent);
  transition: transform 0.1s ease, border-color 0.1s ease;
}
.se-insp-dot:hover { transform: scale(1.15); }
.se-insp-dot.active {
  border-color: #fff;
  outline: 2px solid var(--se-accent);
  outline-offset: 1px;
}

.se-insp-custom {
  position: relative;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  border: 2px solid #555;
  background: conic-gradient(red, yellow, lime, cyan, blue, magenta, red);
  cursor: pointer;
  overflow: hidden;
  flex-shrink: 0;
}
.se-insp-custom input {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  opacity: 0;
  cursor: pointer;
}

.se-insp-eyedrop {
  width: 16px;
  height: 16px;
  display: grid;
  place-items: center;
  padding: 0;
  border: 1px solid var(--se-border-soft);
  border-radius: 50%;
  background: var(--se-surface-2);
  color: var(--se-fg-dim);
  cursor: pointer;
  flex-shrink: 0;
}
.se-insp-eyedrop:hover { color: var(--se-fg); border-color: var(--se-border); }

.se-insp-hex {
  width: 72px;
  margin-left: auto;
  background: var(--se-surface-2);
  border: 1px solid var(--se-border-soft);
  border-radius: var(--se-radius-xs);
  color: var(--se-fg-dim);
  font: 400 10px/1 ui-monospace, "SF Mono", Menlo, monospace;
  text-transform: uppercase;
  padding: 4px 6px;
  box-sizing: border-box;
}
.se-insp-hex:focus {
  outline: none;
  border-color: var(--se-accent);
  box-shadow: var(--se-ring);
  color: var(--se-fg);
}

.se-insp-recent {
  grid-column: 2 / -1;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  padding-top: 6px;
  border-top: 1px dashed var(--se-border-soft);
}

.se-insp-seg {
  grid-column: 2 / -1;
  display: flex;
  gap: 2px;
  padding: 2px;
  background: var(--se-surface-2);
  border: 1px solid var(--se-border-soft);
  border-radius: var(--se-radius-xs);
}
.se-insp-seg button {
  flex: 1;
  height: 22px;
  background: transparent;
  border: 0;
  border-radius: 4px;
  color: var(--se-fg-dim);
  font-size: 11px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.12s ease, color 0.12s ease;
}
.se-insp-seg button.on { background: var(--se-accent); color: #fff; }

.se-insp-text {
  grid-column: 2 / -1;
  width: 100%;
  background: var(--se-surface-2);
  border: 1px solid var(--se-border-soft);
  border-radius: var(--se-radius-xs);
  color: var(--se-fg);
  padding: 4px 7px;
  font-size: 12px;
  box-sizing: border-box;
  transition: border-color 0.14s ease, box-shadow 0.14s ease;
}
.se-insp-text:focus {
  outline: none;
  border-color: var(--se-accent);
  box-shadow: var(--se-ring);
}

.se-insp-zrow {
  grid-column: 2 / -1;
  display: flex;
  gap: 3px;
}
.se-insp-zrow button {
  flex: 1;
  height: 24px;
  background: var(--se-surface-2);
  border: 1px solid var(--se-border-soft);
  border-radius: var(--se-radius-xs);
  color: var(--se-fg-dim);
  font-size: 12px;
  line-height: 1;
  cursor: pointer;
  transition: color 0.12s ease, border-color 0.12s ease;
}
.se-insp-zrow button:hover { color: var(--se-fg); border-color: var(--se-border); }

/* ── Keyboard-shortcuts overlay ───────────────────────────────────────────── */
.se-sc-backdrop {
  position: absolute;
  inset: 0;
  z-index: 400;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: color-mix(in srgb, #000 45%, transparent);
  backdrop-filter: blur(3px);
  -webkit-backdrop-filter: blur(3px);
}

.se-sc-card {
  width: min(460px, 100%);
  max-height: 100%;
  overflow-y: auto;
  padding: 16px 18px;
  background: var(--se-surface);
  border: 1px solid var(--se-border);
  border-radius: var(--se-radius);
  box-shadow: 0 24px 60px -18px rgba(0, 0, 0, 0.7);
  animation: se-pop 0.16s ease;
}

.se-sc-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
  font-weight: 600;
  color: var(--se-fg);
  margin-bottom: 12px;
}

.se-sc-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px 18px;
}
@media (max-width: 520px) { .se-sc-grid { grid-template-columns: 1fr; } }

.se-sc-row {
  display: flex;
  align-items: baseline;
  gap: 8px;
  font-size: 12px;
  color: var(--se-fg-dim);
}
.se-sc-row kbd {
  flex-shrink: 0;
  font-family: ui-monospace, "SF Mono", Menlo, monospace;
  font-size: 10px;
  color: var(--se-fg);
  background: var(--se-surface-2);
  border: 1px solid var(--se-border-soft);
  border-bottom-width: 2px;
  border-radius: 4px;
  padding: 2px 6px;
  white-space: nowrap;
}

.se-sc-clear {
  margin-top: 14px;
  width: 100%;
  height: 30px;
  background: transparent;
  border: 1px solid var(--se-border-soft);
  border-radius: var(--se-radius-xs);
  color: var(--se-fg-dim);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
}
.se-sc-clear:hover:not(:disabled) {
  color: #ff8a8a;
  border-color: color-mix(in srgb, #e5484d 45%, transparent);
}
.se-sc-clear:disabled { opacity: 0.4; cursor: not-allowed; }

/* ── Reduced motion ───────────────────────────────────────────────────────── */
@media (prefers-reduced-motion: reduce) {
  .se-win,
  .se-color-panel,
  .se-inspector,
  .se-sc-card { animation: none; }
  .se-tbtn,
  .se-btn,
  .se-hint,
  .se-rail-btn,
  .se-color-dot,
  .se-insp-dot,
  .se-insp-seg button,
  .se-insp-zrow button,
  .se-toast-enter-active,
  .se-toast-leave-active { transition: none; }
}
</style>
