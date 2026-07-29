/**
 * Priority inheritance / inversion analysis from create pri:N and set_priority STI events.
 */
import { formatTime } from './timeFormat.js'
import { taskMergeKey, taskDisplayName, taskLabelForMergeKey } from './colors.js'

export const BOOST_BAND_COLOR = '#F39C12'
export const INVERSION_BAND_COLOR = '#E74C3C'

const CREATE_PRI_RE = /^create\s+pri:(\d+)\s*$/i
const PRIORITY_STI_RE = /^(set_priority|priority_inherit|priority_disinherit)\s+(.+?)\s+pri:(\d+)\s*$/i

/** @returns {number|null} */
export function parseCreatePriority(note) {
  const m = CREATE_PRI_RE.exec((note ?? '').trim())
  return m ? parseInt(m[1], 10) : null
}

/** @returns {{ taskRef: string, priority: number, kind: string }|null} */
export function parsePriorityStiNote(note) {
  const m = PRIORITY_STI_RE.exec((note ?? '').trim())
  if (!m) return null
  return { kind: m[1].toLowerCase(), taskRef: m[2].trim(), priority: parseInt(m[3], 10) }
}

/** @deprecated alias */
export function parseSetPriorityNote(note) {
  const p = parsePriorityStiNote(note)
  if (!p || p.kind !== 'set_priority') return null
  return { taskRef: p.taskRef, priority: p.priority }
}

/** Merge key from set_priority / priority_inherit note task ref. */
export function mergeKeyFromPriorityRef(taskRef) {
  return taskMergeKey((taskRef ?? '').trim())
}

function mediumBlockers(basePri, peakPri, taskBasePriority, holderMk, taskRepr) {
  if (basePri == null || peakPri == null || peakPri <= basePri) return []
  const out = []
  for (const [mk, pri] of taskBasePriority) {
    if (mk === holderMk) continue
    if (pri > basePri && pri < peakPri) {
      out.push({ mk, label: taskLabelForMergeKey({ taskRepr }, mk), basePri: pri })
    }
  }
  // Match desktop's `sorted(out)` over display-name strings (parser.py
  // `_priority_medium_blockers`): alphabetical by label, not by priority.
  out.sort((a, b) => (a.label < b.label ? -1 : a.label > b.label ? 1 : 0))
  return out
}

function patternLabel(episode) {
  if (episode.inherited) {
    if (episode.inversionSuspect && episode.mediumTasks.length) {
      const names = episode.mediumTasks.slice(0, 2).map(t => t.label)
      const extra = episode.mediumTasks.length > 2 ? ` +${episode.mediumTasks.length - 2}` : ''
      return `Mutex inherit L/M/H (${names.join(', ')}${extra})`
    }
    return 'Mutex inherit'
  }
  if (episode.inversionSuspect && episode.mediumTasks.length) {
    const names = episode.mediumTasks.slice(0, 2).map(t => t.label)
    const extra = episode.mediumTasks.length > 2 ? ` +${episode.mediumTasks.length - 2}` : ''
    return `L/M/H (${names.join(', ')}${extra})`
  }
  if (episode.peakPri > episode.basePri) return 'Boost'
  return '—'
}

/**
 * @param {object[]} stiEvents
 * @param {Map<string, { time: number, priority: number }>} createPriByRaw
 * @param {number} timeMax
 * @param {Map<string, string>} [rawToMk] raw BTF name → merge key
 * @param {Map<string, string>} [taskRepr] merge key → representative raw name
 */
export function buildPriorityData(stiEvents, createPriByRaw, timeMax, rawToMk = new Map(), taskRepr = new Map()) {
  const taskBasePriority = new Map()
  for (const [raw, rec] of createPriByRaw) {
    const mk = rawToMk.get(raw) || taskMergeKey(raw)
    if (!taskBasePriority.has(mk)) taskBasePriority.set(mk, rec.priority)
  }

  const changesByMk = new Map()
  for (const ev of stiEvents || []) {
    if (ev.target !== 'task') continue
    const sp = parsePriorityStiNote(ev.note)
    if (!sp) continue
    const mk = mergeKeyFromPriorityRef(sp.taskRef)
    if (!changesByMk.has(mk)) changesByMk.set(mk, [])
    changesByMk.get(mk).push({
      timeNs: ev.time,
      core: ev.core || '',
      priority: sp.priority,
      kind: sp.kind,
      taskRef: sp.taskRef,
    })
  }

  const hasPriorityInstrumentation =
    taskBasePriority.size > 0 && [...changesByMk.values()].some(list => list.length > 0)

  if (!hasPriorityInstrumentation) {
    return {
      taskBasePriority,
      priorityEpisodes: [],
      priorityEpisodesByMk: new Map(),
      prioritySummaryByMk: new Map(),
      hasPriorityInstrumentation: false,
    }
  }

  const priorityEpisodes = []
  const priorityEpisodesByMk = new Map()

  for (const [mk, basePri] of taskBasePriority) {
    const changes = (changesByMk.get(mk) || []).sort((a, b) => a.timeNs - b.timeNs)
    if (!changes.length) continue

    let effective = basePri
    let open = null

    const closeEpisode = (stopNs) => {
      if (!open || stopNs <= open.startNs) {
        open = null
        return
      }
      const mediumTasks = mediumBlockers(basePri, open.peakPri, taskBasePriority, mk, taskRepr)
      const episode = {
        mk,
        taskLabel: taskLabelForMergeKey({ taskRepr }, mk),
        basePri,
        peakPri: open.peakPri,
        startNs: open.startNs,
        stopNs,
        durationNs: stopNs - open.startNs,
        inherited: open.inherited,
        inversionSuspect: open.inherited || mediumTasks.length > 0,
        mediumTasks,
        pattern: '',
      }
      episode.pattern = patternLabel(episode)
      priorityEpisodes.push(episode)
      if (!priorityEpisodesByMk.has(mk)) priorityEpisodesByMk.set(mk, [])
      priorityEpisodesByMk.get(mk).push(episode)
      open = null
    }

    for (const ch of changes) {
      const prev = effective
      effective = ch.priority
      const isInherit = ch.kind === 'priority_inherit'
      const isDisinherit = ch.kind === 'priority_disinherit'

      if (effective > basePri && prev <= basePri) {
        open = { startNs: ch.timeNs, peakPri: effective, inherited: isInherit }
      } else if (open) {
        if (effective > open.peakPri) open.peakPri = effective
        if (isInherit) open.inherited = true
        if (effective <= basePri || isDisinherit) closeEpisode(ch.timeNs)
      }
    }
    if (open) closeEpisode(timeMax)
  }

  priorityEpisodes.sort((a, b) => a.startNs - b.startNs || a.stopNs - b.stopNs)

  const prioritySummaryByMk = new Map()
  for (const [mk, episodes] of priorityEpisodesByMk) {
    const basePri = taskBasePriority.get(mk)
    let peakPri = basePri
    let totalBoostNs = 0
    let inversionCount = 0
    let inheritCount = 0
    for (const ep of episodes) {
      if (ep.peakPri > peakPri) peakPri = ep.peakPri
      totalBoostNs += ep.durationNs
      if (ep.inversionSuspect) inversionCount++
      if (ep.inherited) inheritCount++
    }
    let pattern = 'Boost only'
    if (inheritCount > 0) pattern = inversionCount > inheritCount ? 'Mutex inherit + L/M/H' : 'Mutex inherit'
    else if (inversionCount > 0) pattern = 'L/M/H pattern'
    prioritySummaryByMk.set(mk, {
      mk,
      label: episodes[0]?.taskLabel || taskLabelForMergeKey({ taskRepr }, mk),
      basePri,
      peakPri,
      episodeCount: episodes.length,
      totalBoostNs,
      inversionCount,
      inheritCount,
      episodes,
      pattern,
    })
  }

  return {
    taskBasePriority,
    priorityEpisodes,
    priorityEpisodesByMk,
    prioritySummaryByMk,
    hasPriorityInstrumentation,
  }
}

export function visiblePriorityEpisodes(episodes, timeStart, timeEnd) {
  if (!episodes?.length) return []
  return episodes.filter(ep => ep.stopNs > timeStart && ep.startNs < timeEnd)
}

/** Stats rows for the panel (one row per boosted task, scoped). */
export function priorityStatsRows(trace, lo, hi) {
  if (!trace?.hasPriorityInstrumentation) return []
  const rows = []
  for (const summary of trace.prioritySummaryByMk?.values() || []) {
    const episodes = (summary.episodes || []).filter(ep =>
      (lo == null || hi == null) ? true : (ep.stopNs > lo && ep.startNs < hi),
    )
    if (!episodes.length) continue
    let peakPri = summary.basePri
    let totalBoostNs = 0
    let inversionCount = 0
    let inheritCount = 0
    for (const ep of episodes) {
      if (ep.peakPri > peakPri) peakPri = ep.peakPri
      const clipLo = lo != null ? Math.max(lo, ep.startNs) : ep.startNs
      const clipHi = hi != null ? Math.min(hi, ep.stopNs) : ep.stopNs
      if (clipHi > clipLo) totalBoostNs += clipHi - clipLo
      if (ep.inversionSuspect) inversionCount++
      if (ep.inherited) inheritCount++
    }
    const scale = trace.timeScale
    let pattern = 'Boost only'
    if (inheritCount > 0) pattern = inversionCount > inheritCount ? 'Mutex inherit + L/M/H' : 'Mutex inherit'
    else if (inversionCount > 0) pattern = 'L/M/H pattern'
    rows.push({
      mk: summary.mk,
      label: summary.label,
      basePri: summary.basePri,
      peakPri,
      episodeCount: episodes.length,
      totalBoostNs,
      inversionCount,
      inheritCount,
      pattern,
      total: formatTime(totalBoostNs, scale),
      episodes,
    })
  }
  rows.sort((a, b) => b.totalBoostNs - a.totalBoostNs || a.label.localeCompare(b.label))
  return rows
}

/** Per-episode detail rows for HTML/CSV export. */
export function priorityEpisodeDetailRows(trace, lo, hi, limit = 200) {
  if (!trace?.hasPriorityInstrumentation) return []
  const scale = trace.timeScale
  const rows = []
  for (const ep of trace.priorityEpisodes || []) {
    if (lo != null && hi != null && !(ep.stopNs > lo && ep.startNs < hi)) continue
    rows.push({
      task: ep.taskLabel,
      basePri: ep.basePri,
      peakPri: ep.peakPri,
      startNs: ep.startNs,
      stopNs: ep.stopNs,
      start: formatTime(ep.startNs, scale),
      stop: formatTime(ep.stopNs, scale),
      duration: formatTime(ep.durationNs, scale),
      durationNs: ep.durationNs,
      pattern: ep.pattern || '—',
      inherited: !!ep.inherited,
    })
  }
  rows.sort((a, b) => a.startNs - b.startNs || a.stopNs - b.stopNs)
  return limit > 0 ? rows.slice(0, limit) : rows
}

/** Suffix for task label column, e.g. " · pri 2". */
export function taskPriorityLabelSuffix(trace, mk) {
  const pri = trace?.taskBasePriority?.get?.(mk)
  if (pri == null) return ''
  return ` · pri ${pri}`
}

export function priorityEpisodePlotPoints(trace, mk, lo, hi) {
  const episodes = trace?.priorityEpisodesByMk?.get(mk) || []
  const scale = trace?.timeScale
  return episodes
    .filter(ep => (lo == null || hi == null) ? true : (ep.stopNs > lo && ep.startNs < hi))
    .map((ep, index) => ({
      index,
      xNs: ep.stopNs,
      yValue: ep.durationNs,
      label: `${ep.taskLabel}: ${ep.basePri}→${ep.peakPri} (${formatTime(ep.durationNs, scale)})`,
      payload: ep,
    }))
}
