/**
 * SvgExporter.js – exports the current timeline viewport as a vector SVG.
 *
 * Mirrors the key visual elements of TimelineRenderer.js but outputs SVG
 * markup instead of drawing to a Canvas 2D context.  The result is a proper
 * vector SVG: segment bars are <rect> elements and labels are <text> elements.
 */

import {
  RULER_H, MIN_SEG_W,
  buildRowLayout, formatTime,
} from './TimelineRenderer.js'
import { getTimelineLayout } from '../utils/timelineLayout.js'
import { taskColor, taskDisplayName, taskMergeKey, stiNoteColor, lighterColor } from '../utils/colors.js'
import {
  visiblePriorityEpisodes,
  BOOST_BAND_COLOR,
  INVERSION_BAND_COLOR,
} from '../utils/priorityAnalysis.js'
import {
  visibleIntervalInstances,
  visibleIntervalMarkerEvents,
  intervalInstancesForDraw,
  intervalColor,
  intervalStripeColors,
} from '../utils/intervalAnalysis.js'
import { cursorSortedPlaced } from '../utils/cursorAnalysis.js'

function L() {
  return getTimelineLayout()
}

function rowBandHeightSvg(row) {
  if (row.type === 'sti') return row.isExpanded ? L().stiWaveformH : L().stiRowH
  return L().rowH
}

function appendIntervalRowBars(els, trace, row, timeStart, timeEnd, pxPerNs, canvasW, darkMode, ox, highlightInterval = null) {
  const rowH = L().rowH
  const { instances, preCulled } = intervalInstancesForDraw(trace, row.key)
  const visible = visibleIntervalInstances(instances, timeStart, timeEnd, preCulled)
  const base = row.color || intervalColor(row.key)
  const stroke = darkMode ? lighterColor(base, 1.55) : lighterColor(base, 0.72)
  const barY = row.y + 2
  const barH = rowH - 4

  for (const inst of visible) {
    const x1 = (inst.startNs - timeStart) * pxPerNs
    const x2 = (inst.stopNs - timeStart) * pxPerNs
    if (x2 < -2 || x1 > canvasW + 2) continue
    const cx = Math.max(0, Math.floor(x1))
    const cx2 = Math.min(Math.ceil(x2), canvasW)
    const drawW = cx2 - cx
    if (drawW < 0.5) continue
    els.push(
      `<rect x="${(ox + cx).toFixed(1)}" y="${barY.toFixed(1)}" ` +
      `width="${drawW.toFixed(1)}" height="${barH}" ` +
      `fill="${base}" stroke="${stroke}" stroke-width="1.25" rx="0"/>`
    )
  }

  const markerEvents = visibleIntervalMarkerEvents(trace, row.key, timeStart, timeEnd)
  if (markerEvents.length > 0) {
    const { dark: tickDark, light: tickLight } = intervalStripeColors(base, darkMode)
    for (const ev of markerEvents) {
      const x = (ev.timeNs - timeStart) * pxPerNs
      if (x < -1 || x > canvasW + 1) continue
      const xi = (ox + Math.round(x)).toFixed(1)
      const color = ev.isStart ? tickDark : tickLight
      const dash = ev.isStart ? '' : ' stroke-dasharray="2,2"'
      els.push(
        `<line x1="${xi}" y1="${barY.toFixed(1)}" x2="${xi}" y2="${(barY + barH).toFixed(1)}" ` +
        `stroke="${color}" stroke-width="1"${dash}/>`
      )
    }
  }

  const hi = (highlightInterval && String(highlightInterval.id) === String(row.key))
    ? highlightInterval
    : null
  if (hi) {
    const markNs = hi.markNs ?? hi.stopNs
    const hiColor = darkMode ? 'rgba(255,255,255,0.92)' : 'rgba(0,0,0,0.88)'
    for (const t of new Set([markNs, hi.startNs, hi.stopNs])) {
      const x = (t - timeStart) * pxPerNs
      if (x < -1 || x > canvasW + 1) continue
      const xi = (ox + Math.round(x)).toFixed(1)
      els.push(
        `<line x1="${xi}" y1="${barY.toFixed(1)}" x2="${xi}" y2="${(barY + barH).toFixed(1)}" ` +
        `stroke="${hiColor}" stroke-width="2"/>`
      )
    }
  }
}

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

function mergeKeyForRow(row) {
  if (row.type === 'task') return row.key
  if (row.type === 'core-task') return taskMergeKey(row.taskKey)
  return null
}

function appendPriorityBoostBands(els, trace, mk, rowY, rowH, timeStart, timeEnd, pxPerNs, canvasW, darkMode, ox) {
  const episodes = trace.priorityEpisodesByMk?.get(mk)
  if (!episodes?.length) return
  const visible = visiblePriorityEpisodes(episodes, timeStart, timeEnd)
  if (!visible.length) return

  const bandH = Math.max(3, Math.floor(rowH * 0.3))
  const bandY = rowY + rowH - bandH

  for (const ep of visible) {
    const x1 = (ep.startNs - timeStart) * pxPerNs
    const x2 = (ep.stopNs - timeStart) * pxPerNs
    if (x2 < -2 || x1 > canvasW + 2) continue
    const cx = Math.max(0, Math.floor(x1))
    const cx2 = Math.min(Math.ceil(x2), canvasW)
    const drawW = cx2 - cx
    if (drawW < 0.5) continue
    const stroke = ep.inversionSuspect ? INVERSION_BAND_COLOR : BOOST_BAND_COLOR
    const fill = ep.inversionSuspect
      ? (darkMode ? 'rgba(231,76,60,0.72)' : 'rgba(231,76,60,0.52)')
      : (darkMode ? 'rgba(243,156,18,0.72)' : 'rgba(243,156,18,0.52)')
    els.push(
      `<rect x="${(ox + cx).toFixed(1)}" y="${bandY.toFixed(1)}" ` +
      `width="${drawW.toFixed(1)}" height="${bandH}" ` +
      `fill="${fill}" stroke="${stroke}" stroke-width="1" rx="0"/>`
    )
  }
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
    showSti     = true,
    stiExpanded = new Set(),
    stiLogScale = false,
    highlightInterval = null,
  } = options

  const timeSpan = timeEnd - timeStart
  if (timeSpan <= 0 || canvasW <= 0 || canvasH <= 0) return ''

  const pxPerNs = canvasW / timeSpan

  // canvasW is the timeline-only canvas width (label column is a separate DOM element).
  // In the SVG we place both side by side, so the total SVG width is wider.
  const OX   = L().labelW          // x-offset: all timeline content starts here
  const svgW = canvasW + L().labelW // total SVG width

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

  // Row layout (mirrors TimelineRenderer.js buildRowLayout call)
  const { rows } = buildRowLayout(trace, viewMode, expanded, RULER_H - scrollY, showSti, stiExpanded)

  // Compute the actual rendered height — the bottom of the last visible row.
  // Using canvasH (the full window height) leaves blank space when the task list
  // is small; svgH trims the SVG to exactly the content that is present.
  let svgH = RULER_H
  for (const row of rows) {
    const rowH = rowBandHeightSvg(row)
    if (row.y >= canvasH || row.y + rowH < 0) continue
    const bottom = Math.min(row.y + rowH + L().rowGap, canvasH)
    if (bottom > svgH) svgH = bottom
  }

  // Full background
  els.push(`<rect width="${svgW}" height="${svgH}" fill="${bgColor}"/>`)

  // Ruler background (full width)
  els.push(`<rect x="0" y="0" width="${svgW}" height="${RULER_H}" fill="${rulerBg}"/>`)

  // ---- Grid lines (optional) ----
  if (showGrid) {
    const step = niceStep(timeSpan)
    const startSnap = Math.ceil(timeStart / step) * step
    for (let t = startSnap; t <= timeEnd; t += step) {
      const rawX = (t - timeStart) * pxPerNs
      if (rawX >= 0 && rawX <= canvasW) {
        const x = (OX + rawX).toFixed(1)
        els.push(`<line x1="${x}" y1="${RULER_H}" x2="${x}" y2="${svgH}" stroke="${gridColor}" stroke-width="1"/>`)
      }
    }
  }

  // ---- Row backgrounds ----
  for (let i = 0; i < rows.length; i++) {
    const row  = rows[i]
    const rowH = rowBandHeightSvg(row)
    if (row.y + rowH < 0 || row.y >= canvasH) continue
    const bg = (row.type === 'sti' || row.type === 'interval') ? stiBg : (i % 2 === 0 ? evenBg : oddBg)
    // Row background covers only the timeline area (label column drawn separately)
    els.push(`<rect x="${OX}" y="${row.y.toFixed(1)}" width="${canvasW}" height="${rowH}" fill="${bg}"/>`)
    // Separator line spans full row width
    if (row.type !== 'sti' && row.type !== 'interval') {
      const sepY = (row.y + rowH + L().rowGap - 1).toFixed(1)
      els.push(`<line x1="0" y1="${sepY}" x2="${svgW}" y2="${sepY}" stroke="${sepColor}" stroke-width="0.5"/>`)
    }
  }

  // ---- Task / core segment bars ----
  for (const row of rows) {
    if (row.type === 'sti' || row.type === 'interval') continue
    const rowH = L().rowH
    if (row.y + rowH < 0 || row.y > canvasH) continue

    const segs = getSegsForRow(trace, row)

    if (segs) {
      for (const seg of segs) {
        if (seg.end <= timeStart || seg.start >= timeEnd) continue
        const rawX1 = (seg.start - timeStart) * pxPerNs
        const rawX2 = (seg.end   - timeStart) * pxPerNs
        const w     = Math.max(MIN_SEG_W, rawX2 - rawX1)
        if (rawX1 + w < 0 || rawX1 > canvasW) continue

        const x1 = OX + rawX1
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

    const mk = mergeKeyForRow(row)
    if (mk) {
      appendPriorityBoostBands(
        els, trace, mk, row.y + 1, rowH - 2,
        timeStart, timeEnd, pxPerNs, canvasW, darkMode, OX,
      )
    }
  }

  // ---- STI markers / waveforms ----
  for (const row of rows) {
    if (row.type !== 'sti') continue
    const rowH = row.isExpanded ? L().stiWaveformH : L().stiRowH
    if (row.y + rowH < 0 || row.y > canvasH) continue

    const evs = trace.stiEventsByTarget?.get(row.key) ?? []

    if (row.isExpanded) {
      // ---- Expanded waveform ----
      if (evs.length === 0) continue
      const PAD         = 4
      const chartTop    = row.y + PAD
      const chartBottom = row.y + rowH - PAD
      const chartHt     = chartBottom - chartTop

      const evVal = ev => parseFloat(ev.note !== '' ? ev.note : ev.event)

      let valMin = Infinity, valMax = -Infinity
      for (const ev of evs) {
        const v = evVal(ev)
        if (!isNaN(v)) { if (v < valMin) valMin = v; if (v > valMax) valMax = v }
      }
      if (!isFinite(valMin)) continue
      if (valMin === valMax) { valMin -= 1; valMax += 1 }

      const signedLog2  = v => Math.sign(v) * Math.log2(1 + Math.abs(v))
      const mappedMin   = stiLogScale ? signedLog2(valMin) : valMin
      const mappedMax   = stiLogScale ? signedLog2(valMax) : valMax
      const mappedRange = mappedMax - mappedMin
      const valToY      = v => chartBottom - (((stiLogScale ? signedLog2(v) : v) - mappedMin) / mappedRange) * chartHt

      // Axis dashed lines (span timeline area only)
      const axisColor = darkMode ? 'rgba(255,255,255,0.12)' : 'rgba(0,0,0,0.12)'
      els.push(`<line x1="${OX}" y1="${chartBottom.toFixed(1)}" x2="${svgW}" y2="${chartBottom.toFixed(1)}" stroke="${axisColor}" stroke-width="0.5" stroke-dasharray="3,3"/>`)
      els.push(`<line x1="${OX}" y1="${chartTop.toFixed(1)}" x2="${svgW}" y2="${chartTop.toFixed(1)}" stroke="${axisColor}" stroke-width="0.5" stroke-dasharray="3,3"/>`)

      // Axis value labels
      const fmtVal   = v => Math.abs(v) >= 1e6 ? (v / 1e6).toFixed(2) + 'M' : Math.abs(v) >= 1e3 ? (v / 1e3).toFixed(1) + 'k' : String(Math.round(v))
      const dimColor = darkMode ? 'rgba(255,255,255,0.3)' : 'rgba(0,0,0,0.3)'
      els.push(`<text x="${svgW - 2}" y="${(chartTop + 10).toFixed(1)}" text-anchor="end" fill="${dimColor}" font-family="monospace" font-size="9">${esc(fmtVal(valMax))}</text>`)
      els.push(`<text x="${svgW - 2}" y="${(chartBottom - 2).toFixed(1)}" text-anchor="end" fill="${dimColor}" font-family="monospace" font-size="9">${esc(fmtVal(valMin))}</text>`)
      if (stiLogScale) {
        const scaleColor = darkMode ? 'rgba(91,200,255,0.55)' : 'rgba(0,100,200,0.55)'
        els.push(`<text x="${OX + 4}" y="${(chartTop + 2).toFixed(1)}" dominant-baseline="hanging" fill="${scaleColor}" font-family="monospace" font-size="9">log&#x2082;</text>`)
      }

      // Clip region (timeline area only)
      const wfClipId = `wf-${clipId++}`
      defs.push(`<clipPath id="${wfClipId}"><rect x="${OX}" y="${row.y.toFixed(1)}" width="${canvasW}" height="${rowH}"/></clipPath>`)

      // Polyline (include one event before range for step-hold continuity)
      const lineColor = darkMode ? '#5BC8FF' : '#0070CC'
      const dotColor  = darkMode ? '#80DFFF' : '#0050AA'
      let prevEv = null
      const rangeEvs = []
      for (const ev of evs) {
        if (ev.time < timeStart) { prevEv = ev }
        else if (ev.time <= timeEnd) { rangeEvs.push(ev) }
      }
      const pts = []
      if (prevEv) { const pv = evVal(prevEv); if (!isNaN(pv)) pts.push(`${OX},${valToY(pv).toFixed(1)}`) }
      for (const ev of rangeEvs) {
        const v = evVal(ev)
        if (!isNaN(v)) pts.push(`${(OX + (ev.time - timeStart) * pxPerNs).toFixed(1)},${valToY(v).toFixed(1)}`)
      }
      if (pts.length >= 2) {
        els.push(`<polyline points="${pts.join(' ')}" fill="none" stroke="${lineColor}" stroke-width="1.5" stroke-linejoin="round" clip-path="url(#${wfClipId})"/>`)
      }
      for (const ev of rangeEvs) {
        const v = evVal(ev); if (isNaN(v)) continue
        els.push(`<circle cx="${(OX + (ev.time - timeStart) * pxPerNs).toFixed(1)}" cy="${valToY(v).toFixed(1)}" r="2.5" fill="${dotColor}" clip-path="url(#${wfClipId})"/>`)
      }
    } else {
      // ---- Collapsed: diamond markers ----
      const midY = row.y + L().stiRowH / 2
      for (const ev of evs) {
        if (ev.time < timeStart || ev.time > timeEnd) continue
        const x     = OX + (ev.time - timeStart) * pxPerNs
        const color = stiNoteColor(ev.note)
        const hw = 4, h = 6
        const pts = `${x.toFixed(1)},${(midY - h).toFixed(1)} ${(x - hw).toFixed(1)},${midY.toFixed(1)} ${x.toFixed(1)},${(midY + h).toFixed(1)} ${(x + hw).toFixed(1)},${midY.toFixed(1)}`
        els.push(`<polygon points="${pts}" fill="${color}"/>`)
      }
    }
  }

  // ---- Interval bars ----
  for (const row of rows) {
    if (row.type !== 'interval') continue
    const rowH = L().rowH
    if (row.y + rowH < 0 || row.y > canvasH) continue
    appendIntervalRowBars(
      els, trace, row, timeStart, timeEnd, pxPerNs, canvasW, darkMode, OX, highlightInterval,
    )
  }

  // ---- Ruler ticks and labels ----
  {
    const step      = niceStep(timeSpan)
    const startSnap = Math.ceil(timeStart / step) * step
    for (let t = startSnap; t <= timeEnd; t += step) {
      const rawX = (t - timeStart) * pxPerNs
      if (rawX < 0 || rawX > canvasW) continue
      const x = OX + rawX
      els.push(`<line x1="${x.toFixed(1)}" y1="${RULER_H - 6}" x2="${x.toFixed(1)}" y2="${RULER_H}" stroke="${rulerText}" stroke-width="1"/>`)
      els.push(
        `<text x="${(x + 3).toFixed(1)}" y="${RULER_H - 9}" ` +
        `fill="${rulerText}" font-family="monospace" font-size="10" dominant-baseline="auto">` +
        `${esc(formatTime(t, trace.timeScale))}</text>`
      )
    }
  }

  // ---- Row labels (left fixed column) ----
  for (let i = 0; i < rows.length; i++) {
    const row  = rows[i]
    const rowH = rowBandHeightSvg(row)
    if (row.y + rowH < 0 || row.y > canvasH) continue

    const midY       = row.y + rowH / 2
    const maxChars   = Math.floor(L().labelW / 7)
    const rawLabel   = row.label
    const label      = rawLabel.length > maxChars ? rawLabel.slice(0, maxChars - 1) + '…' : rawLabel
    let labelColor = row.type === 'sti' ? '#88AABB' : (row.type === 'core' ? '#E0E0E0' : textColor)
    if (row.type === 'interval') labelColor = row.color || intervalColor(row.key)

    // Opaque label column background (matches separate LabelColumn DOM element)
    els.push(`<rect x="0" y="${row.y.toFixed(1)}" width="${L().labelW}" height="${rowH}" fill="${darkMode ? '#1E1E1E' : '#F8F8F8'}"/>`)
    if (row.type === 'interval') {
      const swatch = row.color || intervalColor(row.key)
      els.push(`<rect x="4" y="${(midY - 5).toFixed(1)}" width="10" height="10" fill="${swatch}" stroke="${swatch}" stroke-width="1"/>`)
      els.push(
        `<text x="18" y="${midY.toFixed(1)}" ` +
        `fill="${labelColor}" font-family="monospace" font-size="10" dominant-baseline="middle">` +
        `${esc(label)}</text>`
      )
    } else {
      els.push(
        `<text x="4" y="${midY.toFixed(1)}" ` +
        `fill="${labelColor}" font-family="monospace" font-size="10" dominant-baseline="middle">` +
        `${esc(label)}</text>`
      )
    }
  }

  // Corner (ruler × label column)
  els.push(`<rect x="0" y="0" width="${L().labelW}" height="${RULER_H}" fill="${darkMode ? '#1A1A1A' : '#E8E8E8'}"/>`)
  els.push(
    `<text x="4" y="${RULER_H / 2}" fill="${rulerText}" font-family="monospace" font-size="10" dominant-baseline="middle">` +
    `${viewMode === 'core' ? 'Core / Task' : 'Task / TaskID'}</text>`
  )

  // ---- Cursor lines ----
  const CURSOR_COLORS = ['#FF4444','#44FF88','#4499FF','#FFAA22','#FF44FF','#44FFFF','#FFFF44','#CC44FF']
  const sortedCursors = cursorSortedPlaced(cursors)
  for (let order = 0; order < sortedCursors.length; order++) {
    const { t, slotIndex } = sortedCursors[order]
    const rawX = (t - timeStart) * pxPerNs
    if (rawX < 0 || rawX > canvasW) continue
    const x     = OX + rawX
    const color = CURSOR_COLORS[slotIndex % CURSOR_COLORS.length]
    els.push(
      `<line x1="${x.toFixed(1)}" y1="0" x2="${x.toFixed(1)}" y2="${svgH}" ` +
      `stroke="${color}" stroke-width="1.5" stroke-dasharray="4,3"/>`
    )
    const timeLabel = `C${slotIndex + 1}: ${formatTime(t, trace.timeScale, 3)}`
    const badgeW = timeLabel.length * 6 + 8
    const lx = Math.min(x + 2, svgW - badgeW - 2)
    const ly = 2 + (slotIndex + 1) * 18
    els.push(`<rect x="${lx.toFixed(1)}" y="${ly}" width="${badgeW}" height="14" fill="${color}" rx="2"/>`)
    els.push(`<text x="${(lx + 4).toFixed(1)}" y="${ly + 3}" dominant-baseline="hanging" fill="#000" font-family="monospace" font-size="10" font-weight="bold">${esc(timeLabel)}</text>`)

    if (order > 0) {
      const prevT = sortedCursors[order - 1].t
      const delta = Math.abs(t - prevT)
      const dStr = `Δ ${formatTime(delta, trace.timeScale, 3)}`
      const midX = OX + ((t + prevT) / 2 - timeStart) * pxPerNs
      if (midX >= OX && midX <= OX + canvasW) {
        const dBadgeW = dStr.length * 6 + 6
        const dBadgeH = 14
        let dbx = Math.round(midX - dBadgeW / 2)
        dbx = Math.max(OX + 2, Math.min(dbx, svgW - dBadgeW - 2))
        const dby = RULER_H + 4
        els.push(`<rect x="${dbx.toFixed(1)}" y="${dby}" width="${dBadgeW}" height="${dBadgeH}" fill="${color}" rx="2"/>`)
        els.push(`<text x="${(dbx + 3).toFixed(1)}" y="${dby + 3}" dominant-baseline="hanging" fill="#000" font-family="monospace" font-size="10" font-weight="bold">${esc(dStr)}</text>`)
      }
    }
  }

  // ---- Mark lines (mirrors drawMarksHorizontal canvas behavior) ----
  for (const [ns, label, color, type = 'bookmark'] of marks) {
    const rawX = (ns - timeStart) * pxPerNs
    if (rawX < 0 || rawX > canvasW) continue
    const x = OX + rawX
    const isAnnotation = type === 'annotation'

    // Vertical line — starts at RULER_H
    els.push(
      `<line x1="${x.toFixed(1)}" y1="${RULER_H}" x2="${x.toFixed(1)}" y2="${svgH}" ` +
      `stroke="${color}" stroke-width="${isAnnotation ? '1.0' : '1.2'}" ` +
      (isAnnotation ? `stroke-dasharray="6,3" ` : '') +
      `opacity="0.75"/>`
    )

    // Triangle flag at ruler edge
    const halfW = 4
    const tipY  = RULER_H - 2
    const baseY = tipY - 6
    if (isAnnotation) {
      const midY = (baseY + tipY) / 2
      els.push(`<polygon points="${x},${baseY} ${x + halfW},${midY} ${x},${tipY} ${x - halfW},${midY}" fill="${color}"/>`)
    } else {
      els.push(`<polygon points="${x - halfW},${baseY} ${x + halfW},${baseY} ${x},${tipY}" fill="${color}"/>`)
    }

    // Time badge at top of ruler area
    const timeLabel = formatTime(ns, trace.timeScale)
    const timeW = timeLabel.length * 6 + 8
    const tx = Math.min(x + 2, svgW - timeW - 2)
    els.push(`<rect x="${tx.toFixed(1)}" y="2" width="${timeW}" height="14" fill="${color}" rx="2" opacity="0.85"/>`)
    els.push(`<text x="${(tx + 4).toFixed(1)}" y="3" dominant-baseline="hanging" fill="#000" font-family="monospace" font-size="10">${esc(timeLabel)}</text>`)

    // User label badge in ruler area (bottom)
    const ltext = label || ''
    if (ltext) {
      const estW = ltext.length * 6 + 8
      const lx   = Math.min(x + 3, svgW - estW - 2)
      els.push(`<rect x="${lx.toFixed(1)}" y="${RULER_H - 16}" width="${estW}" height="13" fill="${color}" rx="1" opacity="0.85"/>`)
      els.push(`<text x="${(lx + 4).toFixed(1)}" y="${RULER_H - 14}" dominant-baseline="hanging" fill="#000" font-family="monospace" font-size="10">${esc(ltext)}</text>`)
    }
  }

  return (
    `<svg xmlns="http://www.w3.org/2000/svg" ` +
    `width="${svgW}" height="${svgH}" ` +
    `viewBox="0 0 ${svgW} ${svgH}">\n` +
    (defs.length ? `<defs>\n${defs.join('\n')}\n</defs>\n` : '') +
    els.join('\n') +
    `\n</svg>`
  )
}
