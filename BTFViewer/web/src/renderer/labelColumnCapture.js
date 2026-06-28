/**
 * Canvas rasterisation for label column / column header in snapshots.
 * html-to-image fails to resolve Vue scoped CSS and CSS variables on cloned nodes,
 * so the panel background paints but label text is invisible.
 */
import { RULER_H, RULER_W, rowBandHeight, colBandWidth } from './TimelineRenderer.js'
import { getTimelineLayout } from '../utils/timelineLayout.js'
import { intervalColor } from '../utils/intervalAnalysis.js'

const LABEL_TOP = 16
const LABEL_BOTTOM = 8

function themeColors(darkMode) {
  return {
    panelBg: darkMode ? '#252526' : '#F5F5F5',
    rulerBg: darkMode ? '#2D2D2D' : '#EEEEEE',
    border: darkMode ? '#3C3C3C' : '#DDDDDD',
    fg: darkMode ? '#D4D4D4' : '#1E1E1E',
    fgDim: darkMode ? '#858585' : '#666666',
    sti: '#88AABB',
    coreLabel: darkMode ? '#E0E0E0' : '#1E1E1E',
  }
}

function labelFontSize() {
  return Math.max(10, getTimelineLayout().labelFontSize)
}

function truncateLabel(text, maxPx) {
  const maxChars = Math.max(1, Math.floor(maxPx / 7))
  if (text.length <= maxChars) return text
  return text.slice(0, maxChars - 1) + '…'
}

function canvasToBlob(canvas) {
  return new Promise((resolve) => canvas.toBlob(resolve, 'image/png'))
}

function setupCanvas(width, height, pixelRatio = 1) {
  const dpr = pixelRatio > 0 ? pixelRatio : 1
  const canvas = document.createElement('canvas')
  canvas.width = Math.round(width * dpr)
  canvas.height = Math.round(height * dpr)
  const ctx = canvas.getContext('2d')
  if (!ctx) return null
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  return { canvas, ctx }
}

function drawSwatch(ctx, x, y, size, color, darkMode) {
  ctx.fillStyle = color
  ctx.fillRect(x, y, size, size)
  ctx.strokeStyle = darkMode ? 'rgba(255,255,255,0.22)' : 'rgba(0,0,0,0.35)'
  ctx.lineWidth = 1
  ctx.strokeRect(x + 0.5, y + 0.5, size - 1, size - 1)
}

function labelColorForRow(row, colors) {
  if (row.type === 'sti') return colors.sti
  if (row.type === 'core') return colors.coreLabel
  if (row.type === 'interval') return row.color || intervalColor(row.key)
  return colors.fg
}

function drawLabelRow(ctx, row, screenY, rowH, width, colors, expanded, stiExpanded, darkMode) {
  ctx.fillStyle = colors.panelBg
  ctx.fillRect(0, screenY, width, rowH)

  const midY = screenY + rowH / 2
  let textX = 8
  const labelColor = labelColorForRow(row, colors)
  const swatchSize = 10
  const swatchY = midY - swatchSize / 2

  if (row.type === 'task' || row.type === 'core-task') {
    drawSwatch(ctx, textX, swatchY, swatchSize, row.color, darkMode)
    textX += 16
    if (row.type === 'core-task') textX += 8
  } else if (row.type === 'core') {
    ctx.fillStyle = row.color
    ctx.beginPath()
    ctx.arc(textX + 4, midY, 4, 0, Math.PI * 2)
    ctx.fill()
    textX += 14
    ctx.fillStyle = colors.fgDim
    ctx.font = '8px monospace'
    ctx.textBaseline = 'middle'
    ctx.fillText(expanded?.has(row.key) ? '▼' : '▶', textX, midY)
    textX += 10
  } else if (row.type === 'interval') {
    const swatch = row.color || intervalColor(row.key)
    drawSwatch(ctx, textX, swatchY, swatchSize, swatch, darkMode)
    textX += 16
  } else if (row.type === 'sti') {
    if (row.isTag) {
      ctx.fillStyle = colors.fgDim
      ctx.font = '8px monospace'
      ctx.textBaseline = 'middle'
      ctx.fillText(stiExpanded?.has(row.key) ? '▼' : '▶', textX, midY)
      textX += 10
    } else {
      ctx.fillStyle = colors.sti
      ctx.font = `${labelFontSize()}px monospace`
      ctx.textBaseline = 'middle'
      ctx.fillText('◆', textX, midY)
      textX += 12
    }
  }

  ctx.fillStyle = labelColor
  ctx.font = `${row.type === 'core' ? 12 : labelFontSize()}px monospace`
  ctx.textBaseline = 'middle'
  ctx.fillText(truncateLabel(row.label, width - textX - 4), textX, midY)
}

/**
 * Draw the horizontal-mode task label column (matches LabelColumn.vue).
 */
export function drawLabelColumn(ctx, {
  rowLayout,
  scrollY = 0,
  width,
  height,
  viewMode = 'task',
  darkMode = true,
  expanded = null,
  stiExpanded = null,
}) {
  const colors = themeColors(darkMode)
  const rows = rowLayout?.rows
  if (!rows?.length || width <= 0 || height <= 0) return

  ctx.fillStyle = colors.panelBg
  ctx.fillRect(0, 0, width, height)

  ctx.fillStyle = colors.rulerBg
  ctx.fillRect(0, 0, width, RULER_H)
  ctx.strokeStyle = colors.border
  ctx.beginPath()
  ctx.moveTo(0, RULER_H + 0.5)
  ctx.lineTo(width, RULER_H + 0.5)
  ctx.stroke()

  ctx.fillStyle = colors.fgDim
  ctx.font = `${labelFontSize()}px monospace`
  ctx.textBaseline = 'middle'
  ctx.fillText(viewMode === 'core' ? 'Core / Task' : 'Task / TaskID', 8, RULER_H / 2)

  const bodyTop = RULER_H
  ctx.save()
  ctx.beginPath()
  ctx.rect(0, bodyTop, width, height - bodyTop)
  ctx.clip()

  for (const row of rows) {
    const rowH = rowBandHeight(row)
    const screenY = bodyTop + row.y - scrollY
    if (screenY + rowH < bodyTop || screenY > height) continue
    drawLabelRow(ctx, row, screenY, rowH, width, colors, expanded, stiExpanded, darkMode)
  }
  ctx.restore()

  ctx.strokeStyle = colors.border
  ctx.beginPath()
  ctx.moveTo(width - 0.5, 0)
  ctx.lineTo(width - 0.5, height)
  ctx.stroke()
}

export async function captureLabelColumnBlob(options) {
  const { width, height, pixelRatio = 1 } = options
  if (!width || !height) return null
  const setup = setupCanvas(width, height, pixelRatio)
  if (!setup) return null
  drawLabelColumn(setup.ctx, options)
  return canvasToBlob(setup.canvas)
}

function drawVerticalColumnLabel(ctx, text, cx, topY, trackH, maxW, color) {
  ctx.save()
  ctx.fillStyle = color
  ctx.font = '11px monospace'
  ctx.textAlign = 'left'
  ctx.textBaseline = 'top'
  ctx.translate(cx, topY + trackH)
  ctx.rotate(-Math.PI / 2)
  ctx.fillText(truncateLabel(text, trackH), 0, 0)
  ctx.restore()
}

/**
 * Draw the vertical-mode column header row (matches ColumnHeaderRow.vue).
 */
export function drawColumnHeader(ctx, {
  columnLayout,
  scrollX = 0,
  canvasW,
  headerH,
  darkMode = true,
  expanded = null,
}) {
  const colors = themeColors(darkMode)
  const cols = columnLayout?.cols
  if (!cols?.length || canvasW <= 0 || headerH <= 0) return

  ctx.fillStyle = colors.rulerBg
  ctx.fillRect(0, 0, RULER_W, headerH)
  ctx.strokeStyle = colors.border
  ctx.beginPath()
  ctx.moveTo(RULER_W + 0.5, 0)
  ctx.lineTo(RULER_W + 0.5, headerH)
  ctx.stroke()

  ctx.fillStyle = colors.panelBg
  ctx.fillRect(RULER_W, 0, canvasW - RULER_W, headerH)
  ctx.beginPath()
  ctx.moveTo(RULER_W, headerH - 0.5)
  ctx.lineTo(canvasW, headerH - 0.5)
  ctx.stroke()

  const labelTrackH = Math.max(20, headerH - LABEL_TOP - LABEL_BOTTOM)
  const sx = scrollX || 0

  for (const col of cols) {
    const cw = colBandWidth(col)
    const screenX = col.x - sx
    if (screenX + cw <= RULER_W || screenX >= canvasW) continue

    const drawX = Math.max(RULER_W, screenX)
    const drawW = Math.min(screenX + cw, canvasW) - drawX
    if (drawW <= 0) continue

    ctx.fillStyle = colors.panelBg
    ctx.fillRect(drawX, 0, drawW, headerH)

    if (screenX >= RULER_W) {
      ctx.strokeStyle = colors.border
      ctx.beginPath()
      ctx.moveTo(screenX + 0.5, 0)
      ctx.lineTo(screenX + 0.5, headerH)
      ctx.stroke()
    }

    const cx = screenX + cw / 2
    if (col.type === 'task' || col.type === 'core-task' || col.type === 'interval') {
      ctx.fillStyle = col.color || (col.type === 'interval' ? intervalColor(col.key) : colors.fg)
      ctx.fillRect(cx - 4, 4, 8, 8)
    }

    if (col.type === 'core' || col.isExpandable) {
      ctx.fillStyle = colors.fgDim
      ctx.font = '8px monospace'
      ctx.textAlign = 'left'
      ctx.textBaseline = 'top'
      const isOpen = col.type === 'core'
        ? expanded?.has(col.key)
        : col.isExpanded
      ctx.fillText(isOpen ? '▼' : '▶', screenX + 2, 3)
    }

    const labelColor = col.type === 'sti'
      ? colors.sti
      : (col.type === 'interval' ? (col.color || intervalColor(col.key)) : colors.fg)
    drawVerticalColumnLabel(ctx, col.label, cx, LABEL_TOP, labelTrackH, cw - 4, labelColor)
  }
}

export async function captureColumnHeaderBlob(options) {
  const { canvasW: width, headerH: height, pixelRatio = 1 } = options
  if (!width || !height) return null
  const setup = setupCanvas(width, height, pixelRatio)
  if (!setup) return null
  drawColumnHeader(setup.ctx, options)
  return canvasToBlob(setup.canvas)
}
