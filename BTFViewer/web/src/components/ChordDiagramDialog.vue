<template>
  <div
    class="chord-overlay"
    @click.self="emit('close')"
  >
    <div
      class="chord-dialog"
      role="dialog"
      aria-modal="true"
      aria-label="Migration chord diagram"
    >
      <div class="chord-header">
        <span class="chord-title">Migration Chord Diagram</span>
        <button
          type="button"
          class="chord-close"
          @click="emit('close')"
        >
          Close
        </button>
      </div>
      <p class="chord-sub">
        {{ subtitle }}
      </p>
      <div
        v-if="traceHasBounces"
        class="chord-bounce-bar"
      >
        <button
          type="button"
          class="chord-bounce-toggle"
          :class="{ active: bounceOnly }"
          :title="bounceOnly ? 'Showing only migrations that occurred while a mutex was held across cores' : 'Showing all migrations'"
          @click="bounceOnly = !bounceOnly"
        >
          {{ bounceOnly ? 'Show: Lock-Bounce Only' : 'Show: All Migrations' }}
        </button>
      </div>
      <div
        v-if="!hasData"
        class="chord-empty"
      >
        No migrations in scope.
      </div>
      <div
        v-else
        ref="viewportRef"
        class="chord-viewport"
      >
        <canvas
          ref="canvasRef"
          class="chord-canvas"
          @mousemove="onCanvasMove"
          @mouseleave="onCanvasLeave"
        />
      </div>
      <!-- Always mounted (not v-if) so its reserved height never shifts the
           viewport size — the circle radius is derived from viewport height,
           so any layout jump here would visibly resize/flash the diagram. -->
      <p class="chord-cell-tip">
        {{ hoverTitle }}
      </p>
      <p class="chord-hint">
        Hover a core arc to highlight its migrations · chord width = migration count · color fades from source to destination core
      </p>
      <div
        v-if="hasData"
        class="chord-export-row"
      >
        <button
          type="button"
          class="chord-export-btn"
          @click="exportChordPng"
        >
          Export PNG
        </button>
        <button
          type="button"
          class="chord-export-btn"
          @click="exportChordSvg"
        >
          Export SVG
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { formatTime } from '../renderer/TimelineRenderer.js'
import { coreColor } from '../utils/colors.js'
import {
  coreShortName,
  migrationHeatmapMatrix,
  buildChordLayout,
  traceHasCoreBounceHolds,
} from '../utils/migrationAnalysis.js'
import { getPlacedCursors, getStatsRange } from '../utils/statsRange.js'

const ARC_THICKNESS = 14
const OUTER_PAD = 48

const props = defineProps({
  trace:   { type: Object, required: true },
  cursors: { type: Array, default: () => [] },
  /** Optional { fromCore, toCore, bounceOnly } from Core-Pair chart footer. */
  focusPair: { type: Object, default: null },
})

const emit = defineEmits(['close'])

const bounceOnly = ref(false)
const viewportRef = ref(null)
const canvasRef = ref(null)
const hoverCoreIndex = ref(null)
const pinnedHover = ref(false)
const focusLabel = ref('')
let _drawRaf = 0
let _resizeObserver = null

watch(() => props.trace, (t) => {
  bounceOnly.value = false
  pinnedHover.value = false
  focusLabel.value = ''
  if (t) t._lockBounceNs = undefined
})

const statsRange = computed(() => {
  const placed = getPlacedCursors(props.cursors)
  if (placed.length < 2) return null
  return getStatsRange(props.cursors, true)
})

const scopeSuffix = computed(() => {
  const r = statsRange.value
  if (!r) return ''
  return ` (C1–C${r.nCursors}: ${formatTime(r.lo, props.trace.timeScale)} … ${formatTime(r.hi, props.trace.timeScale)})`
})

const scopeLoHi = computed(() => {
  const r = statsRange.value
  return { lo: r?.lo ?? null, hi: r?.hi ?? null }
})

const traceHasBounces = computed(() => traceHasCoreBounceHolds(props.trace))

const matrix = computed(() => {
  const { lo, hi } = scopeLoHi.value
  return migrationHeatmapMatrix(props.trace, lo, hi, bounceOnly.value)
})

function applyFocusPair(focus) {
  if (!focus?.fromCore || !focus?.toCore) return
  bounceOnly.value = !!focus.bounceOnly
  focusLabel.value = `${coreShortName(focus.fromCore)}→${coreShortName(focus.toCore)}`
  const cores = matrix.value?.cores || []
  const fi = cores.indexOf(focus.fromCore)
  if (fi < 0) return
  pinnedHover.value = true
  hoverCoreIndex.value = fi
}

watch(() => props.focusPair, (focus) => {
  if (focus) applyFocusPair(focus)
})

const chordLayout = computed(() => buildChordLayout(matrix.value.cores, matrix.value.grid))

const maxChordCount = computed(() => {
  let m = 0
  const { cores, grid } = matrix.value
  for (let i = 0; i < cores.length; i++) {
    for (let j = 0; j < cores.length; j++) {
      if (i === j) continue
      if ((grid[i]?.[j] || 0) > m) m = grid[i][j]
    }
  }
  return m
})

const hasData = computed(() => {
  const { cores, grid } = matrix.value
  for (let i = 0; i < cores.length; i++) {
    for (let j = 0; j < cores.length; j++) {
      if (i !== j && (grid[i]?.[j] || 0) > 0) return true
    }
  }
  return false
})

const subtitle = computed(() => {
  const n = matrix.value.cores.length
  const focus = focusLabel.value ? ` · focused ${focusLabel.value}` : ''
  return `Core-to-core migration volume as directional chords (${n} cores)${focus}${scopeSuffix.value}`
})

const hoverTitle = computed(() => {
  const i = hoverCoreIndex.value
  if (i == null) return ''
  const { cores, grid } = matrix.value
  const core = cores[i]
  if (!core) return ''
  let out = 0
  let into = 0
  const parts = []
  for (let j = 0; j < cores.length; j++) {
    if (j === i) continue
    const o = grid[i]?.[j] || 0
    const inn = grid[j]?.[i] || 0
    out += o
    into += inn
    if (o) parts.push(`${coreShortName(core)}→${coreShortName(cores[j])}: ${o}`)
    if (inn) parts.push(`${coreShortName(cores[j])}→${coreShortName(core)}: ${inn}`)
  }
  const summary = `${coreShortName(core)} · ${out} out / ${into} in`
  return parts.length ? `${summary} · ${parts.join(' · ')}` : summary
})

function scheduleDraw() {
  if (_drawRaf) return
  _drawRaf = requestAnimationFrame(() => {
    _drawRaf = 0
    drawChord()
  })
}

function geometry(viewW, viewH) {
  const cx = viewW / 2
  const cy = viewH / 2
  const radius = Math.max(20, Math.min(viewW, viewH) / 2 - OUTER_PAD)
  return { cx, cy, radius }
}

function pointAt(cx, cy, angle, r) {
  return { x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle) }
}

function paintChord(ctx, viewW, viewH, labelColor) {
  ctx.clearRect(0, 0, viewW, viewH)
  const { cores, grid } = matrix.value
  if (!cores.length) return
  const layout = chordLayout.value
  const { cx, cy, radius: R } = geometry(viewW, viewH)
  const inner = R - ARC_THICKNESS / 2 - 2
  const maxCount = maxChordCount.value || 1
  const hovered = hoverCoreIndex.value

  ctx.lineCap = 'round'
  for (let i = 0; i < cores.length; i++) {
    for (let j = 0; j < cores.length; j++) {
      if (i === j) continue
      const count = grid[i]?.[j] || 0
      if (!count) continue
      const bidir = (grid[j]?.[i] || 0) > 0
      const p1 = pointAt(cx, cy, layout.tickAngle(i, j), inner)
      const p2 = pointAt(cx, cy, layout.tickAngle(j, i), inner)
      const mx = (p1.x + p2.x) / 2
      const my = (p1.y + p2.y) / 2
      let vx = mx - cx
      let vy = my - cy
      const vlen = Math.hypot(vx, vy) || 1
      vx /= vlen
      vy /= vlen
      const perpX = -vy
      const perpY = vx
      const sign = i < j ? 1 : -1
      const bidirOffset = bidir ? 6 * sign : 0
      const pull = 0.18
      const ctrlX = cx + vx * inner * pull + perpX * bidirOffset
      const ctrlY = cy + vy * inner * pull + perpY * bidirOffset

      const isDim = hovered != null && hovered !== i && hovered !== j
      const width = Math.max(1, Math.min(12, 1 + 10 * (count / maxCount)))
      const grad = ctx.createLinearGradient(p1.x, p1.y, p2.x, p2.y)
      grad.addColorStop(0, coreColor(cores[i]))
      grad.addColorStop(1, coreColor(cores[j]))

      ctx.beginPath()
      ctx.moveTo(p1.x, p1.y)
      ctx.quadraticCurveTo(ctrlX, ctrlY, p2.x, p2.y)
      ctx.strokeStyle = grad
      ctx.globalAlpha = isDim ? 0.08 : 0.75
      ctx.lineWidth = width
      ctx.stroke()
    }
  }
  ctx.globalAlpha = 1

  for (const arc of layout.arcs) {
    const isHover = hovered === arc.index
    ctx.beginPath()
    ctx.arc(cx, cy, R, arc.startAngle, arc.endAngle)
    ctx.lineWidth = ARC_THICKNESS
    ctx.strokeStyle = coreColor(arc.core)
    ctx.globalAlpha = hovered == null || isHover ? 1 : 0.35
    ctx.stroke()
    ctx.globalAlpha = 1

    const mid = (arc.startAngle + arc.endAngle) / 2
    const lp = pointAt(cx, cy, mid, R + ARC_THICKNESS / 2 + 14)
    ctx.fillStyle = labelColor
    ctx.font = isHover ? 'bold 12px monospace' : '11px monospace'
    ctx.textBaseline = 'middle'
    const cosMid = Math.cos(mid)
    ctx.textAlign = cosMid > 0.15 ? 'left' : cosMid < -0.15 ? 'right' : 'center'
    ctx.fillText(coreShortName(arc.core), lp.x, lp.y)
  }
}

function drawChord() {
  const canvas = canvasRef.value
  const viewport = viewportRef.value
  if (!canvas || !viewport) return
  const viewW = viewport.clientWidth
  const viewH = viewport.clientHeight
  if (viewW < 1 || viewH < 1) return

  const dpr = window.devicePixelRatio || 1
  canvas.width = Math.max(1, Math.floor(viewW * dpr))
  canvas.height = Math.max(1, Math.floor(viewH * dpr))
  canvas.style.width = `${viewW}px`
  canvas.style.height = `${viewH}px`

  const ctx = canvas.getContext('2d')
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  const labelColor = getComputedStyle(viewport).getPropertyValue('--fg-dim').trim() || '#888888'
  paintChord(ctx, viewW, viewH, labelColor)
}

function onCanvasMove(ev) {
  const canvas = canvasRef.value
  const viewport = viewportRef.value
  if (!canvas || !viewport) return
  const rect = canvas.getBoundingClientRect()
  const mx = ev.clientX - rect.left
  const my = ev.clientY - rect.top
  const { cx, cy, radius: R } = geometry(viewport.clientWidth, viewport.clientHeight)
  const dx = mx - cx
  const dy = my - cy
  const dist = Math.hypot(dx, dy)
  if (dist < R - ARC_THICKNESS / 2 - 4 || dist > R + ARC_THICKNESS / 2 + 4) {
    if (!pinnedHover.value) hoverCoreIndex.value = null
    return
  }
  const angle = Math.atan2(dy, dx)
  let found = null
  for (const arc of chordLayout.value.arcs) {
    let a = angle
    while (a < arc.startAngle) a += 2 * Math.PI
    while (a > arc.startAngle + 2 * Math.PI) a -= 2 * Math.PI
    if (a <= arc.endAngle) {
      found = arc.index
      break
    }
  }
  hoverCoreIndex.value = found
  if (found != null) pinnedHover.value = false
}

function onCanvasLeave() {
  if (!pinnedHover.value) hoverCoreIndex.value = null
}

function _exportStamp() {
  const d = new Date()
  const pad = n => String(n).padStart(2, '0')
  return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`
}

function _xmlEsc(v) {
  return String(v ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function _downloadBlob(filename, blob) {
  if (!blob) return
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

function _downloadText(filename, text, mime) {
  const blob = new Blob([text], { type: mime })
  _downloadBlob(filename, blob)
}

function exportChordPng() {
  const canvas = canvasRef.value
  if (!canvas || !hasData.value) return
  canvas.toBlob(blob => {
    _downloadBlob(`migration-chord-${_exportStamp()}.png`, blob)
  }, 'image/png')
}

function exportChordSvg() {
  const viewport = viewportRef.value
  if (!viewport || !hasData.value) return
  const viewW = viewport.clientWidth
  const viewH = viewport.clientHeight
  if (viewW < 1 || viewH < 1) return

  const { cores, grid } = matrix.value
  const layout = chordLayout.value
  const { cx, cy, radius: R } = geometry(viewW, viewH)
  const inner = R - ARC_THICKNESS / 2 - 2
  const maxCount = maxChordCount.value || 1
  const bg = getComputedStyle(viewport).getPropertyValue('--bg').trim() || '#1e1e1e'
  const labelColor = getComputedStyle(viewport).getPropertyValue('--fg-dim').trim() || '#888888'

  const defs = []
  const chordPaths = []
  for (let i = 0; i < cores.length; i++) {
    for (let j = 0; j < cores.length; j++) {
      if (i === j) continue
      const count = grid[i]?.[j] || 0
      if (!count) continue
      const bidir = (grid[j]?.[i] || 0) > 0
      const p1 = pointAt(cx, cy, layout.tickAngle(i, j), inner)
      const p2 = pointAt(cx, cy, layout.tickAngle(j, i), inner)
      const mx = (p1.x + p2.x) / 2
      const my = (p1.y + p2.y) / 2
      let vx = mx - cx
      let vy = my - cy
      const vlen = Math.hypot(vx, vy) || 1
      vx /= vlen
      vy /= vlen
      const perpX = -vy
      const perpY = vx
      const sign = i < j ? 1 : -1
      const bidirOffset = bidir ? 6 * sign : 0
      const pull = 0.18
      const ctrlX = cx + vx * inner * pull + perpX * bidirOffset
      const ctrlY = cy + vy * inner * pull + perpY * bidirOffset
      const width = Math.max(1, Math.min(12, 1 + 10 * (count / maxCount)))
      const gid = `chord-grad-${i}-${j}`
      defs.push(
        `<linearGradient id="${gid}" gradientUnits="userSpaceOnUse" x1="${p1.x}" y1="${p1.y}" x2="${p2.x}" y2="${p2.y}">`
        + `<stop offset="0" stop-color="${_xmlEsc(coreColor(cores[i]))}"/>`
        + `<stop offset="1" stop-color="${_xmlEsc(coreColor(cores[j]))}"/>`
        + '</linearGradient>',
      )
      chordPaths.push(
        `<path d="M ${p1.x} ${p1.y} Q ${ctrlX} ${ctrlY} ${p2.x} ${p2.y}" `
        + `stroke="url(#${gid})" stroke-width="${width}" stroke-opacity="0.75" `
        + 'fill="none" stroke-linecap="round"/>',
      )
    }
  }

  const arcParts = []
  for (const arc of layout.arcs) {
    const p1 = pointAt(cx, cy, arc.startAngle, R)
    const p2 = pointAt(cx, cy, arc.endAngle, R)
    const largeArc = (arc.endAngle - arc.startAngle) > Math.PI ? 1 : 0
    arcParts.push(
      `<path d="M ${p1.x} ${p1.y} A ${R} ${R} 0 ${largeArc} 1 ${p2.x} ${p2.y}" `
      + `stroke="${_xmlEsc(coreColor(arc.core))}" stroke-width="${ARC_THICKNESS}" `
      + 'stroke-opacity="1" fill="none" stroke-linecap="round"/>',
    )
    const mid = (arc.startAngle + arc.endAngle) / 2
    const lp = pointAt(cx, cy, mid, R + ARC_THICKNESS / 2 + 14)
    const cosMid = Math.cos(mid)
    const anchor = cosMid > 0.15 ? 'start' : cosMid < -0.15 ? 'end' : 'middle'
    arcParts.push(
      `<text x="${lp.x}" y="${lp.y}" fill="${_xmlEsc(labelColor)}" font-family="monospace" `
      + `font-size="11" text-anchor="${anchor}" dominant-baseline="middle">${_xmlEsc(coreShortName(arc.core))}</text>`,
    )
  }

  const parts = [
    `<svg xmlns="http://www.w3.org/2000/svg" width="${viewW}" height="${viewH}" viewBox="0 0 ${viewW} ${viewH}">`,
    `<title>${_xmlEsc(subtitle.value)}</title>`,
    `<rect width="100%" height="100%" fill="${_xmlEsc(bg)}"/>`,
    '<defs>', ...defs, '</defs>',
    ...chordPaths,
    ...arcParts,
    '</svg>',
  ]
  _downloadText(`migration-chord-${_exportStamp()}.svg`, parts.join('\n'), 'image/svg+xml;charset=utf-8')
}

watch([matrix, hoverCoreIndex], () => {
  nextTick(() => scheduleDraw())
})

watch(hasData, (ready) => {
  if (ready) nextTick(() => scheduleDraw())
})

onMounted(() => {
  if (props.focusPair) applyFocusPair(props.focusPair)
  nextTick(() => {
    scheduleDraw()
    const el = viewportRef.value
    if (el && typeof ResizeObserver !== 'undefined') {
      _resizeObserver = new ResizeObserver(() => scheduleDraw())
      _resizeObserver.observe(el)
    }
  })
  window.addEventListener('resize', scheduleDraw)
})

onBeforeUnmount(() => {
  if (_drawRaf) cancelAnimationFrame(_drawRaf)
  window.removeEventListener('resize', scheduleDraw)
  _resizeObserver?.disconnect()
})
</script>

<style scoped>
.chord-overlay {
  position: fixed;
  inset: 0;
  z-index: 2000;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}
.chord-dialog {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  /* Fixed (not shrink-to-fit) width: .chord-cell-tip is white-space:nowrap,
     so an auto/max-width-only box would grow to fit its longest hover text
     and visibly resize/flash the diagram whenever the hover title changes. */
  width: clamp(420px, 92vw, 720px);
  height: 85vh;
  max-height: 85vh;
  min-height: 320px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  padding: 12px 14px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.35);
}
.chord-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-shrink: 0;
}
.chord-title {
  font-weight: 600;
  font-size: 14px;
  flex: 1;
}
.chord-close {
  border: 1px solid var(--border);
  background: var(--tb-bg);
  color: var(--fg);
  border-radius: 4px;
  padding: 4px 10px;
  cursor: pointer;
  font-size: 12px;
  flex-shrink: 0;
}
.chord-sub {
  margin: 8px 0 6px;
  font-size: 12px;
  color: var(--fg-dim);
  flex-shrink: 0;
}
.chord-empty {
  padding: 24px 0;
  text-align: center;
  color: var(--fg-dim);
  font-size: 13px;
  flex-shrink: 0;
}
.chord-viewport {
  flex: 1 1 0;
  min-height: 0;
  position: relative;
}
.chord-canvas {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
}
.chord-cell-tip {
  margin: 4px 0 0;
  font-size: 11px;
  line-height: 15px;
  height: 15px;
  color: var(--fg-dim);
  flex-shrink: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.chord-hint {
  margin: 8px 0 0;
  font-size: 11px;
  color: var(--fg-dim);
  flex-shrink: 0;
}
.chord-export-row {
  display: flex;
  gap: 8px;
  margin-top: 8px;
  flex-shrink: 0;
}
.chord-export-btn {
  border: 1px solid var(--border);
  background: var(--tb-bg);
  color: var(--fg);
  border-radius: 4px;
  padding: 4px 10px;
  cursor: pointer;
  font-size: 12px;
}
.chord-export-btn:hover {
  border-color: var(--accent);
}
.chord-bounce-bar {
  display: flex;
  align-items: center;
  margin: 6px 0 2px;
  flex-shrink: 0;
}
.chord-bounce-toggle {
  border: 1px solid var(--border);
  background: var(--tb-bg);
  color: var(--fg-dim);
  border-radius: 4px;
  padding: 3px 10px;
  cursor: pointer;
  font-size: 12px;
  transition: border-color 0.12s, color 0.12s, background 0.12s;
}
.chord-bounce-toggle:hover {
  border-color: var(--accent);
  color: var(--fg);
}
.chord-bounce-toggle.active {
  border-color: #e8a020;
  background: rgba(232, 160, 32, 0.12);
  color: #e8a020;
  font-weight: 600;
}
</style>
