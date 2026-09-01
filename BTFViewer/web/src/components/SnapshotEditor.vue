<template>
  <div class="se-overlay" ref="overlayEl" @click.self="handleClose">
    <div class="se-win">
      <!-- ── Toolbar ─────────────────────────────────────────────────────── -->
      <div class="se-toolbar">

        <!-- Tool buttons -->
        <div class="se-tools">
          <button
            v-for="t in TOOLS"
            :key="t.id"
            class="se-tbtn icon-btn"
            :class="{ active: tool === t.id }"
            :title="t.label"
            @click="setTool(t.id)"
            v-html="t.icon"
          />
        </div>

        <div class="se-sep" />

        <!-- Color picker -->
        <div class="se-ctl se-color-ctl" title="Stroke / text color">
          <span class="se-ctl-lbl">Color</span>
          <button class="se-color-swatch" :style="{ background: color }"
                  @click.stop="colorPanelOpen = !colorPanelOpen" />
          <div v-if="colorPanelOpen" class="se-color-panel" @click.stop>
            <div
              v-for="c in PRESET_COLORS" :key="c"
              class="se-color-dot"
              :class="{ active: color === c }"
              :style="{ background: c }"
              :title="c"
              @click="pickColor(c)"
            />
            <label class="se-color-custom" title="Custom color\u2026">
              <span v-html="ICON_PALETTE" />
              <input type="color" :value="color" @input="e => pickColor(e.target.value)"
                     class="se-color-custom-input" />
            </label>
          </div>
        </div>

        <!-- Stroke width -->
        <label class="se-ctl" title="Stroke width">
          <span class="se-ctl-lbl">Size&nbsp;{{ lineWidth }}</span>
          <input class="se-range" type="range" min="1" max="20" step="1" v-model.number="lineWidth" />
        </label>

        <!-- Dash stroke -->
        <label v-if="tool !== 'text'" class="se-ctl se-dash-ctl" title="Dashed stroke">
          <input type="checkbox" v-model="dashChecked" @change="onDashToggle" />
          <span class="se-ctl-lbl">Dash</span>
        </label>

        <!-- Font size (text tool only) -->
        <label v-if="tool === 'text'" class="se-ctl" title="Font size">
          <span class="se-ctl-lbl">Font&nbsp;{{ fontSize }}</span>
          <input class="se-range" type="range" min="10" max="72" step="2" v-model.number="fontSize" />
        </label>

        <div class="se-sep" />

        <!-- Undo -->
        <button
          class="se-tbtn icon-btn"
          :disabled="!shapes.length && !textEdit.active"
          title="Undo (Ctrl+Z)"
          @click="undo"
          v-html="ICON_UNDO"
        />

        <!-- Clear all -->
        <button
          class="se-tbtn icon-btn"
          :disabled="!shapes.length"
          title="Clear all annotations"
          @click="clearAll"
          v-html="ICON_CLEAR"
        />

        <div class="se-sep" />

        <!-- Copy to clipboard -->
        <button class="se-tbtn action-btn" title="Copy annotated image to clipboard" @click="copyToClipboard">
          <span v-html="ICON_COPY" />
          Copy
        </button>

        <!-- Save PNG -->
        <button class="se-tbtn action-btn" title="Save annotated image as PNG" @click="saveAsPng">
          <span v-html="ICON_SAVE" />
          Save PNG
        </button>

        <div class="se-spacer" />

        <!-- Close -->
        <button class="se-close" title="Close editor" @click="handleClose">✕</button>
      </div>

      <!-- ── Status toast ────────────────────────────────────────────── -->
      <Transition name="se-toast">
        <div v-if="statusVisible" class="se-status" :class="statusType">{{ statusMsg }}</div>
      </Transition>

      <!-- ── Canvas area ────────────────────────────────────────────────── -->
      <div class="se-body" ref="bodyEl">
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
        </div>
      </div>
    </div>

    <!-- ── Context menu ─────────────────────────────────────────────────── -->
    <div v-if="ctxMenu.visible"
         class="se-ctx-menu"
         :style="{ left: ctxMenu.x + 'px', top: ctxMenu.y + 'px' }"
         @mousedown.stop>
      <div class="se-ctx-item se-ctx-delete" @click="ctxDelete">Delete</div>
      <div class="se-ctx-sep" />
      <div class="se-ctx-item">
        <span class="se-ctx-lbl">Color</span>
        <input type="color" class="se-ctx-color"
               :value="ctxShape?.color"
               @input="e => ctxSetProp('color', e.target.value)" />
      </div>
      <template v-if="ctxShape?.type !== 'text'">
        <div class="se-ctx-item">
          <span class="se-ctx-lbl">Size (px)</span>
          <input type="number" class="se-ctx-num" min="1" max="20"
                 :value="ctxShape?.width"
                 @change="e => ctxSetProp('width', +e.target.value)" />
        </div>
        <div class="se-ctx-item">
          <span class="se-ctx-lbl">Label</span>
          <input type="text" class="se-ctx-text"
                 :value="ctxShape?.label || ''"
                 @change="e => ctxSetProp('label', e.target.value)" />
        </div>
      </template>
      <template v-else>
        <div class="se-ctx-item">
          <span class="se-ctx-lbl">Text</span>
          <input type="text" class="se-ctx-text"
                 :value="ctxShape?.text"
                 @change="e => ctxSetProp('text', e.target.value)" />
        </div>
        <div class="se-ctx-item">
          <span class="se-ctx-lbl">Font (pt)</span>
          <input type="number" class="se-ctx-num" min="8" max="72"
                 :value="ctxShape?.fontSize"
                 @change="e => ctxSetProp('fontSize', +e.target.value)" />
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import {
  SNAP_TOOL_ICONS,
  ICON_UNDO,
  ICON_CLEAR,
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
  { id: 'arrow', label: 'Arrow', icon: SNAP_TOOL_ICONS.arrow },
  { id: 'dblarrow', label: 'Double Arrow', icon: SNAP_TOOL_ICONS.dblarrow },
  { id: 'line', label: 'Line', icon: SNAP_TOOL_ICONS.line },
  { id: 'rect', label: 'Rectangle (Shift: square)', icon: SNAP_TOOL_ICONS.rect },
  { id: 'circle', label: 'Circle / Ellipse (Shift: circle)', icon: SNAP_TOOL_ICONS.circle },
  { id: 'text', label: 'Add Text (click to place)', icon: SNAP_TOOL_ICONS.text },
]

const TOOL_CURSORS = {
  arrow: 'crosshair',
  dblarrow: 'crosshair',
  line:  'crosshair',
  rect:  'crosshair',
  circle:'crosshair',
  text:  'text',
}

const LINE_TOOL_TYPES = new Set(['line', 'arrow', 'dblarrow', 'dash'])

// ── Reactive state ────────────────────────────────────────────────────────────

const tool      = ref('arrow')
const color     = ref('#ff4444')
const lineWidth = ref(3)
const fontSize  = ref(20)
const dashChecked = ref(false)

const colorPanelOpen = ref(false)
const PRESET_COLORS = [
  '#ff4444', '#ff8800', '#ffdd00', '#44cc44', '#00bbff', '#4466ff', '#9944ff', '#ff44aa',
  '#ffffff', '#cccccc', '#888888', '#444444', '#000000',
  '#cc0000', '#cc5500', '#aa9900', '#007700', '#005588', '#002299', '#550099',
]
function pickColor(hex) {
  color.value = hex
  colorPanelOpen.value = false
  scheduleRedraw()
}
function closeColorPanel() {
  colorPanelOpen.value = false
}
const shapes    = ref([])
const drawing   = ref(null)
const selectedIdx = ref(-1)

const imgNW  = ref(1)
const imgNH  = ref(1)
const imgEl  = ref(null)
const dScale = ref(1)

const overlayEl  = ref(null)
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
  cursor:  tool.value === 'text'
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
  document.addEventListener('click', closeColorPanel)
  window.addEventListener('resize', computeScale)
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', onDocKeyDown, true)
  document.removeEventListener('click', closeColorPanel)
  window.removeEventListener('resize', computeScale)
  if (_rafId) cancelAnimationFrame(_rafId)
})

function computeScale() {
  if (!bodyEl.value || !imgNW.value || !imgNH.value) return
  const r     = bodyEl.value.getBoundingClientRect()
  const availW = Math.max(1, r.width  - 48)
  const availH = Math.max(1, r.height - 48)
  dScale.value = Math.min(1, availW / imgNW.value, availH / imgNH.value)
}

function onDocKeyDown(e) {
  // Esc — close color panel, then context menu (does NOT close the editor)
  if (e.key === 'Escape') {
    e.preventDefault()
    e.stopPropagation()
    if (colorPanelOpen.value) { colorPanelOpen.value = false; return }
    if (ctxMenu.visible) { closeCtxMenu(); return }
    if (textEdit.active) { cancelText(); return }
    return
  }
  // Ctrl/Cmd+Z — undo
  if (e.key === 'z' && (e.ctrlKey || e.metaKey) && !e.shiftKey) {
    if (overlayEl.value?.contains(document.activeElement) || document.activeElement === document.body) {
      e.preventDefault()
      undo()
    }
  }
}

// ── Tool selection ────────────────────────────────────────────────────────────

function setTool(t) {
  cancelText()
  tool.value = t
}

function onDashToggle() {
  if (selectedIdx.value >= 0) {
    const s = shapes.value[selectedIdx.value]
    if (s && s.type !== 'text') {
      s.dashed = dashChecked.value
      scheduleRedraw()
    }
  }
}

function syncDashFromShape(idx) {
  if (idx < 0 || idx >= shapes.value.length) return
  const s = shapes.value[idx]
  if (s.type !== 'text') dashChecked.value = !!s.dashed
}

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
  closeCtxMenu()
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
    scheduleRedraw()
    return
  }

  if (dragMode.value === 'move' && _dragIdx >= 0 && _dragPrev) {
    moveShape(_dragIdx, pos.x - _dragPrev.x, pos.y - _dragPrev.y)
    _dragPrev = pos
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
    scheduleRedraw()
    return
  }
  if (!_mouseDown) return
  _mouseDown = false
  if (drawing.value && _startPos) {
    const pos   = getPos(e)
    const shape = buildShape(tool.value, _startPos, pos, e.shiftKey)
    if (!isTrivial(shape)) shapes.value.push(shape)
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
  closeCtxMenu()
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
    } else if (s.type === 'rect' || s.type === 'circle') {
      if (x >= s.x - thr && x <= s.x + s.w + thr &&
          y >= s.y - thr && y <= s.y + s.h + thr) return i
    } else {
      if (ptToSegDist(x, y, s.x1, s.y1, s.x2, s.y2) < thr + s.width) return i
    }
  }
  return -1
}

function moveShape(idx, dx, dy) {
  const s = shapes.value[idx]
  if (s.type === 'text' || s.type === 'rect' || s.type === 'circle') {
    s.x += dx; s.y += dy
  } else {
    s.x1 += dx; s.y1 += dy
    s.x2 += dx; s.y2 += dy
  }
}

function cloneShape(shape) {
  if (shape.type === 'text') {
    return {
      type: shape.type,
      color: shape.color,
      fontSize: shape.fontSize,
      x: shape.x,
      y: shape.y,
      text: shape.text,
    }
  }
  if (shape.type === 'rect' || shape.type === 'circle') {
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
  if (shape.type === 'rect' || shape.type === 'circle') {
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
  if (shape.type === 'rect' || shape.type === 'circle') {
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

  if ((s.type === 'rect' || s.type === 'circle') && handleId === 'n') {
    const bottom = s.y + s.h
    const top = pos.y
    s.y = Math.min(top, bottom)
    s.h = Math.abs(bottom - top)
    return
  }

  if ((s.type === 'rect' || s.type === 'circle') && handleId === 's') {
    const top = s.y
    const bottom = pos.y
    s.y = Math.min(top, bottom)
    s.h = Math.abs(bottom - top)
    return
  }

  if ((s.type === 'rect' || s.type === 'circle') && handleId === 'w') {
    const right = s.x + s.w
    const left = pos.x
    s.x = Math.min(left, right)
    s.w = Math.abs(right - left)
    return
  }

  if ((s.type === 'rect' || s.type === 'circle') && handleId === 'e') {
    const left = s.x
    const right = pos.x
    s.x = Math.min(left, right)
    s.w = Math.abs(right - left)
    return
  }

  if ((s.type === 'rect' || s.type === 'circle') && _dragAnchor) {
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

// ── Context menu ──────────────────────────────────────────────────────────────

const ctxMenu  = reactive({ visible: false, x: 0, y: 0, idx: -1 })
const ctxShape = computed(() =>
  ctxMenu.idx >= 0 && ctxMenu.idx < shapes.value.length ? shapes.value[ctxMenu.idx] : null
)

function onContextMenu(e) {
  closeCtxMenu()
  const pos = getPos(e)
  const hit = hitTest(pos.x, pos.y)
  if (hit < 0) return
  selectedIdx.value = hit
  ctxMenu.idx     = hit
  ctxMenu.x       = e.clientX
  ctxMenu.y       = e.clientY
  ctxMenu.visible = true
}

function closeCtxMenu() {
  ctxMenu.visible = false
}

function ctxDelete() {
  if (ctxMenu.idx === selectedIdx.value) selectedIdx.value = -1
  shapes.value.splice(ctxMenu.idx, 1)
  closeCtxMenu()
  scheduleRedraw()
}

function ctxSetProp(key, val) {
  if (ctxShape.value) {
    if (key === 'label' && !val) {
      delete ctxShape.value.label
      delete ctxShape.value.labelFontSize
    } else {
      ctxShape.value[key] = val
      if (key === 'label' && val && !ctxShape.value.labelFontSize) {
        ctxShape.value.labelFontSize = fontSize.value
      }
    }
    scheduleRedraw()
  }
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
  if (type === 'rect' || type === 'circle') {
    const box = forceSnap ? constrainBox(p1, p2) : {
      x: Math.min(p1.x, p2.x),
      y: Math.min(p1.y, p2.y),
      w: Math.abs(p2.x - p1.x),
      h: Math.abs(p2.y - p1.y),
    }
    return {
      ...base,
      ...box,
    }
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
  if (shape.type === 'rect' || shape.type === 'circle') {
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

function beginEditText(idx) {
  beginEditShapeText(idx)
}

function commitText() {
  if (!textEdit.active) return
  const text = textEdit.value.trim()
  if (textEdit.shapeIdx >= 0) {
    const s = shapes.value[textEdit.shapeIdx]
    if (s?.type === 'text') {
      if (text) {
        s.text = text
      } else {
        shapes.value.splice(textEdit.shapeIdx, 1)
        if (selectedIdx.value === textEdit.shapeIdx) selectedIdx.value = -1
        else if (selectedIdx.value > textEdit.shapeIdx) selectedIdx.value -= 1
      }
    } else if (s) {
      if (text) {
        s.label = text
        if (!s.labelFontSize) s.labelFontSize = fontSize.value
      } else {
        delete s.label
        delete s.labelFontSize
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
  }
  textEdit.shapeIdx = -1
  textEdit.angle = 0
  textEdit.active = false
  textEdit.value  = ''
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
  if (shapes.value.length) {
    shapes.value.pop()
    if (selectedIdx.value >= shapes.value.length) selectedIdx.value = -1
    scheduleRedraw()
  }
}

function clearAll() {
  cancelText()
  shapes.value = []
  selectedIdx.value = -1
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
  // White outline pass — always drawn first so color sits on top
  for (const shape of shapes.value) {
    if (shape === skipTextEdit) continue
    paint(ctx, shape, '#ffffff', 2)
    if (shape.label && !isEditingShapeLabel(shape)) {
      paintAttachedLabel(ctx, shape, '#ffffff')
    }
  }
  if (drawing.value) paint(ctx, drawing.value, '#ffffff', 2)
  for (const shape of shapes.value) {
    if (shape === skipTextEdit) continue
    paint(ctx, shape)
    if (shape.label && !isEditingShapeLabel(shape)) {
      paintAttachedLabel(ctx, shape)
    }
  }
  if (drawing.value) paint(ctx, drawing.value)
  const sel = selectedIdx.value
  if (sel >= 0 && sel < shapes.value.length && !drawing.value
      && (!textEdit.active || textEdit.shapeIdx !== sel)) {
    paintSelection(ctx, shapes.value[sel])
  }
}

function shapeBounds(shape) {
  if (shape.type === 'rect' || shape.type === 'circle') {
    return { x: shape.x, y: shape.y, w: shape.w, h: shape.h }
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
  ctx.save()
  ctx.setLineDash([5 / dScale.value, 4 / dScale.value])
  ctx.lineWidth = Math.max(1, 1.5 / dScale.value)
  ctx.strokeStyle = 'rgba(80, 190, 255, 0.95)'
  ctx.strokeRect(b.x, b.y, Math.max(1, b.w), Math.max(1, b.h))
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
  }

  ctx.restore()
}

// ── Export ────────────────────────────────────────────────────────────────────

async function copyToClipboard() {
  commitText()
  await nextTick()
  const canvas = canvasEl.value
  if (!canvas) return
  canvas.toBlob(async (blob) => {
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
    const canvas = canvasEl.value
    if (!canvas) return
    canvas.toBlob((blob) => {
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
  --se-radius:      16px;
  --se-radius-sm:   9px;
  --se-radius-xs:   6px;
  --se-ring:        0 0 0 3px color-mix(in srgb, var(--accent, #4f8bff) 30%, transparent);
}

/* ── Window ────────────────────────────────────────────────────────────────── */
.se-win {
  position: relative;
  display: flex;
  flex-direction: column;
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
}

/* Tool picker — segmented control */
.se-tools {
  display: flex;
  gap: 2px;
  padding: 3px;
  background: var(--se-surface-2);
  border: 1px solid var(--se-border-soft);
  border-radius: var(--se-radius-sm);
}

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

.se-tools .se-tbtn { height: 28px; }

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

.se-tbtn.action-btn {
  height: 32px;
  padding: 0 14px;
  font-weight: 600;
  background: color-mix(in srgb, var(--se-accent) 14%, transparent);
  border-color: color-mix(in srgb, var(--se-accent) 32%, transparent);
  color: color-mix(in srgb, var(--se-accent) 80%, var(--se-fg));
}

.se-tbtn.action-btn:hover {
  background: color-mix(in srgb, var(--se-accent) 22%, transparent);
  border-color: color-mix(in srgb, var(--se-accent) 46%, transparent);
  color: var(--se-fg);
}

.se-tbtn:focus-visible {
  outline: none;
  box-shadow: var(--se-ring);
}

.se-tbtn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

/* ── Separator / Spacer ────────────────────────────────────────────────────── */
.se-sep {
  width: 1px;
  height: 22px;
  background: var(--se-border-soft);
  margin: 0 4px;
  flex-shrink: 0;
}

.se-spacer {
  flex: 1;
}

/* ── Controls ──────────────────────────────────────────────────────────────── */
.se-ctl {
  display: inline-flex;
  flex-direction: row;
  align-items: center;
  gap: 7px;
  height: 32px;
  padding: 0 10px;
  background: var(--se-surface-2);
  border: 1px solid var(--se-border-soft);
  border-radius: var(--se-radius-sm);
  cursor: default;
  box-sizing: border-box;
}

.se-ctl-lbl {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.03em;
  text-transform: uppercase;
  color: var(--se-fg-dim);
  white-space: nowrap;
  line-height: 1;
}

.se-dash-ctl {
  cursor: pointer;
}

.se-dash-ctl input {
  margin: 0;
  cursor: pointer;
}

.se-color-ctl {
  position: relative;
}

.se-color-swatch {
  width: 22px;
  height: 22px;
  padding: 0;
  border: 2px solid color-mix(in srgb, #fff 30%, transparent);
  border-radius: var(--se-radius-xs);
  cursor: pointer;
  flex-shrink: 0;
  box-shadow: inset 0 0 0 1px color-mix(in srgb, #000 25%, transparent);
  transition: transform 0.1s ease, box-shadow 0.14s ease;
}

.se-color-swatch:hover {
  transform: scale(1.08);
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

.se-range {
  width: 92px;
  height: 4px;
  cursor: pointer;
  accent-color: var(--se-accent);
  margin: 0;
}

/* ── Close button ──────────────────────────────────────────────────────────── */
.se-close {
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--se-radius-xs);
  color: var(--se-fg-dim);
  font-size: 15px;
  cursor: pointer;
  line-height: 1;
  padding: 0;
  transition: background 0.14s ease, color 0.14s ease;
}

.se-close:hover {
  background: color-mix(in srgb, #e5484d 18%, transparent);
  color: #ff8a8a;
}

/* ── Canvas body ───────────────────────────────────────────────────────────── */
.se-body {
  flex: 1;
  overflow: auto;
  display: flex;
  align-items: center;
  justify-content: center;
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
  border: 1px dashed rgba(255, 255, 255, 0.55);
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
  bottom: 26px;
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

/* ── Context menu ─────────────────────────────────────────────────────────── */
.se-ctx-menu {
  position: fixed;
  z-index: 10100;
  background: color-mix(in srgb, var(--se-surface) 92%, transparent);
  backdrop-filter: blur(14px) saturate(1.2);
  -webkit-backdrop-filter: blur(14px) saturate(1.2);
  border: 1px solid var(--se-border-soft);
  border-radius: var(--se-radius-sm);
  box-shadow: 0 20px 48px -12px rgba(0, 0, 0, 0.6),
              0 0 0 1px color-mix(in srgb, #fff 5%, transparent);
  padding: 5px;
  min-width: 168px;
  user-select: none;
  font-size: 12px;
  animation: se-pop 0.13s ease;
}

.se-ctx-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 6px 10px;
  border-radius: var(--se-radius-xs);
  color: var(--se-fg);
  cursor: pointer;
  transition: background 0.1s ease;
}

.se-ctx-item:hover {
  background: color-mix(in srgb, var(--se-accent) 16%, transparent);
}

.se-ctx-delete {
  color: #ff8a8a;
}

.se-ctx-delete:hover {
  background: color-mix(in srgb, #e5484d 18%, transparent);
}

.se-ctx-sep {
  height: 1px;
  background: var(--se-border-soft);
  margin: 5px 4px;
}

.se-ctx-lbl {
  flex: 1;
  white-space: nowrap;
}

.se-ctx-color {
  width: 34px;
  height: 22px;
  padding: 1px 2px;
  border: 1px solid var(--se-border-soft);
  border-radius: var(--se-radius-xs);
  background: transparent;
  cursor: pointer;
}

.se-ctx-num,
.se-ctx-text {
  background: var(--se-surface-2);
  border: 1px solid var(--se-border-soft);
  border-radius: var(--se-radius-xs);
  color: var(--se-fg);
  padding: 4px 6px;
  font-size: 12px;
  transition: border-color 0.14s ease, box-shadow 0.14s ease;
}

.se-ctx-num { width: 52px; }
.se-ctx-text { width: 118px; }

.se-ctx-num:focus,
.se-ctx-text:focus,
.se-ctx-color:focus-visible {
  outline: none;
  border-color: var(--se-accent);
  box-shadow: var(--se-ring);
}
</style>
