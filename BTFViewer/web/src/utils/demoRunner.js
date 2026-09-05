/**
 * Run a parsed demo XML pack against in-app host operations.
 * Keyboard injection is skipped; macros map to APIs. `<move>` / `<sweep>` /
 * `<click>` drive a synthetic pointer overlay (the browser cannot move the OS cursor).
 */

import {
  demoTimeToTraceUnits,
  elementText,
  expandVars,
  resolveDemoXy,
  splitCsv,
  truthy,
} from './demoXml.js'
import { pickVoiceLang, voicePathCandidates } from './demoVoice.js'

export class DemoAborted extends Error {
  constructor(message = 'demo aborted') {
    super(message)
    this.name = 'DemoAborted'
  }
}

export class DemoSkip extends Error {
  constructor(direction = 1) {
    super('demo skip')
    this.name = 'DemoSkip'
    this.direction = Number(direction) === 0 ? 0 : (direction < 0 ? -1 : 1)
  }
}

const SKIP_TAGS = new Set([
  'hotkey', 'focus', 'voice', 'note', 'comment', 'log', 'title',
])

export function shouldSkipStep(step, { skipOptional = false, skipTags = [] } = {}) {
  if (skipOptional && step.optional) return true
  const skip = skipTags instanceof Set ? skipTags : new Set(skipTags)
  for (const t of step.tags || []) {
    if (skip.has(t)) return true
  }
  return false
}

function mergeSignals(...signals) {
  const ctl = new AbortController()
  const forward = () => {
    if (!ctl.signal.aborted) ctl.abort()
  }
  for (const s of signals) {
    if (!s) continue
    if (s.aborted) {
      ctl.abort()
      return ctl.signal
    }
    s.addEventListener('abort', forward, { once: true })
  }
  return ctl.signal
}

function sleep(ms, signal) {
  const n = Math.max(0, Number(ms) || 0)
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DemoAborted())
      return
    }
    if (n <= 0) {
      resolve()
      return
    }
    const t = setTimeout(() => {
      signal?.removeEventListener('abort', onAbort)
      resolve()
    }, n)
    const onAbort = () => {
      clearTimeout(t)
      reject(new DemoAborted())
    }
    signal?.addEventListener('abort', onAbort, { once: true })
  })
}

function attr(el, name, vars, fallback = '') {
  if (!el?.attrib || el.attrib[name] == null) return fallback
  return expandVars(el.attrib[name], vars)
}

/**
 * @param {object} host  in-app operations (see App.vue demoHost)
 * @param {object} pack  from packFromFileMap
 * @param {object} [options]
 */
export function createDemoRunner(host, pack, options = {}) {
  const parsed = pack.parsed
  const vars = { ...parsed.vars }
  const defaults = parsed.defaults
  const skipTags = new Set(options.skipTags || [])
  const skipOptional = !!options.skipOptional
  const aiWaitCapSec = options.aiWaitCapSec ?? 4
  const abort = new AbortController()
  let skipCtl = new AbortController()
  let skipDir = 0
  let skipRestart = false
  const voiceLangs = parsed.languages || { defaultId: 'en', list: [{ id: 'en', label: 'English' }] }
  let voiceLang = pickVoiceLang(
    options.voiceLang,
    (voiceLangs.list || []).map(x => x.id),
    voiceLangs.defaultId,
  )
  vars.LANG = voiceLang
  vars.VOICE_LANG = voiceLang
  let paused = false
  let pauseGate = new AbortController()
  let audio = null
  let audioUrl = null
  let audioDone = Promise.resolve()
  let audioResolve = null
  let audioGen = 0

  function waitSignal() {
    if (skipCtl.signal.aborted && !skipDir && !skipRestart && !abort.signal.aborted) {
      skipCtl = new AbortController()
    }
    return mergeSignals(abort.signal, skipCtl.signal)
  }

  function check() {
    if (abort.signal.aborted) throw new DemoAborted()
    if (skipRestart) throw new DemoSkip(0)
    if (skipDir) throw new DemoSkip(skipDir)
  }

  function resetSkipGate() {
    skipDir = 0
    skipRestart = false
    skipCtl = new AbortController()
  }

  function skipError() {
    if (skipRestart) return new DemoSkip(0)
    if (skipDir) return new DemoSkip(skipDir)
    return new DemoAborted()
  }

  function notifyPause() {
    try { pauseGate.abort() } catch { /* ignore */ }
    pauseGate = new AbortController()
  }

  function setPaused(on) {
    if (abort.signal.aborted) return
    const next = !!on
    if (paused === next) return
    paused = next
    if (paused) {
      try { audio?.pause() } catch { /* ignore */ }
    } else {
      const p = audio?.play?.()
      if (p && typeof p.catch === 'function') p.catch(() => {})
    }
    notifyPause()
    host.setDemoPaused?.(paused)
  }

  function requestSkip(dir) {
    if (abort.signal.aborted) return
    skipRestart = false
    skipDir = dir < 0 ? -1 : 1
    stopAudio()
    if (paused) setPaused(false)
    try { skipCtl.abort() } catch { /* ignore */ }
  }

  function requestRestart() {
    if (abort.signal.aborted) return
    skipRestart = true
    skipDir = 0
    stopAudio()
    if (paused) setPaused(false)
    try { skipCtl.abort() } catch { /* ignore */ }
  }

  function setVoiceLang(id) {
    const next = pickVoiceLang(
      id,
      (voiceLangs.list || []).map(x => x.id),
      voiceLangs.defaultId,
    )
    if (next === voiceLang) return voiceLang
    voiceLang = next
    vars.LANG = next
    vars.VOICE_LANG = next
    host.setDemoVoiceLang?.(next)
    requestRestart()
    return next
  }

  async function waitIfPaused() {
    while (paused && !abort.signal.aborted && !skipDir && !skipRestart) {
      await new Promise((resolve, reject) => {
        const gate = pauseGate.signal
        const sig = waitSignal()
        const onGate = () => {
          sig.removeEventListener('abort', onAbort)
          resolve()
        }
        const onAbort = () => {
          gate.removeEventListener('abort', onGate)
          reject(skipError())
        }
        if (sig.aborted) {
          onAbort()
          return
        }
        if (!paused) {
          resolve()
          return
        }
        gate.addEventListener('abort', onGate, { once: true })
        sig.addEventListener('abort', onAbort, { once: true })
      })
    }
    check()
  }

  async function waitMs(ms) {
    let left = Math.max(0, Number(ms) || 0)
    while (true) {
      await waitIfPaused()
      if (left <= 0) return
      const started = Date.now()
      const result = await new Promise((resolve, reject) => {
        const gate = pauseGate.signal
        const sig = waitSignal()
        const timer = setTimeout(() => {
          gate.removeEventListener('abort', onGate)
          sig.removeEventListener('abort', onAbort)
          resolve('ok')
        }, left)
        const onAbort = () => {
          clearTimeout(timer)
          gate.removeEventListener('abort', onGate)
          reject(skipError())
        }
        const onGate = () => {
          clearTimeout(timer)
          sig.removeEventListener('abort', onAbort)
          resolve('gate')
        }
        if (sig.aborted) {
          onAbort()
          return
        }
        sig.addEventListener('abort', onAbort, { once: true })
        gate.addEventListener('abort', onGate, { once: true })
      })
      if (result !== 'gate') return
      left -= Date.now() - started
      if (left < 0) left = 0
    }
  }

  function finishAudio() {
    const resolve = audioResolve
    audioResolve = null
    audioDone = Promise.resolve()
    if (resolve) resolve()
  }

  function waitWithSkip(promise) {
    return new Promise((resolve, reject) => {
      const sig = waitSignal()
      const onAbort = () => {
        reject(skipError())
      }
      if (sig.aborted) {
        onAbort()
        return
      }
      sig.addEventListener('abort', onAbort, { once: true })
      Promise.resolve(promise).then(
        (v) => {
          sig.removeEventListener('abort', onAbort)
          resolve(v)
        },
        (e) => {
          sig.removeEventListener('abort', onAbort)
          reject(e)
        },
      )
    })
  }

  function stopAudio() {
    audioGen += 1
    const el = audio
    audio = null
    if (el) {
      try { el.pause() } catch { /* ignore */ }
      try { el.removeAttribute('src') } catch { /* ignore */ }
      try { el.src = '' } catch { /* ignore */ }
      try { el.load() } catch { /* ignore */ }
    }
    if (audioUrl) {
      URL.revokeObjectURL(audioUrl)
      audioUrl = null
    }
    finishAudio()
  }

  async function playAudioFile(file, block) {
    stopAudio()
    if (!file || typeof Audio === 'undefined') return
    audioUrl = URL.createObjectURL(file)
    const el = new Audio(audioUrl)
    audio = el
    const gen = audioGen
    audioDone = new Promise((resolve) => {
      audioResolve = resolve
      const done = () => {
        el.removeEventListener('ended', done)
        el.removeEventListener('error', done)
        if (gen !== audioGen) return
        finishAudio()
      }
      el.addEventListener('ended', done)
      el.addEventListener('error', done)
    })
    const p = el.play()
    if (p && typeof p.catch === 'function') p.catch(() => {})
    if (block) await waitAudio()
  }

  function audioFinished() {
    const el = audio
    if (!el) return false
    if (el.ended || el.error) return true
    const dur = Number(el.duration)
    const t = Number(el.currentTime)
    return Number.isFinite(dur) && dur > 0 && Number.isFinite(t) && t >= dur - 0.05
  }

  async function waitAudio() {
    check()
    if (audioFinished()) finishAudio()
    try {
      await waitWithSkip(audioDone)
    } catch (err) {
      if (err instanceof DemoSkip || err instanceof DemoAborted) throw err
    }
    check()
  }

  async function runMacro(name, callEl) {
    if (name === 'fit') {
      // Macro "fit" is Ctrl+0 / Zoom Full View, not C1–Cn <fit_view/>.
      await (host.zoomView?.() ?? host.fit())
      return
    }
    if (name === 'clear_cursors') {
      await host.clearCursors()
      return
    }
    if (name === 'clear_bookmarks') {
      await host.clearBookmarks?.()
      return
    }
    if (name === 'clear_annotations') {
      await host.clearAnnotations?.()
      return
    }
    if (name === 'settings') {
      await host.openSettings?.({ page: 'appearance' })
      return
    }
    const body = parsed.macros[name]
    if (!body) return
    const local = { ...vars }
    if (callEl) {
      for (const [k, v] of Object.entries(callEl.attrib || {})) {
        if (k === 'ref' || k === 'name') continue
        local[k] = expandVars(v, vars)
      }
      for (const p of (callEl.children || []).filter(c => c.tag === 'param')) {
        const pn = p.attrib.name || ''
        if (pn) local[pn] = expandVars(elementText(p) || p.attrib.value || '', vars)
      }
    }
    const saved = { ...vars }
    Object.assign(vars, local)
    try {
      for (const child of body) await runAction(child)
    } finally {
      for (const k of Object.keys(vars)) delete vars[k]
      Object.assign(vars, saved)
    }
  }

  async function runAction(el) {
    await waitIfPaused()
    check()
    const tag = el.tag
    if (SKIP_TAGS.has(tag)) {
      if (tag === 'hotkey') {
        const keys = attr(el, 'keys', vars).toLowerCase()
        if (keys === 'esc' || keys === 'escape') await host.pressEscape?.()
      }
      return
    }
    if (tag === 'move' || tag === 'click') {
      const box = host.pointerBox?.() || { left: 0, top: 0, width: 0, height: 0 }
      const xy = resolveDemoXy(el, parsed.targets || {}, box, host.demoTarget)
      if (xy && host.movePointer) {
        const dur = el.attrib.duration != null
          ? Number(el.attrib.duration)
          : (defaults.move_duration ?? 0.35)
        await host.movePointer({ ...xy, duration: dur, signal: waitSignal() })
        if (tag === 'click') await host.clickPointer?.(xy)
      }
      return
    }
    if (tag === 'sweep') {
      if (host.movePointer) {
        const box = host.pointerBox?.() || { left: 0, top: 0, width: 0, height: 0 }
        const yf = Number(el.attrib.y ?? 0.055)
        const x0 = Number(el.attrib.x0 ?? 0.1)
        const x1 = Number(el.attrib.x1 ?? 0.85)
        const steps = Math.max(1, Number(el.attrib.steps ?? 8))
        const pause = Number(el.attrib.pause ?? 0.3)
        const y = box.top + yf * box.height
        for (let i = 0; i < steps; i++) {
          check()
          const fx = x0 + (x1 - x0) * (i / Math.max(1, steps - 1))
          const x = box.left + fx * box.width
          await host.movePointer({ x, y, duration: 0.2, signal: waitSignal() })
          await waitMs(pause * 1000)
        }
      }
      return
    }
    if (tag === 'scroll') {
      return
    }
    if (tag === 'press') {
      const key = attr(el, 'key', vars).toLowerCase()
      if (key === 'esc' || key === 'escape') await host.pressEscape?.()
      else if (key === 'enter' || key === 'return') {
        await host.pressEnter?.(attr(el, 'target', vars))
      }
      return
    }
    if (tag === 'type') {
      // Human-paced typing into a named input target (e.g. the Statistics
      // "Find section" box) so its live-filter/popup reacts one keystroke
      // at a time, like a real user typing.
      const target = attr(el, 'target', vars)
      const fullText = attr(el, 'text', vars, elementText(el))
      const delay = Number(el.attrib.delay ?? 0.1)
      if (!fullText) return
      if (target) await host.focusTarget?.(target)
      let typed = ''
      for (const ch of fullText) {
        check()
        typed += ch
        await host.typeText?.({ target, text: typed })
        if (delay) await waitMs(delay * 1000)
      }
      return
    }
    if (tag === 'confirm') {
      const prompt = expandVars(el.attrib.prompt || elementText(el) || '', vars)
      if (prompt) host.toast?.(prompt, 'info')
      return
    }
    if (tag === 'show_message' || tag === 'message' || tag === 'show_msg') {
      const text = expandVars(
        attr(el, 'text', vars, attr(el, 'message', vars, elementText(el))),
        vars,
      ).trim()
      const sec = Number(attr(el, 'seconds', vars, attr(el, 'duration', vars, '2')))
      let animateClear = true
      try {
        await host.showMessage?.({ text })
        await waitMs(Math.max(0, sec) * 1000)
      } catch (err) {
        if (err instanceof DemoSkip) {
          animateClear = false
          throw err
        }
        throw err
      } finally {
        if (text) await host.clearMessage?.({ animate: animateClear })
      }
      return
    }
    if (tag === 'audio' || tag === 'play') {
      const rel = attr(el, 'file', vars)
      let file = null
      for (const cand of voicePathCandidates(rel, voiceLang, voiceLangs.defaultId)) {
        file = pack.resolve(cand)
        if (file) break
      }
      const block = truthy(el.attrib.block, defaults.audio_block)
      if (!file) {
        host.toast?.(`Demo audio missing: ${rel}`, 'error')
        return
      }
      await playAudioFile(file, block)
      return
    }
    if (tag === 'wait_audio') {
      await waitAudio()
      return
    }
    if (tag === 'stop_audio') {
      stopAudio()
      return
    }
    if (tag === 'wait') {
      const isAi = truthy(el.attrib.ai, false)
      let sec = isAi
        ? Number(el.attrib.seconds ?? defaults.ai_wait)
        : Number(el.attrib.seconds ?? 1)
      if (isAi) sec = Math.min(sec, aiWaitCapSec)
      await waitMs(sec * 1000)
      return
    }
    if (tag === 'macro') {
      await runMacro(attr(el, 'ref', vars, attr(el, 'name', vars)), el)
      return
    }
    if (tag === 'highlight') {
      await host.highlight(attr(el, 'task', vars, attr(el, 'name', vars)))
      return
    }
    if (tag === 'clear_highlight') {
      await host.clearHighlight()
      return
    }
    if (tag === 'tab_nav') {
      const direction = String(attr(el, 'dir', vars, attr(el, 'direction', vars, 'next'))).toLowerCase()
      const forward = !['prev', 'previous', 'back', 'shift', 'shift+tab'].includes(direction)
      await host.tabNav?.(forward)
      return
    }
    if (tag === 'cursors') {
      await host.setCursors({
        times: attr(el, 'times', vars, attr(el, 'timestamps', vars)),
        unit: attr(el, 'unit', vars),
        limit: 'limit' in (el.attrib || {}) ? truthy(el.attrib.limit, false) : undefined,
        zoom: 'zoom' in (el.attrib || {}) ? truthy(el.attrib.zoom, false) : undefined,
      })
      return
    }
    if (tag === 'clear_cursors') {
      await host.clearCursors()
      return
    }
    if (tag === 'clear_bookmarks') {
      await host.clearBookmarks?.()
      return
    }
    if (tag === 'clear_annotations') {
      await host.clearAnnotations?.()
      return
    }
    if (tag === 'zoom_range') {
      await host.zoomRange({
        start: attr(el, 'start', vars),
        end: attr(el, 'end', vars),
        times: attr(el, 'times', vars),
        unit: attr(el, 'unit', vars),
      })
      return
    }
    if (tag === 'zoom_view' || tag === 'full_view' || tag === 'zoom_full') {
      // XML <zoom_view/> = Zoom Full View (toolbar Fit / Ctrl+0).
      await (host.zoomView?.() ?? host.fit())
      return
    }
    if (tag === 'fit_view' || tag === 'fit_api') {
      // XML <fit_view/> = Zoom fit to C1–Cn when cursors are placed.
      await host.fit()
      return
    }
    if (tag === 'zoom_1to1' || tag === 'one_to_one' || tag === '1to1') {
      await host.zoom1to1?.()
      return
    }
    if (tag === 'zoom_in') {
      const times = Math.max(1, Number(el.attrib.times ?? 1))
      for (let i = 0; i < times; i++) {
        check()
        await host.zoomIn?.()
      }
      return
    }
    if (tag === 'zoom_out') {
      await host.zoomOut?.()
      return
    }
    if (tag === 'limit') {
      await host.setLimit(truthy(attr(el, 'on', vars, attr(el, 'enabled', vars, 'true')), true))
      return
    }
    if (tag === 'stats_section') {
      await host.statsSection({
        id: attr(el, 'id', vars, attr(el, 'section', vars)),
        expand: 'expand' in (el.attrib || {}) ? truthy(el.attrib.expand, true) : true,
        collapse_others: 'collapse_others' in (el.attrib || {})
          ? truthy(el.attrib.collapse_others, false)
          : undefined,
        scroll: attr(el, 'scroll', vars),
      })
      return
    }
    if (tag === 'stats_reset' || tag === 'stats_done') {
      await host.statsReset()
      return
    }
    if (tag === 'jump_wcet') {
      await host.jumpWcet(attr(el, 'task', vars, attr(el, 'name', vars)))
      return
    }
    if (tag === 'move_view' || tag === 'move_viewport' || tag === 'pan_view') {
      const attrib = el.attrib || {}
      await host.moveView?.({
        time: attr(el, 'time', vars, attr(el, 'ns', vars, attr(el, 'at', vars))),
        unit: attr(el, 'unit', vars),
        task: attr(el, 'task', vars, attr(el, 'name', vars)),
        timeOmitted: !('time' in attrib || 'ns' in attrib || 'at' in attrib),
      })
      return
    }
    if (tag === 'panel') {
      await host.setPanel(attr(el, 'name', vars, attr(el, 'tab', vars, 'stats')))
      return
    }
    if (tag === 'view_mode' || tag === 'view') {
      await host.setViewMode(attr(el, 'mode', vars, attr(el, 'name', vars, 'task')))
      return
    }
    if (tag === 'cpu_load' || tag === 'load') {
      await host.setCpuLoad(truthy(attr(el, 'on', vars, attr(el, 'enabled', vars, 'true')), true))
      return
    }
    if (tag === 'analysis') {
      let close = false
      if ('close' in (el.attrib || {})) close = truthy(el.attrib.close, true)
      else if ('open' in (el.attrib || {})) close = !truthy(el.attrib.open, true)
      else if (String(el.attrib.action || '').toLowerCase() === 'close') close = true
      await host.openAnalysis({ close })
      return
    }
    if (tag === 'heatmap' || tag === 'chord' || tag === 'corridor') {
      let close = false
      if ('close' in (el.attrib || {})) close = truthy(el.attrib.close, true)
      else if ('open' in (el.attrib || {})) close = !truthy(el.attrib.open, true)
      else if (String(el.attrib.action || '').toLowerCase() === 'close') close = true
      const mode = attr(el, 'mode', vars, tag === 'chord' ? 'chord' : 'heatmap')
      await host.openHeatmap?.({ close, mode })
      return
    }
    if (tag === 'tick_dist' || tag === 'tick_distribution') {
      let close = false
      if ('close' in (el.attrib || {})) close = truthy(el.attrib.close, true)
      else if (String(el.attrib.action || '').toLowerCase() === 'close') close = true
      await host.tickDist?.({ close })
      return
    }
    if (tag === 'find') {
      const clear = truthy(el.attrib.clear, false)
      let query = attr(el, 'query', vars, attr(el, 'text', vars, attr(el, 'q', vars)))
      if (!query) query = expandVars(elementText(el), vars)
      if (clear) query = ''
      await host.find({
        query,
        next: 'next' in (el.attrib || {}) ? truthy(el.attrib.next, true) : !!query,
      })
      return
    }
    if (tag === 'settings') {
      let close = false
      if ('close' in (el.attrib || {})) close = truthy(el.attrib.close, true)
      else if ('open' in (el.attrib || {})) close = !truthy(el.attrib.open, true)
      else if (String(el.attrib.action || '').toLowerCase() === 'close') close = true
      if (close) {
        if (host.closeSettings) await host.closeSettings()
        else if (host.pressEscape) await host.pressEscape()
        else await host.openSettings?.({ close: true })
        return
      }
      await host.openSettings({
        page: attr(el, 'page', vars, attr(el, 'name', vars, 'Appearance')),
        close: false,
      })
      return
    }
    if (tag === 'ui' || tag === 'command' || tag === 'demo_api') {
      const op = attr(el, 'op', vars, attr(el, 'action', vars, attr(el, 'command', vars)))
      if (op) await runAction({ tag: op, attrib: { ...el.attrib }, children: [], text: '', tail: '' })
    }
  }

  async function run() {
    try {
      if (pack.traceFile) await host.loadTraceFile(pack.traceFile)
      const steps = (parsed.steps || []).filter(
        s => !shouldSkipStep(s, { skipOptional, skipTags }))
      const total = steps.length
      let i = 0
      while (i < total) {
        if (abort.signal.aborted) throw new DemoAborted()
        resetSkipGate()
        const step = steps[i]
        host.setStatus?.(`Demo: ${i + 1}/${total} — ${step.title || step.id}`)
        host.setDemoNav?.({
          index: i,
          total,
          title: step.title || step.id,
          canPrev: i > 0,
          canNext: i < total - 1,
        })
        try {
          for (const child of step.children) await runAction(child)
          await waitAudio()
          check()
          await waitMs((defaults.pause || 0) * 1000)
          i += 1
        } catch (err) {
          if (abort.signal.aborted) throw new DemoAborted()
          if (err instanceof DemoSkip || skipDir || skipRestart) {
            await host.clearMessage?.({ animate: false })
            const dir = skipRestart ? 0 : (skipDir || err.direction || 1)
            resetSkipGate()
            if (dir === 0) continue
            i = dir < 0 ? Math.max(0, i - 1) : i + 1
            continue
          }
          throw err
        }
      }
      host.setStatus?.('')
      host.setDemoNav?.(null)
    } catch (err) {
      stopAudio()
      host.setStatus?.('')
      host.setDemoNav?.(null)
      if (err instanceof DemoAborted) return
      throw err
    } finally {
      stopAudio()
    }
  }

  return {
    abort: () => {
      paused = false
      notifyPause()
      abort.abort()
      stopAudio()
      host.setDemoPaused?.(false)
    },
    skipPrev: () => requestSkip(-1),
    skipNext: () => requestSkip(1),
    setVoiceLang,
    get voiceLang() { return voiceLang },
    togglePause: () => setPaused(!paused),
    pause: () => setPaused(true),
    resume: () => setPaused(false),
    get paused() { return paused },
    get aborted() { return abort.signal.aborted },
    run,
  }
}

export function parseCursorTimes(times, unit, timeScale) {
  return splitCsv(times).map(t => demoTimeToTraceUnits(t, unit, timeScale))
}
