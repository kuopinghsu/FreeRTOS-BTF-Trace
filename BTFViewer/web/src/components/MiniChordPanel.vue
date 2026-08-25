<template>
  <div
    ref="wrapRef"
    class="mini-chord"
    :class="{ matrix: viewMode === 'matrix' }"
  >
    <div class="mini-chord-view-toggle">
      <button
        type="button"
        :class="{ active: viewMode === 'circle' }"
        title="Circular topology"
        :aria-pressed="viewMode === 'circle'"
        :disabled="cores.length > MATRIX_CORE_LIMIT"
        @click="setViewMode('circle')"
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
            :d="IC.chord"
          />
        </svg>
      </button>
      <button
        type="button"
        :class="{ active: viewMode === 'matrix' }"
        title="Core-to-core matrix"
        :aria-pressed="viewMode === 'matrix'"
        @click="setViewMode('matrix')"
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
            :d="IC.heatmap"
          />
        </svg>
      </button>
    </div>
    <canvas
      ref="canvasRef"
      class="mini-chord-canvas"
      @mousemove="onMove"
      @mouseleave="onLeave"
      @click="onClick"
      @dblclick="onDblClick"
    />
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { coreColor } from '../utils/colors.js'
import { IC } from '../utils/toolbarIcons.js'
import {
  buildChordLayout,
  buildTaperedRibbonPath,
  chordHitRing,
  chordPointAt,
  chordRingGeometry,
  distToQuadraticBezier,
  coreShortName,
  chordLabelStep,
  chordLabelVisible,
  CHORD_ARC_INNER,
  CHORD_ARC_OUTER,
  CHORD_GRAD_SOURCE_STOP,
} from '../utils/migrationAnalysis.js'

const OUTER_PAD = 36
const MATRIX_CORE_LIMIT = 16
const MATRIX_PAD_L = 36
const MATRIX_PAD_T = 64

const props = defineProps({
  cores: { type: Array, default: () => [] },
  grid: { type: Array, default: () => [] },
  /** Focused corridor { fromCore, toCore } or null */
  focusCorridor: { type: Object, default: null },
  /** Locked core indices [i] or [i,j] for pair isolate */
  focusCores: { type: Array, default: () => [] },
  /** 'all' | 'egress' | 'ingress' */
  directionMode: { type: String, default: 'all' },
})

const emit = defineEmits([
  'select-core',
  'select-pair',
  'select-corridor',
  'spotlight-corridor',
  'hover-info',
])

const wrapRef = ref(null)
const canvasRef = ref(null)
const viewMode = ref('circle')
const hoverCore = ref(null)
const hoverSide = ref(null) // 'egress' | 'ingress' | null
const hoverCorridor = ref(null) // { i, j }
let _drawRaf = 0
let _ro = null

const layout = computed(() => buildChordLayout(props.cores, props.grid))

const maxCount = computed(() => {
  let m = 0
  const g = props.grid
  for (let i = 0; i < props.cores.length; i++) {
    for (let j = 0; j < props.cores.length; j++) {
      if (i !== j && (g[i]?.[j] || 0) > m) m = g[i][j]
    }
  }
  return m || 1
})

function scheduleDraw() {
  if (_drawRaf) return
  _drawRaf = requestAnimationFrame(() => {
    _drawRaf = 0
    draw()
  })
}

function geometry(w, h) {
  const cx = w / 2
  const cy = h / 2
  const radius = Math.max(16, Math.min(w, h) / 2 - OUTER_PAD)
  return { cx, cy, radius }
}

function isDim(i, j) {
  const fc = props.focusCores
  const corr = props.focusCorridor
  if (corr?.fromCore && corr?.toCore) {
    const fi = props.cores.indexOf(corr.fromCore)
    const ti = props.cores.indexOf(corr.toCore)
    return !(i === fi && j === ti)
  }
  if (fc?.length === 1) {
    return i !== fc[0] && j !== fc[0]
  }
  if (fc?.length === 2) {
    const [a, b] = fc
    const ok = (i === a && j === b) || (i === b && j === a)
    return !ok
  }
  const h = hoverCore.value
  if (h != null) {
    if (hoverSide.value === 'egress') return i !== h
    if (hoverSide.value === 'ingress') return j !== h
    return i !== h && j !== h
  }
  return false
}

function paintCircle(ctx, w, h, labelColor) {
  const { cores, grid } = props
  if (!cores.length) return
  const lay = layout.value
  const { cx, cy, radius: R } = geometry(w, h)
  const { rEgress, rIngress, rRibbon } = chordRingGeometry(R)
  const maxC = maxCount.value

  for (let i = 0; i < cores.length; i++) {
    for (let j = 0; j < cores.length; j++) {
      if (i === j) continue
      const count = grid[i]?.[j] || 0
      if (!count) continue
      if (props.directionMode === 'egress' && props.focusCores?.[0] != null && i !== props.focusCores[0]) continue
      if (props.directionMode === 'ingress' && props.focusCores?.[0] != null && j !== props.focusCores[0]) continue

      const bidir = (grid[j]?.[i] || 0) > 0
      const a0 = lay.egressTickAngle(i, j)
      const a1 = lay.ingressTickAngle(j, i)
      const { srcHalf, dstHalf } = lay.ribbonHalfWidths(i, j, maxC)
      const sign = i < j ? 1 : -1
      const bidirOffset = bidir ? 5 * sign : 0
      const ribbon = buildTaperedRibbonPath(cx, cy, rRibbon, a0, a1, srcHalf, dstHalf, bidirOffset)
      const dim = isDim(i, j)
      const hot = hoverCorridor.value?.i === i && hoverCorridor.value?.j === j

      const grad = ctx.createLinearGradient(ribbon.p1.x, ribbon.p1.y, ribbon.p2.x, ribbon.p2.y)
      grad.addColorStop(0, coreColor(cores[i]))
      grad.addColorStop(CHORD_GRAD_SOURCE_STOP, coreColor(cores[i]))
      grad.addColorStop(1, coreColor(cores[j]))

      const path = new Path2D(ribbon.d)
      ctx.globalAlpha = dim ? 0.05 : hot ? 0.95 : 0.72
      ctx.fillStyle = grad
      ctx.fill(path)
    }
  }
  ctx.globalAlpha = 1

  const extra = new Set(props.focusCores || [])
  if (hoverCore.value != null) extra.add(hoverCore.value)
  if (props.focusCorridor?.fromCore) {
    const fi = cores.indexOf(props.focusCorridor.fromCore)
    const ti = cores.indexOf(props.focusCorridor.toCore)
    if (fi >= 0) extra.add(fi)
    if (ti >= 0) extra.add(ti)
  }
  if (hoverCorridor.value) {
    extra.add(hoverCorridor.value.i)
    extra.add(hoverCorridor.value.j)
  }
  const labelStep = chordLabelStep(cores.length, 16, 2 * Math.PI * Math.max(R, 1))

  for (const arc of lay.arcs) {
    const focused = props.focusCores?.includes(arc.index)
      || hoverCore.value === arc.index
      || (props.focusCorridor
        && (props.cores[arc.index] === props.focusCorridor.fromCore
          || props.cores[arc.index] === props.focusCorridor.toCore))
    const dimArc = (props.focusCores?.length || hoverCore.value != null || props.focusCorridor)
      && !focused

    // Outer = egress
    ctx.beginPath()
    ctx.arc(cx, cy, rEgress, arc.startAngle, arc.endAngle)
    ctx.lineWidth = CHORD_ARC_OUTER
    ctx.strokeStyle = coreColor(arc.core)
    ctx.globalAlpha = dimArc ? 0.25 : (hoverSide.value === 'ingress' && hoverCore.value === arc.index ? 0.35 : 1)
    ctx.stroke()

    // Inner = ingress
    ctx.beginPath()
    ctx.arc(cx, cy, rIngress, arc.startAngle, arc.endAngle)
    ctx.lineWidth = CHORD_ARC_INNER
    ctx.strokeStyle = coreColor(arc.core)
    ctx.globalAlpha = dimArc ? 0.25 : (hoverSide.value === 'egress' && hoverCore.value === arc.index ? 0.35 : 0.85)
    ctx.stroke()
    ctx.globalAlpha = 1

    if (!chordLabelVisible(arc.index, labelStep, extra)) continue
    const mid = (arc.startAngle + arc.endAngle) / 2
    const lp = chordPointAt(cx, cy, mid, rEgress + CHORD_ARC_OUTER / 2 + 12)
    ctx.fillStyle = labelColor
    ctx.font = focused ? 'bold 11px monospace' : '10px monospace'
    ctx.textBaseline = 'middle'
    const cosMid = Math.cos(mid)
    ctx.textAlign = cosMid > 0.15 ? 'left' : cosMid < -0.15 ? 'right' : 'center'
    ctx.fillText(coreShortName(arc.core), lp.x, lp.y)
  }
}

function paintMatrix(ctx, w, h, labelColor) {
  const { cores, grid } = props
  const n = cores.length
  if (!n) return
  const padL = MATRIX_PAD_L
  const padT = MATRIX_PAD_T
  const cell = Math.max(4, Math.min((w - padL - 8) / n, (h - padT - 8) / n))
  const maxC = maxCount.value
  ctx.font = '9px monospace'
  ctx.fillStyle = labelColor
  const extra = new Set(props.focusCores || [])
  if (hoverCore.value != null) extra.add(hoverCore.value)
  if (props.focusCorridor?.fromCore) {
    const fi = cores.indexOf(props.focusCorridor.fromCore)
    const ti = cores.indexOf(props.focusCorridor.toCore)
    if (fi >= 0) extra.add(fi)
    if (ti >= 0) extra.add(ti)
  }
  if (hoverCorridor.value) {
    extra.add(hoverCorridor.value.i)
    extra.add(hoverCorridor.value.j)
  }
  const step = chordLabelStep(n, 14, n * cell)
  for (let i = 0; i < n; i++) {
    if (!chordLabelVisible(i, step, extra)) continue
    ctx.textAlign = 'right'
    ctx.fillText(coreShortName(cores[i]), padL - 4, padT + i * cell + cell * 0.7)
    ctx.save()
    ctx.translate(padL + i * cell + cell / 2, padT - 4)
    ctx.rotate(-Math.PI / 4)
    ctx.textAlign = 'left'
    ctx.fillText(coreShortName(cores[i]), 0, 0)
    ctx.restore()
  }
  for (let i = 0; i < n; i++) {
    for (let j = 0; j < n; j++) {
      const v = i === j ? 0 : (grid[i]?.[j] || 0)
      const x = padL + j * cell
      const y = padT + i * cell
      const dim = isDim(i, j)
      if (!v) {
        ctx.globalAlpha = 0.15
        ctx.fillStyle = '#444'
      } else {
        ctx.globalAlpha = dim ? 0.08 : 0.9
        ctx.fillStyle = coreColor(cores[i])
        ctx.globalAlpha *= Math.min(1, 0.25 + 0.75 * (v / maxC))
      }
      ctx.fillRect(x, y, cell - 1, cell - 1)
    }
  }
  ctx.globalAlpha = 1
}

function draw() {
  const canvas = canvasRef.value
  const wrap = wrapRef.value
  if (!canvas || !wrap) return
  const w = wrap.clientWidth
  const h = wrap.clientHeight
  if (w < 1 || h < 1) return
  const dpr = window.devicePixelRatio || 1
  canvas.width = Math.max(1, Math.floor(w * dpr))
  canvas.height = Math.max(1, Math.floor(h * dpr))
  canvas.style.width = `${w}px`
  canvas.style.height = `${h}px`
  const ctx = canvas.getContext('2d')
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.clearRect(0, 0, w, h)
  const labelColor = getComputedStyle(wrap).getPropertyValue('--fg-dim').trim() || '#888'
  if (viewMode.value === 'matrix') paintMatrix(ctx, w, h, labelColor)
  else paintCircle(ctx, w, h, labelColor)
}

function hitTest(mx, my) {
  const wrap = wrapRef.value
  if (!wrap || viewMode.value === 'matrix') return null
  const { cx, cy, radius: R } = geometry(wrap.clientWidth, wrap.clientHeight)
  const dx = mx - cx
  const dy = my - cy
  const dist = Math.hypot(dx, dy)
  const side = chordHitRing(dist, R)
  if (!side) return null
  const angle = Math.atan2(dy, dx)
  for (const arc of layout.value.arcs) {
    let a = angle
    while (a < arc.startAngle) a += 2 * Math.PI
    while (a > arc.startAngle + 2 * Math.PI) a -= 2 * Math.PI
    if (a <= arc.endAngle) return { index: arc.index, side }
  }
  return null
}

function matrixHit(mx, my) {
  const wrap = wrapRef.value
  if (!wrap || viewMode.value !== 'matrix') return null
  const { cores, grid } = props
  const n = cores.length
  if (!n) return null
  const w = wrap.clientWidth
  const h = wrap.clientHeight
  const padL = MATRIX_PAD_L
  const padT = MATRIX_PAD_T
  const cell = Math.max(4, Math.min((w - padL - 8) / n, (h - padT - 8) / n))
  const j = Math.floor((mx - padL) / cell)
  const i = Math.floor((my - padT) / cell)
  if (i < 0 || j < 0 || i >= n || j >= n || i === j) return null
  if (!(grid[i]?.[j])) return null
  return { i, j }
}

function corridorNear(mx, my) {
  const wrap = wrapRef.value
  if (!wrap) return null
  if (viewMode.value === 'matrix') return matrixHit(mx, my)
  const { cores, grid } = props
  const lay = layout.value
  const { cx, cy, radius: R } = geometry(wrap.clientWidth, wrap.clientHeight)
  const { rRibbon } = chordRingGeometry(R)
  let best = null
  let bestD = Infinity
  const maxC = maxCount.value || 1
  for (let i = 0; i < cores.length; i++) {
    for (let j = 0; j < cores.length; j++) {
      if (i === j || !(grid[i]?.[j])) continue
      const a0 = lay.egressTickAngle(i, j)
      const a1 = lay.ingressTickAngle(j, i)
      const { srcHalf, dstHalf } = lay.ribbonHalfWidths(i, j, maxC)
      const bidir = (grid[j]?.[i] || 0) > 0
      const sign = i < j ? 1 : -1
      const ribbon = buildTaperedRibbonPath(
        cx, cy, rRibbon, a0, a1, srcHalf, dstHalf, bidir ? 6 * sign : 0,
      )
      const d = distToQuadraticBezier(mx, my, ribbon.p1, ribbon.ctrl, ribbon.p2)
      const thresh = Math.max(srcHalf, dstHalf, 4) + 8
      if (d > thresh) continue
      if (d < bestD) {
        bestD = d
        best = { i, j }
      }
    }
  }
  return best
}

function onMove(ev) {
  const canvas = canvasRef.value
  if (!canvas) return
  const rect = canvas.getBoundingClientRect()
  const mx = ev.clientX - rect.left
  const my = ev.clientY - rect.top
  const hit = hitTest(mx, my)
  const corr = corridorNear(mx, my)
  hoverCore.value = hit?.index ?? null
  hoverSide.value = hit?.side ?? null
  hoverCorridor.value = corr
  if (corr) {
    emit('hover-info', {
      type: 'corridor',
      fromCore: props.cores[corr.i],
      toCore: props.cores[corr.j],
      count: props.grid[corr.i]?.[corr.j] || 0,
    })
  } else if (hit) {
    emit('hover-info', { type: 'core', coreIndex: hit.index, side: hit.side })
  } else {
    emit('hover-info', null)
  }
}

function onLeave() {
  hoverCore.value = null
  hoverSide.value = null
  hoverCorridor.value = null
  emit('hover-info', null)
}

function onClick(ev) {
  const canvas = canvasRef.value
  if (!canvas) return
  const rect = canvas.getBoundingClientRect()
  const mx = ev.clientX - rect.left
  const my = ev.clientY - rect.top
  const corr = corridorNear(mx, my)
  if (corr) {
    emit('select-corridor', {
      fromCore: props.cores[corr.i],
      toCore: props.cores[corr.j],
    })
    return
  }
  const hit = hitTest(mx, my)
  if (!hit) {
    emit('select-core', { clear: true })
    return
  }
  if (ev.shiftKey) {
    emit('select-pair', { coreIndex: hit.index })
  } else {
    emit('select-core', { coreIndex: hit.index, side: hit.side })
  }
}

function onDblClick(ev) {
  const canvas = canvasRef.value
  if (!canvas) return
  const rect = canvas.getBoundingClientRect()
  const mx = ev.clientX - rect.left
  const my = ev.clientY - rect.top
  const corr = corridorNear(mx, my)
  if (corr) {
    emit('spotlight-corridor', {
      fromCore: props.cores[corr.i],
      toCore: props.cores[corr.j],
    })
  }
}

function setViewMode(mode) {
  if (mode === 'circle' && props.cores.length > MATRIX_CORE_LIMIT) {
    viewMode.value = 'matrix'
    return
  }
  viewMode.value = mode === 'matrix' ? 'matrix' : 'circle'
}

watch(() => props.cores.length, (n) => {
  if (n > MATRIX_CORE_LIMIT) viewMode.value = 'matrix'
}, { immediate: true })

watch(() => [props.cores, props.grid, props.focusCorridor, props.focusCores, props.directionMode, viewMode.value, hoverCore.value, hoverCorridor.value],
  () => scheduleDraw(), { deep: true })

onMounted(() => {
  nextTick(() => {
    scheduleDraw()
    if (wrapRef.value && typeof ResizeObserver !== 'undefined') {
      _ro = new ResizeObserver(() => scheduleDraw())
      _ro.observe(wrapRef.value)
    }
  })
})

onBeforeUnmount(() => {
  if (_drawRaf) cancelAnimationFrame(_drawRaf)
  _ro?.disconnect()
})

defineExpose({ scheduleDraw })
</script>

<style scoped>
.mini-chord {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 180px;
}
.mini-chord-canvas {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}
.mini-chord-view-toggle {
  position: absolute;
  top: 4px;
  right: 4px;
  z-index: 2;
  display: flex;
  gap: 4px;
}
.mini-chord-view-toggle button {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border: 1px solid var(--border);
  background: var(--tb-bg);
  color: var(--fg);
  border-radius: 3px;
  padding: 2px;
  cursor: pointer;
}
.mini-chord-view-toggle button:disabled {
  opacity: 0.4;
  cursor: default;
}
.mini-chord-view-toggle button.active {
  color: var(--fg);
  border-color: var(--accent);
  font-weight: 600;
}
</style>
