/**
 * SvgExporter.js – exports the current timeline viewport as a vector SVG.
 *
 * Mirrors the key visual elements of TimelineRenderer.js but outputs SVG
 * markup instead of drawing to a Canvas 2D context.  The result is a proper
 * vector SVG: segment bars are <rect> elements and labels are <text> elements.
 */

import {
  LABEL_W, RULER_H, ROW_H, ROW_GAP, STI_ROW_H, MIN_SEG_W,
  buildRowLayout, formatTime,
} from './TimelineRenderer.js'
import { taskColor, taskDisplayName, taskMergeKey, stiNoteColor } from '../utils/colors.js'

// ---- Helpers ---------------------------------------------------------------

function esc(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function segmentLabelText(row, seg) {
  if (row.type === 'core') return taskDisplayName(seg.task)
  return row.label || ''
}

function niceStep(span) {
  const targetTicks = 8
  const rough = span / targetTicks
  const mag = Math.pow(10, Math.floor(Math.log10(rough)))
  for (const m of [1, 2, 5, 10]) {
    if (mag * m >= rough) return mag * m
  }
  return mag * 10
}

function getSegsForRow(trace, row) {
  if (row.type === 'task')      return trace.segByMergeKey.get(row.key)
  if (row.type === 'core')      return trace.coreSegs.get(row.key)
  if (row.type === 'core-task') return trace.coreTaskSegs.get(row.coreKey)?.get(row.taskKey)
  return null
}

// ---- Main export function --------------------------------------------------

/**
 * Render the current timeline viewport as an SVG string.
 *
 * @param {object} trace     BtfTrace from parseBtf()
 * @param {object} viewport  { timeStart, timeEnd, scrollY, canvasW, canvasH }
 * @param {object} options   { viewMode, expanded, darkMode, showGrid, cursors, marks, showSti }
 * @returns {string}         SVG markup ready for download
 */
export function renderToSvg(trace, viewport, options = {}) {
  const { timeStart, timeEnd, scrollY, canvasW, canvasH } = viewport
  const {
    viewMode  = 'task',
    expanded  = new Set(),
    darkMode  = true,
    showGrid  = false,
    cursors   = [],
    marks     = [],
    showSti   = true,
  } = options

  const timeSpan = timeEnd - timeStart
  if (timeSpan <= 0 || canvasW <= 0 || canvasH <= 0) return ''

  const pxPerNs = canvasW / timeSpan

  // --- Colour scheme ---
  const bgColor   = darkMode ? '#1E1E1E' : '#FFFFFF'
  const rulerBg   = darkMode ? '#2D2D2D' : '#F0F0F0'
  const textColor = darkMode ? '#D4D4D4' : '#333333'
  const rulerText = darkMode ? '#AAAAAA' : '#555555'
  const evenBg    = darkMode ? '#252526' : '#F5F5F5'
  const oddBg     = darkMode ? '#2D2D2D' : '#EBEBEB'
  const stiBg     = darkMode ? '#1A1A2E' : '#EEF0FA'
  const sepColor  = darkMode ? '#333333' : '#DDDDDD'
  const gridColor = darkMode ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)'

  const els = []
  const defs = []
  let clipId = 0

  // Full background
  els.push(`<rect width="${canvasW}" height="${canvasH}" fill="${bgColor}"/>`)

  // Ruler background
  els.push(`<rect x="0" y="0" width="${canvasW}" height="${RULER_H}" fill="${rulerBg}"/>`)

  // Row layout (mirrors TimelineRenderer.js buildRowLayout call)
  const { rows } = buildRowLayout(trace, viewMode, expanded, RULER_H - scrollY, showSti)

  // ---- Grid lines (optional) ----
  if (showGrid) {
    const step = niceStep(timeSpan)
    const startSnap = Math.ceil(timeStart / step) * step
    for (let t = startSnap; t <= timeEnd; t += step) {
      const x = (t - timeStart) * pxPerNs
      if (x >= 0 && x <= canvasW) {
        els.push(`<line x1="${x.toFixed(1)}" y1="${RULER_H}" x2="${x.toFixed(1)}" y2="${canvasH}" stroke="${gridColor}" stroke-width="1"/>`)
      }
    }
  }

  // ---- Row backgrounds ----
  for (let i = 0; i < rows.length; i++) {
    const row  = rows[i]
    const rowH = row.type === 'sti' ? STI_ROW_H : ROW_H
    if (row.y + rowH < 0 || row.y >= canvasH) continue
    const bg = row.type === 'sti' ? stiBg : (i % 2 === 0 ? evenBg : oddBg)
    els.push(`<rect x="0" y="${row.y.toFixed(1)}" width="${canvasW}" height="${rowH}" fill="${bg}"/>`)
    // Separator line
    if (row.type !== 'sti') {
      const sepY = (row.y + rowH + ROW_GAP - 1).toFixed(1)
      els.push(`<line x1="0" y1="${sepY}" x2="${canvasW}" y2="${sepY}" stroke="${sepColor}" stroke-width="0.5"/>`)
    }
  }

  // ---- Task / core segment bars ----
  for (const row of rows) {
    if (row.type === 'sti') continue
    const rowH = ROW_H
    if (row.y + rowH < 0 || row.y > canvasH) continue

    const segs = getSegsForRow(trace, row)
    if (!segs) continue

    for (const seg of segs) {
      if (seg.end <= timeStart || seg.start >= timeEnd) continue
      const x1 = (seg.start - timeStart) * pxPerNs
      const x2 = (seg.end   - timeStart) * pxPerNs
      const w  = Math.max(MIN_SEG_W, x2 - x1)
      if (x1 + w < 0 || x1 > canvasW) continue

      const repr  = trace.taskRepr?.get(taskMergeKey(seg.task)) ?? seg.task
      const color = taskColor(taskMergeKey(seg.task), repr)
      els.push(
        `<rect x="${x1.toFixed(1)}" y="${(row.y + 1).toFixed(1)}" ` +
        `width="${w.toFixed(1)}" height="${(rowH - 2)}" ` +
        `fill="${color}" rx="1"/>`
      )

      const label = segmentLabelText(row, seg)
      if (label && w >= 40) {
        const textX = Math.round(x1) + 3
        const clipW = Math.ceil(w) - 6
        if (clipW > 0) {
          const textY = row.y + rowH / 2
          const currentClipId = `seg-label-${clipId++}`
          defs.push(
            `<clipPath id="${currentClipId}">` +
            `<rect x="${textX}" y="${(row.y + 1).toFixed(1)}" width="${clipW}" height="${rowH - 2}" rx="1"/>` +
            `</clipPath>`
          )
          els.push(
            `<text x="${textX}" y="${textY.toFixed(1)}" ` +
            `fill="${darkMode ? 'rgba(255,255,255,0.85)' : 'rgba(0,0,0,0.75)'}" ` +
            `font-family="sans-serif" font-size="10" dominant-baseline="middle" ` +
            `clip-path="url(#${currentClipId})">${esc(label)}</text>`
          )
        }
      }
    }
  }

  // ---- STI markers ----
  for (const row of rows) {
    if (row.type !== 'sti') continue
    const rowH = STI_ROW_H
    if (row.y + rowH < 0 || row.y > canvasH) continue

    const evs  = trace.stiEventsByTarget?.get(row.key) ?? []
    const midY = row.y + rowH / 2

    for (const ev of evs) {
      if (ev.time < timeStart || ev.time > timeEnd) continue
      const x     = (ev.time - timeStart) * pxPerNs
      const color = stiNoteColor(ev.note)
      const hw = 4, h = 6
      const pts = `${x.toFixed(1)},${(midY - h).toFixed(1)} ${(x - hw).toFixed(1)},${midY.toFixed(1)} ${(x + hw).toFixed(1)},${midY.toFixed(1)}`
      els.push(`<polygon points="${pts}" fill="${color}"/>`)
    }
  }

  // ---- Ruler ticks and labels ----
  {
    const step      = niceStep(timeSpan)
    const startSnap = Math.ceil(timeStart / step) * step
    for (let t = startSnap; t <= timeEnd; t += step) {
      const x = (t - timeStart) * pxPerNs
      if (x < 0 || x > canvasW) continue
      els.push(`<line x1="${x.toFixed(1)}" y1="${RULER_H - 6}" x2="${x.toFixed(1)}" y2="${RULER_H}" stroke="${rulerText}" stroke-width="1"/>`)
      els.push(
        `<text x="${(x + 3).toFixed(1)}" y="${RULER_H - 9}" ` +
        `fill="${rulerText}" font-family="monospace" font-size="10" dominant-baseline="auto">` +
        `${esc(formatTime(t, trace.timeScale))}</text>`
      )
    }
  }

  // ---- Row labels (right-side fixed column — drawn last so always visible) ----
  // Clip text to LABEL_W characters using SVG clipPath is complex; instead we
  // just draw the label in the left LABEL_W column and truncate the string.
  for (let i = 0; i < rows.length; i++) {
    const row  = rows[i]
    const rowH = row.type === 'sti' ? STI_ROW_H : ROW_H
    if (row.y + rowH < 0 || row.y > canvasH) continue

    const midY       = row.y + rowH / 2
    const maxChars   = Math.floor(LABEL_W / 7)
    const rawLabel   = row.label
    const label      = rawLabel.length > maxChars ? rawLabel.slice(0, maxChars - 1) + '…' : rawLabel
    const labelColor = row.type === 'sti' ? '#88AABB' : (row.type === 'core' ? '#E0E0E0' : textColor)

    // Label background to separate from segments
    els.push(`<rect x="0" y="${row.y.toFixed(1)}" width="${LABEL_W}" height="${rowH}" fill="${darkMode ? '#1E1E1E' : '#F8F8F8'}" opacity="0.92"/>`)
    els.push(
      `<text x="4" y="${midY.toFixed(1)}" ` +
      `fill="${labelColor}" font-family="monospace" font-size="10" dominant-baseline="middle">` +
      `${esc(label)}</text>`
    )
  }

  // Corner (ruler × label column overlap)
  els.push(`<rect x="0" y="0" width="${LABEL_W}" height="${RULER_H}" fill="${darkMode ? '#1A1A1A' : '#E8E8E8'}"/>`)
  els.push(
    `<text x="4" y="${RULER_H / 2}" fill="${rulerText}" font-family="monospace" font-size="10" dominant-baseline="middle">` +
    `${viewMode === 'core' ? 'Core / Task' : 'Task / TaskID'}</text>`
  )

  // ---- Cursor lines ----
  const CURSOR_COLORS = ['#FF4444','#44FF88','#4499FF','#FFAA22','#FF44FF','#44FFFF','#FFFF44','#CC44FF']
  cursors.forEach((cur, idx) => {
    if (!cur || cur.ns == null) return
    const x = (cur.ns - timeStart) * pxPerNs
    if (x < 0 || x > canvasW) return
    const color = CURSOR_COLORS[idx % CURSOR_COLORS.length]
    els.push(
      `<line x1="${x.toFixed(1)}" y1="${RULER_H}" x2="${x.toFixed(1)}" y2="${canvasH}" ` +
      `stroke="${color}" stroke-width="1.2" stroke-dasharray="4,3"/>`
    )
  })

  // ---- Mark lines ----
  for (const [ns, label, color] of marks) {
    const x = (ns - timeStart) * pxPerNs
    if (x < 0 || x > canvasW) continue
    els.push(
      `<line x1="${x.toFixed(1)}" y1="0" x2="${x.toFixed(1)}" y2="${canvasH}" ` +
      `stroke="${color}" stroke-width="1" stroke-dasharray="4,2" opacity="0.8"/>`
    )
    if (label) {
      els.push(
        `<text x="${(x + 3).toFixed(1)}" y="${RULER_H + 14}" ` +
        `fill="${color}" font-family="monospace" font-size="9">${esc(label)}</text>`
      )
    }
  }

  return (
    `<svg xmlns="http://www.w3.org/2000/svg" ` +
    `width="${canvasW}" height="${canvasH}" ` +
    `viewBox="0 0 ${canvasW} ${canvasH}">\n` +
    (defs.length ? `<defs>\n${defs.join('\n')}\n</defs>\n` : '') +
    els.join('\n') +
    `\n</svg>`
  )
}
