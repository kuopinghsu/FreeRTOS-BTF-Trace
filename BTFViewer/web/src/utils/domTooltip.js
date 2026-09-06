/**
 * In-page hover tips for elements with a `title` attribute.
 *
 * Native browser tooltips are drawn outside the page and are not included in
 * tab capture (`getDisplayMedia` / MediaRecorder). These tips live in the DOM
 * so demos and screen recordings show the same captions.
 */

const STYLE_ID = 'btf-dom-tooltip-style'
const TIP_CLASS = 'btf-dom-tooltip'
const STASH = 'data-btf-title'
const SHOW_DELAY_MS = 420
const HIDE_GRACE_MS = 80

/** @type {HTMLElement | null} */
let tipEl = null
/** @type {Element | null} */
let activeEl = null
/** @type {ReturnType<typeof setTimeout> | null} */
let showTimer = null
/** @type {ReturnType<typeof setTimeout> | null} */
let hideTimer = null
let installed = false

function clearTimers() {
  if (showTimer != null) {
    clearTimeout(showTimer)
    showTimer = null
  }
  if (hideTimer != null) {
    clearTimeout(hideTimer)
    hideTimer = null
  }
}

export function tipTextFromElement(el) {
  if (!el || typeof el.getAttribute !== 'function') return ''
  const live = el.getAttribute('title')
  if (live != null && String(live).trim()) return String(live).trim()
  const stashed = el.getAttribute(STASH)
  if (stashed != null && String(stashed).trim()) return String(stashed).trim()
  return ''
}

/** Walk up from *node* to the nearest titled ancestor (skips the tip itself). */
export function closestTitledElement(node) {
  let el = node
  while (el && el.nodeType === 1) {
    if (el.classList?.contains?.(TIP_CLASS)) return null
    if (tipTextFromElement(el)) return el
    el = el.parentElement
  }
  return null
}

/**
 * Place a tip box near *anchor* (client rect), keeping it inside the viewport.
 * @returns {{ left: number, top: number }}
 */
export function placeTipBox(anchor, tipW, tipH, pad = 8, gap = 6) {
  const vw = typeof window !== 'undefined' ? window.innerWidth : 1024
  const vh = typeof window !== 'undefined' ? window.innerHeight : 768
  const aw = Number(anchor?.width) || 0
  const ah = Number(anchor?.height) || 0
  const ax = Number(anchor?.left) || 0
  const ay = Number(anchor?.top) || 0
  let left = ax + aw / 2 - tipW / 2
  let top = ay + ah + gap
  if (top + tipH + pad > vh) top = ay - tipH - gap
  if (top < pad) top = pad
  left = Math.max(pad, Math.min(left, vw - tipW - pad))
  return { left: Math.round(left), top: Math.round(top) }
}

// Read live theme values off the real .app root and copy them onto the tip
// element as inline custom properties before every show. The tip element
// lives under <html> (ensureTip() appends it to document.documentElement,
// a sibling of <body>/.app, not a descendant of either) so App.vue's own
// theme rules — scoped to ".app:not(.dark)" and "body:has(.app:not(.dark))"
// for light theme — never reach it via normal CSS inheritance; only the
// dark values happen to reach it, via :root's own (dark) defaults, which is
// why this was invisible in dark theme and only showed up in light theme.
// Setting these directly on the tip element sidesteps the whole cascade
// question and always reflects whatever the app is actually showing right
// now, including a user's custom UI font size.
//
// Colors are inverted (background: --fg, color: --bg), not matched to the
// panel — the same formula the left/right rail's own built-in tooltips
// (.rail-tip / .act-tip in App.vue) already use: dark app -> light tip,
// light app -> dark tip. One tooltip color language for the whole app,
// rather than adding a second "matches the panel" one here.
const SYNCED_VARS = ['--fg', '--bg', '--font-ui', '--type-meta', '--ui-font-size']

function syncThemeVars(tip) {
  if (typeof document === 'undefined' || typeof getComputedStyle === 'undefined') return
  const root = document.querySelector('.app') || document.documentElement
  const cs = getComputedStyle(root)
  for (const name of SYNCED_VARS) {
    const val = cs.getPropertyValue(name)
    if (val && val.trim()) tip.style.setProperty(name, val.trim())
  }
}

function ensureStyle() {
  if (typeof document === 'undefined') return
  if (document.getElementById(STYLE_ID)) return
  const style = document.createElement('style')
  style.id = STYLE_ID
  style.textContent = `
.${TIP_CLASS} {
  position: fixed;
  left: 0; top: 0;
  max-width: min(28rem, calc(100vw - 16px));
  margin: 0; padding: 0.35em 0.6em;
  border-radius: 4px;
  background: var(--fg, #1a1a1a);
  color: var(--bg, #f7f7f7);
  box-shadow: 0 2px 8px rgba(0,0,0,0.28);
  font-family: var(--font-ui, system-ui, sans-serif);
  font-size: var(--type-meta, var(--ui-font-size, 13px));
  line-height: 1.35;
  pointer-events: none;
  z-index: 2147483646;
  white-space: pre-wrap;
  word-break: break-word;
  opacity: 0;
  transform: translateY(2px);
  transition: opacity 80ms ease, transform 80ms ease;
}
.${TIP_CLASS}.btf-dom-tooltip-show {
  opacity: 1;
  transform: translateY(0);
}
`
  document.head.appendChild(style)
}

function ensureTip() {
  if (typeof document === 'undefined') return null
  ensureStyle()
  if (tipEl) return tipEl
  tipEl = document.createElement('div')
  tipEl.className = TIP_CLASS
  tipEl.setAttribute('role', 'tooltip')
  tipEl.setAttribute('aria-hidden', 'true')
  document.documentElement.appendChild(tipEl)
  return tipEl
}

function stashTitle(el) {
  if (!el || typeof el.getAttribute !== 'function') return
  const t = el.getAttribute('title')
  if (t == null || !String(t).trim()) return
  if (!el.getAttribute(STASH)) el.setAttribute(STASH, t)
  el.removeAttribute('title')
}

function restoreTitle(el) {
  if (!el || typeof el.getAttribute !== 'function') return
  const t = el.getAttribute(STASH)
  if (t == null) return
  if (!el.getAttribute('title')) el.setAttribute('title', t)
  el.removeAttribute(STASH)
}

function hideTipNow() {
  clearTimers()
  if (activeEl) {
    restoreTitle(activeEl)
    activeEl = null
  }
  if (tipEl) {
    tipEl.classList.remove('btf-dom-tooltip-show')
    tipEl.textContent = ''
    tipEl.style.visibility = 'hidden'
  }
}

function showTipFor(el) {
  const text = tipTextFromElement(el)
  if (!text) return
  const tip = ensureTip()
  if (!tip || typeof el.getBoundingClientRect !== 'function') return
  clearTimers()
  if (activeEl && activeEl !== el) restoreTitle(activeEl)
  activeEl = el
  stashTitle(el)
  syncThemeVars(tip)
  tip.textContent = text
  tip.style.visibility = 'hidden'
  tip.classList.remove('btf-dom-tooltip-show')
  // Measure after text is set
  const tw = tip.offsetWidth || 160
  const th = tip.offsetHeight || 28
  const { left, top } = placeTipBox(el.getBoundingClientRect(), tw, th)
  tip.style.left = `${left}px`
  tip.style.top = `${top}px`
  tip.style.visibility = 'visible'
  tip.classList.add('btf-dom-tooltip-show')
}

function scheduleShow(el) {
  clearTimers()
  showTimer = setTimeout(() => {
    showTimer = null
    if (closestTitledElement(el) === el || tipTextFromElement(el)) showTipFor(el)
  }, SHOW_DELAY_MS)
}

function scheduleHide() {
  if (hideTimer != null) clearTimeout(hideTimer)
  hideTimer = setTimeout(() => {
    hideTimer = null
    hideTipNow()
  }, HIDE_GRACE_MS)
}

function onPointerOver(e) {
  const el = closestTitledElement(e.target)
  if (!el) {
    if (activeEl || showTimer) scheduleHide()
    return
  }
  if (hideTimer != null) {
    clearTimeout(hideTimer)
    hideTimer = null
  }
  if (el === activeEl) return
  if (activeEl) hideTipNow()
  scheduleShow(el)
}

function onPointerOut(e) {
  const to = e.relatedTarget
  if (to && (closestTitledElement(to) === activeEl || to === tipEl || tipEl?.contains?.(to))) {
    return
  }
  const from = closestTitledElement(e.target)
  if (!from && !activeEl && !showTimer) return
  scheduleHide()
}

function onScroll() {
  if (activeEl || showTimer) hideTipNow()
}

function onKeyDown(e) {
  if (e.key === 'Escape') hideTipNow()
}

/**
 * Install document-level listeners. Safe to call more than once.
 * @returns {() => void} uninstall
 */
export function installDomTooltips() {
  if (typeof document === 'undefined') return () => {}
  if (installed) return uninstallDomTooltips
  installed = true
  ensureStyle()
  document.addEventListener('pointerover', onPointerOver, true)
  document.addEventListener('pointerout', onPointerOut, true)
  document.addEventListener('focusin', onPointerOver, true)
  document.addEventListener('focusout', onPointerOut, true)
  window.addEventListener('scroll', onScroll, true)
  window.addEventListener('keydown', onKeyDown, true)
  return uninstallDomTooltips
}

export function uninstallDomTooltips() {
  if (!installed || typeof document === 'undefined') return
  installed = false
  document.removeEventListener('pointerover', onPointerOver, true)
  document.removeEventListener('pointerout', onPointerOut, true)
  document.removeEventListener('focusin', onPointerOver, true)
  document.removeEventListener('focusout', onPointerOut, true)
  window.removeEventListener('scroll', onScroll, true)
  window.removeEventListener('keydown', onKeyDown, true)
  hideTipNow()
  tipEl?.remove()
  tipEl = null
  document.getElementById(STYLE_ID)?.remove()
}
