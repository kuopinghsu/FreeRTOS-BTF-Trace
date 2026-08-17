/**
 * Synthetic pointer overlay for web demo / tab recording.
 *
 * The browser cannot move the OS cursor. This paints an in-page arrow, animates
 * it to demo XML targets, and dispatches hover events so timeline tooltips track.
 * Recording reuses the same overlay (follow-mouse) so tab capture includes it.
 * A parked demo overlay hides as soon as the user moves the real mouse.
 */

const STYLE_ID = 'btf-demo-cursor-style'
const CURSOR_SVG = `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" aria-hidden="true">
  <path fill="#fff" stroke="#111" stroke-linejoin="round" stroke-width="1.4"
    d="M5 3.2v17.4l4.5-4.6 2.9 6.9 2.4-1-2.9-6.8H18z"/>
</svg>`

const owners = new Set()
let el = null
let pos = { x: 0, y: 0 }
let hasPos = false
let anim = null
let animResolve = null
let followMove = null
let followOut = null
let overlayHidden = false

function now() {
  return typeof performance !== 'undefined' ? performance.now() : Date.now()
}

function raf(fn) {
  if (typeof requestAnimationFrame === 'function') return requestAnimationFrame(fn)
  return setTimeout(() => fn(now()), 16)
}

function caf(id) {
  if (typeof cancelAnimationFrame === 'function') cancelAnimationFrame(id)
  else clearTimeout(id)
}

function easeInOutCubic(t) {
  return t < 0.5 ? 4 * t * t * t : 1 - ((-2 * t + 2) ** 3) / 2
}

function ensureStyle() {
  if (typeof document === 'undefined') return
  if (document.getElementById(STYLE_ID)) return
  const style = document.createElement('style')
  style.id = STYLE_ID
  style.textContent = `
html.btf-hide-native-cursor, html.btf-hide-native-cursor * { cursor: none !important; }
.btf-demo-cursor {
  position: fixed; left: 0; top: 0; width: 24px; height: 24px;
  margin: 0; padding: 0; pointer-events: none; z-index: 2147483647;
  filter: drop-shadow(0 1px 1px rgba(0,0,0,.45));
  will-change: transform;
}
.btf-demo-cursor svg { display: block; width: 24px; height: 24px; }
`
  document.head.appendChild(style)
}

function applyTransform() {
  if (!el) return
  el.style.transform = `translate3d(${pos.x}px, ${pos.y}px, 0)`
  el.style.visibility = overlayHidden ? 'hidden' : 'visible'
}

function hideOverlay() {
  overlayHidden = true
  if (anim != null) {
    caf(anim)
    anim = null
  }
  if (animResolve) {
    const done = animResolve
    animResolve = null
    done()
  }
  if (el) el.style.visibility = 'hidden'
}

function showOverlay() {
  overlayHidden = false
  applyTransform()
}

export function dispatchHoverAt(x, y) {
  if (typeof document === 'undefined') return
  const stack = typeof document.elementsFromPoint === 'function'
    ? document.elementsFromPoint(x, y)
    : [document.elementFromPoint(x, y)].filter(Boolean)
  const canvas = stack.find(n => n && n.tagName === 'CANVAS')
  const target = canvas || stack[0]
  if (!target) return
  const opts = {
    bubbles: true,
    cancelable: true,
    clientX: x,
    clientY: y,
    view: typeof window !== 'undefined' ? window : undefined,
  }
  try {
    target.dispatchEvent(new PointerEvent('pointermove', {
      ...opts, pointerId: 1, pointerType: 'mouse',
    }))
  } catch { /* jsdom */ }
  target.dispatchEvent(new MouseEvent('mousemove', opts))
}

export function dispatchClickAt(x, y) {
  if (typeof document === 'undefined') return
  const stack = typeof document.elementsFromPoint === 'function'
    ? document.elementsFromPoint(x, y)
    : [document.elementFromPoint(x, y)].filter(Boolean)
  const target = stack.find(n => n && n.tagName === 'CANVAS')
    || stack.find(n => n && !n.closest?.('.demo-status-banner'))
    || stack[0]
  if (!target) return
  const opts = {
    bubbles: true,
    cancelable: true,
    clientX: x,
    clientY: y,
    button: 0,
    view: typeof window !== 'undefined' ? window : undefined,
  }
  target.dispatchEvent(new MouseEvent('mousedown', opts))
  target.dispatchEvent(new MouseEvent('mouseup', opts))
  target.dispatchEvent(new MouseEvent('click', opts))
}

function setPos(x, y, hover = true) {
  pos = { x, y }
  hasPos = true
  applyTransform()
  if (hover) dispatchHoverAt(x, y)
}

function wantFollowMouse() {
  return owners.has('record') && !owners.has('demo')
}

/** Hide OS cursor only when a scripted overlay is the pointer of record. Unused. */
export function shouldHideNativeCursor(_ownerList) {
  return false
}

/** Real (trusted) mouse motion hides the parked demo overlay. */
export function shouldHideSimulatedCursorOnMove(event, ownerList) {
  if (!event?.isTrusted) return false
  const set = ownerList instanceof Set ? ownerList : new Set(ownerList || [])
  if (set.has('record') && !set.has('demo')) return false
  return set.has('demo')
}

function wantHideNative() {
  return shouldHideNativeCursor(owners)
}

function onUserPointerMove(e) {
  if (!e.isTrusted) return
  if (wantFollowMouse()) {
    overlayHidden = false
    pos = { x: e.clientX, y: e.clientY }
    hasPos = true
    applyTransform()
    return
  }
  if (shouldHideSimulatedCursorOnMove(e, owners)) hideOverlay()
}

function syncFollowMouse() {
  if (typeof window === 'undefined' || typeof document === 'undefined') return
  const needListen = owners.size > 0
  if (needListen && !followMove) {
    followMove = onUserPointerMove
    followOut = (e) => {
      if (!e.relatedTarget && el && wantFollowMouse()) el.style.visibility = 'hidden'
    }
    window.addEventListener('pointermove', followMove, true)
    window.addEventListener('mousemove', followMove, true)
    document.addEventListener('mouseout', followOut, true)
  }
  if (!needListen && followMove) {
    window.removeEventListener('pointermove', followMove, true)
    window.removeEventListener('mousemove', followMove, true)
    document.removeEventListener('mouseout', followOut, true)
    followMove = null
    followOut = null
  }
  document.documentElement.classList.toggle('btf-hide-native-cursor', wantHideNative())
}

function ensureDom() {
  if (typeof document === 'undefined') return
  ensureStyle()
  if (el) return
  el = document.createElement('div')
  el.className = 'btf-demo-cursor'
  el.setAttribute('aria-hidden', 'true')
  el.innerHTML = CURSOR_SVG
  document.documentElement.appendChild(el)
  applyTransform()
}

function destroyDom() {
  if (anim != null) {
    caf(anim)
    anim = null
  }
  if (typeof window !== 'undefined' && followMove) {
    window.removeEventListener('pointermove', followMove, true)
    window.removeEventListener('mousemove', followMove, true)
    followMove = null
  }
  if (typeof document !== 'undefined' && followOut) {
    document.removeEventListener('mouseout', followOut, true)
    followOut = null
    document.documentElement.classList.remove('btf-hide-native-cursor')
  }
  el?.remove()
  el = null
  hasPos = false
  overlayHidden = false
  animResolve = null
}

export function acquirePointer(owner) {
  owners.add(owner)
  ensureDom()
  syncFollowMouse()
  return {
    moveTo,
    clickAt: (x, y) => { setPos(x, y); dispatchClickAt(x, y) },
    release: () => releasePointer(owner),
  }
}

export function releasePointer(owner) {
  if (!owners.has(owner)) return
  owners.delete(owner)
  if (!owners.size) destroyDom()
  else syncFollowMouse()
}

export async function moveTo(x, y, durationSec = 0, signal = null) {
  ensureDom()
  showOverlay()
  if (!hasPos) setPos(x, Math.max(8, y - 64), false)
  const dur = Math.max(0, Number(durationSec) || 0) * 1000
  if (dur <= 0 || typeof document === 'undefined') {
    setPos(x, y)
    return
  }
  if (anim != null) {
    caf(anim)
    anim = null
  }
  if (animResolve) {
    const prev = animResolve
    animResolve = null
    prev()
  }
  const x0 = pos.x
  const y0 = pos.y
  const start = now()
  await new Promise((resolve) => {
    animResolve = resolve
    const finish = () => {
      anim = null
      animResolve = null
      resolve()
    }
    const tick = (t) => {
      if (signal?.aborted || overlayHidden) {
        finish()
        return
      }
      const p = Math.min(1, (t - start) / dur)
      const e = easeInOutCubic(p)
      setPos(x0 + (x - x0) * e, y0 + (y - y0) * e)
      if (p < 1) anim = raf(tick)
      else finish()
    }
    anim = raf(tick)
  })
}
