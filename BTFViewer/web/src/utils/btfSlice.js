/**
 * Cursor-range BTF slice (parity with btf_viewer_pkg/btf_slice.py).
 */

import { taskLabelForMergeKey, taskReprGet } from './colors.js'

export function filterBtfTextToRange(text, lo, hi) {
  let a = Number(lo)
  let b = Number(hi)
  if (!Number.isFinite(a) || !Number.isFinite(b)) {
    throw new Error('Slice range must be numeric timestamps')
  }
  a = Math.trunc(a)
  b = Math.trunc(b)
  if (b < a) [a, b] = [b, a]
  const { lines, kept } = filterBtfLines(String(text || '').split(/\r?\n/), a, b)
  return { text: lines.join('\n') + (lines.length ? '\n' : ''), kept }
}

export function reconstructBtfSlice(trace, lo, hi) {
  let a = Number(lo)
  let b = Number(hi)
  if (!Number.isFinite(a) || !Number.isFinite(b)) {
    throw new Error('Slice range must be numeric timestamps')
  }
  a = Math.trunc(a)
  b = Math.trunc(b)
  if (b < a) [a, b] = [b, a]
  const lines = []
  const meta = trace?.meta && typeof trace.meta === 'object' ? trace.meta : {}
  for (const [key, val] of Object.entries(meta)) {
    lines.push(`#${key} ${val}`)
  }
  if (trace?.timeScale && !meta.timeScale) lines.push(`#timeScale ${trace.timeScale}`)
  lines.push(`#sliced ${a}-${b}`)
  const events = []
  for (const seg of trace?.segments || []) {
    const start = Number(seg.start)
    const end = Number(seg.end)
    if (!Number.isFinite(start) || !Number.isFinite(end)) continue
    if (end < a || start > b) continue
    const s = Math.trunc(Math.max(start, a))
    const e = Math.trunc(Math.min(end, b))
    if (s >= e) continue
    const core = seg.core || 'Core_0'
    const mk = seg.mergeKey || seg.task || ''
    const name = String(
      taskLabelForMergeKey(trace, mk) || taskReprGet(trace, mk) || mk || 'task',
    ).replace(/,/g, ' ')
    events.push([s, `${s},${core},0,T,${name},0,resume,`])
    events.push([e, `${e},${core},0,T,${name},0,preempt,`])
  }
  for (const ev of trace?.stiEvents || []) {
    const t = Math.trunc(Number(ev.time))
    if (!Number.isFinite(t) || t < a || t > b) continue
    const note = String(ev.note || '').replace(/\n/g, ' ')
    events.push([
      t,
      `${t},${ev.core || 'Core_0'},0,STI,${ev.target || ''},0,${ev.event || ''},${note}`,
    ])
  }
  for (const tick of trace?.tickStiTimes || []) {
    const t = Math.trunc(Number(tick))
    if (Number.isFinite(t) && t >= a && t <= b) {
      events.push([t, `${t},Core_0,0,STI,TICK,0,trigger,`])
    }
  }
  events.sort((x, y) => x[0] - y[0] || String(x[1]).localeCompare(String(y[1])))
  for (const [, line] of events) lines.push(line)
  return { text: lines.join('\n') + (lines.length ? '\n' : ''), kept: events.length }
}

function filterBtfLines(src, lo, hi) {
  const out = [`#sliced ${lo}-${hi}`]
  let kept = 0
  for (const raw of src) {
    const stripped = String(raw || '').trim()
    if (!stripped) continue
    if (stripped[0] === '#') {
      out.push(stripped)
      continue
    }
    const parts = stripped.split(',', 9)
    if (parts.length < 4) continue
    const evType = String(parts[3] || '').trim()
    if (evType === 'C') {
      out.push(stripped)
      continue
    }
    const t = Number.parseInt(String(parts[0] || '').trim(), 10)
    if (!Number.isFinite(t)) continue
    if (t >= lo && t <= hi) {
      out.push(stripped)
      kept += 1
    }
  }
  return { lines: out, kept }
}
