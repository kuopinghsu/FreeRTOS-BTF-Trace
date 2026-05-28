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
              <svg viewBox="0 0 14 14" width="12" height="12" fill="none" stroke="currentColor"
                   stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="7" cy="7" r="5.5"/><path d="M7 4.5v5M4.5 7h5"/>
              </svg>
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
        >
          <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor"
               stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M4 3L1 6l3 3M1 6h9a4 4 0 0 1 0 8H7"/>
          </svg>
        </button>

        <!-- Clear all -->
        <button
          class="se-tbtn icon-btn"
          :disabled="!shapes.length"
          title="Clear all annotations"
          @click="clearAll"
        >
          <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor"
               stroke-width="1.5" stroke-linecap="round">
            <path d="M2 4h12M5.5 4V3a.5.5 0 0 1 .5-.5h2a.5.5 0 0 1 .5.5v1M4 4l.75 9.5h6.5L12 4"/>
          </svg>
        </button>

        <div class="se-sep" />

        <!-- Copy to clipboard -->
        <button class="se-tbtn action-btn" title="Copy annotated image to clipboard" @click="copyToClipboard">
          <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor"
               stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round">
            <rect x="5" y="2" width="9" height="9" rx="1"/>
            <path d="M5 5H3.5A1.5 1.5 0 0 0 2 6.5v7A1.5 1.5 0 0 0 3.5 15h7A1.5 1.5 0 0 0 12 13.5V12"/>
          </svg>
          Copy
        </button>

        <!-- Save PNG -->
        <button class="se-tbtn action-btn" title="Save annotated image as PNG" @click="saveAsPng">
          <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor"
               stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round">
            <path d="M8 1v9M4 6l4 4 4-4M2 13h12"/>
          </svg>
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

const props = defineProps({
  imageUrl: { type: String, required: true },
})

const emit = defineEmits(['close'])

// ── Tool definitions ──────────────────────────────────────────────────────────

const TOOLS = [
  {
    id: 'arrow', label: 'Arrow',
    icon: `<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M2 14L13 3M13 3H7M13 3V9"/></svg>`,
  },
  {
    id: 'line', label: 'Line',
    icon: `<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><line x1="2" y1="14" x2="14" y2="2"/></svg>`,
  },
  {
    id: 'dash', label: 'Dashed Line',
    icon: `<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-dasharray="3 2.5"><line x1="2" y1="14" x2="14" y2="2"/></svg>`,
  },
  {
    id: 'rect', label: 'Rectangle',
    icon: `<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.6"><rect x="2" y="3" width="12" height="9" rx="1"/></svg>`,
  },
  {
    id: 'circle', label: 'Circle / Ellipse',
    icon: `<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.6"><ellipse cx="8" cy="8" rx="6" ry="5"/></svg>`,
  },
  {
    id: 'text', label: 'Add Text (click to place)',
    icon: `<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M3 4h10M8 4v9M5 13h6"/></svg>`,
  },
]

const TOOL_CURSORS = {
  arrow: 'crosshair',
  line:  'crosshair',
  dash:  'crosshair',
  rect:  'crosshair',
  circle:'crosshair',
  text:  'text',
}

// ── Reactive state ────────────────────────────────────────────────────────────

const tool      = ref('arrow')
const color     = ref('#ff4444')
const lineWidth = ref(3)
const fontSize  = ref(20)

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

const imgNW  = ref(1)
const imgNH  = ref(1)
const imgEl  = ref(null)
const dScale = ref(1)

const overlayEl  = ref(null)
const bodyEl     = ref(null)
const canvasEl   = ref(null)
const textareaEl = ref(null)

const textEdit = reactive({
  active:  false,
  canvasX: 0,
  canvasY: 0,
  value:   '',
})

let _mouseDown   = false
let _startPos    = null
let _dragIdx     = -1
let _dragPrev    = null
let _rafId       = null
let _statusTimer = null

const hoverIdx = ref(-1)

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
  cursor:  (_dragIdx >= 0 || hoverIdx.value >= 0) && tool.value !== 'text'
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
  const fs = fontSize.value * s
  return {
    position:    'absolute',
    left:        `${Math.round(textEdit.canvasX * s)}px`,
    top:         `${Math.round(textEdit.canvasY * s)}px`,
    fontSize:    `${fs}px`,
    lineHeight:  '1.2',
    color:       color.value,
    fontFamily:  'sans-serif',
    fontWeight:  'bold',
    background:  'transparent',
    border:      '1px dashed rgba(255,255,255,0.55)',
    outline:     'none',
    resize:      'none',
    padding:     '0 2px',
    margin:      '0',
    minWidth:    '60px',
    maxWidth:    `${Math.max(60, (imgNW.value - textEdit.canvasX) * s)}px`,
    overflow:    'hidden',
    whiteSpace:  'nowrap',
    boxSizing:   'border-box',
    zIndex:      '1',
  }
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
    textEdit.canvasX = pos.x
    textEdit.canvasY = pos.y
    textEdit.value   = ''
    textEdit.active  = true
    nextTick(() => textareaEl.value?.focus())
    return
  }

  // Hit-test: drag an existing shape rather than drawing a new one
  const hit = hitTest(pos.x, pos.y)
  if (hit >= 0) {
    _dragIdx  = hit
    _dragPrev = pos
    return
  }

  _mouseDown = true
  _startPos  = pos
  drawing.value = buildShape(tool.value, pos, pos)
}

function onMouseMove(e) {
  const pos = getPos(e)

  if (_dragIdx >= 0 && _dragPrev) {
    moveShape(_dragIdx, pos.x - _dragPrev.x, pos.y - _dragPrev.y)
    _dragPrev = pos
    scheduleRedraw()
    return
  }

  if (_mouseDown && _startPos) {
    drawing.value = buildShape(tool.value, _startPos, pos)
    scheduleRedraw()
    return
  }

  // Hover: update cursor hint for draggable shapes
  if (tool.value !== 'text') {
    hoverIdx.value = hitTest(pos.x, pos.y)
  }
}

function onMouseUp(e) {
  if (_dragIdx >= 0) {
    _dragIdx  = -1
    _dragPrev = null
    scheduleRedraw()
    return
  }
  if (!_mouseDown) return
  _mouseDown = false
  if (drawing.value && _startPos) {
    const pos   = getPos(e)
    const shape = buildShape(tool.value, _startPos, pos)
    if (!isTrivial(shape)) shapes.value.push(shape)
    drawing.value = null
  }
  _startPos = null
  scheduleRedraw()
}

function onMouseLeave() {
  hoverIdx.value = -1
  if (_dragIdx >= 0) {
    _dragIdx  = -1
    _dragPrev = null
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
  ctxMenu.idx     = hit
  ctxMenu.x       = e.clientX
  ctxMenu.y       = e.clientY
  ctxMenu.visible = true
}

function closeCtxMenu() {
  ctxMenu.visible = false
}

function ctxDelete() {
  shapes.value.splice(ctxMenu.idx, 1)
  closeCtxMenu()
  scheduleRedraw()
}

function ctxSetProp(key, val) {
  if (ctxShape.value) {
    ctxShape.value[key] = val
    scheduleRedraw()
  }
}

function isTrivial(shape) {
  if ('x1' in shape) return Math.hypot(shape.x2 - shape.x1, shape.y2 - shape.y1) < 3
  if ('w'  in shape) return shape.w < 3 && shape.h < 3
  return false
}

function buildShape(type, p1, p2) {
  const base = { type, color: color.value, width: lineWidth.value }
  if (type === 'rect' || type === 'circle') {
    return {
      ...base,
      x: Math.min(p1.x, p2.x),
      y: Math.min(p1.y, p2.y),
      w: Math.abs(p2.x - p1.x),
      h: Math.abs(p2.y - p1.y),
    }
  }
  return { ...base, x1: p1.x, y1: p1.y, x2: p2.x, y2: p2.y }
}

// ── Text editing ──────────────────────────────────────────────────────────────

function commitText() {
  if (!textEdit.active) return
  const text = textEdit.value.trim()
  if (text) {
    shapes.value.push({
      type:     'text',
      color:    color.value,
      fontSize: fontSize.value,
      x:        textEdit.canvasX,
      y:        textEdit.canvasY,
      text,
    })
  }
  textEdit.active = false
  textEdit.value  = ''
  scheduleRedraw()
}

function cancelText() {
  textEdit.active = false
  textEdit.value  = ''
}

// ── Undo / Clear ──────────────────────────────────────────────────────────────

function undo() {
  if (textEdit.active) { cancelText(); return }
  if (shapes.value.length) {
    shapes.value.pop()
    scheduleRedraw()
  }
}

function clearAll() {
  cancelText()
  shapes.value = []
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
  // White outline pass — always drawn first so color sits on top
  for (const shape of shapes.value) paint(ctx, shape, '#ffffff', 2)
  if (drawing.value) paint(ctx, drawing.value, '#ffffff', 2)
  for (const shape of shapes.value) paint(ctx, shape)
  if (drawing.value) paint(ctx, drawing.value)
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

  if (type === 'line') {
    ctx.beginPath()
    ctx.moveTo(shape.x1, shape.y1)
    ctx.lineTo(shape.x2, shape.y2)
    ctx.stroke()

  } else if (type === 'dash') {
    ctx.setLineDash([shape.width * 4, shape.width * 3])
    ctx.beginPath()
    ctx.moveTo(shape.x1, shape.y1)
    ctx.lineTo(shape.x2, shape.y2)
    ctx.stroke()

  } else if (type === 'arrow') {
    const dx    = shape.x2 - shape.x1
    const dy    = shape.y2 - shape.y1
    const dist  = Math.hypot(dx, dy)
    if (dist < 2) { ctx.restore(); return }
    const angle = Math.atan2(dy, dx)
    const hl    = Math.max(shape.width * 5, 14)
    const ha    = Math.PI / 7
    // Line body (shortened so it doesn't overlap arrowhead)
    const tailX = shape.x2 - hl * 0.6 * Math.cos(angle)
    const tailY = shape.y2 - hl * 0.6 * Math.sin(angle)
    ctx.beginPath()
    ctx.moveTo(shape.x1, shape.y1)
    ctx.lineTo(tailX, tailY)
    ctx.stroke()
    // Filled arrowhead
    ctx.beginPath()
    ctx.moveTo(shape.x2, shape.y2)
    ctx.lineTo(shape.x2 - hl * Math.cos(angle - ha), shape.y2 - hl * Math.sin(angle - ha))
    ctx.lineTo(shape.x2 - hl * Math.cos(angle + ha), shape.y2 - hl * Math.sin(angle + ha))
    ctx.closePath()
    ctx.fill()
    // In outline pass, also stroke the triangle so the halo extends beyond its edges
    if (overrideColor !== null) ctx.stroke()

  } else if (type === 'rect') {
    ctx.strokeRect(shape.x, shape.y, shape.w, shape.h)

  } else if (type === 'circle') {
    if (shape.w < 1 && shape.h < 1) { ctx.restore(); return }
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
      if (blob) { triggerDownload(blob); showStatus('Saved as annotated-snapshot.png') }
    }, 'image/png')
  })
}

function triggerDownload(blob) {
  const url  = URL.createObjectURL(blob)
  const a    = document.createElement('a')
  a.href     = url
  a.download = 'annotated-snapshot.png'
  a.click()
  URL.revokeObjectURL(url)
}
</script>

<style scoped>
/* ── Overlay ───────────────────────────────────────────────────────────────── */
.se-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.78);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10000;
  backdrop-filter: blur(2px);
}

/* ── Window ────────────────────────────────────────────────────────────────── */
.se-win {
  position: relative;
  display: flex;
  flex-direction: column;
  background: #1a1a2e;
  border: 1px solid #3a3a60;
  border-radius: 10px;
  box-shadow: 0 24px 72px rgba(0, 0, 0, 0.75), 0 0 0 1px rgba(255,255,255,0.04);
  max-width: 97vw;
  max-height: 95vh;
  overflow: hidden;
  user-select: none;
}

/* ── Toolbar ───────────────────────────────────────────────────────────────── */
.se-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 3px;
  padding: 5px 8px;
  background: #13132a;
  border-bottom: 1px solid #3a3a60;
  flex-shrink: 0;
}

.se-tools {
  display: flex;
  gap: 2px;
}

/* ── Toolbar button ────────────────────────────────────────────────────────── */
.se-tbtn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 30px;
  padding: 0 8px;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 5px;
  color: #b0b0cc;
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
  line-height: 1;
  transition: background 0.12s, border-color 0.12s, color 0.12s;
  box-sizing: border-box;
}

.se-tbtn.icon-btn {
  padding: 0 5px;
}

.se-tbtn:hover:not(:disabled) {
  background: #262644;
  border-color: #4a4a80;
  color: #e0e0ff;
}

.se-tbtn.active {
  background: #1565c0;
  border-color: #42a5f5;
  color: #e3f2fd;
  box-shadow: 0 0 0 1px #1976d2 inset;
}

.se-tbtn.action-btn {
  background: #162040;
  border-color: #254880;
  color: #80baff;
}

.se-tbtn.action-btn:hover {
  background: #1e3060;
  border-color: #3a6aaa;
  color: #aad4ff;
}

.se-tbtn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

/* ── Separator / Spacer ────────────────────────────────────────────────────── */
.se-sep {
  width: 1px;
  height: 30px;
  background: #3a3a60;
  margin: 0 3px;
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
  gap: 5px;
  height: 30px;
  padding: 0 7px;
  border: 1px solid #3a3a60;
  border-radius: 5px;
  cursor: default;
  box-sizing: border-box;
}

.se-ctl-lbl {
  font-size: 10px;
  color: #6a6a99;
  white-space: nowrap;
  line-height: 1;
}

.se-color-ctl {
  position: relative;
}

.se-color-swatch {
  width: 20px;
  height: 20px;
  padding: 0;
  border: 2px solid #666;
  border-radius: 3px;
  cursor: pointer;
  flex-shrink: 0;
  transition: border-color 0.1s;
}

.se-color-swatch:hover {
  border-color: #aaa;
}

.se-color-panel {
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  z-index: 200;
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  padding: 8px;
  background: #1a1a36;
  border: 1px solid #3a3a60;
  border-radius: 6px;
  width: 163px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.55);
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
  outline: 1px solid rgba(255, 255, 255, 0.4);
  outline-offset: 1px;
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
  width: 80px;
  height: 4px;
  cursor: pointer;
  accent-color: #4a8acc;
  margin: 0;
}

/* ── Close button ──────────────────────────────────────────────────────────── */
.se-close {
  width: 26px;
  height: 26px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 5px;
  color: #7a7aaa;
  font-size: 14px;
  cursor: pointer;
  line-height: 1;
  padding: 0;
  transition: background 0.12s, border-color 0.12s, color 0.12s;
}

.se-close:hover {
  background: #5a1020;
  border-color: #902030;
  color: #ff8888;
}

/* ── Canvas body ───────────────────────────────────────────────────────────── */
.se-body {
  flex: 1;
  overflow: auto;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  min-height: 0;
  background: #0e0e1e;
  /* Checkerboard so transparency is visible */
  background-image:
    linear-gradient(45deg, #1a1a2a 25%, transparent 25%),
    linear-gradient(-45deg, #1a1a2a 25%, transparent 25%),
    linear-gradient(45deg, transparent 75%, #1a1a2a 75%),
    linear-gradient(-45deg, transparent 75%, #1a1a2a 75%);
  background-size: 20px 20px;
  background-position: 0 0, 0 10px, 10px -10px, -10px 0;
}

/* ── Canvas wrap ───────────────────────────────────────────────────────────── */
.se-canvas-wrap {
  box-shadow: 0 6px 28px rgba(0, 0, 0, 0.6), 0 0 0 1px rgba(255,255,255,0.06);
  border-radius: 1px;
}

.se-canvas-wrap canvas {
  display: block;
  border-radius: 1px;
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
  bottom: 22px;
  left: 50%;
  transform: translateX(-50%);
  background: rgba(14, 20, 40, 0.96);
  border: 1px solid #3a6aaa;
  border-radius: 6px;
  color: #80baff;
  font-size: 13px;
  padding: 7px 20px;
  pointer-events: none;
  white-space: nowrap;
  z-index: 200;
  box-shadow: 0 4px 18px rgba(0, 0, 0, 0.55);
}

.se-status.success {
  border-color: #2a8a50;
  color: #6adf9a;
}

.se-status.error {
  border-color: #8a2a2a;
  color: #ff8888;
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
  background: #1a1a2e;
  border: 1px solid #3a3a60;
  border-radius: 7px;
  box-shadow: 0 8px 28px rgba(0,0,0,0.7);
  padding: 4px 0;
  min-width: 160px;
  user-select: none;
  font-size: 12px;
}

.se-ctx-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 5px 12px;
  color: #c0c0e0;
  cursor: pointer;
  transition: background 0.1s;
}

.se-ctx-item:hover {
  background: #262644;
  color: #e0e0ff;
}

.se-ctx-delete {
  color: #ff7070;
}

.se-ctx-delete:hover {
  background: #3a1020;
  color: #ff9999;
}

.se-ctx-sep {
  height: 1px;
  background: #3a3a60;
  margin: 3px 0;
}

.se-ctx-lbl {
  flex: 1;
  white-space: nowrap;
}

.se-ctx-color {
  width: 32px;
  height: 20px;
  padding: 1px 2px;
  border: 1px solid #3a3a60;
  border-radius: 3px;
  background: transparent;
  cursor: pointer;
}

.se-ctx-num {
  width: 48px;
  background: #0e0e1e;
  border: 1px solid #3a3a60;
  border-radius: 3px;
  color: #c0c0e0;
  padding: 2px 4px;
  font-size: 12px;
}

.se-ctx-text {
  width: 110px;
  background: #0e0e1e;
  border: 1px solid #3a3a60;
  border-radius: 3px;
  color: #c0c0e0;
  padding: 2px 4px;
  font-size: 12px;
}
</style>
