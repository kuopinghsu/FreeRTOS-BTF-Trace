import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import { InteractionHandler } from '../src/renderer/InteractionHandler.js'
import { RULER_H } from '../src/renderer/TimelineRenderer.js'

function mockEl() {
  const listeners = Object.create(null)
  return {
    style: {},
    listeners,
    addEventListener(type, fn, opts) {
      const key = opts?.capture ? `${type}:capture` : type
      ;(listeners[key] ||= []).push(fn)
    },
    removeEventListener() {},
    getBoundingClientRect() {
      return { left: 0, top: 0, width: 800, height: 600 }
    },
  }
}

function fire(el, type, props = {}, capture = false) {
  const key = capture ? `${type}:capture` : type
  const ev = {
    button: 0,
    buttons: 1,
    ctrlKey: false,
    metaKey: false,
    shiftKey: false,
    clientX: 120,
    clientY: RULER_H + 40,
    preventDefault() { ev.prevented = true },
    target: el,
    ...props,
  }
  for (const fn of el.listeners[key] || []) fn(ev)
  return ev
}

describe('Ctrl+left-drag measure ruler', () => {
  it('does not open the context menu on Ctrl+left (macOS contextmenu)', () => {
    const canvas = mockEl()
    let menus = 0
    let measures = 0
    const handler = new InteractionHandler(canvas, {
      getTrace: () => ({ timeMin: 0, timeMax: 1e9, timeScale: 'ns', tasks: [] }),
      getViewport: () => ({
        timeStart: 0, timeEnd: 1e9, canvasW: 800, canvasH: 600, scrollY: 0,
      }),
      getOptions: () => ({ orientation: 'h' }),
      onContextMenu() { menus += 1 },
      onMeasureChange() { measures += 1 },
    })
    fire(canvas, 'mousedown', { button: 0, ctrlKey: true, clientY: RULER_H + 40 })
    fire(canvas, 'contextmenu', { ctrlKey: true, clientY: RULER_H + 40 }, true)
    assert.equal(handler._measureDragging, true)
    assert.ok(measures >= 1)
    assert.equal(menus, 0)
    handler.destroy()
  })

  it('still opens the menu on a normal right-click', () => {
    const canvas = mockEl()
    let menus = 0
    const handler = new InteractionHandler(canvas, {
      getTrace: () => null,
      getViewport: () => ({
        timeStart: 0, timeEnd: 1e9, canvasW: 800, canvasH: 600, scrollY: 0,
      }),
      getOptions: () => ({ orientation: 'h' }),
      onContextMenu() { menus += 1 },
    })
    const ev = fire(canvas, 'contextmenu', {
      button: 2, ctrlKey: false, clientY: RULER_H + 40,
    }, true)
    assert.equal(ev.prevented, true)
    assert.equal(menus, 1)
    handler.destroy()
  })
})
